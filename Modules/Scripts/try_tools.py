"""
Modules/Scripts/try_tools.py

Calls the three tools by hand on a real dataset, so you can SEE what a
language model will receive. No Groq call.

Run from the project root (virtual environment active):
    python Modules/Scripts/try_tools.py Logistics
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

from Modules.pipeline import ingest, open_database
from Modules.tools import make_tools

name = sys.argv[1] if len(sys.argv) > 1 else "Logistics"
data = ingest(str(ROOT / "data" / name), source_type="folder")["data"]
db = open_database(data)
tools = {t.name: t for t in make_tools(db)}


def show(title, text):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    try:
        print(json.dumps(json.loads(text), indent=2, ensure_ascii=False)[:2500])
    except Exception:
        print(text[:2500])


first_table = next(iter(db.tables))
show("profile_tool()  -> the whole dataset", tools["profile_tool"].invoke({}))
show(f"profile_tool('{first_table}')  -> column roles", tools["profile_tool"].invoke({"table": first_table}))
show(f"schema_tool('{first_table}')  -> column details", tools["schema_tool"].invoke({"table": first_table}))
show(f"sql_tool  -> a good query",
     tools["sql_tool"].invoke({"sql": f"SELECT COUNT(*) AS n FROM {first_table};"}))
show("sql_tool  -> a DELETE (must be refused)",
     tools["sql_tool"].invoke({"sql": f"DELETE FROM {first_table};"}))
show("sql_tool  -> an unknown column (the error the model will read)",
     tools["sql_tool"].invoke({"sql": f"SELECT no_such_column FROM {first_table};"}))
for table in ["fuel_purchases", "trips", "loads"]:
    show(
        f"profile_tool('{table}') -> column roles",
        tools["profile_tool"].invoke({"table": table})
    )

    show(
        f"schema_tool('{table}') -> column details",
        tools["schema_tool"].invoke({"table": table})
    )
db.close()
