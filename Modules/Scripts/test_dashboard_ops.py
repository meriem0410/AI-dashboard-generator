"""
Tests for Modules/dashboard_ops.py (no model, no database).

    python -m Modules.Scripts.test_dashboard_ops
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Modules import dashboard_ops as ops

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def make():
    def panel(pid, title, kind):
        return {"item": {"id": pid, "title": title, "question": title, "kind": kind,
                         "constraints": {}}, "df": None, "sql": f"SELECT 1 -- {pid}"}
    results = [
        panel("p1", "Total Customers", "kpi"),
        panel("p2", "Total Revenue", "kpi"),
        panel("p3", "Revenue by Customer Type", "bar"),
        panel("p4", "Revenue Share by Type", "pie"),
        panel("p5", "Monthly Revenue Trend", "line"),
        panel("p6", "Top 5 Customers by Revenue", "bar"),
    ]
    return {"question": "q", "plan": {"title": "D", "focus": "", "items": [r["item"] for r in results]},
            "results": results, "unsupported": [], "blocked": []}


def idx(d, ref):
    return ops.resolve_panel(d, ref).get("index")


d = make()
print("\n--- resolve by kind + ordinal ---")
check("'the pie' finds the single pie", idx(d, "the pie") == 3)
check("'the pie chart' too", idx(d, "the pie chart") == 3)
check("'the line/trend' finds the line", idx(d, "the trend") == 4)
check("'the first kpi'", idx(d, "the first kpi") == 0)
check("'the second card'", idx(d, "the second card") == 1)
check("'the last chart' is the last plot (p6)", idx(d, "the last chart") == 5)
check("'the first bar' is p3", idx(d, "the first bar chart") == 2)

print("\n--- resolve by title ---")
check("'top 5 customers' matches p6", idx(d, "top 5 customers") == 5)
check("'monthly revenue' matches the trend", idx(d, "monthly revenue") == 4)
check("'revenue share' matches the pie", idx(d, "revenue share") == 3)

print("\n--- resolve by id and index ---")
check("an explicit id", idx(d, "p3") == 2)
check("an integer index passes through", idx(d, 2) == 2)
check("a negative index", idx(d, -1) == 5)
check("an out-of-range index is None", ops.resolve_panel(d, 99) == {"index": None})

print("\n--- ambiguity and misses ---")
amb = ops.resolve_panel(d, "the bar chart")
check("two bars with no title words -> candidates", amb.get("candidates") == [2, 5], amb)
check("'the kpi' alone -> candidates (3 kpis? here 2)", ops.resolve_panel(d, "the card").get("candidates") == [0, 1])
check("a title that matches nothing -> None", idx(d, "fuel efficiency by driver") is None)
check("'revenue' matches several bars/line -> candidates",
      "candidates" in ops.resolve_panel(d, "revenue") or idx(d, "revenue") is not None)

print("\n--- remove ---")
d = make()
removed = ops.remove_panel(d, 3)                      # the pie
check("the pie is removed", removed["item"]["title"] == "Revenue Share by Type" and len(d["results"]) == 5)
check("ids are renumbered p1..p5", [r["item"]["id"] for r in d["results"]] == ["p1", "p2", "p3", "p4", "p5"])
check("plan.items mirrors results", [i["id"] for i in d["plan"]["items"]] == ["p1", "p2", "p3", "p4", "p5"])
check("remove by resolved reference works end to end",
      (lambda dd: ops.remove_panel(dd, ops.resolve_panel(dd, "monthly revenue")["index"])["item"]["kind"])(make()) == "line")

print("\n--- append / insert ---")
d = make()
new = {"item": {"id": "x", "title": "Avg Revenue per Customer", "question": "avg", "kind": "kpi",
                "constraints": {}}, "df": None, "sql": "SELECT 2"}
ops.append_panel(d, new)
check("append adds at the end", d["results"][-1]["item"]["title"] == "Avg Revenue per Customer")
check("the appended panel gets a fresh id", d["results"][-1]["item"]["id"] == "p7")
d = make()
ops.append_panel(d, new, position=0)
check("insert at a position", d["results"][0]["item"]["title"] == "Avg Revenue per Customer"
      and d["results"][0]["item"]["id"] == "p1")

print("\n--- replace ---")
d = make()
ops.replace_panel(d, 5, new)
check("replace swaps the panel, keeps the slot's id", d["results"][5]["item"]["title"] == "Avg Revenue per Customer"
      and d["results"][5]["item"]["id"] == "p6")

print("\n--- move ---")
d = make()
ops.move_panel(d, 5, 0)                               # move top-5 bar to the front
check("move reorders", [r["item"]["title"] for r in d["results"]][0] == "Top 5 Customers by Revenue")
check("ids follow the new order", [r["item"]["id"] for r in d["results"]] == ["p1", "p2", "p3", "p4", "p5", "p6"])

print("\n--- guards ---")
d = make()
for fn, args in [(ops.remove_panel, (d, 99)), (ops.replace_panel, (d, 99, new)), (ops.move_panel, (d, 0, 99))]:
    try:
        fn(*args); ok = False
    except IndexError:
        ok = True
    check(f"{fn.__name__} rejects a bad index", ok)

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
