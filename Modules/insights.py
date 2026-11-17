"""
Modules/insights.py

Plain-language reads of a dashboard and its panels, computed from the data (no model
call, no quota, deterministic). Two uses:

    panel_explain(panel)      -> one line describing a chart ("Contract is highest ...")
    dashboard_insight(dash)   -> a sentence or two summarising the whole dashboard

KPIs are skipped (their card already shows the number and its delta).
"""
import pandas as pd

from Modules.visualisation import (_looks_continuous, _readable_labels, build_visual_metadata,
                                   format_metric_value)


def _label_and_measure(df):
    """The (label column, measure column) of a categorical result, or (None, None)."""
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    labels = [c for c in df.columns if c not in numeric]
    if not numeric or not labels:
        return None, None
    return labels[0], numeric[-1]


def _date_and_measure(df):
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    date_col = None
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]) or any(
                k in str(c).lower() for k in ("date", "month", "year", "period")):
            date_col = c
            break
    if date_col is None or not numeric:
        return None, None
    measures = [c for c in numeric if c != date_col]
    return (date_col, measures[-1]) if measures else (None, None)


def _explain_categorical(df, title, kind):
    # read the same columns the chart plots, so the sentence matches the picture
    try:
        meta = build_visual_metadata(df, kind, title)
        label, measure = meta.get("x"), meta.get("y")
    except Exception:
        label = measure = None
    if label not in df.columns or measure not in df.columns:
        label, measure = _label_and_measure(df)
    if label is None:
        return None
    if _looks_continuous(df, label, title):
        return None          # a histogram: "512.37 is highest" would mean nothing
    s = df[[label, measure]].dropna().copy()
    if s.empty:
        return None
    # the same unique labels the chart shows ("Charlotte – Portland", not "Charlotte")
    s[label] = _readable_labels(df.loc[s.index], label, measure).values
    s = s.sort_values(measure, ascending=False)
    top_label, top_value = s.iloc[0][label], s.iloc[0][measure]
    if kind == "pie":
        total = s[measure].sum()
        share = (top_value / total * 100) if total else 0
        return f"{top_label} is the largest share at {share:.0f}%."
    if len(s) == 1:
        return f"{top_label}: {format_metric_value(top_value, measure)}."
    bottom_label, bottom_value = s.iloc[-1][label], s.iloc[-1][measure]
    return (f"{top_label} is highest ({format_metric_value(top_value, measure)}); "
            f"{bottom_label} lowest ({format_metric_value(bottom_value, measure)}).")


def _explain_line(df, title):
    date_col, measure = _date_and_measure(df)
    if date_col is None:
        return None
    s = df[[date_col, measure]].dropna()
    s = s.assign(_d=pd.to_datetime(s[date_col], errors="coerce")).dropna(subset=["_d"]).sort_values("_d")
    if len(s) < 2:
        return None
    first, last = s[measure].iloc[0], s[measure].iloc[-1]
    label = (title or "the measure").strip()
    if first == 0 or pd.isna(first):
        direction = "rose" if last > (first or 0) else ("fell" if last < (first or 0) else "was flat")
        return f"{label} {direction} over the period."
    pct = (last - first) / abs(first) * 100
    direction = "rose" if pct > 2 else ("fell" if pct < -2 else "was roughly flat")
    return (f"Over the period {label.lower()} {direction} "
            f"({format_metric_value(first, measure)} to {format_metric_value(last, measure)}).")


def panel_explain(panel):
    """A one-line read of one chart panel, or None (KPIs and tables return None)."""
    item = panel.get("item") or {}
    df = panel.get("df")
    kind = item.get("kind")
    if df is None or getattr(df, "empty", True):
        return None
    try:
        if kind in ("bar", "pie"):
            return _explain_categorical(df, item.get("title", ""), kind)
        if kind == "line":
            return _explain_line(df, item.get("title", ""))
    except Exception:
        return None
    return None


def dashboard_insight(dash, max_facts=2):
    """One or two sentences summarising the dashboard, from its charts. None if the
    dashboard has no chart to read."""
    facts = []
    for r in dash.get("results", []):
        if (r.get("item") or {}).get("kind") in ("bar", "pie", "line"):
            fact = panel_explain(r)
            if fact:
                facts.append(fact)
        if len(facts) >= max_facts:
            break
    return " ".join(facts) if facts else None
