"""
Modules/Scripts/apply_followup_bar.py

Adds the "Modify or ask" box under the dashboard (three exact edits to app.py, with a
backup; your file is not replaced). Needs Modules/followup.py, dashboard_ops.py and the
rest of day 8. Safe to run twice.

    python Modules/Scripts/apply_followup_bar.py
"""
import shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "app.py"
text = path.read_text(encoding="utf-8")
PAIRS = [["from Modules.kpi_trends import kpi_trend, sparkline_svg, format_delta", "from Modules.kpi_trends import kpi_trend, sparkline_svg, format_delta\nfrom Modules.followup import classify_followup, apply_followup, pin_panel"], ["def render_dashboard(dash):\n    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)", "def _render_answer_panel(panel):\n    \"\"\"Show a transient 'ask' answer as its natural KPI / chart / table.\"\"\"\n    if (panel.get(\"item\") or {}).get(\"kind\") == \"kpi\":\n        render_kpi(panel)\n    else:\n        render_item(panel, 9999)\n\n\ndef render_followup_bar(dash):\n    \"\"\"Under the dashboard: one box to add a chart, refine or remove a panel,\n    reorder, or ask a question. Modifications update the in-session dashboard;\n    the user saves with the existing Save button. An 'ask' is answered here and\n    can be pinned onto the dashboard.\"\"\"\n    schema = st.session_state.get(\"schema\")\n    db = st.session_state.get(\"db\")\n    if schema is None or db is None:\n        return\n\n    st.divider()\n    st.markdown(\"#### Modify or ask\")\n\n    pending = st.session_state.get(\"followup_answer\")\n    if pending:\n        with st.container(border=True):\n            _render_answer_panel(pending)\n            add_col, dismiss_col, _ = st.columns([1.3, 1, 4])\n            if add_col.button(\"\uff0b Add to dashboard\", key=\"pin_followup\", use_container_width=True):\n                pin_panel(dash, pending)\n                st.session_state.pop(\"followup_answer\", None)\n                st.session_state[\"dashboard_dirty\"] = True\n                st.session_state.pop(\"filtered_dashboard_cache\", None)\n                flash(\"success\", \"Added to the dashboard. Click Save to keep it.\")\n                st.rerun()\n            if dismiss_col.button(\"Dismiss\", key=\"dismiss_followup\", use_container_width=True):\n                st.session_state.pop(\"followup_answer\", None)\n                st.rerun()\n\n    with st.form(\"followup_form\", clear_on_submit=True):\n        text = st.text_input(\n            \"Your request\", label_visibility=\"collapsed\",\n            placeholder=\"e.g. add a KPI for total fuel cost \u00b7 make the top 5 a top 10 \u00b7 \"\n                        \"remove the pie \u00b7 what is the revenue for Spot?\")\n        submitted = st.form_submit_button(\"Send\", type=\"primary\")\n\n    if not (submitted and text.strip()):\n        return\n    try:\n        with st.spinner(\"Working on it...\"):\n            action = classify_followup(text.strip(), dash, schema)\n            result = apply_followup(action, dash, schema, db)\n    except Exception as exc:\n        flash(\"error\", f\"I couldn't handle that: {exc}\")\n        st.rerun()\n        return\n\n    if result[\"operation\"] == \"ask\":\n        if result.get(\"panel\") is not None and result[\"panel\"].get(\"df\") is not None:\n            st.session_state[\"followup_answer\"] = result[\"panel\"]\n        else:\n            flash(\"info\", result[\"message\"])\n    elif result[\"ok\"]:\n        st.session_state[\"dashboard_dirty\"] = True\n        st.session_state.pop(\"filtered_dashboard_cache\", None)\n        flash(\"success\", result[\"message\"])\n    else:\n        flash(\"info\", result[\"message\"])          # ambiguous, blocked or unsupported\n    st.rerun()\n\n\ndef render_dashboard(dash):\n    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)"], ["    render_panel_details(results)\n\n\n# ============================================================\n# SESSION: DATASET STATE", "    render_panel_details(results)\n    render_followup_bar(dash)\n\n\n# ============================================================\n# SESSION: DATASET STATE"]]

if "render_followup_bar" in text:
    print("Already applied: app.py already has the Modify/ask box.")
    sys.exit(0)
new = text
for old, repl in PAIRS:
    if old not in new:
        print("Could not find an expected block in app.py. Send me your render_dashboard "
              "function and the imports, and I will give an exact patch.")
        sys.exit(1)
    new = new.replace(old, repl, 1)
shutil.copy(path, str(path) + ".before_followup_bar")
path.write_text(new, encoding="utf-8")
print("Patched app.py (3 edits). Backup: app.py.before_followup_bar")
