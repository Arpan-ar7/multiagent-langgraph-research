"""Aggregate evaluation results into a Markdown comparison table."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

SUMMARY_METRICS: tuple[tuple[str, str], ...] = (
    ("relevance", "Judge: relevance (1-5)"),
    ("completeness", "Judge: completeness (1-5)"),
    ("specificity", "Judge: specificity (1-5)"),
    ("grounding_rate", "Grounding rate"),
    ("citation_problems", "Citation problems"),
    ("sources_cited", "Sources cited"),
    ("distinct_domains", "Distinct domains"),
    ("critic_iterations", "Critic iterations"),
    ("failed_researchers", "Failed researchers"),
    ("words", "Report words"),
)


def summarize(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Mean of each metric per configuration."""
    by_config: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_config[row["config"]].append(row)
    return {
        config: {key: round(mean(r[key] for r in group), 2) for key, _ in SUMMARY_METRICS}
        | {"n": len(group)}
        for config, group in by_config.items()
    }


def markdown_table(rows: list[dict[str, Any]], title: str = "Evaluation results") -> str:
    """Configs as columns, metrics as rows."""
    summary = summarize(rows)
    if not summary:
        return f"## {title}\n\nNo results yet.\n"
    configs = sorted(summary)
    lines = [
        f"## {title}",
        "",
        "| Metric | " + " | ".join(configs) + " |",
        "|---|" + "---|" * len(configs),
        "| Runs | " + " | ".join(str(int(summary[c]["n"])) for c in configs) + " |",
    ]
    for key, label in SUMMARY_METRICS:
        lines.append(f"| {label} | " + " | ".join(f"{summary[c][key]:g}" for c in configs) + " |")
    return "\n".join(lines) + "\n"
