"""
Tests for Evaluation/metrics.py (the measuring tools must themselves be right).

    python -m Modules.Scripts.test_eval_metrics
"""
import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Evaluation.metrics import (compare_results, fmt_ci, mcnemar_exact,
                                norm_value, wilson_interval)

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


gold = pd.DataFrame({"driver": ["Ann", "Bob", "Cy"], "miles": [100.0, 250.5, 75.25]})

print("\n--- comparing results ---")
r = compare_results(gold, gold.copy())
check("identical results match exactly", r["match"] and r["exact"] and r["f1"] == 1.0)
check("row order is ignored by default",
      compare_results(gold, gold.iloc[::-1].reset_index(drop=True))["match"])
check("column order and names are ignored",
      compare_results(gold, pd.DataFrame({"m": [75.25, 250.5, 100.0], "who": ["Cy", "Bob", "Ann"]}))["match"])
r = compare_results(gold, gold.assign(extra=[1, 2, 3]))
check("an extra column still matches but is not exact", r["match"] and not r["exact"])
check("text ignores case and outer spaces",
      compare_results(gold, gold.assign(driver=[" ann", "BOB", "cy "]))["match"])
check("integers equal floats", compare_results(pd.DataFrame({"n": [3]}), pd.DataFrame({"n": [3.0]}))["match"])
check("floats equal to 6 significant digits",
      compare_results(pd.DataFrame({"x": [1 / 3]}), pd.DataFrame({"x": [0.3333333]}))["match"])
check("a visibly different number does not match",
      not compare_results(pd.DataFrame({"x": [1.0]}), pd.DataFrame({"x": [1.01]}))["match"])
check("dates compare by day",
      compare_results(pd.DataFrame({"d": pd.to_datetime(["2024-01-05"])}),
                      pd.DataFrame({"d": [dt.date(2024, 1, 5)]}))["match"])
check("NaN equals NULL",
      compare_results(pd.DataFrame({"x": [np.nan, 1.0]}), pd.DataFrame({"x": [None, 1.0]}))["match"])
check("Decimal equals float", norm_value(Decimal("2.50")) == norm_value(2.5))

r = compare_results(gold, gold.assign(miles=[100.0, 250.5, 80.0]))
check("a wrong value in a gold column: no match, reason wrong_or_missing_column",
      not r["match"] and r["reason"] == "wrong_or_missing_column" and r["f1"] == 0.0 and abs(r["col_recall"] - 0.5) < 1e-9, str(r))
r = compare_results(gold, gold.iloc[:2])
check("missing rows: no match, wrong_row_count, recall 2/3",
      not r["match"] and r["reason"] == "wrong_row_count" and abs(r["row_recall"] - 2 / 3) < 1e-9 and r["row_precision"] == 1.0, str(r))
r = compare_results(gold, pd.concat([gold, pd.DataFrame({"driver": ["Dee"], "miles": [5.0]})], ignore_index=True))
check("extra rows: precision 3/4, recall 1", abs(r["row_precision"] - 0.75) < 1e-9 and r["row_recall"] == 1.0, str(r))
check("no result", compare_results(gold, None)["reason"] == "no_result")
check("empty prediction", compare_results(gold, gold.iloc[0:0])["reason"] == "empty_result")
check("empty gold and empty prediction match",
      compare_results(gold.iloc[0:0], gold.iloc[0:0])["match"])

ranked = pd.DataFrame({"driver": ["Cy", "Bob", "Ann"], "miles": [300.0, 200.0, 100.0]})
check("ordered: same rows, other order, no match",
      not compare_results(ranked, ranked.iloc[::-1].reset_index(drop=True), ordered=True)["match"])
check("ordered: right order matches", compare_results(ranked, ranked.copy(), ordered=True)["match"])
check("ordered: wrong order is named", compare_results(ranked, ranked.iloc[::-1].reset_index(drop=True), ordered=True)["reason"] == "wrong_order")

# two gold columns with identical values must still be assigned correctly
dup = pd.DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]})
check("duplicate-valued columns are handled", compare_results(dup, pd.DataFrame({"x": [3, 2, 1], "y": [3, 2, 1]}))["match"])
# the same values in the wrong pairing must not match
pair = pd.DataFrame({"k": ["a", "b"], "v": [1, 2]})
check("the same values paired differently do not match",
      not compare_results(pair, pd.DataFrame({"k": ["a", "b"], "v": [2, 1]}))["match"])

print("\n--- ties and float noise ---")
_g = pd.DataFrame({"k": ["a", "b", "c"], "v": [9, 5, 5]})
_p = pd.DataFrame({"k": ["a", "c", "b"], "v": [9, 5, 5]})
check("ordered: rows tied on the value may swap", compare_results(_g, _p, ordered=True)["match"])
_p2 = pd.DataFrame({"k": ["b", "a", "c"], "v": [5, 9, 5]})
check("ordered: a real order error is still caught", compare_results(_g, _p2, ordered=True)["reason"] == "wrong_order")
check("float noise at a rounding boundary does not break equality",
      compare_results(pd.DataFrame({"x": [98741.15]}), pd.DataFrame({"x": [98741.15000000001]}))["match"])

print("\n--- statistics ---")
lo, hi = wilson_interval(18, 25)
check("Wilson interval of 18/25 is about [0.52, 0.86]", abs(lo - 0.524) < 0.005 and abs(hi - 0.857) < 0.005, f"{lo},{hi}")
check("Wilson stays inside [0,1] at the extremes",
      wilson_interval(0, 10)[0] == 0.0 and wilson_interval(10, 10)[1] == 1.0)
check("Wilson with n=0", wilson_interval(0, 0) == (0.0, 0.0))
check("fmt_ci", fmt_ci(18, 25).startswith("72.0%") and "(18/25)" in fmt_ci(18, 25))

b, c, p = mcnemar_exact([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
check("McNemar: 10 vs 0 discordant is significant (p ~ 0.002)", (b, c) == (10, 0) and abs(p - 2 / 1024) < 1e-9, str(p))
check("McNemar: identical outcomes give p = 1", mcnemar_exact([1, 0, 1], [1, 0, 1]) == (0, 0, 1.0))
check("McNemar: 1 vs 3 discordant is not significant", abs(mcnemar_exact([1, 0, 0, 0], [0, 1, 1, 1])[2] - 0.625) < 1e-9)

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
