"""
Modules/kpi_trends.py

Gives each KPI card a comparison and a small trend, the way a BI tool does:
a delta versus the previous period, and a sparkline of the last few periods.

How it is computed (so it can be explained in the report):
  - The dashboard already knows which date column(s) its panels plot (the scoped
    date dimension from dashboard_filters). The data's span is split into equal
    PERIODS (years when the span is long, otherwise months).
  - For each KPI, its OWN saved SQL is re-run once per period, through
    Database.run_with_filters, which applies only that period's date window and
    then restores the views. No model call is made, and no other panel is affected.
  - The newest period is the "current" value, the one before it the "previous";
    the delta is their difference. The series of per-period values is the sparkline.

Honest limits (degrade rather than mislead):
  - A KPI whose tables carry no date the dashboard filters on gets NO delta
    (every period would be identical). The card simply shows its number.
  - The newest (or oldest) period may be partial (data ending mid-year, or a
    dimension's first year). Such periods are DROPPED: a period counts only when
    the data fills at least MIN_COVERAGE of it. A dashboard whose date only partly
    covers its periods ends up with fewer than two complete periods and shows no
    delta at all, rather than a misleading one. The delta names the period it
    compares against ("+4.1% vs 2023").
  - Deltas are therefore meaningful on operational, time-series metrics (revenue
    over an order date) and quietly absent on attribute-by-lifecycle dashboards
    whose latest period is only partly covered.
"""
import re

import pandas as pd

# metric names that are BETTER when they go DOWN (cost, delay, incidents...).
LOWER_IS_BETTER = (
    "cost", "expense", "spend", "spending", "loss", "delay", "late", "detention",
    "incident", "accident", "violation", "complaint", "claim", "downtime", "idle",
    "turnover", "churn", "defect", "error", "overtime", "fuel",
)
# metrics where direction is not a value judgement.
NEUTRAL = ("age", "count of types", "ratio of")

FLAT_PCT = 1.0          # |delta| below this (percent) is "no real change" -> amber
STRONG_PCT = 10.0       # a large move, for reference by callers
MIN_COVERAGE = 0.85     # a period counts only if the data fills >= 85% of it


def period_windows(min_date, max_date, max_periods=12):
    """Split [min_date, max_date] into up to `max_periods` windows.
    Returns (granularity, [(label, {"start": iso, "end": iso}), ...]) oldest first.
    Years when the span is long, otherwise months."""
    start = pd.Timestamp(min_date).normalize()
    end = pd.Timestamp(max_date).normalize()
    if end < start:
        return "none", []
    years = end.year - start.year + 1
    if years >= 3:
        gran = "year"
        periods = pd.period_range(start, end, freq="Y")
    else:
        gran = "month"
        periods = pd.period_range(start, end, freq="M")
    periods = list(periods)[-max_periods:]
    windows = []
    for p in periods:
        label = str(p.year) if gran == "year" else p.strftime("%b %Y")
        windows.append((label, {"start": p.start_time.date().isoformat(),
                                "end": p.end_time.date().isoformat()}))
    return gran, windows


def _mentions(text, keywords):
    """True if any keyword appears as a WHOLE word/phrase. Substring matching would
    make "age" fire inside "average" and "late" inside "related"."""
    return any(re.search(r"\b" + re.escape(k) + r"\b", text) for k in keywords)


def _coverage(window, data_min, data_max):
    """Fraction of a period's calendar span that the data actually covers (0..1).
    A partial year (data ending mid-year, or a dimension's first year) scores low."""
    period_start = pd.Timestamp(window["start"])
    period_end = pd.Timestamp(window["end"])
    overlap_start = max(data_min, period_start)
    overlap_end = min(data_max, period_end)
    overlap_days = (overlap_end - overlap_start).days + 1 if overlap_end >= overlap_start else 0
    period_days = (period_end - period_start).days + 1
    return overlap_days / period_days if period_days else 0.0


def complete_windows(windows, data_min, data_max, min_coverage=MIN_COVERAGE):
    """Keep only the periods the data fills (>= min_coverage). This is what stops a
    partial trailing period (e.g. a half-finished current year) from producing a
    false -99% delta next to a lifetime total."""
    return [(label, w) for label, w in windows
            if _coverage(w, data_min, data_max) >= min_coverage]


def direction_for_metric(name):
    """'higher_better' | 'lower_better' | 'neutral' from the metric/title text."""
    text = str(name).lower()
    if _mentions(text, NEUTRAL):
        return "neutral"
    if _mentions(text, LOWER_IS_BETTER):
        return "lower_better"
    return "higher_better"


def color_for(delta_pct, direction):
    """A traffic-light colour for the delta: green = improving, red = worsening,
    amber = flat/too small to call, neutral when the metric has no good direction."""
    if delta_pct is None or direction == "neutral":
        return "neutral"
    if abs(delta_pct) < FLAT_PCT:
        return "amber"
    improving = (delta_pct > 0) if direction == "higher_better" else (delta_pct < 0)
    return "green" if improving else "red"


def _scalar(df):
    """The single numeric value of a one-row KPI frame, or None."""
    if df is None or len(df) != 1:
        return None
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric:
        return None
    value = df[numeric[0]].iloc[0]
    return None if pd.isna(value) else float(value)


def kpi_trend(run_window, sql, date_dimension, title="", max_periods=12):
    """Build the trend for one KPI.

    run_window(window_filters) -> DataFrame : runs the KPI's SQL for a date window
        (in the app this is db.run_with_filters(sql, {"date": ...})).
    date_dimension : the dashboard's scoped date dimension, or None.

    Returns None when no meaningful trend exists, otherwise:
      {series: [{"label","value"}], current, previous, delta, delta_pct,
       direction, color, period_label, granularity}"""
    if not date_dimension or not date_dimension.get("mappings"):
        return None
    gran, windows = period_windows(date_dimension["min_date"], date_dimension["max_date"], max_periods)
    # keep only periods the data actually fills, so a partial first/last period cannot
    # manufacture a huge delta (this is what silences the deltas on a dashboard whose
    # date is a lifecycle attribute only partly covering the latest year)
    windows = complete_windows(windows, pd.Timestamp(date_dimension["min_date"]),
                               pd.Timestamp(date_dimension["max_date"]))
    if len(windows) < 2:
        return None

    mappings = date_dimension["mappings"]
    series = []
    for label, window in windows:
        df = run_window({"date": {"start": window["start"], "end": window["end"], "mappings": mappings}})
        value = _scalar(df)
        series.append({"label": label, "value": value})

    valued = [p for p in series if p["value"] is not None]
    if len(valued) < 2:
        return None
    # no date actually bit (every period identical) -> not a real trend
    if len({round(p["value"], 9) for p in valued}) == 1:
        return None

    current, previous = valued[-1]["value"], valued[-2]["value"]
    delta = current - previous
    delta_pct = (delta / previous * 100.0) if previous not in (0, None) else None
    direction = direction_for_metric(title)
    return {
        "series": series,
        "current": current,
        "previous": previous,
        "delta": delta,
        "delta_pct": delta_pct,
        "direction": direction,
        "color": color_for(delta_pct, direction),
        "period_label": valued[-2]["label"],
        "granularity": gran,
    }


# ---- a tiny inline-SVG sparkline (no extra chart, cheap to render) ----
_COLORS = {"green": "#1f9d57", "red": "#d64545", "amber": "#d99100", "neutral": "#8a94a6"}


def sparkline_svg(series, color="neutral", width=96, height=26):
    """A minimal sparkline as an inline SVG string. `series` is the list of
    {"label","value"} from kpi_trend; missing points break the line."""
    values = [p["value"] for p in series]
    present = [v for v in values if v is not None]
    stroke = _COLORS.get(color, _COLORS["neutral"])
    if len(present) < 2:
        return ""
    lo, hi = min(present), max(present)
    span = (hi - lo) or 1.0
    n = len(values)
    step = width / (n - 1)
    pts, last_pt = [], None
    segments, cur = [], []
    for i, v in enumerate(values):
        if v is None:
            if cur:
                segments.append(cur); cur = []
            continue
        x = i * step
        y = height - 2 - (v - lo) / span * (height - 4)
        cur.append(f"{x:.1f},{y:.1f}")
    if cur:
        segments.append(cur)
    polylines = "".join(
        f'<polyline fill="none" stroke="{stroke}" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(seg)}"/>'
        for seg in segments if len(seg) >= 2
    )
    last = segments[-1][-1] if segments and segments[-1] else None
    dot = ""
    if last:
        lx, ly = last.split(",")
        dot = f'<circle cx="{lx}" cy="{ly}" r="2.3" fill="{stroke}"/>'
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg">{polylines}{dot}</svg>')


def format_delta(trend, format_value):
    """A short delta caption, e.g. '+4.1% vs 2023'. `format_value` formats an
    absolute number (the app passes visualisation.format_metric_value-like fn)."""
    if not trend:
        return None, "neutral"
    pct, color = trend["delta_pct"], trend["color"]
    arrow = "▲" if trend["delta"] > 0 else ("▼" if trend["delta"] < 0 else "■")
    if pct is None:
        text = f"{arrow} {format_value(abs(trend['delta']))} vs {trend['period_label']}"
    else:
        text = f"{arrow} {abs(pct):.1f}% vs {trend['period_label']}"
    return text, color
