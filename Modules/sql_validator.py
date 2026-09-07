from config import engine
from config import client
from sqlalchemy import inspect
import re


def validate_query(sql, engine):
    """
    Complete validation before execution.
    """

    schema_result = validate_schema_compatibility(
        sql,
        engine
    )

    return {
        "schema_valid": schema_result["valid"],
        "schema_errors": schema_result["errors"]
    }

# ============================================================
# SQL SCHEMA VALIDATION
# ============================================================

def validate_schema_compatibility(sql, engine):
    """
    Checks whether tables and columns referenced in the SQL
    actually exist in the database.

    Returns:
        {
            "valid": True/False,
            "errors": [...]
        }
    """

    inspector = inspect(engine)

    # --------------------------------------------------------
    # Get database tables
    # --------------------------------------------------------

    tables = inspector.get_table_names()

    # Case-insensitive lookup
    table_map = {
        table.lower(): table
        for table in tables
    }

    errors = []

    # --------------------------------------------------------
    # Extract tables appearing after FROM / JOIN
    # --------------------------------------------------------

    table_pattern = re.compile(
        r'\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)'
        r'(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?',
        re.IGNORECASE
    )

    matches = table_pattern.findall(sql)

    referenced_tables = {}

    for table_name, alias in matches:

        table_key = table_name.lower()

        if table_key not in table_map:
            errors.append(
                f"Unknown table: {table_name}"
            )
            continue

        real_table = table_map[table_key]

        # If alias exists, store it
        if alias:
            # Avoid interpreting SQL keywords as aliases
            if alias.upper() not in {
                "ON", "WHERE", "GROUP", "ORDER",
                "HAVING", "JOIN", "LEFT", "RIGHT",
                "INNER", "OUTER", "FULL"
            }:
                referenced_tables[alias.lower()] = real_table

        referenced_tables[table_name.lower()] = real_table

    # --------------------------------------------------------
    # Validate table.column references
    # --------------------------------------------------------

    column_pattern = re.compile(
        r'\b([A-Za-z_][A-Za-z0-9_]*)\.'
        r'([A-Za-z_][A-Za-z0-9_]*)\b'
    )

    column_matches = column_pattern.findall(sql)

    checked_columns = set()

    for qualifier, column in column_matches:

        qualifier_key = qualifier.lower()
        column_key = column.lower()

        if qualifier_key not in referenced_tables:
            continue

        table_name = referenced_tables[qualifier_key]

        pair = (table_name.lower(), column_key)

        if pair in checked_columns:
            continue

        checked_columns.add(pair)

        columns = inspector.get_columns(table_name)

        valid_columns = {
            col["name"].lower()
            for col in columns
        }

        if column_key not in valid_columns:

            errors.append(
                f"Unknown column: "
                f"{qualifier}.{column}"
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }

# =========================
# VALIDATION
# =========================
def extract_schema_elements(schema_text):
    tables = set()
    columns = set()

    for line in schema_text.split("\n"):
        line = line.strip()

        if line.startswith("TABLE"):
            tables.add(line.split()[1])

        elif line and not line.startswith("(") and not line.startswith(")"):
            col = line.split()[0]
            columns.add(col)

    return tables, columns


def validate_sql(sql, schema_text):

    sql_lower = sql.lower()

    forbidden_words = [
        "orders",
        "transactions",
        "sales",
        "invoice",
        "payment"
    ]

    for word in forbidden_words:
        if word in sql_lower and word not in schema_text.lower():
            return False

    return True






# =========================
# SQL SERVER FIXER
# =========================
# ============================================================
# FIX SQL SERVER SYNTAX
# ============================================================

def fix_sql_server_syntax(sql: str) -> str:
    """
    Fix common SQL dialect issues before sending SQL
    to Microsoft SQL Server.
    """

    if not sql:
        raise ValueError("Empty SQL")

    sql = sql.strip()

    # --------------------------------------------------------
    # 1. Remove markdown
    # --------------------------------------------------------
    sql = re.sub(
        r"```(?:sql|SQL)?",
        "",
        sql
    )

    sql = sql.replace("```", "")

    # --------------------------------------------------------
    # 2. Remove MySQL-style backticks
    #
    # `customer_name` -> customer_name
    # --------------------------------------------------------
    sql = sql.replace("`", "")

    # --------------------------------------------------------
    # 3. Remove accidental double semicolons
    # --------------------------------------------------------
    sql = re.sub(r";+", ";", sql)

    # --------------------------------------------------------
    # 4. SQL Server uses TOP instead of LIMIT
    #
    # LIMIT 5
    # becomes
    # TOP 5
    #
    # This is intentionally conservative.
    # --------------------------------------------------------
    limit_match = re.search(
        r"\bLIMIT\s+(\d+)\s*;?\s*$",
        sql,
        flags=re.IGNORECASE
    )

    if limit_match:
        limit_value = limit_match.group(1)

        sql = re.sub(
            r"\s+LIMIT\s+\d+\s*;?\s*$",
            "",
            sql,
            flags=re.IGNORECASE
        )

        sql = re.sub(
            r"^\s*SELECT\s+",
            f"SELECT TOP {limit_value} ",
            sql,
            count=1,
            flags=re.IGNORECASE
        )

    # --------------------------------------------------------
    # 5. MySQL IFNULL -> SQL Server ISNULL
    # --------------------------------------------------------
    sql = re.sub(
        r"\bIFNULL\s*\(",
        "ISNULL(",
        sql,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # 6. MySQL NOW() -> SQL Server GETDATE()
    # --------------------------------------------------------
    sql = re.sub(
        r"\bNOW\s*\(\s*\)",
        "GETDATE()",
        sql,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # 7. Ensure semicolon
    # --------------------------------------------------------
    sql = sql.strip().rstrip(";") + ";"

    return sql