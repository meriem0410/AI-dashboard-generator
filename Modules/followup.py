"""
Modules/followup.py

Talking to a dashboard after it exists: a follow-up question, or a change.

    classify_followup(text, dashboard, schema) -> FollowupAction
        routes a free-text message to one operation:
        add | edit | remove | move | ask | unsupported | blocked

    apply_followup(action, dashboard, schema, db) -> result
        carries the operation out. add/edit/ask run the SAME panel graph as a
        normal panel (so every safety guard still applies); remove/move are pure
        rearrangements (Modules/dashboard_ops). A question ("ask") is answered but
        NOT added — the caller shows the answer and offers to pin it.

Both take injectable `call` (the model) and `run_panel` so the whole module is
testable without a network. Nothing here renders; it returns plain dicts.
"""
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from Modules.dashboard_ops import (append_panel, move_panel, panels,
                                    remove_panel, replace_panel, resolve_panel)
from Modules.schemas import Constraints, parse_json_model


class FollowupAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    operation: Literal["add", "edit", "remove", "move", "ask", "unsupported", "blocked"]
    target: Optional[str] = None                 # which panel (edit/remove/move)
    title: Optional[str] = None                  # a short title for a new/edited panel
    question: Optional[str] = None               # the (new or modified) panel question; the question to answer
    kind: Optional[Literal["kpi", "bar", "line", "pie", "table"]] = None
    constraints: Constraints = Field(default_factory=Constraints)
    position: Optional[str] = None               # move: "top"/"bottom"/a number
    reason: Optional[str] = None                 # unsupported/blocked


ROUTER_SYSTEM_PROMPT = """
You route a user's message about an EXISTING dashboard to ONE operation.
Return ONLY one JSON object, no text around it:

{"operation": "add|edit|remove|move|ask|unsupported|blocked",
 "target": "which existing panel the message refers to, in the user's words, or null",
 "title": "a short title for a new or edited panel, or null",
 "question": "a natural-language question answerable from the schema, or null",
 "kind": "kpi|bar|line|pie|table or null",
 "constraints": {"top_n": null, "period": null, "entity": null},
 "position": "top|bottom|a number, or null",
 "reason": "for unsupported/blocked only"}

OPERATIONS
- add: the user wants a NEW panel ("add a KPI for total fuel cost", "also show revenue by region").
  Put the new panel's question in "question" and a "kind".
- edit: the user wants an EXISTING panel changed ("make the top 5 a top 10", "show that as a line",
  "use revenue instead"). Put the panel referred to in "target", and in "question" write the FULL
  new question for that panel (merge the original intent with the change), with the new "kind"/"constraints".
- remove: the user wants a panel gone ("remove the pie", "delete the trend"). Set "target".
- move: the user wants a panel reordered ("move the trend to the top"). Set "target" and "position".
- ask: the user asks a QUESTION about the data, not a change ("what's the revenue for Spot?",
  "which driver is safest?"). Put it in "question". Do NOT set a panel to change.
- unsupported: the message needs data that is NOT in the schema. Put why in "reason".
- blocked: the message asks to CHANGE data (delete, update, insert, drop, export). Put why in "reason".

RULES
- Use only tables and columns of the schema for any "question". Never invent one.
- "target" is how the user names a panel ("the pie", "top 5 customers", "the second card"); copy their words.
- top_n is an integer ("top 10" -> 10). period/entity only when the user gives them.
- A question is about the data, never about SQL.
"""


def _summarise(dashboard):
    lines = []
    for i, r in enumerate(panels(dashboard), start=1):
        item = r.get("item") or {}
        lines.append(f'{i}. "{item.get("title", "")}" ({item.get("kind", "?")})')
    return "\n".join(lines) or "(the dashboard has no panels yet)"


def _default_call(messages):
    from config import GROQ_MODEL, client
    from Modules.sql_generator import _format_refused
    base = dict(model=GROQ_MODEL, temperature=0, reasoning_effort="low",
                max_tokens=1200, messages=messages)
    try:
        resp = client.chat.completions.create(response_format={"type": "json_object"}, **base)
    except Exception as e:
        if not _format_refused(e):
            raise
        resp = client.chat.completions.create(**base)
    return resp.choices[0].message.content or ""


def classify_followup(text, dashboard, schema, call=None):
    """Route one message to a FollowupAction. Raises ValueError if the model
    cannot produce a valid action after one retry."""
    call = call or _default_call
    schema_text = (schema if isinstance(schema, str) else str(schema))[:14000]
    user = (f"DATABASE SCHEMA:\n{schema_text}\n\nCURRENT DASHBOARD PANELS:\n{_summarise(dashboard)}\n\n"
            f"USER MESSAGE:\n{text}\n\nReturn the JSON action.")
    messages = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": user}]
    raw = call(messages)
    try:
        return parse_json_model(raw, FollowupAction)
    except ValueError as first:
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": f"Your answer was not valid: {first}\n"
                      "Return the corrected JSON object only."}]
        return parse_json_model(call(messages), FollowupAction)


# ---------------------------------------------------------------- executors
def _default_run_panel(*args, **kwargs):
    from Modules.graph_panel import run_panel
    return run_panel(*args, **kwargs)


def _infer_kind(df):
    if df is None:
        return "table"
    if len(df) == 1:
        return "kpi"
    cols = [str(c).lower() for c in df.columns]
    if any(any(w in c for w in ("date", "month", "year", "period")) for c in cols):
        return "line"
    return "bar"


def _panel_result(out, title, question, kind, constraints):
    """Turn a run_panel output into the panel dict the dashboard stores (the same
    shape graph_dashboard builds)."""
    df = out.get("result") if out.get("success") else None
    error = out.get("error")
    if out.get("success") and (df is None or getattr(df, "empty", False)):
        df, error = None, "The query returned no data."
    cons = constraints.model_dump() if hasattr(constraints, "model_dump") else (constraints or {})
    return {
        "item": {"id": "", "title": title or question, "question": question,
                 "kind": kind or _infer_kind(df), "constraints": cons},
        "df": df, "error": error if (not out.get("success") or df is None) else None,
        "sql": out.get("sql"), "attempts": out.get("attempts", 1),
        "status": out.get("status", "ok"), "assumptions": out.get("assumptions", []),
        "notes": out.get("notes", []), "stage": out.get("stage"), "path": out.get("path"),
    }


def _position_index(position, n):
    if position is None:
        return n - 1
    text = str(position).strip().lower()
    if text in ("top", "start", "beginning", "front", "first"):
        return 0
    if text in ("bottom", "end", "last", "back"):
        return n - 1
    try:
        return max(0, min(int(text) - 1, n - 1))      # 1-based from the user
    except ValueError:
        return n - 1


def _result(ok, operation, message, dashboard=None, panel=None, candidates=None):
    return {"ok": ok, "operation": operation, "message": message,
            "dashboard": dashboard, "panel": panel, "candidates": candidates}


def _resolve_target(dashboard, action):
    res = resolve_panel(dashboard, action.target or "")
    if res.get("candidates"):
        titles = [panels(dashboard)[i]["item"]["title"] for i in res["candidates"]]
        return None, _result(False, action.operation,
                             "Which panel do you mean: " + "; ".join(titles) + "?",
                             candidates=res["candidates"])
    idx = res.get("index")
    if idx is None:
        return None, _result(False, action.operation,
                             f"I couldn't find a panel matching “{action.target}”.")
    return idx, None


def apply_followup(action, dashboard, schema, db, run_panel=None):
    """Carry out a FollowupAction. Returns a result dict:
       {ok, operation, message, dashboard, panel, candidates}.
       dashboard is the updated dashboard (same object) for add/edit/remove/move;
       panel is a transient result for 'ask' (shown, and pinnable)."""
    run_panel = run_panel or _default_run_panel
    op = action.operation

    if op == "blocked":
        return _result(False, "blocked", action.reason or
                       "That would change the data; only read-only queries are run.")
    if op == "unsupported":
        return _result(False, "unsupported", action.reason or
                       "The data doesn't contain what that needs.")

    if op in ("remove", "move", "edit"):
        idx, err = _resolve_target(dashboard, action)
        if err:
            return err

    if op == "remove":
        removed = remove_panel(dashboard, idx)
        return _result(True, "remove", f"Removed “{removed['item']['title']}”.", dashboard)

    if op == "move":
        move_panel(dashboard, idx, _position_index(action.position, len(panels(dashboard))))
        return _result(True, "move", "Moved the panel.", dashboard)

    if op in ("add", "edit", "ask"):
        question = action.question or ""
        if not question:
            return _result(False, op, "I couldn't tell what to run from that message.")
        kind, title = action.kind, action.title
        if op == "edit":
            # An edit keeps what the user did not ask to change: the panel's
            # kind and its title (a table stays a table, its name stays).
            old_item = panels(dashboard)[idx]["item"]
            kind = kind or old_item.get("kind")
            title = title or old_item.get("title")
        out = run_panel(question, schema, db, kind=kind, constraints=action.constraints)
        panel = _panel_result(out, title, question, kind, action.constraints)
        if op == "ask":
            msg = ("Here's the answer." if panel["df"] is not None
                   else (panel["error"] or "I couldn't answer that from the data."))
            return _result(panel["df"] is not None, "ask", msg, panel=panel)
        if op == "add":
            append_panel(dashboard, panel)
            return _result(True, "add", f"Added “{panel['item']['title']}”.", dashboard)
        # edit: a failed re-run never destroys a working panel
        if panel["df"] is None:
            return _result(False, "edit",
                           "I couldn't apply that change, so the panel was left as it was"
                           + (f" ({panel['error']})." if panel.get("error") else "."))
        old_item = panels(dashboard)[idx]["item"]
        for key in ("style", "sort", "kind_locked"):   # presentation choices survive a re-run
            if key in old_item and key not in panel["item"]:
                panel["item"][key] = old_item[key]
        replace_panel(dashboard, idx, panel)
        return _result(True, "edit", f"Updated “{panel['item']['title']}”.", dashboard)

    return _result(False, op, "I didn't understand that change.")


# ------------------------------------------------------------
# PRESENTATION EDITS: no SQL, no model
# ------------------------------------------------------------
# "rename it to X", "sort from lowest to highest", "show as a table/pie/treemap"
# change how a panel LOOKS, not what it computes. Sending them through the model
# re-generated the SQL and could drift (a rename turned a top-5 table into a
# different bar chart). They are recognised here and applied directly to the
# panel item, so the data and the SQL are untouched.

_KIND_ALIASES = {
    "table": ("table", None), "list": ("table", None), "grid": ("table", None),
    "bar": ("bar", "vertical"), "column": ("bar", "vertical"), "bars": ("bar", "vertical"),
    "horizontal": ("bar", "horizontal"),
    "line": ("line", None), "trend": ("line", None), "area": ("line", "area"),
    "pie": ("pie", None), "donut": ("pie", None), "doughnut": ("pie", None),
    "treemap": ("bar", "treemap"), "tree map": ("bar", "treemap"),
    "scatter": ("bar", "scatter"), "histogram": ("bar", "histogram"),
    "kpi": ("kpi", None), "card": ("kpi", None),
}

_RENAME_PATTERNS = (
    r"\b(?:rename|retitle)\b(?:\s+(?:it|this|the\s+(?:panel|chart|table|title|label)))?\s+(?:to|as)\s+(?P<v>.+)",
    r"\bchange\s+the\s+(?:title|label|name|heading)\b(?:\s+of\s+(?:it|this|the\s+\w+))?\s+(?:to|into)\s+(?P<v>.+)",
    r"\b(?:set|make)\s+the\s+(?:title|label|name|heading)\s+(?:to\s+|be\s+)?(?P<v>.+)",
    r"\b(?:call|name|title)\s+it\s+(?P<v>.+)",
    r"^\s*(?:title|label|name)\s*[:=]\s*(?P<v>.+)",
)
_RENAME_INTENT = re.compile(
    r"\b(rename|retitle)\b|\b(title|label|name|heading)\b.*\b(change|edit|update|different|better|new|shorter)\b"
    r"|\b(change|edit|update)\b.*\b(title|label|name|heading)\b")

_ASC = re.compile(r"\b(ascending|asc|lowest\s+(?:to|first)|smallest\s+(?:to|first)|least\s+to|"
                  r"low\s+to\s+high|increasing|a\s*(?:-|to)\s*z|alphabetical)")
_DESC = re.compile(r"\b(descending|desc|highest\s+(?:to|first)|largest\s+(?:to|first)|biggest\s+(?:to|first)|"
                   r"most\s+to|high\s+to\s+low|decreasing|z\s*(?:-|to)\s*a)")
_REVERSE = re.compile(r"\b(reverse|invert|inverse|flip)\b")
_SORT_WORD = re.compile(r"\b(sort|order|rank|arrange)\w*\b")
# words that mean the user wants different DATA, not a different look
_DATA_WORDS = re.compile(r"\b(top|bottom|only|filter|exclude|include|instead|per|by\s+month|"
                         r"by\s+year|average|sum|count|percentage|share|ratio|where|last|between)\b")


def _clean_value(v):
    v = v.strip().strip(" .;")
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'“”«»":
        v = v[1:-1]
    v = v.strip("“”«»\"' ")
    return v


def _match_column(text, columns):
    """The result column named after 'by' in a sort request, fuzzily."""
    m = re.search(r"\bby\s+(?:the\s+)?([\w\s]+?)(?:\s+(?:from|in|asc|desc|ascending|descending|"
                  r"lowest|highest|smallest|largest)\b|$)", text)
    if not m:
        return None
    want = m.group(1).strip().replace(" ", "_")
    for c in columns:
        if str(c).lower() == want:
            return c
    for c in columns:
        name = str(c).lower()
        if want in name or name in want:
            return c
    words = [w for w in want.split("_") if len(w) > 2]
    for c in columns:
        if words and all(w in str(c).lower() for w in words):
            return c
    return None


def presentation_edit(instruction, result):
    """Recognise a look-only change to ONE panel and describe it.

    Returns None when the instruction asks for different data (the caller then
    uses the model), or a dict:
        {"op": "rename", "title": "..."}             or {"op": "ask", "message": ...}
        {"op": "sort", "sort": {"by": col|None, "ascending": bool}}
        {"op": "kind", "kind": "...", "style": "..."|None}
    `result` is the panel dict (item + df)."""
    text = " ".join(str(instruction).split())
    low = text.lower()
    if not low:
        return None

    for pat in _RENAME_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m and _clean_value(m.group("v")):
            return {"op": "rename", "title": _clean_value(m.group("v"))[:120]}
    if _RENAME_INTENT.search(low):
        return {"op": "ask", "message": "What should the new title be? For example: rename it to Top 5 routes by revenue."}

    if _DATA_WORDS.search(low) and not _SORT_WORD.search(low):
        return None

    item = result.get("item") or {}
    df = result.get("df")
    columns = list(df.columns) if df is not None else []

    if _SORT_WORD.search(low) or _REVERSE.search(low) or _ASC.search(low) or _DESC.search(low):
        if re.search(r"\b(top|bottom)\s+\d+", low):
            return None                     # "top 10 sorted ..." changes the data too
        by = _match_column(low, columns)
        current = item.get("sort") or {}
        if _ASC.search(low):
            ascending = True
        elif _DESC.search(low):
            ascending = False
        elif _REVERSE.search(low):
            if "ascending" in current:
                ascending = not current["ascending"]
            else:
                q = f"{item.get('title', '')} {item.get('question', '')}".lower()
                was_asc = any(w in q for w in ("lowest", "least", "worst", "ascending", "smallest"))
                ascending = not was_asc
        else:
            return None
        return {"op": "sort", "sort": {"by": by, "ascending": ascending}}

    m = re.search(r"\b(?:as|into|to|it)\s+(?:a|an)?\s*(tree map|treemap|horizontal|histogram|scatter|area|"
                  r"table|list|grid|bar|bars|column|line|trend|pie|donut|doughnut|kpi|card)\b", low)
    if m and re.search(r"\b(show|display|make|turn|change|switch|convert|render|as)\b", low):
        kind, style = _KIND_ALIASES[m.group(1)]
        return {"op": "kind", "kind": kind, "style": style}
    return None


def apply_presentation_edit(change, dashboard, index):
    """Apply a presentation_edit() change in place. Returns a _result dict."""
    result = panels(dashboard)[index]
    item = result["item"]
    if change["op"] == "ask":
        return _result(False, "edit", change["message"])
    if change["op"] == "rename":
        old = item.get("title")
        item["title"] = change["title"]
        return _result(True, "edit", f"Renamed “{old}” to “{item['title']}”.", dashboard)
    if change["op"] == "sort":
        item["sort"] = change["sort"]
        by = change["sort"].get("by")
        direction = "lowest to highest" if change["sort"]["ascending"] else "highest to lowest"
        what = f" by {str(by).replace('_', ' ')}" if by else ""
        return _result(True, "edit", f"Sorted “{item['title']}”{what}, {direction}.", dashboard)
    if change["op"] == "kind":
        df = result.get("df")
        if change["kind"] == "kpi" and df is not None and len(df) != 1:
            return _result(False, "edit", "A KPI card needs a single value; this panel has "
                           f"{len(df)} rows. Try a bar or a table instead.")
        item["kind"] = change["kind"]
        item["kind_locked"] = True                 # the user chose it: no automatic override
        if change.get("style"):
            item["style"] = change["style"]
        else:
            item.pop("style", None)
        names = {"vertical": "bar chart", "horizontal": "horizontal bar chart", "area": "area chart",
                 "treemap": "treemap", "scatter": "scatter plot", "histogram": "histogram",
                 "bar": "bar chart", "line": "line chart", "pie": "pie chart", "table": "table",
                 "kpi": "KPI card"}
        shown = names.get(change.get("style") or change["kind"], change["kind"])
        return _result(True, "edit", f"“{item['title']}” is now shown as a {shown}.", dashboard)
    return _result(False, "edit", "I didn't understand that change.")


def pin_panel(dashboard, panel):
    """Add a panel that came from an 'ask' answer onto the dashboard."""
    append_panel(dashboard, panel)
    return dashboard
