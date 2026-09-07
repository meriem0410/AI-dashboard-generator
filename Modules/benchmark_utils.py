# =========================

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
