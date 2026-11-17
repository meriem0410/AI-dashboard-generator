"""
Regression tests for the chart and panel-edit bugs found on the deployed app
(Restitution 2 testing), and for the new chart styles.

    python -m Modules.Scripts.test_visual_fixes

Bugs covered:
  - "Fuel Consumption by Truck" was empty: a numeric unit_number was chosen as
    the x-axis over the text truck_id (92 invisible bars on a 2000..8000 axis).
  - "Average MPG by Route" stacked bars: origin_city repeats across routes.
  - "Trip Distance Distribution" faded: hundreds of thin bars instead of a histogram.
  - "edit the label of the chart" turned a top-5 table into a different bar chart:
    look-only edits now never re-run SQL; a model edit keeps kind/title and a failed
    re-run leaves the panel untouched.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from Modules import followup as F
from Modules.visualisation import (build_visual_metadata, format_metric_value,
                                   pie_labels, render_visual)

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def chart(df, kind, title, **extra):
    m = build_visual_metadata(df, kind, title, title=title)
    m.update(extra)
    return m, render_visual(df, m)


print("\n--- category axis ---")
trucks = pd.DataFrame({"truck_id": [f"TRK{i:03d}" for i in range(92)],
                       "unit_number": np.arange(2000, 2092) * 3,
                       "total_fuel_gallons": np.linspace(100, 900, 92)})
m, fig = chart(trucks, "bar", "Fuel Consumption by Truck")
check("a text id beats a numeric dimension for the x-axis", m["x"] == "truck_id", m["x"])
check("92 categories become horizontal bars", fig.data[0].orientation == "h")
check("only the top 25 bars are drawn", len(fig.data[0].y) == 25, len(fig.data[0].y))
check("the title says what was cut", "(top 25 of 92)" in fig.layout.title.text, fig.layout.title.text)
check("the biggest value is drawn first", fig.data[0].y[0] == "TRK091", fig.data[0].y[0])
check("the tall chart gets a taller figure", fig.layout.height > 420)

years = pd.DataFrame({"year": [2023, 2024, 2025], "revenue": [1.0, 2.0, 3.0]})
m, fig = chart(years, "bar", "Revenue by year")
check("a numeric dimension still works when it is the only one", m["x"] == "year")
check("numeric categories are a category axis, not a continuous one",
      fig.layout.xaxis.type == "category")

print("\n--- duplicate labels ---")
routes = pd.DataFrame({"origin_city": ["Charlotte", "Charlotte", "Denver"],
                       "destination_city": ["Portland", "Denver", "Austin"],
                       "avg_mpg": [6.5, 6.7, 6.4]})
m, fig = chart(routes, "bar", "Average MPG by Route")
check("repeated origins get a combined unique label",
      list(fig.data[0].x) == ["Charlotte – Portland", "Charlotte – Denver", "Denver – Austin"],
      list(fig.data[0].x))
check("values are not stacked", max(fig.data[0].y) < 7, list(fig.data[0].y))
check("the raw category travels in customdata for cross-filtering",
      fig.data[0].customdata[0][0] == "Charlotte")

print("\n--- histogram ---")
rng = np.random.default_rng(0)
trips = pd.DataFrame({"trip_distance": rng.random(400) * 900, "trip_count": rng.integers(1, 4, 400)})
m, fig = chart(trips, "bar", "Trip Distance Distribution")
check("a continuous numeric x is drawn as a histogram", type(fig.data[0]).__name__ == "Histogram")
check("a count metric is summed per bin", fig.data[0].histfunc == "sum")

print("\n--- pie ---")
shares = pd.DataFrame({"t": list("abcdefghijk"), "rev": range(11, 0, -1)})
m, fig = chart(shares, "pie", "Revenue share")
check("a pie keeps 7 slices and folds the rest into Other",
      list(fig.data[0].labels)[-1] == "Other" and len(fig.data[0].labels) == 8)
check("pie_labels lists the real categories for the filter pills",
      pie_labels(shares, m) == list("abcdefg"))

print("\n--- styles ---")
for style, trace in (("treemap", "Treemap"), ("horizontal", "Bar"), ("histogram", "Histogram")):
    m, fig = chart(shares, "bar", "x", style=style)
    check(f"style {style} renders a {trace}", fig is not None and type(fig.data[0]).__name__ == trace)
two = pd.DataFrame({"route": list("abcd"), "distance": [1.0, 2, 3, 4], "fuel_gallons": [2.0, 3, 5, 8]})
m, fig = chart(two, "bar", "fuel vs distance", style="scatter")
check("style scatter plots two measures", type(fig.data[0]).__name__ == "Scatter")
monthly = pd.DataFrame({"month_start": pd.date_range("2024-01-01", periods=4, freq="MS"),
                        "revenue": [1.0, 2, 3, 4]})
m, fig = chart(monthly, "line", "Revenue over time", style="area")
check("style area fills the line", fig.data[0].fill == "tozeroy")
m, fig = chart(shares, "bar", "x", sort={"by": "t", "ascending": False})
check("a user sort by another column is applied", list(fig.data[0].x)[:2] == ["k", "j"])

print("\n--- numbers ---")
check("counts keep a thousands separator", format_metric_value(85410, "trip_count") == "85,410")
check("big counts are still abbreviated", format_metric_value(2_500_000, "trip_count") == "2.5M")

print("\n--- presentation edits (no SQL) ---")
panel = {"item": {"id": "p1", "title": "Top 5 Routes", "kind": "table",
                  "question": "list the top 5 routes ordered by total revenue from lowest to highest"},
         "df": pd.DataFrame({"route": ["a"], "total_revenue": [1.0], "trip_count": [3]}), "sql": "S"}
P = F.presentation_edit
check("'edit the label of the chart' asks for the new title", P("edit the label of the chart", panel)["op"] == "ask")
check("rename picks up the new title", P("rename it to Best routes", panel) == {"op": "rename", "title": "Best routes"})
check("quoted titles are unquoted", P('change the title to "Fleet"', panel)["title"] == "Fleet")
check("'inverse the order' flips a lowest-first question",
      P("inverse the order", panel) == {"op": "sort", "sort": {"by": None, "ascending": False}})
check("sort by a named column", P("sort by trip count ascending", panel)["sort"] == {"by": "trip_count", "ascending": True})
check("show as a pie changes the kind", P("show it as a pie", panel) == {"op": "kind", "kind": "pie", "style": None})
check("make it a treemap is a style", P("make it a treemap", panel)["style"] == "treemap")
for text in ("make it top 10", "show it as a percentage", "use revenue instead", "only for 2024"):
    check(f"'{text}' needs new data -> model", P(text, panel) is None)

d = {"question": "q", "plan": {"items": [panel["item"]]}, "results": [panel]}
r = F.apply_presentation_edit(P("rename it to Best routes", panel), d, 0)
check("a rename keeps the data and SQL", r["ok"] and panel["item"]["title"] == "Best routes"
      and panel["sql"] == "S" and panel["item"]["kind"] == "table")
r = F.apply_presentation_edit({"op": "kind", "kind": "kpi", "style": None},
                              {"results": [{"item": {"title": "t"}, "df": pd.DataFrame({"a": [1, 2]})}]}, 0)
check("a multi-row panel can't become a KPI", not r["ok"])

print("\n--- model edits ---")


def fixture():
    item = {"id": "p1", "title": "Top 5 Routes", "question": "top 5 routes", "kind": "table",
            "constraints": {}, "sort": {"by": None, "ascending": True}}
    res = {"item": item, "df": pd.DataFrame({"r": ["a"], "v": [1]}), "sql": "OLD"}
    return {"question": "q", "plan": {"items": [item]}, "results": [res]}


ok = lambda *a, **k: {"success": True, "result": pd.DataFrame({"r": ["a", "b"], "v": [1, 2]}),
                      "sql": "NEW", "attempts": 1, "status": "ok", "assumptions": [], "notes": []}
fail = lambda *a, **k: {"success": False, "error": "no such column", "sql": "BAD"}

d = fixture()
r = F.apply_followup(F.FollowupAction(operation="edit", target="p1", question="top 10 routes"), d, "S", None,
                     run_panel=ok)
it = d["results"][0]["item"]
check("an edit without a new kind keeps the panel's kind", it["kind"] == "table", it["kind"])
check("an edit without a new title keeps the title", it["title"] == "Top 5 Routes", it["title"])
check("presentation choices survive a re-run", it.get("sort") == {"by": None, "ascending": True})

d = fixture()
r = F.apply_followup(F.FollowupAction(operation="edit", target="p1", question="top 10 routes"), d, "S", None,
                     run_panel=fail)
check("a failed edit reports failure", not r["ok"] and "left as it was" in r["message"], r["message"])
check("a failed edit leaves the working panel", d["results"][0]["sql"] == "OLD")

print(f"\n{'ALL PASSED' if failures == 0 else str(failures) + ' FAILED'}")
sys.exit(1 if failures else 0)
