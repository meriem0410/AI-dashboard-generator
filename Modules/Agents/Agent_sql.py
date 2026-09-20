import time

from config import engine, GROQ_MODEL
from Modules.sql_executor import execute_sql
from Modules.sql_validator import validate_query
from Modules.sql_generator import (
    extract_sql,
    safe_generate_sql
)


# ============================================================
# SQL GENERATION AGENT
# ============================================================

def sql_agent(question, schema):

    # ========================================================
    # 1. SQL GENERATION
    # ========================================================

    generation_start = time.perf_counter()

    try:

        raw_response = safe_generate_sql(
        question,
        schema,
        GROQ_MODEL
        )

        generation_time = (
            time.perf_counter()
            - generation_start
        )

    except Exception as e:

        generation_time = (
            time.perf_counter()
            - generation_start
        )

        return {
            "success": False,
            "stage": "generation",
            "error": str(e),
            "raw_response": None,
            "sql": None,
            "validation": None,
            "result": None,
            "generation_time": generation_time,
            "validation_time": 0,
            "execution_time": 0
        }

    # ========================================================
    # 2. SQL EXTRACTION
    # ========================================================

    try:

        sql = extract_sql(raw_response)

    except Exception as e:

        return {
            "success": False,
            "stage": "extraction",
            "error": str(e),
            "raw_response": raw_response,
            "sql": None,
            "validation": None,
            "result": None,
            "generation_time": generation_time,
            "validation_time": 0,
            "execution_time": 0
        }

    # ========================================================
    # 3. PROTECT AGAINST INVALID FALLBACK
    # ========================================================

    if not sql or "SELECT 'INVALID QUERY'" in sql.upper():

        return {
            "success": False,
            "stage": "extraction",
            "error": "No valid SQL query was produced.",
            "raw_response": raw_response,
            "sql": None,
            "validation": None,
            "result": None,
            "generation_time": generation_time,
            "validation_time": 0,
            "execution_time": 0
        }

    # ========================================================
    # 4. SCHEMA VALIDATION
    # ========================================================

    validation_start = time.perf_counter()

    try:

        validation = validate_query(
            sql,
            engine
        )

        validation_time = (
            time.perf_counter()
            - validation_start
        )

    except Exception as e:

        validation_time = (
            time.perf_counter()
            - validation_start
        )

        return {
            "success": False,
            "stage": "validation",
            "error": str(e),
            "raw_response": raw_response,
            "sql": sql,
            "validation": None,
            "result": None,
            "generation_time": generation_time,
            "validation_time": validation_time,
            "execution_time": 0
        }

    # ========================================================
    # 5. REJECT SCHEMA-INCOMPATIBLE QUERY
    # ========================================================

    if not validation.get("schema_valid", False):

        return {
            "success": False,
            "stage": "schema_validation",
            "error": "Query rejected because of schema incompatibility.",
            "raw_response": raw_response,
            "sql": sql,
            "validation": validation,
            "result": None,
            "generation_time": generation_time,
            "validation_time": validation_time,
            "execution_time": 0
        }

    # ========================================================
    # 6. SQL EXECUTION
    # ========================================================

    execution_start = time.perf_counter()

    try:

        result = execute_sql(sql)

        execution_time = (
            time.perf_counter()
            - execution_start
        )

    except Exception as e:

        execution_time = (
            time.perf_counter()
            - execution_start
        )

        return {
            "success": False,
            "stage": "execution",
            "error": str(e),
            "raw_response": raw_response,
            "sql": sql,
            "validation": validation,
            "result": None,
            "generation_time": generation_time,
            "validation_time": validation_time,
            "execution_time": execution_time
        }

    # ========================================================
    # 7. SUCCESS
    # ========================================================

    return {
        "success": True,
        "stage": "completed",
        "error": None,
        "raw_response": raw_response,
        "sql": sql,
        "validation": validation,
        "result": result,
        "generation_time": generation_time,
        "validation_time": validation_time,
        "execution_time": execution_time
    }