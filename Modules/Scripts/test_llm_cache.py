"""
Modules/Scripts/test_llm_cache.py

Offline tests for the record-and-replay cache (Modules/llm_cache.py).
No internet, no Groq call.

Run from the project root:
    python Modules/Scripts/test_llm_cache.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Modules.llm_cache import CacheMiss, CachedClient, make_key, wrap_client

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


class FakeRaw:
    """A stand-in for the real client: counts calls, answers 'answer N'."""

    def __init__(self):
        self.calls = 0
        outer = self

        def create(**kwargs):
            outer.calls += 1
            message = SimpleNamespace(content=f"answer {outer.calls}")
            usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=120)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        self.base_url = "https://example.invalid"


def request(text="hello", **extra):
    return dict(model="m", messages=[{"role": "user", "content": text}], temperature=0, **extra)


print("\n--- keys ---")
check("the same request gives the same key", make_key(request()) == make_key(request()))
check("another prompt gives another key", make_key(request("a")) != make_key(request("b")))
check("another temperature gives another key", make_key(request()) != make_key({**request(), "temperature": 0.5}))
check("timeout does not change the key", make_key(request()) == make_key({**request(), "timeout": 5}))

print("\n--- modes ---")
raw = FakeRaw()
check("off: the very same client comes back", wrap_client(raw, mode="off") is raw)
check("an unknown mode means off", wrap_client(raw, mode="banana") is raw)

with tempfile.TemporaryDirectory() as tmp:
    raw = FakeRaw()
    client = wrap_client(raw, mode="on", directory=tmp)
    check("on: a CachedClient is returned", isinstance(client, CachedClient))

    first = client.chat.completions.create(**request())
    check("on: the first call goes to the model", raw.calls == 1 and first.choices[0].message.content == "answer 1")
    check("on: the answer is recorded in a file", len(list(Path(tmp).glob("*.json"))) == 1)

    second = client.chat.completions.create(**request())
    check("on: the same request is replayed, no new model call",
          raw.calls == 1 and second.choices[0].message.content == "answer 1")
    check("on: a replayed answer is flagged", getattr(second, "cached", False) is True)
    check("on: token counts survive the replay",
          second.usage.prompt_tokens == 100 and second.usage.total_tokens == 120)
    check("on: hits and misses are counted", (client.hits, client.misses) == (1, 1), f"{client.hits},{client.misses}")

    third = client.chat.completions.create(**request("another prompt"))
    check("on: a different request goes to the model", raw.calls == 2 and third.choices[0].message.content == "answer 2")

    record = json.loads(next(Path(tmp).glob("*.json")).read_text(encoding="utf-8"))
    check("the file keeps a short preview, not the whole prompt",
          "request_preview" in record and "messages" not in record)
    check("other attributes pass through to the real client", client.base_url == "https://example.invalid")

    replay_raw = FakeRaw()
    replay = wrap_client(replay_raw, mode="replay", directory=tmp)
    got = replay.chat.completions.create(**request())
    check("replay: a recorded request is answered with no model call",
          replay_raw.calls == 0 and got.choices[0].message.content == "answer 1")
    try:
        replay.chat.completions.create(**request("never seen"))
        check("replay: an unseen request raises CacheMiss", False)
    except CacheMiss:
        check("replay: an unseen request raises CacheMiss", True)
    check("replay: the model was never called", replay_raw.calls == 0)

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
