"""
Tests for Evaluation/run_eval.py and report.py with fake pipelines (no model).

    python -m Modules.Scripts.test_eval_runner
"""
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Evaluation.report import summarise, per_question
from Evaluation.run_eval import classify, is_infra_error, load_questions, run_evaluation, wait_seconds
from Modules.engine_duckdb import Database
from Modules.sql_executor import execute_sql

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


trips = pd.DataFrame({"trip_id": range(1, 21), "driver_id": [f"D{(i % 4) + 1}" for i in range(20)],
                      "miles": [100 + 5 * i for i in range(20)]})
db = Database.from_dataframes({"trips": trips})

QUESTIONS = [
    {"id": "Q1", "question": "total miles", "category": "aggregation", "expected": "answer",
     "gold_sql": "SELECT SUM(miles) AS total FROM trips", "verified": True},
    {"id": "Q2", "question": "miles per driver", "category": "group", "expected": "answer",
     "gold_sql": "SELECT driver_id, SUM(miles) AS m FROM trips GROUP BY driver_id", "verified": True},
    {"id": "Q3", "question": "top 2 drivers", "category": "ranking", "expected": "answer", "ordered": True,
     "gold_sql": "SELECT driver_id, SUM(miles) AS m FROM trips GROUP BY driver_id ORDER BY m DESC LIMIT 2",
     "verified": True},
    {"id": "Q4", "question": "driver satisfaction", "category": "unsupported", "expected": "unsupported", "verified": True},
    {"id": "Q5", "question": "delete trips", "category": "blocked", "expected": "blocked", "verified": True},
    {"id": "Q6", "question": "not verified yet", "category": "x", "expected": "answer",
     "gold_sql": "SELECT 1", "verified": False},
]


def ok(sql):
    return {"success": True, "stage": "completed", "result": execute_sql(sql, db), "sql": sql,
            "attempts": 1, "status": "ok"}


def perfect(item, schema, database):
    sql = {"Q1": "SELECT SUM(miles) AS s FROM trips",
           "Q2": "SELECT driver_id, SUM(miles) AS miles, COUNT(*) AS n FROM trips GROUP BY 1",
           "Q3": "SELECT driver_id, SUM(miles) AS m FROM trips GROUP BY 1 ORDER BY m DESC LIMIT 2"}.get(item["id"])
    if sql:
        return ok(sql)
    if item["expected"] == "unsupported":
        return {"success": False, "stage": "unsupported", "status": "unsupported", "error": "no such data", "attempts": 1}
    return {"success": False, "stage": "blocked", "status": "blocked", "error": "read-only", "attempts": 1}


def sloppy(item, schema, database):
    if item["id"] == "Q1":
        return ok("SELECT AVG(miles) AS s FROM trips")                       # wrong measure
    if item["id"] == "Q2":
        return {"success": False, "stage": "execution", "error": "binder error", "attempts": 3}
    if item["id"] == "Q3":
        return ok("SELECT driver_id, SUM(miles) AS m FROM trips GROUP BY 1 ORDER BY m ASC LIMIT 2")  # wrong top
    return ok("SELECT COUNT(*) AS n FROM trips")                              # answers the unanswerable


runners = {"perfect": perfect, "sloppy": sloppy}

print("\n--- loading questions ---")
tmp = Path(tempfile.mkdtemp())
qfile = tmp / "q.json"
qfile.write_text(json.dumps(QUESTIONS), encoding="utf-8")
kept, skipped = load_questions(qfile)
check("unverified questions are skipped", len(kept) == 5 and skipped == 1)
check("unverified questions can be included", len(load_questions(qfile, True)[0]) == 6)
bad = tmp / "bad.json"
bad.write_text(json.dumps([{"id": "X", "question": "q", "verified": True}]), encoding="utf-8")
try:
    load_questions(bad)
    check("an answerable question without gold SQL is refused", False)
except ValueError:
    check("an answerable question without gold SQL is refused", True)

print("\n--- running ---")
out = tmp / "r.jsonl"
logged = []
recs = run_evaluation(db, "SCHEMA", kept, runners, ["perfect", "sloppy"], 2, out, tag="t", log=logged.append)
by = {(r["condition"], r["run"], r["id"]): r for r in recs}
check("records = conditions x runs x questions", len(recs) == 2 * 2 * 5)
check("a differently written but equivalent query is correct", by[("perfect", 1, "Q1")]["outcome"] == "correct")
check("extra columns are accepted", by[("perfect", 1, "Q2")]["match"] and not by[("perfect", 1, "Q2")]["exact"])
check("a ranking in the right order is correct", by[("perfect", 1, "Q3")]["outcome"] == "correct")
check("correct decline for unsupported", by[("perfect", 1, "Q4")]["outcome"] == "correct_decline")
check("correct decline for a blocked request", by[("perfect", 1, "Q5")]["outcome"] == "correct_decline")
check("wrong measure is labelled wrong_result", by[("sloppy", 1, "Q1")]["outcome"].startswith("wrong_result"))
check("an execution failure is labelled with its stage", by[("sloppy", 1, "Q2")]["outcome"] == "failed:execution")
check("the wrong top-N is not correct", by[("sloppy", 1, "Q3")]["outcome"] != "correct")
check("answering the unanswerable is a hallucination", by[("sloppy", 1, "Q4")]["outcome"] == "hallucinated_answer")
check("attempts are recorded", by[("sloppy", 1, "Q2")]["attempts"] == 3)

print("\n--- resume and protection ---")
try:
    run_evaluation(db, "S", kept, runners, ["perfect"], 1, out, tag="t", log=lambda *_: None)
    check("an existing results file is not overwritten", False)
except FileExistsError:
    check("an existing results file is not overwritten", True)
lines_before = len(out.read_text().splitlines())
again = run_evaluation(db, "S", kept, runners, ["perfect", "sloppy"], 2, out, tag="t", resume=True, log=lambda *_: None)
check("resume re-runs nothing that is done", len(out.read_text().splitlines()) == lines_before and len(again) == lines_before)

def crashing(item, schema, database):
    raise RuntimeError("API down")

crash_recs = run_evaluation(db, "S", kept[:2], {"c": crashing}, ["c"], 1, tmp / "c.jsonl", log=lambda *_: None)
check("a crash is recorded, not raised", crash_recs[0]["outcome"] == "failed:crash" and "API down" in crash_recs[0]["error"])

print("\n--- the report ---")
text = summarise(recs)
check("report has the accuracy table", "Execution accuracy" in text and "| perfect |" in text and "| sloppy |" in text)
check("perfect scores 3/3 on answerable (x2 runs = 6/6)", "(6/6)" in text)
check("report shows hallucinated answers", "Hallucinated answer" in text)
check("report has the paired test", "McNemar" in text and "perfect vs sloppy" in text)
check("report has the stability table", "Stability across runs" in text)
check("report lists failure outcomes", "failed:execution" in text)
check("per-question grid", "| Q1 |" in per_question(recs))

print("\n--- service limits (quota, outage) ---")
LIMIT = ("Error code: 429 - Rate limit reached for model x on tokens per day (TPD): Limit 200000, Used 198406. "
         "Please try again in 5m35.664s.")
check("a 429 is recognised as a service error", is_infra_error({"success": False, "stage": "generation", "error": LIMIT}))
check("a normal failure is not", not is_infra_error({"success": False, "stage": "execution", "error": "binder error"}))
check("a decline is never a service error", not is_infra_error({"success": False, "status": "unsupported", "error": "429 rows"}))
check("the wait is read from the message (5m35.664s + margin)", abs(wait_seconds(LIMIT) - 338.664) < 0.01)
check("the wait is capped", wait_seconds("try again in 99m1s") == 900)
check("a default wait when nothing is said", wait_seconds("rate limit") == 30)

calls = {"n": 0}
def flaky(item, schema, database):
    calls["n"] += 1
    if calls["n"] <= 2:
        return {"success": False, "stage": "generation", "error": LIMIT, "attempts": 1}
    return ok("SELECT SUM(miles) AS s FROM trips")

waits = []
r = run_evaluation(db, "S", kept[:1], {"f": flaky}, ["f"], 1, tmp / "f.jsonl", log=lambda *_: None, sleep=waits.append,
                   max_wait=None)
check("a service error is waited out and retried", r[0]["outcome"] == "correct" and len(waits) == 2 and waits[0] > 300, (r[0]["outcome"], waits))

def always_limited(item, schema, database):
    return {"success": False, "stage": "generation", "error": LIMIT, "attempts": 1}

waits = []
r = run_evaluation(db, "S", kept[:2], {"a": always_limited}, ["a"], 1, tmp / "a.jsonl", log=lambda *_: None,
                   sleep=waits.append, infra_retries=2, max_wait=None)
check("a persistent service error is labelled infra_error", all(x["outcome"] == "infra_error" for x in r) and len(waits) == 4)
txt = summarise(r + [dict(r[0], condition="a2", outcome="correct", match=True, exact=True, f1=1.0, precision=1.0, recall=1.0)])
check("the report excludes infra errors and says so", "excluded" in txt and "a: 2" in txt)
again = run_evaluation(db, "S", kept[:2], {"a": perfect}, ["a"], 1, tmp / "a.jsonl", resume=True, log=lambda *_: None)
check("resume runs infra_error cases again", [x["outcome"] for x in again] == ["correct", "correct"], [x["outcome"] for x in again])
from Evaluation.report import load as load_report
check("the report keeps the last record of a re-run case", {x["outcome"] for x in load_report(tmp / "a.jsonl")} == {"correct"})

waits, lg = [], []
r = run_evaluation(db, "S", kept[:2], {"a": always_limited}, ["a"], 1, tmp / "w.jsonl", log=lg.append,
                   sleep=waits.append, max_wait=60)
check("a long wait (daily quota) stops the run at once, without sleeping or recording a failure",
      r == [] and waits == [] and any("--resume" in str(x) for x in lg) and not (tmp / "w.jsonl").exists()
      or (r == [] and waits == [] and (tmp / "w.jsonl").read_text() == ""))

print("\n--- token budget ---")
lg = []
r = run_evaluation(db, "S", kept, {"p": perfect}, ["p"], 1, tmp / "b.jsonl", log=lg.append,
                   budget_tokens=250, tokens_per_call=100)
check("the run stops cleanly at the budget", len(r) == 3 and any("budget" in str(x) for x in lg), len(r))
r = run_evaluation(db, "S", kept, {"p": perfect}, ["p"], 1, tmp / "b.jsonl", resume=True, log=lambda *_: None,
                   budget_tokens=10 ** 9, tokens_per_call=100)
check("resume finishes the rest", len(r) == 5 and all("real_calls" in x for x in r[3:]))

check("classify: gold column missing is not a match",
      not classify({"expected": "answer", "id": "z"}, {"success": True, "result": pd.DataFrame({"a": [1]})},
                   pd.DataFrame({"b": [9]}))["match"])

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
