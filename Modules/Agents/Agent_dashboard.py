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
from config import GROQ_MODEL, client
from Modules.schemas import Plan, parse_json_model
from Modules.sql_generator import _format_refused

MAX_ITEMS = 12            # safety cap, never reached by a normal request
OPEN_REQUEST_ITEMS = "4 to 6"

PLANNER_SYSTEM_PROMPT = """
You are a senior BI analyst and dashboard-planning agent.

Design a dashboard from (1) the user's request and (2) the database schema.
Return ONLY one JSON object, no text around it and no code fence:

{
  "title": "Short dashboard title",
  "focus": "What the dashboard investigates, in the user's own terms",
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
- If the user LISTS what they want (bullets, numbered points, several
  sentences), return exactly one item per listed point, in the same order.
  A point that asks for two measures stays one item whose question asks for
  both. Add nothing the user did not ask for and merge nothing.
- If the request is OPEN (for example "analyze fuel costs"), propose
  OPEN_REQUEST_ITEMS items: 1 or 2 kpis and the rest charts, each useful on
  its own, without repeating an analysis.
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
    system = PLANNER_SYSTEM_PROMPT.replace("OPEN_REQUEST_ITEMS", OPEN_REQUEST_ITEMS)
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

    if len(plan.items) > MAX_ITEMS:
        plan.items = plan.items[:MAX_ITEMS]
    return plan
