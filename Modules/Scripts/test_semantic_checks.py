"""
Modules/Scripts/test_semantic_checks.py

Offline tests for Modules/semantic_checks.py. No internet, no Groq call.

    python Modules/Scripts/test_semantic_checks.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

import pandas as pd

from Modules.engine_duckdb import Database
from Modules.semantic_checks import check_result, format_problem

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


fuel = pd.DataFrame({
    "fuel_id": range(1, 91),
    "purchase_date": pd.date_range("2024-10-04", periods=90, freq="D"),   # ends 2025-01-01
    "total_cost": [100.0 + i for i in range(90)],
})
loads = pd.DataFrame({
    "load_id": range(1, 25),
    # month starts of 2023 and 2024, the last one moved to 2024-12-31 (the data ends there)
    "load_date": list(pd.date_range("2023-01-01", periods=23, freq="MS")) + [pd.Timestamp("2024-12-31")],
    "revenue": [500.0 + i for i in range(24)],
})
drivers = pd.DataFrame({"driver_id": [f"D{i}" for i in range(1, 21)],
                        "first_name": [f"Name{i}" for i in range(1, 21)],
                        "last_name": ["X"] * 20})
trips = pd.DataFrame({"trip_id": range(1, 41), "driver_id": [f"D{(i % 20) + 1}" for i in range(40)],
                      "miles": [100 + i for i in range(40)]})
db = Database.from_dataframes({"fuel": fuel, "loads": loads, "drivers": drivers, "trips": trips})


def issues(question, sql, kind=None, constraints=None):
    df = db.run(sql)
    return check_result(question, kind, constraints, sql, df, db)


def codes(found, severity=None):
    return {i["code"] for i in found if severity is None or i["severity"] == severity}


print("\n--- ranking ---")
by_driver = "SELECT d.driver_id, d.first_name, SUM(t.miles) AS total_miles FROM drivers d JOIN trips t USING (driver_id) GROUP BY ALL ORDER BY total_miles DESC"
check("best drivers without LIMIT: missing_limit",
      "missing_limit" in codes(issues("Who are our best drivers?", by_driver + ";"), "error"))
check("best drivers with LIMIT 10: no ranking problem",
      not ({"missing_limit", "too_many_rows"} & codes(issues("Who are our best drivers?", by_driver + " LIMIT 10;"))))
check("top 5 but 8 rows: too_many_rows",
      "too_many_rows" in codes(issues("Top 5 drivers by miles", by_driver + " LIMIT 8;")))
check("'per customer' with 'highest' is not a ranking request",
      "missing_limit" not in codes(issues("highest revenue per driver", by_driver + ";")))
check("planner constraint top_n=3 without LIMIT: missing_limit",
      "missing_limit" in codes(issues("drivers by miles", by_driver + ";",
                                      constraints=SimpleNamespace(top_n=3))))

print("\n--- names next to ids ---")
check("an id without a name, although drivers has one: missing_name",
      "missing_name" in codes(issues("miles per driver",
                                     "SELECT driver_id, SUM(miles) AS total_miles FROM trips GROUP BY driver_id;", kind="bar")))
msg = next(i["message"] for i in issues("miles per driver", "SELECT driver_id, SUM(miles) AS total_miles FROM trips GROUP BY driver_id;")
           if i["code"] == "missing_name")
check("the message names the table and its columns", "drivers" in msg and "first_name" in msg, msg)
check("an id with a name: fine",
      "missing_name" not in codes(issues("miles per driver", by_driver + " LIMIT 5;")))
check("an id with no name table anywhere: fine",
      "missing_name" not in codes(issues("trips list", "SELECT trip_id, miles FROM trips;", kind="table")))
check("a KPI is never asked for a name",
      "missing_name" not in codes(issues("how many", "SELECT COUNT(*) AS n FROM trips;", kind="kpi")))

print("\n--- result shape ---")
check("a KPI with 2 rows: kpi_shape error",
      "kpi_shape" in codes(issues("x", "SELECT miles FROM trips LIMIT 2;", kind="kpi"), "error"))
check("a KPI with one number: fine",
      "kpi_shape" not in codes(issues("x", "SELECT SUM(miles) AS total_miles FROM trips;", kind="kpi")))
check("a line chart without a time column: line_needs_time error",
      "line_needs_time" in codes(issues("x", "SELECT driver_id, SUM(miles) AS m FROM trips GROUP BY 1;", kind="line"), "error"))
check("a line chart with a date column: fine",
      "line_needs_time" not in codes(issues("x", "SELECT date_trunc('month', load_date) AS month, SUM(revenue) AS r FROM loads GROUP BY 1 ORDER BY 1;", kind="line")))
check("a bar chart with one bar: warning only",
      codes(issues("x", "SELECT 'a' AS g, COUNT(*) AS n FROM trips;", kind="bar")) == {"single_category"})
check("a pie with 20 slices: warning",
      "too_many_slices" in codes(issues("x", "SELECT driver_id, COUNT(*) AS n FROM trips GROUP BY 1;", kind="pie"), "warning"))
check("no kind: no shape check", not codes(issues("x", "SELECT miles FROM trips LIMIT 2;", kind=None), "error") & {"kpi_shape"})

print("\n--- partial period ---")
monthly_fuel = "SELECT date_trunc('month', purchase_date) AS month, SUM(total_cost) AS spend FROM fuel GROUP BY 1 ORDER BY 1;"
found = issues("monthly fuel spend", monthly_fuel, kind="line")
check("fuel data ends on 2025-01-01: the last month is partial", "partial_period" in codes(found, "warning"), str(found))
check("the note says which month and when the data ends",
      any("2025-01" in i["message"] and "2025-01-01" in i["message"] for i in found), str([i["message"] for i in found]))
check("a partial period is a warning, never an error", "partial_period" not in codes(found, "error"))
monthly_loads = "SELECT date_trunc('month', load_date) AS month, SUM(revenue) AS r FROM loads GROUP BY 1 ORDER BY 1;"
check("loads end in December 2024: no partial period",
      "partial_period" not in codes(issues("monthly revenue", monthly_loads, kind="line")))
check("yearly totals ending in a complete year: fine",
      "partial_period" not in codes(issues("yearly revenue", "SELECT year(load_date) AS year, SUM(revenue) AS r FROM loads GROUP BY 1 ORDER BY 1;")))
check("a year column ending in 2025 over data that stops on 2025-01-01: partial",
      "partial_period" in codes(issues("yearly fuel", "SELECT year(purchase_date) AS year, SUM(total_cost) AS c FROM fuel GROUP BY 1 ORDER BY 1;")))

print("\n--- hard-coded dates ---")
check("a date outside the data: warning",
      "date_outside_coverage" in codes(issues("x", "SELECT SUM(revenue) AS r FROM loads WHERE load_date >= '2026-05-01';"), "warning"))
check("a date inside the data: fine",
      "date_outside_coverage" not in codes(issues("x", "SELECT SUM(revenue) AS r FROM loads WHERE load_date >= '2024-06-01';")))

print("\n--- robustness ---")
check("garbage SQL does not crash the checks",
      isinstance(check_result("x", "bar", None, "not sql at all", pd.DataFrame({"a": [1]}), db), list))
problem = format_problem([{"code": "a", "severity": "error", "message": "FIX THIS"},
                          {"code": "b", "severity": "warning", "message": "JUST A NOTE"}])
check("format_problem carries errors only", "FIX THIS" in problem and "JUST A NOTE" not in problem)

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
