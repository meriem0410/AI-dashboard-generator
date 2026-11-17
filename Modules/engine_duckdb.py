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


def _sql_literal(value):
    """A single value as a safe SQL string literal (single quotes doubled)."""
    return "'" + str(value).replace("'", "''") + "'"


class Database:
    def __init__(self, con, tables):
        self.con = con
        self.tables = tables      # {name: {'columns': [...], 'rows': int}}
        self._filters = {}        # the filters currently applied to the views

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
                'DESCRIBE SELECT * FROM (\n' + _strip(sql) + '\n) AS q'
            ).fetchall()
        finally:
            cur.close()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    def _where_for(self, name, filters):
        """The WHERE conditions a filter set puts on one table, or [] for none.
        Only columns that exist on the table are used, so a filter that names a
        column the table does not have is simply ignored (it cannot break a view)."""
        columns = set(self.tables.get(name, {}).get('columns', []))
        conditions = []

        date = filters.get('date')
        if date:
            # every table that the date dimension maps to is filtered on its own
            # date column; the end day is inclusive (< end + 1 day works for both
            # DATE and TIMESTAMP columns).
            for mapping in date.get('mappings', []):
                if mapping.get('table') == name and mapping.get('column') in columns:
                    col = mapping['column']
                    conditions.append(
                        f'"{col}" >= DATE {_sql_literal(date["start"])} '
                        f'AND "{col}" < DATE {_sql_literal(date["end"])} + INTERVAL 1 DAY')

        category = filters.get('category')
        if category and category.get('table') == name and category.get('column') in columns:
            values = category.get('values') or []
            if values:
                joined = ', '.join(_sql_literal(v) for v in values)
                conditions.append(f'"{category["column"]}" IN ({joined})')

        return conditions

    def set_filters(self, filters):
        """Rebuild the logical views so that every table reads only the rows the
        filters keep. A stored dashboard's SQL is then re-run on filtered data
        with no model call. Pass {} to restore the original, unfiltered views.

        Returns {table: {'before': n, 'after': m}} for the tables a filter changed,
        so the interface can show how many rows each filter kept."""
        filters = filters or {}
        summary = {}
        for name, meta in self.tables.items():
            conditions = self._where_for(name, filters)
            if conditions:
                where = ' WHERE ' + ' AND '.join(conditions)
                self.con.execute(
                    f'CREATE OR REPLACE VIEW {name} AS SELECT * FROM raw_{name}{where}')
                after = self.con.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                summary[name] = {'before': int(meta['rows']), 'after': int(after)}
            else:
                # no filter on this table: make sure it is the plain, full view
                self.con.execute(
                    f'CREATE OR REPLACE VIEW {name} AS SELECT * FROM raw_{name}')
        self._filters = filters
        return summary

    def clear_filters(self):
        """Restore every view to the full, unfiltered table."""
        return self.set_filters({})

    def run_with_filters(self, sql, filters, **run_kwargs):
        """Run `sql` as if `filters` were applied, then restore whatever filters
        were active before. Nothing leaks into the rest of the dashboard, so this
        is safe to call many times during a render (e.g. to compute a KPI's value
        over each past period). Returns the query's DataFrame."""
        previous = self._filters
        try:
            self.set_filters(filters)
            return self.run(sql, **run_kwargs)
        finally:
            self.set_filters(previous)

    @property
    def filters(self):
        return self._filters

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
            # newlines around the query: a trailing -- comment must not swallow the closing parenthesis
            wrapped = f'SELECT * FROM (\n{_strip(sql)}\n) AS q LIMIT {int(row_cap)}'
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
