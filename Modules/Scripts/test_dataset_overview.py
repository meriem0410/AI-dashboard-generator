"""
Tests for Modules/dataset_overview.py.

    python -m Modules.Scripts.test_dataset_overview
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.dataset_overview import build_profile_summary, column_rows

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
        "years_experience": {"dtype": "int64", "role": "measure"}}},
    "trips": {"columns": {"trip_id": {"dtype": "object", "role": "id"}}},
    "relationships": [{"from_table": "trips", "from_column": "driver_id",
                       "to_table": "drivers", "to_column": "driver_id"}],
}
data = {"drivers": pd.DataFrame({"driver_id": range(150)}),
        "trips": pd.DataFrame({"trip_id": range(85410)})}

summary = build_profile_summary(profile, data)
check("both tables are summarised", set(summary["tables"]) == {"drivers", "trips"})
check("row counts come from the data", summary["tables"]["drivers"]["rows"] == 150
      and summary["tables"]["trips"]["rows"] == 85410)
check("columns carry type and role",
      summary["tables"]["drivers"]["columns"]["employment_status"] == {"type": "object", "role": "dimension"})
check("relationships are kept", summary["relationships"][0]["to_table"] == "drivers")
check("'relationships' is not treated as a table", "relationships" not in summary["tables"])
check("the summary is JSON-serialisable", isinstance(json.dumps(summary), str))
check("row count falls back to the profile when data is absent",
      build_profile_summary({"t": {"columns": {"a": {"dtype": "int64", "role": "measure"}}, "rows": 7}})
      ["tables"]["t"]["rows"] == 7)

rows = column_rows(profile["drivers"])
check("column_rows lists every column with type and role",
      rows == [{"column": "driver_id", "type": "object", "role": "id"},
               {"column": "employment_status", "type": "object", "role": "dimension"},
               {"column": "years_experience", "type": "int64", "role": "measure"}])

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
