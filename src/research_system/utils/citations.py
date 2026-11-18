"""Citation handling owned by code, not by the LLM (notebook 06).

The writer only emits `[n]` markers; code assigns the numbers, validates the markers and
builds the References section, so references are correct by construction.
"""

from __future__ import annotations

import re

from research_system.schemas import FactCheckReport

MARKER = re.compile(r"\[(\d+)\]")


def number_sources(fact_check: FactCheckReport) -> dict[str, int]:
    """Assign `[n]` numbers to unique URLs of usable claims, in order of first appearance."""
    numbers: dict[str, int] = {}
    for claim in fact_check.usable_claims():
        for url in claim.source_urls:
            numbers.setdefault(url, len(numbers) + 1)
    return numbers


def validate_citations(markdown: str, numbers: dict[str, int]) -> list[str]:
    """Return problems: markers that point nowhere, and sources never cited."""
    cited = {int(n) for n in MARKER.findall(markdown)}
    valid = set(numbers.values())
    problems = [f"invalid citation [{n}]" for n in sorted(cited - valid)]
    problems += [f"source [{n}] never cited" for n in sorted(valid - cited)]
    return problems


def references_section(numbers: dict[str, int]) -> str:
    """Markdown References list in citation-number order."""
    lines = [f"{n}. {url}" for url, n in sorted(numbers.items(), key=lambda kv: kv[1])]
    return "## References\n" + "\n".join(lines) + "\n"


def assemble_report(
    draft: str, numbers: dict[str, int], limitations: list[str] | None = None
) -> tuple[str, list[str]]:
    """Final Markdown: draft + References (+ Limitations). Returns (report, citation problems)."""
    problems = validate_citations(draft, numbers)
    report = f"{draft.rstrip()}\n\n{references_section(numbers)}"
    notes = list(dict.fromkeys([*(limitations or []), *problems]))  # de-duplicated, ordered
    if notes:
        report += "\n## Limitations of this report\n" + "\n".join(f"- {n}" for n in notes) + "\n"
    return report, problems
