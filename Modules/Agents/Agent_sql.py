import json
import re
import time

from config import GROQ_MODEL, client
from Modules.prompt_builder import build_prompt
from Modules.sql_executor import execute_sql
from Modules.sql_guard import check_read_only, GuardError
from Modules.sql_validator import validate_query
from Modules.sql_generator import complete_json, generate_sql, extract_sql, clean_sql


MAX_ATTEMPTS = 3

# A response that starts like this is a request to change data or the
# engine, not a query. It is stopped as a safety problem and never retried.
_WRITE_START = re.compile(
    r"^\s*(?:```\w*\s*)?(?:DELETE|UPDATE|INSERT|DROP|CREATE|ALTER|TRUNCATE|"
    r"COPY|ATTACH|DETACH|PRAGMA|INSTALL|LOAD|SET|EXPORT|CALL|MERGE|GRANT)\b",
    re.IGNORECASE,
)

# Only errors the model can plausibly fix itself are retried.
# Refusals ("INVALID QUERY"), format failures, API errors, validator crashes
# and anything the safety guard calls unsafe ("safety") STOP immediately.
# "syntax" = the guard could not parse the query or found several statements.
RETRYABLE_STAGES = {"syntax", "schema_validation", "execution"}

EMPTY_RESULT_FEEDBACK = (
    "The query ran but returned 0 rows. The data may not cover the period "
    "you filtered on. Do NOT filter relative to today's date (no current_date or now()); "
    "check DATA COVERAGE at the top of the schema, or remove the date filter."
)


def _result(success, stage, error=None, raw_response=None, sql=None,
            validation=None, result=None,
            generation_time=0, validation_time=0, execution_time=0):
    """Every return path goes through here, so the dict always has the
    same keys."""
    return {
        "success": success,
        "stage": stage,
        "error": error,
        "raw_response": raw_response,
        "sql": sql,
        "validation": validation,
        "result": result,
        "generation_time": generation_time,
        "validation_time": validation_time,
        "execution_time": execution_time,
    }


def _clean_db_error(message, limit=600):
    """Keep only the database's own message: drop the echoed SQL and the
    SQLAlchemy 'Background on this error' link."""
    msg = str(message).split("[SQL:")[0]
    msg = msg.split("(Background on this error")[0]
    return " ".join(msg.split())[:limit]


def repair_sql(question, schema, bad_sql, problem):
    """Ask the model to correct its own query, as a continuation of the
    original conversation (original prompt -> its answer -> the problem)."""
    previous = json.dumps({"status": "ok", "sql": bad_sql,
                           "assumptions": [], "reason": None})
    messages = [
        {"role": "user", "content": build_prompt(schema, question)},
        {"role": "assistant", "content": previous},
        {
            "role": "user",
            "content": (
                "That answer is not acceptable.\n"
                f"PROBLEM: {problem}\n"
                "Return a corrected answer as the same JSON object (status, "
                "sql, assumptions, reason). Follow ALL the rules above. The "
                "sql must be one DuckDB query starting with SELECT or WITH "
                "and ending with a semicolon."
            ),
        },
    ]
    return complete_json(messages, GROQ_MODEL)


def _feedback_for(out):
    """Turn a failed attempt into the problem statement sent to the model."""
    if out["stage"] == "schema_validation":
        errors = (out["validation"] or {}).get("schema_errors") or []
        return (
            "The query references database objects that do not exist: "
            + "; ".join(errors)
            + ". Use ONLY tables and columns from the schema."
        )
    if out["stage"] == "syntax":
        return (
            "The query is not one valid read-only DuckDB SELECT statement: "
            + _clean_db_error(out["error"])
            + " Return exactly one SELECT or WITH query."
        )
    return "DuckDB rejected the query: " + _clean_db_error(out["error"])


# ============================================================
# ONE ATTEMPT
# stages: generation -> extraction -> validation / schema_validation
#         -> execution -> completed
# ============================================================

def _run_once(question, schema, db, feedback=None):
    """feedback is None on the first attempt, or (bad_sql, problem).
    db is the Database object (Modules/engine_duckdb.py) of this session."""

    # ---- 1. SQL GENERATION (or repair) -----------------------
    start = time.perf_counter()
    try:
        if feedback is None:
            raw_response = generate_sql(question, schema, GROQ_MODEL)
        else:
            bad_sql, problem = feedback
            raw_response = repair_sql(question, schema, bad_sql, problem)
    except Exception as e:
        return _result(False, "generation", error=str(e),
                       generation_time=time.perf_counter() - start)
    generation_time = time.perf_counter() - start

    # ---- 2. SQL EXTRACTION (extract -> clean -> dialect fix) --
    try:
        sql = clean_sql(extract_sql(raw_response))
    except Exception as e:
        if _WRITE_START.match(raw_response or ""):
            return _result(False, "safety",
                           error="Only read-only SELECT queries are allowed "
                                 "(the request asks to change data).",
                           raw_response=raw_response,
                           generation_time=generation_time)
        return _result(False, "extraction", error=str(e),
                       raw_response=raw_response,
                       generation_time=generation_time)

    # ---- 3. THE MODEL'S OWN "INVALID QUERY" FALLBACK ----------
    if not sql or "SELECT 'INVALID QUERY'" in sql.upper():
        return _result(False, "extraction",
                       error="No valid SQL query was produced.",
                       raw_response=raw_response,
                       generation_time=generation_time)

    # ---- 3b. SAFETY GUARD (syntax-tree check) ------------------
    try:
        check_read_only(sql)
    except GuardError as e:
        return _result(False, "syntax" if e.retryable else "safety",
                       error=str(e), raw_response=raw_response, sql=sql,
                       generation_time=generation_time)

    # ---- 4. SCHEMA VALIDATION ---------------------------------
    start = time.perf_counter()
    try:
        validation = validate_query(sql, db)
    except Exception as e:
        return _result(False, "validation", error=str(e),
                       raw_response=raw_response, sql=sql,
                       generation_time=generation_time,
                       validation_time=time.perf_counter() - start)
    validation_time = time.perf_counter() - start

    # ---- 5. REJECT SCHEMA-INCOMPATIBLE QUERY ------------------
    if not validation.get("schema_valid", False):
        return _result(False, "schema_validation",
                       error="Query rejected because of schema incompatibility.",
                       raw_response=raw_response, sql=sql,
                       validation=validation,
                       generation_time=generation_time,
                       validation_time=validation_time)

    # ---- 6. SQL EXECUTION -------------------------------------
    start = time.perf_counter()
    try:
        result = execute_sql(sql, db)
    except Exception as e:
        return _result(False, "execution", error=str(e),
                       raw_response=raw_response, sql=sql,
                       validation=validation,
                       generation_time=generation_time,
                       validation_time=validation_time,
                       execution_time=time.perf_counter() - start)
    execution_time = time.perf_counter() - start

    # ---- 7. SUCCESS -------------------------------------------
    return _result(True, "completed",
                   raw_response=raw_response, sql=sql,
                   validation=validation, result=result,
                   generation_time=generation_time,
                   validation_time=validation_time,
                   execution_time=execution_time)


# ============================================================
# SQL GENERATION AGENT (bounded self-correction loop)
# ============================================================

def sql_agent(question, schema, db, max_attempts=MAX_ATTEMPTS):
    """Run the pipeline; on a fixable failure, send the error back to the
    model and try again, up to max_attempts.

    Returns the same dict as before, plus:
      attempts : number of attempts made
      history  : [{attempt, stage, sql, error}, ...] one entry per attempt
    Times are summed over all attempts.
    """
    history = []
    totals = {"generation_time": 0, "validation_time": 0, "execution_time": 0}
    feedback = None
    empty_fallback = None
    out = None

    for attempt in range(1, max_attempts + 1):
        out = _run_once(question, schema, db, feedback)
        for key in totals:
            totals[key] += out[key]

        entry = {"attempt": attempt, "stage": out["stage"],
                 "sql": out["sql"], "error": out["error"]}

        if out["success"]:
            df = out["result"]
            # A valid query with 0 rows is retried once: it is often a wrong
            # (e.g. relative-date) filter rather than a truly empty answer.
            if (df is not None and df.empty
                    and empty_fallback is None and attempt < max_attempts):
                entry["error"] = "Query returned 0 rows"
                history.append(entry)
                empty_fallback = out
                feedback = (out["sql"], EMPTY_RESULT_FEEDBACK)
                continue
            history.append(entry)
            break

        history.append(entry)
        if out["stage"] not in RETRYABLE_STAGES:
            break
        feedback = (out["sql"], _feedback_for(out))

    final = out
    if empty_fallback is not None:
        got_data = (out["success"] and out["result"] is not None
                    and not out["result"].empty)
        if not got_data:
            final = empty_fallback  # a successful, genuinely empty answer

    final = dict(final)
    final.update(totals)
    final["attempts"] = len(history)
    final["history"] = history
    return final