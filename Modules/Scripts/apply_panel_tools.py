"""
Modules/Scripts/apply_panel_tools.py

Adds the per-panel Edit / Remove buttons (four exact edits to app.py, with a backup).
Needs the "Modify or ask" box (apply_followup_bar.py) already applied. Safe to run twice.

    python Modules/Scripts/apply_panel_tools.py
"""
import shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "app.py"
text = path.read_text(encoding="utf-8")
PAIRS = [["from Modules.followup import classify_followup, apply_followup, pin_panel", "from Modules.followup import classify_followup, apply_followup, pin_panel\nfrom Modules.dashboard_ops import remove_panel"], ["def render_dashboard(dash):\n    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)", "def _panel_tools(dash, index):\n    \"\"\"Edit / Remove controls shown under one panel.\"\"\"\n    edit_col, remove_col, _ = st.columns([1, 1, 3])\n    if edit_col.button(\"Edit\", key=f\"edit_btn_{index}\", help=\"Refine this panel\",\n                       use_container_width=True):\n        st.session_state[\"editing_panel\"] = index\n        st.rerun()\n    if remove_col.button(\"Remove\", key=f\"del_btn_{index}\", help=\"Remove this panel\",\n                         use_container_width=True):\n        try:\n            removed = remove_panel(dash, index)\n            st.session_state[\"dashboard_dirty\"] = True\n            st.session_state.pop(\"filtered_dashboard_cache\", None)\n            flash(\"success\", f\"Removed \u201c{removed['item']['title']}\u201d. Click Save to keep it.\")\n        except Exception as exc:\n            flash(\"error\", f\"Couldn't remove the panel: {exc}\")\n        st.rerun()\n\n\ndef _panel_edit_input(dash, index):\n    \"\"\"Inline 'how should I change this panel?' form, shown in place of a panel\n    when its Edit button was pressed.\"\"\"\n    schema = st.session_state.get(\"schema\")\n    db = st.session_state.get(\"db\")\n    item = dash[\"results\"][index][\"item\"]\n    st.markdown(f\"**Refine:** {html.escape(item['title'])}\")\n    with st.form(f\"edit_form_{index}\", clear_on_submit=True):\n        instruction = st.text_input(\n            \"Change\", label_visibility=\"collapsed\",\n            placeholder=\"e.g. make it top 10 \u00b7 show as a line \u00b7 as a percentage\")\n        apply_col, cancel_col = st.columns(2)\n        apply_it = apply_col.form_submit_button(\"Apply\", type=\"primary\", use_container_width=True)\n        cancel = cancel_col.form_submit_button(\"Cancel\", use_container_width=True)\n    if cancel:\n        st.session_state.pop(\"editing_panel\", None)\n        st.rerun()\n    if apply_it and instruction.strip():\n        try:\n            with st.spinner(\"Updating the panel...\"):\n                action = classify_followup(\n                    f'Change the panel \"{item[\"title\"]}\" so that: {instruction.strip()}', dash, schema)\n                action.operation = \"edit\"                       # this is always an edit of THIS panel\n                action.target = item.get(\"id\") or item[\"title\"]\n                if not action.question:\n                    action.question = f'{item[\"question\"]} ({instruction.strip()})'\n                result = apply_followup(action, dash, schema, db)\n        except Exception as exc:\n            flash(\"error\", f\"Couldn't update the panel: {exc}\")\n        else:\n            st.session_state[\"dashboard_dirty\"] = True\n            st.session_state.pop(\"filtered_dashboard_cache\", None)\n            flash(\"success\" if result[\"ok\"] else \"info\", result[\"message\"])\n        st.session_state.pop(\"editing_panel\", None)\n        st.rerun()\n\n\ndef render_dashboard(dash):\n    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)"], ["                with st.container(border=True, key=f\"card_kpi_{index}\"):\n                    render_kpi(result, trend)", "                with st.container(border=True, key=f\"card_kpi_{index}\"):\n                    if st.session_state.get(\"editing_panel\") == index:\n                        _panel_edit_input(dash, index)\n                    else:\n                        render_kpi(result, trend)\n                        _panel_tools(dash, index)"], ["                with st.container(border=True, key=f\"card_panel_{index}\"):\n                    render_item(result, index)", "                with st.container(border=True, key=f\"card_panel_{index}\"):\n                    if st.session_state.get(\"editing_panel\") == index:\n                        _panel_edit_input(dash, index)\n                    else:\n                        render_item(result, index)\n                        _panel_tools(dash, index)"]]
if "_panel_tools" in text:
    print("Already applied: app.py already has the per-panel buttons.")
    sys.exit(0)
if "render_followup_bar" not in text:
    print("Apply the Modify/ask box first (apply_followup_bar.py), then run this.")
    sys.exit(1)
new = text
for old, repl in PAIRS:
    if old not in new:
        print("Could not find an expected block in app.py. Send me render_dashboard and I'll give an exact patch.")
        sys.exit(1)
    new = new.replace(old, repl, 1)
shutil.copy(path, str(path) + ".before_panel_tools")
path.write_text(new, encoding="utf-8")
print("Patched app.py (4 edits). Backup: app.py.before_panel_tools")
