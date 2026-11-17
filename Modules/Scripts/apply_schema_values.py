"""
Modules/Scripts/apply_schema_values.py

Passes the data to build_llm_schema so the schema lists each category column's real
values (one exact edit to Modules/pipeline.py, with a backup). Needs the new
Modules/schema_builder.py from the same package. Safe to run twice.

    python Modules/Scripts/apply_schema_values.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "Modules" / "pipeline.py"
text = path.read_text(encoding="utf-8")

OLD = "    schema = build_llm_schema(profile_dict)\n"
NEW = "    schema = build_llm_schema(profile_dict, data)\n"

if "build_llm_schema(profile_dict, data)" in text:
    print("Already applied: pipeline.py already passes the data to build_llm_schema.")
    sys.exit(0)
if OLD not in text:
    print("Could not find the expected line in pipeline.py. Send me your build_schema "
          "function and I'll give an exact patch.")
    sys.exit(1)
shutil.copy(path, str(path) + ".before_schema_values")
path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
print("Patched pipeline.py. Backup: pipeline.py.before_schema_values")
