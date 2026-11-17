"""
Modules/knowledge_base.py

The schema knowledge base (the "Schema RAG" of the architecture diagram).

OFFLINE, once per dataset (build / save):
    profile + schema stats (schema_tool) + relationships + dataset card
        -> one text chunk per table, per column, per relationship, per
           glossary term and per KPI idea
        -> embeddings -> a FAISS index, saved next to the dataset

ONLINE, for every question (retrieve / select_tables / schema_text):
    question -> embedding -> nearest chunks -> the tables they belong to
        -> expanded with the tables needed to join them and to show names
        -> a schema text that contains ONLY those tables

Why: a prompt that holds the whole schema grows with the dataset. A prompt
that holds the few relevant tables stays short, and the glossary can tell the
model what a business word means in this dataset.

This module never calls a language model. The dataset card it uses comes
from Modules/Agents/Agent_understand.py (or from build_basic_card, which
needs no model).
"""
import json
import time
from pathlib import Path

import faiss
import numpy as np

from Modules.embeddings import get_embedder
from Modules.relationships import describe, detect_relationships
from Modules.schemas import (DatasetCard, GlossaryEntry, KPIIdea, TableCard)
from Modules.tools import make_tools

CHUNK_WEIGHT = {"table": 1.0, "column": 0.7, "glossary": 0.5, "kpi": 0.4,
                "relation": 0.2, "dataset": 0.0}
MAX_KPI_IDEAS = 30


# ----------------------------------------------------------------------
# schema information and the basic card
# ----------------------------------------------------------------------
def collect_schema_info(db):
    """{table: schema_tool output} for every table of the database."""
    schema_tool = next(t for t in make_tools(db) if t.name == "schema_tool")
    return {table: json.loads(schema_tool.invoke({"table": table}))
            for table in db.tables}


def _singular(name):
    n = str(name).replace("_", " ")
    if n.endswith("ies"):
        return n[:-3] + "y"
    if n.endswith("s") and not n.endswith("ss"):
        return n[:-1]
    return n


def _by_role(columns):
    roles = {}
    for c in columns:
        roles.setdefault(c["role"], []).append(c["name"])
    return roles


def build_basic_card(schema_info):
    """A card made from the statistics alone (no model)."""
    tables, ideas = [], []
    for table, d in schema_info.items():
        roles = _by_role(d["columns"])
        measures, dims, dates = (roles.get("measure", []), roles.get("dimension", []),
                                 roles.get("date", []))
        parts = [f"{d['rows']:,} rows."]
        if measures:
            parts.append("Measures: " + ", ".join(measures[:6]) + ".")
        if dims:
            parts.append("Dimensions: " + ", ".join(dims[:6]) + ".")
        if dates:
            parts.append("Dates: " + ", ".join(dates[:4]) + ".")
        tables.append(TableCard(name=table, description=" ".join(parts),
                                entity=_singular(table)))
        for m in measures[:2]:
            label = m.replace("_", " ")
            ideas.append(KPIIdea(name=f"Total {label}",
                                 question=f"What is the total {label} in {table}?",
                                 columns=[f"{table}.{m}"]))
            if dates:
                ideas.append(KPIIdea(
                    name=f"{label.capitalize()} over time",
                    question=f"How has {label} in {table} changed over time?",
                    columns=[f"{table}.{m}", f"{table}.{dates[0]}"]))
    total = sum(d["rows"] for d in schema_info.values())
    return DatasetCard(
        dataset_summary=f"{len(schema_info)} tables, {total:,} rows.",
        tables=tables, kpi_ideas=ideas[:MAX_KPI_IDEAS])


# ----------------------------------------------------------------------
# chunks
# ----------------------------------------------------------------------
def _tables_of(columns):
    return sorted({c.split(".")[0] for c in columns if "." in c})


def build_chunks(schema_info, relationships, card):
    chunks = []

    def add(kind, text, table=None, column=None, tables=None):
        chunks.append({"id": len(chunks), "kind": kind, "text": text.strip(),
                       "table": table, "column": column,
                       "tables": tables if tables is not None else ([table] if table else [])})

    if card.dataset_summary:
        add("dataset", f"Dataset. {card.dataset_summary}")
    table_card = {t.name: t for t in card.tables}
    column_note = {(c.table, c.column): c.description for c in card.columns}
    related = {}
    for r in relationships:
        related.setdefault(r["one_table"], []).append(describe(r))
        related.setdefault(r["many_table"], []).append(describe(r))

    for table, d in schema_info.items():
        tc = table_card.get(table)
        names = ", ".join(c["name"] for c in d["columns"])
        text = f"Table {table}. {tc.description if tc else ''}"
        if tc and tc.entity:
            text += f" One row is a {tc.entity}."
        text += f" Columns: {names}."
        if table in related:
            text += " Related: " + "; ".join(related[table]) + "."
        add("table", text, table=table)
        for c in d["columns"]:
            if c.get("samples"):
                extra = "Values: " + ", ".join(str(x) for x in c["samples"][:5])
            elif c.get("min") is not None:
                extra = f"Range: {c['min']} to {c['max']}"
            else:
                extra = ""
            note = column_note.get((table, c["name"]), "")
            add("column", f"Column {table}.{c['name']} ({c['type']}, {c['role']}). {note} {extra}",
                table=table, column=c["name"])
    for r in relationships:
        add("relation", f"{describe(r)}. Join {r['one_table']} and {r['many_table']} on {r['column']}.",
            tables=[r["one_table"], r["many_table"]])
    for g in card.glossary:
        add("glossary", f"{g.term}: {g.definition} Columns: {', '.join(g.columns)}.",
            tables=_tables_of(g.columns))
    for k in card.kpi_ideas:
        add("kpi", f"KPI idea: {k.name}. {k.question}", tables=_tables_of(k.columns))
    return chunks


def _shortest_path(start, goal, neighbours, max_hops=3):
    """Tables strictly between start and goal on the shortest join path
    (breadth-first search); [] when none exists within max_hops."""
    frontier, seen = [[start]], {start}
    while frontier:
        path = frontier.pop(0)
        if len(path) - 1 > max_hops:
            break
        for n in sorted(neighbours.get(path[-1], set())):
            if n == goal:
                return path[1:]
            if n not in seen:
                seen.add(n)
                frontier.append(path + [n])
    return []


# ----------------------------------------------------------------------
class KnowledgeBase:
    def __init__(self, chunks, index, embedder, schema_info, relationships, card):
        self.chunks = chunks
        self.index = index
        self.embedder = embedder
        self.schema_info = schema_info
        self.relationships = relationships
        self.card = card

    # ---- build ------------------------------------------------------------
    @classmethod
    def build(cls, db, card=None, embedder=None, relationships=None, schema_info=None):
        schema_info = schema_info or collect_schema_info(db)
        relationships = detect_relationships(db) if relationships is None else relationships
        card = card or build_basic_card(schema_info)
        embedder = embedder or get_embedder()
        chunks = build_chunks(schema_info, relationships, card)
        vectors = embedder.embed([c["text"] for c in chunks])
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        return cls(chunks, index, embedder, schema_info, relationships, card)

    # ---- retrieve ---------------------------------------------------------
    def retrieve(self, question, k_chunks=14):
        """The nearest chunks as (score, chunk)."""
        vector = self.embedder.embed([question])
        scores, ids = self.index.search(vector, min(k_chunks, len(self.chunks)))
        return [(float(s), self.chunks[i]) for s, i in zip(scores[0], ids[0]) if i >= 0]

    def _has_name(self, table):
        return any("name" in c["name"].lower() for c in self.schema_info[table]["columns"])

    def select_tables(self, question, k_tables=4, max_tables=8, k_chunks=14, bridge="adjacent"):
        """The tables a question needs: the best-scoring ones, plus the
        tables that connect them and the tables that give names to ids."""
        score = {}
        for s, chunk in self.retrieve(question, k_chunks):
            if s <= 0:
                continue
            weight = CHUNK_WEIGHT.get(chunk["kind"], 0.3)
            for t in chunk["tables"]:
                if t in self.schema_info:
                    score[t] = score.get(t, 0.0) + weight * s
        if not score:
            return list(self.schema_info)[:max_tables]
        selected = sorted(score, key=score.get, reverse=True)[:k_tables]

        neighbours = {}
        for r in self.relationships:
            neighbours.setdefault(r["one_table"], set()).add(r["many_table"])
            neighbours.setdefault(r["many_table"], set()).add(r["one_table"])
        added = []

        # 1. tables that join two selected tables that do not join directly
        if bridge == "path":
            for a in selected:
                for b in selected:
                    if a < b and b not in neighbours.get(a, set()):
                        for t in _shortest_path(a, b, neighbours, max_hops=3):
                            if t not in selected and t not in added:
                                added.append(t)
        else:
            for a in selected:
                for b in selected:
                    if a < b and b not in neighbours.get(a, set()):
                        bridges = (neighbours.get(a, set()) & neighbours.get(b, set())) - set(selected) - set(added)
                        added.extend(sorted(bridges)[:1])
        # 2. the "one" side of a selected table, when it holds a name
        for r in self.relationships:
            if r["many_table"] in selected and r["one_table"] not in selected + added \
                    and self._has_name(r["one_table"]):
                added.append(r["one_table"])
        return (selected + added)[:max_tables]

    # ---- the schema text for the prompt -----------------------------------
    def schema_text(self, tables=None):
        tables = list(tables) if tables is not None else list(self.schema_info)
        card_desc = {t.name: t for t in self.card.tables}
        lines = []

        coverage = []
        for t in tables:
            for c in self.schema_info[t]["columns"]:
                if c["role"] == "date" and c.get("min") is not None:
                    coverage.append(f"- {t}.{c['name']}: {str(c['min'])[:10]} to {str(c['max'])[:10]}")
        if coverage:
            lines.append("DATA COVERAGE (the data only spans these periods; "
                         "never assume it reaches today's date):")
            lines += coverage
            lines.append("")

        lines.append("TABLES")
        for t in tables:
            d = self.schema_info[t]
            tc = card_desc.get(t)
            desc = f" - {tc.description}" if tc and tc.description else ""
            lines.append(f"{t} ({d['rows']:,} rows){desc}")
            for c in d["columns"]:
                if c.get("samples"):
                    detail = " values: " + ", ".join(str(x) for x in c["samples"][:5])
                elif c.get("min") is not None:
                    detail = f" range: {str(c['min'])[:10]} to {str(c['max'])[:10]}"
                elif c["distinct"] == d["rows"] and d["rows"] > 0:
                    detail = " unique"
                else:
                    detail = ""
                lines.append(f"  {c['name']} {c['type']} [{c['role']}]{detail}")
            lines.append("")

        rels = [r for r in self.relationships
                if r["one_table"] in tables and r["many_table"] in tables]
        if rels:
            lines.append("RELATIONSHIPS")
            lines += [f"- {describe(r)}" for r in rels]
            lines.append("")

        glossary = [g for g in self.card.glossary
                    if not _tables_of(g.columns) or set(_tables_of(g.columns)) & set(tables)]
        if glossary:
            lines.append("GLOSSARY")
            lines += [f"- {g.term}: {g.definition} ({', '.join(g.columns)})" for g in glossary]
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def context(self, question, **kwargs):
        """Everything the query agent needs for one question."""
        tables = self.select_tables(question, **kwargs)
        return {"tables": tables, "schema_text": self.schema_text(tables)}

    # ---- save / load ------------------------------------------------------
    def save(self, directory):
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(d / "index.faiss"))
        (d / "chunks.json").write_text(json.dumps(self.chunks, ensure_ascii=False), encoding="utf-8")
        (d / "schema_info.json").write_text(json.dumps(self.schema_info, ensure_ascii=False, default=str), encoding="utf-8")
        (d / "relationships.json").write_text(json.dumps(self.relationships), encoding="utf-8")
        (d / "card.json").write_text(self.card.model_dump_json(indent=2), encoding="utf-8")
        (d / "meta.json").write_text(json.dumps({
            "embedder": self.embedder.name, "dim": int(self.index.d),
            "chunks": len(self.chunks), "tables": list(self.schema_info),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")

    @classmethod
    def load(cls, directory, embedder=None):
        d = Path(directory)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        embedder = embedder or get_embedder(meta["embedder"])
        if embedder.name != meta["embedder"]:
            raise ValueError(f"This index was built with '{meta['embedder']}', "
                             f"not '{embedder.name}'.")
        return cls(
            chunks=json.loads((d / "chunks.json").read_text(encoding="utf-8")),
            index=faiss.read_index(str(d / "index.faiss")),
            embedder=embedder,
            schema_info=json.loads((d / "schema_info.json").read_text(encoding="utf-8")),
            relationships=json.loads((d / "relationships.json").read_text(encoding="utf-8")),
            card=DatasetCard.model_validate_json((d / "card.json").read_text(encoding="utf-8")),
        )
