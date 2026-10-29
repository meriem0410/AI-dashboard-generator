"""
Modules/pipeline.py

UI-agnostic pipeline. No print(), no input(), no fig.show(), no Streamlit.
Every function takes plain inputs and returns plain dicts/frames, so the
Streamlit app, a CLI and future LangGraph nodes can all call them.

Flow:  ingest -> profile -> build_schema -> load_to_database
       -> answer_question -> make_visual
"""

import os
import re
import time

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.types import NVARCHAR

from config import build_db_url
from Modules.Agents.Agent_data import data_agent
from Modules.Agents.Agent_sql import sql_agent
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
STAGES = ("generation", "extraction", "validation",
          "schema_validation", "execution", "completed")


# ------------------------------------------------------------
# 1. INGEST + STANDARDIZE
# ------------------------------------------------------------
def _is_text(series):
    """True for object and for pandas' dedicated string dtypes."""
    return series.dtype == object or pd.api.types.is_string_dtype(series)


def _snake(name):
    """'Load Date' -> 'load_date'; safe as an SQL Server identifier."""
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
# 3. WORKSPACE DATABASE (rebuilt from every upload)
# ------------------------------------------------------------
def _workspace_name():
    return os.getenv("DB_NAME", "dashboard_workspace")


def ensure_database():
    """Create the workspace database if it does not exist yet."""
    name = _workspace_name()
    if not re.fullmatch(r"\w+", name):
        raise ValueError(f"Unsafe database name: {name}")

    admin = create_engine(build_db_url("master"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(
                text(f"IF DB_ID('{name}') IS NULL CREATE DATABASE [{name}]")
            )
    finally:
        admin.dispose()


def reset_workspace(engine):
    """Drop every table of the previous upload so stale tables can never
    leak into validation. Refuses to run unless the database name contains
    'workspace', so it cannot wipe a real database by accident."""
    name = _workspace_name()
    if "workspace" not in name.lower():
        raise RuntimeError(
            f"Refusing to reset database '{name}': its name must contain "
            "'workspace'. Set DB_NAME=dashboard_workspace in .env."
        )
    tables = inspect(engine).get_table_names()
    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f"DROP TABLE [{table}]"))


def _sql_dtypes(df):
    """Short strings -> NVARCHAR(255), long ones -> NVARCHAR(max).
    pandas' default (NVARCHAR(max) everywhere) makes joins on ID columns slow."""
    dtypes = {}
    for col in df.columns:
        if _is_text(df[col]):
            max_len = df[col].dropna().astype(str).str.len().max()
            if pd.notna(max_len) and max_len <= 255:
                dtypes[col] = NVARCHAR(255)
            else:
                dtypes[col] = NVARCHAR(None)
    return dtypes


def load_to_database(data, engine):
    """Rebuild the workspace database from the uploaded tables so that
    sql_agent can query them. Returns the list of table names written."""
    ensure_database()
    reset_workspace(engine)

    written = []
    for table_name, df in data.items():
        df.to_sql(table_name, engine, if_exists="replace", index=False,
                  chunksize=1000, dtype=_sql_dtypes(df))
        written.append(table_name)
    return written


# ------------------------------------------------------------
# 4. ANSWER A QUESTION  (SQL agent)
# ------------------------------------------------------------
def answer_question(question, schema):
    """Thin wrapper over sql_agent. Never raises: failures come back as
    {"success": False, "stage": ..., "error": ...}."""
    try:
        return sql_agent(question, schema)
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
def run_question(question, schema):
    """answer_question + SQL analysis + visual, in one call.
    Stops early (no visual) if the SQL agent failed."""
    t0 = time.perf_counter()
    result = answer_question(question, schema)
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