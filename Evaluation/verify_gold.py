"""
Evaluation/verify_gold.py

Checks the reference answers BEFORE they are used, with two independent
derivations plus a plausibility read by you:

  1. the gold SQL runs on the data (DuckDB);
  2. the same answer is computed again in pandas, written differently
     (Evaluation/gold_<dataset>.py); the two results must agree;
  3. for rankings, a tie at the cut-off (the Nth and N+1th values equal) is
     flagged, because the "top N" is then not unique;
  4. for "unsupported" questions, the column names are searched for the terms
     the question needs; none may exist;
  5. a report shows each result so that YOU can judge plausibility.

    python -m Evaluation.verify_gold Logistics                  # report only
    python -m Evaluation.verify_gold Logistics --mark-verified  # write questions.json,
                                                                # verified=true only where checks 1-4 pass

Read Evaluation/results/verification_report.md before trusting a mark.
"""
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Evaluation.metrics import compare_results


def _head(df, n=6):
    if df is None:
        return "(none)"
    return df.head(n).to_string(index=False)


def tie_at_cutoff(db, sql):
    """For '... ORDER BY x DESC LIMIT N': is value N equal to value N+1?"""
    from Modules.sql_executor import execute_sql
    m = re.search(r"LIMIT\s+(\d+)\s*$", sql.strip().rstrip(";"), flags=re.IGNORECASE)
    if not m:
        return False
    n = int(m.group(1))
    probe = re.sub(r"LIMIT\s+\d+\s*$", f"LIMIT {n + 1}", sql.strip().rstrip(";"), flags=re.IGNORECASE)
    df = execute_sql(probe, db)
    if df is None or len(df) <= n:
        return False
    value_col = df.columns[-1]
    return df[value_col].iloc[n - 1] == df[value_col].iloc[n]


def verify_questions(data, db, questions, pandas_impls):
    """Return a list of dicts: id, status ('ok' | 'problem'), problems [...], gold, pandas."""
    from Modules.sql_executor import execute_sql
    # words of every column name ("operating_hours" -> operating, hours): a probe term must be a
    # whole word, otherwise "rating" would match "operating"
    all_words = {w for df in data.values() for c in df.columns for w in re.split(r"[^a-z0-9]+", str(c).lower()) if w}
    out = []
    for q in questions:
        rec = {"id": q["id"], "question": q["question"], "expected": q.get("expected", "answer"),
               "problems": [], "warnings": [], "gold": None, "pandas": None,
               "sql": q.get("gold_sql"), "definition": q.get("definition"), "alt": None}
        if rec["expected"] == "answer":
            try:
                rec["gold"] = execute_sql(q["gold_sql"], db)
            except Exception as exc:
                rec["problems"].append(f"gold SQL failed: {exc}")
            impl = pandas_impls.get(q["id"])
            if impl is None:
                rec["problems"].append("no independent pandas derivation")
            elif rec["gold"] is not None:
                try:
                    rec["pandas"] = impl(data)
                    cmp = compare_results(rec["gold"], rec["pandas"], ordered=bool(q.get("ordered")))
                    if not (cmp["match"] and cmp["exact"]):
                        rec["problems"].append(f"SQL and pandas disagree ({cmp['reason'] or 'shape'})")
                except Exception as exc:
                    rec["problems"].append(f"pandas derivation failed: {exc}")
                if rec["gold"] is not None and len(rec["gold"]) == 0:
                    rec["problems"].append("the gold result is empty")
            if q.get("alt_sql") and rec["gold"] is not None:
                # the tempting wrong query must give a DIFFERENT result, otherwise the question
                # cannot tell a careful answer from a careless one
                try:
                    rec["alt"] = execute_sql(q["alt_sql"], db)
                    if compare_results(rec["gold"], rec["alt"], ordered=bool(q.get("ordered")))["match"]:
                        rec["warnings"].append("the tempting wrong query gives the SAME result: "
                                               "this question does not discriminate")
                except Exception as exc:
                    rec["warnings"].append(f"the trap query failed: {exc}")
            if q.get("ordered") and rec["gold"] is not None and tie_at_cutoff(db, q["gold_sql"]):
                rec["problems"].append("tie at the top-N cut-off: the answer is not unique")
        elif rec["expected"] == "unsupported":
            hits = [t for t in q.get("probe_terms", []) if t.lower() in all_words]
            if not q.get("probe_terms"):
                rec["problems"].append("no probe_terms to search the columns with")
            if hits:
                rec["problems"].append(f"a column matches {hits}: the data may support this question")
        rec["status"] = "ok" if not rec["problems"] else "problem"
        out.append(rec)
    return out


def write_report(results, path):
    lines = ["# Verification report", "",
             f"{sum(r['status'] == 'ok' for r in results)}/{len(results)} questions pass the automatic checks.", ""]
    for r in results:
        lines += [f"## {r['id']}  [{r['status'].upper()}]  ({r['expected']})", "", r["question"], ""]
        if r["sql"]:
            lines += ["```sql", r["sql"], "```", ""]
        if r.get("definition"):
            lines.append(f"Definition used: {r['definition']}")
        for p in r["problems"]:
            lines.append(f"- PROBLEM: {p}")
        for w in r.get("warnings", []):
            lines.append(f"- WARNING: {w}")
        if r["gold"] is not None:
            lines += ["", "Gold result (first rows):", "```", _head(r["gold"]), "```"]
        if r["pandas"] is not None:
            lines += ["pandas result (first rows):", "```", _head(r["pandas"]), "```"]
        if r.get("alt") is not None:
            lines += ["Result of the tempting wrong query (must differ from the gold):", "```", _head(r["alt"]), "```"]
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dataset = args[0] if args else "Logistics"
    mark = "--mark-verified" in sys.argv
    module = importlib.import_module(f"Evaluation.gold_{dataset.lower()}")

    from Modules.pipeline import ingest, open_database
    data = ingest(str(ROOT / "data" / dataset), source_type="folder")["data"]
    db = open_database(data)
    results = verify_questions(data, db, module.Q, module.PANDAS)
    db.close()

    out_dir = ROOT / "Evaluation" / "results"
    out_dir.mkdir(exist_ok=True)
    write_report(results, out_dir / "verification_report.md")
    for r in results:
        print(f"{r['id']:<5}{r['status']:<9}{'; '.join(r['problems'] + ['WARNING: ' + w for w in r['warnings']])}")

    questions = []
    for q, r in zip(module.Q, results):
        q = dict(q)
        q["verified"] = bool(mark and r["status"] == "ok") or q.get("verified", False) and r["status"] == "ok"
        questions.append(q)
    target = ROOT / "Evaluation" / "questions.json"
    if mark:
        target.write_text(json.dumps(questions, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {target}: {sum(q['verified'] for q in questions)} verified of {len(questions)}")
    else:
        print("\nReport only. Read Evaluation/results/verification_report.md, then re-run with --mark-verified.")


if __name__ == "__main__":
    main()
