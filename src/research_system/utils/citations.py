"""Citation handling owned by code, not by the LLM (notebook 06).

The writer only emits `[n]` markers; code assigns the numbers, validates the markers and
builds the References section, so references are correct by construction.
"""

from __future__ import annotations

import re
from typing import Any

from research_system.schemas import FactCheckReport
from research_system.utils.sources import credibility, domain

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


def linkify_citations(markdown: str, numbers: dict[str, int]) -> str:
    """Turn `[n]` markers into Markdown links to their source (unknown numbers are left as-is)."""
    urls = {n: url for url, n in numbers.items()}

    def link(match: re.Match[str]) -> str:
        url = urls.get(int(match.group(1)))
        return f"[\\[{match.group(1)}\\]]({url})" if url else match.group(0)

    return MARKER.sub(link, markdown)


def source_table(
    numbers: dict[str, int], fact_check: FactCheckReport | None
) -> list[dict[str, Any]]:
    """One row per cited source: number, url, domain, credibility and how its claims fared."""
    rows: list[dict[str, Any]] = []
    for url, n in sorted(numbers.items(), key=lambda kv: kv[1]):
        statuses = [
            c.status for c in (fact_check.claims if fact_check else []) if url in c.source_urls
        ]
        rows.append(
            {
                "n": n,
                "url": url,
                "domain": domain(url),
                "credibility": credibility(url),
                "claims": len(statuses),
                "contested": statuses.count("contested"),
            }
        )
    return rows


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
