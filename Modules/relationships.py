"""
Modules/relationships.py

Finds how the tables join, from the data itself.

A relationship is found when
  - two or more tables have a column with the same name ending in _id,
  - in one of them (the "one" side) that column is unique, and
  - at least `min_inclusion` of the values in the other table also exist there.
Cardinality: the other column unique too -> one-to-one, otherwise one-to-many.

Each relationship is a dict
    {"one_table", "many_table", "column", "cardinality", "inclusion"}

Why it is needed: the role "id" says a column is a key, not on which side of
a join it sits. The cardinality tells which side repeats, which is what
decides whether a SUM after a join gets counted several times.
"""
from itertools import permutations


def _q(name):
    return '"' + str(name).replace('"', '""') + '"'


def detect_relationships(db, min_inclusion=0.9):
    # columns shared by several tables
    owners = {}
    for table, info in db.tables.items():
        for col in info["columns"]:
            if col.lower().endswith("_id") and col.lower() != "id":
                owners.setdefault(col, []).append(table)
    shared = {c: ts for c, ts in owners.items() if len(ts) >= 2}

    relationships = []
    for col, tables in shared.items():
        stats = {}
        for t in tables:
            row = db.run(
                f"SELECT COUNT({_q(col)}) AS nn, COUNT(DISTINCT {_q(col)}) AS d "
                f"FROM {_q(t)};").iloc[0]
            nn, d = int(row["nn"]), int(row["d"])
            stats[t] = {"nonnull": nn, "unique": nn > 0 and d == nn}
        reported = set()
        for one, many in permutations(tables, 2):
            if not stats[one]["unique"] or stats[many]["nonnull"] == 0:
                continue
            # two unique columns: the same relationship is seen from both
            # sides, report it once (and only if the values really match)
            if stats[many]["unique"] and (many, one) in reported:
                continue
            inclusion = float(db.run(
                f"SELECT AVG(CASE WHEN {_q(col)} IN (SELECT {_q(col)} FROM {_q(one)}) "
                f"THEN 1.0 ELSE 0.0 END) AS share FROM {_q(many)} "
                f"WHERE {_q(col)} IS NOT NULL;").iloc[0]["share"])
            if inclusion >= min_inclusion:
                reported.add((one, many))
                relationships.append({
                    "one_table": one, "many_table": many, "column": col,
                    "cardinality": "one-to-one" if stats[many]["unique"] else "one-to-many",
                    "inclusion": round(inclusion, 3),
                })
    return relationships


def describe(rel):
    """One readable line for a relationship."""
    return (f"{rel['one_table']}.{rel['column']} (one) -> "
            f"{rel['many_table']}.{rel['column']} ({rel['cardinality']})")
