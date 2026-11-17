"""
Modules/rag_context.py

Connects the schema knowledge base to the panel graph.

    USE_RAG=on   -> the model sees only the tables the knowledge base selects
    USE_RAG=off  -> the model sees the full schema (default, the old behaviour)

Settings (environment, defaults = the configuration chosen by the retrieval
benchmark: k2_max4 with the basic card):
    RAG_K_TABLES=2  RAG_MAX_TABLES=4  RAG_K_CHUNKS=14  RAG_BRIDGE=adjacent
    RAG_KB_DIR=<folder>   load a saved index instead of building one

The knowledge base is built lazily, once per Database, and cached on it.
"""
import os
import threading

_LOCK = threading.Lock()


def rag_enabled():
    return os.environ.get("USE_RAG", "off").strip().lower() in ("on", "1", "true", "yes")


def settings():
    return {
        "k_tables": int(os.environ.get("RAG_K_TABLES", 2)),
        "max_tables": int(os.environ.get("RAG_MAX_TABLES", 4)),
        "k_chunks": int(os.environ.get("RAG_K_CHUNKS", 14)),
        "bridge": os.environ.get("RAG_BRIDGE", "adjacent"),
    }


def get_kb(db):
    kb = getattr(db, "kb", None)
    if kb is not None:
        return kb
    with _LOCK:
        kb = getattr(db, "kb", None)
        if kb is None:
            from Modules.knowledge_base import KnowledgeBase
            directory = os.environ.get("RAG_KB_DIR")
            kb = KnowledgeBase.load(directory) if directory else KnowledgeBase.build(db)
            db.kb = kb
    return kb


def build_context(db, question):
    """{"tables": [...], "schema_text": str} for one question."""
    kb = get_kb(db)
    tables = kb.select_tables(question, **settings())
    return {"tables": tables, "schema_text": kb.schema_text(tables)}
