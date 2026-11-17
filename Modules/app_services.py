"""
Modules/app_services.py

The app's logic without any Streamlit: turning a finished dashboard into a
stored spec, and a stored spec back into a dashboard by re-running its SQL
(no planner call, no model call).

A spec keeps, for every panel: the item (title, question, chart kind), the SQL
that worked, notes and assumptions, and why a panel failed. It never keeps the
result tables: they are recomputed from the data, so a reopened dashboard
always matches the data it is opened on.
"""
import json


def _plain(value):
    """JSON round trip: the spec must survive being stored."""
    return json.loads(json.dumps(value, default=str))


def dashboard_to_spec(dash, filters=None):
    panels = []
    for r in dash.get("results", []):
        panels.append({
            "item": r.get("item"),
            "sql": r.get("sql"),
            "error": r.get("error"),
            "stage": r.get("stage"),
            "attempts": r.get("attempts", 1),
            "status": r.get("status", "ok"),
            "assumptions": r.get("assumptions", []),
            "notes": r.get("notes", []),
        })
    return _plain({
        "question": dash.get("question"),
        "plan": dash.get("plan"),
        "panels": panels,
        "unsupported": dash.get("unsupported", []),
        "blocked": dash.get("blocked", []),
        "filters": filters or {},
    })


def spec_to_dashboard(spec, run_sql):
    """Rebuild a dashboard dict from a spec. run_sql(sql) -> DataFrame.
    A panel whose SQL fails now (data changed) is shown as failed, never hidden."""
    results = []
    for p in spec.get("panels", []):
        result = {
            "item": p.get("item"), "df": None, "sql": p.get("sql"),
            "error": p.get("error"), "stage": p.get("stage"),
            "attempts": p.get("attempts", 1), "status": p.get("status", "ok"),
            "assumptions": p.get("assumptions", []), "notes": list(p.get("notes", [])),
        }
        if p.get("sql") and not p.get("error"):
            try:
                df = run_sql(p["sql"])
                if df is None or df.empty:
                    result["error"] = "The saved query returns no data on this dataset."
                    result["stage"] = "execution"
                else:
                    result["df"] = df
                    result["stage"] = "completed"
            except Exception as exc:
                result["error"] = f"The saved query could not be re-run: {exc}"
                result["stage"] = "execution"
        results.append(result)
    return {
        "question": spec.get("question"),
        "plan": spec.get("plan") or {"title": "Dashboard", "focus": "", "items": []},
        "results": results,
        "unsupported": spec.get("unsupported", []),
        "blocked": spec.get("blocked", []),
    }


def metadata_from_data(data):
    return {"table_count": len(data),
            "total_rows": int(sum(len(df) for df in data.values())),
            "total_columns": int(sum(df.shape[1] for df in data.values()))}


def default_dataset_name(file_names):
    names = [str(n).rsplit(".", 1)[0] for n in file_names]
    if not names:
        return "Dataset"
    if len(names) == 1:
        return names[0]
    return f"{names[0]} + {len(names) - 1} more"


# ----------------------------------------------------------------------
# Dataset naming: infer a business context from table / column names
# ----------------------------------------------------------------------

import re as _re

# Deterministic and offline: no model call, so the name is reproducible and
# free. Keywords are matched on singular word stems.
DOMAIN_KEYWORDS = {
    "Logistics": ["trip", "vehicle", "driver", "fuel", "shipment", "route",
                  "delivery", "maintenance", "fleet", "warehouse", "cargo",
                  "freight", "truck", "odometer", "incident", "dispatch"],
    "Sales": ["customer", "order", "product", "sale", "category", "basket",
              "cart", "discount", "store", "retail", "price", "item"],
    "Finance": ["invoice", "payment", "account", "transaction", "budget",
                "ledger", "expense", "revenue", "loan", "bank"],
    "HR": ["employee", "salary", "department", "payroll", "hire", "leave",
           "attendance", "recruit", "candidate", "staff"],
    "Healthcare": ["patient", "doctor", "appointment", "diagnosis", "hospital",
                   "prescription", "treatment", "clinic", "physician"],
    "Education": ["student", "course", "teacher", "grade", "enrollment",
                  "exam", "class", "school", "lecture"],
    "Marketing": ["campaign", "lead", "click", "impression", "channel",
                  "conversion", "audience", "ad", "newsletter"],
    "Supply chain": ["supplier", "inventory", "stock", "purchase",
                     "procurement", "vendor", "material"],
    "Customer support": ["ticket", "agent", "sla", "complaint", "support"],
}

TABLE_WEIGHT = 3   # a table name is a stronger signal than a column name
COLUMN_WEIGHT = 1
MIN_SCORE = 3      # at least one table-name hit, or three column hits


def _stems(text):
    out = []
    for word in _re.split(r"[^a-z0-9]+", str(text).lower()):
        if not word:
            continue
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif (word.endswith("s") and len(word) > 3
              and not word.endswith(("ss", "is", "us"))):
            word = word[:-1]
        out.append(word)
    return out


def infer_domain(table_names, column_names=()):
    """Return (domain, score) for the best matching domain, or (None, 0)."""
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        kw = set(keywords)
        score = sum(TABLE_WEIGHT for t in table_names for w in _stems(t) if w in kw)
        score += sum(COLUMN_WEIGHT for c in column_names for w in _stems(c) if w in kw)
        scores[domain] = score
    best = max(scores, key=lambda d: scores[d])  # ties: first in dict order
    return (best, scores[best]) if scores[best] >= MIN_SCORE else (None, 0)


def suggest_dataset_name(file_names, columns=()):
    """A context name such as 'Logistics' from the table names (file names
    without extension) and, when known, the column names. Falls back to the
    generic 'first + N more' name when no domain is recognised."""
    tables = [str(n).rsplit(".", 1)[0] for n in file_names]
    domain, _ = infer_domain(tables, columns)
    return domain or default_dataset_name(file_names)

