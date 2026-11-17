"""
Evaluation/run_all_eval.py

One command to evaluate EVERY part of the pipeline and collect the evidence in a
single document. It runs the cheap, offline checks in full first (they cost no
model quota), then the one quota-bound step (SQL accuracy) under a token budget
that stops cleanly and resumes.

    # see the plan without running anything (no quota spent)
    python -m Evaluation.run_all_eval --tag final --dry-run

    # full run, staying inside a daily token budget (resume the same line later)
    LLM_CACHE=on python -m Evaluation.run_all_eval --tag final --budget 150000 --pace 2

    # offline pillars only (unit suite + safety + retrieval), zero quota
    python -m Evaluation.run_all_eval --tag final --skip-main

Stages measured (each maps to a concrete artifact):
    ingest / profile / schema      unit suite (deterministic components)
    schema retrieval (RAG)         retrieval_eval   (table recall, precision, prompt size)
    SQL generation + repair        run_eval + report(execution accuracy, F1, repair effect, CIs)
    safety guard + locked engine   guard_eval       (attack block rate, benign pass rate)
    semantic validation / decline  run_eval report  (failure taxonomy, correct declines)

Every step is isolated in its own subprocess, so one failure does not lose the
others; whatever ran is written to Evaluation/results/<tag>_evidence.md.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Evaluation" / "results"


def build_steps(args):
    """Return the ordered steps as (key, title, argv, env_overrides, optional).
    Pure function (no side effects) so the plan can be shown or tested."""
    py = sys.executable
    dataset = args.dataset
    tag = args.tag
    conditions = args.conditions

    steps = [
        ("unit", "Unit suite — deterministic components (ingest, profiling, schema, "
                 "filters, KPI trends, ops, semantic checks, insights, export, overview)",
         [py, str(ROOT / "Modules" / "Scripts" / "run_all_tests.py")], {}, False),
        ("guard", "Safety — SQL guard + locked engine (attack block rate, benign pass rate)",
         [py, "-m", "Evaluation.guard_eval"], {}, False),
        ("retrieval", "Schema retrieval (RAG) — table recall, precision, prompt-size sweep",
         [py, "-m", "Evaluation.retrieval_eval", dataset], {}, False),
    ]

    if not args.skip_main:
        main_cmd = [py, "-m", "Evaluation.run_eval",
                    "--dataset", dataset, "--tag", tag,
                    "--conditions", conditions, "--runs", str(args.runs),
                    "--max-wait", str(args.max_wait), "--resume"]
        if args.budget:
            main_cmd += ["--budget", str(args.budget)]
        if args.pace:
            main_cmd += ["--pace", str(args.pace)]
        if args.quick:
            main_cmd += ["--quick"]
        if args.ids:
            main_cmd += ["--ids", args.ids]
        # LLM_CACHE=on makes a resumed/repeated run replay unchanged prompts for free.
        steps.append(("main", "SQL accuracy — generation + repair vs verified gold "
                               "(execution accuracy, precision/recall/F1)",
                      main_cmd, {"LLM_CACHE": os.environ.get("LLM_CACHE", "on")}, False))
        steps.append(("report", "Accuracy report — tables with 95% CIs, repair/RAG effect, "
                                 "failure taxonomy, significance tests",
                      [py, "-m", "Evaluation.report", tag], {}, True))

    return steps


def _run(step, log):
    key, title, argv, env_over, optional = step
    env = dict(os.environ)
    # Force UTF-8 in the child so emoji/box-drawing in print() does not crash on a
    # Windows cp1252 console (and so captured output decodes cleanly).
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.update(env_over)
    log(f"\n{'='*78}\n[{key}] {title}\n{'-'*78}\n$ " + " ".join(argv) +
        (f"   (env: {', '.join(f'{k}={v}' for k, v in env_over.items())})" if env_over else ""))
    started = time.perf_counter()
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), env=env, text=True,
                              capture_output=True, encoding="utf-8", errors="replace")
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr.strip() else "")
        code = proc.returncode
    except Exception as exc:                        # could not even launch the step
        out, code = f"Could not run this step: {exc}", 1
    secs = time.perf_counter() - started
    ok = (code == 0)
    log(out.rstrip())
    log(f"[{key}] {'OK' if ok else 'FAILED (exit %d)' % code} in {secs:.0f}s"
        + ("  — optional, continuing" if (not ok and optional) else ""))
    return {"key": key, "title": title, "argv": argv, "env": env_over,
            "ok": ok, "code": code, "seconds": secs, "output": out.rstrip(),
            "optional": optional}


def write_evidence(tag, results, args):
    """One document that maps each pipeline stage to the step that measured it,
    embeds each step's output, and links the artifact files it wrote."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{tag}_evidence.md"
    lines = [f"# Devoboard — pipeline evaluation evidence (`{tag}`)",
             f"_Generated {datetime.now().isoformat(timespec='seconds')}._", ""]

    lines += ["## Summary", "", "| Stage | Step | Result |", "|---|---|---|"]
    for r in results:
        verdict = "passed" if r["ok"] else ("stopped/partial" if r["optional"] else "FAILED")
        lines.append(f"| {r['title'].split(' — ')[0]} | `{r['key']}` | {verdict} |")
    lines += ["",
              "Artifacts in `Evaluation/results/`: "
              f"`{tag}.jsonl` (raw per-question records), `{tag}_report.md` "
              "(accuracy tables), `guard_eval.md` (safety).", ""]

    for r in results:
        lines += [f"## `{r['key']}` — {r['title']}", "",
                  f"Command: `{' '.join(r['argv'])}`"
                  + (f"  (env: {', '.join(f'{k}={v}' for k, v in r['env'].items())})" if r["env"] else ""),
                  f"Status: {'OK' if r['ok'] else 'exit %d' % r['code']}  ·  {r['seconds']:.0f}s", "",
                  "```", r["output"][-6000:], "```", ""]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", required=True, help="names the result/report/evidence files")
    parser.add_argument("--dataset", default="Logistics")
    parser.add_argument("--conditions", default="graph3",
                        help="SQL conditions for the accuracy step (default graph3 = the "
                             "production setting; use graph1,graph3,graph3_rag to ablate)")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--budget", type=int, default=0,
                        help="token budget for the accuracy step; it stops cleanly near this and resumes")
    parser.add_argument("--pace", type=float, default=0.0,
                        help="seconds between questions in the accuracy step (rate-limit smoothing)")
    parser.add_argument("--max-wait", type=int, default=60)
    parser.add_argument("--quick", action="store_true", help="accuracy step on the quick subset only")
    parser.add_argument("--ids", default="", help="accuracy step on these question ids only")
    parser.add_argument("--skip-main", action="store_true",
                        help="offline pillars only (no model, no quota)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = parser.parse_args()

    steps = build_steps(args)
    if args.dry_run:
        print("Planned evaluation steps (nothing run):\n")
        for key, title, argv, env_over, optional in steps:
            envs = (" ".join(f"{k}={v}" for k, v in env_over.items()) + " ") if env_over else ""
            print(f"  [{key}] {title}\n      $ {envs}" + " ".join(argv) + "\n")
        print(f"Evidence would be written to Evaluation/results/{args.tag}_evidence.md")
        return

    results = [_run(s, print) for s in steps]
    path = write_evidence(args.tag, results, args)

    failed = [r["key"] for r in results if not r["ok"] and not r["optional"]]
    print(f"\n{'='*78}\nEvidence written to {path}")
    if failed:
        print(f"Steps that need attention: {', '.join(failed)}")
    print("If the accuracy step stopped on the token budget/quota, re-run the SAME command "
          "with LLM_CACHE=on to continue where it left off.")


if __name__ == "__main__":
    main()
