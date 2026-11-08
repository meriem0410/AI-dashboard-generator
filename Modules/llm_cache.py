"""
Modules/llm_cache.py

Record-and-replay cache for language-model calls.

Why: a hosted model is slow, rate-limited and not perfectly repeatable. With
the cache you can run the same questions again in seconds, record a demo that
looks identical every time, and compare two code versions on EXACTLY the same
model answers.

Switch it with the environment variable LLM_CACHE:
    off     (default) every call goes to the model, nothing is stored
    on      replay when the same request was seen before, otherwise call the
            model and record the answer
    replay  replay only; a request that was never recorded raises CacheMiss
            (useful to prove that a run needs no network)

The key is a hash of everything that shapes the answer: model, messages,
temperature, reasoning effort, token limit, response format, tools. Change a
word in the prompt and it is a new key.

Only the full text of the answer and the token counts are stored, plus a
short preview of the request. The folder can be deleted at any time.
It wraps the OpenAI-style client used by Modules/sql_generator.py,
Agent_sql.py and the planner; it does not cache LangChain model calls.
"""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

_IGNORED = {"stream", "timeout", "extra_headers", "extra_query", "extra_body"}


class CacheMiss(RuntimeError):
    """replay mode: this request was never recorded."""


def _clean_kwargs(kwargs):
    return {k: v for k, v in kwargs.items() if k not in _IGNORED}


def make_key(kwargs):
    blob = json.dumps(_clean_kwargs(kwargs), sort_keys=True,
                      default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _usage_dict(response):
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    out = {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, name, None)
        if isinstance(value, int):
            out[name] = value
    return out or None


def _build_response(content, usage):
    message = SimpleNamespace(role="assistant", content=content)
    choice = SimpleNamespace(index=0, message=message, finish_reason="stop")
    return SimpleNamespace(
        choices=[choice],
        usage=SimpleNamespace(**usage) if usage else None,
        cached=True,
    )


class CachedClient:
    def __init__(self, client, mode, directory):
        self._client = client
        self.mode = mode
        self.directory = Path(directory)
        self.hits = 0
        self.misses = 0
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create))

    def __getattr__(self, name):          # anything else goes to the real client
        return getattr(self._client, name)

    def _path(self, key):
        return self.directory / f"{key}.json"

    def _create(self, **kwargs):
        key = make_key(kwargs)
        path = self._path(key)

        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.hits += 1
            return _build_response(data["content"], data.get("usage"))

        if self.mode == "replay":
            raise CacheMiss(
                f"No recorded answer for this request (key {key[:12]}...). "
                "Run once with LLM_CACHE=on to record it.")

        response = self._client.chat.completions.create(**kwargs)
        self.misses += 1
        content = response.choices[0].message.content
        self.directory.mkdir(parents=True, exist_ok=True)
        messages = kwargs.get("messages") or [{}]
        record = {
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": kwargs.get("model"),
            "temperature": kwargs.get("temperature"),
            "request_preview": str(messages[-1].get("content", ""))[:300],
            "content": content,
            "usage": _usage_dict(response),
        }
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
        os.replace(tmp, path)             # atomic: never a half-written file
        return response


def wrap_client(client, mode=None, directory="llm_cache"):
    """Return `client` itself when the cache is off, otherwise a CachedClient."""
    mode = (mode if mode is not None else os.getenv("LLM_CACHE", "off")).strip().lower()
    if mode not in ("on", "replay"):
        return client
    return CachedClient(client, mode, directory)
