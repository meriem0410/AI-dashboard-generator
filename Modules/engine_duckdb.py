"""
Modules/engine_duckdb.py

The query engine: an in-memory DuckDB database that runs the SQL written by
the language model.

One Database object = one user session = one uploaded dataset.

Safety layers (the first one is in sql_guard.py and also runs here):
  1. only ONE read-only SELECT is accepted (syntax-tree check);
  2. once the data is loaded, the SQL can no longer read files, install
     extensions or change settings, and it cannot undo this;
  3. memory is limited;
  4. every query has a timeout and a row cap.

Tables are loaded as raw_<name> and the names used by the SQL are VIEWS over
them. Today a view is just SELECT * FROM raw_<name>; later, filters (date
range, dimension values) will rebuild these views so that every stored
dashboard query can be re-run on filtered data without calling the model.
"""
import re
import threading

import duckdb
import pandas as pd

from Modules.sql_guard import check_read_only

MEMORY_LIMIT = '1GB'
THREADS = 2
DEFAULT_TIMEOUT = 30          # seconds
DEFAULT_ROW_CAP = 20000       # rows handed to the dashboard

_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _strip(sql):
    return str(sql).strip().rstrip(';').strip()


def _interrupt(cursor):
    try:
        cursor.interrupt()
    except Exception:
        pass


def _to_df(cursor):
    """cursor.df() when available, otherwise build the frame by hand."""
    try:
        return cursor.df()
    except AttributeError:
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=[d[0] for d in cursor.description])


class Database:
    def __init__(self, con, tables):
        self.con = con
        self.tables = tables      # {name: {'columns': [...], 'rows': int}}

    # ------------------------------------------------------------------
    @classmethod
    def from_dataframes(cls, data, memory_limit=MEMORY_LIMIT):
        """Build the database from {table_name: DataFrame}."""
        con = duckdb.connect(':memory:')
        tables = {}
        for name, df in data.items():
            if not _NAME.match(str(name)):
                raise ValueError(f'Unsafe table name: {name}')
            con.register('_tmp_df', df)
            con.execute(f'CREATE TABLE raw_{name} AS SELECT * FROM _tmp_df')
            con.unregister('_tmp_df')
            con.execute(f'CREATE VIEW {name} AS SELECT * FROM raw_{name}')
            tables[name] = {'columns': [str(c) for c in df.columns],
                            'rows': int(len(df))}

        # Lock everything. The order matters: after lock_configuration no
        # setting can be changed any more.
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute(f'SET threads={THREADS}')
        con.execute('SET enable_external_access=false')
        con.execute('SET lock_configuration=true')
        return cls(con, tables)

    # ------------------------------------------------------------------
    def bind_check(self, sql):
        """Ask DuckDB to understand the query without running it.
        Unknown tables or columns raise a duckdb.Error. Returns the names of
        the result columns."""
        check_read_only(sql)
        cur = self.con.cursor()
        try:
            rows = cur.execute(
                'DESCRIBE SELECT * FROM (' + _strip(sql) + ') AS q'
            ).fetchall()
        finally:
            cur.close()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    def run(self, sql, timeout=DEFAULT_TIMEOUT, row_cap=DEFAULT_ROW_CAP):
        """Run one read-only query and return a pandas DataFrame.
        Raises TimeoutError after `timeout` seconds. If the result was cut
        at `row_cap` rows, df.attrs['truncated'] is True."""
        check_read_only(sql)
        cur = self.con.cursor()
        timer = threading.Timer(timeout, _interrupt, args=(cur,))
        timer.daemon = True
        timer.start()
        try:
            wrapped = f'SELECT * FROM ({_strip(sql)}) AS q LIMIT {int(row_cap)}'
            df = _to_df(cur.execute(wrapped))
        except duckdb.InterruptException:
            raise TimeoutError(
                f'The query took longer than {timeout} seconds and was stopped.'
            )
        finally:
            timer.cancel()
            cur.close()
        if len(df) >= row_cap:
            df.attrs['truncated'] = True
        return df

    # ------------------------------------------------------------------
    def close(self):
        try:
            self.con.close()
        except Exception:
            pass
