"""
Modules/users.py

Email + password accounts, stored through Modules/storage.py.

Passwords are never stored: only a random salt and an scrypt hash (standard
library, no extra package). The user id is derived from the e-mail address, so
it is stable, safe to use in a path, and the same account cannot be created
twice.
"""
import hashlib
import hmac
import json
import os
import re
import time

MIN_PASSWORD = 8
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    pass


def normalise_email(email):
    return str(email or "").strip().lower()


def user_id(email):
    return hashlib.sha256(normalise_email(email).encode("utf-8")).hexdigest()[:20]


def _hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1,
                          dklen=32).hex()


def _record_path(uid):
    return f"accounts/{uid}.json"


def register(store, email, password):
    email = normalise_email(email)
    if not _EMAIL.match(email):
        raise AuthError("Please enter a valid e-mail address.")
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"The password needs at least {MIN_PASSWORD} characters.")
    uid = user_id(email)
    if store.exists(_record_path(uid)):
        raise AuthError("An account with this e-mail already exists.")
    salt = os.urandom(16)
    store.put(_record_path(uid), json.dumps({
        "email": email, "salt": salt.hex(), "hash": _hash(password, salt),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S")}).encode("utf-8"))
    return uid


def login(store, email, password):
    uid = user_id(email)
    try:
        record = json.loads(store.get(_record_path(uid)))
    except FileNotFoundError:
        _hash(password or "", b"\0" * 16)          # same cost: no user-guessing by timing
        raise AuthError("Wrong e-mail or password.")
    candidate = _hash(password or "", bytes.fromhex(record["salt"]))
    if not hmac.compare_digest(candidate, record["hash"]):
        raise AuthError("Wrong e-mail or password.")
    return uid
