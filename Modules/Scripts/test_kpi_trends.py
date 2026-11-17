"""
Tests for Modules/kpi_trends.py and Database.run_with_filters.

    python -m Modules.Scripts.test_kpi_trends
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.engine_duckdb import Database
from Modules.kpi_trends import (color_for, direction_for_metric, format_delta,
                                kpi_trend, period_windows, sparkline_svg)

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


print("\n--- period windows ---")
gran, w = period_windows("2020-01-01", "2024-12-31")
check("a multi-year span uses yearly periods", gran == "year" and [l for l, _ in w] == ["2020", "2021", "2022", "2023", "2024"], w)
gran, w = period_windows("2023-01-10", "2023-08-20")
check("a within-year span uses monthly periods", gran == "month" and len(w) == 8, (gran, len(w)))
check("windows are capped", len(period_windows("2000-01-01", "2024-12-31", max_periods=5)[1]) == 5)
check("an empty span yields nothing", period_windows("2024-01-01", "2020-01-01")[1] == [])

print("\n--- direction and colour ---")
check("cost is lower-better", direction_for_metric("Total Maintenance Cost") == "lower_better")
check("revenue is higher-better", direction_for_metric("Total Revenue") == "higher_better")
check("accidents are lower-better", direction_for_metric("At-fault accident rate") == "lower_better")
check("'average' is not mistaken for the neutral word 'age'",
      direction_for_metric("Average Revenue per Customer") == "higher_better")
check("'related' is not mistaken for 'late'", direction_for_metric("Related revenue") == "higher_better")
check("a real 'age' metric is still neutral", direction_for_metric("Average truck age") == "neutral")
check("a real 'late' metric is still lower-better", direction_for_metric("Late deliveries") == "lower_better")
check("improving revenue is green", color_for(8.0, "higher_better") == "green")
check("rising cost is red", color_for(8.0, "lower_better") == "red")
check("falling cost is green", color_for(-8.0, "lower_better") == "green")
check("a tiny change is amber", color_for(0.3, "higher_better") == "amber")
check("no percentage is neutral", color_for(None, "higher_better") == "neutral")

print("\n--- run_with_filters leaves the views untouched ---")
loads = pd.DataFrame({
    "load_id": [f"L{i}" for i in range(9)],
    "load_date": pd.to_datetime(["2022-03-01", "2022-07-01", "2023-02-01", "2023-08-01",
                                 "2023-11-01", "2024-01-01", "2024-05-01", "2024-09-01", "2024-12-01"]),
    "revenue": [100, 100, 200, 200, 200, 300, 300, 300, 300]})
db = Database.from_dataframes({"loads": loads})
db.set_filters({"category": {"table": "loads", "column": "load_id", "values": ["L0"]}})  # some active filter
before = db.con.execute("SELECT COUNT(*) FROM loads").fetchone()[0]
out = db.run_with_filters("SELECT SUM(revenue) AS r FROM loads",
                          {"date": {"start": "2023-01-01", "end": "2023-12-31",
                                    "mappings": [{"table": "loads", "column": "load_date"}]}})
after = db.con.execute("SELECT COUNT(*) FROM loads").fetchone()[0]
check("the windowed query sees only its period", out["r"].iloc[0] == 600, out["r"].iloc[0])
check("the active filter is restored afterwards (view unchanged)", before == after == 1, (before, after))
db.clear_filters()

print("\n--- a full KPI trend ---")
date_dim = {"min_date": "2022-01-01", "max_date": "2024-12-31",
            "mappings": [{"table": "loads", "column": "load_date"}]}
run_window = lambda f: db.run_with_filters("SELECT SUM(revenue) AS r FROM loads", f)
trend = kpi_trend(run_window, "SELECT SUM(revenue) AS r FROM loads", date_dim, title="Total Revenue")
check("the trend has one value per year", [p["label"] for p in trend["series"]] == ["2022", "2023", "2024"])
check("per-year revenue is correct", [p["value"] for p in trend["series"]] == [200, 600, 1200],
      [p["value"] for p in trend["series"]])
check("current and previous are the last two years", trend["current"] == 1200 and trend["previous"] == 600)
check("the delta percentage is right (+100%)", abs(trend["delta_pct"] - 100.0) < 1e-6)
check("rising revenue is green", trend["color"] == "green")
check("the delta names the comparison period", trend["period_label"] == "2023")

print("\n--- degrade gracefully ---")
check("no date dimension -> no trend", kpi_trend(run_window, "SELECT 1", None) is None)
flat = kpi_trend(lambda f: db.run_with_filters("SELECT COUNT(*) AS n FROM loads WHERE 1=0", f),
                 "SELECT COUNT(*) AS n FROM loads WHERE 1=0", date_dim)
check("a metric that never changes gets no (misleading) trend", flat is None)
# a KPI on a table the date doesn't map: every period identical -> no trend
nodate_dim = {"min_date": "2022-01-01", "max_date": "2024-12-31",
              "mappings": [{"table": "other", "column": "d"}]}
const = kpi_trend(lambda f: db.run_with_filters("SELECT SUM(revenue) AS r FROM loads", f),
                  "SELECT SUM(revenue) AS r FROM loads", nodate_dim)
check("a KPI whose table has no mapped date shows no delta", const is None)

print("\n--- completeness guard (the fix) ---")
from Modules.kpi_trends import _coverage, complete_windows

# operational: three full years -> all complete -> a delta shows
op_dim = {"min_date": "2022-01-01", "max_date": "2024-12-12",
          "mappings": [{"table": "loads", "column": "load_date"}]}
_, w = period_windows(op_dim["min_date"], op_dim["max_date"])
cw = complete_windows(w, pd.Timestamp(op_dim["min_date"]), pd.Timestamp(op_dim["max_date"]))
check("a near-full trailing year is kept (2024 to Dec 12)", [l for l, _ in cw] == ["2022", "2023", "2024"], [l for l, _ in cw])
op_trend = kpi_trend(lambda f: db.run_with_filters("SELECT SUM(revenue) AS r FROM loads", f),
                     "SELECT SUM(revenue) AS r FROM loads", op_dim, title="Total Revenue")
check("operational dashboard still shows a delta", op_trend is not None and op_trend["period_label"] == "2023", op_trend)

# the customer case: 2020 starts in March, 2022 ends in Feb -> only 2021 is full -> NO delta
cust_dim = {"min_date": "2020-03-03", "max_date": "2022-02-15",
            "mappings": [{"table": "loads", "column": "load_date"}]}
_, cw2 = period_windows(cust_dim["min_date"], cust_dim["max_date"]), None
gran, allw = period_windows(cust_dim["min_date"], cust_dim["max_date"])
complete = complete_windows(allw, pd.Timestamp(cust_dim["min_date"]), pd.Timestamp(cust_dim["max_date"]))
check("only the fully-covered year survives (2021)", [l for l, _ in complete] == ["2021"], [l for l, _ in complete])
cust_trend = kpi_trend(lambda f: db.run_with_filters("SELECT COUNT(*) AS n FROM loads", f),
                       "SELECT COUNT(*) AS n FROM loads", cust_dim, title="Total Customers")
check("the customer-style dashboard shows NO delta (was a false -99%)", cust_trend is None, cust_trend)

check("coverage: a full year is ~1.0", abs(_coverage({"start": "2023-01-01", "end": "2023-12-31"},
      pd.Timestamp("2020-01-01"), pd.Timestamp("2025-01-01")) - 1.0) < 0.01)
check("coverage: a 6-week slice of a year is tiny",
      _coverage({"start": "2022-01-01", "end": "2022-12-31"}, pd.Timestamp("2022-01-01"), pd.Timestamp("2022-02-15")) < 0.2)

print("\n--- sparkline svg ---")
svg = sparkline_svg(trend["series"], color="green")
check("the sparkline is an svg polyline", svg.startswith("<svg") and "polyline" in svg and svg.endswith("</svg>"))
check("too few points -> no sparkline", sparkline_svg([{"label": "a", "value": 1}]) == "")
gap = sparkline_svg([{"label": "a", "value": 1}, {"label": "b", "value": None}, {"label": "c", "value": 3},
                     {"label": "d", "value": 4}], color="red")
check("a gap breaks into separate polylines", gap.count("<polyline") == 1 and "d64545" in gap, gap.count("<polyline"))

print("\n--- delta caption ---")
text, color = format_delta(trend, lambda v: f"{v:.0f}")
check("the caption reads like a BI delta", text == "▲ 100.0% vs 2023" and color == "green", text)
check("no trend -> no caption", format_delta(None, str) == (None, "neutral"))

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
