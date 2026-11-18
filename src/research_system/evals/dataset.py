"""Benchmark questions and their LangSmith dataset (notebook 08).

The set is deliberately diverse in research type: a system tuned on one kind of question
can fail on others.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DATASET_NAME = "research-system-benchmark"


@dataclass(frozen=True)
class EvalQuestion:
    kind: str
    question: str


EVAL_QUESTIONS: tuple[EvalQuestion, ...] = (
    EvalQuestion(
        "technical",
        "What are the main techniques for reducing hallucinations in LLMs as of 2026?",
    ),
    EvalQuestion(
        "comparative", "Compare LangGraph, CrewAI and AutoGen for building multi-agent LLM systems."
    ),
    EvalQuestion(
        "trend",
        "What is the current state of solid-state battery commercialization for electric vehicles?",
    ),
    EvalQuestion(
        "factual",
        "How does retrieval-augmented generation work and what are its most common failure modes?",
    ),
    EvalQuestion(
        "exploratory",
        "What effects has generative AI had on software developer employment and hiring?",
    ),
)


def sync_langsmith_dataset(
    client: Any, questions: tuple[EvalQuestion, ...] = EVAL_QUESTIONS
) -> str:
    """Create the LangSmith dataset if needed and add any missing questions. Returns its id."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Research questions of varied type for the multi-agent research system.",
        )
    existing = {ex.inputs.get("question") for ex in client.list_examples(dataset_id=dataset.id)}
    missing = [q for q in questions if q.question not in existing]
    if missing:
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {"inputs": {"question": q.question}, "metadata": {"kind": q.kind}} for q in missing
            ],
        )
    return str(dataset.id)
