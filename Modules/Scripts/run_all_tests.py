"""
Modules/Scripts/run_all_tests.py

Runs every offline test script and prints one summary line per script.
No internet, no Groq call.

    python Modules/Scripts/run_all_tests.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [
    "test_migration.py",
    "test_tools_and_schemas.py",
    "test_graph_panel.py",
    "test_llm_cache.py",
    "test_semantic_checks.py",
    "test_day2.py",
]

bad = 0
for name in SCRIPTS:
    path = ROOT / "Modules" / "Scripts" / name
    proc = subprocess.run([sys.executable, str(path)], cwd=str(ROOT),
                          capture_output=True, text=True)
    lines = proc.stdout.splitlines()
    passed = sum(1 for l in lines if l.startswith("PASS"))
    failed = [l for l in lines if l.startswith("FAIL")]
    status = "OK  " if proc.returncode == 0 and not failed else "FAIL"
    print(f"{status} {name:<30} {passed} checks passed, {len(failed)} failed")
    for l in failed:
        print("      ", l)
    if status == "FAIL":
        bad += 1
        print("       last output:", (proc.stdout + proc.stderr).strip().splitlines()[-3:])

print("\n==== %s ====" % ("ALL TEST SCRIPTS PASSED" if bad == 0 else f"{bad} SCRIPT(S) FAILED"))
sys.exit(1 if bad else 0)
