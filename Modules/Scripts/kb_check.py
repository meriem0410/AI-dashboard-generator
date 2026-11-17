"""
Modules/Scripts/kb_check.py

Retrieval check: for hand-written questions with known tables, does the
knowledge base select the right tables?

    python Modules/Scripts/kb_check.py Logistics
    python Modules/Scripts/kb_check.py Logistics --embedder hashing
    python Modules/Scripts/kb_check.py salesData --k 4
    python Modules/Scripts/kb_check.py Logistics --questions my_questions.json

The questions live in eval/retrieval_questions.json:
    [{"dataset": "Logistics", "question": "...", "tables": ["fuel_purchases", "drivers"]}, ...]
EDIT THE GOLD TABLES to match your real schema before trusting the numbers.

For each question it prints the tables selected and the recall (the share of
the gold tables that were selected). It also prints how many tables were kept
out of the total: that is the saving in prompt size. Every run is appended to
runs/retrieval_check.csv, so you can compare embedders and values of k.
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Modules.embeddings import get_embedder
from Modules.knowledge_base import KnowledgeBase
from Modules.pipeline import ingest, open_database

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("dataset", nargs="?", default="Logistics")
parser.add_argument("--embedder", default=None)
parser.add_argument("--k", type=int, default=4, help="tables kept by relevance (default 4)")
parser.add_argument("--max-tables", type=int, default=8)
parser.add_argument("--questions", default=str(ROOT / "eval" / "retrieval_questions.json"))
args = parser.parse_args()

items = [q for q in json.loads(Path(args.questions).read_text(encoding="utf-8"))
         if q.get("dataset") == args.dataset]
if not items:
    raise SystemExit(f"No questions for dataset '{args.dataset}' in {args.questions}")

data = ingest(str(ROOT / "data" / args.dataset), source_type="folder")["data"]
db = open_database(data)
embedder = get_embedder(args.embedder)
kb = KnowledgeBase.build(db, embedder=embedder)
total = len(kb.schema_info)
print(f"\nembedder={embedder.name}  k={args.k}  tables in dataset={total}\n")


precisions, recalls, f1_scores = [], [], []
hits = 0
sizes = []
total_tp = 0
total_fp = 0
total_fn = 0

for item in items:
    chosen = kb.select_tables(
        item["question"],
        k_tables=args.k,
        max_tables=args.max_tables
    )

    gold = set(item["tables"])
    retrieved = set(chosen)

    if not gold:
        raise ValueError(
            f"Question has no expected tables: {item['question']}"
        )

    true_positives = len(gold & retrieved)
    false_positives = len(retrieved - gold)
    false_negatives = len(gold - retrieved)

    precision = (
        true_positives / len(retrieved)
        if retrieved else 0.0
    )
    recall = true_positives / len(gold)

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0 else 0.0
    )

    precisions.append(precision)
    recalls.append(recall)
    f1_scores.append(f1)

    total_tp += true_positives
    total_fp += false_positives
    total_fn += false_negatives

    hits += recall == 1.0
    sizes.append(len(retrieved))

    flag = "OK  " if recall == 1.0 else "MISS"

    print(
        f"{flag} P={precision:.2f} "
        f"R={recall:.2f} F1={f1:.2f} "
        f"{item['question'][:48]:<48} -> {chosen}"
    )

# Macro averages: each question has equal weight.
mean_precision = sum(precisions) / len(precisions)
mean_recall = sum(recalls) / len(recalls)
mean_f1 = sum(f1_scores) / len(f1_scores)

# Micro averages: aggregate all table predictions.
micro_precision = (
    total_tp / (total_tp + total_fp)
    if total_tp + total_fp else 0.0
)
micro_recall = (
    total_tp / (total_tp + total_fn)
    if total_tp + total_fn else 0.0
)

print("\n" + "=" * 65)
print("RETRIEVAL EVALUATION")
print("=" * 65)
print(f"Questions evaluated : {len(items)}")
print(f"All gold found      : {hits}/{len(items)}")
print(f"Macro precision     : {mean_precision:.3f}")
print(f"Macro recall        : {mean_recall:.3f}")
print(f"Macro F1            : {mean_f1:.3f}")
print(f"Micro precision     : {micro_precision:.3f}")
print(f"Micro recall        : {micro_recall:.3f}")
print(
    f"Average tables kept : "
    f"{sum(sizes) / len(sizes):.1f} of {total}"
)
print("=" * 65)

# Save the expanded metrics to a new CSV.
# Use a new filename because the existing CSV has an older schema.
log = ROOT / "runs" / "retrieval_metrics_v2.csv"
log.parent.mkdir(exist_ok=True)

new = not log.exists()

with open(log, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)

    if new:
        w.writerow([
            "time",
            "dataset",
            "embedder",
            "k",
            "max_tables",
            "questions",
            "macro_precision",
            "macro_recall",
            "macro_f1",
            "micro_precision",
            "micro_recall",
            "all_found",
            "avg_tables_kept",
            "total_tables"
        ])

    w.writerow([
        datetime.now().isoformat(timespec="seconds"),
        args.dataset,
        embedder.name,
        args.k,
        args.max_tables,
        len(items),
        round(mean_precision, 3),
        round(mean_recall, 3),
        round(mean_f1, 3),
        round(micro_precision, 3),
        round(micro_recall, 3),
        hits,
        round(sum(sizes) / len(sizes), 2),
        total
    ])

print(f"\nMetrics saved to {log}")
db.close()

