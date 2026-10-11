
import pandas as pd
import os
import json
import re
import streamlit as st
from groq import Groq
from config import engine, GROQ_MODEL
from dotenv import load_dotenv

load_dotenv()

from Modules.Agents.Agent_data import data_agent
from Modules.profiler import profile_data
from Modules.schema_builder import build_llm_schema, save_schema
from Modules.Agents.Agent_sql import sql_agent
from Modules.visualisation import (
    choose_visual,
    build_visual_metadata,
    render_visual,
)


st.set_page_config(
    page_title="AI Dashboard Generator",
    page_icon="📊",
    layout="wide",
)

st.title("AI-Powered Dashboard Generator")
st.caption(
    "Describe what you want to analyze. "
    "The dashboard will focus on your question."
)


# ------------------------------------------------------------
# DASHBOARD PLANNER — FIRST MVP
# ------------------------------------------------------------

def plan_dashboard(question, schema):
    """
    Build a dashboard plan grounded in the available database schema.
    Returns a list of KPIs and chart definitions.
    """

    # Support schemas represented as either strings or dictionaries.
    schema_text = (
        schema if isinstance(schema, str)
        else json.dumps(schema, ensure_ascii=False, default=str)
    )

    # Keep the prompt reasonably sized.
    schema_text = schema_text[:18000]

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    system_prompt = """
You are a senior BI analyst and dashboard-planning agent.

Your task is to design a dashboard based on:
1. The user's actual analytical question.
2. The database schema supplied below.

STRICT RULES:
- Use only tables and columns present in the schema.
- Never invent column names, metrics, relationships, or business facts.
- Focus most visualizations on the user's main topic.
- If the user asks about fuel and trips, prioritize fuel consumption,
  fuel spending, fuel purchases, and trip-related analysis where supported.
- Include supporting metrics only when they help answer the user's question.
- Do not create generic charts unrelated to the question.
- Avoid charts that would return only one category or a constant value
  when another useful analysis is possible.
- Do not use ID columns as numeric measures.
- Use a date column only if the schema contains a suitable date/time column.
- Do not assume fuel quantity, fuel price, distance, status, or revenue exists.
  Check the schema first.
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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1400,
    )

    content = response.choices[0].message.content.strip()

    # Handle accidental Markdown fences.
    content = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        content,
        flags=re.IGNORECASE,
    ).strip()

    plan = json.loads(content)

    allowed_kinds = {"kpi", "bar", "line", "pie", "table"}
    items = plan.get("items", [])

    if not isinstance(items, list):
        raise ValueError("The dashboard planner returned an invalid items list.")

    validated_items = []
    for item in items:
        if not isinstance(item, dict):
            continue

        title = item.get("title")
        chart_question = item.get("question")
        kind = item.get("kind")

        if (
            isinstance(title, str)
            and isinstance(chart_question, str)
            and kind in allowed_kinds
            and title.strip()
            and chart_question.strip()
        ):
            validated_items.append({
                "title": title.strip(),
                "question": chart_question.strip(),
                "kind": kind,
            })

    if not validated_items:
        raise ValueError("The planner did not produce any valid visualizations.")

    return {
        "title": str(plan.get("title", "Your Dashboard")),
        "focus": str(plan.get("focus", question)),
        "items": validated_items[:6],
    }


# ------------------------------------------------------------
# RUN ONE ANALYTICAL QUESTION
# ------------------------------------------------------------

def run_analysis(question, schema):
    """Use the existing SQL agent to answer one dashboard question."""

    result = sql_agent(question, schema)
    with st.expander("Debug SQL result"):
        st.code(result.get("sql") or "No SQL returned", language="sql")

        if result.get("success") and result.get("result") is not None:
            debug_df = result["result"]

            st.write("Result shape:", debug_df.shape)
            st.write("Result columns:", debug_df.columns.tolist())
            st.dataframe(debug_df.head(20), use_container_width=True)

    if not result.get("success"):
        error = result.get("error", "SQL analysis failed.")
        return None, error

    df = result.get("result")

    if df is None:
        return None, "The SQL agent did not return a result."

    if not isinstance(df, pd.DataFrame):
        return None, "The SQL agent returned an unexpected result format."

    if df.empty:
        return None, "The query returned no data."

    return df, None

# ------------------------------------------------------------
# RENDER ONE DASHBOARD ITEM
# ------------------------------------------------------------

def render_item(item, schema):
    st.subheader(item["title"])

    with st.spinner(f"Analyzing: {item['title']}..."):
        df, error = run_analysis(item["question"], schema)

    if error:
        st.warning(f"Could not generate this visualization: {error}")
        return

    kind = item["kind"]

    # Explicit time-series requests should use a line chart
    # when the query result contains date information.
    question_lower = item["question"].lower()

    time_keywords = (
        "over time", "trend", "monthly", "by month",
        "per month", "by year", "yearly", "daily",
        "weekly", "by date", "evolution"
    )

    has_time_intent = any(
        keyword in question_lower
        for keyword in time_keywords
    )

    has_year_month = (
        {"year", "month"}.issubset(
            {str(c).lower() for c in df.columns}
        )
    )

    has_date_column = any(
        any(word in str(c).lower() for word in (
            "date", "datetime", "timestamp", "month_start"
        ))
        for c in df.columns
    )


    # KPI: show a single numeric result as a metric
    if kind == "kpi":
        numeric_cols = df.select_dtypes(
            include="number"
        ).columns.tolist()

        if len(df) == 1 and numeric_cols:
            col = numeric_cols[0]
            st.metric(
                label=col.replace("_", " ").title(),
                value=f"{df[col].iloc[0]:,.2f}",
            )
        else:
            st.dataframe(df, use_container_width=True)
        return

    # Choose a visual type for this particular result
    if kind == "auto":
        kind = choose_visual(item["question"], df)

    # Reuse your existing metadata builder and renderer
    metadata = build_visual_metadata(
        df,
        kind,
        item["question"],
    )

    fig = render_visual(df, metadata)

    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)

    with st.expander("View query results"):
        st.dataframe(df, use_container_width=True)


# ------------------------------------------------------------
# LOAD AND PROFILE THE DATASET
# ------------------------------------------------------------

@st.cache_resource(show_spinner="Loading and profiling the dataset...")
def prepare_dataset():
    dataset = data_agent("data/Logistics")
    data = dataset["data"]

    profile = profile_data(data)
    schema = build_llm_schema(profile)
    save_schema(schema)

    return schema, dataset.get("metadata", {})


# ------------------------------------------------------------
# DASHBOARD UI
# ------------------------------------------------------------

question = st.text_area(
    "What would you like to analyze?",
    placeholder=(
        "Example: Analyze fuel consumption, fuel costs "
        "and their relationship with trips."
    ),
    height=100,
)

if st.button("Generate Dashboard", type="primary"):
    if not question.strip():
        st.warning("Please enter an analysis question.")
    else:
        try:
            schema, dataset_metadata = prepare_dataset()
            dashboard_plan = plan_dashboard(question, schema)
            plan = dashboard_plan["items"]

            st.divider()
            st.header(dashboard_plan["title"])
            st.write(f"**Your question:** {question}")
            st.caption(dashboard_plan["focus"])
            st.caption(f"{len(plan)} visualizations planned for your objective.")

            # KPIs first
            kpis = [item for item in plan if item["kind"] == "kpi"]
            charts = [item for item in plan if item["kind"] != "kpi"]

            for item in kpis:
                render_item(item, schema)

            st.divider()

            # Two-column chart layout
            for i in range(0, len(charts), 2):
                columns = st.columns(2)

                with columns[0]:
                    render_item(charts[i], schema)

                if i + 1 < len(charts):
                    with columns[1]:
                        render_item(charts[i + 1], schema)

        except Exception as exc:
            st.error(f"Dashboard generation failed: {exc}")
