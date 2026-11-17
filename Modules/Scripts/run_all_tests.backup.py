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
    "test_composition.py",
    "test_knowledge_base.py",
    "test_data_agent.py",
    "test_rag_context.py",
    "test_library.py",
    "test_app_services.py",
    "test_eval_metrics.py",
    "test_guard_eval.py",
    "test_eval_runner.py", "test_gold_logistics.py", "test_retrieval_eval.py", "test_engine_filters.py", "test_dashboard_filters_scope.py", "test_kpi_headline.py", "test_kpi_trends.py", "test_dashboard_ops.py", "test_followup.py", "test_schema_values.py", "test_insights.py", "test_export_html.py", "test_dataset_overview.py",
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
