"""
Modules/Scripts/build_kb.py

Builds the schema knowledge base of a dataset and saves it:
relationships, dataset card, text chunks, embeddings, FAISS index.

Run from the project root, virtual environment active:

    python Modules/Scripts/build_kb.py Logistics
    python Modules/Scripts/build_kb.py Logistics --llm          (the Data Agent writes the card)
    python Modules/Scripts/build_kb.py Logistics --embedder hashing

Options
    dataset        a folder under data/ (default Logistics)
    --llm          run the Data Agent (calls Groq; the cache applies if LLM_CACHE=on).
                   Without it the card is made from statistics only.
    --embedder     auto (default), fastembed or hashing
    --out          where to save (default: <DATA_DIR>/<dataset>/kb)
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from config import DATA_DIR
from Modules.Agents.Agent_understand import understand_dataset
from Modules.embeddings import get_embedder
from Modules.knowledge_base import KnowledgeBase, collect_schema_info
from Modules.pipeline import ingest, open_database
from Modules.relationships import describe, detect_relationships

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("dataset", nargs="?", default="Logistics")
parser.add_argument("--llm", action="store_true")
parser.add_argument("--embedder", default=None)
parser.add_argument("--out", default=None)
args = parser.parse_args()

out_dir = Path(args.out) if args.out else (ROOT / DATA_DIR / args.dataset / "kb")

data = ingest(str(ROOT / "data" / args.dataset), source_type="folder")["data"]
db = open_database(data)

t = time.perf_counter()
schema_info = collect_schema_info(db)
print(f"\nschema statistics: {time.perf_counter() - t:.1f} s")

t = time.perf_counter()
relationships = detect_relationships(db)
print(f"relationships: {len(relationships)} found in {time.perf_counter() - t:.1f} s")
for r in relationships:
    print("  ", describe(r), f"(inclusion {r['inclusion']})")

t = time.perf_counter()
card, trace = understand_dataset(db, use_llm=args.llm, relationships=relationships, schema_info=schema_info)
print(f"\ndataset card: mode={trace['mode']}  tool calls={trace['calls']}  "
      f"tools={trace['tools_used']}  dropped={trace['dropped']}  ({time.perf_counter() - t:.1f} s)")
if trace["fallback_reason"]:
    print("  model not used:", trace["fallback_reason"])
print("  summary:", card.dataset_summary)
for tc in card.tables:
    print(f"  - {tc.name}: {tc.description[:110]}")
if card.glossary:
    print("  glossary:", ", ".join(g.term for g in card.glossary))
print("  KPI ideas:")
for k in card.kpi_ideas[:10]:
    print(f"    * {k.name}: {k.question}")

t = time.perf_counter()
embedder = get_embedder(args.embedder)
kb = KnowledgeBase.build(db, card=card, embedder=embedder, relationships=relationships, schema_info=schema_info)
print(f"\nknowledge base: {len(kb.chunks)} chunks, embedder={embedder.name} ({embedder.dim} numbers each), "
      f"built in {time.perf_counter() - t:.1f} s")
kb.save(out_dir)
size = sum(p.stat().st_size for p in out_dir.iterdir())
print(f"saved to {out_dir}  ({size / 1024:.0f} KB)")
db.close()
