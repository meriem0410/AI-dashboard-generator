"""
Tests for the value hints in Modules/schema_builder.build_llm_schema.

    python -m Modules.Scripts.test_schema_values
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("GROQ_API_KEY", "test-dummy-key")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.schema_builder import build_llm_schema

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


profile = {
    "drivers": {"columns": {
        "driver_id": {"dtype": "object", "role": "id"},
        "employment_status": {"dtype": "object", "role": "dimension"},
        "cdl_class": {"dtype": "object", "role": "dimension"},
        "first_name": {"dtype": "object", "role": "dimension"},
        "years_experience": {"dtype": "int64", "role": "measure"},
    }},
    "relationships": [{"from_table": "x"}],          # not a table -> ignored
}
data = {"drivers": pd.DataFrame({
    "driver_id": [f"DRV{i:03d}" for i in range(60)],
    "employment_status": (["Active"] * 40 + ["Terminated"] * 15 + ["On Leave"] * 5),
    "cdl_class": (["Class A", "Class B"] * 30),
    "first_name": [f"Name{i}" for i in range(60)],   # high-cardinality -> no hint
    "years_experience": list(range(60)),
})}

# without data: unchanged, no hints (backwards compatible)
plain = build_llm_schema(profile)
check("without data the schema has the columns", "employment_status: object (dimension)" in plain)
check("without data there are no value hints", "one of:" not in plain)

# with data: hints with the REAL casing
full = build_llm_schema(profile, data)
check("a low-cardinality column lists its real values",
      "employment_status: object (dimension) -- one of: Active, On Leave, Terminated" in full, full)
check("the casing is exactly the data's ('Active', not 'active')", "Active" in full and "active," not in full)
check("a two-value column is listed", "cdl_class: object (dimension) -- one of: Class A, Class B" in full)
check("an id column gets no values", "driver_id" in full and "driver_id: object (id) -- one of" not in full)
check("a high-cardinality text column gets no values", "first_name: object (dimension)\n" in full
      and "Name0" not in full)
check("a numeric column gets no values", "years_experience: int64 (measure)\n" in full)
check("relationships (not a table) are skipped", "TABLE relationships" not in full)

# booleans
pb = {"t": {"columns": {"on_time_flag": {"dtype": "bool", "role": "dimension"}}}}
db = {"t": pd.DataFrame({"on_time_flag": [True, False, True]})}
check("a boolean column is hinted true/false",
      "on_time_flag: bool (dimension) -- one of: true, false" in build_llm_schema(pb, db))

# a column present in the profile but missing from the data must not crash
pm = {"t": {"columns": {"ghost": {"dtype": "object", "role": "dimension"}}}}
check("a column not in the data is safe", "ghost: object (dimension)" in build_llm_schema(pm, {"t": pd.DataFrame({"x": [1]})}))

# a very-high-cardinality cap
many = {"t": {"columns": {"c": {"dtype": "object", "role": "dimension"}}}}
dmany = {"t": pd.DataFrame({"c": [f"v{i}" for i in range(100)]})}
check("more than the cap -> no hint", "one of:" not in build_llm_schema(many, dmany))

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
