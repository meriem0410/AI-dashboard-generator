
"""
Modules/dashboard_filters.py

Discovers generic dashboard-level filters.

Date filtering:
    One global date range is mapped to one primary operational
    date column per relevant fact/detail table.

Categorical filtering:
    Low-cardinality descriptive columns can be exposed as
    categorical controls.

The profile relationship metadata helps identify fact/detail tables.
Lifecycle dates in dimension tables are excluded.
"""

import re
import pandas as pd


# ============================================================
# COLUMN CLASSIFICATION
# ============================================================

CATEGORY_HINTS = {
    "status",
    "type",
    "category",
    "mode",
    "region",
    "country",
    "state",
    "fuel",
    "priority",
    "segment",
    "department",
    "class",
    "channel",
    "kind",
}

EXCLUDED_DATE_HINTS = (
    "birth",
    "hire",
    "termination",
    "acquisition",
    "contract",
    "expiration",
    "expiry",
    "renewal",
    "effective",
    "license",
    "certification",
)

MAX_CATEGORY_VALUES = 40


# Higher scores represent preferred operational dates.
DATE_PRIORITIES = {
    "actual_datetime": 130,
    "actual_date": 125,
    "purchase_date": 120,
    "dispatch_date": 120,
    "transaction_date": 120,
    "event_datetime": 118,
    "event_date": 118,
    "incident_date": 115,
    "maintenance_date": 115,
    "delivery_date": 110,
    "pickup_date": 105,
    "load_date": 100,
    "scheduled_datetime": 95,
    "scheduled_date": 90,
    "order_date": 90,
    "service_date": 90,
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def _python_value(value):

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass

    return value


def _is_identifier(column):

    name = str(column).strip().lower()

    return (
        name == "id"
        or name.endswith("_id")
        or name.startswith("id_")
        or name.endswith("_identifier")
        or name in {"index", "row_number"}
    )


def _parse_dates(series):
    """Parse values into timezone-naive timestamps.

    pd.to_datetime(..., utc=True) returns a tz-NAIVE array for input that cannot
    be read as dates (e.g. booleans, which all coerce to NaT), and tz_convert then
    raises. So only strip the timezone when there is one."""

    parsed = pd.to_datetime(
        series,
        errors="coerce",
        utc=True
    )

    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_convert(None)
    return parsed


# ============================================================
# DATE FIELD DETECTION
# ============================================================

def _date_score(column, is_fact_table, is_datetime):

    name = str(column).lower().strip()

    # Exclude dates that describe the lifecycle of a dimension.
    if any(
        hint in name
        for hint in EXCLUDED_DATE_HINTS
    ):
        return -1

    if name in DATE_PRIORITIES:
        return DATE_PRIORITIES[name]

    # General event-like datetime fields.
    if name.endswith("_datetime") or name.endswith("_timestamp"):
        return 85 if is_fact_table else 60

    if name.endswith("_date"):
        return 75 if is_fact_table else 55

    if name in {"date", "datetime", "timestamp"}:
        return 65 if is_fact_table else 45

    # A datetime field in a known fact table can be used as
    # a fallback when its name is not descriptive.
    if is_datetime and is_fact_table:
        return 40

    return -1


def _discover_date_column(df, table_name, is_fact_table):
    """
    Select the primary operational date column for one table.

    Only one date column is selected per table. For example,
    actual_datetime takes priority over scheduled_datetime.
    """

    candidates = []

    for column in df.columns:

        series = df[column]

        is_datetime = (
            pd.api.types.is_datetime64_any_dtype(series)
        )

        score = _date_score(
            column,
            is_fact_table,
            is_datetime
        )

        if score < 0:
            continue

        # A column must either have datetime dtype or a
        # date/time-related name.
        name = str(column).lower()

        has_date_name = (
            "date" in name
            or "time" in name
            or "timestamp" in name
        )

        if not is_datetime and not has_date_name:
            continue

        # Verify that the values really represent dates.
        sample = series.dropna().head(100)

        if sample.empty:
            continue

        parsed_sample = _parse_dates(sample)

        if parsed_sample.notna().mean() < 0.80:
            continue

        # Parse the full column to calculate its coverage.
        parsed = _parse_dates(series).dropna()

        if parsed.empty:
            continue

        candidates.append({
            "table": table_name,
            "column": column,
            "score": score,
            "min_date": parsed.min().date().isoformat(),
            "max_date": parsed.max().date().isoformat(),
            "valid_dates": int(len(parsed))
        })

    if not candidates:
        return None

    # Select only the highest-priority operational date.
    candidates.sort(
        key=lambda item: (
            item["score"],
            item["valid_dates"]
        ),
        reverse=True
    )

    selected = candidates[0]

    return {
        "table": selected["table"],
        "column": selected["column"],
        "min_date": selected["min_date"],
        "max_date": selected["max_date"]
    }


# ============================================================
# FILTER CATALOG
# ============================================================

def discover_filter_catalog(data, profile_info=None):
    """
    Discover a virtual global date dimension and categorical filters.

    profile_info:
        Output of profile_data(), including its relationships list.

    Returns:

    {
        "date_dimension": {
            "min_date": "...",
            "max_date": "...",
            "mappings": [...]
        },
        "category_fields": [...]
    }
    """

    profile_info = profile_info or {}

    # --------------------------------------------------------
    # IDENTIFY FACT/DETAIL TABLES
    # --------------------------------------------------------

    relationships = profile_info.get(
        "relationships", []
    )

    fact_tables = {
        relation["from_table"]
        for relation in relationships
        if relation.get("from_table")
    }

    # --------------------------------------------------------
    # BUILD PRIMARY DATE MAPPINGS
    # --------------------------------------------------------

    mappings = []

    for table_name, df in data.items():

        if df is None or df.empty:
            continue

        selected = _discover_date_column(
            df,
            table_name,
            table_name in fact_tables
        )

        if selected is not None:
            mappings.append(selected)

    mappings.sort(
        key=lambda item: item["table"]
    )

    date_dimension = None

    if mappings:

        global_min = min(
            item["min_date"]
            for item in mappings
        )

        global_max = max(
            item["max_date"]
            for item in mappings
        )

        date_dimension = {
            "label": "Global operational date",
            "min_date": global_min,
            "max_date": global_max,
            "mappings": mappings
        }

    # --------------------------------------------------------
    # DISCOVER CATEGORICAL FILTERS
    # --------------------------------------------------------

    category_fields = []

    for table_name, df in data.items():

        if df is None or df.empty:
            continue

        for column in df.columns:

            if _is_identifier(column):
                continue

            series = df[column]

            is_text = (
                pd.api.types.is_object_dtype(series)
                or pd.api.types.is_string_dtype(series)
                or isinstance(
                    series.dtype,
                    pd.CategoricalDtype
                )
            )

            is_boolean = pd.api.types.is_bool_dtype(series)

            if not (is_text or is_boolean):
                continue

            name = str(column).lower()

            tokens = set(
                re.split(r"[_\W]+", name)
            )

            has_category_hint = bool(
                tokens.intersection(CATEGORY_HINTS)
            )

            if not (has_category_hint or is_boolean):
                continue

            values = [
                _python_value(value)
                for value in series.dropna().unique().tolist()
            ]

            if not (
                2 <= len(values) <= MAX_CATEGORY_VALUES
            ):
                continue

            values.sort(
                key=lambda value: str(value).casefold()
            )

            category_fields.append({
                "id": f"{table_name}::{column}",
                "table": table_name,
                "column": column,
                "values": values
            })

    return {
        "date_dimension": date_dimension,
        "category_fields": category_fields
    }


# ============================================================
# SCOPE A CATALOG TO ONE DASHBOARD
# ============================================================
#
# The global catalog above describes the whole dataset. A single dashboard
# usually looks at a few tables, and the date it plots is not always the
# "operational" date the global discovery prefers: a dashboard about customers
# plots the customer date (e.g. acquisition_date), which the global discovery
# excludes on purpose. If the filter kept the global range, it would offer years
# the charts never show and would map to tables the dashboard never queries, so
# nothing would happen when you filter.
#
# scope_catalog_to_dashboard narrows the catalog to the tables the dashboard's
# panels actually query, and rebuilds the date range from the date columns those
# panels actually plot. The result is a date filter whose range matches the
# charts and whose mappings really bite.

import sqlglot
from sqlglot import exp


def _tables_in_sql(sql):
    """Base tables a query reads (view names; CTE names and aliases excluded)."""
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except Exception:
        return set()
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    names = set()
    for t in tree.find_all(exp.Table):
        name = (t.name or "").lower()
        if name and name not in ctes:
            names.add(name)
    return names


def _columns_in_sql(sql):
    """Every column name a query mentions, lower-cased (table-qualified or not)."""
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except Exception:
        return set()
    return {c.name.lower() for c in tree.find_all(exp.Column) if c.name}


def _date_columns_of(df):
    """Every column of a table that really holds dates (permissive: lifecycle
    dates are NOT excluded here, because if a dashboard plots one it is relevant)."""
    found = []
    for column in df.columns:
        series = df[column]
        name = str(column).lower()
        if pd.api.types.is_datetime64_any_dtype(series):
            found.append(column)                 # a real datetime column
            continue
        # otherwise only TEXT columns whose name looks like a date, validated by
        # parsing. Booleans and numerics (on_time_flag, model_year, ...) are not
        # dates even when their name contains "time"/"year".
        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue
        if not any(k in name for k in ("date", "time", "timestamp", "period")):
            continue
        sample = series.dropna().head(100)
        if sample.empty or _parse_dates(sample).notna().mean() < 0.80:
            continue
        found.append(column)
    return found


def _panels_of(dash):
    """The panels of a dashboard dict, in either of the two shapes used in the app."""
    return dash.get("results") or dash.get("panels") or []


def scope_catalog_to_dashboard(dash, catalog, data):
    """Return a copy of `catalog` narrowed to the dashboard `dash`.

    - date_dimension: one mapping per table the dashboard queries, on the date
      column that table's panels actually reference; the range is recomputed
      from that column's data, so it matches the charts.
    - category_fields: only those on tables the dashboard queries.

    If nothing can be determined (no SQL, parse failure), the original catalog is
    returned unchanged, so a dashboard is never left worse off than before."""
    if not catalog or data is None:
        return catalog

    sqls = [p.get("sql") for p in _panels_of(dash) if p.get("sql")]
    if not sqls:
        return catalog

    used_tables = set()
    for sql in sqls:
        used_tables |= _tables_in_sql(sql)
    used_tables &= set(data)                      # only real tables
    if not used_tables:
        return catalog

    # columns referenced, per table that the panels using it mention
    referenced = set()
    for sql in sqls:
        referenced |= _columns_in_sql(sql)

    mappings = []
    for table in sorted(used_tables):
        df = data[table]
        if df is None or df.empty:
            continue
        # the date columns of this table that a panel actually plots
        candidates = [c for c in _date_columns_of(df) if str(c).lower() in referenced]
        if not candidates:
            continue
        # if several, keep the one with the most valid dates (the main time axis)
        best, best_valid, best_min, best_max = None, -1, None, None
        for column in candidates:
            parsed = _parse_dates(df[column]).dropna()
            if len(parsed) > best_valid:
                best, best_valid = column, len(parsed)
                best_min, best_max = parsed.min().date().isoformat(), parsed.max().date().isoformat()
        if best is not None:
            mappings.append({"table": table, "column": best,
                             "min_date": best_min, "max_date": best_max})

    scoped = dict(catalog)
    if mappings:
        scoped["date_dimension"] = {
            "label": "Dashboard date range",
            "min_date": min(m["min_date"] for m in mappings),
            "max_date": max(m["max_date"] for m in mappings),
            "mappings": mappings,
        }
    else:
        scoped["date_dimension"] = None           # this dashboard has no date to filter on

    scoped["category_fields"] = [
        f for f in catalog.get("category_fields", []) if f.get("table") in used_tables
    ]
    return scoped
