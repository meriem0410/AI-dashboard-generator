"""
Tests for the dashboard composition rule: 3-5 KPI cards and 4-7 charts, always.
No network: the model is a fake that answers in turn.

    python -m Modules.Scripts.test_composition
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import Modules.Agents.Agent_dashboard as planner
from Modules.Agents.Agent_dashboard import composition, plan_dashboard

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


class FakeModel:
    def __init__(self, answers):
        self.queue = list(answers)
        self.requests = []
        outer = self

        def create(**kwargs):
            outer.requests.append(kwargs)
            if not outer.queue:
                raise RuntimeError("no more answers")
            text = outer.queue.pop(0)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def install(answers):
    m = FakeModel(answers)
    planner.client = m
    return m


def item(n, kind, title=None, question=None):
    return {"id": f"p{n}", "title": title or f"{kind} {n}", "question": question or f"question {kind} {n}", "kind": kind}


def plan_json(kinds, listed=False):
    return json.dumps({"title": "T", "focus": "F", "listed": listed,
                       "items": [item(i, k) for i, k in enumerate(kinds, 1)]})


def extra_json(kinds, prefix="extra"):
    return json.dumps({"items": [item(i, k, f"{prefix} {k} {i}", f"{prefix} q {k} {i}") for i, k in enumerate(kinds, 1)]})


planner.ENFORCE_COMPOSITION = True

print("\n--- composition counts ---")
from Modules.schemas import PlanItem
c = composition([PlanItem(title="a", question="q", kind=k) for k in ["kpi", "kpi", "bar", "line", "pie", "table"]])
check("counts kpis, plots and tables", c == (2, 3, 1), str(c))

print("\n--- a thin plan is topped up ---")
m = install([plan_json(["bar"]), extra_json(["kpi", "kpi", "kpi", "line", "pie", "bar"])])
p = plan_dashboard("which customer type earns most", "SCHEMA")
k, pl, t = composition(p.items)
check("one chart becomes 3 kpis + 4 plots", (k, pl) == (3, 4), f"{k},{pl}")
check("the user's own item stays first", p.items[0].title == "bar 1")
check("added items are traceable", len(p.added) == 6 and all(i in [x.id for x in p.items] for i in p.added))
check("ids are unique", len({i.id for i in p.items}) == len(p.items))
check("the top-up request names what is missing", "exactly 3 supporting item(s) of kind kpi" in m.requests[1]["messages"][-1]["content"]
      and "3 supporting item(s) of kind bar, line or pie" in m.requests[1]["messages"][-1]["content"])
check("only one top-up call is made", len(m.requests) == 2)

print("\n--- a complete plan is left alone ---")
m = install([plan_json(["kpi"] * 3 + ["bar", "line", "pie", "bar"])])
p = plan_dashboard("x", "SCHEMA")
check("no extra call when 3 kpis and 4 plots exist", len(m.requests) == 1 and p.added == [])

print("\n--- duplicates and wrong kinds are not accepted ---")
dup = json.dumps({"items": [item(1, "kpi", "kpi 1", "question kpi 1"),          # same as an existing item
                            item(2, "kpi", "new a", "qa"), item(3, "kpi", "new b", "qb"),
                            item(4, "table", "a table", "qt"),                  # a table never fills a plot slot
                            item(5, "bar", "new c", "qc"), item(6, "bar", "new d", "qd"),
                            item(7, "bar", "new e", "qe"), item(8, "bar", "new f", "qf")]})
install([plan_json(["kpi", "bar"]), dup])
p = plan_dashboard("x", "SCHEMA")
k, pl, t = composition(p.items)
check("duplicate title/question skipped", [i.title for i in p.items].count("kpi 1") == 1)
check("kpis filled to 3 and plots to 4, no more", (k, pl) == (3, 4), f"{k},{pl}")
check("a table does not fill a chart slot", t == 0)

print("\n--- a failing top-up never breaks the request ---")
install([plan_json(["bar", "line"])])          # second call raises: no answers left
p = plan_dashboard("x", "SCHEMA")
check("the plan is returned as the model wrote it", len(p.items) == 2 and p.added == [])
install([plan_json(["bar"]), "not json"])
p = plan_dashboard("x", "SCHEMA")
check("an invalid top-up is ignored", len(p.items) == 1)

print("\n--- maxima ---")
install([plan_json(["kpi"] * 7 + ["bar"] * 9)])
p = plan_dashboard("open request", "SCHEMA")
k, pl, _ = composition(p.items)
check("an open request is trimmed to 5 kpis and 7 plots", (k, pl) == (5, 7), f"{k},{pl}")
install([plan_json(["kpi"] * 7 + ["bar"] * 9, listed=True)])
p = plan_dashboard("a list of 16 points", "SCHEMA")
check("points the user listed are never cut", len(p.items) == 12 or len(p.items) == 16)   # MAX_ITEMS safety cap only
check("the safety cap still applies", len(p.items) <= planner.MAX_ITEMS)

print("\n--- the prompt ---")
pr = planner.PLANNER_SYSTEM_PROMPT
check("prompt demands 3 to 5 kpis and 4 to 7 charts", "3 to 5 items of kind kpi" in pr and "4 to 7 items of kind" in pr)
check("prompt asks for supporting items such as entity counts", "number of the main entities" in pr)
check("prompt asks for the 'listed' flag", '"listed"' in pr)

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
