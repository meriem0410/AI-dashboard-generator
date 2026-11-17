"""
Modules/export_html.py

Turns a dashboard into ONE self-contained HTML report the user can download, open
in any browser, share, and print to PDF (A4 landscape). No model call.

    dashboard_to_html(dash, insight=None, title="Dashboard", *, dataset=None,
                      filters=None, include_sql=False, generated_at=None,
                      offline=False) -> str

What the report carries, beyond the charts themselves:
  - context: dataset name, generation date, and the filters that were applied, so a
    printed page is never ambiguous about what it shows;
  - the same look as the screen: KPI row first, the same chart styles, sorting,
    palette, the "top 25 of 92" notes and the one-line reading under each chart;
  - optionally an appendix with the question and the validated SQL behind every
    panel (the trust story, on paper).
"""
import datetime as _dt
import html as _html

import pandas as pd

from Modules.insights import panel_explain
from Modules.visualisation import build_visual_metadata, format_metric_value, render_visual

ACCENT = "#E2231A"
INK = "#1B1F2A"
SLATE = "#33415C"
PALETTE = ["#E8645C", "#33415C", "#8EB8C7", "#F4B1AB", "#A7B4C8", "#F2CF9A", "#7FB7A5"]
BAR_COLOUR = "#7FAFC0"
MAX_TABLE_ROWS = 200
WIDE_KINDS = ("line", "table")


# ------------------------------------------------------------
# small helpers
# ------------------------------------------------------------

def _esc(value):
    return _html.escape(str(value))


def _kpi_text(df, metadata):
    """(headline, subvalue) for a KPI, mirroring the app's card logic."""
    if df is None or len(df) != 1:
        return None, None
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    labels = [c for c in df.columns if c not in numeric]
    if len(labels) == 1 and numeric:
        label_value = df[labels[0]].iloc[0]
        num_col = metadata.get("y") if metadata.get("y") in numeric else numeric[0]
        num_value = df[num_col].iloc[0]
        if pd.notna(label_value):
            return str(label_value), (None if pd.isna(num_value) else format_metric_value(num_value, num_col))
    col = metadata.get("y") if metadata.get("y") in df.columns else (numeric[0] if numeric else df.columns[0])
    value = df[col].iloc[0]
    return (format_metric_value(value, col) if pd.notna(value) else "n/a"), None


def describe_filters(filters):
    """A readable line for the applied filters dict ({"date": ..., "category": ...})."""
    if not filters:
        return "No filters applied (all data)."
    parts = []
    date = filters.get("date")
    if date and date.get("start"):
        parts.append(f"Date {date['start']} to {date.get('end', date['start'])}")
    cat = filters.get("category")
    if cat and cat.get("values"):
        column = str(cat.get("column", "")).replace("_", " ")
        parts.append(f"{column}: {', '.join(str(v) for v in cat['values'])}")
    return "; ".join(parts) + "." if parts else "No filters applied (all data)."


def _is_id(column):
    name = str(column).lower()
    return name == "id" or name.endswith("_id") or name in ("year", "unit_number")


def _sorted(df, item):
    sort = item.get("sort") or {}
    if not sort:
        return df
    by = sort.get("by")
    if by not in df.columns:
        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not _is_id(c)]
        by = numeric[-1] if numeric else None
    if by is None:
        return df
    return df.sort_values(by, ascending=bool(sort.get("ascending")), na_position="last")


def _fmt_cell(column, value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and not _is_id(column):
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _table_html(df, item):
    df = _sorted(df, item)
    note = ""
    if len(df) > MAX_TABLE_ROWS:
        note = f'<p class="note">Showing the first {MAX_TABLE_ROWS} of {len(df):,} rows.</p>'
        df = df.head(MAX_TABLE_ROWS)
    numeric = {c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}
    head = "".join(f'<th class="{"num" if c in numeric else ""}">{_esc(str(c).replace("_", " ").title())}</th>'
                   for c in df.columns)
    rows = []
    for record in df.itertuples(index=False):
        cells = "".join(
            f'<td class="{"num" if c in numeric else ""}">{_esc(_fmt_cell(c, v))}</td>'
            for c, v in zip(df.columns, record))
        rows.append(f"<tr>{cells}</tr>")
    return f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>{note}'


def _style(fig):
    """The dashboard look, for print: palette, quiet grid, no in-chart title."""
    fig.update_layout(
        colorway=PALETTE, title_text=None,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=8, b=8),
        font=dict(family="Arial, Helvetica, sans-serif", size=12, color=SLATE),
        legend=dict(orientation="h", y=-0.22, x=0, title_text=""),
    )
    fig.update_xaxes(showgrid=False, linecolor="#D5DCE5", automargin=True)
    fig.update_yaxes(gridcolor="#E8EDF2", zeroline=False, automargin=True)
    bars = [t for t in fig.data if t.type in ("bar", "histogram")]
    for trace in bars:
        current = getattr(trace.marker, "color", None)
        if len(bars) == 1 and (current is None or isinstance(current, str)):
            trace.update(marker=dict(color=BAR_COLOUR))
    for i, trace in enumerate(t for t in fig.data if t.type == "scatter"):
        colour = PALETTE[i % len(PALETTE)]
        trace.update(line=dict(color=colour, width=2.6), marker=dict(color=colour))
    fig.update_traces(selector=dict(type="pie"), hole=0.55,
                      marker=dict(line=dict(color="#fff", width=2)))
    return fig


# ------------------------------------------------------------
# panels
# ------------------------------------------------------------

def _kpi_html(panel):
    item = panel.get("item") or {}
    df = panel.get("df")
    label = _esc(item.get("title", ""))
    if df is None or getattr(df, "empty", True) or panel.get("error"):
        reason = _esc(panel.get("error") or "No data.")
        return f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-value">n/a</div><p class="note">{reason}</p></div>'
    metadata = build_visual_metadata(df, "card", item.get("question", ""), title=item.get("title"))
    value, sub = _kpi_text(df, metadata)
    sub_html = f'<div class="kpi-sub">{_esc(sub)}</div>' if sub else ""
    return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{_esc(value)}</div>{sub_html}</div>')


def _panel_html(panel, include_plotlyjs):
    """One chart or table card. Returns (html, used_plotly)."""
    item = panel.get("item") or {}
    df = panel.get("df")
    kind = item.get("kind")
    wide = " wide" if kind in WIDE_KINDS else ""
    head = f"<h3>{_esc(item.get('title', ''))}</h3>"
    if df is None or getattr(df, "empty", True) or panel.get("error"):
        reason = _esc(panel.get("error") or "No data.")
        return f'<section class="panel{wide}">{head}<p class="note">{reason}</p></section>', False

    if kind == "kpi":                       # a KPI that ended up among charts
        return f'<section class="panel">{_kpi_html(panel)}</section>', False

    if kind in ("bar", "line", "pie"):
        try:
            metadata = build_visual_metadata(df, kind, item.get("question", ""), title=item.get("title"))
            metadata["style"] = item.get("style")          # same look as on screen
            metadata["sort"] = item.get("sort")
            fig = render_visual(df, metadata)
        except Exception:
            fig, metadata = None, {}
        if fig is not None:
            asked = fig.layout.height or 0
            height = 340 if asked <= 420 else min(int(asked * 0.75), 900)
            fig = _style(fig)
            fig.update_layout(height=height)
            body = fig.to_html(include_plotlyjs=include_plotlyjs, full_html=False,
                               config={"displaylogo": False, "responsive": True,
                                       "modeBarButtonsToRemove": ["select2d", "lasso2d"]})
            notes = []
            if metadata.get("note"):
                notes.append(metadata["note"])
            reading = panel_explain(panel)
            if reading:
                notes.append(reading)
            notes_html = "".join(f'<p class="note">{_esc(n)}</p>' for n in notes)
            return f'<section class="panel{wide}">{head}{body}{notes_html}</section>', True

    # table, or a chart that could not be built
    return f'<section class="panel wide">{head}{_table_html(df, item)}</section>', False


def _appendix_html(results):
    rows = []
    for n, panel in enumerate(results, 1):
        item = panel.get("item") or {}
        sql = panel.get("sql")
        if not sql:
            continue
        status = "failed" if panel.get("error") else "validated and executed"
        tries = panel.get("attempts", 1)
        tries_txt = f", self-corrected in {tries} attempts" if tries and tries > 1 else ""
        rows.append(
            f'<div class="sql-item"><h4>{n}. {_esc(item.get("title", ""))}</h4>'
            f'<p class="note">Question: {_esc(item.get("question", ""))} &middot; {status}{tries_txt}</p>'
            f'<pre>{_esc(sql)}</pre></div>')
    if not rows:
        return ""
    return ('<section class="appendix"><h2>Appendix: how each figure was produced</h2>'
            '<p class="note">Every panel comes from one read-only SQL query, generated by the '
            'agent, checked by the SQL guard and the semantic checks, then executed on the '
            'dataset. The exact queries are below.</p>' + "".join(rows) + "</section>")


# ------------------------------------------------------------
# document
# ------------------------------------------------------------

def dashboard_to_html(dash, insight=None, title="Dashboard", *, dataset=None, filters=None,
                      include_sql=False, generated_at=None, offline=False):
    """A complete, self-contained HTML document for the dashboard.

    offline=True embeds plotly.js (about 3.5 MB) so the file works with no
    internet; the default loads it once from the CDN."""
    results = dash.get("results", [])
    kpis = [r for r in results if (r.get("item") or {}).get("kind") == "kpi"]
    others = [r for r in results if (r.get("item") or {}).get("kind") != "kpi"]

    plotly_mode = True if offline else "cdn"
    parts, loaded = [], False
    for panel in others:
        part, used = _panel_html(panel, False if loaded else plotly_mode)
        # plotly.js is only written by the first chart that actually renders
        loaded = loaded or used
        parts.append(part)

    when = generated_at or _dt.datetime.now()
    when_txt = when.strftime("%d %B %Y, %H:%M") if hasattr(when, "strftime") else str(when)
    meta = [f"Generated {_esc(when_txt)}"]
    if dataset:
        meta.insert(0, f"Dataset: {_esc(dataset)}")
    filters_txt = _esc(describe_filters(filters))
    question = dash.get("question")
    question_html = (f'<p class="question">Requested: &ldquo;{_esc(question)}&rdquo;</p>'
                     if question else "")
    insight_html = f'<div class="insight"><b>Key reading.</b> {_esc(insight)}</div>' if insight else ""
    kpi_html = (f'<div class="kpis">{"".join(_kpi_html(k) for k in kpis)}</div>' if kpis else "")
    appendix = _appendix_html(results) if include_sql else ""
    safe_title = _esc(title)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>
 :root {{ --accent: {ACCENT}; --ink: {INK}; --slate: {SLATE}; --line: #E5E8EF; --muted: #6B7280; }}
 * {{ box-sizing: border-box; }}
 body {{ font-family: Arial, Helvetica, sans-serif; margin: 0; color: var(--ink); background: #F4F6FB; }}
 .page {{ max-width: 1280px; margin: 0 auto; padding: 28px 32px 40px; }}
 header {{ background: #fff; border-radius: 12px; padding: 18px 22px; margin-bottom: 18px;
          border: 1px solid var(--line); border-left: 6px solid var(--accent); }}
 .brand {{ font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; color: var(--accent); font-weight: 700; }}
 h1 {{ margin: 4px 0 6px; font-size: 1.7rem; }}
 .meta {{ color: var(--muted); font-size: .85rem; }}
 .filters {{ display: inline-block; margin-top: 8px; padding: 4px 10px; border-radius: 999px;
            background: #EEF2F7; color: var(--slate); font-size: .82rem; }}
 .question {{ color: var(--slate); font-size: .9rem; margin: 8px 0 0; }}
 .insight {{ background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px;
            margin-bottom: 16px; color: var(--slate); }}
 .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 16px; }}
 .kpi {{ background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }}
 .kpi::before {{ content: ""; display: block; width: 26px; height: 3px; background: var(--accent); margin-bottom: 10px; }}
 .kpi-label {{ color: var(--muted); font-size: .85rem; }}
 .kpi-value {{ font-size: 1.9rem; font-weight: 700; margin-top: 4px; }}
 .kpi-sub {{ color: var(--muted); font-size: .82rem; }}
 .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
 .panel {{ background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; min-width: 0; }}
 .panel.wide {{ grid-column: 1 / -1; }}
 h3 {{ margin: 0 0 8px; font-size: 1rem; }}
 .note {{ color: var(--muted); font-size: .8rem; margin: 6px 0 0; }}
 table {{ border-collapse: collapse; width: 100%; font-size: .85rem; }}
 th {{ text-align: left; color: var(--muted); font-weight: 600; border-bottom: 2px solid var(--line); padding: 6px 10px; }}
 td {{ padding: 6px 10px; border-bottom: 1px solid #F0F2F6; }}
 th.num {{ text-align: right; }}
 td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
 .appendix {{ margin-top: 26px; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 18px 22px; }}
 .appendix h2 {{ margin: 0 0 6px; font-size: 1.15rem; }}
 .sql-item h4 {{ margin: 16px 0 2px; font-size: .92rem; }}
 pre {{ background: #F6F8FB; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px;
       font-size: .78rem; white-space: pre-wrap; word-break: break-word; }}
 footer {{ margin-top: 22px; color: var(--muted); font-size: .78rem; text-align: center; }}
 @media (max-width: 820px) {{ .grid {{ grid-template-columns: 1fr; }} .page {{ padding: 16px; }} }}
 @page {{ size: A4 landscape; margin: 12mm; }}
 @media print {{
   body {{ background: #fff; }}
   .page {{ padding: 0; max-width: none; }}
   .panel, .kpi, .sql-item, header, .insight {{ break-inside: avoid; }}
   .appendix {{ break-before: page; border: none; padding: 0; }}
   .modebar {{ display: none !important; }}
 }}
</style></head>
<body><div class="page">
<header>
 <div class="brand">Devoboard report</div>
 <h1>{safe_title}</h1>
 <div class="meta">{' &middot; '.join(meta)}</div>
 <div class="filters">Filters: {filters_txt}</div>
 {question_html}
</header>
{insight_html}
{kpi_html}
<div class="grid">
{"".join(parts)}
</div>
{appendix}
<footer>Generated by Devoboard. Every figure comes from a validated, read-only SQL query on the dataset named above.</footer>
</div></body></html>"""
