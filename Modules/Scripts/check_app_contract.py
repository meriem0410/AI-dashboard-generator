"""
Modules/Scripts/check_app_contract.py

Checks that every method app.py calls on the database object (db.something(...)) exists on
the Database class in Modules/engine_duckdb.py. It would have caught "'Database' object has
no attribute 'set_filters'" before the app was started.

    python Modules/Scripts/check_app_contract.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Modules.engine_duckdb import Database

source = (ROOT / "app.py").read_text(encoding="utf-8")
called = sorted(set(re.findall(r"\bdb\.([A-Za-z_]\w*)\s*\(", source)))
# attributes that are set on the object at runtime (not methods)
missing = [name for name in called if not hasattr(Database, name)]
print("methods app.py calls on db:", ", ".join(called) or "(none)")
if missing:
    print("MISSING on Database:", ", ".join(missing))
    sys.exit(1)
print("OK: every method app.py calls exists on Database.")
