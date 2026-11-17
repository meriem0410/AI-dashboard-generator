"""
Tests for Modules/export_html.py (no model, no database).

    python -m Modules.Scripts.test_export_html
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.export_html import dashboard_to_html

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def panel(kind, df, title, question="q"):
    return {"item": {"kind": kind, "title": title, "question": question}, "df": df}


dash = {"results": [
    panel("kpi", pd.DataFrame({"revenue": [262_530_000.0]}), "Total Revenue"),
    panel("kpi", pd.DataFrame({"customer_type": ["Contract"], "v": [206_800_000.0]}), "Top Type"),
    panel("bar", pd.DataFrame({"customer_type": ["Contract", "Spot"], "revenue": [98.8e6, 82.9e6]}),
          "Revenue by Type"),
    panel("line", pd.DataFrame({"month": pd.to_datetime(["2022-01-01", "2023-01-01"]), "revenue": [100.0, 150.0]}),
          "Revenue per Month"),
    panel("table", pd.DataFrame({"id": ["A", "B"], "amount": [1, 2]}), "Recent"),
]}

html = dashboard_to_html(dash, insight="Contract leads revenue.", title="Fleet Operations")

check("it is a complete HTML document", html.startswith("<!doctype html>") and "</html>" in html)
check("the title appears", "<h1>Fleet Operations</h1>" in html)
check("the insight appears", "Contract leads revenue." in html)
check("a KPI value is rendered", "262.53M" in html)
check("a 'which type' KPI shows the label, not the number", "Contract" in html and 'kpi-label">Top Type' in html)
check("charts are embedded as Plotly", "Plotly.newPlot" in html or "plotly" in html.lower())
check("plotly.js is loaded exactly once (cdn)", html.count("plotly") >= 1 and html.lower().count("cdn.plot.ly") <= 2)
check("a table is rendered as HTML", "<table" in html and "Amount" in html)
check("the title is HTML-escaped", "<script>" not in dashboard_to_html(
    {"results": []}, title="<script>x</script>"))

# robustness
check("an empty dashboard still produces a valid document",
      dashboard_to_html({"results": []}).startswith("<!doctype html>"))
check("a panel with no data shows a note",
      "No data." in dashboard_to_html({"results": [panel("bar", pd.DataFrame(), "Empty")]}))
err = {"item": {"kind": "kpi", "title": "Broken"}, "df": None, "error": "the query failed"}
check("a failed panel shows its error", "the query failed" in dashboard_to_html({"results": [err]}))

# report context (Restitution 2 upgrade)
print("\n--- report context ---")
from Modules.export_html import describe_filters
full = dict(dash, question="fleet overview")
full["results"] = full["results"] + [
    {"item": {"kind": "bar", "title": "Fuel", "question": "fuel by truck"}, "sql": "SELECT truck_id, SUM(g) FROM fuel GROUP BY 1",
     "df": pd.DataFrame({"truck_id": [f"T{i:02d}" for i in range(40)], "fuel_gallons": range(40)}), "attempts": 2}]
filters = {"category": {"table": "customers", "column": "customer_type", "values": ["Spot"]}}
rep = dashboard_to_html(full, title="Fleet", dataset="Logistics", filters=filters, include_sql=True)
check("the dataset name is printed", "Dataset: Logistics" in rep)
check("the applied filters are printed", "customer type: Spot" in rep)
check("no filters says so", describe_filters({}) == "No filters applied (all data).")
check("the original request is printed", "fleet overview" in rep)
check("the SQL appendix is included on request", "Appendix: how each figure was produced" in rep
      and "SELECT truck_id" in rep and "self-corrected in 2 attempts" in rep)
check("the SQL appendix is off by default", "Appendix" not in dashboard_to_html(full))
check("the cut-off note travels with the chart", "Showing the top 25 of 40." in rep)
check("KPIs come first, in their own row", rep.index('class="kpis"') < rep.index('class="grid"'))
check("plotly.js is written once", rep.count("cdn.plot.ly/plotly") == 1, rep.count("cdn.plot.ly/plotly"))
check("table numbers get separators", "4,567" in dashboard_to_html(
    {"results": [panel("table", pd.DataFrame({"r": ["a"], "amount": [4567.0]}), "T")]}))
check("a table follows the user's sort", (lambda h: h.index(">b<") < h.index(">a<"))(dashboard_to_html(
    {"results": [{"item": {"kind": "table", "title": "T", "sort": {"by": "v", "ascending": False}},
                  "df": pd.DataFrame({"r": ["a", "b"], "v": [1, 2]})}]})))
check("print layout is A4 landscape", "size: A4 landscape" in rep)

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
