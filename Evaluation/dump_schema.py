"""
Evaluation/dump_schema.py

Writes a compact description of the dataset (tables, columns, types, ranges,
sample values, detected relationships) to Evaluation/schema_dump.md. This is
what is needed to write and verify the reference ("gold") SQL of the questions.
It reads only the local dataset; nothing is sent anywhere.

    python -m Evaluation.dump_schema Logistics
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd


def describe_frame(name, df):
    lines = [f"### {name}  ({len(df):,} rows, {len(df.columns)} columns)", "",
             "| column | type | distinct | null % | min | max | examples |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for c in df.columns:
        s = df[c]
        nun = int(s.nunique(dropna=True))
        nulls = 100 * float(s.isna().mean())
        lo = hi = ""
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            if s.notna().any():
                lo, hi = str(s.min())[:19], str(s.max())[:19]
        ex = ", ".join(str(v)[:24] for v in s.dropna().unique()[:4])
        lines.append(f"| {c} | {s.dtype} | {nun} | {nulls:.0f} | {lo} | {hi} | {ex} |")
    return "\n".join(lines)


def main():
    dataset = sys.argv[1] if len(sys.argv) > 1 else "Logistics"
    from Modules.pipeline import ingest, open_database
    data = ingest(str(ROOT / "data" / dataset), source_type="folder")["data"]
    parts = [f"# Schema dump: {dataset}", ""]
    for name, df in data.items():
        parts += [describe_frame(name, df), ""]
    try:
        from Modules.relationships import describe, detect_relationships
        db = open_database(data)
        rels = detect_relationships(db)
        parts += ["## Detected relationships", ""] + [f"- {describe(r)}" for r in rels]
        db.close()
    except Exception as exc:
        parts += [f"(relationships unavailable: {exc})"]
    out = ROOT / "Evaluation" / "schema_dump.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print("\n".join(parts))
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
