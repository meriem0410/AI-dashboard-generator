import requests
import json
import re
from loader import load_data_folder
from datetime import datetime


OLLAMA_URL = "http://localhost:11434/api/generate"


# =========================
# PROMPT
# =========================
def build_prompt(schema, question):
    return f"""
You are a SQL generator.

=====================
STEP-BY-STEP RULES
=====================

STEP 1:
Identify ONE primary table that best answers the question.

STEP 2:
Use ONLY columns from that table unless a JOIN is strictly required.

STEP 3:
If a column does not exist in the selected table:
→ switch table OR return:
SELECT 'INVALID QUERY';
STRICT MODE:
- Output ONLY SQL
- NO text
- NO explanation
- NO markdown
- Database system is Microsoft SQL Server
- NEVER use LIMIT
- Use TOP for limiting rows
- GROUP BY aliases is not allowed
- Repeat full expressions in GROUP BY

CRITICAL:
- Use ONLY tables and columns from schema
- Do NOT invent tables
- Do NOT invent columns


IMPORTANT:
- Prefer simple queries
- Prefer single table if possible
- Avoid unnecessary JOINs
- If multiple tables contain the same column:
  - Prefer the most relevant table
DATE RULES:
- Use only date columns present in schema
- Date columns must come from the same table as the metric when possible
- Prefer:
  load_date, dispatch_date, purchase_date, maintenance_date
  
EXAMPLE:

Question: total revenue per customer
SQL:
SELECT customer_id, SUM(revenue)
FROM loads
GROUP BY customer_id;

Question: total trips per driver
SQL:
SELECT driver_id, COUNT(trip_id)
FROM trips
GROUP BY driver_id;

Question: revenue by month
SQL:
SELECT MONTH(load_date) AS month,
       SUM(revenue) AS total_revenue
FROM loads
GROUP BY MONTH(load_date)
ORDER BY month;

SCHEMA:
{schema}

QUESTION:
{question}

SQL:
"""

# =========================
# PROFILING
# =========================
def profile_data(data):
    profile = {}

    for table_name, df in data.items():
        profile[table_name] = {
            "rows": df.shape[0],
            "columns": df.shape[1],
            "column_names": df.columns.tolist(),
            "data_types": df.dtypes.astype(str).to_dict()
        }

    return profile


# =========================
# SCHEMA BUILDER (LLM FORMAT)
# =========================
def build_llm_schema(profile):
    schema_text = ""

    for table, info in profile.items():
        schema_text += f"\nTABLE {table} (\n"

        for col, dtype in info["data_types"].items():
            schema_text += f"  {col} {dtype},\n"

        schema_text = schema_text.rstrip(",\n") + "\n)\n"

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
# CLEAN SQL
# =========================
def clean_sql(text):

    text = text.strip()

    text = re.sub(r"```sql", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")

    return text.strip()


# =========================
# CALL OLLAMA
# =========================
def generate_sql(question, schema):

    schema = reduce_schema(schema, question)
    prompt = build_prompt(schema, question)

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": 120
            }
        },
        timeout=180
    )

    return response.json()["response"]


# =========================
# VALIDATION
# =========================
def extract_schema_elements(schema_text):
    tables = set()
    columns = set()

    for line in schema_text.split("\n"):
        line = line.strip()

        if line.startswith("TABLE"):
            tables.add(line.split()[1])

        elif line and not line.startswith("(") and not line.startswith(")"):
            col = line.split()[0]
            columns.add(col)

    return tables, columns


def validate_sql(sql, schema_text):

    sql_lower = sql.lower()

    forbidden_words = [
        "orders",
        "transactions",
        "sales",
        "invoice",
        "payment"
    ]

    for word in forbidden_words:
        if word in sql_lower and word not in schema_text.lower():
            return False

    return True


# =========================
# SAFE GENERATION (RETRY)
# =========================
def safe_generate_sql(question, schema):

    raw = generate_sql(question, schema)

    sql = clean_sql(raw)
    sql = fix_sql_server_syntax(sql)

    if validate_sql(sql, schema):
        return sql

    return "SELECT 'INVALID QUERY';"


# =========================
# SAVE SCHEMA
# =========================
def save_schema(schema, path="schema.txt"):
    with open(path, "w") as f:
        f.write(schema)

    print(f"Schema saved to {path}")

# =========================
# SQL SERVER FIXER
# =========================
def fix_sql_server_syntax(sql):

    # Fix LIMIT
    if "LIMIT" in sql.upper():

        match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)

        if match:
            limit_value = match.group(1)

            sql = re.sub(
                r"SELECT",
                f"SELECT TOP {limit_value}",
                sql,
                count=1,
                flags=re.IGNORECASE
            )

            sql = re.sub(
                r"LIMIT\s+\d+",
                "",
                sql,
                flags=re.IGNORECASE
            )

    # Fix GROUP BY month alias
    sql = re.sub(
        r"GROUP BY\s+([a-zA-Z_]+)\s*,\s*month",
        r"GROUP BY \1, MONTH(purchase_date)",
        sql,
        flags=re.IGNORECASE
    )
    
    # Fix ORDER BY month alias
    sql = re.sub(
        r"ORDER BY\s+([a-zA-Z_]+)\s*;",
        r"ORDER BY \1, MONTH(purchase_date);",
        sql,
        flags=re.IGNORECASE
    )

    # Fix GROUP BY aliases
    if "GROUP BY year, month" in sql:

        sql = sql.replace(
            "GROUP BY year, month",
            """GROUP BY 
DATEPART(year, maintenance_date),
DATEPART(month, maintenance_date)"""
        )

    if "ORDER BY year, month" in sql:

        sql = sql.replace(
            "ORDER BY year, month",
            """ORDER BY 
DATEPART(year, maintenance_date),
DATEPART(month, maintenance_date)"""
        )

    return sql

# =========================
# AUTO QUESTION GENERATOR
# =========================
def generate_test_questions(profile):

    questions = []

    aggregation_keywords = [
        ("revenue", "SUM"),
        ("total_cost", "SUM"),
        ("fuel_gallons_used", "SUM"),
        ("trips_completed", "SUM"),
        ("average_mpg", "AVG"),
        ("idle_time_hours", "AVG"),
        ("detention_minutes", "AVG")
    ]

    ranking_templates = [
        "top 5 {entity} by {metric}",
        "top 10 {entity} by {metric}"
    ]

    date_templates = [
        "{metric} by month",
        "{metric} by year",
        "{metric} over time"
    ]

    aggregation_templates = [
        "total {metric} by {entity}",
        "average {metric} by {entity}"
    ]

    # =========================
    # LOOP TABLES
    # =========================
    for table, info in profile.items():

        columns = info["column_names"]

        # ---------------------
        # ENTITY COLUMNS
        # ---------------------
        entity_columns = [
            c for c in columns
            if c.endswith("_id")
        ]

        # ---------------------
        # METRIC COLUMNS
        # ---------------------
        metric_columns = [
            c for c in columns
            if any(
                keyword in c.lower()
                for keyword, _ in aggregation_keywords
            )
        ]

        # ---------------------
        # DATE COLUMNS
        # ---------------------
        date_columns = [
            c for c in columns
            if "date" in c.lower()
            or "month" in c.lower()
            or "time" in c.lower()
        ]

        # =====================
        # AGGREGATION QUESTIONS
        # =====================
        for entity in entity_columns:
            for metric in metric_columns:

                questions.append(
                    f"total {metric} by {entity}"
                )

                questions.append(
                    f"average {metric} by {entity}"
                )

        # =====================
        # RANKING QUESTIONS
        # =====================
        for entity in entity_columns:
            for metric in metric_columns:

                questions.append(
                    f"top 5 {entity} by {metric}"
                )

                questions.append(
                    f"top 10 {entity} by {metric}"
                )

        # =====================
        # DATE QUESTIONS
        # =====================
        for metric in metric_columns:

            questions.append(
                f"{metric} by month"
            )

            questions.append(
                f"{metric} by year"
            )

            questions.append(
                f"{metric} over time"
            )

    # Remove duplicates
    questions = list(set(questions))

    return questions
    
def analyze_sql(sql):
    sql_lower = sql.lower()

    return {
        "has_select": "select" in sql_lower,
        "has_group_by": "group by" in sql_lower,
        "has_join": "join" in sql_lower,
        "has_top": "top" in sql_lower,
        "has_aggregation": any(x in sql_lower for x in ["sum", "avg", "count"]),
        "is_invalid": "invalid query" in sql_lower
    }


def run_batch_tests(schema, profile):
    results = []

    questions = generate_test_questions(profile)

    for q in questions:
        print(f"\n🔍 Testing: {q}")

        sql = safe_generate_sql(q, schema)

        metrics = analyze_sql(sql)

        result = {
            "question": q,
            "sql": sql,
            "timestamp": str(datetime.now()),
            **metrics
        }

        results.append(result)

        print(sql)

    return results

def compute_summary(results):
    n = len(results)

    summary = {
        "total_tests": n,
        "hallucination_rate": sum(r["is_invalid"] for r in results) / n,
        "group_by_usage": sum(r["has_group_by"] for r in results) / n,
        "join_usage": sum(r["has_join"] for r in results) / n,
        "aggregation_usage": sum(r["has_aggregation"] for r in results) / n
    }

    return summary

# =========================
# SCORING
# =========================
def score_result(sql):

    score = 0

    sql_lower = sql.lower()

    if "invalid query" not in sql_lower:
        score += 1

    if "select" in sql_lower:
        score += 1

    if any(x in sql_lower for x in [
        "group by",
        "top",
        "join",
        "avg",
        "sum"
    ]):
        score += 1

    if "limit" not in sql_lower:
        score += 1

    return score

# =========================
# BENCHMARK METRICS
# =========================
def compute_metrics(results):

    total = len(results)

    hallucination_rate = (
        sum(r["is_invalid"] for r in results) / total
    )

    join_rate = (
        sum(r["has_join"] for r in results) / total
    )

    aggregation_rate = (
        sum(r["has_group_by"] for r in results) / total
    )

    sql_server_error_rate = (
        sum(r["uses_limit"] for r in results) / total
    )

    print("\n📊 BENCHMARK METRICS")
    print("=" * 40)

    print(f"Total tests: {total}")
    print(f"Hallucination rate: {hallucination_rate:.2f}")
    print(f"JOIN usage rate: {join_rate:.2f}")
    print(f"Aggregation rate: {aggregation_rate:.2f}")
    print(f"SQL Server syntax error rate: {sql_server_error_rate:.2f}")

# =========================
# SAVE JOURNAL
# =========================
def save_journal(results, path="journal.txt"):

    with open(path, "w", encoding="utf-8") as f:

        for r in results:

            f.write("=" * 60 + "\n")

            f.write(f"QUESTION:\n{r['question']}\n\n")

            f.write(f"SQL:\n{r['sql']}\n\n")

            f.write("METRICS:\n")

            f.write(f"- Invalid Query: {r['is_invalid']}\n")
            f.write(f"- Has JOIN: {r['has_join']}\n")
            f.write(f"- Has GROUP BY: {r['has_group_by']}\n")
            f.write(f"- Has ORDER BY: {r['has_order_by']}\n")
            f.write(f"- Uses TOP: {r['has_top']}\n")
            f.write(f"- Uses LIMIT: {r['uses_limit']}\n")
            f.write(f"- Alias GROUP BY issue: {r['uses_alias_group_by']}\n")
            f.write(f"- Score: {r['score']}/4\n\n")

    print(f"\n📘 Journal saved to {path}")

# =========================
# MAIN
# =========================
# =========================
# MAIN
# =========================
def main():

    print("🚀 Loading data...")
    data = load_data_folder("Logistics/")

    print("\n📊 Profiling data...\n")
    profile = profile_data(data)

    print("\n🧠 Building LLM schema...\n")
    schema = build_llm_schema(profile)

    save_schema(schema)

    # =========================
    # SINGLE QUESTION MODE
    # =========================

    question = input("\n❓ Enter your question: ")

    print("\n🤖 Generating SQL...\n")

    sql = safe_generate_sql(question, schema)

    print("=" * 60)
    print("QUESTION:")
    print(question)

    print("\nSQL GENERATED:")
    print(sql)

    print("\nANALYSIS:")
    print(json.dumps(analyze_sql(sql), indent=4))

    print("\n✅ Done.")
# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()

