"""
Modules/Scripts/test_tools_and_schemas.py

Offline tests for Modules/schemas.py and Modules/tools.py.
No internet, no Groq call, no real data.

Run from the project root:
    python Modules/Scripts/test_tools_and_schemas.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

import pandas as pd

from Modules.engine_duckdb import Database
from Modules.schemas import SQLAnswer, parse_sql_answer
from Modules.tools import make_tools

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def raises(fn):
    try:
        fn()
        return False
    except Exception:
        return True


# ---------------------------------------------------------------------
print("\n--- A. SQLAnswer ---")
check("ok with sql is valid", SQLAnswer(status="ok", sql="SELECT 1;").sql == "SELECT 1;")
check("ok without sql is refused", raises(lambda: SQLAnswer(status="ok")))
check("ok with blank sql is refused", raises(lambda: SQLAnswer(status="ok", sql="   ")))
check("ambiguous needs an assumption",
      raises(lambda: SQLAnswer(status="ambiguous", sql="SELECT 1;")))
check("ambiguous with an assumption is valid",
      SQLAnswer(status="ambiguous", sql="SELECT 1;", assumptions=["best = revenue"]).assumptions
      == ["best = revenue"])
check("unsupported needs a reason", raises(lambda: SQLAnswer(status="unsupported")))
check("unsupported with a reason is valid",
      SQLAnswer(status="unsupported", reason="no such column").sql is None)
check("unsupported must not carry sql",
      raises(lambda: SQLAnswer(status="unsupported", sql="SELECT 1;", reason="x")))
check("blocked with a reason is valid", SQLAnswer(status="blocked", reason="write request").status == "blocked")
check("an unknown status is refused", raises(lambda: SQLAnswer(status="maybe", sql="SELECT 1;")))
check("an unknown field is refused", raises(lambda: SQLAnswer(status="ok", sql="SELECT 1;", color="red")))

check("parse: a bare JSON object",
      parse_sql_answer('{"status": "ok", "sql": "SELECT 1;"}').sql == "SELECT 1;")
check("parse: inside a code fence and extra words",
      parse_sql_answer('Here you go:\n```json\n{"status": "blocked", "reason": "no deletes"}\n```').status == "blocked")
check("parse: text without JSON is refused", raises(lambda: parse_sql_answer("SELECT 1;")))
check("parse: broken JSON is refused", raises(lambda: parse_sql_answer('{"status": "ok", "sql": ')))
check("parse: wrong shape is refused", raises(lambda: parse_sql_answer('{"status": "ok"}')))
check("parse: empty text is refused", raises(lambda: parse_sql_answer("")))

# ---------------------------------------------------------------------
print("\n--- B. tools ---")
customers = pd.DataFrame({"customer_id": [f"C{i}" for i in range(1, 201)],
                          "customer_name": [f"Name {i}" for i in range(1, 201)]})
n = 600
trips = pd.DataFrame({
    "trip_id": range(1, n + 1),
    "customer_id": [f"C{(i % 200) + 1}" for i in range(n)],
    "trip_status": ["completed", "cancelled", "completed"] * (n // 3),
    "dispatch_date": pd.date_range("2022-01-01", periods=n, freq="D"),
    "distance_miles": [100 + (i % 50) for i in range(n)],
    "is_team": [i % 2 == 0 for i in range(n)],
    "notes": [None if i % 4 == 0 else "ok" for i in range(n)],
})
db = Database.from_dataframes({"customers": customers, "trips": trips})
tools = {t.name: t for t in make_tools(db, profile=None)}

check("three tools with the expected names",
      set(tools) == {"profile_tool", "schema_tool", "sql_tool"}, str(list(tools)))
check("every tool has a description for the model",
      all(len(t.description) > 40 for t in tools.values()))

out = json.loads(tools["profile_tool"].invoke({}))
check("profile_tool (no argument) lists both tables", out["ok"] and {t["name"] for t in out["tables"]} == {"customers", "trips"})
trips_entry = next(t for t in out["tables"] if t["name"] == "trips")
check("profile_tool reports the row count", trips_entry["rows"] == 600)
check("profile_tool reports the date coverage",
      trips_entry["date_coverage"]["dispatch_date"][0].startswith("2022-01-01"), str(trips_entry))
check("profile_tool total rows", out["total_rows"] == 800)

out = json.loads(tools["profile_tool"].invoke({"table": "TRIPS"}))
check("profile_tool(table) finds a table whatever the case", out["ok"] and out["table"] == "trips")
check("roles: ids are recognised", "trip_id" in out["roles"]["id"] and "customer_id" in out["roles"]["id"], str(out["roles"]))
check("roles: a number is a measure", "distance_miles" in out["roles"]["measure"], str(out["roles"]))
check("roles: a low-cardinality text is a dimension", "trip_status" in out["roles"]["dimension"], str(out["roles"]))
check("roles: a date is a date", out["roles"]["date"] == ["dispatch_date"], str(out["roles"]))
out_c = json.loads(tools["profile_tool"].invoke({"table": "customers"}))
check("roles: a text with one value per row is a label",
      out_c["roles"].get("label") == ["customer_name"], str(out_c["roles"]))

out = json.loads(tools["schema_tool"].invoke({"table": "trips"}))
cols = {c["name"]: c for c in out["columns"]}
check("schema_tool lists every column", len(cols) == 7, str(list(cols)))
check("schema_tool: text column has samples",
      set(cols["trip_status"]["samples"]) == {"completed", "cancelled"}, str(cols["trip_status"]))
check("schema_tool: number has min and max", cols["distance_miles"]["min"] == 100 and cols["distance_miles"]["max"] == 149)
check("schema_tool: null share is computed", cols["notes"]["null_pct"] == 25.0, str(cols["notes"]["null_pct"]))
check("schema_tool: distinct count is computed", cols["trip_status"]["distinct"] == 2)
check("schema_tool: a boolean gets its values", sorted(cols["is_team"]["samples"]) == [False, True], str(cols["is_team"]))
check("schema_tool output is JSON text", isinstance(tools["schema_tool"].invoke({"table": "trips"}), str))

out = json.loads(tools["schema_tool"].invoke({"table": "nope"}))
check("schema_tool: unknown table gives the list of tables",
      (not out["ok"]) and set(out["tables"]) == {"customers", "trips"}, str(out))

out = json.loads(tools["sql_tool"].invoke({"sql": "SELECT trip_status, COUNT(*) AS n FROM trips GROUP BY trip_status ORDER BY n DESC;"}))
check("sql_tool: a good query returns columns and rows",
      out["ok"] and out["columns"] == ["trip_status", "n"] and out["row_count"] == 2, str(out))
out = json.loads(tools["sql_tool"].invoke({"sql": "SELECT * FROM trips;"}))
check("sql_tool: only the first 5 rows come back",
      out["ok"] and len(out["rows"]) == 5 and out["row_count"] == 600, str(out["row_count"]))
check("sql_tool: dates in rows are JSON text", isinstance(out["rows"][0][3], str), str(out["rows"][0]))

out = json.loads(tools["sql_tool"].invoke({"sql": "DELETE FROM trips;"}))
check("sql_tool: DELETE is refused at stage safety", (not out["ok"]) and out["stage"] == "safety", str(out))
out = json.loads(tools["sql_tool"].invoke({"sql": "SELECT ( FROM trips;"}))
check("sql_tool: a parse error is stage syntax", (not out["ok"]) and out["stage"] == "syntax", str(out))
out = json.loads(tools["sql_tool"].invoke({"sql": "SELECT nope FROM trips;"}))
check("sql_tool: an unknown column is stage schema_validation",
      (not out["ok"]) and out["stage"] == "schema_validation" and "nope" in out["error"], str(out))
out = json.loads(tools["sql_tool"].invoke({"sql": "SELECT * FROM read_csv('/etc/passwd');"}))
check("sql_tool: a file read is refused", (not out["ok"]) and out["stage"] == "safety", str(out))
check("sql_tool: nothing deleted or broken by the attacks",
      json.loads(tools["sql_tool"].invoke({"sql": "SELECT COUNT(*) AS n FROM trips;"}))["rows"][0][0] == 600)

# two sessions never share tools
db2 = Database.from_dataframes({"only_here": pd.DataFrame({"a": [1, 2, 3]})})
tools2 = {t.name: t for t in make_tools(db2)}
out = json.loads(tools2["schema_tool"].invoke({"table": "trips"}))
check("tools of another session cannot see this session's tables", not out["ok"] and out["tables"] == ["only_here"], str(out))

db.close(); db2.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
