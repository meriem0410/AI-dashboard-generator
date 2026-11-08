import pandas as pd
import streamlit as st

from Modules.pipeline import ingest, profile, build_schema, open_database
from Modules.graph_dashboard import run_dashboard
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
# DASHBOARD GENERATION
# The planner and the panel agents live in Modules/ (graph_dashboard.py);
# the app only shows progress and renders the result.
# ============================================================

def generate_dashboard(question, schema, db):
    """Plan, then run every planned question. Heavy work happens once;
    the result is stored in st.session_state so UI clicks don't redo it."""
    progress = st.progress(0.0, text="Planning...")

    def on_progress(i, total, title):
        progress.progress(i / max(total, 1), text=f"Analyzing: {title}")

    try:
        return run_dashboard(question, schema, db, on_progress=on_progress)
    finally:
        progress.empty()


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
        stage = res.get("stage")
        if stage == "unsupported":
            st.info(f"Not available in this dataset: {error}")
        elif stage == "blocked":
            st.warning(f"Not executed: {error}")
        else:
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

    for assumption in res.get("assumptions", []):
        st.caption(f"Assumption: {assumption}")
    for note in res.get("notes", []):
        st.caption(f"Note: {note}")

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

    for flagged in dash.get("unsupported", []):
        st.info(f"Not available in this dataset: {flagged['request']}. {flagged['reason']}")
    for flagged in dash.get("blocked", []):
        st.warning(f"Not executed: {flagged['request']}. {flagged['reason']}")

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

        old_db = st.session_state.pop("db", None)
        if old_db is not None:
            old_db.close()
        for key in ("data", "metadata", "schema", "dashboard"):
            st.session_state.pop(key, None)

        try:
            with st.spinner("Loading and standardizing your files..."):
                dataset = ingest(uploaded_files, source_type="upload")

            with st.spinner("Profiling the dataset and building the schema..."):
                schema = build_schema(profile(dataset["data"]), data=dataset["data"])

            with st.spinner("Loading the data into the query engine..."):
                db = open_database(dataset["data"])

            st.session_state["db"] = db
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
                    question.strip(), st.session_state["schema"],
                    st.session_state["db"]
                )
            except Exception as exc:
                st.session_state.pop("dashboard", None)
                st.error(f"Dashboard generation failed: {exc}")

    if "dashboard" in st.session_state:
        st.divider()
        render_dashboard(st.session_state["dashboard"])