"""
Modules/Scripts/run_questions.py

Sends the 12 test questions through the real SQL agent (this DOES call Groq)
and records what happened in runs/run_log.jsonl. This is the 'run' you keep
as evidence. Run it before and after every change and compare the logs.

Run from the project root:
    python Modules/Scripts/run_questions.py Logistics

Optional: a JSON file of your own questions:
    python Modules/Scripts/run_questions.py Logistics my_questions.json
    (a list of {"id": "Q1", "question": "..."})
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Modules.pipeline import ingest, profile, build_schema, open_database
from Modules.Agents.Agent_sql import sql_agent
from config import GROQ_MODEL

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

name = sys.argv[1] if len(sys.argv) > 1 else "Logistics"
if len(sys.argv) > 2:
    items = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    questions = [(q["id"], q["question"]) for q in items]
else:
    questions = QUESTIONS

folder = ROOT / "data" / name
print(f"\nLoading {folder} ...")
data = ingest(str(folder), source_type="folder")["data"]
schema = build_schema(profile(data), data=data)
db = open_database(data)

log_dir = ROOT / "runs"
log_dir.mkdir(exist_ok=True)
log_path = log_dir / "run_log.jsonl"

print(f"\n{'id':<5}{'ok':<6}{'stage':<19}{'tries':<7}{'rows':<7}{'sec':<6}")
for qid, question in questions:
    t = time.perf_counter()
    out = sql_agent(question, schema, db)
    seconds = time.perf_counter() - t
    df = out.get("result")
    rows = None if df is None else len(df)
    print(f"{qid:<5}{str(out['success']):<6}{out['stage']:<19}"
          f"{out.get('attempts', 1):<7}{str(rows):<7}{seconds:<6.1f}")
    record = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "dataset": name,
        "model": GROQ_MODEL,
        "engine": "duckdb",
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
        "history": out.get("history"),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"\nLog appended to {log_path}")
db.close()
