"""
Modules/Scripts/apply_date_scope.py

Adds the dashboard-scoped date/category filter to YOUR app.py with two small,
exact edits, WITHOUT replacing the file (so any manual change of yours stays):

  1. import scope_catalog_to_dashboard next to discover_filter_catalog
  2. in render_dashboard, narrow the catalog to the dashboard before the filter bar

    python Modules/Scripts/apply_date_scope.py

Safe to run twice. Writes app.py.before_date_scope first.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "app.py"
text = path.read_text(encoding="utf-8")

EDITS = [
    ("from Modules.dashboard_filters import discover_filter_catalog\n",
     "from Modules.dashboard_filters import discover_filter_catalog, scope_catalog_to_dashboard\n"),
    ("    active_filters = render_filter_bar(dash, catalog)\n",
     "    # Narrow the dataset-wide catalog to THIS dashboard: the date range and the\n"
     "    # category pills then match the panels actually on screen, so the filters bite.\n"
     "    catalog = scope_catalog_to_dashboard(dash, catalog, st.session_state.get(\"data\"))\n"
     "    active_filters = render_filter_bar(dash, catalog)\n"),
]

if "scope_catalog_to_dashboard(dash, catalog" in text:
    print("Already applied: app.py already scopes the catalog to the dashboard.")
    sys.exit(0)

new, applied = text, 0
for old, repl in EDITS:
    if old in new:
        new = new.replace(old, repl, 1)
        applied += 1
    else:
        print("Could not find the expected line:\n  " + old.strip()[:80]
              + "\nYour app.py differs from what I expected. Send me your render_dashboard "
              "function and the import block, and I will give you an exact patch.")
        sys.exit(1)

shutil.copy(path, str(path) + ".before_date_scope")
path.write_text(new, encoding="utf-8")
print(f"Patched app.py ({applied} edits). Backup: app.py.before_date_scope")
