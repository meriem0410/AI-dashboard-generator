"""
Modules/dataset_overview.py

Turns the profiler's output into a compact, serialisable summary for the dataset
overview page (and its downloadable profile.json). Pure: no Streamlit, no model.

    build_profile_summary(profile_result, data=None) -> dict
"""


def build_profile_summary(profile_result, data=None):
    """{"tables": {name: {rows, columns:{col:{type, role}}}}, "relationships": [...]}.
    Entries in the profile that are not tables (e.g. 'relationships') are skipped."""
    data = data or {}
    out = {"tables": {}, "relationships": list(profile_result.get("relationships", []))}
    for table, info in profile_result.items():
        if not isinstance(info, dict) or "columns" not in info:
            continue
        df = data.get(table)
        out["tables"][table] = {
            "rows": int(len(df)) if df is not None else info.get("rows"),
            "columns": {col: {"type": col_info.get("dtype"), "role": col_info.get("role")}
                        for col, col_info in info["columns"].items()},
        }
    return out


def column_rows(info):
    """A list of {column, type, role} for one table's profile entry (for a table view)."""
    return [{"column": col, "type": ci.get("dtype", ""), "role": ci.get("role", "")}
            for col, ci in info.get("columns", {}).items()]
