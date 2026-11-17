"""
Modules/Agents/Agent_dashboard.py

The planner: turns the user's request into a dashboard plan.

It replaces plan_dashboard that used to live in app.py. What changed:
  - unsupported requests (the data does not exist) are LISTED with a reason
    instead of silently dropped;
  - requests to change data are LISTED as blocked;
  - when the user lists items, you get exactly those items, no padding and
    no silent cut;
  - every item carries the constraints the user gave (top N, period,
    entity), so they can be checked after the query ran;
  - temperature 0, JSON answer validated with Pydantic, one retry.
"""
import json

from config import GROQ_MODEL, client
from Modules.schemas import Plan, parse_json_model
from Modules.sql_generator import _format_refused

MAX_ITEMS = 12            # safety cap, never reached by a normal request
OPEN_REQUEST_ITEMS = "4 to 6"      # kept for compatibility; see the composition below

# A dashboard is always a complete BI page, however narrow the question:
# KPI cards on top, then charts. The planner is asked for this, and the code
# below checks it and tops it up when the model falls short.
KPI_MIN, KPI_MAX = 3, 5
PLOT_MIN, PLOT_MAX = 4, 7          # bar / line / pie charts
PLOT_KINDS = ("bar", "line", "pie")
ENFORCE_COMPOSITION = True         # tests that exercise the raw planner switch it off

PLANNER_SYSTEM_PROMPT = """
You are a senior BI analyst and dashboard-planning agent.

Design a dashboard from (1) the user's request and (2) the database schema.
Return ONLY one JSON object, no text around it and no code fence:

{
  "title": "Short dashboard title",
  "focus": "What the dashboard investigates, in the user's own terms",
  "listed": false,
  "items": [
    {"id": "p1", "title": "Short title", "question": "A natural-language question answerable from the schema",
     "kind": "kpi", "constraints": {"top_n": null, "period": null, "entity": null}}
  ],
  "unsupported": [{"request": "what the user asked", "reason": "what the data lacks"}],
  "blocked": [{"request": "what the user asked", "reason": "only read-only queries are run"}]
}

RULES
- kind is one of: kpi, bar, line, pie, table. A kpi returns one number.
  bar compares categories, line shows change over time, pie shows a few
  parts of a whole.
- ALWAYS plan a complete BI dashboard, however narrow the question is.
  It has 3 to 5 items of kind kpi (the cards on top) and 4 to 7 items of kind
  bar, line or pie (the charts), plus at most one table. Never fewer, never more.
- Start from what the user asked. If the user LISTS what they want (bullets,
  numbers, several sentences) set "listed": true and make one item per listed
  point, in the same order (a point that asks for two measures stays one item).
  Otherwise set "listed": false and turn the request into its natural items.
- Then complete the dashboard with SUPPORTING items about the same subject:
  kpis such as the number of the main entities (for example the number of
  customers), totals, averages and rates; charts such as a breakdown by
  category, a trend over time when the data has dates, a top N ranking and a
  distribution. Every supporting item must be answerable from the schema and
  must not repeat another item.
- A kpi question returns ONE number. A chart question returns a small table
  of at most 25 rows.
- Use only tables and columns of the schema. Never invent a column, a metric
  or a relationship. The schema starts with DATA COVERAGE: the periods the
  data really spans.
- If a point needs data that does NOT exist in the schema, do NOT make an
  item for it and do NOT replace it with a similar metric: put it in
  "unsupported" and say what is missing.
- If a point asks to change data (delete, update, insert, drop, create,
  export), put it in "blocked". If the same sentence also asks to SHOW
  something read-only (for example the number of remaining records), make an
  item for that read-only part, and say in its title that it is read-only
  and that no data is changed.
- Fill constraints when the user gave them: top_n (an integer, "top 5" is 5),
  period (as the user said it), entity (driver, customer, route ...).
  Otherwise use null.
- Never ask for "recent" periods or "the last N months" unless the user did.
- Do not use ID columns as numeric measures.
- A question must be about the data, never about SQL.
"""


def _call(messages):
    base = dict(model=GROQ_MODEL, temperature=0, reasoning_effort="low",
                max_tokens=3000, messages=messages)
    try:
        response = client.chat.completions.create(
            response_format={"type": "json_object"}, **base)
    except Exception as e:
        if not _format_refused(e):
            raise
        response = client.chat.completions.create(**base)
    return response.choices[0].message.content or ""


def plan_dashboard(question, schema):
    """Return a validated Plan. Raises ValueError if the model cannot produce
    a valid plan after one retry."""
    schema_text = schema if isinstance(schema, str) else str(schema)
    schema_text = schema_text[:18000]
    system = PLANNER_SYSTEM_PROMPT
    user = (f"DATABASE SCHEMA:\n{schema_text}\n\n"
            f"USER'S REQUEST:\n{question}\n\n"
            "Return the JSON plan.")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]

    raw = _call(messages)
    try:
        plan = parse_json_model(raw, Plan)
    except ValueError as first_error:
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content":
                      f"Your answer was not valid: {first_error}\n"
                      "Return the corrected JSON object only."}]
        try:
            plan = parse_json_model(_call(messages), Plan)
        except ValueError as e:
            raise ValueError(f"The planner did not return a valid plan: {e}")

    if ENFORCE_COMPOSITION:
        plan = ensure_composition(plan, system, schema_text, question)

    if len(plan.items) > MAX_ITEMS:
        plan.items = plan.items[:MAX_ITEMS]
    return plan


# ----------------------------------------------------------------------
# composition: 3-5 kpis and 4-7 charts, always
# ----------------------------------------------------------------------
def composition(items):
    """(kpis, plots, tables) counts of a list of plan items."""
    kpis = sum(1 for i in items if i.kind == "kpi")
    plots = sum(1 for i in items if i.kind in PLOT_KINDS)
    tables = sum(1 for i in items if i.kind == "table")
    return kpis, plots, tables


def _norm(text):
    return " ".join(str(text).lower().split())


def ensure_composition(plan, system, schema_text, question):
    """Trim an open request that overshoots, and ask the model for the
    supporting items that are missing. The user's own points are never cut.
    A failing top-up leaves the plan as the model wrote it (never an error)."""
    items = list(plan.items)

    if not plan.listed:                       # an open request: respect the maxima
        kept, k, c = [], 0, 0
        for it in items:
            if it.kind == "kpi":
                k += 1
                if k > KPI_MAX:
                    continue
            elif it.kind in PLOT_KINDS:
                c += 1
                if c > PLOT_MAX:
                    continue
            kept.append(it)
        items = kept

    kpis, plots, _ = composition(items)
    need_kpi = max(0, KPI_MIN - kpis)
    need_plot = max(0, PLOT_MIN - plots)
    plan.items = items
    if not (need_kpi or need_plot):
        return plan

    current = [{"title": i.title, "question": i.question, "kind": i.kind} for i in items]
    ask = (f"DATABASE SCHEMA:\n{schema_text}\n\nUSER'S REQUEST:\n{question}\n\n"
           f"The dashboard so far:\n{json.dumps(current, ensure_ascii=False)}\n\n"
           f"It is too thin. Add exactly {need_kpi} supporting item(s) of kind kpi and "
           f"{need_plot} supporting item(s) of kind bar, line or pie, about the same "
           "subject, answerable from the schema, not repeating any item above. "
           'Return ONLY {"items": [...]} with the same item fields as before.')
    try:
        extra = parse_json_model(_call([{"role": "system", "content": system},
                                        {"role": "user", "content": ask}]), Plan)
    except Exception:
        return plan

    seen_titles = {_norm(i.title) for i in items}
    seen_questions = {_norm(i.question) for i in items}
    added = []
    for it in extra.items:
        if _norm(it.title) in seen_titles or _norm(it.question) in seen_questions:
            continue
        if it.kind == "kpi" and need_kpi > 0:
            need_kpi -= 1
        elif it.kind in PLOT_KINDS and need_plot > 0:
            need_plot -= 1
        else:
            continue
        seen_titles.add(_norm(it.title))
        seen_questions.add(_norm(it.question))
        it.id = f"s{len(added) + 1}"
        items.append(it)
        added.append(it.id)

    # unique ids again, in order; remember which ones were added
    old_to_new = {}
    for n, it in enumerate(items, start=1):
        old = it.id
        it.id = f"p{n}"
        old_to_new[old] = it.id
    plan.items = items
    plan.added = [old_to_new[a] for a in added]
    return plan
