"""
Modules/Scripts/test_migration.py

Offline tests for the DuckDB migration. They need NO internet, NO Groq call
and NO real data: they use tiny tables and a fake language model.

Run from the project root:
    python Modules/Scripts/test_migration.py

Every line starts with PASS or FAIL. The last line tells you how many failed.
"""
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")   # config.py wants one

import duckdb
import pandas as pd

from Modules.sql_guard import check_read_only, GuardError
from Modules.engine_duckdb import Database
import Modules.Agents.Agent_sql as agent_module
import Modules.sql_generator as generator_module
from Modules.prompt_builder import build_prompt

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


# ---------------------------------------------------------------------
# A. THE SAFETY GUARD
# ---------------------------------------------------------------------
print("\n--- A. safety guard ---")
LEGIT = {
    "simple": "SELECT * FROM trips LIMIT 5;",
    "no semicolon": "SELECT COUNT(*) AS n FROM trips",
    "cte": "WITH y AS (SELECT year(d) AS yr, SUM(r) AS tot FROM t GROUP BY 1) "
           "SELECT yr, tot, LAG(tot) OVER (ORDER BY yr) AS prev FROM y ORDER BY yr;",
    "window": "SELECT a, SUM(x) OVER (PARTITION BY a ORDER BY d) AS running FROM t;",
    "union": "SELECT a FROM t1 UNION ALL SELECT a FROM t2;",
    "subquery": "SELECT * FROM (SELECT a, COUNT(*) AS n FROM t GROUP BY a) AS s WHERE n > 1;",
    "join": "SELECT c.name, SUM(l.r) AS total FROM c JOIN l ON c.id = l.id GROUP BY c.name;",
    "date_trunc": "SELECT date_trunc('month', d) AS month, SUM(x) AS total FROM t GROUP BY 1 ORDER BY 1;",
    "strftime and date_diff": "SELECT strftime(d, '%Y-%m') AS ym, date_diff('day', a, b) AS days FROM t;",
    "semicolon inside a string": "SELECT * FROM t WHERE note = 'a;b';",
    "refusal marker": "SELECT 'INVALID QUERY';",
}
ATTACKS = {
    "delete": "DELETE FROM trips WHERE d < '2024-01-01';",
    "WITH then delete": "WITH o AS (SELECT id FROM trips) DELETE FROM trips WHERE id IN (SELECT id FROM o);",
    "two statements": "SELECT 1; DROP TABLE trips;",
    "update": "UPDATE trips SET status = 'x';",
    "insert": "INSERT INTO trips SELECT * FROM trips;",
    "drop": "DROP TABLE trips;",
    "create table as": "CREATE TABLE x AS SELECT * FROM trips;",
    "select into": "SELECT * INTO newt FROM trips;",
    "copy": "COPY trips TO '/tmp/out.csv';",
    "attach": "ATTACH '/tmp/x.db' AS x;",
    "pragma": "PRAGMA database_list;",
    "install": "INSTALL httpfs;",
    "set": "SET enable_external_access=true;",
    "read_csv": "SELECT * FROM read_csv('/etc/passwd');",
    "read_parquet": "SELECT * FROM read_parquet('/tmp/x.parquet');",
    "file path as table": "SELECT * FROM '/etc/passwd';",
    "glob": "SELECT * FROM glob('/*');",
    "duckdb_settings": "SELECT * FROM duckdb_settings();",
    "parenthesis injection": "SELECT 1) AS q; DROP TABLE raw_trips; --",
    "describe": "DESCRIBE trips;",
    "empty": "",
}
for name, sql in LEGIT.items():
    try:
        check_read_only(sql)
        check("guard accepts: " + name, True)
    except GuardError as e:
        check("guard accepts: " + name, False, str(e))
for name, sql in ATTACKS.items():
    try:
        check_read_only(sql)
        check("guard refuses: " + name, False, "it was accepted")
    except GuardError:
        check("guard refuses: " + name, True)

# ---------------------------------------------------------------------
# B. THE ENGINE (sandbox, timeout, row cap)
# ---------------------------------------------------------------------
print("\n--- B. engine ---")
customers = pd.DataFrame({"customer_id": [1, 2, 3],
                          "customer_name": ["Alpha", "Beta", "Gamma"]})
loads = pd.DataFrame({
    "load_id": range(1, 7),
    "customer_id": [1, 1, 2, 2, 3, 3],
    "load_date": pd.to_datetime(["2022-01-15", "2022-06-15", "2023-01-15",
                                 "2023-06-15", "2024-01-15", "2024-06-15"]),
    "revenue": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
})
db = Database.from_dataframes({"customers": customers, "loads": loads})

df = db.run("SELECT customer_name, SUM(revenue) AS total_revenue FROM customers "
            "JOIN loads USING (customer_id) GROUP BY customer_name ORDER BY total_revenue DESC;")
check("a normal join query returns a DataFrame", isinstance(df, pd.DataFrame) and len(df) == 3)
check("the answer is correct (Gamma = 1100)",
      df.iloc[0]["customer_name"] == "Gamma" and float(df.iloc[0]["total_revenue"]) == 1100.0)
check("ORDER BY survives the row-cap wrapper", list(df["customer_name"]) == ["Gamma", "Beta", "Alpha"])

df = db.run("SELECT date_trunc('month', load_date) AS month, SUM(revenue) AS total_revenue "
            "FROM loads GROUP BY 1 ORDER BY 1;")
check("a date_trunc query works and keeps a date column",
      pd.api.types.is_datetime64_any_dtype(df["month"]), str(df.dtypes.to_dict()))

check("bind_check returns the result column names",
      db.bind_check("SELECT load_id, revenue * 2 AS double_revenue FROM loads;")
      == ["load_id", "double_revenue"])

for label, sql in {"unknown column": "SELECT nope FROM loads;",
                   "unknown table": "SELECT * FROM nope;"}.items():
    try:
        db.bind_check(sql)
        check("bind_check refuses an " + label, False)
    except duckdb.Error:
        check("bind_check refuses an " + label, True)

big = db.run("SELECT * FROM range(1000) t(x);", row_cap=100)
check("row cap cuts the result and flags it", len(big) == 100 and big.attrs.get("truncated") is True)

t0 = time.time()
try:
    db.run("SELECT sum(x*y) FROM range(300000) a(x), range(300000) b(y);", timeout=1)
    check("timeout stops a heavy query", False, "it ran to the end")
except TimeoutError:
    check("timeout stops a heavy query", True)
check("the timeout is fast (about 1 s)", time.time() - t0 < 5, f"{time.time() - t0:.1f}s")

for name, sql in {"DELETE through db.run": "DELETE FROM loads;",
                  "injection through db.run": "SELECT 1) AS q; DROP TABLE raw_loads; --"}.items():
    try:
        db.run(sql)
        check(name + " is refused", False)
    except GuardError:
        check(name + " is refused", True)

# Even if the guard were bypassed, the engine itself must hold:
raw = db.con.cursor()
for name, sql in {"file read": "SELECT * FROM read_csv('/etc/hosts');",
                  "file write": "COPY loads TO 'leak.csv';",
                  "change a setting": "SET enable_external_access=true;",
                  "attach a file": "ATTACH 'x.db' AS x;"}.items():
    try:
        raw.execute(sql).fetchall()
        check("engine blocks (guard bypassed): " + name, False, "it ran")
    except duckdb.Error:
        check("engine blocks (guard bypassed): " + name, True)

# DuckDB reads "SELECT 1 DELETE FROM loads" as a SELECT whose column is named
# DELETE: it either errors or returns a row, but it never deletes anything.
try:
    raw.execute("SELECT 1 DELETE FROM loads").fetchall()
except duckdb.Error:
    pass

check("all rows are still there after the attacks",
      db.run("SELECT COUNT(*) AS n FROM loads;").iloc[0]["n"] == 6)
check("raw tables exist next to the views",
      db.run("SELECT COUNT(*) AS n FROM raw_loads;").iloc[0]["n"] == 6)

# ---------------------------------------------------------------------
# C. THE AGENT LOOP, WITH A FAKE LANGUAGE MODEL
# ---------------------------------------------------------------------
print("\n--- C. agent loop (fake model, no internet) ---")


def fake_client(answers):
    """A stand-in for the Groq client that returns the given answers in turn."""
    queue = list(answers)

    def create(**kwargs):
        text = queue.pop(0) if queue else "SELECT 'INVALID QUERY';"
        message = SimpleNamespace(content=text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    chat = SimpleNamespace(completions=SimpleNamespace(create=create))
    return SimpleNamespace(chat=chat)


def run_agent(answers, question="test question"):
    stub = fake_client(answers)
    agent_module.client = stub
    generator_module.client = stub
    return agent_module.sql_agent(question, "SCHEMA TEXT", db)


out = run_agent(["SELECT COUNT(*) AS n FROM loads;"])
check("good SQL: success on attempt 1", out["success"] and out["attempts"] == 1, str(out["error"]))
check("good SQL: the result is a DataFrame", isinstance(out["result"], pd.DataFrame))

out = run_agent(["SELECT nope FROM loads;", "SELECT COUNT(*) AS n FROM loads;"])
check("unknown column then fixed: success on attempt 2",
      out["success"] and out["attempts"] == 2, f"{out['stage']} {out['error']}")
check("history records the failed attempt",
      out["history"][0]["stage"] == "schema_validation", str(out["history"]))

out = run_agent(["DELETE FROM loads;"])
check("DELETE: stops at stage safety, no retry",
      (not out["success"]) and out["stage"] == "safety" and out["attempts"] == 1,
      f"{out['stage']} attempts={out['attempts']}")
check("DELETE: nothing was deleted",
      db.run("SELECT COUNT(*) AS n FROM loads;").iloc[0]["n"] == 6)

out = run_agent(["WITH o AS (SELECT load_id FROM loads) DELETE FROM loads WHERE load_id IN (SELECT load_id FROM o);"])
check("WITH ... DELETE: stops at stage safety", out["stage"] == "safety", out["stage"])

out = run_agent(["SELECT ( FROM loads;", "SELECT COUNT(*) AS n FROM loads;"])
check("unparseable query then fixed: retried through stage syntax",
      out["success"] and out["history"][0]["stage"] == "syntax", str(out["history"]))

out = run_agent(["SELECT * INTO copy_of_loads FROM loads;"])
check("SELECT ... INTO: stops at stage safety, no retry",
      (not out["success"]) and out["stage"] == "safety" and out["attempts"] == 1, out["stage"])

out = run_agent(["SELECT 1; DELETE FROM loads;"])
check("a second statement after SELECT is never executed",
      db.run("SELECT COUNT(*) AS n FROM loads;").iloc[0]["n"] == 6)

out = run_agent(["SELECT 'INVALID QUERY';"])
check("the model's refusal ends at stage extraction, no retry",
      (not out["success"]) and out["stage"] == "extraction" and out["attempts"] == 1, out["stage"])

# ---------------------------------------------------------------------
# D. THE PROMPT
# ---------------------------------------------------------------------
print("\n--- D. prompt ---")
prompt = build_prompt("MY SCHEMA", "MY QUESTION")
check("the prompt contains the schema and the question",
      "MY SCHEMA" in prompt and "MY QUESTION" in prompt)
check("the prompt is written for DuckDB, not SQL Server",
      "DuckDB" in prompt and "TOP" in prompt and "SQL Server" not in prompt)

db.close()
print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
