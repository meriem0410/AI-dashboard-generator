"""
Modules/Scripts/test_rag_context.py

Offline tests for the knowledge base inside the panel graph (USE_RAG).
A fake model answers in turn; the hashing embedder is used (no download).

    python Modules/Scripts/test_rag_context.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")
os.environ["EMBEDDER"] = os.environ.get("EMBEDDER", "hashing")

import pandas as pd

import Modules.Agents.Agent_sql as agent_module
import Modules.sql_generator as generator_module
from Modules.engine_duckdb import Database
from Modules.graph_panel import run_panel
from Modules.knowledge_base import KnowledgeBase, _shortest_path
from Modules.rag_context import rag_enabled, settings

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
            text = outer.queue.pop(0) if outer.queue else "{}"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def install(answers):
    m = FakeModel(answers)
    for mod in (generator_module, agent_module):
        mod.client = m
    return m


def answer(sql):
    return json.dumps({"status": "ok", "sql": sql, "assumptions": [], "reason": None})


drivers = pd.DataFrame({"driver_id": [f"D{i}" for i in range(1, 21)],
                        "first_name": [f"Name{i}" for i in range(1, 21)]})
fuel = pd.DataFrame({"fuel_id": range(1, 61), "driver_id": [f"D{(i % 20) + 1}" for i in range(60)],
                     "total_cost": [100.0 + i for i in range(60)]})
trucks = pd.DataFrame({"truck_id": [f"T{i}" for i in range(1, 11)], "model": [f"M{i}" for i in range(10)]})
maint = pd.DataFrame({"maintenance_id": range(1, 31), "truck_id": [f"T{(i % 10) + 1}" for i in range(30)],
                      "repair_cost": [50.0 + i for i in range(30)]})
db = Database.from_dataframes({"drivers": drivers, "fuel_purchases": fuel,
                               "trucks": trucks, "maintenance_records": maint})
FULL = "FULL_SCHEMA_MARKER"
Q = "total fuel cost per driver"
GOOD = "SELECT d.driver_id, d.first_name, SUM(f.total_cost) AS total_cost FROM fuel_purchases f JOIN drivers d USING (driver_id) GROUP BY ALL;"


def prompt_of(model, i=0):
    return "\n".join(str(x["content"]) for x in model.requests[i]["messages"])


print("\n--- A. off by default ---")
os.environ.pop("USE_RAG", None)
check("rag is off by default", not rag_enabled())
m = install([answer(GOOD)])
g = run_panel(Q, FULL, db)
check("off: the model sees the full schema", FULL in prompt_of(m) and g["rag"] is None)
check("off: the path starts with retrieve", g["path"][0] == "retrieve")

print("\n--- B. on ---")
m = install([answer(GOOD)])
g = run_panel(Q, FULL, db, use_rag=True)
check("on: the question still succeeds", g["success"], f"{g['stage']} {g['error']}")
check("on: the model sees the retrieved schema, not the full one", FULL not in prompt_of(m) and "fuel_purchases" in prompt_of(m))
check("on: the tables are reported", g["rag"] and "fuel_purchases" in g["rag"]["tables"], str(g["rag"]))
check("on: fewer tables than the database", len(g["rag"]["tables"]) <= settings()["max_tables"])

print("\n--- C. built once ---")
kb1 = db.kb
install([answer(GOOD)])
run_panel(Q, FULL, db, use_rag=True)
check("the knowledge base is reused", db.kb is kb1)

print("\n--- D. saved index ---")
with tempfile.TemporaryDirectory() as d:
    kb1.save(d)
    db2 = Database.from_dataframes({"drivers": drivers, "fuel_purchases": fuel})
    os.environ["RAG_KB_DIR"] = d
    install([answer(GOOD)])
    g = run_panel(Q, FULL, db2, use_rag=True)
    check("RAG_KB_DIR loads a saved index", g["success"] and db2.kb is not None, str(g["error"]))
    os.environ.pop("RAG_KB_DIR")
    db2.close()

print("\n--- E. repair gets the full schema ---")
m = install([answer("SELECT nope FROM fuel_purchases;"), answer(GOOD)])
g = run_panel(Q, FULL, db, use_rag=True)
check("after a schema error the repair sees the full schema",
      g["success"] and FULL in prompt_of(m, 1) and g["rag"]["expanded"], str(g["rag"]))

print("\n--- F. retrieval failure ---")
orig = db.kb.select_tables
db.kb.select_tables = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
m = install([answer(GOOD)])
g = run_panel(Q, FULL, db, use_rag=True)
check("a retrieval error falls back to the full schema", g["success"] and FULL in prompt_of(m))
db.kb.select_tables = orig

print("\n--- H. a decline under retrieval is double-checked with the full schema ---")
os.environ.pop("USE_RAG", None)
UNSUP = json.dumps({"status": "unsupported", "sql": None, "assumptions": [], "reason": "no such table"})
m = install([UNSUP, answer(GOOD)])
g = run_panel(Q, FULL, db, use_rag=True)
check("unsupported under retrieval: asked again with the full schema",
      g["success"] and len(m.requests) == 2 and FULL not in prompt_of(m, 0) and FULL in prompt_of(m, 1), str(g["stage"]))
check("the widening is traceable", "widen" in g["path"] and g["rag"]["widened"] and any("full schema" in n for n in g["notes"]))
m = install([UNSUP, UNSUP])
g = run_panel(Q, FULL, db, use_rag=True)
check("still unsupported with the full schema: the decline stands, asked only twice",
      g["status"] == "unsupported" and not g["success"] and len(m.requests) == 2, str(len(m.requests)))
m = install([UNSUP])
g = run_panel(Q, FULL, db, use_rag=False)
check("without retrieval a decline is final at once", g["status"] == "unsupported" and len(m.requests) == 1)
m = install([json.dumps({"status": "blocked", "sql": None, "assumptions": [], "reason": "read-only"})])
g = run_panel(Q, FULL, db, use_rag=True)
check("a blocked request is never re-asked", g["status"] == "blocked" and len(m.requests) == 1)

print("\n--- G. environment switch ---")
os.environ["USE_RAG"] = "on"
check("USE_RAG=on is read", rag_enabled())
m = install([answer(GOOD)])
g = run_panel(Q, FULL, db)
check("the switch changes the prompt without a code change", FULL not in prompt_of(m))
os.environ["USE_RAG"] = "off"

print("\n--- H. path bridging ---")
nb = {"a": {"b"}, "b": {"a", "c"}, "c": {"b", "d"}, "d": {"c"}}
check("shortest path lists the tables in between", _shortest_path("a", "d", nb) == ["b", "c"])
check("no path within the hop limit gives []", _shortest_path("a", "d", nb, max_hops=1) == [])
sel = db.kb.select_tables("maintenance cost per driver", k_tables=2, max_tables=6, bridge="path")
check("bridge=path returns a list of known tables", all(t in db.tables for t in sel), str(sel))

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
