"""
Modules/semantic_checks.py

Deterministic checks on a query that RAN, to see whether it answers the
question. The database accepted the SQL; these checks look at what came back.

check_result(...) returns a list of issues, each a dict
    {"code": ..., "severity": "error" | "warning", "message": ...}
  error    the model can fix it: the issue is sent back to the repair step
  warning  nothing the model can fix (for example the data really ends in
           the middle of a month): shown to the user as a note

Checks
  missing_limit       a ranking was asked (top, best, worst ...) but no LIMIT
  too_many_rows       the result has more rows than the requested top N
  missing_name        an id is shown with no name, although a table has one
  kpi_shape           a KPI must be one row with a number
  line_needs_time     a line chart needs a date or year column
  single_category     a bar chart with one row
  too_many_slices     a pie chart with many parts
  partial_period      the last period of a trend is incomplete
  date_outside_coverage  a hard-coded date outside the data's date range

None of this raises: a check that cannot run is skipped.
"""
import calendar
import re

import pandas as pd
import sqlglot
from sqlglot import exp

RANK_WORDS = re.compile(r"\b(top|best|worst|highest|lowest)\b", re.IGNORECASE)
PER_WORDS = re.compile(r"\b(each|every|per)\b", re.IGNORECASE)
TOP_N = re.compile(r"\btop\s+(\d+)\b", re.IGNORECASE)
DATE_LITERAL = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b")
DEFAULT_TOP = 10
MAX_PIE_SLICES = 12
MANY_CATEGORIES = 60


def _issue(code, severity, message, **details):
    out = {"code": code, "severity": severity, "message": message}
    out.update(details)
    return out


# ----------------------------------------------------------------------
# data coverage (cached on the Database object)
# ----------------------------------------------------------------------
def get_coverage(db):
    """{table: {date_column: (min, max)}} for every date column."""
    cached = getattr(db, "_coverage_cache", None)
    if cached is not None:
        return cached
    coverage = {}
    types = db.run(
        "SELECT table_name, column_name, data_type FROM information_schema.columns;"
    )
    for table in db.tables:
        cols = [r.column_name for r in types.itertuples()
                if r.table_name == table
                and str(r.data_type).upper().startswith(("DATE", "TIMESTAMP"))]
        if not cols:
            continue
        parts = []
        for i, c in enumerate(cols):
            parts += [f'MIN("{c}") AS lo{i}', f'MAX("{c}") AS hi{i}']
        row = db.run(f'SELECT {", ".join(parts)} FROM "{table}";').iloc[0]
        coverage[table] = {c: (row[f"lo{i}"], row[f"hi{i}"]) for i, c in enumerate(cols)}
    db._coverage_cache = coverage
    return coverage


def _tables_used(sql):
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
        return {t.name.lower() for t in tree.find_all(exp.Table)}
    except Exception:
        return set()


def _bounds(db, sql):
    """(earliest, latest) date over the date columns of the tables the query uses."""
    used = _tables_used(sql)
    lows, highs = [], []
    for table, cols in get_coverage(db).items():
        if table.lower() in used:
            for lo, hi in cols.values():
                if pd.notna(lo):
                    lows.append(pd.Timestamp(lo))
                if pd.notna(hi):
                    highs.append(pd.Timestamp(hi))
    if not highs:
        return None, None
    return min(lows), max(highs)


# ----------------------------------------------------------------------
# individual checks
# ----------------------------------------------------------------------
def _wants_ranking(question, constraints):
    if constraints and getattr(constraints, "top_n", None):
        return True
    q = question or ""
    return bool(TOP_N.search(q) or (RANK_WORDS.search(q) and not PER_WORDS.search(q)))


def _requested_n(question, constraints):
    if constraints and getattr(constraints, "top_n", None):
        return int(constraints.top_n)
    m = TOP_N.search(question or "")
    return int(m.group(1)) if m else None


def _has_limit(sql):
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
        return tree.find(exp.Limit) is not None or tree.find(exp.Fetch) is not None
    except Exception:
        return True      # cannot tell: do not complain


def _check_ranking(question, constraints, sql, df):
    if not _wants_ranking(question, constraints):
        return []
    n = _requested_n(question, constraints)
    issues = []
    if not _has_limit(sql):
        issues.append(_issue(
            "missing_limit", "error",
            "The question asks for a ranking (top, best or worst): ORDER BY the "
            f"metric and add LIMIT {n or DEFAULT_TOP}."))
    elif n and len(df) > n:
        issues.append(_issue("too_many_rows", "error",
                             f"The question asks for the top {n} but {len(df)} rows came back."))
    return issues


def _check_names(df, db, kind):
    if kind == "kpi" or len(df) < 2:
        return []
    id_cols = [c for c in df.columns if str(c).lower() == "id" or str(c).lower().endswith("_id")]
    has_text = any(df[c].dtype == object or pd.api.types.is_string_dtype(df[c])
                   for c in df.columns if c not in id_cols)
    if not id_cols or has_text:
        return []
    issues = []
    for col in id_cols[:1]:
        for table, info in db.tables.items():
            cols = info["columns"]
            names = [c for c in cols if "name" in c.lower() and c != col]
            if col in cols and names:
                issues.append(_issue(
                    "missing_name", "error",
                    f"The result shows {col} without a name. Table {table} has "
                    f"{', '.join(names)}: join it and return the name next to {col}."))
                return issues
    return issues


def _check_shape(df, kind):
    if kind is None:
        return []
    issues = []
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if kind == "kpi":
        if len(df) != 1 or not numeric:
            issues.append(_issue("kpi_shape", "error",
                                 "A KPI must be exactly one row with a numeric value; "
                                 f"this result has {len(df)} rows."))
    elif kind == "line":
        time_cols = [c for c in df.columns
                     if pd.api.types.is_datetime64_any_dtype(df[c])
                     or str(c).lower() in ("year", "month", "date", "period", "week", "quarter")]
        if not time_cols:
            issues.append(_issue("line_needs_time", "error",
                                 "A line chart needs one date or year column and a measure; "
                                 "use date_trunc for a date column."))
    elif kind == "bar":
        if len(df) == 1:
            issues.append(_issue("single_category", "warning", "The bar chart has a single bar."))
        elif len(df) > MANY_CATEGORIES:
            issues.append(_issue("many_categories", "warning",
                                 f"{len(df)} categories: only the top ones will be drawn."))
    elif kind == "pie":
        if len(df) > MAX_PIE_SLICES:
            issues.append(_issue("too_many_slices", "warning",
                                 f"{len(df)} slices are too many for a pie chart."))
    return issues


def _granularity(dates):
    d = pd.Series(sorted(set(pd.to_datetime(dates)))).diff().dropna().dt.days
    if d.empty:
        return None
    m = float(d.median())
    if m <= 1.5:
        return "day"
    if m <= 8:
        return "week"
    if m <= 40:
        return "month"
    if m <= 100:
        return "quarter"
    return "year"


def _period_end(start, granularity):
    start = pd.Timestamp(start).normalize()
    if granularity == "day":
        return start
    if granularity == "week":
        return start + pd.Timedelta(days=6)
    if granularity == "month":
        return start.replace(day=calendar.monthrange(start.year, start.month)[1])
    if granularity == "quarter":
        month = start.month + 2
        return start.replace(month=month, day=calendar.monthrange(start.year, month)[1])
    return start.replace(month=12, day=31)


def _check_partial_period(df, db, sql):
    # a date column, or a plain year column
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    if date_cols:
        dates = df[date_cols[0]].dropna()
        granularity = _granularity(dates) if len(dates) >= 2 else None
        last = pd.Timestamp(dates.max()) if len(dates) else None
    else:
        year_cols = [c for c in df.columns if str(c).lower() == "year"
                     and pd.api.types.is_integer_dtype(df[c])]
        if not year_cols or df[year_cols[0]].dropna().empty:
            return []
        granularity = "year"
        last = pd.Timestamp(int(df[year_cols[0]].max()), 1, 1)
    if granularity is None or last is None:
        return []
    _, data_end = _bounds(db, sql)
    if data_end is None:
        return []
    end = _period_end(last, granularity)
    if data_end.normalize() < end:
        label = last.strftime({"year": "%Y", "month": "%Y-%m"}.get(granularity, "%Y-%m-%d"))
        return [_issue(
            "partial_period", "warning",
            f"The last {granularity} ({label}) is incomplete: the data ends on "
            f"{data_end.date()}. Read it as a partial period.",
            period=label, data_end=str(data_end.date()))]
    return []


def _check_date_literals(sql, db):
    low, high = _bounds(db, sql)
    if low is None:
        return []
    issues = []
    for y, m, d in DATE_LITERAL.findall(sql):
        try:
            stamp = pd.Timestamp(int(y), int(m), int(d))
        except ValueError:
            continue
        if stamp < low.normalize() or stamp > high.normalize():
            issues.append(_issue(
                "date_outside_coverage", "warning",
                f"The query hard-codes {stamp.date()}, outside the data's dates "
                f"({low.date()} to {high.date()})."))
    return issues


# ----------------------------------------------------------------------
def check_result(question, kind, constraints, sql, df, db):
    """All checks. Returns a list of issue dicts (possibly empty)."""
    issues = []
    for step in (
        lambda: _check_ranking(question, constraints, sql, df),
        lambda: _check_names(df, db, kind),
        lambda: _check_shape(df, kind),
        lambda: _check_partial_period(df, db, sql),
        lambda: _check_date_literals(sql, db),
    ):
        try:
            issues.extend(step())
        except Exception:
            continue          # a check that cannot run is skipped, never fatal
    return issues


def format_problem(issues):
    """The text sent back to the model for the error-level issues."""
    errors = [i["message"] for i in issues if i["severity"] == "error"]
    return ("The query ran, but its result does not answer the question properly:\n- "
            + "\n- ".join(errors)
            + "\nFix only these points and keep everything else.")
