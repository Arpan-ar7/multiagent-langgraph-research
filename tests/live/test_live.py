"""Smoke tests against real APIs. Skipped by default; run with:  uv run pytest -m live

They spend real quota (Tavily credits, LLM requests), so keep them few and small.
"""

from __future__ import annotations

import pytest

from research_system.config.settings import get_settings
from research_system.tools import build_research_tools, extract_urls

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def tools() -> dict[str, object]:
    settings = get_settings()
    if not settings.tavily_api_key:
        pytest.skip("TAVILY_API_KEY not set")
    return {t.name: t for t in build_research_tools(settings)}


def test_web_search_returns_citable_results(tools: dict) -> None:  # type: ignore[type-arg]
    out = tools["web_search"].invoke({"query": "LangGraph Send API map-reduce"})
    assert not out.startswith("ERROR"), out
    assert len(extract_urls(out)) >= 3


def test_paper_and_wikipedia_search(tools: dict) -> None:  # type: ignore[type-arg]
    assert extract_urls(tools["search_papers"].invoke({"query": "retrieval augmented generation"}))
    assert "wikipedia.org" in tools["search_wikipedia"].invoke({"query": "Large language model"})


def test_full_research_run() -> None:
    """End-to-end with real LLMs (~15-25 requests): one sub-question, no revision loop."""
    from research_system.graph import RunOptions
    from research_system.service import ResearchService, RunStatus

    service = ResearchService()
    snap = service.run(
        "What is the LangGraph Send API used for?",
        RunOptions(max_sub_questions=1, max_iterations=1, max_tool_calls=2),
    )
    assert snap.status is RunStatus.DONE, snap
    assert snap.report and "## References" in snap.report
