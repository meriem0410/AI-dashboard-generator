import os
import re

import pyodbc
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()

# =========================
# Groq configuration
# =========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not configured. Add it to your .env file."
    )

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)


# =========================
# SQL Server configuration
# =========================
def pick_odbc_driver():
    """Use ODBC_DRIVER from .env if it is installed; otherwise pick the
    newest installed 'ODBC Driver NN for SQL Server'. This avoids the
    IM002 'Data source name not found' error caused by a driver name
    that does not exist on the machine."""
    installed = pyodbc.drivers()

    wanted = os.getenv("ODBC_DRIVER")
    if wanted and wanted in installed:
        return wanted

    candidates = [
        d for d in installed
        if re.fullmatch(r"ODBC Driver \d+ for SQL Server", d)
    ]
    if candidates:
        return max(candidates, key=lambda d: int(re.search(r"\d+", d).group()))

    raise RuntimeError(
        "No 'ODBC Driver NN for SQL Server' found. "
        f"Installed drivers: {installed}"
    )


def build_db_url(database=None):
    """SQL-authentication URL built from environment variables.
    URL.create() escapes special characters in the password for us."""
    return URL.create(
        "mssql+pyodbc",
        username=os.getenv("DB_USER", "sa"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "1433")),
        database=database or os.getenv("DB_NAME", "dashboard_workspace"),
        query={
            "driver": pick_odbc_driver(),
            "TrustServerCertificate": "yes",  # local container, self-signed cert
        },
    )


# create_engine does not connect until first use, so importing config
# never fails just because the database is down.
engine = create_engine(build_db_url(), fast_executemany=True)