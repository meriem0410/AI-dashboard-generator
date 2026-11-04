"""
Modules/sql_guard.py

First safety layer: reads the SQL written by the language model as a syntax
tree (with sqlglot) and refuses everything except ONE read-only SELECT.

A regular expression cannot do this reliably. For example, a query that
starts with WITH can end in DELETE, and two statements can follow each other
without any semicolon. A syntax tree sees the real structure.

check_read_only(sql) returns None when the query is acceptable and raises
GuardError otherwise.
  - GuardError.retryable is True when the model can plausibly fix the problem
    (the query could not be parsed, or contains several statements).
  - It is False for anything that looks like a write or a file access: the
    agent stops instead of asking the model to try again.
"""
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


class GuardError(ValueError):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def _classes(*names):
    """Classes that exist in the installed sqlglot version."""
    return tuple(getattr(exp, n) for n in names if hasattr(exp, n))


# The top of the tree must be one of these.
_ALLOWED_ROOTS = _classes('Select', 'SetOperation', 'Union', 'Subquery')

# None of these may appear anywhere inside the tree.
_FORBIDDEN_NODES = _classes(
    'Insert', 'Update', 'Delete', 'Merge', 'Drop', 'Create', 'Alter',
    'Command', 'Copy', 'Set', 'Use', 'Pragma', 'Attach', 'Detach', 'Into',
    'Install', 'Transaction', 'Commit', 'Rollback', 'Export', 'Describe',
    'Show', 'TruncateTable',
)

# Functions that read files, list files or expose engine internals.
_BLOCKED_PREFIXES = ('read_', 'duckdb_', 'pragma_', 'parquet_', 'csv_scan',
                     'json_scan')
_BLOCKED_NAMES = {'glob', 'sniff_csv', 'current_setting', 'query',
                  'query_table', 'getenv'}


def _short(error, limit=300):
    return ' '.join(str(error).split())[:limit]


def _function_name(node):
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    if isinstance(node, exp.Func):
        try:
            return node.sql_name().lower()
        except Exception:
            return node.key.lower()
    return None


def check_read_only(sql):
    if not sql or not str(sql).strip():
        raise GuardError('The query is empty.', retryable=True)

    try:
        statements = [s for s in sqlglot.parse(sql, read='duckdb')
                      if s is not None]
    except SqlglotError as e:
        raise GuardError('The query could not be parsed as DuckDB SQL: '
                         + _short(e), retryable=True)

    if len(statements) != 1:
        raise GuardError('Exactly one SQL statement is allowed, found '
                         f'{len(statements)}.', retryable=True)

    tree = statements[0]
    if not isinstance(tree, _ALLOWED_ROOTS):
        raise GuardError('Only read-only SELECT queries are allowed '
                         f'(found: {tree.key.upper()}).')

    for node in tree.find_all(exp.Expression):
        if isinstance(node, _FORBIDDEN_NODES):
            raise GuardError('A forbidden operation was found inside the '
                             f'query: {node.key.upper()}.')

        if isinstance(node, exp.Table):
            # A table must be a plain name. A string such as '/etc/passwd' or
            # 'data.csv' in the FROM clause would make DuckDB read a file.
            table_name = node.name
            if isinstance(node.this, exp.Literal) or (
                    isinstance(node.this, exp.Identifier)
                    and not re.fullmatch(r'\w+', table_name or '')):
                raise GuardError('Reading a file by path is not allowed.')

        name = _function_name(node)
        if name and (name in _BLOCKED_NAMES
                     or name.startswith(_BLOCKED_PREFIXES)):
            raise GuardError(f'The function {name} is not allowed.')


def is_safe(sql):
    """(True, None) or (False, reason). Convenience for tests and the UI."""
    try:
        check_read_only(sql)
        return True, None
    except GuardError as e:
        return False, str(e)
