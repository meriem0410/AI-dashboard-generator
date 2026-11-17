"""
Evaluation/run_eval.py

Runs the question set through the SQL pipeline under several CONDITIONS and
records, for every (condition, run, question), what happened and whether the
result matches the hand-verified reference ("gold") result.

    python -m Evaluation.run_eval --dataset Logistics --tag first
    python -m Evaluation.run_eval --dataset Logistics --conditions graph1,graph3 --runs 2 --tag ab
    python -m Evaluation.run_eval --tag first --resume          # continue an interrupted run

Conditions (what is switched, everything else equal; same data, same model):
    agent       the first loop (Modules/Agents/Agent_sql.py): generate, execute, retry
    graph1      the graph (guard, schema check, semantic check) with ONE attempt
    graph3      the same graph, up to 3 attempts: shows what repair adds
    graph3_rag  graph3 + schema retrieval (only the relevant tables in the prompt)

The question file (default Evaluation/questions.json), a JSON list of:
    {"id": "Q01", "question": "...", "category": "aggregation",
     "expected": "answer" | "unsupported" | "blocked",
     "gold_sql": "SELECT ...",          (for expected = answer)
     "ordered": false,                  (true when the order of rows is the answer)
     "kind": "kpi" | "bar" | "line" | "pie" | "table",
     "verified": true}                  (set to true ONLY after checking the gold result by hand)
Unverified questions are skipped unless --include-unverified is given.

Quota or outage errors from the model service (429 ...) are waited out and retried; a case that
still fails is labelled infra_error, excluded from accuracy and re-run by --resume.
Staying inside a daily token quota:
    --quick            a small stratified subset (questions marked "quick")
    --ids Q17,H05      only these questions
    --budget 150000    stop cleanly near this many tokens; continue with --resume
    LLM_CACHE=on       an unchanged prompt is replayed for free, so after a code change only
                       the prompts that changed are paid for (graph1 and graph3 share theirs)
Results are appended to Evaluation/results/<tag>.jsonl; summarise them with
python -m Evaluation.report <tag>. Use LLM_CACHE=on to replay answers.
"""
import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Evaluation.metrics import compare_results

DECLINED_STAGES = ("blocked", "unsupported", "safety")
RESULTS_DIR = ROOT / "Evaluation" / "results"


def was_declined(out):
    return (out.get("status") in ("unsupported", "blocked")
            or out.get("stage") in DECLINED_STAGES)


def _cache_hits():
    """Number of answers replayed from the LLM cache so far (None when there is no cache)."""
    try:
        from config import client
        return getattr(client, "hits", None)
    except Exception:
        return None


_INFRA = re.compile(r"\b429\b|rate.?limit|tokens per day|tokens per minute|\b50[0234]\b|"
                    r"timed? ?out|connection (error|reset|aborted)|service unavailable|overloaded", re.I)


def is_infra_error(out):
    """The model service refused or failed (quota, outage). That says nothing about the
    pipeline, so such a case is excluded from accuracy and run again."""
    if out.get("success") or was_declined(out):
        return False
    return bool(_INFRA.search(str(out.get("error") or "")))


def wait_seconds(error, default=30, cap=900):
    """'Please try again in 5m35.66s' -> 335 (+ margin), capped."""
    text = str(error)
    m = re.search(r"try again in\s+(?:(\d+)m)?\s*([\d.]+)s", text)
    if m:
        return min(cap, int(m.group(1) or 0) * 60 + float(m.group(2)) + 3)
    return default


def _cache_misses():
    """Number of REAL model calls so far when the cache wrapper is active (None otherwise)."""
    try:
        from config import client
        return getattr(client, "misses", None)
    except Exception:
        return None


def _real_tokens():
    """Cumulative tokens actually billed by real model calls (None when the cache
    wrapper is off or the client does not report usage). Used for an exact
    --budget instead of the rough per-call estimate."""
    try:
        from config import client
        return getattr(client, "real_tokens", None)
    except Exception:
        return None


def classify(item, out, gold_df):
    """Turn one pipeline output into an outcome label plus the match metrics."""
    expected = item.get("expected", "answer")
    if is_infra_error(out):
        return {"outcome": "infra_error", "match": False, "exact": False, "f1": 0.0, "precision": 0.0,
                "recall": 0.0, "col_recall": 0.0, "reason": "service error"}
    declined = was_declined(out)
    result = out.get("result")
    got_data = bool(out.get("success")) and result is not None
    info = {"outcome": "", "match": False, "exact": False, "f1": 0.0, "precision": 0.0,
            "recall": 0.0, "col_recall": 0.0, "reason": ""}

    if expected != "answer":
        if declined:
            info["outcome"] = "correct_decline"
        elif got_data:
            info["outcome"] = "hallucinated_answer"      # answered what the data cannot answer
        else:
            info["outcome"] = "no_answer"                # failed without a graceful decline
        return info

    if declined:
        info["outcome"] = "wrong_decline"
        return info
    if not got_data:
        info["outcome"] = "failed:" + str(out.get("stage") or "unknown")
        return info
    cmp = compare_results(gold_df, result, ordered=bool(item.get("ordered")))
    info.update(match=cmp["match"], exact=cmp["exact"], f1=cmp["f1"],
                precision=cmp["row_precision"], recall=cmp["row_recall"],
                col_recall=cmp["col_recall"], reason=cmp["reason"])
    info["outcome"] = "correct" if cmp["match"] else "wrong_result:" + (cmp["reason"] or "unknown")
    return info


def load_questions(path, include_unverified=False):
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    kept = [q for q in items if include_unverified or q.get("verified")]
    skipped = len(items) - len(kept)
    for q in kept:
        if q.get("expected", "answer") == "answer" and not q.get("gold_sql"):
            raise ValueError(f"{q.get('id')}: expected 'answer' needs a gold_sql")
    return kept, skipped


def run_evaluation(db, schema, questions, runners, conditions, runs, out_path,
                   tag="", resume=False, log=print, sleep=time.sleep, infra_retries=4,
                   budget_tokens=None, tokens_per_call=0, max_wait=60, pace=0):
    """Core loop. `runners` maps a condition name to
    fn(item, schema, db) -> pipeline output dict. Returns the list of records."""
    from Modules.sql_executor import execute_sql

    done = set()
    records = []
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if resume and out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("outcome") == "infra_error":
                continue                          # a service failure is run again
            records.append(r)
            done.add((r["condition"], r["run"], r["id"]))
    elif out_path.exists():
        raise FileExistsError(f"{out_path} exists: choose another --tag or use --resume")

    gold = {}
    for q in questions:
        if q.get("expected", "answer") == "answer":
            gold[q["id"]] = execute_sql(q["gold_sql"], db)
            if gold[q["id"]] is None:
                raise ValueError(f"{q['id']}: the gold query returned nothing")

    spent = 0
    for condition in conditions:
        for run in range(1, runs + 1):
            for q in questions:
                if (condition, run, q["id"]) in done:
                    continue
                if budget_tokens and spent >= budget_tokens:
                    log(f"Token budget reached (about {spent:,} of {budget_tokens:,}). Stopped cleanly: "
                        "run the same command with --resume to continue.")
                    return records
                hits_before = _cache_hits()
                misses_before = _cache_misses()
                rtok_before = _real_tokens()
                started = time.perf_counter()
                for attempt in range(infra_retries + 1):
                    try:
                        out = runners[condition](q, schema, db)
                        crashed = None
                    except Exception as exc:                   # a crash is data too
                        out, crashed = {"success": False, "stage": "crash", "error": str(exc)}, str(exc)
                    if not is_infra_error(out) or attempt == infra_retries:
                        break
                    pause = wait_seconds(out.get("error"))
                    if max_wait is not None and pause > max_wait:
                        # a daily quota is not worth waiting for: stop, keep what is done
                        log(f"{condition:<11} run{run} {q['id']:<6} the model service asks to wait {pause:.0f}s "
                            f"(more than --max-wait {max_wait}s): quota reached. Stopped cleanly, nothing lost: "
                            "run the same command with --resume later.")
                        return records
                    log(f"{condition:<11} run{run} {q['id']:<6} service limit reached: waiting {pause:.0f}s "
                        f"(try {attempt + 2}/{infra_retries + 1})")
                    sleep(pause)
                seconds = time.perf_counter() - started
                hits_after = _cache_hits()
                misses_after = _cache_misses()
                used_cache = (misses_before is not None and misses_after is not None
                              and (misses_after != misses_before or hits_after != hits_before))
                if used_cache:
                    real_calls = misses_after - misses_before
                else:
                    real_calls = int(out.get("attempts", 1) or 1)
                rtok_after = _real_tokens()
                if (rtok_before is not None and rtok_after is not None
                        and rtok_after > rtok_before):
                    tokens_this = rtok_after - rtok_before      # exact: real billed tokens
                else:
                    # No real-token delta (cache replay, a fake runner, or usage not
                    # reported): fall back to the estimate so the budget still advances.
                    tokens_this = real_calls * tokens_per_call
                spent += tokens_this
                replayed = None if hits_before is None or hits_after is None else hits_after > hits_before
                info = classify(q, out, gold.get(q["id"]))
                rec = {
                    "time": datetime.now().isoformat(timespec="seconds"), "tag": tag,
                    "condition": condition, "run": run, "id": q["id"],
                    "category": q.get("category", ""), "expected": q.get("expected", "answer"),
                    **info,
                    "attempts": out.get("attempts", 1), "seconds": round(seconds, 2),
                    "replayed": replayed, "real_calls": real_calls,
                    "tokens": int(tokens_this) if tokens_this else 0,
                    "status": out.get("status"), "stage": out.get("stage"),
                    "sql": out.get("sql"), "error": crashed or out.get("error"),
                    "rows": None if out.get("result") is None else int(len(out["result"])),
                    "gold_rows": None if q["id"] not in gold else int(len(gold[q["id"]])),
                    "assumptions": out.get("assumptions"), "notes": out.get("notes"),
                }
                records.append(rec)
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                log(f"{condition:<11} run{run} {q['id']:<6} {rec['outcome']:<28} "
                    f"tries={rec['attempts']} {seconds:5.1f}s")
                # Smooth the call rate to stay under a per-minute limit; skip when
                # the answer was replayed from cache (no real call was made).
                if pace and not replayed:
                    sleep(pace)
    return records


def make_runners():
    """The real pipeline (imports Groq, so only here)."""
    from Modules.Agents.Agent_sql import sql_agent
    from Modules.graph_panel import build_panel_graph, run_panel

    graphs = {}

    def graph_for(db):
        if id(db) not in graphs:
            graphs[id(db)] = build_panel_graph(db)
        return graphs[id(db)]

    def panel(max_attempts, use_rag):
        def run(item, schema, db):
            return run_panel(item["question"], schema, db, max_attempts=max_attempts,
                             graph=graph_for(db), kind=item.get("kind"), use_rag=use_rag)
        return run

    return {
        "agent": lambda item, schema, db: sql_agent(item["question"], schema, db),
        "graph1": panel(1, False),
        "graph3": panel(3, False),
        "graph3_rag": panel(3, True),
    }


def main():
    # The pipeline (Agent_data) prints a unicode banner at ingestion; on a Windows
    # cp1252 console that raises UnicodeEncodeError. Make this process's streams
    # tolerant so a direct run never dies before the model is even called.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="Logistics")
    parser.add_argument("--questions", default=str(ROOT / "Evaluation" / "questions.json"))
    parser.add_argument("--conditions", default="graph1,graph3,graph3_rag")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--include-unverified", action="store_true")
    parser.add_argument("--quick", action="store_true",
                        help="only the questions marked quick (a small stratified subset)")
    parser.add_argument("--ids", default="", help="only these questions, e.g. Q17,H05,H12")
    parser.add_argument("--max-wait", type=int, default=60,
                        help="longest pause accepted when the service asks to wait; beyond it the run stops cleanly")
    parser.add_argument("--budget", type=int, default=0,
                        help="stop cleanly after about this many tokens (continue later with --resume)")
    parser.add_argument("--pace", type=float, default=0.0,
                        help="seconds to wait between questions to stay under a per-minute rate limit "
                             "(e.g. 2.5 keeps well under 30 req/min); 0 = no pause")
    args = parser.parse_args()

    questions, skipped = load_questions(args.questions, args.include_unverified)
    if not questions:
        sys.exit("No verified question. Verify the gold SQL by hand and set \"verified\": true.")
    if args.quick:
        questions = [q for q in questions if q.get("quick")]
    if args.ids:
        wanted = {x.strip() for x in args.ids.split(",") if x.strip()}
        questions = [q for q in questions if q["id"] in wanted]
    if not questions:
        sys.exit("No question left after --quick / --ids.")
    print(f"{len(questions)} questions ({skipped} skipped as unverified)")

    from Modules.pipeline import ingest, profile, build_schema, open_database
    folder = ROOT / "data" / args.dataset
    data = ingest(str(folder), source_type="folder")["data"]
    schema = build_schema(profile(data), data=data)
    db = open_database(data)

    runners = make_runners()
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    unknown = [c for c in conditions if c not in runners]
    if unknown:
        sys.exit(f"Unknown condition(s): {unknown}. Choose from {list(runners)}")

    out_path = RESULTS_DIR / f"{args.tag}.jsonl"
    per_call = len(schema) // 4 + 500            # prompt (schema + instructions) + answer, rough
    worst = len(questions) * len(conditions) * args.runs * per_call
    import os
    print(f"About {per_call:,} tokens per model call; at most ~{worst:,} tokens if nothing is replayed "
          f"(cache: {os.environ.get('LLM_CACHE', 'off')}"
          + (f", budget {args.budget:,}" if args.budget else "") + ").")
    records = run_evaluation(db, schema, questions, runners, conditions, args.runs, out_path,
                             tag=args.tag, resume=args.resume,
                             budget_tokens=args.budget or None, tokens_per_call=per_call,
                             max_wait=args.max_wait, pace=args.pace)
    real = sum(r.get("real_calls") or 0 for r in records)
    measured = sum(r.get("tokens") or 0 for r in records if r.get("tokens"))
    token_note = (f"{measured:,} tokens measured" if measured
                  else f"about {real * per_call:,} tokens estimated")
    print(f"Real model calls in this file: {real} ({token_note}); "
          f"replayed cases: {sum(1 for r in records if r.get('replayed'))}.")
    print(f"\nResults: {out_path}\nNext: python -m Evaluation.report {args.tag}")
    db.close()


if __name__ == "__main__":
    main()
