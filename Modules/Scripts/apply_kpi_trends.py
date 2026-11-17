"""
Modules/Scripts/apply_kpi_trends.py

Adds a previous-period delta + sparkline to each KPI card (three exact edits to app.py,
with a backup; your file is not replaced). Needs Modules/kpi_trends.py and the
run_with_filters method on the engine, both included in this package. Safe to run twice.

    python Modules/Scripts/apply_kpi_trends.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "app.py"
text = path.read_text(encoding="utf-8")

PAIRS = [["from Modules.visualisation import (\n    build_visual_metadata,\n    render_visual,\n    format_metric_value,\n)", "from Modules.visualisation import (\n    build_visual_metadata,\n    render_visual,\n    format_metric_value,\n)\nfrom Modules.kpi_trends import kpi_trend, sparkline_svg, format_delta"], ["def render_kpi(res):\n    item = res[\"item\"]\n    df, error = res.get(\"df\"), res.get(\"error\")\n    label = html.escape(item[\"title\"])\n\n    value_text, sub_text = None, None\n    if not error and df is not None:\n        metadata = build_visual_metadata(df, \"card\", item[\"question\"], title=item[\"title\"])\n        value_text, sub_text = _kpi_headline(df, metadata)\n\n    if value_text is None:\n        reason = html.escape(str(error or \"No value available.\"))\n        st.markdown(\n            f'<div class=\"kpi\"><div class=\"kpi-label\">{label}</div>'\n            f'<div class=\"kpi-value\">n/a</div><div class=\"pnote\">{reason}</div></div>',\n            unsafe_allow_html=True,\n        )\n        return\n\n    sub_html = (\n        f'<div class=\"kpi-sub\" style=\"font-size:0.8rem;color:#6b7280;margin-top:2px;\">'\n        f'{html.escape(str(sub_text))}</div>' if sub_text else ''\n    )\n    st.markdown(\n        f'<div class=\"kpi\"><div class=\"kpi-label\">{label}</div>'\n        f'<div class=\"kpi-value\">{html.escape(str(value_text))}</div>{sub_html}</div>',\n        unsafe_allow_html=True,\n    )\n    for assumption in res.get(\"assumptions\", []):\n        st.caption(f\"Assumption: {assumption}\")", "_DELTA_HEX = {\"green\": \"#1f9d57\", \"red\": \"#d64545\", \"amber\": \"#d99100\", \"neutral\": \"#6b7280\"}\n\n\ndef _kpi_trend_for(res, db, date_dimension):\n    \"\"\"Previous-period delta + sparkline for one KPI, or None. Never raises.\"\"\"\n    sql = res.get(\"sql\")\n    if not sql or db is None or res.get(\"error\") or res.get(\"df\") is None:\n        return None\n    try:\n        return kpi_trend(lambda f: db.run_with_filters(sql, f), sql, date_dimension,\n                         title=res[\"item\"][\"title\"])\n    except Exception:\n        return None\n\n\ndef render_kpi(res, trend=None):\n    item = res[\"item\"]\n    df, error = res.get(\"df\"), res.get(\"error\")\n    label = html.escape(item[\"title\"])\n\n    value_text, sub_text = None, None\n    if not error and df is not None:\n        metadata = build_visual_metadata(df, \"card\", item[\"question\"], title=item[\"title\"])\n        value_text, sub_text = _kpi_headline(df, metadata)\n\n    if value_text is None:\n        reason = html.escape(str(error or \"No value available.\"))\n        st.markdown(\n            f'<div class=\"kpi\"><div class=\"kpi-label\">{label}</div>'\n            f'<div class=\"kpi-value\">n/a</div><div class=\"pnote\">{reason}</div></div>',\n            unsafe_allow_html=True,\n        )\n        return\n\n    sub_html = (\n        f'<div class=\"kpi-sub\" style=\"font-size:0.8rem;color:#6b7280;margin-top:2px;\">'\n        f'{html.escape(str(sub_text))}</div>' if sub_text else ''\n    )\n\n    # A delta + sparkline, like a BI tool. Only for a plain numeric KPI: a\n    # \"which type is highest\" card (sub_text set) has no sensible period trend.\n    trend_html = ''\n    if trend and sub_text is None:\n        text, color = format_delta(trend, format_metric_value)\n        svg = sparkline_svg(trend[\"series\"], color)\n        hexcol = _DELTA_HEX.get(color, _DELTA_HEX[\"neutral\"])\n        delta_html = (f'<span style=\"color:{hexcol};font-size:0.82rem;font-weight:600;\">'\n                      f'{html.escape(text)}</span>' if text else '')\n        if delta_html or svg:\n            trend_html = (\n                '<div class=\"kpi-trend\" style=\"display:flex;align-items:center;'\n                f'justify-content:space-between;gap:8px;margin-top:6px;\">{delta_html}{svg}</div>')\n\n    st.markdown(\n        f'<div class=\"kpi\"><div class=\"kpi-label\">{label}</div>'\n        f'<div class=\"kpi-value\">{html.escape(str(value_text))}</div>{sub_html}{trend_html}</div>',\n        unsafe_allow_html=True,\n    )\n    for assumption in res.get(\"assumptions\", []):\n        st.caption(f\"Assumption: {assumption}\")"], ["    if kpis:\n        for column, (index, result) in zip(st.columns(len(kpis)), kpis):\n            with column:\n                with st.container(border=True, key=f\"card_kpi_{index}\"):\n                    render_kpi(result)", "    if kpis:\n        db = st.session_state.get(\"db\")\n        date_dimension = catalog.get(\"date_dimension\")\n        for column, (index, result) in zip(st.columns(len(kpis)), kpis):\n            trend = _kpi_trend_for(result, db, date_dimension)\n            with column:\n                with st.container(border=True, key=f\"card_kpi_{index}\"):\n                    render_kpi(result, trend)"]]

if "_kpi_trend_for" in text:
    print("Already applied: app.py already shows KPI trends.")
    sys.exit(0)

new = text
for old, repl in PAIRS:
    if old not in new:
        print("Could not find an expected block in app.py. Send me your render_kpi function "
              "and the KPI render loop in render_dashboard, and I will give an exact patch.")
        sys.exit(1)
    new = new.replace(old, repl, 1)

shutil.copy(path, str(path) + ".before_kpi_trends")
path.write_text(new, encoding="utf-8")
print("Patched app.py (3 edits). Backup: app.py.before_kpi_trends")
