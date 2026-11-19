# 09 · Citations and fact-checking: making the report trustworthy

Files: `agents/fact_checker.py`, `utils/citations.py`, `utils/sources.py`. Status: ✅ (decision record: `docs/decisions/0004-code-built-citations.md`)

LLMs invent URLs. Our answer is a **chain of custody** for every citation:

```
tool output (URL: lines) ──► Finding.retrieved_urls      (filled by code)
researcher claim cites URL ──► grounded only if URL ∈ retrieved_urls   (code)
grounded claims ──► numbered [1], [2]…                  (code)
writer sees only [n] markers, never URLs                 (prompt rule)
References section built from the number map             (code)
every [n] in the text validated                          (code)
```

## Steps in code

1. `extract_urls(tool_output)` collects the URLs the researcher actually saw.
2. `ground_claims(findings)` marks a claim grounded only if **all** its cited URLs were retrieved.
3. `number_sources(fact_check)` gives each unique URL of a usable claim a number, in order of first appearance.
4. The writer writes `... as shown in recent studies [2][3].`
5. `assemble_report()`:
   - `validate_citations()` lists problems: `[7]` that points nowhere, or a source never cited
   - appends `## References` (`1. https://...`)
   - appends `## Limitations of this report` (failed researchers, skipped steps, citation problems)
6. The UI's `linkify_citations()` turns `[n]` into clickable links, and `source_table()` shows each source with its domain, credibility and how many of its claims were contested.

## Why this matters

- References are **correct by construction**: the LLM cannot write a wrong URL because it never writes URLs.
- The **grounding rate** (grounded claims ÷ all claims) is a deterministic quality metric used in evaluation. The first real benchmark run scored **1.00**.
- Trade-off (intentional): a true fact the model "remembers" but did not retrieve is dropped.

## Credibility scoring

Simple, transparent rules (`utils/sources.py`): `arxiv.org, .gov, .edu, nature.com, acm.org, ieee.org, science.org` → 0.9; `wikipedia.org, github.com, reuters.com, apnews.com, bbc.co` → 0.7; everything else → 0.5. Not perfect, but explainable.
