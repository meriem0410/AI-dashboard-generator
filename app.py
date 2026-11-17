"""
app.py  -  AI Dashboard Creator (Streamlit)

Flow (one view per step, a stepper on top):
    Home -> New dashboard:  Data  ->  Question  ->  Dashboard
    Library: My datasets | My dashboards | History

Everything a user saves goes through Modules/storage.py (a local folder, or a
Google Cloud Storage bucket when STORAGE_BACKEND=gcs). A saved dashboard
stores its SQL, so reopening it re-runs the SQL on the data: no model call.
"""
import copy
import hashlib
import html
import json
import re
import time

import pandas as pd
import streamlit as st

from Modules import library as lib
from Modules.app_services import (
    dashboard_to_spec,
    default_dataset_name,
    suggest_dataset_name,
    metadata_from_data,
    spec_to_dashboard,
)
from Modules.dashboard_filters import discover_filter_catalog, scope_catalog_to_dashboard
from Modules.graph_dashboard import run_dashboard
from Modules.pipeline import (
    ingest,
    profile,
    build_schema,
    open_database,
)
from Modules.semantic_checks import check_result, format_problem
from Modules.sql_executor import execute_sql
from Modules.storage import get_storage
from Modules.users import AuthError, login, register
from Modules.visualisation import (
    build_visual_metadata,
    render_visual,
    format_metric_value,
    pie_labels,
)
from Modules.kpi_trends import kpi_trend, sparkline_svg, format_delta
from Modules.followup import (apply_followup, apply_presentation_edit, classify_followup,
                              pin_panel, presentation_edit)
from Modules.dashboard_ops import remove_panel
from Modules.insights import panel_explain, dashboard_insight
from Modules.export_html import dashboard_to_html
from Modules.export_xlsx import dashboard_to_xlsx
from Modules.dataset_overview import build_profile_summary, column_rows


st.set_page_config(
    page_title="Devoboard",
    page_icon="◧",
    layout="wide",
)

# One accent colour (Devoteam-style red, approximate) + a dark ink colour.
# Change ACCENT here and in .streamlit/config.toml (primaryColor) to re-theme.
ACCENT = "#E2231A"
INK = "#1B1F2A"

st.markdown(
    f"""
    <style>
    :root {{ --accent: {ACCENT}; --ink: {INK}; }}
    .stApp {{ background: #F6F7FB; }}
    .stAppDeployButton {{ display: none; }}
    .block-container {{ padding-top: 2.2rem; max-width: 1250px; }}

    [data-testid="stSidebar"] {{ background: var(--ink); }}
    [data-testid="stSidebar"] > div:first-child {{ padding-top: 0; }}
    [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding-top: 0; }}
    [data-testid="stSidebar"] * {{ color: #E8EAF0; }}
    [data-testid="stSidebar"] .stButton button {{
        background: transparent; border: 1px solid #4a5163; color: #fff;
    }}
    [data-testid="stSidebar"] .stButton button:hover {{
        border-color: var(--accent); color: #fff;
    }}
    .brandpanel {{
        background: rgba(255,255,255,.06); margin: 0 -1rem 1.2rem;
        padding: 22px 20px 16px;
    }}
    .navlabel {{
        color: var(--accent) !important; font-size: .72rem; font-weight: 600;
        letter-spacing: .14em; margin: .4rem 0 .2rem;
    }}
    [data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stRadio"]),
    [data-testid="stSidebar"] [data-testid="stRadio"],
    [data-testid="stSidebar"] [data-testid="stRadio"] > div {{ width: 100% !important; }}
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] {{ gap: 0; width: 100%; }}
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div {{ width: 100%; }}
    [data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
        display: flex; width: 100%; margin: 0; padding: 13px 2px;
        border-bottom: 1px solid #8a2a2f !important; cursor: pointer;
    }}
    [data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {{
        display: none;
    }}
    [data-testid="stSidebar"] label[data-testid="stRadioOption"] p {{
        font-size: .74rem; font-weight: 600; letter-spacing: .09em;
        text-transform: uppercase;
    }}
    [data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover p {{ color: #fff; }}
    [data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p {{
        color: var(--accent);
    }}
    .dsbox {{ margin-top: 1.4rem; }}
    .dsbox .k {{ font-size: .7rem; letter-spacing: .12em; color: #9aa1b4 !important; }}
    .dsbox .v {{ font-size: .95rem; font-weight: 600; margin-top: 2px; }}
    .brandrow {{ display:flex; align-items:center; gap:12px; }}
    .brandrow .sub {{ font-size:.7rem; color:#9aa1b4 !important; letter-spacing:.08em; }}
    .logo {{ display:inline-flex; }}
    .authbox {{ text-align:center; margin-top:4vh; }}
    .authbox .logo {{ margin-bottom:.6rem; }}
    .brand {{ font-size: 1.15rem; font-weight: 700; letter-spacing: .2px; }}
    .brand b {{ color: var(--accent); }}
    .who {{ font-size: .82rem; color: #9aa1b4 !important; word-break: break-all; }}

    .hero h1 {{ font-size: 2.3rem; margin-bottom: .2rem; color: var(--ink); }}
    .hero p {{ color: #5b6275; font-size: 1.05rem; margin-bottom: 1.4rem; }}
    .muted {{ color: #7a8196; font-size: .85rem; }}
    .chip {{
        display: inline-block; background: #F1F3F9; border-radius: 999px;
        padding: 3px 12px; margin: 2px 6px 2px 0; font-size: .82rem; color: #3b4257;
    }}

    .stepper {{ display: flex; gap: 10px; margin: 0 0 1.4rem; }}
    .step {{
        flex: 1; display: flex; align-items: center; gap: 10px;
        padding: 10px 14px; border-radius: 10px; background: #fff;
        border: 1px solid #e3e6ee; color: #7a8196;
    }}
    .step span {{
        width: 24px; height: 24px; border-radius: 50%; background: #e3e6ee;
        display: inline-flex; align-items: center; justify-content: center;
        font-weight: 600; font-size: .8rem; color: #5b6275;
    }}
    .step.active {{ border-color: var(--accent); color: var(--ink); font-weight: 600; }}
    .step.active span {{ background: var(--accent); color: #fff; }}
    .step.done span {{ background: var(--ink); color: #fff; }}

    [data-testid="stMetric"] {{
        background: #fff; border: 1px solid #e3e6ee; border-radius: 12px;
        padding: 14px 16px; box-shadow: 0 1px 2px rgba(20,25,40,.06);
    }}
    [data-testid="stMetricLabel"] p {{ color: #5b6275; }}
    [data-testid="stVerticalBlockBorderWrapper"] {{ background: #fff; border-radius: 12px; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# Placeholder logo: replace the inner <svg> (or use an <img src="data:...">)
# with your own mark. Keep the wrapper so sizes stay consistent.
LOGO_HTML = (
    '<span class="logo"><svg viewBox="0 0 32 32" width="32" height="32">'
    '<rect width="32" height="32" rx="8" fill="%s"/>'
    '<rect x="7" y="16" width="4.5" height="9" rx="1" fill="#fff"/>'
    '<rect x="13.8" y="10" width="4.5" height="15" rx="1" fill="#fff"/>'
    '<rect x="20.5" y="6" width="4.5" height="19" rx="1" fill="#fff"/>'
    "</svg></span>" % ACCENT
)


@st.cache_resource
def get_store():
    return get_storage()


store = get_store()


# ============================================================
# DASHBOARD GENERATION
# ============================================================

def generate_dashboard(question, schema, db):
    """Plan and execute every dashboard item."""
    progress = st.progress(0.0, text="Planning...")

    def on_progress(i, total, title):
        progress.progress(
            i / max(total, 1),
            text=f"Analyzing: {title}",
        )

    try:
        return run_dashboard(
            question,
            schema,
            db,
            on_progress=on_progress,
        )
    finally:
        progress.empty()


# ============================================================
# GLOBAL DASHBOARD FILTERS
# ============================================================

NO_FILTER = "__no_filter__"


def reset_dashboard_filters():
    """Clear applied filters and restore the original DuckDB views."""
    st.session_state["applied_dashboard_filters"] = {}

    # Reset the global calendar controls.
    st.session_state["dashboard_date_filter_enabled"] = False
    st.session_state.pop("dashboard_date_range", None)

    # Reset the categorical control.
    st.session_state["dashboard_category_field"] = NO_FILTER

    # Remove selections belonging to previously selected categories.
    for key in list(st.session_state.keys()):
        if key.startswith("dashboard_category_values::"):
            del st.session_state[key]

    # Drop any active cross-filter (chart-click) and reset the chart that set it.
    cf = st.session_state.pop("cross_filter", None)
    if cf and cf.get("source_key"):
        st.session_state.pop(cf["source_key"], None)
    _bump_filter_widgets()

    # Remove any cached filtered dashboard.
    st.session_state.pop("filtered_dashboard_cache", None)

    # Restore the original unfiltered logical views.
    db = st.session_state.get("db")
    if db is not None:
        db.set_filters({})


def _date_bounds(date_dimension):
    return (
        pd.Timestamp(date_dimension["min_date"]).date(),
        pd.Timestamp(date_dimension["max_date"]).date(),
    )


def collect_dashboard_filters(catalog):
    """Read the filter widgets' state and build the filter dict.
    Same output as before the redesign: {"date": {...}, "category": {...}}."""
    date_dimension = catalog.get("date_dimension")
    category_lookup = {f["id"]: f for f in catalog.get("category_fields", [])}
    new_filters = {}

    selected = st.session_state.get("dashboard_date_range")
    if (
        date_dimension
        and st.session_state.get("dashboard_date_filter_enabled", False)
        and selected
    ):
        if isinstance(selected, (tuple, list)):
            if len(selected) >= 2:
                start_date, end_date = selected[0], selected[1]
            elif len(selected) == 1:
                start_date = end_date = selected[0]
            else:
                start_date = end_date = None
        else:
            start_date = end_date = selected

        if start_date is not None and end_date is not None:
            new_filters["date"] = {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "mappings": [
                    {"table": m["table"], "column": m["column"]}
                    for m in date_dimension["mappings"]
                ],
            }

    field_id = st.session_state.get("dashboard_category_field", NO_FILTER)
    if field_id != NO_FILTER and field_id in category_lookup:
        values = st.session_state.get("dashboard_category_values::" + field_id, [])
        if values:
            field = category_lookup[field_id]
            new_filters["category"] = {
                "table": field["table"],
                "column": field["column"],
                "values": list(values),
            }
    return new_filters


def _pill_label(base, active_text):
    return f"{base}: {active_text}" if active_text else base


def render_filter_bar(dash, catalog):
    """The dashboard's top bar: three pills that open drop-downs (Date,
    Category, Overview) and the dashboard title on the right. Returns the
    applied filters."""
    date_dimension = catalog.get("date_dimension")
    category_fields = catalog.get("category_fields", [])
    category_lookup = {f["id"]: f for f in category_fields}
    active = st.session_state.get("applied_dashboard_filters", {})

    st.session_state.setdefault("dashboard_date_filter_enabled", False)
    st.session_state.setdefault("dashboard_category_field", NO_FILTER)

    date_text = None
    if active.get("date"):
        d = active["date"]
        date_text = "filtered"
    cat_text = None
    if active.get("category"):
        c = active["category"]
        cat_text = f"{len(c['values'])} selected"

    apply_clicked = False

    with st.container(key="dash_header"):
        col_date, col_cat, col_info, col_gap, col_title = st.columns([1.1, 1.1, 1, 0.3, 2.6])

        # ---------------- DATE ----------------
        with col_date:
            if date_dimension:
                with st.popover(_pill_label("Date", date_text), use_container_width=True):
                    min_date, max_date = _date_bounds(date_dimension)
                    st.markdown("**Period**")
                    enabled = st.checkbox(
                        "Filter by period", key="dashboard_date_filter_enabled"
                    )
                    st.date_input(
                        "Select period",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date,
                        key="dashboard_date_range",
                        format="DD/MM/YYYY",
                        disabled=not enabled,
                    )
                    st.caption(
                        f"Applied to {len(date_dimension['mappings'])} date "
                        "columns of the dataset."
                    )
                    a, b = st.columns(2)
                    if a.button("Apply", type="primary", use_container_width=True,
                                key="apply_filters_date"):
                        apply_clicked = True
                    b.button("Clear", use_container_width=True,
                             key="clear_filters_date", on_click=reset_dashboard_filters)
            else:
                st.button("Date", disabled=True, use_container_width=True,
                          key="date_pill_off", help="No date column was detected.")

        # ---------------- CATEGORY ----------------
        with col_cat:
            if category_lookup:
                with st.popover(_pill_label("Category", cat_text), use_container_width=True):
                    st.markdown("**Category**")
                    field_id = st.selectbox(
                        "Filter by",
                        options=[NO_FILTER] + list(category_lookup.keys()),
                        format_func=lambda v: (
                            "No category filter" if v == NO_FILTER
                            else f"{category_lookup[v]['column']} "
                                 f"({category_lookup[v]['table']})"
                        ),
                        key="dashboard_category_field",
                    )
                    if field_id != NO_FILTER:
                        values_key = "dashboard_category_values::" + field_id
                        st.session_state.setdefault(values_key, [])
                        st.multiselect(
                            "Values",
                            options=category_lookup[field_id]["values"],
                            key=values_key,
                        )
                    a, b = st.columns(2)
                    if a.button("Apply", type="primary", use_container_width=True,
                                key="apply_filters_category"):
                        apply_clicked = True
                    b.button("Clear", use_container_width=True,
                             key="clear_filters_category", on_click=reset_dashboard_filters)
            else:
                st.button("Category", disabled=True, use_container_width=True,
                          key="cat_pill_off", help="No category column was detected.")

        # ---------------- OVERVIEW ----------------
        with col_info:
            with st.popover("Overview", use_container_width=True):
                st.markdown(f"**Your question**\n\n{dash['question']}")
                if dash["plan"].get("focus"):
                    st.caption(dash["plan"]["focus"])
                added = dash["plan"].get("added") or []
                if added:
                    st.caption(
                        f"{len(added)} supporting indicator(s) were added to give "
                        "the full picture."
                    )

        with col_title:
            st.markdown(
                f'<div class="dash-title">{html.escape(dash["plan"]["title"])}</div>',
                unsafe_allow_html=True,
            )

    if apply_clicked:
        # A manual pill choice overrides any chart-click cross-filter; reset the
        # originating chart's selection so it does not re-apply on the next run.
        cf = st.session_state.pop("cross_filter", None)
        if cf and cf.get("source_key"):
            st.session_state.pop(cf["source_key"], None)
        _bump_filter_widgets()
        st.session_state["applied_dashboard_filters"] = collect_dashboard_filters(catalog)
        st.session_state.pop("filtered_dashboard_cache", None)
        st.rerun()

    return st.session_state.get("applied_dashboard_filters", {})


# ============================================================
# RE-EXECUTE SAVED DASHBOARD SQL
# ============================================================

def refresh_dashboard_with_filters(dash, filters):
    """Re-run saved, previously validated panel SQL against filtered views."""
    db = st.session_state["db"]

    # No filters: restore original views and original dashboard results.
    if not filters:
        db.set_filters({})
        return dash

    payload = {
        "question": dash.get("question"),
        "sql": [
            {
                "id": result.get("item", {}).get("id"),
                "sql": result.get("sql"),
            }
            for result in dash.get("results", [])
        ],
        "filters": filters,
    }
    signature = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    cached = st.session_state.get("filtered_dashboard_cache")
    if cached and cached.get("signature") == signature:
        return cached["dashboard"]

    # Rebuild the existing DuckDB logical views using the selected filters.
    row_summary = db.set_filters(filters)
    refreshed_results = []

    for result in dash.get("results", []):
        updated = dict(result)
        sql = result.get("sql")

        # Preserve unsupported, blocked and initially failed panels.
        if result.get("error") is not None or not sql:
            refreshed_results.append(updated)
            continue

        try:
            # Reuse the saved SQL. No planner or LLM call is made here.
            df = execute_sql(sql, db)
            updated["df"] = df

            if df is None or df.empty:
                updated["error"] = (
                    "No records match the selected dashboard filters."
                )
                updated["stage"] = "filter_empty"
                updated["notes"] = []
                refreshed_results.append(updated)
                continue

            updated["error"] = None
            updated["stage"] = "completed"

            # Re-check filtered results with the original panel intent.
            item = result["item"]
            try:
                issues = check_result(
                    item["question"],
                    item["kind"],
                    item.get("constraints"),
                    sql,
                    df,
                    db,
                )

                errors = [
                    issue for issue in issues
                    if issue.get("severity") == "error"
                ]
                warnings = [
                    issue["message"] for issue in issues
                    if issue.get("severity") == "warning"
                ]

                updated["issues"] = issues
                updated["notes"] = warnings

                if errors:
                    updated["notes"].append(
                        "Semantic validation after filtering: "
                        + format_problem(issues)
                    )
            except Exception as exc:
                updated["notes"] = [
                    "Filtered query executed, but semantic revalidation "
                    f"could not be completed: {exc}"
                ]

            updated["filter_refreshed"] = True

        except Exception as exc:
            updated["df"] = None
            updated["error"] = f"Could not refresh this panel: {exc}"
            updated["stage"] = "filter_execution"

        refreshed_results.append(updated)

    filtered_dashboard = dict(dash)
    filtered_dashboard["results"] = refreshed_results
    filtered_dashboard["filter_row_summary"] = row_summary
    filtered_dashboard["active_filters"] = filters

    st.session_state["filtered_dashboard_cache"] = {
        "signature": signature,
        "dashboard": filtered_dashboard,
    }
    return filtered_dashboard


# ============================================================
# RENDERING
# ============================================================

TIME_KEYWORDS = (
    "over time", "trend", "monthly", "by month", "per month",
    "by year", "yearly", "daily", "weekly", "by date", "evolution",
)

# Pale palette built around the Devoteam red and ink colours.
PALETTE = ["#E8645C", "#33415C", "#8EB8C7", "#F4B1AB", "#A7B4C8", "#F2CF9A", "#7FB7A5"]
BAR_COLOUR = "#7FAFC0"      # single-series bars: pale teal, like the reference

DASHBOARD_CSS = """
<style>
.stApp { background: linear-gradient(180deg, #E8F0F5 0%, #F2F5F9 60%); }
.block-container { max-width: 1320px; }
.st-key-dash_header {
    background: #fff; border-radius: 22px; padding: 10px 18px;
    box-shadow: 0 6px 20px rgba(40,70,90,.10); margin-bottom: 1.1rem;
}
.st-key-dash_header button {
    border-radius: 999px; font-weight: 600; background: #E3EDF2;
    border: 0; color: #1B1F2A;
}
.st-key-dash_header button:hover { background: #F9D6D3; color: #1B1F2A; }
.st-key-dash_header button:disabled { background: #F0F3F6; color: #9aa3b2; }
.dash-title {
    text-align: right; font-weight: 700; font-size: 1.15rem;
    color: #1B1F2A; padding-top: 6px; line-height: 1.2;
}
[class*="st-key-card_"] {
    border: 0 !important; background: #fff !important; border-radius: 16px;
    box-shadow: 0 2px 12px rgba(40,70,90,.08); padding: 10px 12px 16px;
}
.kpi:before {
    content: ""; display: block; width: 26px; height: 3px;
    background: var(--accent); border-radius: 3px; margin-bottom: 10px;
}
.kpi-label { color: #5b6275; font-size: .85rem; line-height: 1.25; min-height: 2.1em; }
.kpi-value { color: #1B1F2A; font-size: 2.1rem; font-weight: 700; line-height: 1.2; padding-bottom: 4px; }
.ptitle { font-weight: 700; font-size: 1.02rem; color: #1B1F2A; margin: 2px 0 6px; }
.pnote { color: #7a8196; font-size: .8rem; }
.filter-line { color: #5b6275; font-size: .85rem; margin: -.3rem 0 .8rem; }
</style>
"""


def style_figure(fig):
    """Make every chart look like part of the same dashboard."""
    try:
        # A long horizontal bar list asked for a taller figure: keep it readable.
        asked = fig.layout.height or 0
        height = 300 if asked <= 420 else min(int(asked * 0.75), 900)
        fig.update_layout(
            colorway=PALETTE,
            title_text=None,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=height,
            margin=dict(l=8, r=8, t=8, b=8),
            font=dict(size=12, color="#33415C"),
            legend=dict(orientation="h", y=-0.22, x=0, title_text=""),
        )
        fig.update_xaxes(showgrid=False, linecolor="#D5DCE5", title_font_size=11,
                         automargin=True)
        fig.update_yaxes(gridcolor="#E8EDF2", zeroline=False, title_font_size=11,
                         automargin=True)
        # Traces that carry one explicit colour get the palette colour in turn.
        for i, trace in enumerate(fig.data):
            colour = PALETTE[i % len(PALETTE)]
            if trace.type in ("bar", "histogram"):
                current = getattr(trace.marker, "color", None)
                if current is None or isinstance(current, str):
                    single = sum(1 for t in fig.data if t.type in ("bar", "histogram")) == 1
                    trace.update(marker=dict(color=BAR_COLOUR if single else colour))
            elif trace.type == "scatter":
                trace.update(line=dict(color=colour, width=2.6))
                if trace.mode == "markers":
                    trace.update(marker=dict(color=colour))
        fig.update_traces(selector=dict(type="pie"), hole=0.55,
                          marker=dict(line=dict(color="#fff", width=2)))
    except Exception:
        pass
    return fig


def _kpi_headline(df, metadata):
    """What a KPI card should show, as (headline, subvalue).

    - A plain single number ("Total trips") -> (formatted number, None).
    - A "which X is highest/lowest" answer, whose row is (label, number) -> the
      LABEL is the headline and the number is the small subvalue. This fixes a
      card titled "Customer Type with Highest Revenue" that showed the amount
      (e.g. 206.8M) instead of the type ("Contract")."""
    if df is None or len(df) != 1:
        return None, None
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    labels = [c for c in df.columns if c not in numeric]

    # one label + at least one number: the answer is the label
    if len(labels) == 1 and numeric:
        label_value = df[labels[0]].iloc[0]
        num_col = metadata.get("y") if metadata.get("y") in numeric else numeric[0]
        num_value = df[num_col].iloc[0]
        if pd.notna(label_value):
            sub = None if pd.isna(num_value) else format_metric_value(num_value, num_col)
            return str(label_value), sub

    # a plain number
    column = metadata.get("y")
    if column is None or column not in df.columns:
        column = numeric[0] if numeric else df.columns[0]
    value = df[column].iloc[0]
    if pd.isna(value):
        return None, None
    return format_metric_value(value, column), None


def _kpi_value(df, metadata):
    """Backwards-compatible: the headline part of a KPI, or None."""
    return _kpi_headline(df, metadata)[0]


_DELTA_HEX = {"green": "#1f9d57", "red": "#d64545", "amber": "#d99100", "neutral": "#6b7280"}


def _kpi_trend_for(res, db, date_dimension):
    """Previous-period delta + sparkline for one KPI, or None. Never raises."""
    sql = res.get("sql")
    if not sql or db is None or res.get("error") or res.get("df") is None:
        return None
    try:
        return kpi_trend(lambda f: db.run_with_filters(sql, f), sql, date_dimension,
                         title=res["item"]["title"])
    except Exception:
        return None


def render_kpi(res, trend=None):
    item = res["item"]
    df, error = res.get("df"), res.get("error")
    label = html.escape(item["title"])

    value_text, sub_text = None, None
    if not error and df is not None:
        metadata = build_visual_metadata(df, "card", item["question"], title=item["title"])
        value_text, sub_text = _kpi_headline(df, metadata)

    if value_text is None:
        reason = html.escape(str(error or "No value available."))
        st.markdown(
            f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">n/a</div><div class="pnote">{reason}</div></div>',
            unsafe_allow_html=True,
        )
        return

    sub_html = (
        f'<div class="kpi-sub" style="font-size:0.8rem;color:#6b7280;margin-top:2px;">'
        f'{html.escape(str(sub_text))}</div>' if sub_text else ''
    )

    # A delta + sparkline, like a BI tool. Only for a plain numeric KPI: a
    # "which type is highest" card (sub_text set) has no sensible period trend.
    trend_html = ''
    if trend and sub_text is None:
        text, color = format_delta(trend, format_metric_value)
        svg = sparkline_svg(trend["series"], color)
        hexcol = _DELTA_HEX.get(color, _DELTA_HEX["neutral"])
        delta_html = (f'<span style="color:{hexcol};font-size:0.82rem;font-weight:600;">'
                      f'{html.escape(text)}</span>' if text else '')
        if delta_html or svg:
            trend_html = (
                '<div class="kpi-trend" style="display:flex;align-items:center;'
                f'justify-content:space-between;gap:8px;margin-top:6px;">{delta_html}{svg}</div>')

    st.markdown(
        f'<div class="kpi"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{html.escape(str(value_text))}</div>{sub_html}{trend_html}</div>',
        unsafe_allow_html=True,
    )
    for assumption in res.get("assumptions", []):
        st.caption(f"Assumption: {assumption}")


def render_panel_details(results):
    """One collapsed section with the SQL and data behind every panel, so the
    cards stay clean."""
    with st.expander("SQL and data behind each panel"):
        for res in results:
            item = res["item"]
            st.markdown(f"**{item['title']}**  \n"
                        f"<span class='pnote'>{html.escape(item['question'])}</span>",
                        unsafe_allow_html=True)
            if res.get("attempts", 1) > 1:
                st.caption(f"Self-corrected: succeeded on attempt {res['attempts']}.")
            for note in res.get("notes", []):
                st.caption(f"Note: {note}")
            if res.get("sql"):
                st.code(res["sql"], language="sql")
            if res.get("df") is not None:
                st.dataframe(res["df"], width="stretch")
            st.divider()


# ------------------------------------------------------------
# CROSS-FILTERING: click a bar/pie slice to filter the whole dashboard
# ------------------------------------------------------------

def _category_field_for_value(catalog, clicked, prefer_col=None):
    """Find the catalog category field whose value list contains the clicked
    value. If several match, prefer the one whose column is the clicked chart's
    own dimension. Returns None when the value is not a filterable category."""
    clicked_s = str(clicked)
    fields = catalog.get("category_fields", []) if catalog else []
    matches = [
        f for f in fields
        if any(str(v) == clicked_s for v in f.get("values", []))
    ]
    if not matches:
        return None
    if prefer_col:
        for f in matches:
            if str(f["column"]).lower() == str(prefer_col).lower():
                return f
    return matches[0]


def _clicked_value(points):
    """The category value behind a Plotly click (x for a vertical bar, label for
    a pie, y for a horizontal bar)."""
    if not points:
        return None
    pt = points[0]
    # The renderer stores the raw category in customdata, because the visible
    # label can be a combined one ("Charlotte – Portland").
    custom = pt.get("customdata")
    if isinstance(custom, (list, tuple)) and custom:
        custom = custom[0]
    if custom is not None and not isinstance(custom, (bool, dict)):
        return custom
    if pt.get("label") is not None:
        return pt["label"]
    for key in ("x", "y"):                       # the text side: x (vertical) or y (horizontal)
        v = pt.get(key)
        if isinstance(v, str):
            return v.split(" – ")[0]
    for key in ("x", "y"):
        v = pt.get(key)
        if v is not None and not isinstance(v, bool):
            return v
    return pt.get("value")


def _apply_cross_filter(field, clicked, source_key):
    """Set the chart-click as the dashboard's category filter and rerun. The
    guard returns without rerunning when the same slice is already applied, so
    the persisted selection never causes a rerun loop."""
    new = {"field_id": field["id"], "value": str(clicked), "source_key": source_key}
    cur = st.session_state.get("cross_filter")
    if (cur and cur.get("field_id") == new["field_id"]
            and cur.get("value") == new["value"]
            and cur.get("source_key") == source_key):
        return
    # Switching source chart: reset the previous one's selection so only one
    # chart ever carries a live selection.
    if cur and cur.get("source_key") and cur["source_key"] != source_key:
        st.session_state.pop(cur["source_key"], None)
        _bump_filter_widgets()
    st.session_state["cross_filter"] = new
    applied = dict(st.session_state.get("applied_dashboard_filters", {}))
    applied["category"] = {
        "table": field["table"], "column": field["column"], "values": [clicked],
    }
    st.session_state["applied_dashboard_filters"] = applied
    st.session_state.pop("filtered_dashboard_cache", None)
    st.rerun()


def _handle_chart_selection(event, df, catalog, source_key):
    """Read a Plotly selection event and, when it lands on a filterable
    category, apply it as a cross-filter. Unknown values are ignored silently."""
    try:
        points = event.selection.points if event and event.selection else []
    except Exception:
        points = []
    if not points:
        return
    clicked = _clicked_value(points)
    if clicked is None:
        return
    prefer_col = None
    try:
        obj_cols = [c for c in df.columns if str(df[c].dtype) == "object"]
        prefer_col = obj_cols[0] if obj_cols else None
    except Exception:
        prefer_col = None
    field = _category_field_for_value(catalog, clicked, prefer_col)
    if field is not None:
        _apply_cross_filter(field, clicked, source_key)


def _bump_filter_widgets():
    """Pills keep their value in the browser even when their state is popped, so
    resetting them means giving them a fresh key (pills_<idx>_v<n>)."""
    st.session_state["xf_ver"] = st.session_state.get("xf_ver", 0) + 1


def clear_cross_filter():
    """on_click callback for the 'Clear cross-filter' button."""
    _bump_filter_widgets()
    cf = st.session_state.pop("cross_filter", None)
    if cf and cf.get("source_key"):
        st.session_state.pop(cf["source_key"], None)   # reset the chart selection
    applied = dict(st.session_state.get("applied_dashboard_filters", {}))
    applied.pop("category", None)
    st.session_state["applied_dashboard_filters"] = applied
    st.session_state.pop("filtered_dashboard_cache", None)


def _pie_filter_pills(df, metadata, catalog, idx):
    """Plotly pies emit no selection events in Streamlit, so a pie gets a row of
    pills under it: picking one cross-filters the dashboard like a bar click."""
    labels = pie_labels(df, metadata)
    x = metadata.get("x")
    options = [v for v in labels if _category_field_for_value(catalog, v, x) is not None]
    if not options:
        return
    key = f"pills_{idx}_v{st.session_state.get('xf_ver', 0)}"
    cross = st.session_state.get("cross_filter") or {}
    # Clearing the filter elsewhere (button, filter bar, another chart) pops this
    # key, so the pill is unselected again on the next run.
    choice = st.pills("Filter by", options, selection_mode="single", key=key,
                      label_visibility="collapsed")
    if choice:
        field = _category_field_for_value(catalog, choice, x)
        if field is not None:
            _apply_cross_filter(field, choice, key)
    elif cross.get("source_key") == key:
        clear_cross_filter()
        st.rerun()


def _sorted_table(df, item):
    """A table panel, sorted the way the user asked (item["sort"])."""
    sort = item.get("sort") or {}
    if not sort or df is None or df.empty:
        return df
    by = sort.get("by")
    if by not in df.columns:
        numeric = [c for c in df.columns
                   if pd.api.types.is_numeric_dtype(df[c]) and not str(c).lower().endswith("_id")]
        meta_y = build_visual_metadata(df, "bar", item.get("question", "")).get("y")
        by = meta_y if meta_y in df.columns else (numeric[-1] if numeric else None)
    if by is None:
        return df
    return df.sort_values(by, ascending=bool(sort.get("ascending")), na_position="last")


def show_table(df, **kwargs):
    """st.dataframe with readable numbers (85,410 not 85410); ids stay raw."""
    config = {}
    try:
        for c in df.columns:
            name = str(c).lower()
            if (pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
                    and not (name == "id" or name.endswith("_id") or name in ("year", "unit_number"))):
                config[c] = st.column_config.NumberColumn(format="localized")
    except Exception:
        config = {}
    try:
        st.dataframe(df, width="stretch", hide_index=True, column_config=config or None, **kwargs)
    except Exception:
        st.dataframe(df, width="stretch", hide_index=True, **kwargs)


def render_item(res, idx, catalog=None, allow_cross_filter=False):
    """One chart or table panel (KPIs go through render_kpi)."""
    item = res["item"]
    df = res.get("df")
    error = res.get("error")
    sql = res.get("sql")
    attempts = res.get("attempts", 1)

    st.markdown(f'<div class="ptitle">{html.escape(item["title"])}</div>',
                unsafe_allow_html=True)

    if error:
        stage = res.get("stage")
        if stage == "unsupported":
            st.info(f"Not available in this dataset: {error}")
        elif stage == "blocked":
            st.warning(f"Not executed: {error}")
        elif stage == "filter_empty":
            st.info("No records match the currently selected filters.")
        elif stage == "filter_execution":
            st.warning(f"Could not refresh this panel with the selected filters: {error}")
        else:
            st.warning(f"Could not generate this visualization: {error}")
        if attempts > 1:
            st.caption(f"The SQL agent tried {attempts} times before giving up.")
        if sql:
            with st.expander("Generated SQL"):
                st.code(sql, language="sql")
        return

    if df is None:
        st.warning("No result data is available for this panel.")
        return

    kind = item["kind"]
    columns_lower = {str(column).lower() for column in df.columns}
    has_time_intent = any(k in item["question"].lower() for k in TIME_KEYWORDS)
    has_year_month = {"year", "month"}.issubset(columns_lower)
    has_date_column = any(
        any(word in column for word in ("date", "datetime", "timestamp", "month_start"))
        for column in columns_lower
    )
    if (kind in ("bar", "pie") and not item.get("kind_locked") and not item.get("style")
            and has_time_intent and (has_year_month or has_date_column)):
        kind = "line"

    if kind == "table":
        show_table(_sorted_table(df, item))
    else:
        metadata = {}
        try:
            intent_text = f"{item['title']} {item['question']}"
            metadata = build_visual_metadata(df, kind, intent_text, title=item["title"])
            metadata["style"] = item.get("style")
            metadata["sort"] = item.get("sort")
            fig = render_visual(df, metadata)
            if metadata.get("note"):
                st.caption(metadata["note"])
            if metadata.get("chart") == "table":
                reason = metadata.get("fallback_reason")
                st.caption(f"Shown as a table: {reason}" if reason
                           else "Shown as a table: no suitable chart for these columns.")
        except Exception as exc:
            fig = None
            st.warning(f"Chart rendering failed: {exc}. Showing the data instead.")

        if fig is not None:
            chart_config = {
                # one tool only: "download as PNG", shown when hovering the chart
                "displayModeBar": "hover",
                "modeBarButtons": [["toImage"]],
                "displaylogo": False,
                "responsive": True,
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": f"dashboard_chart_{idx + 1}",
                    "height": 800, "width": 1200, "scale": 2,
                },
            }
            cross_ok = (
                allow_cross_filter
                and metadata.get("chart") == "bar"
                and metadata.get("style") not in ("treemap", "scatter", "histogram")
                and bool((catalog or {}).get("category_fields"))
            )
            pie_pills = (
                allow_cross_filter
                and metadata.get("chart") == "pie"
                and metadata.get("style") is None
                and bool((catalog or {}).get("category_fields"))
            )
            if cross_ok:
                # versioned like the pills: a cleared selection must not come back
                chart_key = f"chart_{idx}_v{st.session_state.get('xf_ver', 0)}"
                event = st.plotly_chart(
                    style_figure(fig),
                    width="stretch",
                    theme=None,
                    key=chart_key,
                    on_select="rerun",
                    selection_mode="points",
                    config=chart_config,
                )
                _handle_chart_selection(event, df, catalog, chart_key)
            else:
                st.plotly_chart(
                    style_figure(fig),
                    width="stretch",
                    theme=None,
                    key=f"chart_{idx}",
                    config=chart_config,
                )
                if pie_pills:
                    _pie_filter_pills(df, metadata, catalog, idx)
        else:
            show_table(_sorted_table(df, item))

    for assumption in res.get("assumptions", []):
        st.caption(f"Assumption: {assumption}")


# Width of a panel in a chart row (a row holds 3.5 units).
PANEL_WEIGHT = {"line": 2.0, "table": 2.0, "bar": 1.5, "pie": 1.0}
ROW_CAPACITY = 3.5


def pack_rows(charts):
    """Group charts into rows the way the reference dashboard does: a wide
    trend next to a donut, two bars side by side... Returns a list of rows,
    each a list of (index, result, weight)."""
    rows, current, used = [], [], 0.0
    for index, result in charts:
        weight = PANEL_WEIGHT.get(result["item"]["kind"], 1.5)
        if current and used + weight > ROW_CAPACITY:
            rows.append(current)
            current, used = [], 0.0
        current.append((index, result, weight))
        used += weight
    if current:
        rows.append(current)

    # A lonely last panel: a pie is centred, anything else takes the full width.
    return rows


def _render_answer_panel(panel):
    """Show a transient 'ask' answer as its natural KPI / chart / table."""
    if (panel.get("item") or {}).get("kind") == "kpi":
        render_kpi(panel)
    else:
        render_item(panel, 9999)


def render_followup_bar(dash):
    """Under the dashboard: one box to add a chart, refine or remove a panel,
    reorder, or ask a question. Modifications update the in-session dashboard;
    the user saves with the existing Save button. An 'ask' is answered here and
    can be pinned onto the dashboard."""
    schema = st.session_state.get("schema")
    db = st.session_state.get("db")
    if schema is None or db is None:
        return

    st.divider()
    st.markdown("#### Modify or ask")

    # the last result, shown right here next to the box (conversation style),
    # not as a page-top flash
    message = st.session_state.get("followup_message")
    if message:
        {"success": st.success, "info": st.info, "error": st.error}.get(
            message.get("level"), st.info)(message.get("text", ""))

    pending = st.session_state.get("followup_answer")
    if pending:
        with st.container(border=True):
            _render_answer_panel(pending)
            add_col, dismiss_col, _ = st.columns([1.3, 1, 4])
            if add_col.button("Add to dashboard", key="pin_followup", use_container_width=True):
                _push_undo(dash)
                pin_panel(dash, pending)
                st.session_state.pop("followup_answer", None)
                st.session_state["dashboard_dirty"] = True
                st.session_state.pop("filtered_dashboard_cache", None)
                st.session_state["followup_message"] = {
                    "level": "success", "text": "Added to the dashboard. Click Save to keep it."}
                st.rerun()
            if dismiss_col.button("Dismiss", key="dismiss_followup", use_container_width=True):
                st.session_state.pop("followup_answer", None)
                st.session_state.pop("followup_message", None)
                st.rerun()

    with st.form("followup_form", clear_on_submit=True):
        text = st.text_input(
            "Your request", label_visibility="collapsed",
            placeholder="e.g. add a KPI for total fuel cost, make the top 5 a top 10, "
                        "remove the pie, what is the revenue for Spot?")
        submitted = st.form_submit_button("Send", type="primary")

    if not (submitted and text.strip()):
        return
    st.session_state.pop("followup_message", None)
    st.session_state.pop("followup_answer", None)
    _push_undo(dash)
    try:
        with st.spinner("Working on it..."):
            action = classify_followup(text.strip(), dash, schema)
            result = apply_followup(action, dash, schema, db)
    except Exception as exc:
        _drop_undo()
        st.session_state["followup_message"] = {"level": "error", "text": f"I couldn't handle that: {exc}"}
        st.rerun()
        return

    if result["operation"] == "ask" or not result["ok"]:
        _drop_undo()                         # nothing changed on the dashboard
    if result["operation"] == "ask":
        if result.get("panel") is not None and result["panel"].get("df") is not None:
            st.session_state["followup_answer"] = result["panel"]
        else:
            st.session_state["followup_message"] = {"level": "info", "text": result["message"]}
    elif result["ok"]:
        st.session_state["dashboard_dirty"] = True
        st.session_state.pop("filtered_dashboard_cache", None)
        st.session_state["followup_message"] = {"level": "success", "text": result["message"]}
    else:
        st.session_state["followup_message"] = {"level": "info", "text": result["message"]}
    st.rerun()


# ------------------------------------------------------------
# UNDO: every change to a dashboard can be taken back
# ------------------------------------------------------------
UNDO_DEPTH = 10


def _push_undo(dash):
    """Remember the dashboard as it is, before a change. Panel items are copied
    (edits mutate them); result tables are shared, they are never changed."""
    stack = st.session_state.get("undo_stack")
    if not stack or stack.get("owner") != id(dash):
        stack = {"owner": id(dash), "items": []}
    stack["items"].append({
        "results": [dict(r, item=copy.deepcopy(r["item"])) for r in dash.get("results", [])],
        "title": (dash.get("plan") or {}).get("title"),
    })
    stack["items"] = stack["items"][-UNDO_DEPTH:]
    st.session_state["undo_stack"] = stack


def _drop_undo():
    """The change did not happen: forget the snapshot taken for it."""
    stack = st.session_state.get("undo_stack")
    if stack and stack["items"]:
        stack["items"].pop()


def _undo_available(dash):
    stack = st.session_state.get("undo_stack")
    return bool(stack and stack.get("owner") == id(dash) and stack["items"])


def undo_last_change(dash):
    """Put the dashboard back as it was before the last change."""
    if not _undo_available(dash):
        return False
    snap = st.session_state["undo_stack"]["items"].pop()
    dash["results"] = snap["results"]
    dash.setdefault("plan", {})["items"] = [r["item"] for r in snap["results"]]
    st.session_state["dashboard_dirty"] = True
    st.session_state.pop("filtered_dashboard_cache", None)
    st.session_state.pop("editing_panel", None)
    st.session_state.pop("edit_note", None)
    return True


def _panel_icons(dash, index):
    """Two small icon buttons (edit, remove) in the top-right corner of a panel."""
    _, tools = st.columns([6, 2.2])
    with tools:
        # A dedicated spacer column between the two icons guarantees a visible
        # gap (st.columns gap= alone left them stuck together on small cards).
        edit_col, _, remove_col = st.columns([1.3, 1, 1.3])
        if edit_col.button("", key=f"pedit_{index}", icon=":material/edit:",
                           help="Edit this panel", use_container_width=True):
            st.session_state["editing_panel"] = index
            st.rerun()
        if remove_col.button("", key=f"prem_{index}", icon=":material/delete:",
                             help="Remove this panel", use_container_width=True):
            _push_undo(dash)
            try:
                removed = remove_panel(dash, index)
                st.session_state["dashboard_dirty"] = True
                st.session_state.pop("filtered_dashboard_cache", None)
                st.session_state["followup_message"] = {
                    "level": "success", "text": f"Removed “{removed['item']['title']}”. Click Save to keep it."}
            except Exception as exc:
                _drop_undo()
                st.session_state["followup_message"] = {"level": "error", "text": f"Couldn't remove the panel: {exc}"}
            st.rerun()


def _panel_edit_input(dash, index):
    """Inline 'how should I change this panel?' form, shown in place of a panel
    when its Edit button was pressed."""
    schema = st.session_state.get("schema")
    db = st.session_state.get("db")
    item = dash["results"][index]["item"]
    st.caption(f"Refining: {item['title']}")
    note = st.session_state.get("edit_note")
    if note and note.get("index") == index:
        st.info(note["text"])
    with st.form(f"edit_form_{index}", clear_on_submit=True):
        instruction = st.text_input(
            "Change", label_visibility="collapsed",
            placeholder="e.g. rename it to ..., sort lowest to highest, show as a pie, make it top 10")
        apply_col, cancel_col, _ = st.columns([1, 1, 3])
        apply_it = apply_col.form_submit_button("Apply", type="primary", use_container_width=True)
        cancel = cancel_col.form_submit_button("Cancel", use_container_width=True)
    if cancel:
        st.session_state.pop("editing_panel", None)
        st.session_state.pop("edit_note", None)
        st.rerun()
    if not (apply_it and instruction.strip()):
        return

    def finish(result):
        """Success closes the editor with a toast; anything else keeps it open
        with the explanation (or the question) right above the input."""
        if not result["ok"]:
            _drop_undo()
        if result["ok"]:
            st.session_state["dashboard_dirty"] = True
            st.session_state.pop("filtered_dashboard_cache", None)
            st.session_state.pop("editing_panel", None)
            st.session_state.pop("edit_note", None)
            st.session_state["panel_toast"] = result["message"] + " Click Save to keep it."
        else:
            st.session_state["edit_note"] = {"index": index, "text": result["message"]}
        st.rerun()

    _push_undo(dash)
    # Look-only changes (rename, sort, show as ...) never touch the SQL.
    change = presentation_edit(instruction.strip(), dash["results"][index])
    if change is not None:
        finish(apply_presentation_edit(change, dash, index))

    try:
        with st.spinner("Updating the panel..."):
            action = classify_followup(
                f'Change the panel "{item["title"]}" so that: {instruction.strip()}', dash, schema)
            action.operation = "edit"                       # this is always an edit of THIS panel
            action.target = item.get("id") or item["title"]
            # The router sometimes proposes a new kind the user never asked
            # for (a table became a bar chart). Keep the kind unless named.
            if not re.search(r"\b(table|bar|line|pie|donut|kpi|card|chart|graph|trend)\b",
                             instruction.lower()):
                action.kind = None
                action.title = None
            if not action.question:
                action.question = f'{item["question"]} ({instruction.strip()})'
            result = apply_followup(action, dash, schema, db)
    except Exception as exc:
        result = {"ok": False, "message": f"Couldn't update the panel: {exc}"}
    finish(result)


def render_dashboard(dash):
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)
    toast = st.session_state.pop("panel_toast", None)
    if toast:
        st.toast(toast)

    catalog = st.session_state.get(
        "dashboard_filter_catalog",
        {"date_dimension": None, "category_fields": []},
    )
    # Narrow the dataset-wide catalog to THIS dashboard: the date range and the
    # category pills then match the panels actually on screen, so the filters bite.
    catalog = scope_catalog_to_dashboard(dash, catalog, st.session_state.get("data"))
    active_filters = render_filter_bar(dash, catalog)

    try:
        display_dashboard = refresh_dashboard_with_filters(dash, active_filters)
    except Exception as exc:
        st.error(f"Could not apply dashboard filters: {exc}")
        return

    results = display_dashboard["results"]

    insight = dashboard_insight(display_dashboard)
    if insight:
        st.caption(f"Insight: {insight}")

    # What the data could not answer, and what was refused.
    for flagged in dash.get("unsupported", []):
        st.info(f"Not available in this dataset: {flagged['request']}. {flagged['reason']}")
    for flagged in dash.get("blocked", []):
        st.warning(f"Not executed: {flagged['request']}. {flagged['reason']}")

    if active_filters:
        parts = []
        date_spec = active_filters.get("date")
        if date_spec:
            parts.append(f"Period {date_spec['start']} to {date_spec['end']}")
        category_spec = active_filters.get("category")
        if category_spec:
            parts.append(f"{category_spec['column']}: "
                         f"{', '.join(map(str, category_spec['values']))}")
        st.markdown(
            '<div class="filter-line">Filters: ' + html.escape(" · ".join(parts))
            + "</div>", unsafe_allow_html=True)
        summary = display_dashboard.get("filter_row_summary", {})
        if summary:
            with st.expander("Rows kept by the filters"):
                for table_name, counts in summary.items():
                    st.caption(f"{table_name}: {counts['before']:,} → {counts['after']:,} rows")

    kpis = [(i, r) for i, r in enumerate(results) if r["item"]["kind"] == "kpi"]
    charts = [(i, r) for i, r in enumerate(results) if r["item"]["kind"] != "kpi"]

    # Cross-filter banner: active state with a Clear button, or a one-line hint.
    cross = st.session_state.get("cross_filter")
    if cross:
        cc1, cc2 = st.columns([5, 1])
        with cc1:
            st.markdown(
                '<div class="filter-line">Cross-filter from a chart click: '
                + html.escape(str(cross.get("value"))) + "</div>",
                unsafe_allow_html=True,
            )
        with cc2:
            st.button("Clear cross-filter", key="clear_cross_filter_btn",
                      on_click=clear_cross_filter, use_container_width=True)
    elif catalog.get("category_fields") and any(
            r["item"]["kind"] in ("bar", "pie") for _, r in charts):
        st.caption("Tip: click a bar, or a category under a pie, to filter the whole dashboard.")

    if kpis:
        db = st.session_state.get("db")
        date_dimension = catalog.get("date_dimension")
        for column, (index, result) in zip(st.columns(len(kpis)), kpis):
            trend = _kpi_trend_for(result, db, date_dimension)
            with column:
                with st.container(border=True, key=f"card_kpi_{index}"):
                    if st.session_state.get("editing_panel") == index:
                        _panel_edit_input(dash, index)
                    else:
                        _panel_icons(dash, index)
                        render_kpi(result, trend)

    for row in pack_rows(charts):
        if len(row) == 1:
            index, result, weight = row[0]
            if result["item"]["kind"] == "pie":
                _, middle, _ = st.columns([1, 1.6, 1])
                slots = [(middle, row[0])]
            else:
                slots = [(st.container(), row[0])]
        else:
            columns = st.columns([w for _, _, w in row])
            slots = list(zip(columns, row))
        for column, (index, result, _) in slots:
            with column:
                with st.container(border=True, key=f"card_panel_{index}"):
                    if st.session_state.get("editing_panel") == index:
                        _panel_edit_input(dash, index)
                    else:
                        _panel_icons(dash, index)
                        render_item(result, index, catalog=catalog,
                                    allow_cross_filter=True)
                        explain = panel_explain(result)
                        if explain:
                            st.caption(explain)

    render_panel_details(results)
    render_followup_bar(dash)


# ============================================================
# SESSION: DATASET STATE
# ============================================================

DATASET_KEYS = (
    "data", "metadata", "schema", "profile", "dashboard",
    "dashboard_filter_catalog", "filtered_dashboard_cache",
    "applied_dashboard_filters", "dataset_id", "dataset_name",
    "dashboard_id", "dashboard_title",
)


def clear_dataset_state():
    """Close the database and forget the dataset, dashboard and filters."""
    old_db = st.session_state.pop("db", None)
    if old_db is not None:
        old_db.close()
    for key in DATASET_KEYS:
        st.session_state.pop(key, None)
    reset_dashboard_filters()


def activate_dataset(dataset_id, name, data, profile_result, schema, metadata):
    """Make a dataset the active one: query engine + filter catalog."""
    clear_dataset_state()

    with st.spinner("Loading the data into the query engine..."):
        db = open_database(data)

    st.session_state["db"] = db
    st.session_state["data"] = data
    st.session_state["metadata"] = metadata
    st.session_state["schema"] = schema
    st.session_state["profile"] = profile_result
    st.session_state["dataset_id"] = dataset_id
    st.session_state["dataset_name"] = name

    with st.spinner("Discovering the dashboard filters..."):
        try:
            catalog = discover_filter_catalog(data, profile_result)
        except Exception:
            # A stored profile may differ in small ways from a fresh one:
            # profile again rather than fail.
            catalog = discover_filter_catalog(data, profile(data))
    st.session_state["dashboard_filter_catalog"] = catalog
    st.session_state["applied_dashboard_filters"] = {}
    return catalog


def open_saved_dataset(dataset_id):
    data, profile_result, schema, meta = lib.load_dataset(store, USER_ID, dataset_id)
    # Rebuild the schema from the data so it carries the current value hints
    # (the saved schema may predate them), so SQL filters match the real casing.
    schema = build_schema(profile_result, data=data)
    activate_dataset(dataset_id, meta["name"], data, profile_result,
                     schema, metadata_from_data(data))


def open_saved_dashboard(dashboard_id):
    record = lib.load_dashboard(store, USER_ID, dashboard_id)

    if st.session_state.get("dataset_id") != record["dataset_id"]:
        open_saved_dataset(record["dataset_id"])

    db = st.session_state["db"]
    db.set_filters({})
    spec = record["spec"]

    with st.spinner("Rebuilding the dashboard from its saved SQL..."):
        dash = spec_to_dashboard(spec, lambda sql: execute_sql(sql, db))

    st.session_state["dashboard"] = dash
    st.session_state.pop("dashboard_dirty", None)
    st.session_state.pop("undo_stack", None)
    st.session_state.pop("export_file", None)
    st.session_state["applied_dashboard_filters"] = spec.get("filters") or {}
    st.session_state.pop("filtered_dashboard_cache", None)
    st.session_state["dashboard_id"] = dashboard_id
    st.session_state["dashboard_title"] = record["title"]


def go(page, step=None):
    """Switch page (and step of the New-dashboard flow) and rerun."""
    st.session_state["nav_target"] = page
    if step:
        st.session_state["flow_step"] = step
    st.rerun()


def flash(kind, text):
    st.session_state["flash"] = (kind, text)


def show_flash():
    message = st.session_state.pop("flash", None)
    if message:
        getattr(st, message[0])(message[1])


def log_out():
    clear_dataset_state()
    for key in ("user_id", "user_email", "page", "nav_target", "flow_step",
                "question_text", "flash"):
        st.session_state.pop(key, None)


# ============================================================
# LOGIN
# ============================================================

def auth_page():
    st.markdown(
        '<div class="authbox">%s<div class="hero"><h1>Devo'
        '<span style="color:%s">board</span></h1>'
        "<p>Turn your data into interactive dashboards by asking in plain "
        "language.</p></div></div>" % (LOGO_HTML.replace('width="32" height="32"', 'width="56" height="56"'), ACCENT),
        unsafe_allow_html=True,
    )

    _, middle, _ = st.columns([1, 1.3, 1])
    with middle:
        tab_in, tab_up = st.tabs(["Log in", "Create account"])

        with tab_in:
            with st.form("login_form"):
                email = st.text_input("E-mail")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log in", type="primary")
            if submitted:
                try:
                    st.session_state["user_id"] = login(store, email, password)
                    st.session_state["user_email"] = email.strip().lower()
                    st.rerun()
                except AuthError as exc:
                    st.error(str(exc))

        with tab_up:
            with st.form("register_form"):
                email = st.text_input("E-mail", key="reg_email")
                password = st.text_input(
                    "Password (at least 8 characters)",
                    type="password", key="reg_password",
                )
                again = st.text_input(
                    "Repeat the password", type="password", key="reg_again",
                )
                submitted = st.form_submit_button("Create account", type="primary")
            if submitted:
                if password != again:
                    st.error("The two passwords do not match.")
                else:
                    try:
                        st.session_state["user_id"] = register(store, email, password)
                        st.session_state["user_email"] = email.strip().lower()
                        st.rerun()
                    except AuthError as exc:
                        st.error(str(exc))


if "user_id" not in st.session_state:
    auth_page()
    st.stop()

USER_ID = st.session_state["user_id"]


# ============================================================
# SIDEBAR
# ============================================================

PAGES = {
    "home": "Home",
    "create": "New dashboard",
    "datasets": "My datasets",
    "dashboards": "My dashboards",
    "history": "History",
}

if "nav_target" in st.session_state:
    st.session_state["page"] = st.session_state.pop("nav_target")
st.session_state.setdefault("page", "home")
st.session_state.setdefault("flow_step", "data")

with st.sidebar:
    st.markdown(
        f'<div class="brandpanel"><div class="brandrow">{LOGO_HTML}'
        '<div><div class="brand">Devo<b>board</b></div>'
        f'<div class="sub">{html.escape(st.session_state["user_email"])}</div></div></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="navlabel">PAGES</div>', unsafe_allow_html=True)
    st.radio(
        "Navigation",
        options=list(PAGES),
        format_func=lambda key: PAGES[key],
        key="page",
        label_visibility="collapsed",
    )
    if st.session_state.get("dataset_name"):
        st.markdown(
            '<div class="dsbox"><div class="k">ACTIVE DATASET</div>'
            f'<div class="v">{html.escape(st.session_state["dataset_name"])}</div></div>',
            unsafe_allow_html=True,
        )
    st.write("")
    st.button("Log out", on_click=log_out, use_container_width=True)

page = st.session_state["page"]


# ============================================================
# SHARED PIECES
# ============================================================

STEPS = [("data", "Data"), ("ask", "Question"), ("dashboard", "Dashboard")]


def stepper(current):
    index = [key for key, _ in STEPS].index(current)
    cells = []
    for i, (key, label) in enumerate(STEPS):
        state = "done" if i < index else "active" if i == index else ""
        mark = "✓" if i < index else str(i + 1)
        cells.append(f'<div class="step {state}"><span>{mark}</span>{label}</div>')
    st.markdown('<div class="stepper">' + "".join(cells) + "</div>",
                unsafe_allow_html=True)


def dataset_card(with_continue=False):
    """Compact summary of the active dataset; the profiling insights sit
    behind 'Show details'."""
    metadata = st.session_state["metadata"]
    data = st.session_state["data"]
    name = html.escape(st.session_state["dataset_name"])

    with st.container(border=True):
        st.markdown(
            f'<div class="muted">Active dataset</div><h3 style="margin:0 0 .5rem">{name}</h3>'
            f'<span class="chip">{metadata["table_count"]} tables</span>'
            f'<span class="chip">{metadata["total_rows"]:,} rows</span>'
            f'<span class="chip">{metadata["total_columns"]} columns</span>',
            unsafe_allow_html=True,
        )
        with st.expander("Show details"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Tables", metadata["table_count"])
            c2.metric("Total rows", f"{metadata['total_rows']:,}")
            c3.metric("Total columns", metadata["total_columns"])

            st.markdown("**Tables**")
            st.dataframe(
                pd.DataFrame([
                    {"Table": t, "Rows": len(df), "Columns": len(df.columns)}
                    for t, df in data.items()
                ]),
                width="stretch", hide_index=True,
            )
            for table_name, df in data.items():
                with st.expander(f"Preview: {table_name}"):
                    st.dataframe(df.head(10), width="stretch")

            catalog = st.session_state.get("dashboard_filter_catalog") or {}
            date_dimension = catalog.get("date_dimension")
            if date_dimension:
                st.markdown(
                    f"**Global date range:** {date_dimension['min_date']} → "
                    f"{date_dimension['max_date']}"
                )
                st.dataframe(pd.DataFrame(date_dimension["mappings"]),
                             width="stretch", hide_index=True)

        if with_continue:
            if st.button("Continue: ask your question →", type="primary"):
                st.session_state["flow_step"] = "ask"
                st.rerun()


# ============================================================
# PAGE: HOME
# ============================================================

def page_home():
    st.markdown(
        '<div class="hero"><h1>Turn your data into a dashboard</h1>'
        "<p>Upload tables, describe what you want to understand, and get a "
        "validated, interactive dashboard you can save and reopen.</p></div>",
        unsafe_allow_html=True,
    )
    show_flash()

    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown("#### Upload new data")
        st.caption("CSV or Excel files. Several tables are fine: the joins are detected for you.")
        if st.button("Upload data", type="primary", key="home_upload"):
            go("create", "data")

    saved = lib.list_datasets(store, USER_ID)
    with right, st.container(border=True):
        st.markdown("#### Use a saved dataset")
        if not saved:
            st.caption("Nothing saved yet. Your uploads will appear here.")
        else:
            choice = st.selectbox(
                "Saved datasets", [d["id"] for d in saved],
                format_func=lambda i: next(d["name"] for d in saved if d["id"] == i),
                label_visibility="collapsed", key="home_saved_choice",
            )
            if st.button("Open dataset", key="home_open_dataset"):
                try:
                    open_saved_dataset(choice)
                    go("create", "overview")
                except Exception as exc:
                    st.error(f"Could not open this dataset: {exc}")

    st.write("")
    st.markdown("#### Recent dashboards")
    dashboards = lib.list_dashboards(store, USER_ID)[:4]
    if not dashboards:
        st.caption("Dashboards you save will show up here.")
    names = {d["id"]: d["name"] for d in saved}
    for d in dashboards:
        with st.container(border=True):
            a, b = st.columns([5, 1])
            a.markdown(f"**{d['title']}**")
            a.caption(f"{names.get(d['dataset_id'], 'deleted dataset')} · "
                      f"updated {d['updated'].replace('T', ' ')}")
            if b.button("Open", key=f"home_open_{d['id']}",
                        disabled=d["dataset_id"] not in names):
                try:
                    open_saved_dashboard(d["id"])
                    go("create", "dashboard")
                except Exception as exc:
                    st.error(f"Could not open this dashboard: {exc}")


# ============================================================
# PAGE: MY DATASETS
# ============================================================

def page_datasets():
    st.title("My datasets")
    datasets = lib.list_datasets(store, USER_ID)
    if not datasets:
        st.info("No saved dataset yet. Upload one from 'New dashboard'.")
        return

    dashboards = lib.list_dashboards(store, USER_ID)

    for meta in datasets:
        total_rows = sum(t["rows"] for t in meta["tables"].values())
        used_by = [d for d in dashboards if d["dataset_id"] == meta["id"]]
        with st.container(border=True):
            left, mid, right = st.columns([4, 1, 1])
            left.markdown(f"**{meta['name']}**")
            left.caption(
                f"{len(meta['tables'])} tables · {total_rows:,} rows · "
                f"saved {meta['created'].replace('T', ' ')} · "
                f"{len(used_by)} dashboard(s)"
            )
            if mid.button("Open", key=f"open_ds_{meta['id']}"):
                try:
                    open_saved_dataset(meta["id"])
                    lib.add_history(store, USER_ID, "dataset_open", meta["name"],
                                    dataset_id=meta["id"])
                    go("create", "overview")
                except Exception as exc:
                    st.error(f"Could not open this dataset: {exc}")

            confirm = right.checkbox("Confirm", key=f"confirm_ds_{meta['id']}",
                                     help="Deleting also deletes its dashboards.")
            if right.button("Delete", key=f"del_ds_{meta['id']}", disabled=not confirm):
                for d in used_by:
                    lib.delete_dashboard(store, USER_ID, d["id"])
                lib.delete_dataset(store, USER_ID, meta["id"])
                if st.session_state.get("dataset_id") == meta["id"]:
                    clear_dataset_state()
                st.rerun()


# ============================================================
# PAGE: MY DASHBOARDS
# ============================================================

def page_dashboards():
    st.title("My dashboards")
    dashboards = lib.list_dashboards(store, USER_ID)
    if not dashboards:
        st.info("No saved dashboard yet. Generate one and press 'Save'.")
        return

    names = {d["id"]: d["name"] for d in lib.list_datasets(store, USER_ID)}

    for d in dashboards:
        with st.container(border=True):
            left, mid, right = st.columns([4, 1, 1])
            left.markdown(f"**{d['title']}**")
            left.caption(
                f"Dataset: {names.get(d['dataset_id'], 'deleted')} · "
                f"updated {d['updated'].replace('T', ' ')}"
            )
            if mid.button("Open", key=f"open_db_{d['id']}",
                          disabled=d["dataset_id"] not in names):
                try:
                    open_saved_dashboard(d["id"])
                    lib.add_history(store, USER_ID, "dashboard_open", d["title"],
                                    dataset_id=d["dataset_id"], dashboard_id=d["id"])
                    go("create", "dashboard")
                except Exception as exc:
                    st.error(f"Could not open this dashboard: {exc}")

            confirm = right.checkbox("Confirm", key=f"confirm_db_{d['id']}")
            if right.button("Delete", key=f"del_db_{d['id']}", disabled=not confirm):
                lib.delete_dashboard(store, USER_ID, d["id"])
                if st.session_state.get("dashboard_id") == d["id"]:
                    st.session_state.pop("dashboard", None)
                    st.session_state.pop("dashboard_id", None)
                st.rerun()


# ============================================================
# PAGE: HISTORY
# ============================================================

def page_history():
    st.title("History")
    items = lib.list_history(store, USER_ID, limit=100)
    if not items:
        st.info("Nothing yet.")
        return
    labels = {
        "question": "Question", "dataset_upload": "Dataset uploaded",
        "dataset_open": "Dataset opened", "dashboard_save": "Dashboard saved",
        "dashboard_open": "Dashboard opened",
    }
    st.dataframe(
        pd.DataFrame([
            {"When": i["time"].replace("T", " "),
             "What": labels.get(i["kind"], i["kind"]),
             "Detail": i["text"],
             "OK": "✓" if i.get("ok", True) else "✗"}
            for i in items
        ]),
        width="stretch",
        hide_index=True,
    )


# ============================================================
# NEW DASHBOARD: STEP 1 - DATA
# ============================================================

def step_data():
    stepper("data")
    st.markdown("## Bring your data")
    show_flash()

    has_dataset = "data" in st.session_state
    if has_dataset:
        dataset_card(with_continue=True)
        st.write("")

    container = (
        st.expander("Use a different dataset") if has_dataset else st.container()
    )
    with container:
        saved = lib.list_datasets(store, USER_ID)
        tab_new, tab_saved = st.tabs(["Upload new files", "Use a saved dataset"])

        with tab_saved:
            if not saved:
                st.caption("You have no saved dataset yet.")
            else:
                choice = st.selectbox(
                    "Saved datasets",
                    options=[d["id"] for d in saved],
                    format_func=lambda i: next(d["name"] for d in saved if d["id"] == i),
                )
                if st.button("Open dataset", type="primary"):
                    try:
                        open_saved_dataset(choice)
                        go("create", "overview")
                    except Exception as exc:
                        st.error(f"Could not open this dataset: {exc}")

        with tab_new:
            uploaded_files = st.file_uploader(
                "Upload CSV or Excel files",
                type=["csv", "xlsx", "xls"],
                accept_multiple_files=True,
            )
            if uploaded_files:
                name = st.text_input(
                    "Dataset name",
                    value=suggest_dataset_name([f.name for f in uploaded_files]),
                )
                if st.button("Load and save dataset", type="primary"):
                    try:
                        with st.spinner("Loading and standardizing your files..."):
                            dataset = ingest(uploaded_files, source_type="upload")
                        with st.spinner("Profiling the dataset and building the schema..."):
                            profile_result = profile(dataset["data"])
                            schema = build_schema(profile_result, data=dataset["data"])
                        final_name = name.strip() or "Dataset"
                        auto_name = suggest_dataset_name([f.name for f in uploaded_files])
                        if final_name == auto_name:
                            # Untouched suggestion: refine it with the column names.
                            columns = [c for df in dataset["data"].values() for c in df.columns]
                            final_name = suggest_dataset_name(
                                [f.name for f in uploaded_files], columns
                            )
                        with st.spinner("Saving the dataset to your library..."):
                            dataset_id = lib.save_dataset(
                                store, USER_ID, final_name,
                                dataset["data"], profile_result, schema,
                            )
                        lib.add_history(store, USER_ID, "dataset_upload",
                                        final_name, dataset_id=dataset_id)
                        activate_dataset(
                            dataset_id, final_name, dataset["data"],
                            profile_result, schema, dataset["metadata"],
                        )
                        flash("success", "Dataset loaded, saved to your library and ready.")
                        go("create", "overview")
                    except Exception as exc:
                        clear_dataset_state()
                        st.error(f"Failed to prepare the dataset: {exc}")


# ============================================================
# NEW DASHBOARD: STEP 1b - DATASET OVERVIEW
# ============================================================

def step_overview():
    """Between opening a dataset and asking: show what the system understood about
    the data — tables, columns, types/roles and detected relationships — with
    downloads, and a button to go on to the question."""
    name = st.session_state.get("dataset_name", "Dataset")
    meta = st.session_state.get("metadata", {}) or {}
    profile_result = st.session_state.get("profile", {}) or {}
    schema = st.session_state.get("schema", "") or ""
    data = st.session_state.get("data", {}) or {}

    head_l, head_r = st.columns([4, 1.2])
    head_l.markdown(f"## {html.escape(name)}")
    if head_r.button("Change dataset", use_container_width=True):
        go("create", "data")
    show_flash()

    c1, c2, c3 = st.columns(3)
    c1.metric("Tables", meta.get("table_count", len(data)))
    c2.metric("Total rows", f"{int(meta.get('total_rows', 0)):,}")
    c3.metric("Total columns", meta.get("total_columns", 0))

    if st.button("Create a dashboard — ask a question", type="primary"):
        go("create", "ask")

    import json as _json
    summary = build_profile_summary(profile_result, data)
    d1, d2 = st.columns(2)
    d1.download_button("Download schema (.txt)", schema or "(no schema)",
                       file_name=f"{name}_schema.txt", mime="text/plain", use_container_width=True)
    d2.download_button("Download profile (.json)", _json.dumps(summary, indent=2, default=str),
                       file_name=f"{name}_profile.json", mime="application/json", use_container_width=True)

    st.markdown("#### Tables and columns")
    for table, info in profile_result.items():
        if not isinstance(info, dict) or "columns" not in info:
            continue
        df = data.get(table)
        rows = len(df) if df is not None else info.get("rows", "?")
        with st.expander(f"{table}  —  {len(info['columns'])} columns, {rows} rows"):
            st.dataframe(pd.DataFrame(column_rows(info)), hide_index=True, use_container_width=True)

    relationships = profile_result.get("relationships") or []
    if relationships:
        st.markdown("#### Detected relationships")
        st.dataframe(pd.DataFrame(relationships), hide_index=True, use_container_width=True)


# ============================================================
# NEW DASHBOARD: STEP 2 - QUESTION
# ============================================================

def suggest_questions(data, limit=3):
    """Example questions built from the loaded data itself, each using columns
    of ONE table, so they are answerable by construction (no generic prompts)."""
    def nice(name):
        return str(name).replace("_", " ").lower()

    out = []
    for table, df in data.items():
        if len(out) >= limit:
            break
        cols = [str(c) for c in df.columns]
        nums = [
            c for c in cols
            if pd.api.types.is_numeric_dtype(df[c])
            and not (c.lower() == "id" or c.lower().endswith("_id"))
            and df[c].nunique() > 10
        ]
        cats = [
            c for c in cols
            if (df[c].dtype == object or pd.api.types.is_string_dtype(df[c]))
            and 2 <= df[c].nunique() <= 30
            and not (c.lower() == "id" or c.lower().endswith("_id"))
        ]
        dates = [c for c in cols if pd.api.types.is_datetime64_any_dtype(df[c])]
        if nums and cats:
            out.append(f"Which {nice(cats[0])} has the highest {nice(nums[0])}?")
        elif nums and dates:
            out.append(f"How does {nice(nums[0])} evolve over time?")
        elif cats:
            out.append(f"What is the distribution of {nice(cats[0])}?")
    return out


def _use_example(text):
    st.session_state["question_text"] = text


def step_ask():
    stepper("ask")
    st.markdown("## What would you like to analyze?")

    top_left, top_right = st.columns([5, 1])
    top_left.markdown(
        f'<span class="chip">Dataset: {html.escape(st.session_state["dataset_name"])}</span>',
        unsafe_allow_html=True,
    )
    if top_right.button("Change dataset", use_container_width=True):
        go("create", "data")

    st.caption("Describe the topic in your own words. You can ask for several "
               "indicators at once.")
    st.text_area(
        "Your analytical question",
        key="question_text",
        placeholder=("Example: Analyze fuel consumption, fuel costs and their "
                     "relationship with trips."),
        height=120,
        label_visibility="collapsed",
    )

    examples = suggest_questions(st.session_state["data"])
    if examples:
        st.caption("Ideas based on your data")
        cols = st.columns(len(examples))
        for col, text in zip(cols, examples):
            col.button(text, on_click=_use_example, args=(text,),
                       use_container_width=True,
                       key=f"ex_{hashlib.md5(text.encode()).hexdigest()[:8]}")

    question = (st.session_state.get("question_text") or "").strip()
    if st.button("Generate dashboard", type="primary"):
        if not question:
            st.warning("Please enter an analysis question.")
            return
        db = st.session_state.get("db")
        schema = st.session_state.get("schema")
        if db is None or not schema:
            st.error("Please load a dataset first.")
            return
        try:
            reset_dashboard_filters()
            st.session_state.pop("dashboard_id", None)
            st.session_state.pop("dashboard_title", None)
            st.session_state["dashboard"] = generate_dashboard(question, schema, db)
            st.session_state.pop("dashboard_dirty", None)
            st.session_state.pop("undo_stack", None)
            st.session_state.pop("export_file", None)
            lib.add_history(store, USER_ID, "question", question,
                            dataset_id=st.session_state.get("dataset_id"))
        except Exception as exc:
            st.session_state.pop("dashboard", None)
            st.session_state.pop("filtered_dashboard_cache", None)
            lib.add_history(store, USER_ID, "question", question,
                            dataset_id=st.session_state.get("dataset_id"), ok=False)
            st.error(f"Dashboard generation failed: {exc}")
            return
        st.session_state["flow_step"] = "dashboard"
        st.rerun()


# ============================================================
# NEW DASHBOARD: STEP 3 - DASHBOARD
# ============================================================

def save_dashboard_now(dash, title, default_title, as_new):
    dashboard_id = st.session_state.get("dashboard_id")
    filters = st.session_state.get("applied_dashboard_filters", {})
    final_title = title.strip() or default_title
    new_id = lib.save_dashboard(
        store, USER_ID, st.session_state["dataset_id"], final_title,
        dashboard_to_spec(dash, filters),
        dashboard_id=None if as_new else dashboard_id,
    )
    st.session_state["dashboard_id"] = new_id
    st.session_state["dashboard_title"] = final_title
    st.session_state.pop("dashboard_dirty", None)
    lib.add_history(store, USER_ID, "dashboard_save", final_title,
                    dataset_id=st.session_state["dataset_id"], dashboard_id=new_id)
    flash("success", "Dashboard saved to your library.")


def render_export_menu(dash, title):
    """The Export popover: a report (HTML, prints to PDF) or an Excel workbook,
    of exactly what is on screen (current filters applied)."""
    fmt = st.radio("Format", ["Report (HTML, print to PDF)", "Excel workbook (.xlsx)"],
                   key="export_format", label_visibility="collapsed")
    include_sql = st.checkbox("Include the SQL behind each panel", value=True, key="export_sql",
                              help="Adds an appendix (report) or a sheet (Excel) with every validated query.")
    offline = False
    if fmt.startswith("Report"):
        offline = st.checkbox("Works offline (+3.5 MB)", value=False, key="export_offline",
                              help="Embeds the chart library so the file opens without internet.")
    if st.button("Prepare file", type="primary", use_container_width=True, key="export_prepare"):
        filters = st.session_state.get("applied_dashboard_filters", {})
        try:
            with st.spinner("Building the file..."):
                shown = refresh_dashboard_with_filters(dash, filters) if filters else dash
                insight = dashboard_insight(shown)
                dataset = st.session_state.get("dataset_name")
                safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title.strip()).strip("_") or "dashboard"
                if fmt.startswith("Report"):
                    data = dashboard_to_html(shown, insight, title, dataset=dataset, filters=filters,
                                             include_sql=include_sql, offline=offline)
                    st.session_state["export_file"] = {
                        "data": data, "name": f"{safe}.html", "mime": "text/html"}
                else:
                    data = dashboard_to_xlsx(shown, title, insight=insight, dataset=dataset,
                                             filters=filters, include_sql=include_sql)
                    st.session_state["export_file"] = {
                        "data": data, "name": f"{safe}.xlsx",
                        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
        except Exception as exc:
            st.session_state.pop("export_file", None)
            st.error(f"Couldn't build the file: {exc}")
    ready = st.session_state.get("export_file")
    if ready:
        st.download_button(f"Download {ready['name']}", ready["data"], file_name=ready["name"],
                           mime=ready["mime"], use_container_width=True, key="export_download")
        if ready["name"].endswith(".html"):
            st.caption("For a PDF: open the file, then Print and Save as PDF (A4 landscape).")
    st.caption("Exports what is on screen, with the current filters. "
               "To download one chart as an image, hover it and use the camera icon.")


def step_dashboard():
    dash = st.session_state["dashboard"]
    dashboard_id = st.session_state.get("dashboard_id")
    default_title = st.session_state.get("dashboard_title") or dash["plan"]["title"]

    back, change, name, save, copy_col, undo_col, export = st.columns(
        [1.1, 1.1, 2.4, 0.9, 1.0, 0.8, 1.0])
    if back.button("← New question", use_container_width=True):
        go("create", "ask")
    if change.button("Change dataset", use_container_width=True):
        go("create", "data")
    title = name.text_input(
        "Dashboard name", value=default_title, label_visibility="collapsed",
        key=f"save_title::{dashboard_id or 'new'}::{default_title}",
    )
    dirty = st.session_state.get("dashboard_dirty")
    if save.button("Save", type="primary" if dirty or not dashboard_id else "secondary",
                   use_container_width=True,
                   help="You have unsaved changes" if dirty else "Save to your library"):
        save_dashboard_now(dash, title, default_title, as_new=False)
        st.rerun()
    if dashboard_id and copy_col.button("Save as copy", use_container_width=True):
        save_dashboard_now(dash, title, default_title, as_new=True)
        st.rerun()
    if undo_col.button("Undo", icon=":material/undo:", use_container_width=True,
                       disabled=not _undo_available(dash), help="Take back the last change"):
        undo_last_change(dash)
        st.session_state["panel_toast"] = "Last change undone."
        st.rerun()
    with export.popover("Export", icon=":material/download:", use_container_width=True):
        render_export_menu(dash, title or default_title or "Dashboard")
    if dirty:
        st.caption("Unsaved changes. Click Save to keep them in your library.")

    show_flash()
    render_dashboard(dash)


def page_create():
    step = st.session_state.get("flow_step", "data")

    # Never show a step whose input is missing.
    if step == "dashboard" and "dashboard" not in st.session_state:
        step = "ask"
    if step in ("ask", "overview") and "schema" not in st.session_state:
        step = "data"
    st.session_state["flow_step"] = step

    {"data": step_data, "overview": step_overview,
     "ask": step_ask, "dashboard": step_dashboard}[step]()


{
    "home": page_home,
    "create": page_create,
    "datasets": page_datasets,
    "dashboards": page_dashboards,
    "history": page_history,
}[page]()
