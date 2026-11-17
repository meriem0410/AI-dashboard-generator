"""
Tests for scope_catalog_to_dashboard: the date/category filter is narrowed to the
dashboard on screen, so its range matches the charts and it actually filters.

    python -m Modules.Scripts.test_dashboard_filters_scope
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.dashboard_filters import (discover_filter_catalog, scope_catalog_to_dashboard,
                                        _date_columns_of, _parse_dates)

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


# A dataset like the user's: customers carry an (excluded) acquisition_date in
# 2020-2022; loads/trips are operational in 2022-2024.
customers = pd.DataFrame({
    "customer_id": [f"C{i}" for i in range(12)],
    "customer_type": (["Spot", "Contract", "Dedicated"] * 4),
    "annual_revenue_potential": [1000 * (i + 1) for i in range(12)],
    "acquisition_date": pd.to_datetime(
        ["2020-01-10", "2020-06-15", "2020-11-20", "2021-02-01", "2021-05-05",
         "2021-08-08", "2021-10-10", "2021-12-31", "2022-01-01", "2020-03-03",
         "2021-07-07", "2022-02-02"])})
loads = pd.DataFrame({
    "load_id": [f"L{i}" for i in range(12)],
    "customer_id": [f"C{i % 12}" for i in range(12)],
    "load_date": pd.to_datetime(
        ["2022-01-01", "2022-06-01", "2023-01-15", "2023-07-04", "2023-12-31",
         "2024-02-02", "2024-08-08", "2022-11-11", "2023-05-05", "2024-01-01",
         "2023-09-09", "2024-12-12"]),
    "revenue": [100.0 * (i + 1) for i in range(12)]})
data = {"customers": customers, "loads": loads}

relationships = [{"from_table": "loads", "to_table": "customers"}]
catalog = discover_filter_catalog(data, {"relationships": relationships})

print("\n--- the global catalog is dataset-wide (the bug's starting point) ---")
gmin, gmax = catalog["date_dimension"]["min_date"], catalog["date_dimension"]["max_date"]
check("global range reaches into the operational years", gmax >= "2024-01-01", gmax)
check("global range excludes the customer lifecycle date (acquisition_date)",
      all(m["column"] != "acquisition_date" for m in catalog["date_dimension"]["mappings"]),
      catalog["date_dimension"]["mappings"])

print("\n--- a customers-only dashboard ---")
cust_dash = {"results": [
    {"sql": "SELECT date_trunc('month', acquisition_date) AS m, COUNT(*) AS n "
            "FROM customers GROUP BY 1 ORDER BY 1"},
    {"sql": "SELECT customer_type, SUM(annual_revenue_potential) AS r FROM customers GROUP BY 1"},
]}
scoped = scope_catalog_to_dashboard(cust_dash, catalog, data)
dd = scoped["date_dimension"]
check("the date filter now uses the customer date it actually plots",
      [m["column"] for m in dd["mappings"]] == ["acquisition_date"], dd["mappings"])
check("the offered range matches the chart (2020-2022), not the operational years",
      dd["min_date"].startswith("2020") and dd["max_date"] <= "2022-12-31", (dd["min_date"], dd["max_date"]))
check("the category pill only offers the dashboard's table",
      {f["table"] for f in scoped["category_fields"]} == {"customers"},
      [f["id"] for f in scoped["category_fields"]])

print("\n--- an operations dashboard on loads ---")
ops_dash = {"results": [
    {"sql": "SELECT date_trunc('month', load_date) AS m, SUM(revenue) AS r FROM loads GROUP BY 1"},
]}
scoped = scope_catalog_to_dashboard(ops_dash, catalog, data)
dd = scoped["date_dimension"]
check("the loads dashboard filters on load_date", [m["column"] for m in dd["mappings"]] == ["load_date"])
check("its range is the operational years (2022-2024)",
      dd["min_date"].startswith("2022") and dd["max_date"].startswith("2024"), (dd["min_date"], dd["max_date"]))

print("\n--- a dashboard with no date column plotted ---")
nodate = {"results": [{"sql": "SELECT customer_type, COUNT(*) AS n FROM customers GROUP BY 1"}]}
scoped = scope_catalog_to_dashboard(nodate, catalog, data)
check("no date is plotted, so no date filter is offered (instead of a wrong one)",
      scoped["date_dimension"] is None, scoped["date_dimension"])
check("the category filter is still offered", scoped["category_fields"], scoped["category_fields"])

print("\n--- a dashboard across both tables ---")
both = {"results": [
    {"sql": "SELECT date_trunc('month', load_date) AS m, SUM(revenue) FROM loads GROUP BY 1"},
    {"sql": "SELECT date_trunc('month', acquisition_date) AS m, COUNT(*) FROM customers GROUP BY 1"}]}
scoped = scope_catalog_to_dashboard(both, catalog, data)
cols = {(m["table"], m["column"]) for m in scoped["date_dimension"]["mappings"]}
check("both date columns are mapped", cols == {("loads", "load_date"), ("customers", "acquisition_date")}, cols)
check("the combined range spans both (2020-2024)",
      scoped["date_dimension"]["min_date"].startswith("2020")
      and scoped["date_dimension"]["max_date"].startswith("2024"))


print("\n--- regression: a boolean column named with 'time' must not crash (tz-naive) ---")
events = pd.DataFrame({
    "event_id": [f"E{i}" for i in range(6)],
    "load_id": [f"L{i%6}" for i in range(6)],
    "on_time_flag": [True, False, True, False, True, False],     # bool, name has 'time'
    "event_date": pd.to_datetime(["2023-01-01", "2023-02-01", "2023-03-01",
                                  "2023-04-01", "2023-05-01", "2023-06-01"]),
    "model_year": [2015, 2016, 2017, 2018, 2019, 2020]})          # int, name has 'year'
check("_parse_dates on booleans does not raise", _parse_dates(events["on_time_flag"]) is not None)
cols = _date_columns_of(events)
check("the boolean 'on_time_flag' is NOT a date column", "on_time_flag" not in cols, cols)
check("the integer 'model_year' is NOT a date column", "model_year" not in cols, cols)
check("the real 'event_date' IS a date column", "event_date" in cols, cols)
bool_dash = {"results": [{"sql": "SELECT 100.0 * AVG(CASE WHEN on_time_flag THEN 1 ELSE 0 END) AS p FROM events"},
                         {"sql": "SELECT date_trunc('month', event_date) AS m, COUNT(*) FROM events GROUP BY 1"}]}
scoped_ok = scope_catalog_to_dashboard(bool_dash, discover_filter_catalog({"events": events}, {}), {"events": events})
check("scoping a dashboard that uses a boolean flag does not crash",
      scoped_ok["date_dimension"] is not None
      and [m["column"] for m in scoped_ok["date_dimension"]["mappings"]] == ["event_date"],
      scoped_ok["date_dimension"])

print("\n--- robustness: no SQL, bad SQL, empty ---")
check("a dashboard with no SQL is left unchanged", scope_catalog_to_dashboard({"results": []}, catalog, data) is catalog)
check("unparseable SQL does not crash",
      scope_catalog_to_dashboard({"results": [{"sql": "NOT SQL ;;"}]}, catalog, data)["date_dimension"] is None
      or True)
check("a None catalog is returned as-is", scope_catalog_to_dashboard(cust_dash, None, data) is None)

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
