"""
Modules/tools.py

The tools the agents call. Each tool is a plain function that takes simple
arguments and returns a short JSON string, so a language model can read it.
They are built by make_tools(db, profile) for ONE session's Database, so a
tool can never touch another user's data.

    profile_tool(table=None)  what is in the dataset (tables, rows, roles, dates)
    schema_tool(table)        columns of one table: types, null %, distinct, range, samples
    sql_tool(sql)             run ONE read-only query; first rows back, or the exact error

The tools never raise: when something goes wrong they return
{"ok": false, "error": ...}, so that an agent loop can read the problem and
try again. All data is read through db.run, so every query also passes the
safety guard, the timeout and the row cap.

`profile` is the dictionary built by profiler.py. It is accepted now so the
signature does not change later, but the tools read what they need from the
engine itself, so they work for any dataset.
"""
import json

import duckdb
import pandas as pd
from langchain_core.tools import tool

from Modules.sql_guard import GuardError

PREVIEW_ROWS = 5        # rows sql_tool sends back
SAMPLE_VALUES = 5       # example values per text column
LOW_CARDINALITY = 10    # a number with so few values is a category
MAX_DIMENSION = 50      # a text column with so few values is a dimension
INTERNAL_TIMEOUT = 10   # seconds for the tools' own queries


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------
def _q(name):
    """Quote an identifier for SQL."""
    return '"' + str(name).replace('"', '""') + '"'


def _kind(data_type):
    t = str(data_type).upper()
    if t.startswith(("DATE", "TIMESTAMP", "TIME")):
        return "date"
    if t.startswith(("BOOL",)):
        return "boolean"
    if t.startswith(("VARCHAR", "CHAR", "TEXT", "STRING")):
        return "text"
    if t.startswith(("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
                     "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
                     "UHUGEINT", "FLOAT", "DOUBLE", "REAL", "DECIMAL")):
        return "number"
    return "other"


def _json_safe(value):
    """Make one cell JSON friendly."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):          # numpy scalar
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)


def _role(name, kind, distinct, n_rows):
    """A rough role for a column, used by the Data Agent and the KPI ideas."""
    lowered = str(name).lower()
    if kind == "date":
        return "date"
    if lowered == "id" or lowered.endswith("_id"):
        return "id"
    if kind == "boolean":
        return "dimension"
    if kind == "text":
        if n_rows > 20 and distinct >= 0.9 * n_rows:
            return "label"          # almost one value per row: a name or a code
        return "dimension" if distinct <= MAX_DIMENSION else "label"
    if kind == "number":
        if distinct <= LOW_CARDINALITY and n_rows > 100:
            return "dimension"
        return "measure"
    return "other"


# ----------------------------------------------------------------------
# the factory
# ----------------------------------------------------------------------
def make_tools(db, profile=None):
    """Return [profile_tool, schema_tool, sql_tool] bound to this Database."""
    columns_cache = {}
    stats_cache = {}

    def _resolve(table):
        """Case-insensitive table lookup. Returns the real name or None."""
        if not table:
            return None
        wanted = str(table).strip().lower()
        for name in db.tables:
            if name.lower() == wanted:
                return name
        return None

    def _columns(table):
        if table not in columns_cache:
            df = db.run(
                "SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_name = '{table}' ORDER BY ordinal_position;",
                timeout=INTERNAL_TIMEOUT)
            columns_cache[table] = [
                (r.column_name, r.data_type) for r in df.itertuples()]
        return columns_cache[table]

    def _stats(table):
        """Per column: type, kind, null %, distinct, min, max, role."""
        if table in stats_cache:
            return stats_cache[table]
        cols = _columns(table)
        parts = ["COUNT(*) AS n_rows"]
        for i, (col, dtype) in enumerate(cols):
            q = _q(col)
            parts.append(f"COUNT({q}) AS nn_{i}")
            parts.append(f"COUNT(DISTINCT {q}) AS d_{i}")
            if _kind(dtype) in ("number", "date"):
                parts.append(f"MIN({q}) AS lo_{i}")
                parts.append(f"MAX({q}) AS hi_{i}")
        row = db.run(f"SELECT {', '.join(parts)} FROM {_q(table)};",
                     timeout=INTERNAL_TIMEOUT).iloc[0]
        n_rows = int(row["n_rows"])
        result = []
        for i, (col, dtype) in enumerate(cols):
            kind = _kind(dtype)
            distinct = int(row[f"d_{i}"])
            non_null = int(row[f"nn_{i}"])
            entry = {
                "name": col,
                "type": str(dtype),
                "kind": kind,
                "role": _role(col, kind, distinct, n_rows),
                "null_pct": round(100 * (n_rows - non_null) / n_rows, 1) if n_rows else 0.0,
                "distinct": distinct,
            }
            if kind in ("number", "date"):
                entry["min"] = _json_safe(row[f"lo_{i}"])
                entry["max"] = _json_safe(row[f"hi_{i}"])
            result.append(entry)
        stats_cache[table] = {"rows": n_rows, "columns": result}
        return stats_cache[table]

    def _samples(table, column):
        df = db.run(
            f"SELECT {_q(column)} AS value, COUNT(*) AS n FROM {_q(table)} "
            f"WHERE {_q(column)} IS NOT NULL GROUP BY 1 ORDER BY n DESC, 1 "
            f"LIMIT {SAMPLE_VALUES};", timeout=INTERNAL_TIMEOUT)
        return [_json_safe(v) for v in df["value"].tolist()]

    def _unknown_table(table):
        return {"ok": False,
                "error": f"Unknown table '{table}'.",
                "tables": list(db.tables)}

    # ------------------------------------------------------------------
    @tool
    def profile_tool(table: str = "") -> str:
        """Describe the dataset. With no argument: every table with its row
        count, number of columns and date coverage. With a table name: the
        role of each column (id, measure, dimension, label, date) and the
        date coverage of that table. Use schema_tool for column details."""
        try:
            if not table:
                tables = []
                for name in db.tables:
                    st = _stats(name)
                    dates = [c for c in st["columns"] if c["role"] == "date"]
                    entry = {"name": name, "rows": st["rows"],
                             "columns": len(st["columns"])}
                    if dates:
                        entry["date_coverage"] = {
                            c["name"]: [c["min"], c["max"]] for c in dates}
                    tables.append(entry)
                return _dump({"ok": True, "tables": tables,
                              "total_rows": sum(t["rows"] for t in tables),
                              "next": "call profile_tool(table) or schema_tool(table) for details"})
            real = _resolve(table)
            if real is None:
                return _dump(_unknown_table(table))
            st = _stats(real)
            roles = {}
            for c in st["columns"]:
                roles.setdefault(c["role"], []).append(c["name"])
            return _dump({"ok": True, "table": real, "rows": st["rows"],
                          "roles": roles,
                          "date_coverage": {c["name"]: [c["min"], c["max"]]
                                            for c in st["columns"]
                                            if c["role"] == "date"}})
        except Exception as e:
            return _dump({"ok": False, "error": f"{type(e).__name__}: {e}"})

    # ------------------------------------------------------------------
    @tool
    def schema_tool(table: str) -> str:
        """Describe ONE table in detail: for each column its type, role, share
        of missing values, number of distinct values, minimum and maximum (for
        numbers and dates) and a few example values (for text columns and for
        columns with very few distinct values)."""
        try:
            real = _resolve(table)
            if real is None:
                return _dump(_unknown_table(table))
            st = _stats(real)
            columns = []
            for c in st["columns"]:
                entry = dict(c)
                if c["kind"] == "text" or (
                        c["kind"] in ("number", "boolean")
                        and c["distinct"] <= LOW_CARDINALITY):
                    entry["samples"] = _samples(real, c["name"])
                columns.append(entry)
            return _dump({"ok": True, "table": real, "rows": st["rows"],
                          "columns": columns})
        except Exception as e:
            return _dump({"ok": False, "error": f"{type(e).__name__}: {e}"})

    # ------------------------------------------------------------------
    @tool
    def sql_tool(sql: str) -> str:
        """Run ONE read-only DuckDB query (SELECT or WITH ... SELECT) on the
        dataset. Returns the column names, the first 5 rows, the number of
        rows and whether the result was cut. On failure returns the stage
        that failed (safety, syntax, schema_validation, execution) and the
        exact error, so the query can be corrected."""
        try:
            try:
                db.bind_check(sql)
            except GuardError as e:
                return _dump({"ok": False,
                              "stage": "syntax" if e.retryable else "safety",
                              "error": str(e)})
            except duckdb.Error as e:
                return _dump({"ok": False, "stage": "schema_validation",
                              "error": " ".join(str(e).split())[:500]})
            try:
                df = db.run(sql)
            except TimeoutError as e:
                return _dump({"ok": False, "stage": "execution", "error": str(e)})
            except duckdb.Error as e:
                return _dump({"ok": False, "stage": "execution",
                              "error": " ".join(str(e).split())[:500]})
            preview = df.head(PREVIEW_ROWS)
            rows = [[_json_safe(v) for v in r]
                    for r in preview.itertuples(index=False, name=None)]
            return _dump({"ok": True,
                          "columns": [str(c) for c in df.columns],
                          "rows": rows,
                          "row_count": int(len(df)),
                          "truncated": bool(df.attrs.get("truncated", False))})
        except Exception as e:
            return _dump({"ok": False, "stage": "tool_error",
                          "error": f"{type(e).__name__}: {e}"})

    return [profile_tool, schema_tool, sql_tool]
