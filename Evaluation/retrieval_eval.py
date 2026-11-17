"""
Evaluation/retrieval_eval.py

Evaluates the schema retrieval (RAG) layer ALONE, with no language model and therefore no quota:
for every verified question, which tables does the reference SQL need, and did retrieval hand
them to the model?

    python -m Evaluation.retrieval_eval Logistics

Metrics (per question, then averaged)
  table recall     share of the needed tables that were retrieved. A missing table makes the
                   question unanswerable for the model, so this is the metric that matters.
  all-tables hit   1 when EVERY needed table was retrieved (the question can still be answered)
  precision        share of the retrieved tables that were needed (noise in the prompt)
  size             characters of retrieved schema / characters of the full schema (what is saved)

A small sweep over the retrieval settings shows the trade-off between recall and prompt size, so
the chosen configuration can be defended with numbers rather than by habit.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sqlglot
from sqlglot import exp

SWEEP = [  # (label, k_tables, max_tables)
    ("k2_max4 (default)", 2, 4),
    ("k3_max6", 3, 6),
    ("k4_max8", 4, 8),
]


def gold_tables(sql, known_tables):
    """Tables of the database that the SQL reads (CTE names and aliases are not tables)."""
    known = {t.lower(): t for t in known_tables}
    tree = sqlglot.parse_one(sql, read="duckdb")
    used = {known[t.name.lower()] for t in tree.find_all(exp.Table) if t.name.lower() in known}
    return sorted(used)


def retrieval_scores(questions, select_fn, size_fn, known_tables, full_size):
    """select_fn(question_text) -> list of tables; size_fn(tables) -> characters of schema text."""
    rows = []
    for q in questions:
        need = set(gold_tables(q["gold_sql"], known_tables))
        got = set(select_fn(q["question"]))
        rows.append({
            "id": q["id"], "category": q.get("category", ""), "need": sorted(need), "got": sorted(got),
            "missing": sorted(need - got),
            "recall": len(need & got) / len(need) if need else 1.0,
            "all": need <= got,
            "precision": len(need & got) / len(got) if got else 0.0,
            "size": size_fn(sorted(got)) / full_size if full_size else 1.0,
        })
    n = len(rows)
    summary = {
        "n": n,
        "recall": sum(r["recall"] for r in rows) / n if n else 0.0,
        "all_hit": sum(r["all"] for r in rows) / n if n else 0.0,
        "precision": sum(r["precision"] for r in rows) / n if n else 0.0,
        "size": sum(r["size"] for r in rows) / n if n else 0.0,
    }
    return rows, summary


def render(results):
    """results: list of (label, rows, summary)."""
    lines = ["# Schema retrieval: evaluation (no language model)", "",
             "For each verified question: the tables its reference SQL needs against the tables retrieval "
             "handed to the model. A missing table makes the question unanswerable for the model.", "",
             "| Setting | Questions | Table recall | All needed tables retrieved | Precision | Prompt size vs full schema |",
             "| --- | --- | --- | --- | --- | --- |"]
    for label, _, s in results:
        lines.append(f"| {label} | {s['n']} | {s['recall']:.3f} | {s['all_hit']:.1%} | {s['precision']:.3f} "
                     f"| {s['size']:.1%} |")
    for label, rows, _ in results:
        bad = [r for r in rows if not r["all"]]
        lines += ["", f"## Questions that lost a table: {label} ({len(bad)})", ""]
        if not bad:
            lines.append("None.")
            continue
        lines += ["| Question | Category | Needed | Retrieved | Missing |", "| --- | --- | --- | --- | --- |"]
        for r in bad:
            lines.append(f"| {r['id']} | {r['category']} | {', '.join(r['need'])} | {', '.join(r['got'])} "
                         f"| **{', '.join(r['missing'])}** |")
    return "\n".join(lines) + "\n"


def main():
    dataset = next((a for a in sys.argv[1:] if not a.startswith("--")), "Logistics")
    from Modules.pipeline import ingest, open_database
    from Modules.rag_context import get_kb, settings

    data = ingest(str(ROOT / "data" / dataset), source_type="folder")["data"]
    db = open_database(data)
    kb = get_kb(db)
    tables = list(data)
    full_size = len(kb.schema_text(tables))
    questions = [q for q in json.loads((ROOT / "Evaluation" / "questions.json").read_text(encoding="utf-8"))
                 if q.get("expected", "answer") == "answer" and q.get("verified")]
    base = settings()
    results = []
    for label, k, m in SWEEP:
        cfg = dict(base, k_tables=k, max_tables=m)
        rows, summary = retrieval_scores(questions, lambda text, c=cfg: kb.select_tables(text, **c),
                                         lambda ts: len(kb.schema_text(ts)), tables, full_size)
        results.append((label, rows, summary))
    text = render(results)
    out = ROOT / "Evaluation" / "results" / "retrieval_eval.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Written to {out}")
    db.close()


if __name__ == "__main__":
    main()
