"""
End-to-end smoke test. Run after scripts.init_db:

    python -m scripts.smoke_test

Goes through ingest -> profile -> schema -> run_question for a few
representative questions and prints the stage reached for each.
Exit code is non-zero if any case behaves differently than expected.
"""

import os
import sys

from Modules.pipeline import ingest, profile, build_schema, run_question

DATA_DIR = os.getenv("DATA_DIR", "data/Logistics")

# (question, should_succeed)
CASES = [
    ("What is the total revenue in 2024?", True),
    ("Top 5 customers by revenue", True),
    ("What is the average salary of astronauts?", False),  # concept not in schema
]


def main():
    data = ingest(DATA_DIR)["data"]
    schema = build_schema(profile(data), save=False)

    mismatches = 0

    for question, should_succeed in CASES:
        out = run_question(question, schema)
        agent = out["agent"]

        ok = out["success"] == should_succeed
        if not ok:
            mismatches += 1

        rows = None if agent.get("result") is None else len(agent["result"])
        visual = out["visual"]["type"] if out.get("visual") else None

        print("-" * 70)
        print(f"{'PASS' if ok else 'FAIL'}  {question}")
        print(f"  expected success : {should_succeed}")
        print(f"  success / stage  : {out['success']} / {agent.get('stage')}")
        print(f"  error            : {agent.get('error')}")
        print(f"  sql              : {agent.get('sql')}")
        print(f"  rows / visual    : {rows} / {visual}")
        print(
            f"  times (s)        : gen {agent.get('generation_time', 0):.2f}"
            f" | val {agent.get('validation_time', 0):.2f}"
            f" | exec {agent.get('execution_time', 0):.2f}"
        )
        if out.get("visual_error"):
            print(f"  visual_error     : {out['visual_error']}")

    print("-" * 70)
    print(f"{len(CASES) - mismatches}/{len(CASES)} cases behaved as expected")
    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()