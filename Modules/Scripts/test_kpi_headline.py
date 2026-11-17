"""
Tests for _kpi_headline: a 'which X is highest' KPI shows the label, not the number.

Loads only that function from app.py (importing all of app.py would pull the whole
pipeline), with its real dependency format_metric_value.

    python -m Modules.Scripts.test_kpi_headline
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules.visualisation import format_metric_value

# pull _kpi_headline (and _kpi_value) straight out of app.py, without importing app
source = (ROOT / "app.py").read_text(encoding="utf-8")
m = re.search(r"\ndef _kpi_headline\(.*?\n(?=\ndef render_kpi)", source, re.S)
assert m, "could not find _kpi_headline in app.py"
ns = {"pd": pd, "format_metric_value": format_metric_value}
exec(m.group(0), ns)
H = ns["_kpi_headline"]

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


# the exact bug: a (label, number) row must headline the LABEL
df = pd.DataFrame({"customer_type": ["Contract"], "total_revenue_potential": [206_800_000.0]})
head, sub = H(df, {"y": "total_revenue_potential"})
check("a 'which type' KPI shows the type as the headline", head == "Contract", head)
check("the amount becomes the small subvalue", sub == "206.8M", sub)

df = pd.DataFrame({"n": [85410]})
head, sub = H(df, {"y": "n"})
check("a plain count shows the number, no subvalue", sub is None and head in ("85410", "85.41K"), (head, sub))

df = pd.DataFrame({"total": [262525800.29]})
head, sub = H(df, {"y": "total"})
check("a large number is formatted", head == "262.53M" and sub is None, (head, sub))

df = pd.DataFrame({"revenue": [100.0], "make": ["Volvo"]})
head, sub = H(df, {"y": "revenue"})
check("label is found whatever the column order", head == "Volvo" and sub is not None, (head, sub))

df = pd.DataFrame({"cost": [95_592_992.0], "gallons": [24_519_037.8]})
head, sub = H(df, {"y": "cost"})
check("two numerics: headline is the chosen metric, no label", head == "95.59M" and sub is None, (head, sub))

df = pd.DataFrame({"customer_type": [None], "total": [500.0]})
head, sub = H(df, {"y": "total"})
check("a null label does not headline 'None'", head == "500" and sub is None, (head, sub))

check("multi-row frame is not a KPI", H(pd.DataFrame({"a": [1, 2]}), {"y": "a"}) == (None, None))
check("empty / None frames are safe", H(None, {}) == (None, None))
check("_kpi_value stays backwards-compatible", ns["_kpi_value"](
    pd.DataFrame({"customer_type": ["Spot"], "v": [3.0]}), {"y": "v"}) == "Spot")

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
