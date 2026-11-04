"""
Modules/sql_validator.py

Second check, after the safety guard: ask DuckDB itself whether the query
makes sense for the loaded data (do the tables and columns exist, do the
types fit). Nothing is executed: DuckDB only binds the query.

validate_query(sql, db) keeps the dictionary the agent already expects:
    {"schema_valid": bool, "schema_errors": [str, ...]}
"""
import duckdb


def _short(error, limit=500):
    return " ".join(str(error).split())[:limit]


def validate_query(sql, db):
    try:
        db.bind_check(sql)
    except duckdb.Error as e:
        return {"schema_valid": False, "schema_errors": [_short(e)]}
    return {"schema_valid": True, "schema_errors": []}
