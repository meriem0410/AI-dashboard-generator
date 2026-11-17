"""
Tests for the evaluation harness additions:
  - real/cached token accounting in Modules.llm_cache.CachedClient
  - the "evaluate everything" orchestrator Evaluation.run_all_eval (pure parts)

    python -m Modules.Scripts.test_eval_harness
"""
import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("GROQ_API_KEY", "test-dummy-key")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from types import SimpleNamespace

from Modules.llm_cache import CachedClient
from Evaluation import run_all_eval as R

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "::", detail)


# ---------- token accounting ----------

class _Upstream:
    def __init__(self):
        self.n = 0

    class _C:
        def __init__(self, o):
            self.o = o

        def create(self, **kw):
            self.o.n += 1
            msg = SimpleNamespace(content=f"ans{self.o.n}", tool_calls=None)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg)],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=40, total_tokens=140))

    @property
    def chat(self):
        return SimpleNamespace(completions=self._C(self))


d = tempfile.mkdtemp()
c = CachedClient(_Upstream(), "on", d)
msgs = [{"role": "user", "content": "hello"}]
c.chat.completions.create(model="m", messages=msgs)                 # real call -> miss
check("real call bills tokens", c.misses == 1 and c.real_tokens == 140, (c.misses, c.real_tokens))
check("no cached tokens yet", c.cached_tokens == 0, c.cached_tokens)
c.chat.completions.create(model="m", messages=msgs)                 # identical -> cache hit
check("cache hit does not bill quota", c.real_tokens == 140, c.real_tokens)
check("cache hit counts saved tokens", c.hits == 1 and c.cached_tokens == 140, (c.hits, c.cached_tokens))
c.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}])
check("second distinct prompt bills again", c.misses == 2 and c.real_tokens == 280, (c.misses, c.real_tokens))


# ---------- orchestrator plan ----------

def ns(**kw):
    base = dict(tag="t", dataset="Logistics", conditions="graph3", runs=1, budget=0,
                pace=0.0, max_wait=60, quick=False, ids="", skip_main=False)
    base.update(kw)
    return SimpleNamespace(**base)


keys = [s[0] for s in R.build_steps(ns())]
check("default plan has all five stages",
      keys == ["unit", "guard", "retrieval", "main", "report"], keys)
check("skip-main leaves only the offline pillars",
      [s[0] for s in R.build_steps(ns(skip_main=True))] == ["unit", "guard", "retrieval"], "")

main = [s for s in R.build_steps(ns(budget=150000, pace=2.0, quick=True, ids="H05")) if s[0] == "main"][0]
argv, env = main[2], main[3]
check("budget forwarded", "--budget" in argv and "150000" in argv, argv)
check("pace forwarded", "--pace" in argv and "2.0" in argv, argv)
check("quick forwarded", "--quick" in argv, argv)
check("ids forwarded", "--ids" in argv and "H05" in argv, argv)
check("resume always set", "--resume" in argv, argv)
check("accuracy step replays cache for free", env.get("LLM_CACHE") == "on", env)

ablate = [s for s in R.build_steps(ns(conditions="graph1,graph3,graph3_rag")) if s[0] == "main"][0]
check("ablation conditions pass through", "graph1,graph3,graph3_rag" in ablate[2], ablate[2])

report_step = [s for s in R.build_steps(ns()) if s[0] == "report"][0]
check("report step is optional (a clean budget stop must not fail the run)",
      report_step[4] is True, report_step)


# ---------- evidence document ----------

R.RESULTS_DIR = Path(tempfile.mkdtemp())
fake = [{"key": "guard", "title": "Safety — SQL guard + locked engine",
         "argv": ["python", "-m", "Evaluation.guard_eval"], "env": {},
         "ok": True, "code": 0, "seconds": 1.0,
         "output": "attack block rate 100%\nbenign pass rate 100%", "optional": False}]
p = R.write_evidence("t", fake, ns())
txt = p.read_text(encoding="utf-8")
check("evidence doc names the run", "pipeline evaluation evidence" in txt, "")
check("evidence doc embeds step output", "attack block rate 100%" in txt, "")
check("evidence doc has the stage summary table", "| Stage | Step | Result |" in txt, "")

print("\n==== %s ====" % ("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
sys.exit(1 if failures else 0)
