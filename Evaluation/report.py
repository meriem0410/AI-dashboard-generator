"""
Evaluation/report.py

Turns a results file (Evaluation/results/<tag>.jsonl) into the tables of the
report: accuracy with 95% confidence intervals, precision / recall, the effect
of repair and retrieval, the failure taxonomy, and paired significance tests.

    python -m Evaluation.report first          # writes results/first_report.md
"""
import json
import statistics
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Evaluation.metrics import fmt_ci, mcnemar_exact

GUIDE = """## How to read this

- **Execution accuracy**: the query's *result* equals the verified reference result (rows as a set,
  extra columns allowed, numbers to 6 significant digits). Different SQL with the same result is correct.
- **Exact**: accuracy counting only results with no extra column.
- **Row precision / recall / F1**: on matched results, how many returned rows are right / how many right rows
  were returned (averaged over answerable questions; a result missing a gold column scores 0).
- **wrong_or_missing_column**: no column of the result matches a reference column (it is missing, or it holds
  other values: a wrong number, a wrong filter).
- **First-attempt accuracy**: correct with a single attempt. **Repair gain**: correct only after a retry.
- **Correct decline**: for questions the data cannot answer or that ask to change data, the system refuses
  with a reason. **Hallucinated answer**: it returned numbers anyway (the worst outcome).
- Intervals are 95% Wilson intervals; with about 25 questions they are wide, and a gap smaller than the
  interval is not evidence of a difference. The paired test (McNemar, exact) compares two conditions on the
  same questions.
"""


def load(tag):
    """All records; when a case was run again (resume), the LAST record counts."""
    path = RESULTS_DIR_FOR(tag)
    last = {}
    for l in path.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            last[(r["condition"], r["run"], r["id"])] = r
    return list(last.values())


def RESULTS_DIR_FOR(tag):
    p = Path(tag)
    return p if p.suffix == ".jsonl" else ROOT / "Evaluation" / "results" / f"{tag}.jsonl"


def summarise(records):
    infra = [r for r in records if r.get("outcome") == "infra_error"]
    records = [r for r in records if r.get("outcome") != "infra_error"]
    conds = list(dict.fromkeys(r["condition"] for r in records))
    lines = []
    if infra:
        per = Counter(r["condition"] for r in infra)
        lines += ["> **%d case(s) excluded** because the model service failed or refused (quota, outage), "
                  "not because of the pipeline: %s. Run the same command with `--resume` to run them again."
                  % (len(infra), ", ".join(f"{c}: {n}" for c, n in per.items())), ""]
    ans = {c: [r for r in records if r["condition"] == c and r["expected"] == "answer"] for c in conds}
    una = {c: [r for r in records if r["condition"] == c and r["expected"] != "answer"] for c in conds}

    # --- headline table
    lines += ["## Answerable questions", "",
              "| Condition | Questions x runs | Execution accuracy | Exact | Row precision | Row recall | F1 "
              "| First-attempt acc. | Repair gain | Mean attempts | Median s |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in conds:
        rs = ans[c]
        if not rs:
            continue
        n = len(rs)
        ok = sum(r["match"] for r in rs)
        first = sum(1 for r in rs if r["match"] and r["attempts"] == 1)
        gain = sum(1 for r in rs if r["match"] and r["attempts"] > 1)
        lines.append(
            f"| {c} | {n} | {fmt_ci(ok, n)} | {fmt_ci(sum(r['exact'] for r in rs), n)} "
            f"| {statistics.mean(r['precision'] for r in rs):.3f} | {statistics.mean(r['recall'] for r in rs):.3f} "
            f"| {statistics.mean(r['f1'] for r in rs):.3f} | {fmt_ci(first, n)} | {gain} "
            f"| {statistics.mean(r['attempts'] for r in rs):.2f} | {statistics.median(r['seconds'] for r in rs):.1f} |")

    # --- unanswerable
    if any(una.values()):
        lines += ["", "## Questions the data cannot answer, or that ask to change data", "",
                  "| Condition | Questions x runs | Correct decline | Hallucinated answer | No answer (failed) |",
                  "| --- | --- | --- | --- | --- |"]
        for c in conds:
            rs = una[c]
            if not rs:
                continue
            n = len(rs)
            cnt = Counter(r["outcome"] for r in rs)
            lines.append(f"| {c} | {n} | {fmt_ci(cnt['correct_decline'], n)} "
                         f"| {fmt_ci(cnt['hallucinated_answer'], n)} | {cnt['no_answer']} |")

    # --- by category
    cats = sorted({r["category"] for rs in ans.values() for r in rs})
    if len(cats) > 1:
        lines += ["", "## Accuracy by question category", "",
                  "| Category | " + " | ".join(conds) + " |", "| --- |" + " --- |" * len(conds)]
        for cat in cats:
            cells = []
            for c in conds:
                rs = [r for r in ans[c] if r["category"] == cat]
                cells.append(f"{sum(r['match'] for r in rs)}/{len(rs)}" if rs else "-")
            lines.append(f"| {cat or '(none)'} | " + " | ".join(cells) + " |")

    # --- failure taxonomy
    lines += ["", "## What went wrong (answerable questions that were not correct)", "",
              "| Outcome | " + " | ".join(conds) + " |", "| --- |" + " --- |" * len(conds)]
    outcomes = sorted({r["outcome"] for rs in ans.values() for r in rs if r["outcome"] != "correct"})
    for o in outcomes:
        lines.append(f"| {o} | " + " | ".join(str(sum(1 for r in ans[c] if r["outcome"] == o)) for c in conds) + " |")
    if not outcomes:
        lines.append("| (none) |" + " |" * len(conds))

    # --- stability across runs
    runs = sorted({r["run"] for r in records})
    if len(runs) > 1:
        lines += ["", "## Stability across runs", "",
                  "Share of questions whose outcome is identical in every run (temperature 0).", "",
                  "| Condition | Stable questions |", "| --- | --- |"]
        for c in conds:
            by_q = defaultdict(set)
            for r in records:
                if r["condition"] == c:
                    by_q[r["id"]].add(r["outcome"])
            lines.append(f"| {c} | {sum(1 for v in by_q.values() if len(v) == 1)}/{len(by_q)} |")

    # --- paired tests (first run)
    if len(conds) > 1:
        first = min(runs)
        lines += ["", "## Paired comparison (run 1, answerable questions)", "",
                  "| A vs B | A right, B wrong | A wrong, B right | p (exact McNemar) |", "| --- | --- | --- | --- |"]
        for a, b in combinations(conds, 2):
            ra = {r["id"]: r["match"] for r in ans[a] if r["run"] == first}
            rb = {r["id"]: r["match"] for r in ans[b] if r["run"] == first}
            ids = sorted(set(ra) & set(rb))
            if not ids:
                continue
            x, y, p = mcnemar_exact([ra[i] for i in ids], [rb[i] for i in ids])
            lines.append(f"| {a} vs {b} | {x} | {y} | {p:.3f} |")
    return "\n".join(lines)


def per_question(records):
    """A compact grid: which question each condition got right (run 1)."""
    conds = list(dict.fromkeys(r["condition"] for r in records))
    first = min(r["run"] for r in records)
    ids = list(dict.fromkeys(r["id"] for r in records))
    lines = ["## Per question (run %d)" % first, "", "| Question | Category | " + " | ".join(conds) + " |",
             "| --- | --- |" + " --- |" * len(conds)]
    for qid in ids:
        row = {r["condition"]: r for r in records if r["id"] == qid and r["run"] == first}
        cat = next((r["category"] for r in row.values()), "")
        lines.append(f"| {qid} | {cat} | " + " | ".join(row[c]["outcome"] if c in row else "-" for c in conds) + " |")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python -m Evaluation.report <tag>")
    tag = sys.argv[1]
    records = load(tag)
    if not records:
        sys.exit("empty results file")
    text = f"# Evaluation report: {tag}\n\n{GUIDE}\n{summarise(records)}\n\n{per_question(records)}\n"
    out = ROOT / "Evaluation" / "results" / f"{Path(tag).stem}_report.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
