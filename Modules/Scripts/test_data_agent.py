"""
Modules/Scripts/test_data_agent.py

Offline tests for the Data Agent (Modules/Agents/Agent_understand.py) and for
the tool-call support of the LLM cache. A fake model answers in turn: it can
ask for tools or give text. No internet, no Groq call.

    python Modules/Scripts/test_data_agent.py
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

import numpy as np
import pandas as pd

import Modules.Agents.Agent_understand as agent_module
import Modules.sql_generator as generator_module
from Modules.Agents.Agent_understand import understand_dataset
from Modules.engine_duckdb import Database
from Modules.llm_cache import wrap_client

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


n = 100
data = {
    "drivers": pd.DataFrame({"driver_id": [f"D{i}" for i in range(10)],
                             "first_name": [f"N{i}" for i in range(10)]}),
    "trips": pd.DataFrame({"trip_id": range(n), "driver_id": [f"D{i % 10}" for i in range(n)],
                           "miles": np.linspace(100, 900, n),
                           "trip_status": ["completed", "cancelled"] * (n // 2),
                           "dispatch_date": pd.date_range("2022-01-01", periods=n, freq="D")}),
}
db = Database.from_dataframes(data)


class FakeModel:
    """Each item of the script is a string (a text reply) or a list of
    (tool name, arguments) pairs (a reply that asks for tools)."""

    def __init__(self, script, fail_with=None):
        self.queue = list(script)
        self.requests = []
        self.fail_with = fail_with
        outer = self

        def create(**kwargs):
            outer.requests.append(kwargs)
            if outer.fail_with:
                raise outer.fail_with
            item = outer.queue.pop(0) if outer.queue else "{}"
            if isinstance(item, list):
                calls = [SimpleNamespace(id=f"call{len(outer.requests)}_{i}", type="function",
                                         function=SimpleNamespace(name=name, arguments=json.dumps(args)))
                         for i, (name, args) in enumerate(item)]
                message = SimpleNamespace(content=None, tool_calls=calls)
            else:
                message = SimpleNamespace(content=item, tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def install(script, **kw):
    model = FakeModel(script, **kw)
    agent_module.client = model
    generator_module.client = model
    return model


CARD = json.dumps({
    "dataset_summary": "Trips driven by drivers.",
    "tables": [{"name": "trips", "description": "One row per completed or cancelled trip.", "entity": "trip"},
               {"name": "drivers", "description": "The drivers.", "entity": "driver"},
               {"name": "ghost_table", "description": "does not exist", "entity": "x"}],
    "columns": [{"table": "trips", "column": "trip_status", "description": "completed or cancelled"},
                {"table": "trips", "column": "no_such_column", "description": "invented"}],
    "glossary": [{"term": "mileage", "definition": "distance driven on a trip", "columns": ["trips.miles", "trips.fake"]},
                 {"term": "", "definition": "empty term", "columns": []}],
    "kpi_ideas": [{"name": "Average trip miles", "question": "What is the average trip distance?", "columns": ["trips.miles"]},
                  {"name": "Invented KPI", "question": "x", "columns": ["trips.nonexistent"]}],
})

print("\n--- A. the agent with tools ---")
model = install([[("schema_tool", {"table": "trips"})], "I have what I need.", CARD])
card, trace = understand_dataset(db, max_calls=8)
check("the model's card is used (mode llm)", trace["mode"] == "llm", str(trace))
check("one tool call was made and recorded", trace["calls"] == 1 and trace["tools_used"] == ["schema_tool"], str(trace))
check("the path is llm, tools, llm, finalize", trace["path"] == ["llm", "tools", "llm", "finalize"], str(trace["path"]))
check("the tools were offered to the model", {t["function"]["name"] for t in model.requests[0]["tools"]}
      == {"profile_tool", "schema_tool", "sql_tool"})
check("the first request already contains the dataset overview", "DATASET OVERVIEW" in model.requests[0]["messages"][1]["content"])
check("the tool result reached the model", "trip_status" in json.dumps(model.requests[1]["messages"]))
final_prompt = model.requests[-1]["messages"][-1]["content"]
check("the final call carries the tool evidence, as text", "EVIDENCE GATHERED" in final_prompt and "trip_status" in final_prompt)
check("the final call has no tools", "tools" not in model.requests[-1])
check("the final call asks for a JSON object", model.requests[-1].get("response_format") == {"type": "json_object"})
tables = {t.name: t for t in card.tables}
check("every real table is in the card, none invented", set(tables) == {"drivers", "trips"}, str(set(tables)))
check("the model's table description replaced the statistic one", tables["trips"].description.startswith("One row per"))
check("an invented column note is dropped, a real one kept",
      [(c.table, c.column) for c in card.columns] == [("trips", "trip_status")], str(card.columns))
check("an invalid column is removed from a glossary entry, the entry kept",
      card.glossary and card.glossary[0].columns == ["trips.miles"], str(card.glossary))
check("a glossary entry with no term is dropped", len(card.glossary) == 1)
check("a KPI idea on an invented column is dropped", all("Invented" not in k.name for k in card.kpi_ideas))
check("the model's KPI idea comes first, template ideas complete the list",
      card.kpi_ideas[0].name == "Average trip miles" and len(card.kpi_ideas) > 1)
check("the dropped items are counted", trace["dropped"] >= 5, str(trace["dropped"]))

print("\n--- B. budget and bad calls ---")
three = [("schema_tool", {"table": "trips"}), ("schema_tool", {"table": "drivers"}), ("profile_tool", {})]
model = install([three, [("schema_tool", {"table": "trips"})], CARD])
card, trace = understand_dataset(db, max_calls=2)
check("the budget of 2 tool calls is enforced", trace["calls"] == 2, str(trace))
check("a request beyond the budget goes straight to the final card", trace["path"] == ["llm", "tools", "llm", "finalize"], str(trace["path"]))
exhausted = [m for m in model.requests[1]["messages"] if m.get("role") == "tool"]
check("the tool call over budget is answered with 'budget exhausted'", any("budget exhausted" in m["content"] for m in exhausted))

model = install([[("no_such_tool", {})], "done", CARD])
card, trace = understand_dataset(db)
check("an unknown tool does not crash or use the budget", trace["mode"] == "llm" and trace["calls"] == 0, str(trace))

print("\n--- C. when the model fails the basic card is kept ---")
model = install(["done", "this is not json"])
card, trace = understand_dataset(db)
check("an invalid final answer falls back to the basic card", trace["mode"] == "basic" and trace["fallback_reason"], str(trace))
check("the basic card still describes every table", {t.name for t in card.tables} == {"drivers", "trips"} and all(t.description for t in card.tables))
check("the basic card still has KPI ideas", len(card.kpi_ideas) > 0)

model = install([], fail_with=RuntimeError("API down"))
card, trace = understand_dataset(db)
check("an API error falls back to the basic card", trace["mode"] == "basic" and "API down" in trace["fallback_reason"], str(trace))

model = install(["never used"])
card, trace = understand_dataset(db, use_llm=False)
check("use_llm=False makes no model call", len(model.requests) == 0 and trace["mode"] == "basic")

print("\n--- D. the cache records and replays tool calls ---")
with tempfile.TemporaryDirectory() as tmp:
    raw = FakeModel([[("schema_tool", {"table": "trips"})]])
    client = wrap_client(raw, mode="on", directory=tmp)
    request = dict(model="m", messages=[{"role": "user", "content": "inspect"}], temperature=0, tools=[{"type": "function"}])
    first = client.chat.completions.create(**request)
    second = client.chat.completions.create(**request)
    check("the first call goes to the model and returns a tool call",
          len(raw.requests) == 1 and first.choices[0].message.tool_calls[0].function.name == "schema_tool")
    call = second.choices[0].message.tool_calls[0]
    check("the replay returns the same tool call", call.function.name == "schema_tool"
          and json.loads(call.function.arguments) == {"table": "trips"} and call.id == first.choices[0].message.tool_calls[0].id)
    check("the replay needed no new model call", len(raw.requests) == 1)
    check("a replayed tool-call reply reports its finish reason", second.choices[0].finish_reason == "tool_calls")

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
