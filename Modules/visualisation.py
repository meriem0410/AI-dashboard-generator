
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

METRIC_KEYWORDS = {
    "fuel": ("gallon", "fuel", "quantity", "volume"),
    "consumption": ("gallon", "fuel", "consumption", "quantity"),
    "cost": ("cost", "amount", "price", "spend", "expense"),
    "spending": ("cost", "amount", "spend", "expense"),
    "revenue": ("revenue", "sales", "amount"),
    "trip": ("trip_count", "trip_total", "total_trips"),
    "count": ("count", "total", "number"),
    "average": ("average", "avg", "mean"),
    "satisfaction": ("satisfaction", "rating", "score"),
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
    """Find the most reliable date column."""

    # Prefer actual datetime columns.
    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            return column

    # Then inspect columns whose names indicate dates.
    for column in df.columns:
        name = str(column).lower()

        if not any(keyword in name for keyword in DATE_KEYWORDS):
            continue

        values = df[column].dropna()

        if values.empty:
            continue

        if pd.api.types.is_datetime64_any_dtype(values):
            return column

        sample = values.astype(str).head(100)
        parsed = pd.to_datetime(sample, errors="coerce")

        if parsed.notna().mean() >= 0.8:
            return column

    # Conservative fallback based on sampled values.
    for column in df.columns:
        if pd.api.types.is_numeric_dtype(df[column]):
            continue

        values = df[column].dropna()

        if values.empty:
            continue

        sample = values.astype(str).head(100)

        looks_like_date = sample.str.contains(
            r"\d{4}-\d{2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
            regex=True
        ).mean()

        if looks_like_date >= 0.8:
            return column

    return None


def _is_text_column(df, column):
    return not pd.api.types.is_numeric_dtype(df[column]) and not pd.api.types.is_bool_dtype(df[column])


def _find_category_column(df, date_column=None, metric_column=None):
    """Find a category suitable for the chart's X-axis.

    Order: descriptive text (city, type) -> text identifiers (TRK-001) ->
    numeric dimensions (year, unit number) -> numeric ids. A text label always
    beats a number, so a result with truck_id and unit_number is plotted by
    truck_id, not by a continuous 2000..8000 axis."""
    others = [c for c in df.columns if c != date_column and c != metric_column]
    groups = (
        [c for c in others if not _is_id_column(c) and _is_text_column(df, c)],
        [c for c in others if _is_id_column(c) and _is_text_column(df, c)],
        [c for c in others if not _is_id_column(c) and not _is_text_column(df, c)],
        [c for c in others if _is_id_column(c) and not _is_text_column(df, c)],
    )
    for group in groups:
        if group:
            return group[0]
    return None


def _find_metric_column(df, question=""):
    """Identify the numeric measure that best matches the question."""

    numeric_columns = [
        c for c in df.select_dtypes(include="number").columns
        if not _is_id_column(c)
    ]

    if not numeric_columns:
        return None

    question_lower = question.lower()

    # Match the requested business metric first.
    for keyword, preferred_names in METRIC_KEYWORDS.items():
        if keyword not in question_lower:
            continue

        for preferred in preferred_names:
            for column in numeric_columns:
                if preferred in str(column).lower():
                    return column

    # Prefer clearly aggregated measures.
    aggregate_words = (
        "total", "sum", "average", "avg", "mean",
        "count", "amount", "quantity", "gallon",
        "cost", "revenue", "consumption", "distance",
        "satisfaction", "score", "rating"
    )

    for column in numeric_columns:
        name = str(column).lower()

        if any(word in name for word in aggregate_words):
            return column

    # Only use the numeric column if it is unambiguous.
    if len(numeric_columns) == 1:
        return numeric_columns[0]

    return None


def _find_year_month_columns(df):
    """Detect separate year and month columns."""

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

    return year_col, month_col


# ============================================================
# CHOOSE VISUAL
# ============================================================

def choose_visual(question, df=None):

    q = question.lower()

    time_keywords = (
        "over time", "trend", "evolution", "monthly",
        "by month", "per month", "by year", "yearly",
        "daily", "weekly", "by date", "per year"
    )

    if any(word in q for word in time_keywords):
        if df is None or _find_date_column(df) is not None:
            return "line"

    if df is not None and len(df) == 1:
        if _find_metric_column(df, question) is not None:
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


# ============================================================
# BUILD VISUAL METADATA
# ============================================================

def build_visual_metadata(df, visual_type, question="", title=None):

    # Support both planner naming and existing pipeline naming.
    if visual_type == "kpi":
        visual_type = "card"

    metadata = {
    "chart": visual_type,
    "x": None,
    "y": None,
    "color": None,
    "title": title or question,
    "sort_order": None,
    "fallback_reason": None,
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
            metadata["x"] = "__generated_month_date__"
            metadata["year_col"] = year_col
            metadata["month_col"] = month_col

        else:
            metadata["chart"] = "table"
            metadata["fallback_reason"] = (
                "A valid date column or separate year/month columns "
                "could not be identified."
            )
            return metadata

        metadata["y"] = metric_column

    if metric_column is None:
        metadata["chart"] = "table"
        metadata["fallback_reason"] = (
            "No suitable numeric metric was identified for the line chart."
        )

    if visual_type == "bar":

        category = _find_category_column(
            df, date_column, metric_column
        )

        metadata["x"] = category
        metadata["y"] = metric_column

        # Preserve the intended ranking direction.
        if any(word in question.lower() for word in (
            "lowest", "least", "worst"
        )):
            metadata["sort_order"] = "ascending"

        elif any(word in question.lower() for word in (
            "top", "highest", "most", "best", "rank"
        )):
            metadata["sort_order"] = "descending"

        if category is None or metric_column is None:
            metadata["chart"] = "table"

        if category is None:
            metadata["fallback_reason"] = (
                "No suitable category column was identified for the bar chart."
            )
        else:
            metadata["fallback_reason"] = (
                "No suitable numeric metric was identified for the bar chart."
            )

        return metadata

    if visual_type == "pie":

        metadata["x"] = _find_category_column(
            df, date_column, metric_column
        )
        metadata["y"] = metric_column

        if metadata["x"] is None or metric_column is None:
            metadata["chart"] = "table"

        if metadata["x"] is None:
            metadata["fallback_reason"] = (
                "No suitable category column was identified for the pie chart."
            )
        else:
            metadata["fallback_reason"] = (
                "No suitable numeric metric was identified for the pie chart."
            )
        return metadata

    return metadata


# ============================================================
# SHARED FIGURE FORMATTING
# ============================================================


def _format_figure(fig, title, height=420):

    fig.update_layout(
        template="plotly_white",
        title={
            "text": title,
            "x": 0.02,
            "xanchor": "left"
        },
        autosize=True,
        height=height,
        margin=dict(l=65, r=30, t=75, b=85),

        hoverlabel=dict(
            bgcolor="white",
            font_size=13,
            font_family="Arial"
        ),

        font=dict(
            size=12,
            family="Arial"
        ),

        hovermode="closest",
    )

    return fig




def _label(column):
    """Convert database column names into readable axis labels."""
    return str(column).replace("_", " ").strip().title()


def _metric_unit(column):
    """
    Identify units only when they are explicitly indicated
    by the metric column name.
    """
    name = str(column).lower()

    if any(word in name for word in ("usd", "dollars", "dollar")):
        return "USD"

    if "gallon" in name:
        return "Gallons"

    if "kilometer" in name or re.search(r"(^|_)km($|_)", name):
        return "Kilometres"

    if "mile" in name:
        return "Miles"

    if "liter" in name or "litre" in name:
        return "Litres"

    if "minute" in name:
        return "Minutes"

    if "hour" in name:
        return "Hours"

    if "percent" in name or "percentage" in name:
        return "%"

    return None


def _axis_label(column):
    """Return a readable metric label, including a known unit."""
    label = _label(column)
    unit = _metric_unit(column)

    if unit:
        return f"{label} ({unit})"

    return label


def format_metric_value(value, column=None):
    """
    Format KPI values without unnecessary decimal places. Counts under a
    million keep every digit with a thousands separator (85,410).
    """
    if pd.isna(value):
        return "N/A"

    value = float(value)
    name = str(column).lower() if column is not None else ""

    # Identify metrics that represent counts.
    is_count = (
        "count" in name
        or "number_of" in name
        or name.startswith("num_")
    )

    # Counts should be displayed as integers.
    if is_count and value.is_integer() and abs(value) < 1_000_000:
        formatted = f"{value:,.0f}"
    else:
        absolute = abs(value)

        if absolute >= 1_000_000:
            formatted = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
        elif absolute >= 1_000:
            formatted = f"{value / 1_000:.2f}".rstrip("0").rstrip(".") + "K"
        else:
            formatted = f"{value:.2f}".rstrip("0").rstrip(".")

    unit = _metric_unit(column) if column is not None else None

    if unit == "USD":
        return f"${formatted}"

    if unit and unit != "%":
        return f"{formatted} {unit}"

    if unit == "%":
        return f"{formatted}%"

    return formatted


def _hover_value_label(column):
    """Return a unit suffix for hover labels."""
    unit = _metric_unit(column)

    if unit == "USD":
        return " USD"

    if unit:
        return f" {unit}"

    return ""




# ============================================================
# CHART HELPERS
# ============================================================

MAX_BARS = 25            # more than this is unreadable; keep the top N
HORIZONTAL_FROM = 15     # this many categories or more -> horizontal bars
MAX_SLICES = 7           # a pie keeps its 7 biggest slices, the rest is "Other"
HISTOGRAM_FROM = 30      # a numeric x with this many distinct values is a measure

_CONTINUOUS_WORDS = (
    "distance", "mile", "km", "kilomet", "amount", "price", "cost", "duration",
    "hour", "minute", "age", "weight", "score", "rating", "mpg", "speed",
    "revenue", "fuel", "gallon", "load", "salary", "income",
)

_COUNT_WORDS = ("count", "number_of", "num_", "trips", "total_trips", "n_")


def _is_count_column(column):
    name = str(column).lower()
    return any(w in name for w in _COUNT_WORDS) or name == "n"


def _readable_labels(df, x, y):
    """Labels for x that are unique, so bars never silently stack.

    A route result has origin_city repeated (Charlotte -> Portland, Charlotte ->
    Denver...). Plotted on origin_city alone the bars of one city stack into one
    tall bar with a wrong total. Here the next text column is joined in
    ("Charlotte – Portland"); failing that an id, failing that a row number.
    Returns the label Series (or the original column when already unique)."""
    labels = df[x].astype(str)
    if not labels.duplicated().any():
        return labels

    text_cols = [c for c in df.columns
                 if c not in (x, y) and _is_text_column(df, c) and not _is_id_column(c)]
    id_cols = [c for c in df.columns if c not in (x, y) and _is_id_column(c)]
    for extra in text_cols + id_cols:
        candidate = labels + " – " + df[extra].astype(str)
        labels = candidate
        if not labels.duplicated().any():
            return labels

    counter = labels.groupby(labels).cumcount() + 1
    dup = labels.duplicated(keep=False)
    return labels.where(~dup, labels + " #" + counter.astype(str))


def _looks_continuous(df, x, title=""):
    """A numeric x with many distinct values is a measure, not a category."""
    if x not in df.columns or not pd.api.types.is_numeric_dtype(df[x]):
        return False
    if _is_id_column(x):
        return False
    if df[x].nunique(dropna=True) < HISTOGRAM_FROM:
        return False
    name = str(x).lower()
    text = str(title).lower()
    return (any(w in name for w in _CONTINUOUS_WORDS)
            or "distribution" in text or "histogram" in text
            or not pd.api.types.is_integer_dtype(df[x]))


def _render_histogram(df, metadata):
    x, y = metadata.get("x"), metadata.get("y")
    title = metadata.get("title", "")
    plot_df = df.dropna(subset=[x])
    if plot_df.empty:
        return None
    if y in plot_df.columns and y != x:
        histfunc = "sum" if _is_count_column(y) else "avg"
        fig = px.histogram(plot_df, x=x, y=y, histfunc=histfunc, nbins=30)
        y_title = _axis_label(y) if histfunc == "sum" else f"Average {_axis_label(y)}"
    else:
        fig = px.histogram(plot_df, x=x, nbins=30)
        y_title = "Count"
    fig.update_traces(marker_line_width=0.5, marker_line_color="white")
    fig.update_xaxes(title_text=_axis_label(x), automargin=True)
    fig.update_yaxes(title_text=y_title, tickformat="~s", rangemode="tozero")
    fig.update_layout(bargap=0.05, showlegend=False)
    return _format_figure(fig, title)


def _apply_sort(plot_df, metadata, y):
    """Sort by a user-chosen column (item["sort"]) or by the metric."""
    sort = metadata.get("sort") or {}
    by = sort.get("by")
    if by in plot_df.columns:
        return plot_df.sort_values(by, ascending=bool(sort.get("ascending")),
                                   na_position="last"), True
    if sort and "ascending" in sort:
        return plot_df.sort_values(y, ascending=bool(sort["ascending"]),
                                   na_position="last"), True
    order = metadata.get("sort_order")
    if order:
        return plot_df.sort_values(y, ascending=(order == "ascending"),
                                   na_position="last"), True
    return plot_df, False


def _render_bar(df, metadata):
    x, y = metadata.get("x"), metadata.get("y")
    color = metadata.get("color")
    title = metadata.get("title", "")

    if x not in df.columns or y not in df.columns:
        return None

    style = metadata.get("style")
    if style == "histogram" or (style is None and _looks_continuous(df, x, title)):
        return _render_histogram(df, metadata)

    plot_df = df.dropna(subset=[y]).copy()
    if plot_df.empty:
        return None
    plot_df["__label__"] = _readable_labels(plot_df, x, y).values
    plot_df["__raw__"] = plot_df[x].astype(str).values

    plot_df, sorted_ = _apply_sort(plot_df, metadata, y)

    total = len(plot_df)
    horizontal = style == "horizontal" or (style != "vertical" and total >= HORIZONTAL_FROM)
    note = ""
    if total > MAX_BARS:
        if not sorted_:
            plot_df = plot_df.sort_values(y, ascending=False, na_position="last")
        plot_df = plot_df.head(MAX_BARS)
        note = f" (top {MAX_BARS} of {total})"
        metadata["note"] = f"Showing the top {MAX_BARS} of {total}."
    shown_title = f"{title}{note}" if title else note.strip()
    combined = not plot_df["__label__"].equals(plot_df["__raw__"])
    x_title = _label(x)
    if combined:
        parts = [c for c in df.columns if c != y and _is_text_column(df, c) and not _is_id_column(c)]
        x_title = " – ".join(_label(c) for c in parts[:2]) if len(parts) >= 2 else _label(x)

    metric_label = _axis_label(y)
    hover_unit = _hover_value_label(y)
    use_color = color if color in plot_df.columns else None

    if horizontal:
        fig = px.bar(plot_df, x=y, y="__label__", orientation="h", color=use_color,
                     custom_data=["__raw__"],
                     labels={y: metric_label, "__label__": x_title})
        fig.update_traces(hovertemplate=(f"<b>%{{y}}</b><br>{metric_label}: %{{x:,.2~f}}"
                                         f"{hover_unit}<extra></extra>"))
        fig.update_yaxes(type="category", title_text=x_title, automargin=True,
                         autorange="reversed",
                         categoryorder="array", categoryarray=list(plot_df["__label__"]))
        fig.update_xaxes(title_text=metric_label, tickformat="~s", rangemode="tozero")
        height = max(420, 24 * len(plot_df) + 150)
    else:
        fig = px.bar(plot_df, x="__label__", y=y, color=use_color,
                     custom_data=["__raw__"],
                     labels={y: metric_label, "__label__": x_title})
        fig.update_traces(hovertemplate=(f"<b>%{{x}}</b><br>{metric_label}: %{{y:,.2~f}}"
                                         f"{hover_unit}<extra></extra>"))
        fig.update_xaxes(type="category", title_text=x_title, tickangle=-35,
                         automargin=True,
                         categoryorder="array", categoryarray=list(plot_df["__label__"]))
        fig.update_yaxes(title_text=metric_label, tickformat="~s", rangemode="tozero")
        height = 420

    fig.update_layout(showlegend=bool(use_color),
                      legend_title_text=_label(use_color) if use_color else None)
    return _format_figure(fig, shown_title, height=height)


def _render_pie(df, metadata):
    x, y = metadata.get("x"), metadata.get("y")
    title = metadata.get("title", "")
    if x not in df.columns or y not in df.columns:
        return None

    plot_df = df.dropna(subset=[x, y]).copy()
    plot_df = plot_df[plot_df[y] > 0] if pd.api.types.is_numeric_dtype(plot_df[y]) else plot_df
    if plot_df.empty:
        return None
    plot_df["__label__"] = _readable_labels(plot_df, x, y).values
    plot_df = plot_df.sort_values(y, ascending=False)

    # Many thin slices are unreadable: keep the biggest, fold the rest.
    if len(plot_df) > MAX_SLICES + 1:
        head = plot_df.head(MAX_SLICES)[["__label__", y]]
        other = pd.DataFrame({"__label__": ["Other"], y: [plot_df[y].iloc[MAX_SLICES:].sum()]})
        plot_df = pd.concat([head, other], ignore_index=True)

    metric_label = _axis_label(y)
    hover_unit = _hover_value_label(y)
    fig = px.pie(plot_df, names="__label__", values=y, hole=0.35,
                 labels={"__label__": _label(x), y: metric_label})
    fig.update_traces(
        textposition="inside", textinfo="percent", sort=False,
        hovertemplate=("<b>%{label}</b>"
                       f"<br>{metric_label}: %{{value:,.2~f}}{hover_unit}"
                       "<br>Share: %{percent}<extra></extra>"))
    fig.update_layout(showlegend=True, legend_title_text=_label(x))
    return _format_figure(fig, title)


def pie_labels(df, metadata):
    """The slice labels a pie will show, in order (used by the app to offer a
    click-to-filter control under the pie). Empty when the pie can't render."""
    x, y = metadata.get("x"), metadata.get("y")
    if df is None or x not in getattr(df, "columns", []) or y not in df.columns:
        return []
    plot_df = df.dropna(subset=[x, y]).sort_values(y, ascending=False)
    return [str(v) for v in plot_df[x].head(MAX_SLICES).tolist()]


def _render_treemap(df, metadata):
    x, y = metadata.get("x"), metadata.get("y")
    title = metadata.get("title", "")
    if x not in df.columns or y not in df.columns:
        return None
    plot_df = df.dropna(subset=[x, y]).copy()
    plot_df = plot_df[plot_df[y] > 0]
    if plot_df.empty:
        return None
    plot_df["__label__"] = _readable_labels(plot_df, x, y).values
    metric_label = _axis_label(y)
    fig = px.treemap(plot_df, path=["__label__"], values=y)
    fig.update_traces(
        root_color="rgba(0,0,0,0)", textinfo="label+percent root",
        hovertemplate=(f"<b>%{{label}}</b><br>{metric_label}: %{{value:,.2~f}}"
                       f"{_hover_value_label(y)}<extra></extra>"))
    return _format_figure(fig, title, height=460)


def _render_scatter(df, metadata):
    """Two measures against each other (e.g. distance vs fuel). Needs a second
    numeric column besides the metric; otherwise None (caller falls back)."""
    y = metadata.get("y")
    title = metadata.get("title", "")
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
               and not _is_id_column(c) and c != y]
    if y not in df.columns or not numeric:
        return None
    x = numeric[0]
    label_col = metadata.get("x") if metadata.get("x") in df.columns else None
    plot_df = df.dropna(subset=[x, y])
    if plot_df.empty:
        return None
    fig = px.scatter(plot_df, x=x, y=y, hover_name=label_col,
                     labels={x: _axis_label(x), y: _axis_label(y)})
    fig.update_traces(marker=dict(size=9, opacity=0.75))
    fig.update_xaxes(title_text=_axis_label(x), tickformat="~s")
    fig.update_yaxes(title_text=_axis_label(y), tickformat="~s")
    return _format_figure(fig, title)


# ============================================================
# RENDER VISUAL
# ============================================================

def render_visual(df, metadata):

    if df is None or df.empty:
        return None

    chart_type = metadata.get("chart")
    x = metadata.get("x")
    y = metadata.get("y")
    color = metadata.get("color")
    title = metadata.get("title", "")

    # --------------------------------------------------------
    # KPI / CARD
    # --------------------------------------------------------

    if chart_type == "card":

        if y not in df.columns:
            return None

        value = df[y].iloc[0]

        if pd.isna(value):
            return None

        fig = go.Figure(
            go.Indicator(
                mode="number",
                value=float(value),
                title={"text": _label(y)},
                number={"valueformat": ",.2f"}
            )
        )

        return _format_figure(fig, title)

    # --------------------------------------------------------
    # BAR
    # --------------------------------------------------------

    
    # --------------------------------------------------------
    # BAR
    # --------------------------------------------------------

    style = metadata.get("style")

    if chart_type in ("bar", "pie") and style == "treemap":
        return _render_treemap(df, metadata)

    if chart_type in ("bar", "pie") and style == "scatter":
        fig = _render_scatter(df, metadata)
        if fig is not None:
            return fig

    if chart_type == "bar":
        return _render_bar(df, metadata)

    # --------------------------------------------------------
    # LINE
    # --------------------------------------------------------

    
    # --------------------------------------------------------
    # LINE
    # --------------------------------------------------------

    if chart_type == "line":

        plot_df = df.copy()

        if y not in plot_df.columns:
            return None

        # Construct a proper date from separate year/month columns.
        if x == "__generated_month_date__":

            year_col = metadata.get("year_col")
            month_col = metadata.get("month_col")

            if year_col not in plot_df.columns or month_col not in plot_df.columns:
                return None

            years = pd.to_numeric(
                plot_df[year_col], errors="coerce"
            )

            months = pd.to_numeric(
                plot_df[month_col], errors="coerce"
            )

            valid_months = months.between(1, 12)

            plot_df[x] = pd.NaT

            plot_df.loc[valid_months, x] = pd.to_datetime(
                {
                    "year": years[valid_months],
                    "month": months[valid_months],
                    "day": 1
                },
                errors="coerce"
            )

        elif x in plot_df.columns:

            plot_df[x] = pd.to_datetime(
                plot_df[x], errors="coerce"
            )

        else:
            return None

        plot_df = plot_df.dropna(subset=[x, y])

        if plot_df.empty:
            return None

        plot_df = plot_df.sort_values(x)

        metric_label = _axis_label(y)
        hover_unit = _hover_value_label(y)

        fig = px.line(
            plot_df,
            x=x,
            y=y,
            color=color if color in plot_df.columns else None,
            title=title,
            markers=True,
            labels={
                x: _label(x),
                y: metric_label,
                color: _label(color) if color else ""
            }
        )

        if metadata.get("style") == "area":
            fig.update_traces(fill="tozeroy")

        fig.update_traces(
            line=dict(width=2.5),
            marker=dict(size=7),
            hovertemplate=(
                "<b>%{x|%B %Y}</b>"
                f"<br>{metric_label}: %{{y:~.2f}}"
                f"{hover_unit}"
                "<extra></extra>"
            )
        )

        fig.update_xaxes(
            type="date",
            tickformat="%b %Y",
            tickangle=-35,
            title_text=_label(x),
            automargin=True
        )

        fig.update_yaxes(
            title_text=metric_label,
            tickformat="~s",
            rangemode="tozero"
        )

        fig.update_layout(
            hovermode="x unified",
            showlegend=bool(color),
            legend_title_text=_label(color) if color else None
        )

        return _format_figure(fig, title)

    # --------------------------------------------------------
    # PIE
    # --------------------------------------------------------

    
    # --------------------------------------------------------
    # PIE
    # --------------------------------------------------------

    if chart_type == "pie":
        return _render_pie(df, metadata)

    return None
