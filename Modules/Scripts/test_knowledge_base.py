"""
Modules/Scripts/test_knowledge_base.py

Offline tests for relationship detection, the embedders and the schema
knowledge base. No internet, no model download, no Groq call (the neural
embedder is replaced by the hashing one).

    python Modules/Scripts/test_knowledge_base.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

import numpy as np
import pandas as pd

import Modules.embeddings as embeddings_module
from Modules.embeddings import HashingEmbedder, get_embedder
from Modules.engine_duckdb import Database
from Modules.knowledge_base import KnowledgeBase, build_basic_card, collect_schema_info
from Modules.relationships import detect_relationships

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


n = 200
dates = pd.date_range("2022-01-01", periods=n, freq="D")
data = {
    "customers": pd.DataFrame({"customer_id": [f"C{i}" for i in range(20)],
                               "customer_name": [f"Customer {i}" for i in range(20)]}),
    "drivers": pd.DataFrame({"driver_id": [f"D{i}" for i in range(20)],
                             "first_name": [f"Name{i}" for i in range(20)],
                             "last_name": ["X"] * 20,
                             "hire_date": pd.date_range("2010-01-01", periods=20, freq="90D")}),
    "routes": pd.DataFrame({"route_id": [f"R{i}" for i in range(10)],
                            "origin_city": [f"City{i}" for i in range(10)],
                            "destination_city": [f"Town{i}" for i in range(10)]}),
    "loads": pd.DataFrame({"load_id": [f"L{i}" for i in range(n)],
                           "customer_id": [f"C{i % 20}" for i in range(n)],
                           "route_id": [f"R{i % 10}" for i in range(n)],
                           "load_date": dates, "revenue": np.linspace(500, 5000, n)}),
    "trips": pd.DataFrame({"trip_id": [f"T{i}" for i in range(n)],
                           "load_id": [f"L{i}" for i in range(n)],
                           "driver_id": [f"D{i % 20}" for i in range(n)],
                           "dispatch_date": dates, "miles": np.linspace(100, 900, n),
                           "trip_status": ["completed", "cancelled"] * (n // 2)}),
    "fuel_purchases": pd.DataFrame({"fuel_id": range(400),
                                    "trip_id": [f"T{i % n}" for i in range(400)],
                                    "driver_id": [f"D{i % 20}" for i in range(400)],
                                    "purchase_date": pd.date_range("2022-01-01", periods=400, freq="12h"),
                                    "gallons": np.linspace(50, 200, 400),
                                    "total_cost": np.linspace(200, 900, 400)}),
    "safety_incidents": pd.DataFrame({"incident_id": range(15),
                                      "trip_id": [f"T{i % 5}" for i in range(15)],
                                      "incident_type": ["collision", "spill", "delay"] * 5,
                                      "incident_date": pd.date_range("2022-02-01", periods=15, freq="10D")}),
    "inspections": pd.DataFrame({"trip_id": [f"T{i}" for i in range(10)],
                                 "result": ["pass"] * 10}),
    "ghost": pd.DataFrame({"trip_id": [f"X{i}" for i in range(10)], "note": ["a"] * 10}),
}
db = Database.from_dataframes(data)

print("\n--- A. relationships ---")
rels = detect_relationships(db)
found = {(r["one_table"], r["many_table"], r["column"], r["cardinality"]) for r in rels}
check("customers -> loads on customer_id, one-to-many", ("customers", "loads", "customer_id", "one-to-many") in found, str(found))
check("routes -> loads on route_id, one-to-many", ("routes", "loads", "route_id", "one-to-many") in found)
check("loads <-> trips on load_id is one-to-one", ("loads", "trips", "load_id", "one-to-one") in found, str(found))
check("trips -> fuel_purchases on trip_id, one-to-many", ("trips", "fuel_purchases", "trip_id", "one-to-many") in found)
check("drivers -> trips on driver_id, one-to-many", ("drivers", "trips", "driver_id", "one-to-many") in found)
check("drivers -> fuel_purchases on driver_id, one-to-many", ("drivers", "fuel_purchases", "driver_id", "one-to-many") in found)
check("trips -> safety_incidents on trip_id, one-to-many", ("trips", "safety_incidents", "trip_id", "one-to-many") in found)
check("a unique column whose values all exist in trips is one-to-one (inspections)",
      ("trips", "inspections", "trip_id", "one-to-one") in found, str(found))
check("two non-unique columns are not a relationship (fuel vs incidents on trip_id)",
      not any({r["one_table"], r["many_table"]} == {"fuel_purchases", "safety_incidents"} for r in rels))
check("values that do not exist on the other side are not a relationship (ghost.trip_id)",
      not any("ghost" in (r["one_table"], r["many_table"]) for r in rels), str([r for r in rels if "ghost" in (r["one_table"], r["many_table"])]))
check("every relationship reports its inclusion", all(0.9 <= r["inclusion"] <= 1.0 for r in rels))

print("\n--- B. embedders ---")
h = HashingEmbedder()
v = h.embed(["fuel cost per driver", "revenue per customer", ""])
check("hashing vectors have the declared size", v.shape == (3, h.dim))
check("hashing vectors are unit length (the empty text is zero)", abs(float(np.linalg.norm(v[0])) - 1) < 1e-5 and float(np.linalg.norm(v[2])) == 0.0)
check("the same text gives the same vector", np.allclose(h.embed(["fuel cost"]), h.embed(["fuel cost"])))
sim = lambda a, b: float((h.embed([a]) @ h.embed([b]).T)[0, 0])
check("shared words are closer than unrelated words",
      sim("fuel purchases cost", "total fuel cost") > sim("fuel purchases cost", "safety incident type"))
check("plural and singular match", sim("drivers", "driver") > 0.6, str(sim("drivers", "driver")))
check("snake_case names are split into words", sim("fuel_purchases", "fuel purchases") > 0.9, str(sim("fuel_purchases", "fuel purchases")))

real = embeddings_module.FastEmbedEmbedder


class Broken:
    def __init__(self, *a, **k):
        raise RuntimeError("no network")


embeddings_module.FastEmbedEmbedder = Broken
fallback = get_embedder("auto")
embeddings_module.FastEmbedEmbedder = real
check("auto falls back to hashing when the neural model cannot load", fallback.name == "hashing")
check("an explicit hashing request works", get_embedder("hashing").name == "hashing")

print("\n--- C. the knowledge base ---")
info = collect_schema_info(db)
check("schema info exists for every table", set(info) == set(data))
kb = KnowledgeBase.build(db, embedder=HashingEmbedder(), relationships=rels, schema_info=info)
kinds = [c["kind"] for c in kb.chunks]
check("one table chunk per table", kinds.count("table") == len(data))
check("one column chunk per column", kinds.count("column") == sum(len(d.columns) for d in data.values()))
check("one relation chunk per relationship", kinds.count("relation") == len(rels))
check("KPI idea chunks come from the basic card", kinds.count("kpi") > 0)
check("every chunk has an id and text", all(c["text"] and c["id"] == i for i, c in enumerate(kb.chunks)))

def tables_for(q, **kw):
    return kb.select_tables(q, **kw)

t = tables_for("total fuel cost per driver")
check("fuel cost per driver -> fuel_purchases and drivers", {"fuel_purchases", "drivers"} <= set(t), str(t))
t = tables_for("total revenue per customer")
check("revenue per customer -> loads and customers", {"loads", "customers"} <= set(t), str(t))
t = tables_for("how many safety incidents by type", k_tables=2)
check("safety incidents by type -> safety_incidents", "safety_incidents" in t, str(t))
t = tables_for("average miles per trip", k_tables=1)
check("a table that holds ids gets the table that holds their names (trips -> drivers)", "trips" in t and "drivers" in t, str(t))
t = tables_for("revenue and fuel cost", k_tables=2)
check("a table that joins two selected tables is added (loads, fuel_purchases -> trips)",
      {"loads", "fuel_purchases", "trips"} <= set(t), str(t))
check("the selection never exceeds max_tables", len(tables_for("everything about everything", k_tables=8, max_tables=5)) <= 5)
check("a question with no matching word still returns tables", len(tables_for("zzzz qqqq")) > 0)

ctx = kb.context("total fuel cost per driver")
text = ctx["schema_text"]
check("schema text has the coverage block", "DATA COVERAGE" in text and "purchase_date" in text)
check("schema text shows roles", "[measure]" in text and "[id]" in text and "[date]" in text)
check("schema text lists the relationships between the selected tables", "RELATIONSHIPS" in text and "drivers.driver_id" in text, text[:500])
check("schema text leaves out tables that were not selected", "safety_incidents" not in text and "ghost" not in text)
check("schema text is shorter than the full schema", len(text) < len(kb.schema_text()))
check("sample values appear for text columns", "completed" in kb.schema_text(["trips"]))

print("\n--- D. save and load ---")
with tempfile.TemporaryDirectory() as tmp:
    kb.save(tmp)
    expected = {"index.faiss", "chunks.json", "schema_info.json", "relationships.json", "card.json", "meta.json"}
    check("all files are written", expected <= {p.name for p in Path(tmp).iterdir()})
    loaded = KnowledgeBase.load(tmp, embedder=HashingEmbedder())
    check("the loaded base has the same chunks", len(loaded.chunks) == len(kb.chunks))
    check("the loaded base selects the same tables",
          loaded.select_tables("total fuel cost per driver") == kb.select_tables("total fuel cost per driver"))
    meta = json.loads((Path(tmp) / "meta.json").read_text())
    meta["embedder"] = "something-else"
    (Path(tmp) / "meta.json").write_text(json.dumps(meta))
    try:
        KnowledgeBase.load(tmp, embedder=HashingEmbedder())
        check("an index built with another embedder is refused", False)
    except ValueError:
        check("an index built with another embedder is refused", True)

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
