"""
Modules/storage.py

One tiny storage interface with two back ends, so the app never knows where
its files live.

    LocalStorage  a folder on disk (development, tests, a host with a disk)
    GCSStorage    a Google Cloud Storage bucket (Cloud Run: its disk is wiped
                  at every restart, so anything saved must go to the bucket)

Environment:
    STORAGE_BACKEND=local (default) | gcs
    APP_DATA_DIR=./app_data        (local)
    GCS_BUCKET=<bucket name>       (gcs; credentials come from the Cloud Run
                                    service account or `gcloud auth`)

Paths are always relative, use "/" and never contain "..".
"""
import os
import shutil
from pathlib import Path


def _clean(path):
    path = str(path).replace("\\", "/").strip("/")
    parts = path.split("/")
    if not path or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"Invalid storage path: {path!r}")
    return path


class LocalStorage:
    name = "local"

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _full(self, path):
        full = (self.root / _clean(path)).resolve()
        if self.root not in full.parents:
            raise ValueError("Path escapes the storage root.")
        return full

    def put(self, path, data):
        full = self._full(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        tmp = full.with_suffix(full.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, full)                      # never leave half a file

    def get(self, path):
        full = self._full(path)
        if not full.is_file():
            raise FileNotFoundError(path)
        return full.read_bytes()

    def exists(self, path):
        return self._full(path).is_file()

    def list(self, prefix):
        base = self._full(prefix)
        if not base.is_dir():
            return []
        return sorted(str(p.relative_to(self.root)).replace("\\", "/")
                      for p in base.rglob("*") if p.is_file())

    def delete_prefix(self, prefix):
        base = self._full(prefix)
        if base.is_dir():
            shutil.rmtree(base)
        elif base.is_file():
            base.unlink()


class GCSStorage:
    name = "gcs"

    def __init__(self, bucket, client=None):
        if client is None:
            from google.cloud import storage          # optional dependency
            client = storage.Client()
        self.bucket = client.bucket(bucket)

    def put(self, path, data):
        self.bucket.blob(_clean(path)).upload_from_string(data)

    def get(self, path):
        blob = self.bucket.blob(_clean(path))
        if not blob.exists():
            raise FileNotFoundError(path)
        return blob.download_as_bytes()

    def exists(self, path):
        return self.bucket.blob(_clean(path)).exists()

    def list(self, prefix):
        prefix = _clean(prefix) + "/"
        return sorted(b.name for b in self.bucket.list_blobs(prefix=prefix))

    def delete_prefix(self, prefix):
        prefix = _clean(prefix)
        for b in list(self.bucket.list_blobs(prefix=prefix + "/")):
            b.delete()
        blob = self.bucket.blob(prefix)
        if blob.exists():
            blob.delete()


def get_storage():
    backend = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
    if backend == "gcs":
        bucket = os.environ.get("GCS_BUCKET")
        if not bucket:
            raise RuntimeError("STORAGE_BACKEND=gcs needs GCS_BUCKET.")
        return GCSStorage(bucket)
    return LocalStorage(os.environ.get("APP_DATA_DIR", "app_data"))
