"""
Modules/pipeline.py

UI-agnostic pipeline. No print(), no input(), no fig.show(), no Streamlit.
Every function takes plain inputs and returns plain dicts/frames, so the
Streamlit app, a CLI and future LangGraph nodes can all call them.

Flow:  ingest -> profile -> build_schema -> open_database
       -> answer_question -> make_visual
"""

import re
import time

import pandas as pd

from Modules.Agents.Agent_data import data_agent
from Modules.Agents.Agent_sql import sql_agent
from Modules.engine_duckdb import Database
from Modules.profiler import profile_data
from Modules.schema_builder import build_llm_schema, save_schema
from Modules.visualisation import (
    choose_visual,
    build_visual_metadata,
    render_visual,
)

try:  # optional: only used for SQL statistics in run_question
    from Modules.benchmark_utils import analyze_sql
except ImportError:
    analyze_sql = None

# Stage vocabulary returned by sql_agent
STAGES = ("generation", "extraction", "safety", "syntax", "validation",
          "schema_validation", "execution", "completed")


# ------------------------------------------------------------
# 1. INGEST + STANDARDIZE
# ------------------------------------------------------------
def _is_text(series):
    """True for object and for pandas' dedicated string dtypes."""
    return series.dtype == object or pd.api.types.is_string_dtype(series)


def _snake(name):
    """'Load Date' -> 'load_date'; safe as a table or column name."""
    name = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower()
    if not name:
        name = "col"
    if name[0].isdigit():
        name = f"t_{name}"
    return name


def _unique(names):
    seen, out = {}, []
    for n in names:
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 0
        out.append(n)
    return out


def standardize(data):
    """Clean table/column names and parse date columns BEFORE profiling,
    so the profile, the schema and the database all agree."""
    names = _unique([_snake(t) for t in data])
    clean = {}
    for new_name, (_, df) in zip(names, data.items()):
        df = df.copy()
        df.columns = _unique([_snake(c) for c in df.columns])
        for col in df.columns:
            if "date" in col and _is_text(df[col]):
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().mean() >= 0.9:
                    df[col] = parsed
        clean[new_name] = df
    return clean


def ingest(source, source_type="folder"):
    """source: folder path, or list of Streamlit UploadedFile objects.
    Returns {"data": {table: DataFrame}, "metadata": {...}}."""
    result = data_agent(source, source_type=source_type)
    result["data"] = standardize(result["data"])
    result["metadata"]["tables"] = list(result["data"].keys())
    return result


# ------------------------------------------------------------
# 2. PROFILE + SCHEMA
# ------------------------------------------------------------
def profile(data):
    """Returns the profile dict."""
    return profile_data(data)


def date_coverage(data):
    """One line per datetime column with its min/max. Tells the LLM which
    period the data really covers, so it never invents 'the last 12 months'
    relative to today's date. Only columns parsed as dates are listed
    (standardize() parses columns whose name contains 'date')."""
    lines = []
    for table, df in data.items():
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                lo, hi = df[col].min(), df[col].max()
                if pd.notna(lo) and pd.notna(hi):
                    lines.append(f"- {table}.{col}: {lo:%Y-%m-%d} to {hi:%Y-%m-%d}")
    if not lines:
        return ""
    return (
        "DATA COVERAGE (the data only spans these periods; "
        "never assume it reaches today's date):\n"
        + "\n".join(lines) + "\n\n"
    )


def build_schema(profile_dict, data=None, save=True):
    """Returns the schema string injected into the SQL prompt.
    If `data` is given, a DATA COVERAGE section is placed FIRST so it is
    never cut off when the schema is truncated."""
    schema = build_llm_schema(profile_dict)
    if data is not None:
        schema = date_coverage(data) + schema
    if save:
        save_schema(schema)
    return schema


# ------------------------------------------------------------
# 3. QUERY ENGINE (one in-memory DuckDB database per upload)
# ------------------------------------------------------------
def open_database(data):
    """Load the uploaded tables ({name: DataFrame}) into a fresh, locked-down
    in-memory DuckDB database and return it. The caller keeps the Database
    object (the Streamlit app stores it in st.session_state) and passes it
    to sql_agent / answer_question / run_question."""
    return Database.from_dataframes(data)


# ------------------------------------------------------------
# 4. ANSWER A QUESTION  (SQL agent)
# ------------------------------------------------------------
def answer_question(question, schema, db):
    """Thin wrapper over sql_agent. Never raises: failures come back as
    {"success": False, "stage": ..., "error": ...}."""
    try:
        return sql_agent(question, schema, db)
    except Exception as e:  # last-resort guard
        return {
            "success": False,
            "stage": "generation",
            "error": f"Unhandled error: {e}",
            "raw_response": None,
            "sql": None,
            "validation": None,
            "result": None,
            "generation_time": 0.0,
            "validation_time": 0.0,
            "execution_time": 0.0,
        }


# ------------------------------------------------------------
# 5. VISUAL
# ------------------------------------------------------------
def make_visual(question, df):
    """Returns {"type": str, "metadata": dict, "figure": plotly Figure}."""
    visual_type = choose_visual(question, df)
    visual_meta = build_visual_metadata(df, visual_type, question)
    figure = render_visual(df, visual_meta)
    return {"type": visual_type, "metadata": visual_meta, "figure": figure}


# ------------------------------------------------------------
# 6. FULL RUN FOR ONE QUESTION
# ------------------------------------------------------------
def run_question(question, schema, db):
    """answer_question + SQL analysis + visual, in one call.
    Stops early (no visual) if the SQL agent failed."""
    t0 = time.perf_counter()
    result = answer_question(question, schema, db)
    out = {"question": question, "agent": result, "visual": None,
           "sql_analysis": None, "success": result.get("success", False)}

    if not out["success"]:
        out["total_time"] = time.perf_counter() - t0
        return out

    df = result["result"]
    if analyze_sql is not None:
        out["sql_analysis"] = analyze_sql(result["sql"])
    try:
        out["visual"] = make_visual(question, df)
    except Exception as e:
        out["visual_error"] = str(e)  # query succeeded, chart failed

    out["total_time"] = time.perf_counter() - t0
    return out