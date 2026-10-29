import re
import pandas as pd
from config import engine


_READ_ONLY = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def execute_sql(sql):
    """Run a validated read-only query and return a DataFrame.

    Raises on any failure (instead of printing and returning None) so that
    sql_agent can report stage="execution" with the real error message.
    """
    if not sql or not _READ_ONLY.match(sql):
        raise ValueError("Only SELECT/WITH queries may be executed.")

    # Exactly one statement: a ';' may only appear at the very end.
    if ";" in sql.strip().rstrip(";"):
        raise ValueError("Multiple SQL statements are not allowed.")

    return pd.read_sql(sql, engine)