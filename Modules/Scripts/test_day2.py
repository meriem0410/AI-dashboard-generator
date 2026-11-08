"""
Modules/Scripts/test_day2.py

Offline tests for Day 2: the plan models, the planner, the JSON statuses and
semantic repair in the panel graph, and the dashboard graph end to end.
A fake language model answers in turn: no internet, no Groq call.

    python Modules/Scripts/test_day2.py
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

import pandas as pd

import Modules.Agents.Agent_dashboard as planner_module
import Modules.Agents.Agent_sql as agent_module
import Modules.sql_generator as generator_module
from Modules.Agents.Agent_dashboard import PLANNER_SYSTEM_PROMPT, plan_dashboard
from Modules.engine_duckdb import Database
from Modules.graph_dashboard import run_dashboard
from Modules.graph_panel import run_panel
from Modules.schemas import Plan, parse_json_model

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def raises(fn):
    try:
        fn()
        return False
    except Exception:
        return True


fuel = pd.DataFrame({"fuel_id": range(1, 91),
                     "purchase_date": pd.date_range("2024-10-04", periods=90, freq="D"),
                     "total_cost": [100.0 + i for i in range(90)]})
drivers = pd.DataFrame({"driver_id": [f"D{i}" for i in range(1, 21)],
                        "first_name": [f"Name{i}" for i in range(1, 21)]})
trips = pd.DataFrame({"trip_id": range(1, 41), "driver_id": [f"D{(i % 20) + 1}" for i in range(40)],
                      "miles": [100 + i for i in range(40)]})
db = Database.from_dataframes({"fuel": fuel, "drivers": drivers, "trips": trips})


class FakeModel:
    """Answers in turn and remembers every request."""

    def __init__(self, answers):
        self.queue = list(answers)
        self.requests = []
        outer = self

        def create(**kwargs):
            outer.requests.append(kwargs)
            text = outer.queue.pop(0) if outer.queue else "{}"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def install(answers):
    model = FakeModel(answers)
    for module in (planner_module, generator_module, agent_module):
        module.client = model
    return model


def answer(status="ok", sql=None, assumptions=None, reason=None):
    return json.dumps({"status": status, "sql": sql, "assumptions": assumptions or [], "reason": reason})


# ---------------------------------------------------------------------
print("\n--- A. the plan models ---")
plan = parse_json_model(json.dumps({
    "title": "T", "focus": "F",
    "items": [{"title": "a", "question": "q", "kind": "kpi"}, {"title": "b", "question": "q2", "kind": "bar"}],
    "unsupported": [{"request": "satisfaction", "reason": "no such column"}],
    "blocked": [{"request": "delete trips", "reason": "read-only"}]}), Plan)
check("a full plan is read", len(plan.items) == 2 and len(plan.unsupported) == 1 and len(plan.blocked) == 1)
check("missing ids are filled in and unique", [i.id for i in plan.items] == ["p1", "p2"], str([i.id for i in plan.items]))
check("constraints default to empty", plan.items[0].constraints.top_n is None)
check("a plan with only an unsupported request is valid",
      len(parse_json_model(json.dumps({"unsupported": [{"request": "x", "reason": "y"}]}), Plan).items) == 0)
check("an empty plan is refused", raises(lambda: parse_json_model("{}", Plan)))
check("an unknown chart kind is refused",
      raises(lambda: parse_json_model(json.dumps({"items": [{"title": "a", "question": "q", "kind": "radar"}]}), Plan)))
check("extra fields are ignored",
      len(parse_json_model(json.dumps({"items": [{"title": "a", "question": "q", "kind": "kpi", "mood": "x"}], "extra": 1}), Plan).items) == 1)

# ---------------------------------------------------------------------
print("\n--- B. the planner ---")
good_plan = json.dumps({
    "title": "Ops", "focus": "fuel and trips",
    "items": [{"id": f"p{i}", "title": f"Item {i}", "question": f"question {i}", "kind": "bar",
               "constraints": {"top_n": 5 if i == 2 else None, "period": None, "entity": None}} for i in range(1, 9)],
    "unsupported": [{"request": "driver satisfaction per month", "reason": "the schema has no satisfaction score"}],
    "blocked": [{"request": "delete all trips older than 2024", "reason": "only read-only queries are run"}]})
model = install([good_plan])
p = plan_dashboard("a request with 8 listed points", "SCHEMA")
check("all 8 listed items are kept (no silent cut at 6)", len(p.items) == 8, str(len(p.items)))
check("unsupported and blocked requests are kept with reasons",
      p.unsupported[0].reason.startswith("the schema") and p.blocked[0].request.startswith("delete"))
check("the constraint top_n is carried", p.items[1].constraints.top_n == 5)
check("the planner runs at temperature 0", model.requests[0]["temperature"] == 0)
check("the planner asks for a JSON object", model.requests[0].get("response_format") == {"type": "json_object"})
check("the old 'omit it' rule is gone from the prompt", "omit it" not in PLANNER_SYSTEM_PROMPT)
check("the prompt tells the model to list unsupported requests", '"unsupported"' in PLANNER_SYSTEM_PROMPT)

model = install(["not json at all", good_plan])
p = plan_dashboard("request", "SCHEMA")
check("an invalid first answer gets one retry", len(p.items) == 8 and len(model.requests) == 2)
check("the retry shows the model what was wrong",
      "not valid" in model.requests[1]["messages"][-1]["content"])
install(["nope", "still nope"])
check("two invalid answers raise a clear error", raises(lambda: plan_dashboard("request", "SCHEMA")))

# ---------------------------------------------------------------------
print("\n--- C. the panel graph with JSON answers ---")
LIMITED = "SELECT d.driver_id, d.first_name, SUM(t.miles) AS total_miles FROM drivers d JOIN trips t USING (driver_id) GROUP BY ALL ORDER BY total_miles DESC LIMIT 5;"
UNLIMITED = LIMITED.replace(" LIMIT 5", "")

model = install([answer("ok", "SELECT COUNT(*) AS n FROM trips;")])
g = run_panel("how many trips", "SCHEMA", db)
check("status ok: success, no assumptions", g["success"] and g["status"] == "ok" and g["assumptions"] == [])

model = install([answer("ambiguous", LIMITED, ["best drivers = most miles driven"])])
g = run_panel("Who are our best drivers?", "SCHEMA", db)
check("status ambiguous: the assumption reaches the result",
      g["success"] and g["status"] == "ambiguous" and g["assumptions"] == ["best drivers = most miles driven"], str(g["assumptions"]))

model = install([answer("unsupported", None, None, "the schema has no driver satisfaction score")])
g = run_panel("average driver satisfaction per month", "SCHEMA", db)
check("status unsupported: stops with the reason",
      (not g["success"]) and g["stage"] == "unsupported" and "satisfaction" in g["error"], f"{g['stage']} {g['error']}")
check("unsupported is not retried and runs no query",
      g["attempts"] == 1 and len(model.requests) == 1 and g["path"] == ["generate", "extract", "finish"], str(g["path"]))

model = install([answer("blocked", None, None, "only read-only queries are run")])
g = run_panel("Delete all trips", "SCHEMA", db)
check("status blocked: stops with the reason", (not g["success"]) and g["stage"] == "blocked" and g["status"] == "blocked")
check("blocked: nothing deleted", db.run("SELECT COUNT(*) AS n FROM trips;").iloc[0]["n"] == 40)

print("\n--- C2. semantic checks inside the graph ---")
model = install([answer("ok", UNLIMITED), answer("ok", LIMITED)])
g = run_panel("Top 5 drivers by miles", "SCHEMA", db, kind="bar")
check("a ranking without LIMIT is repaired", g["success"] and g["attempts"] == 2 and "repair" in g["path"], f"{g['attempts']} {g['path']}")
check("the failed attempt is recorded as stage semantic", g["history"][0]["stage"] == "semantic", str(g["history"]))
check("the repair request carries the problem text", "LIMIT" in model.requests[1]["messages"][-1]["content"])
check("the repaired result has 5 rows", len(g["result"]) == 5)

variants = [UNLIMITED, UNLIMITED.replace("total_miles DESC", "total_miles ASC"),
            UNLIMITED.replace("total_miles DESC", "d.first_name")]
model = install([answer("ok", v) for v in variants])
g = run_panel("Top 5 drivers by miles", "SCHEMA", db, kind="bar")
check("when the budget runs out, the last good result is kept (never destroyed)",
      g["success"] and g["result"] is not None and len(g["result"]) == 20, f"{g['success']} {g['stage']}")
check("the unresolved problem is shown as a note", any(n.startswith("Unresolved") for n in g["notes"]), str(g["notes"]))
check("it used all 3 attempts", g["attempts"] == 3, str(g["attempts"]))

model = install([answer("ok", UNLIMITED)] * 3)
g = run_panel("Top 5 drivers by miles", "SCHEMA", db, kind="bar")
check("the same query again stops the loop and still returns the good result",
      g["success"] and g["attempts"] == 2 and len(g["result"]) == 20, f"{g['success']} {g['attempts']} {g['stage']}")

model = install([answer("ok", "SELECT miles FROM trips LIMIT 3;"), answer("ok", "SELECT SUM(miles) AS total_miles FROM trips;")])
g = run_panel("total miles", "SCHEMA", db, kind="kpi")
check("a KPI that returns several rows is repaired to one row",
      g["success"] and len(g["result"]) == 1 and g["attempts"] == 2, f"{g['attempts']} {g['stage']}")

model = install([answer("ok", "SELECT date_trunc('month', purchase_date) AS month, SUM(total_cost) AS spend FROM fuel GROUP BY 1 ORDER BY 1;")])
g = run_panel("monthly fuel spend", "SCHEMA", db, kind="line")
check("a partial last month does not trigger a repair", g["success"] and g["attempts"] == 1)
check("it becomes a note for the user", any("incomplete" in n for n in g["notes"]), str(g["notes"]))

# ---------------------------------------------------------------------
print("\n--- D. the dashboard graph end to end ---")
plan_json = json.dumps({
    "title": "Trips", "focus": "miles and drivers",
    "items": [
        {"id": "p1", "title": "Total miles", "question": "What are the total miles?", "kind": "kpi"},
        {"id": "p2", "title": "Top drivers", "question": "Top 5 drivers by miles", "kind": "bar",
         "constraints": {"top_n": 5}},
        {"id": "p3", "title": "Satisfaction", "question": "Average satisfaction", "kind": "line"}],
    "unsupported": [{"request": "driver satisfaction per month", "reason": "no satisfaction score in the data"}],
    "blocked": [{"request": "delete trips before 2024", "reason": "only read-only queries are run"}]})
model = install([plan_json,
                 answer("ok", "SELECT SUM(miles) AS total_miles FROM trips;"),
                 answer("ok", LIMITED),
                 answer("unsupported", None, None, "no satisfaction score in the data")])
progress = []
dash = run_dashboard("a request", "SCHEMA", db, on_progress=lambda i, n, t: progress.append((i, n, t)))
check("one result per planned item", len(dash["results"]) == 3)
check("the KPI and the ranking succeeded",
      dash["results"][0]["df"] is not None and dash["results"][1]["df"] is not None and len(dash["results"][1]["df"]) == 5)
check("the panel the model called unsupported carries the reason",
      dash["results"][2]["stage"] == "unsupported" and "satisfaction" in dash["results"][2]["error"] and dash["results"][2]["df"] is None)
check("unsupported and blocked requests come back with reasons",
      dash["unsupported"][0]["reason"].startswith("no satisfaction") and dash["blocked"][0]["request"].startswith("delete"))
check("the orchestrator path is plan, panels, assemble", dash["path"] == ["plan", "panels", "assemble"], str(dash["path"]))
check("progress was reported for every item", [p[0] for p in progress] == [0, 1, 2] and progress[0][2] == "Total miles", str(progress))
check("the plan keeps the item titles", [i["title"] for i in dash["plan"]["items"]] == ["Total miles", "Top drivers", "Satisfaction"])
check("one planner call plus one call per item, nothing for the flagged requests", len(model.requests) == 4, str(len(model.requests)))

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
