import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Modules.pipeline import ingest

name = sys.argv[1] if len(sys.argv) > 1 else 'Logistics'   # folder name under data/
DATA_FOLDER = ROOT / 'data' / name
OUT_FOLDER = ROOT / 'data_parquet' / name
OUT_FOLDER.mkdir(parents=True, exist_ok=True)

files = list(DATA_FOLDER.glob('*.csv')) + list(DATA_FOLDER.glob('*.xlsx'))
print(len(files), 'files found in', DATA_FOLDER)
if not files:
    raise SystemExit('No CSV or Excel files found: check the folder name')

t = time.perf_counter()
data = ingest(str(DATA_FOLDER), source_type='folder')['data']
print('ingest', round(time.perf_counter() - t, 1), 's')

for table, df in data.items():
    try:
        df.to_parquet(OUT_FOLDER / f'{table}.parquet', index=False)
    except Exception as e:
        print('PARQUET ERROR', table, '->', e)
        text_cols = df.select_dtypes(include='object').columns
        df[text_cols] = df[text_cols].astype(str)
        df.to_parquet(OUT_FOLDER / f'{table}.parquet', index=False)

mem = psutil.Process().memory_info()
print('peak memory (Windows):', round(getattr(mem, 'peak_wset', mem.rss) / 1024 / 1024), 'MB')