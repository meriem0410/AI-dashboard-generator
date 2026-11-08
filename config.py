import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from Modules.llm_cache import wrap_client

load_dotenv()

# =========================
# Groq configuration
# =========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not configured. Add it to your .env file."
    )

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    timeout=60,       # seconds, so a stuck call cannot freeze the app
    max_retries=2,    # the client retries rate-limit and network errors
)

# Record-and-replay cache for model calls. LLM_CACHE=off (default), on, replay.
# See Modules/llm_cache.py.
client = wrap_client(
    client,
    directory=os.getenv("LLM_CACHE_DIR", str(Path(__file__).resolve().parent / "llm_cache")),
)

# =========================
# Storage
# =========================
# Where datasets and dashboards will be saved (used by the persistence step).
# Locally this is a folder; on a cloud host it will be a mounted volume.
DATA_DIR = Path(os.getenv("DATA_DIR", "workspace_data"))
