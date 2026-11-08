import re

from config import client
from Modules.prompt_builder import build_prompt


# ============================================================
# EXTRACT SQL
# ============================================================

def extract_sql(response: str) -> str:
    """
    Extract the SQL query from an LLM response.

    Handles:
    - <think>...</think>
    - ```sql ... ```
    - ``` ... ```
    - explanations before/after SQL
    - SELECT queries
    - WITH/CTE queries
    """

    if not response:
        raise ValueError("Empty LLM response")

    text = response.strip()

    # --------------------------------------------------------
    # 1. Remove Qwen reasoning blocks
    # --------------------------------------------------------
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL
    )

    # --------------------------------------------------------
    # 2. Remove markdown code fences
    # --------------------------------------------------------
    text = re.sub(
        r"```(?:sql|SQL)?",
        "",
        text
    )

    text = text.replace("```", "")

    text = text.strip()

    # --------------------------------------------------------
    # 3. Look for SELECT
    #
    # SELECT is much safer than blindly searching for WITH.
    # --------------------------------------------------------
    select_match = re.search(
        r"\bSELECT\b",
        text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # 4. Look for a real CTE
    #
    # We require:
    # WITH <name> AS (
    #
    # This prevents:
    # "with the customers table..."
    # from being interpreted as SQL.
    # --------------------------------------------------------
    with_match = re.search(
        r"\bWITH\s+[A-Za-z_][A-Za-z0-9_]*\s+AS\s*\(",
        text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # 5. Choose the earliest valid SQL start
    # --------------------------------------------------------
    positions = []

    if select_match:
        positions.append(select_match.start())

    if with_match:
        positions.append(with_match.start())

    if not positions:
        raise ValueError(
            "Could not find a SQL SELECT or valid WITH clause "
            "in the LLM response"
        )

    start = min(positions)

    sql = text[start:].strip()

    # --------------------------------------------------------
    # 6. Remove anything after the SQL query
    #
    # Most generated queries end with ;
    # --------------------------------------------------------
    semicolon = sql.find(";")

    if semicolon != -1:
        sql = sql[:semicolon + 1]

    sql = sql.strip()

    # --------------------------------------------------------
    # 7. Final safety check
    # --------------------------------------------------------
    if not re.match(
        r"^(SELECT\b|WITH\s+[A-Za-z_][A-Za-z0-9_]*\s+AS\s*\()",
        sql,
        flags=re.IGNORECASE
    ):
        raise ValueError(
            "Extracted text does not appear to be valid SQL"
        )

    return sql


# CLEAN SQL
# =========================
# ============================================================
# CLEAN SQL
# ============================================================

def clean_sql(sql: str) -> str:
    """
    Clean an already-extracted SQL query.
    """

    if not sql:
        raise ValueError("Empty SQL query")

    sql = sql.strip()

    # Remove markdown fences if somehow still present
    sql = re.sub(
        r"```(?:sql|SQL)?",
        "",
        sql
    )

    sql = sql.replace("```", "")

    # Remove invisible characters
    sql = sql.replace("\ufeff", "")
    sql = sql.replace("\u200b", "")

    # Remove MySQL-style backticks: `name` -> name
    sql = sql.replace("`", "")

    # Normalize whitespace
    sql = re.sub(r"[ \t]+", " ", sql)

    # Normalize excessive newlines
    sql = re.sub(r"\n\s*\n+", "\n", sql)

    # Remove accidental semicolons/spaces at the end
    sql = sql.strip()

    # Ensure one terminating semicolon
    sql = sql.rstrip(";").strip() + ";"

    return sql

# =========================
# CALL GROQ LLM
# =========================
def _format_refused(error):
    """True when the API refused the JSON response format (not a real failure)."""
    text = str(error).lower()
    return (getattr(error, "status_code", None) == 400
            or "response_format" in text or "json" in text)


def complete_json(messages, model):
    """Call the model asking for a JSON object. If the API refuses that
    response format, call again without it: the prompt already describes the
    JSON, and the answer is parsed tolerantly afterwards."""
    base = dict(model=model, temperature=0, reasoning_effort="low",
                messages=messages)
    try:
        response = client.chat.completions.create(
            response_format={"type": "json_object"}, **base)
    except Exception as e:
        if not _format_refused(e):
            raise
        response = client.chat.completions.create(**base)
    return response.choices[0].message.content


def generate_sql(question, schema, model):
    """First call. Returns the model's raw text (a JSON object, or a bare
    query from an older prompt)."""
    prompt = build_prompt(schema, question)
    return complete_json([{"role": "user", "content": prompt}], model)
