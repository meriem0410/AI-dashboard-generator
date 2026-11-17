"""
Evaluation/guard_eval.py

Measures the SAFETY layers, offline (no model, no network, no data needed):

  Layer 1  the SQL guard (Modules/sql_guard.py): reads the query as a syntax tree.
  Layer 2  the engine (Modules/engine_duckdb.py): locked DuckDB, no external access.

A corpus of ATTACKS (queries that must be refused) and BENIGN queries (realistic
analytics queries that must pass) is run through the guard. Two numbers matter:

  attack block rate   share of attacks refused        (security: want 100%)
  benign pass rate    share of normal queries allowed (usability: want 100%)
                      the benign set deliberately contains look-alikes such as a
                      column named "delete_flag" or the text 'drop table' in a
                      string, which a keyword filter would wrongly refuse.

For every attack the guard lets through (ideally none), and for the attacks that
reach the engine directly, the engine layer is tried alone, to show what the
second layer would still stop (defence in depth).

    python -m Evaluation.guard_eval            # prints a table, writes results/guard_eval.md
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.engine_duckdb import Database
from Modules.sql_guard import is_safe

# (category, sql)
ATTACKS = [
    ("write", "DELETE FROM trips"),
    ("write", "delete from trips where 1=1"),
    ("write", "UPDATE trips SET miles = 0"),
    ("write", "INSERT INTO trips VALUES (1, 'D1', 5)"),
    ("write", "INSERT INTO trips SELECT * FROM trips"),
    ("write", "DROP TABLE trips"),
    ("write", "DROP VIEW trips"),
    ("write", "CREATE TABLE x AS SELECT * FROM trips"),
    ("write", "CREATE OR REPLACE VIEW trips AS SELECT 1"),
    ("write", "ALTER TABLE trips ADD COLUMN z INT"),
    ("write", "TRUNCATE TABLE trips"),
    ("write", "MERGE INTO trips USING drivers ON 1=1 WHEN MATCHED THEN DELETE"),
    ("write", "SELECT * INTO backup FROM trips"),
    ("cte-write", "WITH t AS (SELECT * FROM trips) DELETE FROM trips"),
    ("cte-write", "WITH t AS (SELECT 1) INSERT INTO trips SELECT * FROM trips"),
    ("cte-write", "WITH d AS (DELETE FROM trips RETURNING *) SELECT * FROM d"),
    ("stacked", "SELECT 1; DROP TABLE trips"),
    ("stacked", "SELECT 1; SELECT 2"),
    ("stacked", "SELECT * FROM trips; DELETE FROM trips;"),
    ("stacked", "SELECT 1 /* x */; /* y */ DROP TABLE trips"),
    ("obfuscated", "/**/DELETE/**/FROM/**/trips"),
    ("obfuscated", "DeLeTe FrOm trips"),
    ("obfuscated", "-- harmless\nDROP TABLE trips"),
    ("obfuscated", "  \n\t DROP TABLE trips"),
    ("file-read", "SELECT * FROM read_csv('/etc/passwd')"),
    ("file-read", "SELECT * FROM read_csv_auto('data/secret.csv')"),
    ("file-read", "SELECT * FROM read_parquet('x.parquet')"),
    ("file-read", "SELECT * FROM read_json('x.json')"),
    ("file-read", "SELECT * FROM read_text('/etc/passwd')"),
    ("file-read", "SELECT * FROM '/etc/passwd'"),
    ("file-read", "SELECT * FROM 'data/secret.csv'"),
    ("file-read", "SELECT * FROM glob('/*')"),
    ("file-read", "SELECT * FROM parquet_scan('x.parquet')"),
    ("file-read", "SELECT * FROM sniff_csv('x.csv')"),
    ("file-write", "COPY trips TO '/tmp/out.csv'"),
    ("file-write", "COPY (SELECT * FROM trips) TO '/tmp/out.csv'"),
    ("file-write", "EXPORT DATABASE '/tmp/export'"),
    ("engine", "ATTACH '/tmp/other.db' AS other"),
    ("engine", "DETACH other"),
    ("engine", "INSTALL httpfs"),
    ("engine", "LOAD httpfs"),
    ("engine", "PRAGMA database_list"),
    ("engine", "SET enable_external_access = true"),
    ("engine", "SET memory_limit = '100GB'"),
    ("engine", "RESET enable_external_access"),
    ("engine", "CALL pragma_database_size()"),
    ("engine", "SELECT * FROM duckdb_settings()"),
    ("engine", "SELECT * FROM duckdb_tables()"),
    ("engine", "SELECT current_setting('enable_external_access')"),
    ("engine", "SELECT getenv('HOME')"),
    ("engine", "SELECT * FROM query_table('trips')"),
    ("engine", "SELECT * FROM query('DELETE FROM trips')"),
    ("engine", "EXECUTE foo"),
    ("engine", "VACUUM"),
    ("engine", "BEGIN TRANSACTION"),
    ("engine", "DESCRIBE trips"),
    ("engine", "SHOW TABLES"),
]

BENIGN = [
    ("aggregate", "SELECT COUNT(*) AS n FROM trips"),
    ("aggregate", "SELECT AVG(miles) AS avg_miles, SUM(miles) AS total FROM trips"),
    ("aggregate", "SELECT driver_id, SUM(miles) AS total FROM trips GROUP BY driver_id ORDER BY total DESC LIMIT 5"),
    ("join", "SELECT d.first_name, SUM(t.miles) AS m FROM drivers d JOIN trips t USING (driver_id) GROUP BY ALL"),
    ("join", "SELECT * FROM trips t LEFT JOIN drivers d ON t.driver_id = d.driver_id"),
    ("cte", "WITH t AS (SELECT driver_id, SUM(miles) AS m FROM trips GROUP BY 1) SELECT * FROM t WHERE m > 100"),
    ("cte", "WITH a AS (SELECT 1 AS x), b AS (SELECT 2 AS x) SELECT * FROM a UNION ALL SELECT * FROM b"),
    ("window", "SELECT driver_id, miles, RANK() OVER (PARTITION BY driver_id ORDER BY miles DESC) AS r FROM trips"),
    ("window", "SELECT trip_id, SUM(miles) OVER (ORDER BY trip_id) AS running FROM trips"),
    ("date", "SELECT date_trunc('month', purchase_date) AS month, SUM(total_cost) AS spend FROM fuel GROUP BY 1 ORDER BY 1"),
    ("date", "SELECT EXTRACT(year FROM purchase_date) AS y, COUNT(*) FROM fuel GROUP BY 1"),
    ("case", "SELECT CASE WHEN miles > 120 THEN 'long' ELSE 'short' END AS kind, COUNT(*) FROM trips GROUP BY 1"),
    ("subquery", "SELECT * FROM trips WHERE miles > (SELECT AVG(miles) FROM trips)"),
    ("subquery", "SELECT * FROM (SELECT driver_id, COUNT(*) AS n FROM trips GROUP BY 1) q WHERE n > 1"),
    ("quoted", 'SELECT "driver_id", "miles" FROM "trips"'),
    ("lookalike", "SELECT 'DROP TABLE trips' AS note"),
    ("lookalike", "SELECT * FROM drivers WHERE first_name = 'delete'"),
    ("lookalike", "SELECT * FROM drivers WHERE first_name LIKE '%update%'"),
    ("lookalike", "SELECT miles AS delete_flag, miles AS update_date, miles AS insert_count FROM trips"),
    ("lookalike", "SELECT COUNT(*) AS drop_offs FROM trips"),
    ("lookalike", "SELECT 1 AS \"create\""),
    ("lookalike", "SELECT 'a;b' AS semi"),
    ("lookalike", "SELECT 1 -- DROP TABLE trips"),
    ("lookalike", "SELECT /* DELETE FROM trips */ 1"),
    ("lookalike", "SELECT * FROM trips WHERE miles BETWEEN 100 AND 200 ORDER BY miles LIMIT 10 OFFSET 5"),
    ("string-fn", "SELECT UPPER(first_name), LENGTH(first_name), first_name || '!' FROM drivers"),
    ("string-fn", "SELECT regexp_matches(first_name, '^N') FROM drivers"),
    ("math", "SELECT ROUND(AVG(miles) / NULLIF(COUNT(*), 0), 2) FROM trips"),
    ("distinct", "SELECT DISTINCT driver_id FROM trips ORDER BY 1"),
    ("having", "SELECT driver_id FROM trips GROUP BY 1 HAVING COUNT(*) > 1"),
    ("union", "SELECT driver_id FROM trips UNION SELECT driver_id FROM drivers"),
    ("trailing-semicolon", "SELECT COUNT(*) FROM trips;"),
]


def _engine():
    """A real locked database with three small tables."""
    fuel = pd.DataFrame({"fuel_id": range(1, 31),
                         "purchase_date": pd.date_range("2024-01-01", periods=30),
                         "total_cost": [100.0 + i for i in range(30)]})
    drivers = pd.DataFrame({"driver_id": [f"D{i}" for i in range(1, 6)],
                            "first_name": ["Nora", "Omar", "Pia", "Quinn", "Rae"]})
    trips = pd.DataFrame({"trip_id": range(1, 21),
                          "driver_id": [f"D{(i % 5) + 1}" for i in range(20)],
                          "miles": [100 + 7 * i for i in range(20)]})
    return Database.from_dataframes({"fuel": fuel, "drivers": drivers, "trips": trips})


def engine_alone_blocks(db, sql):
    """True if the engine (without the guard) refuses or cannot run the query,
    False if it runs. A write that succeeds only changes an in-memory copy."""
    try:
        cur = db.con.cursor()
        try:
            cur.execute(sql)
            try:
                cur.fetchall()
            except Exception:
                pass
        finally:
            cur.close()
        return False
    except Exception:
        return True


def evaluate():
    db = _engine()
    rows = {"attacks": [], "benign": []}
    for category, sql in ATTACKS:
        safe, reason = is_safe(sql)
        rows["attacks"].append({"category": category, "sql": sql, "guard_blocked": not safe,
                                "reason": reason,
                                "engine_alone_blocked": engine_alone_blocks(_engine(), sql)})
    for category, sql in BENIGN:
        safe, reason = is_safe(sql)
        rows["benign"].append({"category": category, "sql": sql, "guard_allowed": safe, "reason": reason})
    # benign queries must also RUN on the engine
    for r in rows["benign"]:
        try:
            db.run(r["sql"])
            r["runs"] = True
        except Exception as e:
            r["runs"] = False
            r["run_error"] = str(e)[:150]
    db.close()
    return rows


def report(rows):
    attacks, benign = rows["attacks"], rows["benign"]
    blocked = sum(a["guard_blocked"] for a in attacks)
    allowed = sum(b["guard_allowed"] for b in benign)
    runs = sum(1 for b in benign if b.get("runs"))
    lines = ["# Safety layers: evaluation", "",
             f"- Attacks tested: {len(attacks)}; refused by the guard: **{blocked}/{len(attacks)}** "
             f"({100 * blocked / len(attacks):.1f}%)",
             f"- Benign queries tested: {len(benign)}; allowed by the guard: **{allowed}/{len(benign)}** "
             f"({100 * allowed / len(benign):.1f}%); executed successfully: {runs}/{len(benign)}",
             ""]
    by_cat = defaultdict(lambda: [0, 0, 0])
    for a in attacks:
        c = by_cat[a["category"]]
        c[0] += 1
        c[1] += a["guard_blocked"]
        c[2] += a["engine_alone_blocked"]
    lines += ["## Attacks by category", "",
              "| Category | Attacks | Guard refuses | Engine alone refuses |", "| --- | --- | --- | --- |"]
    for cat, (n, g, e) in by_cat.items():
        lines.append(f"| {cat} | {n} | {g}/{n} | {e}/{n} |")
    missed = [a for a in attacks if not a["guard_blocked"]]
    lines += ["", "## Attacks the guard let through", ""]
    lines += [f"- `{a['sql']}` ({a['category']}); engine alone: "
              f"{'refused' if a['engine_alone_blocked'] else 'would run'}" for a in missed] or ["None."]
    wrong = [b for b in benign if not b["guard_allowed"] or not b.get("runs")]
    lines += ["", "## Benign queries wrongly refused or failing", ""]
    lines += [f"- `{b['sql']}`: {b.get('reason') or b.get('run_error')}" for b in wrong] or ["None."]
    only_guard = [a for a in attacks if a["guard_blocked"] and not a["engine_alone_blocked"]]
    lines += ["", "## Defence in depth", "",
              f"{sum(a['engine_alone_blocked'] for a in attacks)}/{len(attacks)} attacks would also fail on the "
              f"locked engine alone. {len(only_guard)} are stopped ONLY by the guard "
              "(mostly writes on the in-memory copy, which the engine permits); the guard is therefore "
              "necessary, and the engine lock covers file and configuration access independently."]
    return "\n".join(lines)


if __name__ == "__main__":
    rows = evaluate()
    text = report(rows)
    out = ROOT / "Evaluation" / "results"
    out.mkdir(exist_ok=True)
    (out / "guard_eval.md").write_text(text, encoding="utf-8")
    (out / "guard_eval.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    print(text)
    print(f"\nWritten to {out / 'guard_eval.md'}")
