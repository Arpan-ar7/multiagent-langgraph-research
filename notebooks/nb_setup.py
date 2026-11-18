"""Shared setup for the experiment notebooks.

Every notebook starts with:

    from nb_setup import setup
    ROOT = setup()

What it does:
1. Finds the project root (works whether Jupyter was started in the root or in notebooks/).
2. Loads API keys from the root .env file into environment variables.
3. Prints which keys are present (never their values).
4. Turns on a SQLite LLM cache: identical prompts to the same model are answered
   from disk instead of the API. This matters on the OpenRouter free tier
   (~50 requests/day), because re-running a notebook then costs zero requests.
"""

from __future__ import annotations

import os
import time
import warnings
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

KEYS = ("GROQ_API_KEY", "OPENROUTER_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY")


def project_root() -> Path:
    """Return the repository root (the folder that holds pyproject.toml)."""
    here = Path.cwd()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise FileNotFoundError("Could not locate project root (pyproject.toml).")


def setup(cache: bool = True, tracing: bool | None = None) -> Path:
    """Load .env, report key status, and optionally enable the LLM cache.

    Args:
        cache: Store LLM responses in data/llm_cache.sqlite so re-runs are free.
        tracing: Force LangSmith tracing on/off. None keeps the .env setting.
    """
    root = project_root()
    load_dotenv(root / ".env", override=True)

    if tracing is not None:
        os.environ["LANGSMITH_TRACING"] = "true" if tracing else "false"

    print("API keys:")
    for key in KEYS:
        status = "set" if os.getenv(key) else "MISSING"
        print(f"  {key:<20} {status}")
    print(f"  LangSmith tracing    {os.getenv('LANGSMITH_TRACING', 'false')}")

    if cache:
        from langchain_community.cache import SQLiteCache
        from langchain_core.globals import set_llm_cache

        db = root / "data" / "llm_cache.sqlite"
        db.parent.mkdir(exist_ok=True)
        set_llm_cache(SQLiteCache(database_path=str(db)))
        # Harmless notice from SQLiteCache about a future default. Registered *after* the
        # LangChain import, because importing LangChain resets warning filters.
        warnings.filterwarnings("ignore", message=".*allowed_objects.*")
        print(f"LLM cache: {db.relative_to(root)}")
    return root


def disable_cache() -> None:
    """Turn the LLM cache off (needed when measuring real latency)."""
    from langchain_core.globals import set_llm_cache

    set_llm_cache(None)


@contextmanager
def timer(label: str = "elapsed"):
    """Context manager that prints how long the wrapped block took."""
    start = time.perf_counter()
    result: dict[str, float] = {}
    try:
        yield result
    finally:
        result["seconds"] = time.perf_counter() - start
        print(f"[{label}] {result['seconds']:.2f}s")
