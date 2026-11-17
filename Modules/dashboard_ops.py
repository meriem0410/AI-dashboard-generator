"""
Modules/dashboard_ops.py

The vocabulary of changing an existing dashboard, as pure functions on the
dashboard dict that run_dashboard produces:

    {"question", "plan": {"title","focus","items":[item,...]},
     "results": [{"item", "df", "sql", ...}, ...],
     "unsupported": [...], "blocked": [...]}

Follow-up and modification (the LLM router, the panel re-runs) build on these.
Nothing here calls a model or the database: given a resolved target and a ready
panel result, it rearranges the dict and keeps it consistent (ids unique,
plan.items mirroring results). Resolving the user's words to a panel
("the pie", "top 5 customers", "the second card") is here too, because that is
deterministic and worth testing on its own.
"""
import re

PLOT_KINDS = ("bar", "line", "pie")

# words the user uses for a kind -> the kinds they mean
_KIND_WORDS = {
    "kpi": ("kpi",), "card": ("kpi",), "metric": ("kpi",),
    "bar": ("bar",), "column": ("bar",),
    "line": ("line",), "trend": ("line",), "time": ("line",),
    "pie": ("pie",), "donut": ("pie",), "doughnut": ("pie",),
    "table": ("table",),
    "chart": PLOT_KINDS, "graph": PLOT_KINDS, "plot": PLOT_KINDS,
    "panel": None,            # any kind
}

_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2,
             "fourth": 3, "4th": 3, "fifth": 4, "5th": 4, "sixth": 5, "6th": 5,
             "seventh": 6, "7th": 6, "eighth": 7, "8th": 7, "last": -1}

_STOP = {"the", "a", "an", "of", "for", "by", "show", "me", "remove", "delete",
         "drop", "add", "please", "this", "that"}
# every word that names a KIND is not a title word (so "the bar chart" has no
# title words left and is correctly ambiguous when there are several bars)
_KIND_TOKENS = set(_KIND_WORDS) | set(_ORDINALS) | {"chart", "graph", "plot", "panel", "card"}


def _norm(text):
    return " ".join(str(text).lower().split())


def panels(dashboard):
    return dashboard.get("results", [])


def _kind_of(result):
    return (result.get("item") or {}).get("kind")


def _kinds_wanted(text):
    """The kinds a reference names, or None for 'any'. Returns (kinds_or_None, matched)."""
    for word, kinds in _KIND_WORDS.items():
        if re.search(r"\b" + word + r"\b", text):
            return kinds, True
    return None, False


def _ordinal_in(text):
    for word, idx in _ORDINALS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", text):
            return idx
    m = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", text)
    if m:
        return int(m.group(1)) - 1
    return None


def resolve_panel(dashboard, ref):
    """Find the panel a user reference points to.

    Returns {"index": i} on a single match, {"index": None} on no match, or
    {"candidates": [i, ...]} when the reference fits more than one panel (so the
    caller can ask which). `ref` is free text ("the pie", "top 5 customers",
    "second kpi", "p3") or an integer index."""
    results = panels(dashboard)
    n = len(results)
    if isinstance(ref, int):
        if -n <= ref < n:
            return {"index": ref % n}            # a negative index becomes its positive form
        return {"index": None}
    text = _norm(ref)

    # an explicit id (p3, s1)
    for i, r in enumerate(results):
        if (r.get("item") or {}).get("id", "").lower() == text:
            return {"index": i}

    kinds, named_kind = _kinds_wanted(text)
    subset = [i for i, r in enumerate(results)
              if kinds is None or _kind_of(r) in kinds]

    # the words left once stop-words, kind words and ordinals are removed
    content_words = [w for w in re.findall(r"[a-z0-9]+", text)
                     if w not in _STOP and w not in _KIND_TOKENS]

    # kind + ordinal ("the second chart", "the pie", "the last kpi")
    ordinal = _ordinal_in(text)
    if named_kind:
        if ordinal is not None:
            return {"index": subset[ordinal]} if subset and -len(subset) <= ordinal < len(subset) else {"index": None}
        if len(subset) == 1:
            return {"index": subset[0]}
        # a bare kind that matches several, with no title words -> ambiguous
        if not content_words:
            return {"candidates": subset} if subset else {"index": None}

    # title match on the remaining words
    if content_words:
        words = content_words
        scored = []
        for i in subset:
            title = _norm((results[i].get("item") or {}).get("title", ""))
            hits = sum(1 for w in words if w in title)
            if hits:
                scored.append((hits, i))
        if scored:
            best = max(h for h, _ in scored)
            top = [i for h, i in scored if h == best]
            return {"index": top[0]} if len(top) == 1 else {"candidates": top}

    if ordinal is not None and subset:
        return {"index": subset[ordinal]} if -len(subset) <= ordinal < len(subset) else {"index": None}
    return {"index": None}


# ---------------------------------------------------------------- mutations
def _renumber(dashboard):
    """Give panels fresh unique ids p1..pn and keep plan.items in step."""
    results = panels(dashboard)
    for n, r in enumerate(results, start=1):
        if r.get("item"):
            r["item"]["id"] = f"p{n}"
    dashboard.setdefault("plan", {})["items"] = [r["item"] for r in results]
    return dashboard


def remove_panel(dashboard, index):
    results = panels(dashboard)
    if not (-len(results) <= index < len(results)):
        raise IndexError("no such panel")
    removed = results.pop(index)
    _renumber(dashboard)
    return removed


def append_panel(dashboard, result, position=None):
    """Add a ready panel result. position=None appends; an int inserts there."""
    results = panels(dashboard)
    if position is None:
        results.append(result)
    else:
        results.insert(max(0, min(position, len(results))), result)
    _renumber(dashboard)
    return dashboard


def replace_panel(dashboard, index, result):
    results = panels(dashboard)
    if not (-len(results) <= index < len(results)):
        raise IndexError("no such panel")
    results[index] = result
    _renumber(dashboard)
    return dashboard


def move_panel(dashboard, index, to):
    results = panels(dashboard)
    n = len(results)
    if not (-n <= index < n) or not (-n <= to < n):
        raise IndexError("no such panel")
    r = results.pop(index)
    results.insert(to % n if to < 0 else to, r)
    _renumber(dashboard)
    return dashboard
