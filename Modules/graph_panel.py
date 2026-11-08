"""
Modules/graph_panel.py

The Query Generation Agent as a LangGraph graph.

It turns ONE question into a query that is safe, valid, executed and checked
against the question, and repairs it when a check fails. Each step is a node,
each decision a conditional edge, and the path taken is recorded, so it can be
drawn, logged and evaluated.

    START -> generate -> extract -> safety -> schema_check -> execute
                            ^                                    |
                            |                                    v
                         repair <------------------------- semantic_check
                                                                 |
                                                                 v
                                                      check -> finish -> END

Nodes
    generate        first call to the language model (answer = JSON)
    extract         read the answer: status ok / ambiguous give a query;
                    unsupported / blocked stop here with a reason; the old
                    bare-SQL format is still understood
    safety          syntax-tree guard (one read-only SELECT)
    schema_check    DuckDB binds the query: unknown tables or columns
    execute         run it (timeout, row cap)
    semantic_check  does the result answer the question? (Modules/semantic_checks.py)
                    errors go back to repair, warnings become notes
    check           success? an empty result gets one extra try
    repair          second and third call to the model, with the problem
    finish          build the final dictionary

Stages. Retried: syntax, schema_validation, execution, semantic.
Stopped at once: generation (API error), extraction, safety, unsupported,
blocked, repeated_sql (the repair returned the same query).

A semantic problem never destroys a good result: if the budget runs out, the
last result that executed is returned with the unresolved problems as notes.

The Database is not stored in the graph state (it is not serialisable):
build_panel_graph(db) captures it, so one graph belongs to one session.
"""
import operator
import time
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from config import GROQ_MODEL
from Modules.Agents.Agent_sql import (
    EMPTY_RESULT_FEEDBACK,
    MAX_ATTEMPTS,
    RETRYABLE_STAGES,
    _WRITE_START,
    _feedback_for,
    repair_sql,
)
from Modules.schemas import SQLAnswer, parse_sql_answer
from Modules.semantic_checks import check_result, format_problem
from Modules.sql_executor import execute_sql
from Modules.sql_generator import clean_sql, extract_sql, generate_sql
from Modules.sql_guard import GuardError, check_read_only
from Modules.sql_validator import validate_query

RETRYABLE = set(RETRYABLE_STAGES) | {"semantic"}


class PanelState(TypedDict, total=False):
    # inputs
    question: str
    schema: str
    max_attempts: int
    kind: Optional[str]               # kpi, bar, line, pie, table, or None
    constraints: Any                  # Constraints from the planner, or None
    # control
    attempt: int
    feedback: Optional[tuple]         # (bad_sql, problem) for the next repair
    failed: bool
    retry: bool
    empty_fallback: Optional[dict]
    last_good: Optional[dict]         # the last result that executed
    # the current attempt
    raw_response: Optional[str]
    sql: Optional[str]
    validation: Optional[dict]
    result: Any                       # a DataFrame
    stage: str
    status: str                       # ok, ambiguous, unsupported, blocked
    assumptions: list
    issues: list
    error: Optional[str]
    success: bool
    # accumulated over the whole run
    history: Annotated[list, operator.add]
    path: Annotated[list, operator.add]
    notes: Annotated[list, operator.add]
    generation_time: Annotated[float, operator.add]
    validation_time: Annotated[float, operator.add]
    execution_time: Annotated[float, operator.add]
    # output
    final: dict


_ATTEMPT_RESET = {
    "failed": False, "retry": False, "sql": None, "validation": None,
    "result": None, "error": None, "stage": "generation", "success": False,
    "status": "ok", "assumptions": [], "issues": [],
}


def _norm(sql):
    """Compare two queries ignoring case, spaces and semicolons."""
    return " ".join(str(sql).lower().replace(";", " ").split())


def _fail(state, node, stage, error, sql=None, validation=None, **extra):
    """What a failing node returns: the failure, the history entry for this
    attempt and, when the model can fix it, the problem statement."""
    feedback = None
    if stage == "semantic":
        feedback = (sql, error)
    elif stage in RETRYABLE:
        feedback = (sql, _feedback_for(
            {"stage": stage, "validation": validation, "error": error}))
    update = {
        "failed": True, "stage": stage, "error": error, "success": False,
        "sql": sql, "validation": validation, "feedback": feedback,
        "history": [{"attempt": state["attempt"], "stage": stage,
                     "sql": sql, "error": error}],
        "path": [node],
    }
    update.update(extra)
    return update


def _router(next_node):
    """After a node: continue, repair, or finish."""
    def route(state):
        if not state.get("failed"):
            return next_node
        if state.get("stage") in RETRYABLE and state["attempt"] < state["max_attempts"]:
            return "repair"
        return "finish"
    return route


def build_panel_graph(db):
    """Build and compile the graph for one session's Database."""

    # ---- generate -------------------------------------------------------
    def generate(state):
        start = time.perf_counter()
        update = dict(_ATTEMPT_RESET, attempt=1, feedback=None, path=["generate"])
        try:
            raw = generate_sql(state["question"], state["schema"], GROQ_MODEL)
        except Exception as e:
            update.update(_fail(state | {"attempt": 1}, "generate", "generation", str(e)))
            update["generation_time"] = time.perf_counter() - start
            update["raw_response"] = None
            return update
        update["raw_response"] = raw
        update["generation_time"] = time.perf_counter() - start
        return update

    # ---- repair ---------------------------------------------------------
    def repair(state):
        start = time.perf_counter()
        attempt = state["attempt"] + 1
        bad_sql, problem = state["feedback"]
        update = dict(_ATTEMPT_RESET, attempt=attempt, path=["repair"])
        try:
            raw = repair_sql(state["question"], state["schema"], bad_sql, problem)
        except Exception as e:
            update.update(_fail(state | {"attempt": attempt}, "repair", "generation", str(e)))
            update["generation_time"] = time.perf_counter() - start
            update["raw_response"] = None
            update["feedback"] = state["feedback"]
            return update
        update["raw_response"] = raw
        update["generation_time"] = time.perf_counter() - start
        return update

    # ---- extract --------------------------------------------------------
    def extract(state):
        raw = state.get("raw_response")
        answer = None
        try:
            answer = parse_sql_answer(raw)
        except ValueError:
            answer = None             # not JSON: an older bare-SQL answer

        extra = {}
        if answer is not None:
            if answer.status in ("unsupported", "blocked"):
                return _fail(state, "extract", answer.status, answer.reason,
                             status=answer.status)
            extra = {"status": answer.status, "assumptions": list(answer.assumptions)}
            candidate = answer.sql
        else:
            candidate = raw

        try:
            sql = clean_sql(extract_sql(candidate))
        except Exception as e:
            if _WRITE_START.match(raw or ""):
                return _fail(state, "extract", "safety",
                             "Only read-only SELECT queries are allowed "
                             "(the request asks to change data).")
            return _fail(state, "extract", "extraction", str(e))
        if not sql or "SELECT 'INVALID QUERY'" in sql.upper():
            return _fail(state, "extract", "extraction",
                         "No valid SQL query was produced.")
        previous = (state.get("feedback") or (None,))[0]
        if previous and _norm(sql) == _norm(previous):
            return _fail(state, "extract", "repeated_sql",
                         "The model returned the same query again.", sql=sql)
        return dict(extra, sql=sql, path=["extract"])

    # ---- safety ---------------------------------------------------------
    def safety(state):
        try:
            check_read_only(state["sql"])
        except GuardError as e:
            return _fail(state, "safety", "syntax" if e.retryable else "safety",
                         str(e), sql=state["sql"])
        return {"path": ["safety"]}

    # ---- schema_check ---------------------------------------------------
    def schema_check(state):
        start = time.perf_counter()
        try:
            validation = validate_query(state["sql"], db)
        except Exception as e:
            return _fail(state, "schema_check", "validation", str(e),
                         sql=state["sql"],
                         validation_time=time.perf_counter() - start)
        elapsed = time.perf_counter() - start
        if not validation.get("schema_valid", False):
            return _fail(state, "schema_check", "schema_validation",
                         "Query rejected because of schema incompatibility.",
                         sql=state["sql"], validation=validation,
                         validation_time=elapsed)
        return {"validation": validation, "validation_time": elapsed,
                "path": ["schema_check"]}

    # ---- execute --------------------------------------------------------
    def execute(state):
        start = time.perf_counter()
        try:
            result = execute_sql(state["sql"], db)
        except Exception as e:
            return _fail(state, "execute", "execution", str(e),
                         sql=state["sql"], validation=state.get("validation"),
                         execution_time=time.perf_counter() - start)
        update = {"result": result, "execution_time": time.perf_counter() - start,
                  "path": ["execute"]}
        if not result.empty:          # remember it: a semantic nit must not lose it
            update["last_good"] = {
                "success": True, "stage": "completed", "error": None,
                "raw_response": state.get("raw_response"), "sql": state["sql"],
                "validation": state.get("validation"), "result": result,
                "status": state.get("status", "ok"),
                "assumptions": list(state.get("assumptions", []))}
        return update

    # ---- semantic_check -------------------------------------------------
    def semantic_check(state):
        df = state["result"]
        if df is None or df.empty:
            return {"path": ["semantic_check"]}      # the empty case is handled in check
        try:
            issues = check_result(state["question"], state.get("kind"),
                                  state.get("constraints"), state["sql"], df, db)
        except Exception:
            issues = []
        errors = [i for i in issues if i["severity"] == "error"]
        warnings = [i["message"] for i in issues if i["severity"] == "warning"]
        if errors:
            return _fail(state, "semantic_check", "semantic", format_problem(issues),
                         sql=state["sql"], validation=state.get("validation"),
                         issues=issues, result=df,
                         notes=warnings)
        return {"issues": issues, "notes": warnings, "path": ["semantic_check"]}

    # ---- check ----------------------------------------------------------
    def check(state):
        df = state["result"]
        entry = {"attempt": state["attempt"], "stage": "completed",
                 "sql": state["sql"], "error": None}
        update = {"success": True, "stage": "completed", "error": None,
                  "retry": False, "path": ["check"]}
        if (df is not None and df.empty and state.get("empty_fallback") is None
                and state["attempt"] < state["max_attempts"]):
            entry["error"] = "Query returned 0 rows"
            update["retry"] = True
            update["feedback"] = (state["sql"], EMPTY_RESULT_FEEDBACK)
            update["empty_fallback"] = {
                "success": True, "stage": "completed", "error": None,
                "raw_response": state.get("raw_response"), "sql": state["sql"],
                "validation": state.get("validation"), "result": df,
                "status": state.get("status", "ok"),
                "assumptions": list(state.get("assumptions", []))}
        update["history"] = [entry]
        return update

    # ---- finish ---------------------------------------------------------
    def finish(state):
        keys = ("success", "stage", "error", "raw_response", "sql",
                "validation", "result", "status", "assumptions")
        final = {k: state.get(k) for k in keys}
        notes = list(state.get("notes", []))
        fallback = state.get("empty_fallback")
        if fallback is not None:
            result = state.get("result")
            got_data = (bool(state.get("success")) and result is not None
                        and not result.empty)
            if not got_data:
                final = {k: fallback.get(k) for k in keys}   # a genuinely empty answer
        good = state.get("last_good")
        # A query ran earlier but a later step failed or a semantic problem
        # stayed unresolved: return the result that ran, with the problem as a note.
        if (not final.get("success") and good is not None
                and final.get("stage") in RETRYABLE | {"repeated_sql", "generation"}):
            if final.get("error"):
                notes.append("Unresolved: " + str(final["error"]).split("\n")[0][:200])
            final = {k: good.get(k) for k in keys}
        final.setdefault("status", "ok")
        final["assumptions"] = final.get("assumptions") or []
        final.update({
            "generation_time": state.get("generation_time", 0.0),
            "validation_time": state.get("validation_time", 0.0),
            "execution_time": state.get("execution_time", 0.0),
            "attempts": len(state.get("history", [])),
            "history": list(state.get("history", [])),
            "notes": list(dict.fromkeys(notes)),         # no duplicates, same order
            "issues": list(state.get("issues", [])),
            "path": list(state.get("path", [])) + ["finish"],
            "runner": "graph",
        })
        return {"final": final, "path": ["finish"]}

    # ---- wiring ---------------------------------------------------------
    graph = StateGraph(PanelState)
    for name, fn in [("generate", generate), ("extract", extract),
                     ("safety", safety), ("schema_check", schema_check),
                     ("execute", execute), ("semantic_check", semantic_check),
                     ("check", check), ("repair", repair), ("finish", finish)]:
        graph.add_node(name, fn)

    graph.add_edge(START, "generate")
    # (node, next node when all is well, can a failure here be repaired?)
    for node, nxt, can_repair in [
            ("generate", "extract", False), ("repair", "extract", False),
            ("extract", "safety", False), ("safety", "schema_check", True),
            ("schema_check", "execute", True), ("execute", "semantic_check", True),
            ("semantic_check", "check", True)]:
        targets = {nxt: nxt, "finish": "finish"}
        if can_repair:
            targets["repair"] = "repair"
        graph.add_conditional_edges(node, _router(nxt), targets)
    graph.add_conditional_edges(
        "check", lambda s: "repair" if s.get("retry") else "finish",
        {"repair": "repair", "finish": "finish"})
    graph.add_edge("finish", END)
    return graph.compile()


def run_panel(question, schema, db, max_attempts=MAX_ATTEMPTS, graph=None,
              kind=None, constraints=None):
    """Run one question through the graph. Same return value as sql_agent,
    plus path, status, assumptions, notes, issues and runner == 'graph'.
    kind and constraints come from the planner (both optional)."""
    graph = graph or build_panel_graph(db)
    state = graph.invoke(
        {"question": question, "schema": schema, "max_attempts": max_attempts,
         "kind": kind, "constraints": constraints,
         "attempt": 0, "feedback": None, "empty_fallback": None, "last_good": None,
         "history": [], "path": [], "notes": [], "generation_time": 0.0,
         "validation_time": 0.0, "execution_time": 0.0},
        config={"recursion_limit": 80},
    )
    return state["final"]
