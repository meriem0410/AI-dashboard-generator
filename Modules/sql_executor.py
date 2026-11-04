"""
Modules/sql_executor.py

Runs a query on the session's Database and returns a DataFrame.
The Database re-checks the query with the safety guard, applies a timeout
and a row cap, and raises on any failure so that sql_agent can report
stage="execution" with the real error message.
"""


def execute_sql(sql, db):
    return db.run(sql)
