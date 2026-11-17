"""
Tests for Modules/export_xlsx.py (no model, no database).

    python -m Modules.Scripts.test_export_xlsx
"""
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from openpyxl import load_workbook

from Modules.export_xlsx import _sheet_name, dashboard_to_xlsx

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def panel(kind, df, title, **extra):
    return {"item": {"kind": kind, "title": title, "question": title.lower(), **extra}, "df": df,
            "sql": f"SELECT /* {title} */ 1"}


dash = {"question": "fleet overview", "results": [
    panel("kpi", pd.DataFrame({"trip_count": [85410]}), "Total Trips"),
    panel("kpi", pd.DataFrame({"customer_type": ["Contract"], "revenue": [206.8e6]}), "Top Type"),
    panel("bar", pd.DataFrame({"origin_city": ["Charlotte", "Charlotte", "Denver"],
                               "destination_city": ["Portland", "Denver", "Austin"],
                               "avg_mpg": [6.5, 6.7, 6.4]}), "Average MPG by Route"),
    panel("line", pd.DataFrame({"month": pd.to_datetime(["2024-01-01", "2024-02-01"]), "revenue": [1.0, 2.0]}),
          "Revenue per Month"),
    panel("pie", pd.DataFrame({"customer_type": ["Contract", "Spot"], "revenue": [3.0, 1.0]}), "Share"),
    panel("table", pd.DataFrame({"route": ["a", "b"], "total_revenue": [1234567.5, 10.0]}), "Routes: top/bottom [x]",
          sort={"by": "total_revenue", "ascending": True}),
    {"item": {"kind": "bar", "title": "Broken", "question": "q"}, "df": None, "error": "the query failed", "sql": "SELECT x"},
]}
filters = {"category": {"table": "c", "column": "customer_type", "values": ["Spot"]}}
data = dashboard_to_xlsx(dash, title="Fleet", insight="Contract leads.", dataset="Logistics", filters=filters)
wb = load_workbook(io.BytesIO(data))

check("it is a valid xlsx", data[:2] == b"PK" and wb is not None)
check("an Overview sheet comes first", wb.sheetnames[0] == "Overview")
check("one sheet per chart/table panel, plus SQL", len(wb.sheetnames) == 1 + 5 + 1, wb.sheetnames)
ov = wb["Overview"]
text = " ".join(str(c.value) for row in ov.iter_rows() for c in row if c.value is not None)
check("the overview carries dataset, filters and reading",
      "Logistics" in text and "customer type: Spot" in text and "Contract leads." in text)
check("a KPI is stored as a real number", any(c.value == 85410 for row in ov.iter_rows() for c in row))
check("a 'which type' KPI keeps its label", "Contract" in text)

route = wb[wb.sheetnames[1]]
labels = [route.cell(row=r, column=1).value for r in range(5, 8)]
check("repeated categories get a unique label column", "Charlotte – Portland" in labels, labels)
check("bar/line/pie sheets carry a native chart",
      all(len(wb[n]._charts) == 1 for n in wb.sheetnames[1:4]), [len(wb[n]._charts) for n in wb.sheetnames[1:4]])
check("data is an Excel table with a frozen header", route.tables and route.freeze_panes == "A5")

table = wb[wb.sheetnames[4]]
check("sheet names are cleaned of forbidden characters", "[" not in wb.sheetnames[4] and ":" not in wb.sheetnames[4],
      wb.sheetnames[4])
check("the user's sort is kept", table["A5"].value == "b", table["A5"].value)
check("numbers get a thousands format", table["B6"].number_format == "#,##0.00", table["B6"].number_format)
check("a failed panel says why", wb[wb.sheetnames[5]]["A4"].value == "the query failed")

sql = wb["SQL"]
check("the SQL sheet lists every query", sql.max_row == 1 + 7 and "SELECT" in str(sql["D2"].value), sql.max_row)
check("SQL can be left out", "SQL" not in load_workbook(io.BytesIO(dashboard_to_xlsx(dash, include_sql=False))).sheetnames)
check("an empty dashboard still exports",
      load_workbook(io.BytesIO(dashboard_to_xlsx({"results": []}))).sheetnames[0] == "Overview")
used = set()
check("duplicate long titles stay unique and <= 31 chars",
      len({_sheet_name(1, "x" * 50, used), _sheet_name(1, "x" * 50, used)}) == 2
      and all(len(n) <= 31 for n in used))

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
