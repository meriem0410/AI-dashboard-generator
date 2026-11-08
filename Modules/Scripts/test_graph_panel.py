"""
Modules/Scripts/test_graph_panel.py

Offline tests for the LangGraph panel graph (Modules/graph_panel.py).
The key test: for every scenario, the graph and the old sql_agent loop,
given the SAME fake model answers, must end the same way.
No internet, no Groq call, no real data.

Run from the project root:
    python Modules/Scripts/test_graph_panel.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

import pandas as pd

import Modules.Agents.Agent_sql as agent_module
import Modules.sql_generator as generator_module
from Modules.engine_duckdb import Database
from Modules.graph_panel import build_panel_graph, run_panel

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


loads = pd.DataFrame({
    "load_id": range(1, 7),
    "revenue": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
    "load_date": pd.to_datetime(["2022-01-15", "2022-06-15", "2023-01-15",
                                 "2023-06-15", "2024-01-15", "2024-06-15"]),
})
db = Database.from_dataframes({"loads": loads})


def fake_client(answers, raise_on_call=None):
    """A stand-in for the Groq client returning the answers in turn."""
    queue = list(answers)

    def create(**kwargs):
        if raise_on_call is not None:
            raise raise_on_call
        text = queue.pop(0) if queue else "SELECT 'INVALID QUERY';"
        message = SimpleNamespace(content=text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def install(answers, raise_on_call=None):
    stub = fake_client(answers, raise_on_call)
    agent_module.client = stub
    generator_module.client = stub


def run_agent(answers, **kw):
    install(answers, **kw)
    return agent_module.sql_agent("test question", "SCHEMA", db)


def run_graph(answers, **kw):
    install(answers, **kw)
    return run_panel("test question", "SCHEMA", db)


def norm(sql):
    return " ".join(str(sql or "").lower().replace(";", " ").split())


COUNT = "SELECT COUNT(*) AS n FROM loads;"
SCENARIOS = {
    "good SQL": [COUNT],
    "unknown column, then fixed": ["SELECT nope FROM loads;", COUNT],
    "three bad answers (budget exhausted)":
        ["SELECT a FROM loads;", "SELECT b FROM loads;", "SELECT c FROM loads;"],
    "DELETE": ["DELETE FROM loads;"],
    "WITH ... DELETE": ["WITH o AS (SELECT load_id FROM loads) DELETE FROM loads WHERE load_id IN (SELECT load_id FROM o);"],
    "SELECT ... INTO": ["SELECT * INTO copy_of_loads FROM loads;"],
    "unparseable, then fixed": ["SELECT ( FROM loads;", COUNT],
    "the model refuses": ["SELECT 'INVALID QUERY';"],
    "empty result, then data": ["SELECT * FROM loads WHERE revenue < 0;", COUNT],
    "empty result twice": ["SELECT * FROM loads WHERE revenue < 0;", "SELECT * FROM loads WHERE revenue < -5;"],
    "runtime error, then fixed": ["SELECT CAST('abc' AS INTEGER) AS x FROM loads;", COUNT],
}

print("\n--- A. the graph agrees with the old agent loop ---")
for name, answers in SCENARIOS.items():
    a = run_agent(answers)
    g = run_graph(answers)
    same = (
        a["success"] == g["success"] and a["stage"] == g["stage"]
        and a["attempts"] == g["attempts"] and norm(a["sql"]) == norm(g["sql"])
        and [h["stage"] for h in a["history"]] == [h["stage"] for h in g["history"]]
        and (a["result"] is None) == (g["result"] is None)
    )
    check(f"same outcome: {name}", same,
          f"agent={a['success']}/{a['stage']}/{a['attempts']}  graph={g['success']}/{g['stage']}/{g['attempts']}")
    check(f"  same keys as the agent: {name}", set(a) <= set(g), str(set(a) - set(g)))

print("\n--- B. what the graph reports ---")
g = run_graph([COUNT])
check("good SQL: success on attempt 1", g["success"] and g["attempts"] == 1, str(g["error"]))
check("good SQL: the whole path is recorded",
      g["path"] == ["generate", "extract", "safety", "schema_check", "execute", "semantic_check", "check", "finish"], str(g["path"]))
check("good SQL: a DataFrame comes back", isinstance(g["result"], pd.DataFrame) and g["result"].iloc[0]["n"] == 6)
check("runner is named", g["runner"] == "graph")
check("generation and execution times are recorded", g["generation_time"] >= 0 and g["execution_time"] >= 0)

g = run_graph(["SELECT nope FROM loads;", COUNT])
check("a repair shows in the path",
      g["path"] == ["generate", "extract", "safety", "schema_check", "repair",
                    "extract", "safety", "schema_check", "execute", "semantic_check", "check", "finish"], str(g["path"]))
check("the failed attempt is in the history",
      g["history"][0]["stage"] == "schema_validation" and g["history"][1]["stage"] == "completed", str(g["history"]))

g = run_graph(["DELETE FROM loads;"])
check("DELETE stops at stage safety without a repair",
      g["stage"] == "safety" and "repair" not in g["path"] and g["attempts"] == 1, str(g["path"]))
check("DELETE: nothing was deleted", db.run("SELECT COUNT(*) AS n FROM loads;").iloc[0]["n"] == 6)

g = run_graph(["SELECT a FROM loads;", "SELECT b FROM loads;", "SELECT c FROM loads;", COUNT])
check("the attempt budget is 3: a fourth answer is never asked for",
      (not g["success"]) and g["attempts"] == 3 and g["path"].count("repair") == 2, f"{g['attempts']} {g['path']}")

g = run_graph(["SELECT nope FROM loads;", "SELECT nope FROM loads;", COUNT])
check("a repeated query stops the loop (stage repeated_sql)",
      g["stage"] == "repeated_sql" and g["attempts"] == 2, f"{g['stage']} {g['attempts']}")

g = run_graph([], raise_on_call=RuntimeError("API down"))
check("an API error stops at stage generation",
      (not g["success"]) and g["stage"] == "generation" and "API down" in g["error"], str(g["error"]))

g = run_graph(["SELECT * FROM loads WHERE revenue < 0;", "SELECT * FROM loads WHERE revenue < -5;"])
check("two empty results give a successful, genuinely empty answer",
      g["success"] and g["result"] is not None and g["result"].empty, f"{g['success']} {g['stage']}")

print("\n--- C. the drawing ---")
text = build_panel_graph(None).get_graph().draw_mermaid()
check("the Mermaid drawing names every node",
      all(n in text for n in ["generate", "extract", "safety", "schema_check", "execute", "semantic_check", "check", "repair", "finish"]))
check("generate has no edge to repair (it cannot be repaired)", "generate -.-> repair" not in text)

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
