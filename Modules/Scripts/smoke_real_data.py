"""
Modules/Scripts/smoke_real_data.py

Loads one of your real datasets (a folder under data/) into the new DuckDB
engine and checks that it behaves: row counts, a few queries with timings,
memory use, and the safety refusals. No Groq call is made.

Run from the project root:
    python Modules/Scripts/smoke_real_data.py Logistics
    python Modules/Scripts/smoke_real_data.py salesData
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

import duckdb
import psutil

from Modules.pipeline import ingest, open_database
from Modules.sql_guard import GuardError

name = sys.argv[1] if len(sys.argv) > 1 else "Logistics"
folder = ROOT / "data" / name


def mb():
    return round(psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024)


print(f"\n=== SMOKE TEST on {folder} ===")
print("memory at start:", mb(), "MB")

t = time.perf_counter()
data = ingest(str(folder), source_type="folder")["data"]
print(f"ingest: {time.perf_counter() - t:.1f} s, memory {mb()} MB")

t = time.perf_counter()
db = open_database(data)
print(f"open_database: {time.perf_counter() - t:.2f} s, memory {mb()} MB")

print("\ntables in the engine:")
for table, info in db.tables.items():
    print(f"  {table}: {info['rows']:,} rows, {len(info['columns'])} columns")

biggest = max(db.tables, key=lambda k: db.tables[k]["rows"])
first_col = db.tables[biggest]["columns"][0]
print(f"\nqueries on the biggest table ({biggest}):")
queries = {
    "row count": f"SELECT COUNT(*) AS n FROM {biggest};",
    "first 3 rows": f"SELECT * FROM {biggest} LIMIT 3;",
    f"top 5 values of {first_col}": (
        f"SELECT {first_col}, COUNT(*) AS n FROM {biggest} "
        f"GROUP BY {first_col} ORDER BY n DESC LIMIT 5;"),
}
for label, sql in queries.items():
    t = time.perf_counter()
    df = db.run(sql)
    print(f"  {label}: {len(df)} rows in {(time.perf_counter() - t) * 1000:.0f} ms")

print("\nsafety checks (each must be refused):")
refused = 0
for label, sql in {
    "DELETE": f"DELETE FROM {biggest};",
    "read a file": "SELECT * FROM read_csv('/etc/passwd');",
    "unknown column": f"SELECT this_column_does_not_exist FROM {biggest};",
}.items():
    try:
        db.run(sql)
        print(f"  FAIL  {label} was accepted")
    except (GuardError, duckdb.Error) as e:
        refused += 1
        print(f"  PASS  {label}: {str(e)[:90]}")

print(f"\nfinal memory: {mb()} MB")
print("RESULT:", "OK" if refused == 3 else "PROBLEM: see FAIL lines above")
db.close()
