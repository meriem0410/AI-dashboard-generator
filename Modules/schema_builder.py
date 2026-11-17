
from config import client

import pandas as pd

# =========================
# SCHEMA BUILDER (LLM FORMAT)
# =========================
#
# When the data is available, each low-cardinality text (or boolean) column is
# listed with its REAL values, e.g.
#     employment_status: object (dimension) -- one of: Active, On Leave, Terminated
# so the model filters on the exact value ('Active', not 'active'). This removes a
# whole class of wrong-but-valid queries that returned zero rows from a case or
# spelling mismatch.

MAX_HINT_VALUES = 25            # columns with more distinct values get no value hint
_ID_SUFFIXES = ("_id", "_identifier")


def _looks_like_id(name):
    n = str(name).strip().lower()
    return n == "id" or n.endswith(_ID_SUFFIXES) or n.startswith("id_")


def _value_hint(series):
    """A ' one of: a, b, c' hint for a low-cardinality text/boolean column, with
    the real casing. None for numeric, high-cardinality or empty columns."""
    if pd.api.types.is_bool_dtype(series):
        return "one of: true, false"
    if not (pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype)):
        return None
    values = series.dropna().unique().tolist()
    if not (1 <= len(values) <= MAX_HINT_VALUES):
        return None
    shown = sorted(str(v) for v in values)
    return "one of: " + ", ".join(shown)


def build_llm_schema(profile, data=None):
    schema_text = ""

    for table, info in profile.items():

        # Ignore entries that are not tables (e.g. relationships).
        if not isinstance(info, dict):
            continue

        # Ignore dictionaries without columns.
        if "columns" not in info:
            continue

        schema_text += f"\nTABLE {table} (\n"

        df = data.get(table) if isinstance(data, dict) else None

        for col, col_info in info["columns"].items():
            dtype = col_info["dtype"]
            role = col_info["role"]

            line = f"    {col}: {dtype} ({role})"

            if df is not None and col in df.columns and not _looks_like_id(col):
                try:
                    hint = _value_hint(df[col])
                except Exception:
                    hint = None
                if hint:
                    line += f" -- {hint}"

            schema_text += line + "\n"

        schema_text += ")\n"

    return schema_text


# =========================
# REDUCE SCHEMA (IMPORTANT)
# =========================
def reduce_schema(schema_text, question):
    keywords = [word.lower() for word in question.split()]

    lines = schema_text.split("\n")
    filtered = []
    keep = False

    for line in lines:
        if line.startswith("TABLE"):
            keep = any(k in line.lower() for k in keywords)

        if any(k in line.lower() for k in keywords):
            keep = True

        if keep:
            filtered.append(line)

    return "\n".join(filtered)


# =========================
# SAVE SCHEMA
# =========================
def save_schema(schema, path="schema.txt"):
    with open(path, "w", encoding="utf-8") as f:
        f.write(schema)

    print(f"Schema saved to {path}")
