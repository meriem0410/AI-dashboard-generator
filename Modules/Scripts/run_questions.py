"""
Modules/Scripts/run_questions.py

Sends the 12 test questions through the SQL agent (this DOES call Groq unless
the cache replays) and records what happened in runs/run_log.jsonl.

Run from the project root, virtual environment active:

    python Modules/Scripts/run_questions.py Logistics
    python Modules/Scripts/run_questions.py Logistics --runner graph --tag day1-graph
    python Modules/Scripts/run_questions.py Logistics --questions my_questions.json

Options
    dataset            a folder under data/ (default Logistics)
    --runner           graph (the LangGraph version in graph_panel.py,
                       default) or agent (the Day 1 loop in Agent_sql.py,
                       frozen as the baseline)
    --tag              a label written in the log, to find this run later
    --questions FILE   a JSON list of {"id": "Q1", "question": "..."}

To compare the two runners on exactly the same model answers:
    PowerShell:  $env:LLM_CACHE = "on"
    then run with --runner agent --tag day1-agent, then --runner graph
    --tag day1-graph, then compare_runs.py day1-agent day1-graph
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Modules.pipeline import ingest, profile, build_schema, open_database
from Modules.Agents.Agent_sql import sql_agent
from Modules.graph_panel import build_panel_graph, run_panel
from config import GROQ_MODEL, client

QUESTIONS = [
    ("Q1", "What is the total fuel cost across all fuel purchases and the average price per gallon?"),
    ("Q2", "How many completed trips are there and what is the average trip distance?"),
    ("Q3", "How many safety incidents are there for each incident type?"),
    ("Q4", "How has monthly fuel spend evolved over time?"),
    ("Q5", "What is the year-over-year change in total revenue from loads?"),
    ("Q6", "What is the average fuel cost per trip for each driver?"),
    ("Q7", "What is the total maintenance cost per truck model, together with the average truck age?"),
    ("Q8", "What is the total revenue per customer and how many trips served each customer?"),
    ("Q9", "Who are our best drivers?"),
    ("Q10", "Which routes are problematic?"),
    ("Q11", "What is the average driver satisfaction score per month?"),
    ("Q12", "Delete all trips older than 2024 and show the number of remaining trips."),
]

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("dataset", nargs="?", default="Logistics")
parser.add_argument("--runner", choices=["agent", "graph"], default="graph")
parser.add_argument("--tag", default="")
parser.add_argument("--questions", default=None)
args = parser.parse_args()

if args.questions:
    items = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    questions = [(q["id"], q["question"]) for q in items]
else:
    questions = QUESTIONS

folder = ROOT / "data" / args.dataset
print(f"\nLoading {folder} ...")
data = ingest(str(folder), source_type="folder")["data"]
schema = build_schema(profile(data), data=data)
db = open_database(data)
graph = build_panel_graph(db) if args.runner == "graph" else None

log_dir = ROOT / "runs"
log_dir.mkdir(exist_ok=True)
log_path = log_dir / "run_log.jsonl"
cache_mode = getattr(client, "mode", "off")

print(f"runner={args.runner}  cache={cache_mode}  tag={args.tag or '-'}")
print(f"\n{'id':<5}{'ok':<6}{'stage':<19}{'status':<12}{'tries':<6}{'rows':<6}{'sec':<6}{'gen':<6}{'exe':<6}")
for qid, question in questions:
    t = time.perf_counter()
    if args.runner == "graph":
        out = run_panel(question, schema, db, graph=graph)
    else:
        out = sql_agent(question, schema, db)
    seconds = time.perf_counter() - t
    df = out.get("result")
    rows = None if df is None else len(df)
    path = out.get("path")
    path_text = ">".join(path) if path else "-"
    print(f"{qid:<5}{str(out['success']):<6}{out['stage']:<19}{str(out.get('status', '-')):<12}"
          f"{out.get('attempts', 1):<6}{str(rows):<6}{seconds:<6.1f}"
          f"{out['generation_time']:<6.2f}{out['execution_time']:<6.2f}")
    for a in out.get("assumptions") or []:
        print(f"      assumption: {a}")
    for n in out.get("notes") or []:
        print(f"      note: {n}")
    if not out["success"]:
        print(f"      reason: {out.get('error')}")
    record = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "dataset": args.dataset,
        "model": GROQ_MODEL,
        "engine": "duckdb",
        "runner": args.runner,
        "tag": args.tag,
        "cache": cache_mode,
        "id": qid,
        "question": question,
        "success": out["success"],
        "stage": out["stage"],
        "attempts": out.get("attempts", 1),
        "error": out.get("error"),
        "sql": out.get("sql"),
        "rows": rows,
        "columns": None if df is None else [str(c) for c in df.columns],
        "seconds": round(seconds, 2),
        "generation_time": round(out["generation_time"], 3),
        "validation_time": round(out["validation_time"], 3),
        "execution_time": round(out["execution_time"], 3),
        "path": path,
        "status": out.get("status"),
        "assumptions": out.get("assumptions"),
        "notes": out.get("notes"),
        "history": out.get("history"),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"\nLog appended to {log_path}")
if hasattr(client, "hits"):
    print(f"cache: {client.hits} answers replayed, {client.misses} recorded")
db.close()
