# 06 · Tools and search

Files: `src/research_system/tools/providers.py` (adapters) and `tools/research_tools.py` (agent tools). Status: ✅

## Two layers

1. **Providers** (`providers.py`) talk to one API each and convert the result into one common shape, `SearchResult` (title, url, content, source, published, score). Providers are allowed to raise errors.
2. **Tools** (`research_tools.py`) are what the LLM sees. They call providers, format the results and **never raise**.

## The researcher's four tools

| Tool | Backed by | When the model should use it |
|---|---|---|
| `web_search(query)` | Tavily → DuckDuckGo fallback | news, docs, blogs, current info |
| `search_papers(query)` | arXiv | scientific methods, benchmarks |
| `search_wikipedia(query)` | Wikipedia | background definitions (not recent events) |
| `fetch_page(url)` | Tavily Extract | read a promising page in full (cut to 4,000 chars) |

The docstring of each `@tool` function is what the model reads to decide which tool to use, so the docstrings are written as usage instructions.

## Design rules (from notebook 03)

1. **Numbered results with explicit URL lines**, so the model can cite and code can check:
   ```
   [1] Some title
   URL: https://example.com/page
   Published: 2026-03-01
   First 600 characters of content...
   ```
   `extract_urls()` reads these `URL:` lines to fill `Finding.retrieved_urls`.
2. **Never raise.** A failing tool returns `ERROR: web search unavailable (...). Try search_papers or search_wikipedia.` The agent can then switch tools instead of the whole run crashing.
3. **Bounded output:** snippets ≤600 chars, papers ≤800, Wikipedia ≤1,000, pages ≤4,000. This protects the context window and token budget.

## Search fallback

`search_with_fallback(query, providers)` tries Tavily first and DuckDuckGo second. It returns the first non-empty result, and only raises if all providers fail.

## What we measured (notebook 03)

- Tavily: ~2–5 s, ~1,200 chars per result, relevance-scored. Clearly the best.
- DuckDuckGo: intermittent, with snippets 3–5× shorter. Fallback only.
- arXiv: sorting by date destroys relevance, so we use relevance sort with years in the query.
