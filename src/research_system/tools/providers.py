"""Search provider adapters: each converts one API's output into `SearchResult` (notebook 03).

Adapters raise on failure; the agent-facing tools (tools/research_tools.py) catch errors and
turn them into readable messages.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from research_system.schemas import SearchResult

SearchFn = Callable[[str], list[SearchResult]]


def _tavily_kwargs(api_key: str | None) -> dict[str, Any]:
    return {"tavily_api_key": api_key} if api_key else {}


def tavily_search(
    query: str, k: int = 5, api_key: str | None = None, **opts: Any
) -> list[SearchResult]:
    """Tavily web search: LLM-ready chunks with relevance scores."""
    from langchain_tavily import TavilySearch

    raw = TavilySearch(max_results=k, **_tavily_kwargs(api_key), **opts).invoke({"query": query})
    return [
        SearchResult(
            title=r["title"],
            url=r["url"],
            content=r["content"],
            source="tavily",
            score=r.get("score"),
        )
        for r in raw["results"]
    ]


def tavily_extract(url: str, max_chars: int = 4000, api_key: str | None = None) -> str:
    """Main text of a web page, truncated to bound the context budget."""
    from langchain_tavily import TavilyExtract

    raw = TavilyExtract(**_tavily_kwargs(api_key)).invoke({"urls": [url]})
    if not raw.get("results"):
        raise ValueError(f"extraction failed for {url}")
    text: str = raw["results"][0]["raw_content"]
    return text[:max_chars]


def ddg_search(query: str, k: int = 5) -> list[SearchResult]:
    """Keyless DuckDuckGo search. Intermittent (scraping-based): best-effort fallback only."""
    from ddgs import DDGS

    raw = DDGS(timeout=10).text(query, max_results=k)
    return [
        SearchResult(title=r["title"], url=r["href"], content=r["body"], source="duckduckgo")
        for r in raw
    ]


def arxiv_search(query: str, k: int = 4) -> list[SearchResult]:
    """arXiv papers, relevance-sorted (date sorting destroys relevance; see nb 03)."""
    import arxiv

    papers = arxiv.Client().results(arxiv.Search(query=query, max_results=k))
    return [
        SearchResult(
            title=p.title,
            url=p.entry_id,
            content=p.summary.replace("\n", " "),
            source="arxiv",
            published=p.published.date().isoformat(),
        )
        for p in papers
    ]


def wikipedia_search(query: str, k: int = 2, max_chars: int = 1500) -> list[SearchResult]:
    """Wikipedia summaries for background knowledge."""
    from langchain_community.utilities import WikipediaAPIWrapper

    docs = WikipediaAPIWrapper(top_k_results=k, doc_content_chars_max=max_chars).load(query)  # type: ignore[call-arg]
    return [
        SearchResult(
            title=d.metadata["title"],
            url=d.metadata["source"],
            content=d.page_content,
            source="wikipedia",
        )
        for d in docs
    ]


def search_with_fallback(
    query: str, providers: Sequence[tuple[str, SearchFn]]
) -> tuple[str, list[SearchResult]]:
    """Try providers in order; return (provider_name, results) from the first non-empty one."""
    errors: list[str] = []
    for name, fn in providers:
        try:
            results = fn(query)
        except Exception as e:  # provider failures are expected; try the next one
            errors.append(f"{name}: {type(e).__name__}")
            continue
        if results:
            return name, results
        errors.append(f"{name}: no results")
    raise RuntimeError("; ".join(errors) or "no providers configured")
