"""
Modules/library.py

Each user's saved work: datasets, dashboards and request history.
Everything lives under users/<user id>/ in the storage back end, so one user
can never reach another user's files (every function takes the user id and
builds the path itself; ids are checked).

    datasets/<id>/meta.json, schema.txt, profile.json, tables/<name>.parquet
    dashboards/<id>.json      the dashboard SPEC: questions, SQL, chart kinds,
                              filters (enough to rebuild it with no model call)
    history.json              the latest requests

Saving a processed dataset (tables + profile + schema) means a returning user
skips ingestion and profiling.
"""
import io
import json
import re
import time
import uuid

import pandas as pd

MAX_HISTORY = 300
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _check_id(value, what="id"):
    if not _ID.match(str(value or "")):
        raise ValueError(f"Invalid {what}.")
    return value


def _base(uid):
    return f"users/{_check_id(uid, 'user id')}"


def _new_id():
    return uuid.uuid4().hex[:12]


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")


# ---- datasets ------------------------------------------------------------
def save_dataset(store, uid, name, data, profile, schema):
    """data = {table: DataFrame}. Returns the dataset id."""
    did = _new_id()
    base = f"{_base(uid)}/datasets/{did}"
    for table, df in data.items():
        _check_id(table, "table name")
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        store.put(f"{base}/tables/{table}.parquet", buf.getvalue())
    store.put(f"{base}/profile.json", _dump(profile))
    store.put(f"{base}/schema.txt", str(schema).encode("utf-8"))
    store.put(f"{base}/meta.json", _dump({
        "id": did, "name": str(name)[:120], "created": _now(),
        "tables": {t: {"rows": int(len(df)), "columns": int(df.shape[1])}
                   for t, df in data.items()}}))
    return did


def list_datasets(store, uid):
    out = []
    for path in store.list(f"{_base(uid)}/datasets"):
        if path.endswith("/meta.json"):
            out.append(json.loads(store.get(path)))
    return sorted(out, key=lambda m: m["created"], reverse=True)


def load_dataset(store, uid, did):
    """Returns (data, profile, schema, meta)."""
    base = f"{_base(uid)}/datasets/{_check_id(did, 'dataset id')}"
    meta = json.loads(store.get(f"{base}/meta.json"))
    data = {t: pd.read_parquet(io.BytesIO(store.get(f"{base}/tables/{t}.parquet")))
            for t in meta["tables"]}
    profile = json.loads(store.get(f"{base}/profile.json"))
    schema = store.get(f"{base}/schema.txt").decode("utf-8")
    return data, profile, schema, meta


def delete_dataset(store, uid, did):
    store.delete_prefix(f"{_base(uid)}/datasets/{_check_id(did, 'dataset id')}")


# ---- dashboards ----------------------------------------------------------
def save_dashboard(store, uid, dataset_id, title, spec, dashboard_id=None):
    """spec = any JSON-able dict (panels with question, sql, kind, filters).
    Passing dashboard_id overwrites that dashboard (an edit)."""
    _check_id(dataset_id, "dataset id")
    dash_id = _check_id(dashboard_id) if dashboard_id else _new_id()
    path = f"{_base(uid)}/dashboards/{dash_id}.json"
    created = _now()
    if dashboard_id and store.exists(path):
        created = json.loads(store.get(path)).get("created", created)
    store.put(path, _dump({"id": dash_id, "dataset_id": dataset_id,
                           "title": str(title)[:160], "created": created,
                           "updated": _now(), "spec": spec}))
    return dash_id


def list_dashboards(store, uid):
    out = []
    for path in store.list(f"{_base(uid)}/dashboards"):
        d = json.loads(store.get(path))
        out.append({k: d[k] for k in ("id", "dataset_id", "title", "created", "updated")})
    return sorted(out, key=lambda m: m["updated"], reverse=True)


def load_dashboard(store, uid, dash_id):
    return json.loads(store.get(f"{_base(uid)}/dashboards/{_check_id(dash_id)}.json"))


def delete_dashboard(store, uid, dash_id):
    store.delete_prefix(f"{_base(uid)}/dashboards/{_check_id(dash_id)}.json")


# ---- history -------------------------------------------------------------
def add_history(store, uid, kind, text, dataset_id=None, dashboard_id=None, ok=True):
    path = f"{_base(uid)}/history.json"
    items = json.loads(store.get(path)) if store.exists(path) else []
    items.append({"time": _now(), "kind": kind, "text": str(text)[:500],
                  "dataset_id": dataset_id, "dashboard_id": dashboard_id, "ok": bool(ok)})
    store.put(path, _dump(items[-MAX_HISTORY:]))


def list_history(store, uid, limit=50):
    path = f"{_base(uid)}/history.json"
    items = json.loads(store.get(path)) if store.exists(path) else []
    return list(reversed(items))[:limit]
