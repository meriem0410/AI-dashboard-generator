"""
Modules/Scripts/apply_kpi_label_fix.py

Makes a KPI card show the LABEL for a "which X is highest" question (e.g. "Contract")
instead of the amount (206.8M), with the amount as a small subvalue. Two exact edits to
app.py, with a backup; your file is not replaced. Safe to run twice.

    python Modules/Scripts/apply_kpi_label_fix.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "app.py"
text = path.read_text(encoding="utf-8")

OLD1_V = "def _kpi_value(df, metadata):\n    \"\"\"The single number of a KPI result, formatted, or None.\"\"\"\n    if df is None or len(df) != 1:\n        return None\n    column = metadata.get(\"y\")\n    if column is None or column not in df.columns:\n        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]\n        column = numeric[0] if numeric else df.columns[0]\n    value = df[column].iloc[0]\n    if pd.isna(value):\n        return None\n    return format_metric_value(value, column)"
NEW1_V = "def _kpi_headline(df, metadata):\n    \"\"\"What a KPI card should show, as (headline, subvalue).\n\n    - A plain single number (\"Total trips\") -> (formatted number, None).\n    - A \"which X is highest/lowest\" answer, whose row is (label, number) -> the\n      LABEL is the headline and the number is the small subvalue. This fixes a\n      card titled \"Customer Type with Highest Revenue\" that showed the amount\n      (e.g. 206.8M) instead of the type (\"Contract\").\"\"\"\n    if df is None or len(df) != 1:\n        return None, None\n    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]\n    labels = [c for c in df.columns if c not in numeric]\n\n    # one label + at least one number: the answer is the label\n    if len(labels) == 1 and numeric:\n        label_value = df[labels[0]].iloc[0]\n        num_col = metadata.get(\"y\") if metadata.get(\"y\") in numeric else numeric[0]\n        num_value = df[num_col].iloc[0]\n        if pd.notna(label_value):\n            sub = None if pd.isna(num_value) else format_metric_value(num_value, num_col)\n            return str(label_value), sub\n\n    # a plain number\n    column = metadata.get(\"y\")\n    if column is None or column not in df.columns:\n        column = numeric[0] if numeric else df.columns[0]\n    value = df[column].iloc[0]\n    if pd.isna(value):\n        return None, None\n    return format_metric_value(value, column), None\n\n\ndef _kpi_value(df, metadata):\n    \"\"\"Backwards-compatible: the headline part of a KPI, or None.\"\"\"\n    return _kpi_headline(df, metadata)[0]"
OLD2_V = "    value_text = None\n    if not error and df is not None:\n        metadata = build_visual_metadata(df, \"card\", item[\"question\"], title=item[\"title\"])\n        value_text = _kpi_value(df, metadata)\n\n    if value_text is None:\n        reason = html.escape(str(error or \"No value available.\"))\n        st.markdown(\n            f'<div class=\"kpi\"><div class=\"kpi-label\">{label}</div>'\n            f'<div class=\"kpi-value\">n/a</div><div class=\"pnote\">{reason}</div></div>',\n            unsafe_allow_html=True,\n        )\n        return\n\n    st.markdown(\n        f'<div class=\"kpi\"><div class=\"kpi-label\">{label}</div>'\n        f'<div class=\"kpi-value\">{html.escape(str(value_text))}</div></div>',\n        unsafe_allow_html=True,\n    )"
NEW2_V = "    value_text, sub_text = None, None\n    if not error and df is not None:\n        metadata = build_visual_metadata(df, \"card\", item[\"question\"], title=item[\"title\"])\n        value_text, sub_text = _kpi_headline(df, metadata)\n\n    if value_text is None:\n        reason = html.escape(str(error or \"No value available.\"))\n        st.markdown(\n            f'<div class=\"kpi\"><div class=\"kpi-label\">{label}</div>'\n            f'<div class=\"kpi-value\">n/a</div><div class=\"pnote\">{reason}</div></div>',\n            unsafe_allow_html=True,\n        )\n        return\n\n    sub_html = (\n        f'<div class=\"kpi-sub\" style=\"font-size:0.8rem;color:#6b7280;margin-top:2px;\">'\n        f'{html.escape(str(sub_text))}</div>' if sub_text else ''\n    )\n    st.markdown(\n        f'<div class=\"kpi\"><div class=\"kpi-label\">{label}</div>'\n        f'<div class=\"kpi-value\">{html.escape(str(value_text))}</div>{sub_html}</div>',\n        unsafe_allow_html=True,\n    )"

EDITS = [
    (OLD1_V, NEW1_V),
    (OLD2_V, NEW2_V),
]

if "_kpi_headline" in text:
    print("Already applied: app.py already has the KPI label fix.")
    sys.exit(0)

new = text
for old, repl in EDITS:
    if old not in new:
        print("Could not find an expected block in app.py. Your render_kpi / _kpi_value "
              "differs from what I expected. Send me those two functions and I will give an exact patch.")
        sys.exit(1)
    new = new.replace(old, repl, 1)

shutil.copy(path, str(path) + ".before_kpi_label")
path.write_text(new, encoding="utf-8")
print("Patched app.py (2 edits). Backup: app.py.before_kpi_label")
