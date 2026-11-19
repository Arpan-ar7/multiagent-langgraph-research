# ADR 0004: Code-built citations and URL grounding

**Status:** Accepted

## Context
LLMs invent or garble URLs. A research report is only trustworthy if every citation points to a source that was actually retrieved.

## Decision
- Tools return numbered results with explicit `URL:` lines. Each researcher's `retrieved_urls` are taken from the tool outputs, not from the model.
- The fact-checker drops claims whose cited URLs were never retrieved (deterministic) and asks the LLM only for credibility and contradiction judgements.
- The writer emits `[n]` markers only. Code numbers the sources, validates the markers and builds the References section.

## Consequences
- References are correct by construction, and the grounding rate is a deterministic evaluation metric.
- Claims from sources the model "remembers" but did not retrieve are dropped, even if true. That trade-off is intended.
