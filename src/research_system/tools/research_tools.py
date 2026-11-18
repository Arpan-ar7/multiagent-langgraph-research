"""Agent-facing LangChain tools (notebook 03).

Design rules:
1. Return compact, numbered text with URLs, so the model can cite and code can verify.
2. Never raise: return `ERROR: ... try X instead` so the agent can re-route.
3. Bound output size (context budget).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from langchain_core.tools import BaseTool, tool

from research_system.config.settings import Settings
from research_system.schemas import SearchResult
from research_system.tools import providers
from research_system.tools.providers import SearchFn

URL_LINE = re.compile(r"^URL: (\S+)", re.MULTILINE)


def format_results(results: Sequence[SearchResult], max_chars: int = 600) -> str:
    """Render results as a numbered list the LLM can cite from."""
    if not results:
        return "No results found."
    blocks = []
    for i, r in enumerate(results, 1):
        header = f"[{i}] {r.title}\nURL: {r.url}"
        if r.published:
            header += f"\nPublished: {r.published}"
        blocks.append(f"{header}\n{r.content[:max_chars]}")
    return "\n\n".join(blocks)


def extract_urls(tool_output: str) -> list[str]:
    """URLs listed in a formatted tool output (used to ground citations)."""
    return URL_LINE.findall(tool_output)


def web_providers(settings: Settings) -> list[tuple[str, SearchFn]]:
    """Ordered web search providers: Tavily, then best-effort DuckDuckGo."""
    key = settings.tavily_api_key.get_secret_value() if settings.tavily_api_key else None
    k = settings.search_max_results
    return [
        ("tavily", lambda q: providers.tavily_search(q, k=k, api_key=key)),
        ("duckduckgo", lambda q: providers.ddg_search(q, k=k)),
    ]


def build_research_tools(
    settings: Settings, web: Sequence[tuple[str, SearchFn]] | None = None
) -> list[BaseTool]:
    """Create the researcher's toolset. `web` can be overridden (e.g. stub providers in tests)."""
    web_chain = list(web) if web is not None else web_providers(settings)
    snippet = settings.snippet_max_chars
    tavily_key = settings.tavily_api_key.get_secret_value() if settings.tavily_api_key else None

    @tool
    def web_search(query: str) -> str:
        """Search the web for current information: news, documentation, blogs, company
        announcements. Use specific queries including entities and timeframes."""
        try:
            _, results = providers.search_with_fallback(query, web_chain)
            return format_results(results, snippet)
        except Exception as e:
            return f"ERROR: web search unavailable ({e}). Try search_papers or search_wikipedia."

    @tool
    def search_papers(query: str) -> str:
        """Search arXiv for academic research papers. Use for scientific methods, benchmarks
        and empirical results. Include key technical terms and, for recent work, a year."""
        try:
            return format_results(providers.arxiv_search(query), max_chars=800)
        except Exception as e:
            return f"ERROR: arXiv unavailable ({type(e).__name__}). Try web_search instead."

    @tool
    def search_wikipedia(query: str) -> str:
        """Look up background knowledge and definitions on Wikipedia. Not for recent events."""
        try:
            return format_results(providers.wikipedia_search(query), max_chars=1000)
        except Exception as e:
            return f"ERROR: Wikipedia unavailable ({type(e).__name__})."

    @tool
    def fetch_page(url: str) -> str:
        """Read the main text of a web page found via search, when the snippet is not
        detailed enough."""
        try:
            text = providers.tavily_extract(url, settings.page_max_chars, api_key=tavily_key)
            return f"URL: {url}\n{text}"
        except Exception as e:
            return f"ERROR: could not fetch page ({type(e).__name__})."

    return [web_search, search_papers, search_wikipedia, fetch_page]
