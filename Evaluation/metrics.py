"""
Evaluation/metrics.py

The measuring tools. No model, no network: pure functions that are unit-tested
(Modules/Scripts/test_eval_metrics.py), so a number in the report can be traced
to a definition written here.

Execution accuracy
------------------
A generated query is judged by what it RETURNS, not by how its SQL is spelled
(two different queries can be both right). Its result is compared with the
result of a hand-verified reference ("gold") query:

  match      every column of the gold result appears in the prediction with the
             same values, and the rows agree (as a set of rows, or in order when
             the question asks for a ranking). Extra columns in the prediction
             are allowed: "driver name and miles" answers "miles per driver".
  exact      match, and the prediction has no extra column.
  col_recall share of gold columns found in the prediction.
  row_precision / row_recall / f1
             (only when every gold column is found): how many returned rows are in the gold
             result, and how many gold rows were returned.

Numbers are compared to 6 significant digits (after removing float noise; in ordered
comparisons, rows tied on the numbers may come in any order), text ignoring case and outer
spaces, dates by calendar day, NaN equal to NULL.

Statistics
----------
wilson_interval   95% confidence interval of a proportion (small samples).
mcnemar_exact     paired test: do two conditions differ on the SAME questions?
"""
import itertools
import math
from collections import Counter
from decimal import Decimal

import pandas as pd


# ----------------------------------------------------------------------
# normalising values
# ----------------------------------------------------------------------
def norm_value(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, bool):
        return ("b", bool(v))
    if isinstance(v, (int, float, Decimal)) or hasattr(v, "dtype") and pd.api.types.is_number(v):
        # strip float noise first (sum order changes the last digits), then keep 6 significant
        # digits; without the first step a value such as 98741.15 can fall on either side
        # of a rounding boundary depending on the order of the additions
        return ("n", float(f"{float(f'{float(v):.10g}'):.6g}"))
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "isoformat"):
        ts = pd.Timestamp(v)
        return ("d", str(ts.date()) if ts == ts.normalize() else ts.isoformat())
    return ("s", str(v).strip().casefold())


def _columns(df):
    """List of columns, each a list of normalised values."""
    return [[norm_value(v) for v in df[c].tolist()] for c in df.columns]


# ----------------------------------------------------------------------
# comparing two results
# ----------------------------------------------------------------------
MAX_ASSIGNMENTS = 500     # bound on the column-matching search


def _project(cols, order, n_rows):
    return [tuple(cols[j][i] for j in order) for i in range(n_rows)]


def compare_results(gold, pred, ordered=False):
    """Compare a prediction with the gold result. Both are DataFrames (pred may
    be None). Returns a dict: match, exact, col_recall, row_precision,
    row_recall, f1, reason."""
    out = {"match": False, "exact": False, "col_recall": 0.0,
           "row_precision": 0.0, "row_recall": 0.0, "f1": 0.0, "reason": ""}
    if pred is None:
        out["reason"] = "no_result"
        return out
    if gold is None:
        raise ValueError("the gold result is missing")

    if len(gold) == 0:
        same = len(pred) == 0
        out.update(match=same, exact=same and len(pred.columns) == len(gold.columns),
                   row_precision=1.0 if same else 0.0, row_recall=1.0,
                   f1=1.0 if same else 0.0, col_recall=1.0,
                   reason="" if same else "gold_empty_pred_not")
        return out
    if len(pred) == 0:
        out["reason"] = "empty_result"
        return out

    g_cols, p_cols = _columns(gold), _columns(pred)
    g_counts = [Counter(c) for c in g_cols]
    p_counts = [Counter(c) for c in p_cols]

    def related(g, p):
        """Same values, or one is a subset of the other (rows missing or extra)."""
        return not (g - p) or not (p - g)

    # candidate prediction columns for every gold column
    candidates = [[j for j, pc in enumerate(p_counts) if related(gc, pc)] for gc in g_counts]
    found = [bool(c) for c in candidates]
    out["col_recall"] = sum(found) / max(len(found), 1)

    def rows_of(assignment):
        g_idx = [i for i, a in enumerate(assignment) if a is not None]
        gr = _project(g_cols, g_idx, len(gold))
        pr = _project(p_cols, [assignment[i] for i in g_idx], len(pred))
        return gr, pr

    def numeric_part(row):
        return tuple(x for x in row if x is not None and x[0] == "n")

    def agree(gr, pr):
        if not ordered:
            return Counter(gr) == Counter(pr)
        if Counter(gr) != Counter(pr):
            return False
        # same rows; the ORDER must agree on the ranking values. Rows that tie on those
        # values may legitimately come in either order.
        if all(numeric_part(r) for r in gr):
            return [numeric_part(r) for r in gr] == [numeric_part(r) for r in pr]
        return gr == pr

    # exact search over column assignments (bounded)
    best, tried = None, 0
    pools = [c if c else [None] for c in candidates]
    for combo in itertools.product(*pools):
        tried += 1
        if tried > MAX_ASSIGNMENTS:
            break
        used = [j for j in combo if j is not None]
        if len(used) != len(set(used)):
            continue
        gr, pr = rows_of(list(combo))
        if all(found) and agree(gr, pr):
            best = list(combo)
            break
        if best is None:
            best = list(combo)

    if best is None:
        out["reason"] = "no_column_in_common"
        return out

    if not all(found):
        # a gold column is absent (missing, or present with other values): no row-level credit (it would be misleading)
        out["reason"] = "wrong_or_missing_column"
        return out

    gr, pr = rows_of(best)
    if gr:
        common = sum((Counter(gr) & Counter(pr)).values())
        out["row_recall"] = common / len(gr)
        out["row_precision"] = common / max(len(pr), 1)
        p, r = out["row_precision"], out["row_recall"]
        out["f1"] = 2 * p * r / (p + r) if p + r else 0.0

    if agree(gr, pr):
        out["match"] = True
        out["exact"] = len(p_cols) == len(g_cols)
        return out

    if len(pred) != len(gold):
        out["reason"] = "wrong_row_count"
    elif not ordered or Counter(gr) == Counter(pr):
        out["reason"] = "wrong_order" if ordered and Counter(gr) == Counter(pr) else "wrong_values"
    else:
        out["reason"] = "wrong_values"
    return out


# ----------------------------------------------------------------------
# statistics
# ----------------------------------------------------------------------
def wilson_interval(successes, n, z=1.96):
    """95% Wilson score interval for a proportion. (0, 0) when n == 0."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(a_correct, b_correct):
    """Exact two-sided McNemar test on paired outcomes (lists of bool, same
    questions in the same order). Returns (b, c, p) where b = A right and B
    wrong, c = A wrong and B right."""
    if len(a_correct) != len(b_correct):
        raise ValueError("paired lists must have the same length")
    b = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)
    c = sum(1 for x, y in zip(a_correct, b_correct) if y and not x)
    n = b + c
    if n == 0:
        return b, c, 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return b, c, min(1.0, 2 * tail)


def fmt_ci(successes, n):
    """'72.0% [53.0, 85.6] (18/25)'"""
    if n == 0:
        return "n/a (0)"
    lo, hi = wilson_interval(successes, n)
    return f"{100 * successes / n:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}] ({successes}/{n})"
