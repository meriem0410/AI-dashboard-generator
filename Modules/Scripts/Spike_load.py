import os
import sys
import time
from pathlib import Path

import duckdb
import psutil

ROOT = Path(__file__).resolve().parents[2]
name = sys.argv[1] if len(sys.argv) > 1 else 'Logistics'
PARQUET = ROOT / 'data_parquet' / name

def mb():
    return round(psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024)

files = sorted(PARQUET.glob('*.parquet'))
if not files:
    raise SystemExit('No parquet files: run spike_prepare.py first')

print('before', mb(), 'MB')
con = duckdb.connect(':memory:')
t = time.perf_counter()
for f in files:
    con.execute(f"CREATE TABLE {f.stem} AS SELECT * FROM read_parquet('{f.as_posix()}')")
print('loading', round(time.perf_counter() - t, 2), 's -', mb(), 'MB')

total = 0
t = time.perf_counter()
for f in files:
    n = con.execute(f'SELECT COUNT(*) FROM {f.stem}').fetchall()[0][0]
    total += n
    print(f'  {f.stem}: {n} rows')
print('total rows', total, '- count queries', round(time.perf_counter() - t, 3), 's -', mb(), 'MB')
