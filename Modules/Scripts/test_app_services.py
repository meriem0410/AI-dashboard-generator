"""
Modules/Scripts/test_app_services.py

Offline tests: a dashboard becomes a spec, survives storage, and is rebuilt
from SQL alone. Uses a real in-memory DuckDB Database and no model.

    python Modules/Scripts/test_app_services.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

import pandas as pd

from Modules import library as lib
from Modules.app_services import (dashboard_to_spec, default_dataset_name, suggest_dataset_name, infer_domain,
                                  metadata_from_data, spec_to_dashboard)
from Modules.engine_duckdb import Database
from Modules.sql_executor import execute_sql
from Modules.storage import LocalStorage

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


trips = pd.DataFrame({"trip_id": range(1, 7), "miles": [10, 20, 30, 40, 50, 60.0],
                      "dispatch_date": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-02-02",
                                                       "2024-02-20", "2024-03-03", "2024-03-30"])})
db = Database.from_dataframes({"trips": trips})

df_total = db.run("SELECT SUM(miles) AS total_miles FROM trips;")
dash = {
    "question": "Analyse trips",
    "plan": {"title": "Trips overview", "focus": "Distance", "items": []},
    "results": [
        {"item": {"id": "p1", "title": "Total miles", "question": "total miles", "kind": "kpi"},
         "df": df_total, "error": None, "sql": "SELECT SUM(miles) AS total_miles FROM trips;",
         "attempts": 2, "status": "ambiguous", "assumptions": ["miles = distance driven"],
         "notes": ["a note"], "stage": "completed", "path": ["generate"]},
        {"item": {"id": "p2", "title": "Satisfaction", "question": "driver satisfaction", "kind": "bar"},
         "df": None, "error": "the schema has no satisfaction score", "sql": None,
         "attempts": 1, "status": "unsupported", "assumptions": [], "notes": [], "stage": "unsupported"},
    ],
    "unsupported": [{"request": "satisfaction", "reason": "no such column"}],
    "blocked": [],
}
filters = {"date": {"start": "2024-01-01", "end": "2024-02-29", "mappings": [{"table": "trips", "column": "dispatch_date"}]}}

spec = dashboard_to_spec(dash, filters)
check("the spec is JSON-able", json.loads(json.dumps(spec)) == spec)
check("result tables are not stored", all("df" not in p for p in spec["panels"]))
check("the filters are kept", spec["filters"] == filters)
check("sql, notes and assumptions are kept",
      spec["panels"][0]["sql"].startswith("SELECT SUM") and spec["panels"][0]["assumptions"] == ["miles = distance driven"])

with tempfile.TemporaryDirectory() as tmp:
    store = LocalStorage(tmp)
    did = lib.save_dataset(store, "u1", "Trips", {"trips": trips}, {}, "SCHEMA")
    dash_id = lib.save_dashboard(store, "u1", did, "Trips overview", spec)
    rec = lib.load_dashboard(store, "u1", dash_id)

rebuilt = spec_to_dashboard(rec["spec"], lambda sql: execute_sql(sql, db))
check("the rebuilt dashboard has the same panels", len(rebuilt["results"]) == 2)
check("the KPI is recomputed from SQL", float(rebuilt["results"][0]["df"].iloc[0, 0]) == 210.0)
check("a failed panel stays failed with its reason",
      rebuilt["results"][1]["df"] is None and rebuilt["results"][1]["stage"] == "unsupported")
check("the plan and unsupported lists are restored",
      rebuilt["plan"]["title"] == "Trips overview" and rebuilt["unsupported"][0]["request"] == "satisfaction")
check("render needs: question, plan title/focus, results with item",
      rebuilt["question"] == "Analyse trips" and "focus" in rebuilt["plan"]
      and all("item" in r for r in rebuilt["results"]))

bad = json.loads(json.dumps(spec))
bad["panels"][0]["sql"] = "SELECT nope FROM trips;"
r = spec_to_dashboard(bad, lambda sql: execute_sql(sql, db))["results"][0]
check("a saved query that now fails is reported, not hidden",
      r["df"] is None and r["stage"] == "execution" and "could not be re-run" in r["error"], str(r["error"]))

empty = json.loads(json.dumps(spec))
empty["panels"][0]["sql"] = "SELECT * FROM trips WHERE miles < 0;"
r = spec_to_dashboard(empty, lambda sql: execute_sql(sql, db))["results"][0]
check("a saved query that returns nothing is reported", r["df"] is None and "no data" in r["error"])

check("an empty spec rebuilds to an empty dashboard", spec_to_dashboard({}, lambda s: None)["results"] == [])
check("metadata", metadata_from_data({"trips": trips}) == {"table_count": 1, "total_rows": 6, "total_columns": 3})
check("one file name", default_dataset_name(["fleet.csv"]) == "fleet")
check("several file names", default_dataset_name(["a.csv", "b.csv", "c.csv"]) == "a + 2 more")

check("name: logistics from tables", suggest_dataset_name(["trips.csv","vehicles.csv","drivers.csv","fuel_logs.csv"]) == "Logistics")
check("name: sales from tables", suggest_dataset_name(["customers.csv","orders.csv","products.csv"]) == "Sales")
check("name: hr from tables", suggest_dataset_name(["employees.xlsx","departments.xlsx"]) == "HR")
check("name: unknown falls back", suggest_dataset_name(["foo.csv","bar.csv"]) == "foo + 1 more")
check("name: single unknown keeps file name", suggest_dataset_name(["misc_x.csv"]) == "misc_x")
check("name: columns can decide", suggest_dataset_name(["a.csv","b.csv"], ["patient_id","diagnosis","doctor"]) == "Healthcare")
check("name: one weak column hit is not enough", infer_domain(["a"], ["price"])[0] is None)
check("name: plural stems", infer_domain(["Deliveries"])[0] == "Logistics")

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
