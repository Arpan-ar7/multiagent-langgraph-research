"""Components finalised in notebooks 01-03, shared by the later notebooks.

This module is a *staging area*: it collects the decisions made so far so notebooks 04+
don't copy-paste them. In Phase 2 its contents move into src/research_system/
(config/llm.py, schemas/, tools/).
"""

from __future__ import annotations

import os
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------- models (nb 01)

ROLE_MODELS: dict[str, list[tuple[str, str]]] = {
    # role -> ordered (provider, model) chain: primary first, then fallbacks
    "reasoning": [
        ("openrouter", "nvidia/nemotron-3.5-super-vl:free"),
        ("openrouter", "baidu/ernie-5.5-flash-preview:free"),
        ("openrouter", "inclusionai/ling-3.2-flash:free"),
    ],
    "worker": [
        ("openrouter", "baidu/ernie-5.5-flash-preview:free"),
        ("openrouter", "nvidia/nemotron-3.5-super-vl:free"),
        ("openrouter", "inclusionai/ling-3.2-flash:free"),
    ],
}
if os.getenv("GROQ_API_KEY"):  # Groq goes first for every role once a key exists
    ROLE_MODELS["reasoning"].insert(0, ("groq", "llama-3.3-70b-versatile"))
    ROLE_MODELS["worker"].insert(0, ("groq", "llama-3.1-8b-instant"))


def make_model(
    provider: str, model: str, temperature: float = 0.0, max_retries: int = 1, timeout: float = 90
) -> BaseChatModel:
    """Provider-agnostic chat model factory. `timeout` is in seconds."""
    if provider == "openrouter":
        from langchain_openrouter import ChatOpenRouter

        return ChatOpenRouter(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            timeout=int(timeout * 1000),
        )  # SDK uses ms
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=model, temperature=temperature, max_retries=max_retries, timeout=timeout
        )
    raise ValueError(f"Unknown provider: {provider}")


def role_models(role: str, temperature: float = 0.0) -> list[BaseChatModel]:
    """All models for a role, primary first."""
    return [make_model(p, m, temperature) for p, m in ROLE_MODELS[role]]


def llm_for(role: str, temperature: float = 0.0) -> Runnable:
    """Plain chat runnable for a role, with fallbacks."""
    primary, *backups = role_models(role, temperature)
    return primary.with_fallbacks(backups)


def structured(schema: type[BaseModel], role: str, temperature: float = 0.0) -> Runnable:
    """Structured-output runnable: schema applied per model, then chained as fallbacks (nb 02)."""
    primary, *backups = [m.with_structured_output(schema) for m in role_models(role, temperature)]
    return primary.with_fallbacks(backups)


# --------------------------------------------------------------------------- schemas (nb 02)


class SubQuestion(BaseModel):
    """One focused, independently searchable research question."""

    question: str = Field(
        description="A specific question answerable via search, phrased as a search-friendly question"
    )
    rationale: str = Field(
        description="Why this question is needed to answer the main objective (one sentence)"
    )
    search_strategy: Literal["web", "academic", "encyclopedic"] = Field(
        description="web = news/blogs/docs, academic = research papers, encyclopedic = definitions/background"
    )


class ResearchPlan(BaseModel):
    """A plan that decomposes a research query into focused sub-questions and a report outline."""

    objective: str = Field(description="The research objective restated in one precise sentence")
    research_type: Literal["factual", "comparative", "technical", "trend_analysis", "exploratory"]
    sub_questions: list[SubQuestion] = Field(
        min_length=3,
        max_length=5,
        description="3-5 non-overlapping sub-questions covering the objective",
    )
    report_outline: list[str] = Field(
        min_length=3, max_length=7, description="Section headings for the final report"
    )

    @field_validator("sub_questions")
    @classmethod
    def no_duplicates(cls, v: list[SubQuestion]) -> list[SubQuestion]:
        texts = [s.question.strip().lower() for s in v]
        if len(set(texts)) != len(texts):
            raise ValueError("sub_questions must be unique")
        return v


class SearchResult(BaseModel):
    """Provider-independent search hit; the unit of evidence that flows through the system."""

    title: str
    url: str
    content: str
    source: Literal["tavily", "duckduckgo", "arxiv", "wikipedia"]
    score: float | None = None
    published: str | None = None


# --------------------------------------------------------------------------- search adapters (nb 03)


def tavily_search(query: str, k: int = 5, **kwargs) -> list[SearchResult]:
    from langchain_tavily import TavilySearch

    raw = TavilySearch(max_results=k, **kwargs).invoke({"query": query})
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


def ddg_search(query: str, k: int = 5) -> list[SearchResult]:
    from ddgs import DDGS

    raw = DDGS(timeout=10).text(query, max_results=k)
    return [
        SearchResult(title=r["title"], url=r["href"], content=r["body"], source="duckduckgo")
        for r in raw
    ]


def arxiv_search(query: str, k: int = 4) -> list[SearchResult]:
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


def wikipedia_search(query: str) -> list[SearchResult]:
    from langchain_community.utilities import WikipediaAPIWrapper

    docs = WikipediaAPIWrapper(top_k_results=2, doc_content_chars_max=1500).load(query)
    return [
        SearchResult(
            title=d.metadata["title"],
            url=d.metadata["source"],
            content=d.page_content,
            source="wikipedia",
        )
        for d in docs
    ]


def format_results(results: list[SearchResult], max_chars: int = 600) -> str:
    """Render results as a compact numbered list the LLM can cite from."""
    if not results:
        return "No results found."
    return "\n\n".join(
        f"[{i}] {r.title}\nURL: {r.url}"
        + (f"\nPublished: {r.published}" if r.published else "")
        + f"\n{r.content[:max_chars]}"
        for i, r in enumerate(results, 1)
    )


WEB_PROVIDERS = [
    ("tavily", lambda q: tavily_search(q, k=5)),
    ("duckduckgo", lambda q: ddg_search(q, k=5)),
]


def search_with_fallback(query: str, providers=None) -> tuple[str, list[SearchResult]]:
    """Try providers in order; return (provider_name, results) from the first that succeeds."""
    errors = []
    for name, fn in providers or WEB_PROVIDERS:
        try:
            results = fn(query)
            if results:
                return name, results
            errors.append(f"{name}: no results")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
    raise RuntimeError("; ".join(errors))


# --------------------------------------------------------------------------- tools (nb 03)


@tool
def web_search(query: str) -> str:
    """Search the web for current information: news, documentation, blogs, company announcements.
    Use specific queries including entities and timeframes."""
    try:
        _, results = search_with_fallback(query)
        return format_results(results)
    except Exception as e:
        return (
            f"ERROR: web search unavailable ({e}). Try search_papers or search_wikipedia instead."
        )


@tool
def search_papers(query: str) -> str:
    """Search arXiv for academic research papers. Use for scientific methods, benchmarks and empirical results.
    Include key technical terms and, for recent work, a year."""
    try:
        return format_results(arxiv_search(query), max_chars=800)
    except Exception as e:
        return f"ERROR: arXiv unavailable ({type(e).__name__}). Try web_search instead."


@tool
def search_wikipedia(query: str) -> str:
    """Look up background knowledge and definitions on Wikipedia. Not for recent events."""
    try:
        return format_results(wikipedia_search(query), max_chars=1000)
    except Exception as e:
        return f"ERROR: Wikipedia unavailable ({type(e).__name__})."


@tool
def fetch_page(url: str) -> str:
    """Read the main text of a web page found via search, when the snippet is not detailed enough."""
    try:
        from langchain_tavily import TavilyExtract

        raw = TavilyExtract().invoke({"urls": [url]})
        if not raw.get("results"):
            return f"ERROR: could not extract {url}."
        return raw["results"][0]["raw_content"][:4000]
    except Exception as e:
        return f"ERROR: could not fetch page ({type(e).__name__})."


RESEARCH_TOOLS = [web_search, search_papers, search_wikipedia, fetch_page]
