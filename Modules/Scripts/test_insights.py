"""
Tests for Modules/insights.py (no model, no database).

    python -m Modules.Scripts.test_insights
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.insights import dashboard_insight, panel_explain

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def panel(kind, df, title="Panel"):
    return {"item": {"kind": kind, "title": title}, "df": df}


print("\n--- bar ---")
bar = panel("bar", pd.DataFrame({"customer_type": ["Contract", "Spot", "Dedicated"],
                                 "revenue": [98_800_000, 82_900_000, 80_900_000]}),
            "Revenue by Customer Type")
e = panel_explain(bar)
check("bar names highest and lowest", "Contract is highest" in e and "Dedicated lowest" in e, e)
check("bar formats large values", "98.8M" in e, e)

print("\n--- pie ---")
pie = panel("pie", pd.DataFrame({"t": ["Active", "Terminated"], "n": [124, 26]}), "Status")
e = panel_explain(pie)
check("pie gives the top share as a percent", "Active is the largest share at 83%" in e, e)

print("\n--- line ---")
up = panel("line", pd.DataFrame({"month": pd.to_datetime(["2022-01-01", "2023-01-01", "2024-01-01"]),
                                 "revenue": [100.0, 150.0, 200.0]}), "Monthly Revenue")
e = panel_explain(up)
check("a rising line is described as rising", "rose" in e and "100" in e and "200" in e, e)
flat = panel("line", pd.DataFrame({"month": pd.to_datetime(["2022-01-01", "2023-01-01"]),
                                   "revenue": [100.0, 100.5]}), "Flat")
check("a near-flat line says roughly flat", "roughly flat" in panel_explain(flat), panel_explain(flat))
down = panel("line", pd.DataFrame({"month": pd.to_datetime(["2022-01-01", "2023-01-01"]),
                                   "v": [200.0, 100.0]}), "Falling")
check("a falling line says fell", "fell" in panel_explain(down), panel_explain(down))

print("\n--- kpi / table / empty return None ---")
check("a KPI has no explain line (card shows it)", panel_explain(panel("kpi", pd.DataFrame({"n": [200]}))) is None)
check("an empty df is safe", panel_explain(panel("bar", pd.DataFrame())) is None)
check("a None df is safe", panel_explain({"item": {"kind": "bar"}, "df": None}) is None)
check("a single-bar result still reads", "Contract:" in panel_explain(
    panel("bar", pd.DataFrame({"t": ["Contract"], "v": [5.0]}))))

print("\n--- dashboard insight ---")
third = panel("pie", pd.DataFrame({"t": ["A", "B"], "n": [9, 1]}), "Third chart")
dash = {"results": [panel("kpi", pd.DataFrame({"n": [200]})), bar, up, third]}
ins = dashboard_insight(dash)
check("the insight combines the chart reads", "Contract is highest" in ins and "rose" in ins, ins)
check("it uses at most two facts (the third chart is not included)",
      "largest share" not in ins, ins)
check("a dashboard with only KPIs has no insight",
      dashboard_insight({"results": [panel("kpi", pd.DataFrame({"n": [1]}))]}) is None)
check("an empty dashboard is safe", dashboard_insight({"results": []}) is None)

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
