
import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ============================================================
# COLUMN DETECTION
# ============================================================

DATE_KEYWORDS = (
    "date", "datetime", "timestamp", "time",
    "month_start", "year_month", "period"
)

ID_KEYWORDS = (
    "id", "_id", "identifier", "index",
    "number_id"
)

METRIC_KEYWORDS = {
    "fuel": ("gallon", "fuel", "quantity", "volume"),
    "consumption": ("gallon", "fuel", "consumption", "quantity"),
    "cost": ("cost", "amount", "price", "spend", "expense"),
    "spending": ("cost", "amount", "spend", "expense"),
    "revenue": ("revenue", "sales", "amount"),
    "trip": ("trip_count", "trip_total", "total_trips"),
    "count": ("count", "total", "number"),
    "average": ("average", "avg", "mean"),
    "delay": ("delay", "minutes_late", "late"),
    "distance": ("distance", "miles", "kilometers", "km"),
}


def _is_id_column(column):
    name = str(column).lower().strip()

    return (
        name == "id"
        or name.endswith("_id")
        or name.startswith("id_")
        or name.endswith("_identifier")
        or name in {"index", "row_number"}
    )


def _find_date_column(df):
    """Prefer date-like column names, then inspect datetime dtypes."""

    columns = list(df.columns)

    # Prefer explicit date/time names.
    for column in columns:
        name = str(column).lower()

        if any(keyword in name for keyword in DATE_KEYWORDS):
            return column

    # Already parsed datetime columns.
    for column in columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            return column

    # Conservative fallback: parse only columns that look date-like
    # from their values. Avoid interpreting arbitrary categories as dates.
    for column in columns:
        if pd.api.types.is_numeric_dtype(df[column]):
            continue

        values = df[column].dropna()

        if values.empty:
            continue

        sample = values.astype(str).head(30)

        looks_like_date = sample.str.contains(
            r"[-/]\d{1,2}[-/]\d{2,4}|"
            r"\d{4}-\d{2}|\d{4}-\d{2}-\d{2}|"
            r"\d{4}-\d{2}-\d{2}[T ]",
            regex=True
        ).mean()

        if looks_like_date >= 0.8:
            return column

    return None


def _find_category_column(df, date_column=None):
    """Find a useful dimension, preferring non-ID text columns."""

    candidates = [
        column for column in df.columns
        if column != date_column
        and not _is_id_column(column)
        and not pd.api.types.is_numeric_dtype(df[column])
    ]

    if candidates:
        return candidates[0]

    # IDs may be valid categories for a top-trips chart,
    # but should not be mistaken for measures.
    id_candidates = [
        column for column in df.columns
        if column != date_column and _is_id_column(column)
    ]

    return id_candidates[0] if id_candidates else None


def _find_metric_column(df, question=""):
    """Choose a numeric measure without defaulting blindly to column 1."""

    numeric_columns = [
        column for column in df.select_dtypes(include="number").columns
        if not _is_id_column(column)
    ]

    if not numeric_columns:
        return None

    question_lower = question.lower()

    # First, use the question to identify the intended measure.
    for keyword, preferred_names in METRIC_KEYWORDS.items():
        if keyword not in question_lower:
            continue

        for preferred in preferred_names:
            for column in numeric_columns:
                if preferred in str(column).lower():
                    return column

    # Next, prefer names that clearly indicate an aggregate.
    aggregate_words = (
        "total", "sum", "average", "avg", "mean",
        "count", "amount", "quantity", "gallon",
        "cost", "revenue", "consumption", "distance"
    )

    for column in numeric_columns:
        name = str(column).lower()

        if any(word in name for word in aggregate_words):
            return column

    # If the only measure is unambiguous, use it.
    if len(numeric_columns) == 1:
        return numeric_columns[0]

    # Ambiguous: don't silently claim that the first number is correct.
    return None


# ============================================================
# CHOOSE VISUAL
# ============================================================

def choose_visual(question, df=None):

    q = question.lower()

    # Explicit temporal intent takes precedence when the result
    # contains a date column.
    time_keywords = (
        "over time", "trend", "evolution", "monthly",
        "by month", "per month", "by year", "yearly",
        "daily", "weekly", "by date", "per year"
    )

    if any(word in q for word in time_keywords):
        if df is None or _find_date_column(df) is not None:
            return "line"

    # A single-value result can be a KPI.
    if df is not None and len(df) == 1:
        metric = _find_metric_column(df, question)

        if metric is not None:
            return "card"

    if any(word in q for word in (
        "top", "highest", "lowest", "most",
        "least", "best", "worst", "rank"
    )):
        return "bar"

    if any(word in q for word in (
        "share", "distribution", "proportion",
        "percentage", "breakdown"
    )):
        return "pie"

    return "table"


def _find_year_month_columns(df):
    """Detect separate numeric year and month columns."""

    year_col = next(
        (
            c for c in df.columns
            if str(c).lower().strip() in {"year", "calendar_year"}
        ),
        None
    )

    month_col = next(
        (
            c for c in df.columns
            if str(c).lower().strip() in {
                "month", "month_number", "calendar_month"
            }
        ),
        None
    )

    if year_col is not None and month_col is not None:
        return year_col, month_col

    return None, None


# ============================================================
# BUILD VISUAL METADATA
# ============================================================

def build_visual_metadata(df, visual_type, question=""):

    metadata = {
        "chart": visual_type,
        "x": None,
        "y": None,
        "title": question
    }

    if df is None or df.empty:
        return metadata

    date_column = _find_date_column(df)
    metric_column = _find_metric_column(df, question)

    if visual_type == "card":
        metadata["y"] = metric_column
        return metadata

    
    if visual_type == "line":

        year_col, month_col = _find_year_month_columns(df)

        if date_column is not None:
            metadata["x"] = date_column

        elif year_col is not None and month_col is not None:
            # render_visual will construct a real date from these columns.
            metadata["x"] = "__generated_month_date__"
            metadata["year_col"] = year_col
            metadata["month_col"] = month_col

        else:
            metadata["chart"] = "table"
            return metadata

        metadata["y"] = metric_column

        if metric_column is None:
            metadata["chart"] = "table"

        return metadata


        # If no date is available, don't invent a time axis.
        if date_column is None:
            metadata["chart"] = "table"
            return metadata

        metadata["y"] = metric_column

        if metric_column is None:
            metadata["chart"] = "table"

        return metadata

    if visual_type == "bar":
        category = _find_category_column(df, date_column)

        # If this is a ranking by a trip ID, allow the ID as a
        # category, but never as the numeric measure.
        if category is None:
            category = _find_category_column(df)

        metadata["x"] = category
        metadata["y"] = metric_column

        if category is None or metric_column is None:
            metadata["chart"] = "table"

        return metadata

    if visual_type == "pie":
        metadata["x"] = _find_category_column(df, date_column)
        metadata["y"] = metric_column

        if metadata["x"] is None or metric_column is None:
            metadata["chart"] = "table"

        return metadata

    return metadata


# ============================================================
# RENDER VISUAL
# ============================================================

def render_visual(df, metadata):

    if df is None or df.empty:
        return None

    chart_type = metadata.get("chart")
    x = metadata.get("x")
    y = metadata.get("y")
    title = metadata.get("title", "")

    if chart_type == "card":
        if y not in df.columns:
            return None

        value = df[y].iloc[0]

        if pd.isna(value):
            return None

        return go.Figure(
            go.Indicator(
                mode="number",
                value=float(value),
                title={"text": title}
            )
        )

    if chart_type == "bar":
        if x not in df.columns or y not in df.columns:
            return None

        fig = px.bar(df, x=x, y=y, title=title)
        return fig

   
    if chart_type == "line":

        plot_df = df.copy()
        x = metadata.get("x")
        y = metadata.get("y")

        if y not in plot_df.columns:
            return None

        # Handle SQL results containing separate year and month columns.
        if x == "__generated_month_date__":

            year_col = metadata["year_col"]
            month_col = metadata["month_col"]

            years = pd.to_numeric(
                plot_df[year_col], errors="coerce"
            )

            months = pd.to_numeric(
                plot_df[month_col], errors="coerce"
            )

            plot_df[x] = pd.to_datetime(
                {
                    "year": years,
                    "month": months,
                    "day": 1
                },
                errors="coerce"
            )

        elif x not in plot_df.columns:
            return None

        else:
            plot_df[x] = pd.to_datetime(
                plot_df[x], errors="coerce"
            )

        # Invalid dates must not be plotted as misleading categories.
        plot_df = plot_df.dropna(subset=[x])

        if plot_df.empty:
            return None

        plot_df = plot_df.sort_values(x)

        fig = px.line(
            plot_df,
            x=x,
            y=y,
            title=title,
            markers=True
        )

        fig.update_xaxes(
            type="date",
            tickformat="%b %Y",
            tickangle=-45,
            title_text="Month"
        )

        return fig


    if chart_type == "pie":
        if x not in df.columns or y not in df.columns:
            return None

        return px.pie(
            df,
            names=x,
            values=y,
            title=title
        )

    # Tables remain the application's responsibility.
    return None
