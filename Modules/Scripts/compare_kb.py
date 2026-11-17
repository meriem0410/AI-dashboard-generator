
"""
Modules/Scripts/compare_kb.py

Controlled comparison of Basic Schema RAG vs LLM-enriched Schema RAG.

Both knowledge bases use:
    - The same dataset
    - The same schema information
    - The same detected relationships
    - The same embedding model
    - The same evaluation questions
    - The same retrieval configurations

Only the dataset card changes.

Run from the project root:

    python Modules/Scripts/compare_kb.py Logistics

    python Modules/Scripts/compare_kb.py Logistics --embedder fastembed

    python Modules/Scripts/compare_kb.py Logistics --questions eval/retrieval_questions.json

Outputs:
    runs/schema_rag_comparison_<dataset>_<timestamp>/
        summary.csv
        per_question.csv
        metadata.json
        kb_basic/
        kb_llm/

The script requires a successful LLM run. If Groq fails and the
Data Agent falls back to basic mode, the benchmark stops rather
than reporting a misleading comparison.
"""

import argparse
import csv
import json
import math
import statistics
import sys
import time

from datetime import datetime
from pathlib import Path


# ------------------------------------------------------------
# PROJECT PATHS
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


from Modules.Agents.Agent_understand import understand_dataset
from Modules.embeddings import get_embedder
from Modules.knowledge_base import (
    KnowledgeBase,
    build_basic_card,
    collect_schema_info,
)
from Modules.pipeline import ingest, open_database
from Modules.relationships import detect_relationships


# ------------------------------------------------------------
# RETRIEVAL CONFIGURATIONS
# ------------------------------------------------------------

CONFIGS = [
    {"name": "k4_max8", "k": 4, "max_tables": 8},
    {"name": "k3_max4", "k": 3, "max_tables": 4},
    {"name": "k2_max4", "k": 2, "max_tables": 4},
]

DEFAULT_K_CHUNKS = 14


# ------------------------------------------------------------
# ARGUMENTS
# ------------------------------------------------------------

parser = argparse.ArgumentParser(description=__doc__)

parser.add_argument(
    "dataset",
    nargs="?",
    default="Logistics",
)

parser.add_argument(
    "--embedder",
    default="fastembed",
    choices=["fastembed", "hashing"],
)

parser.add_argument(
    "--questions",
    default=str(ROOT / "eval" / "retrieval_questions.json"),
)

parser.add_argument(
    "--k-chunks",
    type=int,
    default=DEFAULT_K_CHUNKS,
    help="Number of nearest chunks considered during retrieval.",
)

args = parser.parse_args()

if args.k_chunks < 1:
    raise SystemExit("--k-chunks must be at least 1")


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def precision_at_complete_recall(question_rows):
    """
    Average precision for questions where every required table
    was successfully retrieved (recall = 1).
    """
    complete_rows = [
        row for row in question_rows
        if math.isclose(
            float(row["recall"]),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9
        )
    ]

    if not complete_rows:
        return None

    return statistics.mean(
        float(row["precision"])
        for row in complete_rows
    )

def write_csv(path, rows):
    """Write dictionaries to a CSV file."""

    if not rows:
        return

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def percentile(values, percentile_value):
    """Calculate a percentile without requiring NumPy."""

    if not values:
        return 0.0

    ordered = sorted(values)

    index = math.ceil(
        percentile_value / 100 * len(ordered)
    ) - 1

    return ordered[max(0, index)]


def safe_divide(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def card_statistics(card):
    """Return useful information about the generated dataset card."""

    return {
        "tables": len(card.tables),
        "column_notes": len(card.columns),
        "glossary_entries": len(card.glossary),
        "kpi_ideas": len(card.kpi_ideas),
        "dataset_summary": card.dataset_summary,
    }


def validate_questions(items, schema_info):
    """Check that every question has valid expected table names."""

    valid_tables = set(schema_info)

    for i, item in enumerate(items, start=1):
        question = item.get("question", "").strip()
        gold = set(item.get("tables", []))

        if not question:
            raise ValueError(
                f"Question {i} has an empty question."
            )

        if not gold:
            raise ValueError(
                f"Question {i} has no expected tables: {question}"
            )

        unknown = gold - valid_tables

        if unknown:
            raise ValueError(
                f"Question {i} references unknown tables: "
                f"{sorted(unknown)}"
            )


# ------------------------------------------------------------
# EVALUATION OF ONE KNOWLEDGE BASE
# ------------------------------------------------------------

def evaluate_kb(
    kb,
    items,
    version,
    total_tables,
):
    """
    Evaluate one KB with all retrieval configurations.

    Returns:
        per_question_rows
        summary_rows
    """

    per_question_rows = []
    summary_rows = []

    for config in CONFIGS:

        config_name = config["name"]
        k = config["k"]
        max_tables = config["max_tables"]

        print(
            f"\n[{version.upper()}] "
            f"Configuration: {config_name}"
        )

        precisions = []
        recalls = []
        f1_scores = []
        jaccards = []
        retrieval_times = []

        total_tp = 0
        total_fp = 0
        total_fn = 0

        exact_matches = 0
        complete_recall = 0

        retrieved_sizes = []
        extra_sizes = []
        missing_sizes = []

        for index, item in enumerate(items, start=1):

            question = item["question"]
            gold = set(item["tables"])

            # Measure only the table-selection operation.
            start = time.perf_counter()

            chosen = kb.select_tables(
                question,
                k_tables=k,
                max_tables=max_tables,
                k_chunks=args.k_chunks,
            )

            elapsed_ms = (
                time.perf_counter() - start
            ) * 1000

            retrieval_times.append(elapsed_ms)

            retrieved = set(chosen)

            # ------------------------------------------------
            # CONFUSION COUNTS
            # ------------------------------------------------

            tp = len(gold & retrieved)
            fp = len(retrieved - gold)
            fn = len(gold - retrieved)

            # ------------------------------------------------
            # PER-QUESTION METRICS
            # ------------------------------------------------

            precision = safe_divide(
                tp,
                len(retrieved),
            )

            recall = safe_divide(
                tp,
                len(gold),
            )

            f1 = safe_divide(
                2 * precision * recall,
                precision + recall,
            )

            union = gold | retrieved

            jaccard = safe_divide(
                len(gold & retrieved),
                len(union),
            )

            exact_match = retrieved == gold

            full_recall = recall == 1.0

            precisions.append(precision)
            recalls.append(recall)
            f1_scores.append(f1)
            jaccards.append(jaccard)

            total_tp += tp
            total_fp += fp
            total_fn += fn

            exact_matches += int(exact_match)
            complete_recall += int(full_recall)

            retrieved_sizes.append(len(retrieved))
            extra_sizes.append(fp)
            missing_sizes.append(fn)

            # ------------------------------------------------
            # SAVE PER-QUESTION RESULTS
            # ------------------------------------------------

            row = {
                "version": version,
                "config": config_name,
                "k": k,
                "max_tables": max_tables,
                "question_id": index,
                "question": question,
                "gold_tables": json.dumps(sorted(gold)),
                "retrieved_tables": json.dumps(sorted(retrieved)),
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "jaccard": round(jaccard, 4),
                "exact_match": exact_match,
                "complete_recall": full_recall,
                "retrieved_count": len(retrieved),
                "retrieval_ms": round(elapsed_ms, 3),
            }

            per_question_rows.append(row)

            flag = "OK" if full_recall else "MISS"

            print(
                f"  {flag} "
                f"P={precision:.2f} "
                f"R={recall:.2f} "
                f"F1={f1:.2f} "
                f"J={jaccard:.2f} "
                f"({elapsed_ms:.1f} ms) "
                f"-> {sorted(retrieved)}"
            )

        # ----------------------------------------------------
        # AGGREGATE METRICS
        # ----------------------------------------------------

        n = len(items)

        macro_precision = statistics.mean(precisions)
        macro_recall = statistics.mean(recalls)
        macro_f1 = statistics.mean(f1_scores)
        macro_jaccard = statistics.mean(jaccards)

        micro_precision = safe_divide(
            total_tp,
            total_tp + total_fp,
        )

        micro_recall = safe_divide(
            total_tp,
            total_tp + total_fn,
        )

        micro_f1 = safe_divide(
            2 * micro_precision * micro_recall,
            micro_precision + micro_recall,
        )

        avg_retrieved = statistics.mean(retrieved_sizes)
        avg_extra = statistics.mean(extra_sizes)
        avg_missing = statistics.mean(missing_sizes)

        context_reduction = (
            1 - avg_retrieved / total_tables
        ) * 100 if total_tables else 0.0

        # ----------------------------------------------------
        # SUMMARY ROW
        # ----------------------------------------------------
        # Precision calculated only for questions with complete recall
        complete_recall_precisions = [
            precision
            for precision, recall in zip(precisions, recalls)
            if math.isclose(
                float(recall),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-9
            )
        ]

        precision_at_complete_recall = (
            statistics.mean(complete_recall_precisions)
            if complete_recall_precisions
            else None
        )
        summary = {
            "version": version,
            "config": config_name,
            "k": k,
            "max_tables": max_tables,
            "k_chunks": args.k_chunks,
            "questions": n,

            "macro_precision": round(macro_precision, 4),
            "macro_recall": round(macro_recall, 4),
            "macro_f1": round(macro_f1, 4),
            "macro_jaccard": round(macro_jaccard, 4),

            "micro_precision": round(micro_precision, 4),
            "micro_recall": round(micro_recall, 4),
            "micro_f1": round(micro_f1, 4),

            "exact_match_rate": round(
                exact_matches / n, 4
            ),

            "complete_recall_rate": round(
                complete_recall / n, 4
            ),

            "exact_matches": exact_matches,
            "complete_recall_questions": complete_recall,

            "avg_retrieved_tables": round(
                avg_retrieved, 2
            ),

            "avg_false_positives": round(avg_extra, 2),
            "avg_false_negatives": round(avg_missing, 2),

            "context_reduction_percent": round(
                context_reduction, 2
            ),

            "avg_retrieval_ms": round(
                statistics.mean(retrieval_times), 3
            ),

            "p95_retrieval_ms": round(
                percentile(retrieval_times, 95), 3
            ),
            "complete_recall_rate": round(
                complete_recall / n, 4
            ),

            "exact_matches": exact_matches,
            "complete_recall_questions": complete_recall,

            "precision_at_complete_recall": (
                round(precision_at_complete_recall, 4)
                if precision_at_complete_recall is not None
                else None
            ),
        
            "total_tp": total_tp,
            "total_fp": total_fp,
            "total_fn": total_fn,

            "total_dataset_tables": total_tables,
        }

        summary_rows.append(summary)

        print(
            f"\n  Macro F1: {macro_f1:.3f}"
            f" | Micro F1: {micro_f1:.3f}"
            f" | Macro P: {macro_precision:.3f}"
            f" | Macro R: {macro_recall:.3f}"
        )

    return per_question_rows, summary_rows


# ------------------------------------------------------------
# MAIN BENCHMARK
# ------------------------------------------------------------

def main():

    # --------------------------------------------------------
    # LOAD QUESTIONS
    # --------------------------------------------------------

    questions_path = Path(args.questions)

    if not questions_path.is_absolute():
        questions_path = ROOT / questions_path

    if not questions_path.exists():
        raise SystemExit(
            f"Questions file not found: {questions_path}"
        )

    items = [
        q
        for q in json.loads(
            questions_path.read_text(encoding="utf-8")
        )
        if q.get("dataset") == args.dataset
    ]

    if not items:
        raise SystemExit(
            f"No questions for dataset '{args.dataset}'."
        )

    print("\n" + "=" * 70)
    print("BASIC vs LLM-ENRICHED SCHEMA RAG BENCHMARK")
    print("=" * 70)
    print(f"Dataset          : {args.dataset}")
    print(f"Questions        : {len(items)}")
    print(f"Embedder         : {args.embedder}")
    print(f"Configurations   : {len(CONFIGS)}")
    print(f"Chunks per query : {args.k_chunks}")

    # --------------------------------------------------------
    # INGEST DATASET
    # --------------------------------------------------------

    data = ingest(
        str(ROOT / "data" / args.dataset),
        source_type="folder",
    )["data"]

    db = open_database(data)

    try:

        # ----------------------------------------------------
        # COMMON SCHEMA AND RELATIONSHIPS
        # ----------------------------------------------------

        print("\n[1/6] Collecting schema information...")

        start = time.perf_counter()

        schema_info = collect_schema_info(db)

        schema_time = time.perf_counter() - start

        total_tables = len(schema_info)

        print(
            f"  {total_tables} tables "
            f"in {schema_time:.2f} seconds"
        )

        print("\n[2/6] Detecting relationships...")

        start = time.perf_counter()

        relationships = detect_relationships(db)

        relationship_time = time.perf_counter() - start

        print(
            f"  {len(relationships)} relationships "
            f"in {relationship_time:.2f} seconds"
        )

        validate_questions(items, schema_info)

        # ----------------------------------------------------
        # BUILD BASIC CARD
        # ----------------------------------------------------

        print("\n[3/6] Creating the BASIC dataset card...")

        start = time.perf_counter()

        basic_card = build_basic_card(schema_info)

        basic_card_time = time.perf_counter() - start

        print(
            f"  {len(basic_card.tables)} table descriptions"
            f" | {len(basic_card.kpi_ideas)} KPI ideas"
            f" | {basic_card_time:.3f} seconds"
        )

        # ----------------------------------------------------
        # BUILD LLM CARD
        # ----------------------------------------------------

        print("\n[4/6] Running the LLM Data Agent...")

        start = time.perf_counter()

        llm_card, llm_trace = understand_dataset(
            db,
            use_llm=True,
            relationships=relationships,
            schema_info=schema_info,
        )

        llm_card_time = time.perf_counter() - start

        print(
            f"  Mode: {llm_trace['mode']}"
            f" | Tool calls: {llm_trace['calls']}"
            f" | Tools: {llm_trace['tools_used']}"
            f" | Dropped: {llm_trace['dropped']}"
            f" | {llm_card_time:.2f} seconds"
        )

        if llm_trace["mode"] != "llm":
            raise RuntimeError(
                "The Data Agent did not successfully use the LLM. "
                "Benchmark cancelled to avoid comparing two basic cards. "
                f"Reason: {llm_trace['fallback_reason']}"
            )

        # ----------------------------------------------------
        # INITIALIZE ONE SHARED EMBEDDER
        # ----------------------------------------------------

        print("\n[5/6] Building both knowledge bases...")

        embedder = get_embedder(args.embedder)

        # Warm up embedding inference before measuring retrieval.
        embedder.embed(["Schema RAG benchmark warmup"])

        # ----------------------------------------------------
        # BASIC KB
        # ----------------------------------------------------

        start = time.perf_counter()

        kb_basic = KnowledgeBase.build(
            db,
            card=basic_card,
            embedder=embedder,
            relationships=relationships,
            schema_info=schema_info,
        )

        basic_kb_time = time.perf_counter() - start

        # ----------------------------------------------------
        # LLM KB
        # ----------------------------------------------------

        start = time.perf_counter()

        kb_llm = KnowledgeBase.build(
            db,
            card=llm_card,
            embedder=embedder,
            relationships=relationships,
            schema_info=schema_info,
        )

        llm_kb_time = time.perf_counter() - start

        print(
            f"  Basic KB: {len(kb_basic.chunks)} chunks "
            f"in {basic_kb_time:.2f} seconds"
        )

        print(
            f"  LLM KB:   {len(kb_llm.chunks)} chunks "
            f"in {llm_kb_time:.2f} seconds"
        )

        # ----------------------------------------------------
        # OUTPUT DIRECTORY
        # ----------------------------------------------------

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        output_dir = (
            ROOT
            / "runs"
            / f"schema_rag_comparison_{args.dataset}_{timestamp}"
        )

        output_dir.mkdir(parents=True, exist_ok=True)

        # Preserve both KB versions for reproducibility.
        kb_basic.save(output_dir / "kb_basic")
        kb_llm.save(output_dir / "kb_llm")

        # ----------------------------------------------------
        # EVALUATE BASIC KB
        # ----------------------------------------------------

        print("\n[6/6] Evaluating retrieval performance...")

        basic_questions, basic_summary = evaluate_kb(
            kb=kb_basic,
            items=items,
            version="basic",
            total_tables=total_tables,
        )

        # ----------------------------------------------------
        # EVALUATE LLM KB
        # ----------------------------------------------------

        llm_questions, llm_summary = evaluate_kb(
            kb=kb_llm,
            items=items,
            version="llm",
            total_tables=total_tables,
        )

        # ----------------------------------------------------
        # SAVE RESULTS
        # ----------------------------------------------------

        all_questions = basic_questions + llm_questions
        all_summaries = basic_summary + llm_summary

        write_csv(
            output_dir / "per_question.csv",
            all_questions,
        )

        write_csv(
            output_dir / "summary.csv",
            all_summaries,
        )

        metadata = {
            "dataset": args.dataset,
            "timestamp": timestamp,
            "embedder": embedder.name,
            "embedding_dimension": embedder.dim,
            "questions_file": str(questions_path),
            "number_of_questions": len(items),
            "number_of_tables": total_tables,
            "number_of_relationships": len(relationships),
            "k_chunks": args.k_chunks,
            "configurations": CONFIGS,

            "timings_seconds": {
                "schema_collection": round(schema_time, 3),
                "relationship_detection": round(
                    relationship_time, 3
                ),
                "basic_card_generation": round(
                    basic_card_time, 3
                ),
                "llm_card_generation": round(
                    llm_card_time, 3
                ),
                "basic_kb_build": round(
                    basic_kb_time, 3
                ),
                "llm_kb_build": round(
                    llm_kb_time, 3
                ),
            },

            "basic_card": card_statistics(basic_card),
            "llm_card": card_statistics(llm_card),

            "llm_trace": llm_trace,

            "chunks": {
                "basic": len(kb_basic.chunks),
                "llm": len(kb_llm.chunks),
            },
        }

        (output_dir / "metadata.json").write_text(
            json.dumps(
                metadata,
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

        # ----------------------------------------------------
        # FINAL COMPARISON
        # ----------------------------------------------------

        print("\n" + "=" * 85)
        print("FINAL COMPARISON: BASIC vs LLM")
        print("=" * 85)

        print(
            f"{'Configuration':<15}"
            f"{'Version':<10}"
            f"{'Macro P':>10}"
            f"{'Macro R':>10}"
            f"{'Macro F1':>10}"
            f"{'Micro F1':>10}"
            f"{'Avg tables':>12}"
        )

        print("-" * 85)

        for row in all_summaries:
            print(
                f"{row['config']:<15}"
                f"{row['version']:<10}"
                f"{row['macro_precision']:>10.3f}"
                f"{row['macro_recall']:>10.3f}"
                f"{row['macro_f1']:>10.3f}"
                f"{row['micro_f1']:>10.3f}"
                f"{row['avg_retrieved_tables']:>12.2f}"
            )

        print("-" * 85)

        print("\nOUTPUT FILES")
        print(f"  Results       : {output_dir}")
        print(f"  Summary       : {output_dir / 'summary.csv'}")
        print(f"  Per question  : {output_dir / 'per_question.csv'}")
        print(f"  Metadata      : {output_dir / 'metadata.json'}")
        print(f"  Basic KB      : {output_dir / 'kb_basic'}")
        print(f"  LLM KB        : {output_dir / 'kb_llm'}")

        print("\nBenchmark completed successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
