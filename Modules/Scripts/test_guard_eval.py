"""
Regression test of the safety layers: the whole attack / benign corpus of
Evaluation/guard_eval.py must stay at 100% / 100%, and every benign query must
run on the engine.

    python -m Modules.Scripts.test_guard_eval
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Evaluation.guard_eval import ATTACKS, BENIGN, evaluate

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


rows = evaluate()
missed = [a["sql"] for a in rows["attacks"] if not a["guard_blocked"]]
wrong = [b["sql"] for b in rows["benign"] if not b["guard_allowed"]]
broken = [(b["sql"], b.get("run_error")) for b in rows["benign"] if not b.get("runs")]

check("the corpus is not trivially small", len(ATTACKS) >= 50 and len(BENIGN) >= 30)
check("every attack is refused by the guard", not missed, str(missed))
check("no benign query is refused", not wrong, str(wrong))
check("every benign query runs on the engine", not broken, str(broken))
check("a trailing -- comment does not break the wrapped query",
      any(b["sql"].startswith("SELECT 1 -- DROP") and b["runs"] for b in rows["benign"]))
check("file and configuration attacks fail on the engine alone as well",
      all(a["engine_alone_blocked"] for a in rows["attacks"] if a["category"] in ("file-read", "file-write")))

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
