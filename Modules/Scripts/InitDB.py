"""
Create the database (if missing) and load every file found in DATA_DIR.

Run from the project root:
    python -m scripts.init_db
    docker compose run --rm app python -m scripts.init_db

Replaces the manual SSIS / SSMS load. Uses the same ingest() and
load_to_database() as the Streamlit upload path.
"""

import os
import re
import time

from sqlalchemy import create_engine, text

from config import build_db_url, engine
from Modules.pipeline import ingest, load_to_database

DATA_DIR = os.getenv("DATA_DIR", "data/Logistics")
DB_NAME = os.getenv("DB_NAME", "LogisticsDB")


def wait_for_server(admin_engine, tries=30, delay=2):
    for _ in range(tries):
        try:
            with admin_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            time.sleep(delay)
    raise RuntimeError("SQL Server did not become reachable. Is the db container up?")


def ensure_database():
    if not re.fullmatch(r"\w+", DB_NAME):
        raise ValueError(f"Unsafe database name: {DB_NAME}")

    admin_engine = create_engine(
        build_db_url("master"), isolation_level="AUTOCOMMIT"
    )
    wait_for_server(admin_engine)

    with admin_engine.connect() as conn:
        conn.execute(
            text(f"IF DB_ID('{DB_NAME}') IS NULL CREATE DATABASE [{DB_NAME}]")
        )
    admin_engine.dispose()


if __name__ == "__main__":
    print(f"Creating database {DB_NAME} if needed...")
    ensure_database()

    print(f"Loading files from {DATA_DIR}...")
    result = ingest(DATA_DIR, source_type="folder")

    tables = load_to_database(result["data"], engine)
    print(f"Done. {len(tables)} tables loaded: {', '.join(tables)}")