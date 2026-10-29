import json
import re

import pandas as pd
import streamlit as st

from config import client, GROQ_MODEL, engine
from Modules.pipeline import ingest, profile, build_schema, load_to_database
from Modules.Agents.Agent_sql import sql_agent
from Modules.visualisation import build_visual_metadata, render_visual


st.set_page_config(
    page_title="AI Dashboard Creator",
    page_icon="📊",
    layout="wide",
)

st.title("📊 AI Dashboard Creator")
st.write(
    "Upload your dataset, describe what you want to analyze, "
    "and get a dashboard focused on your question."
)


# ============================================================
# DASHBOARD PLANNER
# ============================================================

PLANNER_SYSTEM_PROMPT = """
You are a senior BI analyst and dashboard-planning agent.

Your task is to design a dashboard based on:
1. The user's actual analytical question.
2. The database schema supplied below.

STRICT RULES:
- Use only tables and columns present in the schema.
- Never invent column names, metrics, relationships, or business facts.
- Focus most visualizations on the user's main topic.
- Include supporting metrics only when they help answer the user's question.
- Do not create generic charts unrelated to the question.
- Avoid charts that would return only one category or a constant value
  when another useful analysis is possible.
- Do not use ID columns as numeric measures.
- Use a date column only if the schema contains a suitable date/time column.
- Do not assume any metric exists. Check the schema first.
- Never ask for "recent" periods or "the last N months" unless the user did;
  the schema starts with DATA COVERAGE, the periods the data really spans.
- Every chart must specify a clear analytical question, not SQL.
- Each visualization must be independently useful.
- Prefer 1-2 KPIs and 3-5 charts.
- Use only these types: kpi, bar, line, pie, table.
- KPIs should return a single numeric value.
- Bar charts compare categories; line charts show change over time;
  pie charts show a small number of meaningful parts of a whole.
- If a metric cannot be supported by the schema, omit it.
- Return valid JSON only. Do not use Markdown.

Return this exact structure:
{
  "title": "Short dashboard title",
  "focus": "What the dashboard will investigate",
  "items": [
    {
      "title": "Short visualization title",
      "question": "A natural-language question that can be answered using the schema",
      "kind": "kpi"
    }
  ]
}
"""


def plan_dashboard(question, schema):
    """Ask the LLM for a dashboard plan grounded in the schema."""

    schema_text = (
        schema if isinstance(schema, str)
        else json.dumps(schema, ensure_ascii=False, default=str)
    )
    schema_text = schema_text[:18000]

    user_prompt = f"""
DATABASE SCHEMA:
{schema_text}

USER'S ANALYTICAL QUESTION:
{question}

Create a focused dashboard plan.
Return 4 to 6 visualizations total, including 1 or 2 KPIs if supported.
Prioritize the user's main topic. Do not repeat the same analysis.
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        reasoning_effort="low",
        max_tokens=2000,
    )

    content = (response.choices[0].message.content or "").strip()
    content = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE
    ).strip()

    try:
        plan = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"The planner did not return valid JSON: {e}")

    allowed_kinds = {"kpi", "bar", "line", "pie", "table"}
    items = plan.get("items", [])
    if not isinstance(items, list):
        raise ValueError("The dashboard planner returned an invalid items list.")

    validated = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        chart_question = item.get("question")
        kind = item.get("kind")
        if (
            isinstance(title, str) and title.strip()
            and isinstance(chart_question, str) and chart_question.strip()
            and kind in allowed_kinds
        ):
            validated.append({
                "title": title.strip(),
                "question": chart_question.strip(),
                "kind": kind,
            })

    if not validated:
        raise ValueError("The planner did not produce any valid visualizations.")

    return {
        "title": str(plan.get("title", "Your Dashboard")),
        "focus": str(plan.get("focus", question)),
        "items": validated[:6],
    }


# ============================================================
# ANALYSIS (computed once, stored in session_state)
# ============================================================

def run_analysis(question, schema):
    """Answer one dashboard question with the SQL agent.
    Returns (dataframe | None, error | None, sql | None, attempts)."""

    result = sql_agent(question, schema)
    sql = result.get("sql")
    attempts = result.get("attempts", 1)

    if not result.get("success"):
        return None, result.get("error", "SQL analysis failed."), sql, attempts

    df = result.get("result")
    if df is None:
        return None, "The SQL agent did not return a result.", sql, attempts
    if not isinstance(df, pd.DataFrame):
        return None, "The SQL agent returned an unexpected result format.", sql, attempts
    if df.empty:
        return None, "The query returned no data.", sql, attempts

    return df, None, sql, attempts


def generate_dashboard(question, schema):
    """Plan, then run every planned question. Heavy work happens once;
    the result is stored in st.session_state so UI clicks don't redo it."""

    plan = plan_dashboard(question, schema)
    results = []

    progress = st.progress(0.0, text="Analyzing...")
    total = len(plan["items"])
    for i, item in enumerate(plan["items"]):
        progress.progress(i / total, text=f"Analyzing: {item['title']}")
        df, error, sql, attempts = run_analysis(item["question"], schema)
        results.append({"item": item, "df": df, "error": error,
                        "sql": sql, "attempts": attempts})
    progress.empty()

    return {"question": question, "plan": plan, "results": results}


# ============================================================
# RENDERING
# ============================================================

TIME_KEYWORDS = (
    "over time", "trend", "monthly", "by month", "per month",
    "by year", "yearly", "daily", "weekly", "by date", "evolution",
)


def render_item(res, idx):
    item, df, error, sql = res["item"], res["df"], res["error"], res["sql"]
    attempts = res.get("attempts", 1)

    st.subheader(item["title"])

    if error:
        st.warning(f"Could not generate this visualization: {error}")
        if attempts > 1:
            st.caption(f"The SQL agent tried {attempts} times before giving up.")
        if sql:
            with st.expander("Generated SQL"):
                st.code(sql, language="sql")
        return

    kind = item["kind"]

    # Time-series questions should be line charts when the result has dates.
    columns_lower = {str(c).lower() for c in df.columns}
    has_time_intent = any(k in item["question"].lower() for k in TIME_KEYWORDS)
    has_year_month = {"year", "month"}.issubset(columns_lower)
    has_date_column = any(
        word in c for c in columns_lower
        for word in ("date", "datetime", "timestamp", "month_start")
    )
    if kind in ("bar", "pie") and has_time_intent and (has_year_month or has_date_column):
        kind = "line"

    if kind == "kpi":
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if len(df) == 1 and numeric_cols:
            col = numeric_cols[0]
            st.metric(
                label=str(col).replace("_", " ").title(),
                value=f"{df[col].iloc[0]:,.2f}",
            )
        else:
            st.dataframe(df, width="stretch")
    elif kind == "table":
        st.dataframe(df, width="stretch")
    else:
        try:
            metadata = build_visual_metadata(df, kind, item["question"])
            fig = render_visual(df, metadata)
        except Exception as e:
            fig = None
            st.caption(f"Chart could not be drawn ({e}); showing the data instead.")

        if fig is not None:
            st.plotly_chart(fig, width="stretch", key=f"chart_{idx}")
        else:
            st.dataframe(df, width="stretch")

    with st.expander("SQL and data"):
        if attempts > 1:
            st.caption(f"Self-corrected: the query succeeded on attempt {attempts}.")
        if sql:
            st.code(sql, language="sql")
        st.dataframe(df, width="stretch")


def render_dashboard(dash):
    plan, results = dash["plan"], dash["results"]

    st.header(plan["title"])
    st.write(f"**Your question:** {dash['question']}")
    st.caption(plan["focus"])

    kpis = [(i, r) for i, r in enumerate(results) if r["item"]["kind"] == "kpi"]
    charts = [(i, r) for i, r in enumerate(results) if r["item"]["kind"] != "kpi"]

    if kpis:
        for col, (i, r) in zip(st.columns(len(kpis)), kpis):
            with col:
                render_item(r, i)
        st.divider()

    for start in range(0, len(charts), 2):
        cols = st.columns(2)
        for col, (i, r) in zip(cols, charts[start:start + 2]):
            with col:
                render_item(r, i)


# ============================================================
# 1. IMPORT YOUR DATA
# ============================================================

st.header("1. Import your data")

uploaded_files = st.file_uploader(
    "Upload CSV or Excel files",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.success(f"{len(uploaded_files)} file(s) selected.")

    if st.button("🚀 Load dataset", type="primary"):

        for key in ("data", "metadata", "schema", "dashboard"):
            st.session_state.pop(key, None)

        try:
            with st.spinner("Loading and standardizing your files..."):
                dataset = ingest(uploaded_files, source_type="upload")

            with st.spinner("Profiling the dataset and building the schema..."):
                schema = build_schema(profile(dataset["data"]), data=dataset["data"])

            with st.spinner("Preparing the query database..."):
                load_to_database(dataset["data"], engine)

            st.session_state["data"] = dataset["data"]
            st.session_state["metadata"] = dataset["metadata"]
            st.session_state["schema"] = schema

            st.success("Dataset loaded, profiled and ready to query!")

        except Exception as e:
            st.error(f"Failed to prepare the dataset: {e}")


# ============================================================
# 2. DATASET OVERVIEW
# ============================================================

if "data" in st.session_state:

    data = st.session_state["data"]
    metadata = st.session_state["metadata"]

    st.divider()
    st.header("2. Dataset overview")

    col1, col2, col3 = st.columns(3)
    col1.metric("Tables", metadata["table_count"])
    col2.metric("Total rows", f"{metadata['total_rows']:,}")
    col3.metric("Total columns", metadata["total_columns"])

    st.subheader("Loaded tables")
    for table_name, df in data.items():
        with st.expander(
            f"📄 {table_name} — {len(df):,} rows × {len(df.columns)} columns"
        ):
            st.dataframe(df.head(10), width="stretch")
            st.write("Columns:", list(df.columns))


# ============================================================
# 3. ASK YOUR QUESTION -> DASHBOARD
# ============================================================

if "schema" in st.session_state:

    st.divider()
    st.header("3. What would you like to analyze?")

    question = st.text_area(
        "Your analytical question",
        placeholder="Example: Analyze fuel consumption, fuel costs and their relationship with trips.",
        height=100,
    )

    if st.button("Generate Dashboard", type="primary"):
        if not question.strip():
            st.warning("Please enter an analysis question.")
        else:
            try:
                st.session_state["dashboard"] = generate_dashboard(
                    question.strip(), st.session_state["schema"]
                )
            except Exception as exc:
                st.session_state.pop("dashboard", None)
                st.error(f"Dashboard generation failed: {exc}")

    if "dashboard" in st.session_state:
        st.divider()
        render_dashboard(st.session_state["dashboard"])