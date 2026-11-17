"""
Tests for Evaluation/retrieval_eval.py (no model, no embeddings).

    python -m Modules.Scripts.test_retrieval_eval
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Evaluation.retrieval_eval import gold_tables, render, retrieval_scores

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


T = ["trips", "loads", "customers", "drivers"]
check("one table", gold_tables("SELECT COUNT(*) FROM trips", T) == ["trips"])
check("joins and aliases", gold_tables(
    "SELECT c.customer_type FROM trips t JOIN loads l ON t.load_id = l.load_id "
    "JOIN customers c ON l.customer_id = c.customer_id", T) == ["customers", "loads", "trips"])
check("a CTE name is not a table", gold_tables(
    "WITH f AS (SELECT * FROM trips) SELECT * FROM f JOIN drivers d ON 1=1", T) == ["drivers", "trips"])
check("subquery tables are found", gold_tables("SELECT * FROM (SELECT * FROM loads) q", T) == ["loads"])
check("names are case-insensitive", gold_tables("SELECT 1 FROM TRIPS", T) == ["trips"])

Q = [{"id": "a", "category": "x", "question": "one table", "gold_sql": "SELECT 1 FROM trips"},
     {"id": "b", "category": "y", "question": "needs three",
      "gold_sql": "SELECT 1 FROM trips t JOIN loads l ON 1=1 JOIN customers c ON 1=1"}]
retrieved = {"one table": ["trips", "drivers"], "needs three": ["trips", "loads"]}
rows, s = retrieval_scores(Q, lambda text: retrieved[text], lambda ts: 100 * len(ts), T, 400)
check("recall per question", rows[0]["recall"] == 1.0 and abs(rows[1]["recall"] - 2 / 3) < 1e-9)
check("a lost table is reported", rows[1]["missing"] == ["customers"] and not rows[1]["all"] and rows[0]["all"])
check("precision counts noise", rows[0]["precision"] == 0.5 and rows[1]["precision"] == 1.0)
check("size is relative to the full schema", abs(rows[0]["size"] - 0.5) < 1e-9)
check("summary: all-hit share, mean recall", s["all_hit"] == 0.5 and abs(s["recall"] - (1 + 2 / 3) / 2) < 1e-9)
text = render([("cfg", rows, s)])
check("the report names the question that lost a table", "**customers**" in text and "| b |" in text)
rows2, s2 = retrieval_scores(Q, lambda text: T, lambda ts: 100 * len(ts), T, 400)
check("retrieving everything: recall 1, size 100%", s2["recall"] == 1.0 and abs(s2["size"] - 1.0) < 1e-9)
check("no lost table: the report says None", "None." in render([("cfg", rows2, s2)]))

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
