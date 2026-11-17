"""
Modules/Scripts/fix_engine_wrapper.py

Applies the one real change of the engine fix (a query ending in a '-- comment' no longer breaks
the wrapper) to YOUR Modules/engine_duckdb.py, WITHOUT touching anything else in the file
(your set_filters and the rest stay as they are).

    python Modules/Scripts/fix_engine_wrapper.py                      # patches Modules/engine_duckdb.py
    python Modules/Scripts/fix_engine_wrapper.py path/to/engine.py

Safe to run twice. It writes <file>.before_wrapper_fix first.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Modules" / "engine_duckdb.py"
text = path.read_text(encoding="utf-8")

CHANGES = [
    ("wrapped = f'SELECT * FROM ({_strip(sql)}) AS q LIMIT {int(row_cap)}'",
     "# newlines around the query: a trailing -- comment must not swallow the closing parenthesis\n"
     "            wrapped = f'SELECT * FROM (\\n{_strip(sql)}\\n) AS q LIMIT {int(row_cap)}'"),
    ("'DESCRIBE SELECT * FROM (' + _strip(sql) + ') AS q'",
     "'DESCRIBE SELECT * FROM (\\n' + _strip(sql) + '\\n) AS q'"),
]

new, done = text, []
for old, repl in CHANGES:
    if old in new:
        new = new.replace(old, repl)
        done.append(old[:45])
if not done:
    already = "\\n) AS q" in text
    print("Nothing to change: " + ("the fix is already there." if already else
          "the expected lines were not found. Send me the run() and bind_check() functions of your file."))
    sys.exit(0)
shutil.copy(path, str(path) + ".before_wrapper_fix")
path.write_text(new, encoding="utf-8")
print(f"Patched {path}: {len(done)} line(s) changed. Backup: {path}.before_wrapper_fix")
print("set_filters present:", "def set_filters" in new)
