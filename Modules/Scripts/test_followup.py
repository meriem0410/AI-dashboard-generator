"""
Tests for Modules/followup.py (no model, no database: call and run_panel are faked).

    python -m Modules.Scripts.test_followup
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules import followup as F

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
                         "constraints": {}}, "df": pd.DataFrame({"x": [1]}), "sql": f"S -- {pid}"}
    results = [panel("p1", "Total Customers", "kpi"),
               panel("p2", "Revenue by Customer Type", "bar"),
               panel("p3", "Revenue Share by Type", "pie"),
               panel("p4", "Monthly Revenue Trend", "line")]
    return {"question": "q", "plan": {"title": "D", "focus": "", "items": [r["item"] for r in results]},
            "results": results, "unsupported": [], "blocked": []}


def fake_call(payload):
    """A router stand-in: returns the JSON we pass via a closure."""
    return json.dumps(payload)


def ok_panel(df=None):
    return lambda *a, **k: {"success": True, "result": df if df is not None else pd.DataFrame({"n": [5]}),
                           "sql": "SELECT 5 AS n", "attempts": 1, "status": "ok",
                           "assumptions": [], "notes": [], "stage": "completed", "path": ["x"]}


# ---- classify ----
print("\n--- classify routes the message ---")
d = make()
act = F.classify_followup("add a KPI for total fuel cost", d, "SCHEMA",
                          call=lambda m: fake_call({"operation": "add", "question": "What is the total fuel cost?",
                                                    "kind": "kpi", "title": "Total Fuel Cost"}))
check("an 'add' is parsed with its question and kind", act.operation == "add" and act.kind == "kpi"
      and "fuel" in act.question.lower())
act = F.classify_followup("make the top 5 a top 10", d, "S",
                          call=lambda m: fake_call({"operation": "edit", "target": "top 5 customers",
                                                    "question": "Top 10 customers by revenue", "kind": "bar",
                                                    "constraints": {"top_n": 10}}))
check("an 'edit' carries target and new constraints", act.operation == "edit" and act.constraints.top_n == 10)
check("the router prompt lists the current panels", "Revenue Share by Type" in F._summarise(d))
bad = [False]
def flaky(m):
    if not bad[0]:
        bad[0] = True
        return "not json"
    return fake_call({"operation": "ask", "question": "What is revenue for Spot?"})
act = F.classify_followup("revenue for spot?", d, "S", call=flaky)
check("an invalid answer is retried once", act.operation == "ask")

# ---- apply: remove ----
print("\n--- remove ---")
d = make()
r = F.apply_followup(F.FollowupAction(operation="remove", target="the pie"), d, "S", None, run_panel=ok_panel())
check("remove drops the pie and reports it", r["ok"] and len(d["results"]) == 3
      and "Revenue Share" in r["message"], r["message"])
check("ids renumber after remove", [p["item"]["id"] for p in d["results"]] == ["p1", "p2", "p3"])

print("\n--- remove with an ambiguous target asks back ---")
d2 = make()
d2["results"].append({"item": {"id": "p5", "title": "Another Bar", "kind": "bar", "question": "q",
                               "constraints": {}}, "df": pd.DataFrame({"x": [1]}), "sql": "s"})
d2["plan"]["items"] = [p["item"] for p in d2["results"]]
r = F.apply_followup(F.FollowupAction(operation="remove", target="the bar"), d2, "S", None, run_panel=ok_panel())
check("an ambiguous target returns candidates, changes nothing",
      not r["ok"] and r["candidates"] and len(d2["results"]) == 5, r)
check("the clarifying message names the options", "Revenue by Customer Type" in r["message"])

print("\n--- a missing target is reported ---")
d = make()
r = F.apply_followup(F.FollowupAction(operation="remove", target="fuel efficiency"), d, "S", None, run_panel=ok_panel())
check("no match -> a helpful message, nothing removed", not r["ok"] and len(d["results"]) == 4)

# ---- apply: add ----
print("\n--- add ---")
d = make()
r = F.apply_followup(F.FollowupAction(operation="add", question="What is the total fuel cost?",
                                      kind="kpi", title="Total Fuel Cost"), d, "S", None,
                     run_panel=ok_panel(pd.DataFrame({"fuel": [123.0]})))
check("add runs a panel and appends it", r["ok"] and len(d["results"]) == 5
      and d["results"][-1]["item"]["title"] == "Total Fuel Cost")
check("the new panel keeps its sql and a fresh id", d["results"][-1]["sql"] == "SELECT 5 AS n"
      and d["results"][-1]["item"]["id"] == "p5")

# ---- apply: edit ----
print("\n--- edit ---")
d = make()
r = F.apply_followup(F.FollowupAction(operation="edit", target="revenue by customer type",
                                      question="Revenue by customer type as a share", kind="pie"), d, "S", None,
                     run_panel=ok_panel(pd.DataFrame({"t": ["a", "b"], "v": [1, 2]})))
check("edit replaces the panel at its slot, keeping position/id",
      r["ok"] and d["results"][1]["item"]["kind"] == "pie" and d["results"][1]["item"]["id"] == "p2"
      and len(d["results"]) == 4, [p["item"]["kind"] for p in d["results"]])

# ---- apply: move ----
print("\n--- move ---")
d = make()
r = F.apply_followup(F.FollowupAction(operation="move", target="monthly revenue", position="top"), d, "S", None,
                     run_panel=ok_panel())
check("move puts the trend first", r["ok"] and d["results"][0]["item"]["title"] == "Monthly Revenue Trend")
d = make()
F.apply_followup(F.FollowupAction(operation="move", target="total customers", position="bottom"), d, "S", None,
                 run_panel=ok_panel())
check("move to bottom works", d["results"][-1]["item"]["title"] == "Total Customers")

# ---- apply: ask (answer, don't add) ----
print("\n--- ask answers but does not change the dashboard ---")
d = make()
r = F.apply_followup(F.FollowupAction(operation="ask", question="What is revenue for Spot?"), d, "S", None,
                     run_panel=ok_panel(pd.DataFrame({"revenue": [999.0]})))
check("ask returns a panel and leaves the dashboard untouched",
      r["ok"] and r["panel"] is not None and len(d["results"]) == 4 and r["dashboard"] is None)
check("the ask answer can then be pinned", (F.pin_panel(d, r["panel"]) is d) and len(d["results"]) == 5
      and d["results"][-1]["item"]["id"] == "p5")

# ---- blocked / unsupported ----
print("\n--- blocked and unsupported never touch the dashboard ---")
d = make()
r = F.apply_followup(F.FollowupAction(operation="blocked", reason="deletes rows"), d, "S", None, run_panel=ok_panel())
check("blocked is refused with a reason, no change", not r["ok"] and len(d["results"]) == 4 and "delete" in r["message"].lower())
r = F.apply_followup(F.FollowupAction(operation="unsupported", reason="no weather data"), d, "S", None, run_panel=ok_panel())
check("unsupported is refused with a reason", not r["ok"] and "weather" in r["message"].lower())

# ---- kind inference for a bare add/ask ----
print("\n--- kind inference ---")
check("a single row infers a kpi", F._infer_kind(pd.DataFrame({"n": [1]})) == "kpi")
check("a dated frame infers a line", F._infer_kind(pd.DataFrame({"month": ["2024-01", "2024-02"], "v": [1, 2]})) == "line")
check("otherwise a bar", F._infer_kind(pd.DataFrame({"cat": ["a", "b"], "v": [1, 2]})) == "bar")

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
