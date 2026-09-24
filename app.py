import streamlit as st

from Modules.Agents.Agent_data import data_agent


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Dashboard Creator",
    page_icon="📊",
    layout="wide"
)


# ============================================================
# HEADER
# ============================================================

st.title("📊 AI Dashboard Creator")

st.write(
    "Upload your dataset and let the system "
    "automatically analyze its structure."
)


# ============================================================
# DATA INPUT
# ============================================================

st.header("1. Import your data")

uploaded_files = st.file_uploader(
    "Upload CSV or Excel files",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)


# ============================================================
# PROCESS DATA
# ============================================================

if uploaded_files:

    st.success(
        f"{len(uploaded_files)} file(s) selected."
    )

    if st.button(
        "🚀 Load dataset",
        type="primary"
    ):

        try:

            with st.spinner(
                "Loading and validating your dataset..."
            ):

                dataset = data_agent(
                    uploaded_files,
                    source_type="upload"
                )

            data = dataset["data"]
            metadata = dataset["metadata"]

            # Store data in Streamlit session
            st.session_state["data"] = data
            st.session_state["metadata"] = metadata

            st.success(
                "Dataset successfully loaded!"
            )

        except Exception as e:

            st.error(
                f"Failed to load dataset: {e}"
            )


# ============================================================
# DATASET SUMMARY
# ============================================================

if "data" in st.session_state:

    data = st.session_state["data"]
    metadata = st.session_state["metadata"]

    st.divider()

    st.header("2. Dataset overview")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Tables",
            metadata["table_count"]
        )

    with col2:
        st.metric(
            "Total rows",
            metadata["total_rows"]
        )

    with col3:
        st.metric(
            "Total columns",
            metadata["total_columns"]
        )

    st.subheader("Loaded tables")

    for table_name, df in data.items():

        with st.expander(
            f"📄 {table_name} — "
            f"{len(df)} rows × {len(df.columns)} columns"
        ):

            st.dataframe(
                df.head(10),
                width="stretch"
            )

            st.write(
                "Columns:",
                list(df.columns)
            )