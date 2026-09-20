from config import engine
from config import client
import re 
from Modules.prompt_builder import build_prompt
from Modules.schema_builder import reduce_schema
from Modules.sql_validator import (
    validate_sql,
    fix_sql_server_syntax
)



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
def generate_sql(question, schema, model):

    #schema = reduce_schema(schema, question)

    prompt = build_prompt(schema, question)

    response = client.chat.completions.create(
        model=model,
        temperature=0,
         reasoning_effort="low",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content


# =========================
# SAFE GENERATION (RETRY)
# =========================
# ============================================================
# SAFE GENERATION
# ============================================================

def safe_generate_sql(question, schema, model):

    raw = generate_sql(question, schema, model)

    try:

        # 1. Extract SQL from LLM response
        sql = extract_sql(raw)

        # 2. Clean extracted SQL
        sql = clean_sql(sql)

        # 3. Convert to SQL Server syntax
        sql = fix_sql_server_syntax(sql)

        # 4. Validate
        if validate_sql(sql, schema):
            return sql

        raise ValueError("Generated SQL failed validation.")

    except Exception as e:

        print(f"⚠️ SQL processing error: {e}")
        raise