from config import engine
from config import client

# =========================
# SCHEMA BUILDER (LLM FORMAT)
# =========================
def build_llm_schema(profile):
    schema_text = ""

    for table, info in profile.items():

        # Ignorer les éléments qui ne sont pas des tables (ex: relationships)
        if not isinstance(info, dict):
            continue

        # Ignorer les dictionnaires qui ne possèdent pas de colonnes
        if "columns" not in info:
            continue

        schema_text += f"\nTABLE {table} (\n"

        for col, col_info in info["columns"].items():
            dtype = col_info["dtype"]
            role = col_info["role"]

            schema_text += f"    {col}: {dtype} ({role})\n"

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