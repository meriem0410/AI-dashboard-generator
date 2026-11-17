"""
Tests for Database.set_filters (the filter views the dashboard relies on).

    python -m Modules.Scripts.test_engine_filters
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.engine_duckdb import Database

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


loads = pd.DataFrame({
    "load_id": [f"L{i}" for i in range(10)],
    "customer_type": ["Spot", "Contract", "Spot", "Dedicated", "Contract",
                      "Spot", "Contract", "Dedicated", "Spot", "Contract"],
    "load_date": pd.to_datetime(["2022-06-01", "2023-01-15", "2023-03-20", "2023-07-04",
                                 "2023-12-31", "2024-02-02", "2022-11-11", "2023-05-05",
                                 "2024-08-08", "2023-09-09"]),
    "revenue": [100.0 * (i + 1) for i in range(10)]})
trips = pd.DataFrame({"trip_id": [f"T{i}" for i in range(10)],
                      "load_id": [f"L{i}" for i in range(10)],
                      "dispatch_date": loads["load_date"]})
db = Database.from_dataframes({"loads": loads, "trips": trips})


def count(name):
    return db.con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]


print("\n--- no filter ---")
check("empty filters leave every row", db.set_filters({}) == {} and count("loads") == 10)
check("filters property reflects state", db.filters == {})

print("\n--- category filter ---")
s = db.set_filters({"category": {"table": "loads", "column": "customer_type", "values": ["Spot", "Dedicated"]}})
check("only the chosen categories remain", count("loads") == 6)
check("the summary reports before and after", s["loads"] == {"before": 10, "after": 6}, s)
check("a table without the column is untouched and absent from the summary",
      count("trips") == 10 and "trips" not in s)

print("\n--- date filter on several tables ---")
s = db.set_filters({"date": {"start": "2023-01-01", "end": "2023-12-31",
                             "mappings": [{"table": "loads", "column": "load_date"},
                                          {"table": "trips", "column": "dispatch_date"}]}})
check("loads keeps only 2023 (end day inclusive)", count("loads") == 6, count("loads"))
check("the last day of the range is kept", db.con.execute(
    "SELECT COUNT(*) FROM loads WHERE load_date = DATE '2023-12-31'").fetchone()[0] == 1)
check("the date filter applies to every mapped table", count("trips") == 6)
check("both tables appear in the summary", set(s) == {"loads", "trips"})

print("\n--- date and category together ---")
s = db.set_filters({
    "date": {"start": "2023-01-01", "end": "2023-12-31",
             "mappings": [{"table": "loads", "column": "load_date"}]},
    "category": {"table": "loads", "column": "customer_type", "values": ["Contract"]}})
check("both conditions apply (2023 AND Contract)", count("loads") == 3, count("loads"))

print("\n--- restore ---")
db.set_filters({})
check("clearing restores every row", count("loads") == 10 and count("trips") == 10)
check("clear_filters is a shortcut", db.set_filters({"category": {"table": "loads", "column": "customer_type",
      "values": ["Spot"]}}) and db.clear_filters() == {} and count("loads") == 10)

print("\n--- stored SQL re-runs on filtered views ---")
db.set_filters({"category": {"table": "loads", "column": "customer_type", "values": ["Contract"]}})
total = db.run("SELECT SUM(revenue) AS r FROM loads")["r"][0]
check("a saved aggregate now sees only filtered rows",
      total == loads[loads.customer_type == "Contract"]["revenue"].sum(), total)

print("\n--- safety: a value with a quote cannot break out ---")
tricky = pd.DataFrame({"name": ["O'Brien", "normal", "x"], "v": [1, 2, 3]})
db2 = Database.from_dataframes({"t": tricky})
db2.set_filters({"category": {"table": "t", "column": "name", "values": ["O'Brien"]}})
check("a single quote in a value is handled", db2.con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1)

print("\n--- an unknown column is ignored, not fatal ---")
s = db.set_filters({"category": {"table": "loads", "column": "no_such_col", "values": ["x"]}})
check("a filter on a missing column changes nothing", s == {} and count("loads") == 10)

print("\n--- the guard still blocks model SQL after filtering ---")
db.set_filters({"category": {"table": "loads", "column": "customer_type", "values": ["Spot"]}})
blocked = False
try:
    db.run("DELETE FROM loads")
except Exception:
    blocked = True
check("writes are still refused on filtered views", blocked)

db.close()
db2.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
