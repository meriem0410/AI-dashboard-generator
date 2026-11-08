"""
Modules/Scripts/compare_runs.py

Compares two tagged runs of run_questions.py question by question.

    python Modules/Scripts/compare_runs.py day1-agent day1-graph

For each question it shows the outcome of both runs and whether they agree
(same success, same stage, same number of attempts, same SQL). When both
runs used the cache, the same prompts get the same recorded answers, so a
correct graph must agree on every line.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
log_path = ROOT / "runs" / "run_log.jsonl"

if len(sys.argv) != 3:
    raise SystemExit("usage: python Modules/Scripts/compare_runs.py TAG_A TAG_B")
tag_a, tag_b = sys.argv[1], sys.argv[2]
if not log_path.exists():
    raise SystemExit(f"No log found at {log_path}")


def latest(tag):
    """The most recent record per question id for this tag."""
    found = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("tag") == tag:
            found[record["id"]] = record
    return found


def norm(sql):
    return " ".join(str(sql or "").lower().replace(";", " ").split())


a, b = latest(tag_a), latest(tag_b)
if not a or not b:
    raise SystemExit(f"No records for tag '{tag_a}' ({len(a)}) or '{tag_b}' ({len(b)}).")

print(f"\n{'id':<5}{tag_a + ' (ok/stage/tries)':<34}{tag_b + ' (ok/stage/tries)':<34}{'same SQL':<10}verdict")
agree = 0
ids = [i for i in a if i in b]
for qid in ids:
    ra, rb = a[qid], b[qid]
    left = f"{ra['success']}/{ra['stage']}/{ra['attempts']}"
    right = f"{rb['success']}/{rb['stage']}/{rb['attempts']}"
    same_sql = norm(ra["sql"]) == norm(rb["sql"])
    same = (ra["success"], ra["stage"], ra["attempts"]) == (rb["success"], rb["stage"], rb["attempts"]) and same_sql
    agree += same
    print(f"{qid:<5}{left:<34}{right:<34}{str(same_sql):<10}{'AGREE' if same else 'DIFFERENT'}")
print(f"\n{agree} of {len(ids)} questions agree.")
