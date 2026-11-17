"""
Evaluation/inspect_run.py

Look inside an evaluation run: which questions failed, what SQL was written, why.

    python -m Evaluation.inspect_run first                 # every case that was not correct
    python -m Evaluation.inspect_run first --id Q17        # one question, all conditions and runs
    python -m Evaluation.inspect_run first --all           # everything
    python -m Evaluation.inspect_run first --condition graph3_rag

Prints to the screen and writes Evaluation/results/<tag>_inspect.md.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "Evaluation" / "results"


def load(tag):
    path = RESULTS / f"{tag}.jsonl"
    if not path.exists():
        sys.exit(f"{path} not found")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag")
    ap.add_argument("--id")
    ap.add_argument("--condition")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    recs = load(a.tag)
    qfile = ROOT / "Evaluation" / "questions.json"
    questions = {q["id"]: q for q in json.loads(qfile.read_text(encoding="utf-8"))} if qfile.exists() else {}

    good = ("correct", "correct_decline")
    rows = [r for r in recs
            if (not a.id or r["id"] == a.id)
            and (not a.condition or r["condition"] == a.condition)
            and (a.all or a.id or r["outcome"] not in good)]

    lines = [f"# Inspection: {a.tag}", ""]
    rep = [r.get("replayed") for r in recs]
    if any(x is not None for x in rep):
        lines += [f"Answers replayed from the LLM cache: {sum(1 for x in rep if x)}/{len(rep)} "
                  "(a replayed answer was not generated again: timings and run-to-run stability "
                  "are then not measurements)", ""]
    else:
        lines += ["Cache information was not recorded in this run.", ""]
    lines += ["Outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(r["outcome"] for r in recs).items())), ""]
    if not rows:
        lines.append("Nothing to show with these filters.")
    for r in rows:
        q = questions.get(r["id"], {})
        lines += [f"## {r['id']}  {r['condition']}  run {r['run']}  ->  {r['outcome']}", "",
                  f"Question: {q.get('question', '?')}", ""]
        if q.get("gold_sql"):
            lines += ["Reference SQL:", "```sql", q["gold_sql"], "```"]
        lines += ["Generated SQL:", "```sql", str(r.get("sql")), "```",
                  f"stage={r.get('stage')} status={r.get('status')} attempts={r.get('attempts')} "
                  f"rows={r.get('rows')} (gold {r.get('gold_rows')}) seconds={r.get('seconds')} "
                  f"replayed={r.get('replayed')}"]
        if r.get("error"):
            lines.append(f"error/reason: {r['error']}")
        for k in ("assumptions", "notes"):
            if r.get(k):
                lines.append(f"{k}: {r[k]}")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    out = RESULTS / f"{a.tag}_inspect.md"
    out.write_text(text, encoding="utf-8")
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
