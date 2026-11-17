"""
Modules/Scripts/test_library.py

Offline tests for storage, accounts and each user's saved work.
The Google Cloud Storage back end is tested with an in-memory fake bucket.

    python Modules/Scripts/test_library.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from Modules import library as lib
from Modules.storage import GCSStorage, LocalStorage, get_storage
from Modules.users import AuthError, login, register, user_id

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def raises(fn, exc=Exception):
    try:
        fn()
        return False
    except exc:
        return True


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name

    def upload_from_string(self, data):
        self.bucket.objects[self.name] = bytes(data)

    def download_as_bytes(self):
        return self.bucket.objects[self.name]

    def exists(self):
        return self.name in self.bucket.objects

    def delete(self):
        self.bucket.objects.pop(self.name, None)


class FakeBucket:
    def __init__(self):
        self.objects = {}

    def blob(self, name):
        return FakeBlob(self, name)

    def list_blobs(self, prefix=""):
        return [FakeBlob(self, n) for n in sorted(self.objects) if n.startswith(prefix)]


class FakeClient:
    def __init__(self):
        self.b = FakeBucket()

    def bucket(self, name):
        return self.b


tmp = tempfile.mkdtemp()
BACKENDS = {"local": LocalStorage(tmp), "gcs (fake)": GCSStorage("bucket", client=FakeClient())}

data = {"drivers": pd.DataFrame({"driver_id": ["D1", "D2"], "name": ["Ann", "Bob"]}),
        "trips": pd.DataFrame({"trip_id": [1, 2, 3], "driver_id": ["D1", "D1", "D2"],
                               "dispatch_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"])})}

for label, store in BACKENDS.items():
    print(f"\n--- {label} ---")
    store.put("a/b/c.txt", b"hello")
    check("put then get", store.get("a/b/c.txt") == b"hello")
    check("exists", store.exists("a/b/c.txt") and not store.exists("a/b/none.txt"))
    check("list under a prefix", store.list("a") == ["a/b/c.txt"], str(store.list("a")))
    check("a missing file raises FileNotFoundError", raises(lambda: store.get("zzz.txt"), FileNotFoundError))
    check("'..' in a path is refused", raises(lambda: store.put("../x.txt", b"x"), ValueError))
    store.delete_prefix("a")
    check("delete_prefix removes everything below", store.list("a") == [] and not store.exists("a/b/c.txt"))

    # accounts
    uid = register(store, "Ann@Example.com", "correct horse")
    check("register returns the user id", uid == user_id("ann@example.com"))
    check("login works (e-mail case does not matter)", login(store, "ANN@example.com", "correct horse") == uid)
    check("wrong password refused", raises(lambda: login(store, "ann@example.com", "wrong password"), AuthError))
    check("unknown user refused with the same message",
          raises(lambda: login(store, "nobody@example.com", "whatever123"), AuthError))
    check("duplicate account refused", raises(lambda: register(store, "ann@example.com", "another pass1"), AuthError))
    check("short password refused", raises(lambda: register(store, "x@y.com", "short"), AuthError))
    check("invalid e-mail refused", raises(lambda: register(store, "not-an-email", "longenough1"), AuthError))
    check("the password is not stored in clear",
          b"correct horse" not in store.get(f"accounts/{uid}.json"))
    bob = register(store, "bob@example.com", "bobs password")

    # datasets
    did = lib.save_dataset(store, uid, "Logistics", data, {"tables": {}}, "SCHEMA TEXT")
    got, profile, schema, meta = lib.load_dataset(store, uid, did)
    check("a saved dataset reloads identical", all(got[t].equals(data[t]) for t in data))
    check("date columns keep their type", pd.api.types.is_datetime64_any_dtype(got["trips"]["dispatch_date"]))
    check("schema and profile reload", schema == "SCHEMA TEXT" and profile == {"tables": {}})
    check("the dataset list shows it", [d["name"] for d in lib.list_datasets(store, uid)] == ["Logistics"])
    check("metadata has row counts", meta["tables"]["trips"]["rows"] == 3)

    # isolation
    check("another user sees no datasets", lib.list_datasets(store, bob) == [])
    check("another user cannot load it", raises(lambda: lib.load_dataset(store, bob, did), FileNotFoundError))
    check("a path-like id is refused", raises(lambda: lib.load_dataset(store, uid, "../" + did), ValueError))
    check("a path-like user id is refused", raises(lambda: lib.list_datasets(store, "../" + uid), ValueError))

    # dashboards
    spec = {"panels": [{"title": "Trips", "question": "how many trips", "sql": "SELECT 1", "kind": "kpi"}],
            "filters": {}}
    dash = lib.save_dashboard(store, uid, did, "Fleet overview", spec)
    check("a dashboard reloads with its spec", lib.load_dashboard(store, uid, dash)["spec"] == spec)
    first_created = lib.load_dashboard(store, uid, dash)["created"]
    spec2 = {"panels": spec["panels"] + [{"title": "Cost", "question": "q", "sql": "SELECT 2", "kind": "bar"}], "filters": {}}
    lib.save_dashboard(store, uid, did, "Fleet overview v2", spec2, dashboard_id=dash)
    d = lib.load_dashboard(store, uid, dash)
    check("saving with an id overwrites (an edit)", len(d["spec"]["panels"]) == 2 and d["title"] == "Fleet overview v2")
    check("the creation time is kept on edit", d["created"] == first_created)
    check("the dashboard list shows one entry", len(lib.list_dashboards(store, uid)) == 1)
    check("another user sees no dashboards", lib.list_dashboards(store, bob) == [])
    check("another user cannot load it", raises(lambda: lib.load_dashboard(store, bob, dash), FileNotFoundError))

    # history
    lib.add_history(store, uid, "question", "total fuel cost", dataset_id=did, dashboard_id=dash)
    lib.add_history(store, uid, "edit", "remove the cost panel", dashboard_id=dash, ok=False)
    h = lib.list_history(store, uid)
    check("history is newest first", [x["kind"] for x in h] == ["edit", "question"], str(h))
    check("history is private", lib.list_history(store, bob) == [])
    for i in range(lib.MAX_HISTORY + 20):
        lib.add_history(store, bob, "question", f"q{i}")
    check("history keeps only the latest entries", len(lib.list_history(store, bob, limit=10 ** 6)) == lib.MAX_HISTORY)

    # deletion
    lib.delete_dashboard(store, uid, dash)
    lib.delete_dataset(store, uid, did)
    check("deleted work is gone", lib.list_dashboards(store, uid) == [] and lib.list_datasets(store, uid) == [])

print("\n--- configuration ---")
os.environ["STORAGE_BACKEND"] = "local"
os.environ["APP_DATA_DIR"] = tmp + "/cfg"
check("get_storage returns the local back end by default", get_storage().name == "local")
os.environ["STORAGE_BACKEND"] = "gcs"
os.environ.pop("GCS_BUCKET", None)
check("gcs without a bucket name is a clear error", raises(get_storage, RuntimeError))

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
