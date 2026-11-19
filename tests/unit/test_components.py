"""Schemas, settings, tools and the fact-checker's deterministic logic."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from research_system.agents.fact_checker import build_report, ground_claims
from research_system.config.settings import ModelSpec, Settings
from research_system.schemas import (
    Claim,
    Conflict,
    ConflictReport,
    Critique,
    Finding,
    SearchResult,
    SubQuestion,
)
from research_system.tools import (
    build_research_tools,
    extract_urls,
    format_results,
    search_with_fallback,
)
from tests.conftest import make_plan


class TestSchemas:
    def test_plan_rejects_duplicate_sub_questions(self) -> None:
        with pytest.raises(ValidationError, match="unique"):
            make_plan(("same", "Same", "other"))

    def test_plan_allows_one_to_five_sub_questions(self) -> None:
        assert len(make_plan(("only one",)).sub_questions) == 1
        with pytest.raises(ValidationError):
            make_plan(())
        with pytest.raises(ValidationError):
            make_plan(tuple(f"q{i}" for i in range(6)))

    def test_with_sub_questions_validates(self) -> None:
        plan = make_plan()
        trimmed = plan.with_sub_questions(plan.sub_questions[:2])
        assert [q.question for q in trimmed.sub_questions] == ["costs", "adoption"]
        with pytest.raises(ValidationError):
            plan.with_sub_questions([])

    def test_checkpoint_roundtrip_keeps_nested_models(self) -> None:
        """Regression: invalid models were restored via model_construct with nested dicts."""
        from research_system.graph.checkpointing import safe_serializer

        serde = safe_serializer()
        plan = make_plan().with_sub_questions(make_plan().sub_questions[:2])
        restored = serde.loads_typed(serde.dumps_typed(plan))
        assert isinstance(restored.sub_questions[0], SubQuestion)

    def test_critique_approval_is_threshold_based(self) -> None:
        c = Critique(coverage=4, evidence_use=5, coherence=4, justification="")
        assert c.approved(4) and not c.approved(5)

    def test_sub_question_strategy_is_restricted(self) -> None:
        with pytest.raises(ValidationError):
            SubQuestion(question="q", rationale="r", search_strategy="google")  # type: ignore[arg-type]


class TestSettings:
    def test_model_list_parses_from_comma_string(self) -> None:
        s = Settings(_env_file=None, reasoning_models="openrouter:a/b:free, groq:c")  # type: ignore[call-arg]
        assert s.reasoning_models == [
            ModelSpec(provider="openrouter", model="a/b:free"),
            ModelSpec(provider="groq", model="c"),
        ]

    def test_groq_joins_the_chain_only_when_key_present(self) -> None:
        without = Settings(_env_file=None, groq_api_key=None)  # type: ignore[call-arg]
        with_key = Settings(_env_file=None, groq_api_key=SecretStr("k"))  # type: ignore[call-arg]
        assert all(m.provider == "openrouter" for m in without.models_for("worker"))
        # Default: Groq is the rescue model at the end (its free tier is 8k tokens/minute).
        assert with_key.models_for("worker")[0].provider == "openrouter"
        assert with_key.models_for("worker")[-1] == ModelSpec(
            provider="groq", model=with_key.groq_worker_model
        )


def _result(url: str) -> SearchResult:
    return SearchResult(title="T", url=url, content="body", source="tavily")


class TestTools:
    def test_format_and_extract_urls_roundtrip(self) -> None:
        text = format_results([_result("https://a.com/1"), _result("https://b.com/2")])
        assert text.startswith("[1] T\nURL: https://a.com/1")
        assert extract_urls(text) == ["https://a.com/1", "https://b.com/2"]

    def test_fallback_skips_failing_and_empty_providers(self) -> None:
        def boom(q: str) -> list[SearchResult]:
            raise ConnectionError

        name, results = search_with_fallback(
            "q", [("down", boom), ("empty", lambda q: []), ("ok", lambda q: [_result("https://x")])]
        )
        assert name == "ok" and len(results) == 1

    def test_web_search_tool_never_raises(self, settings: Settings) -> None:
        def boom(q: str) -> list[SearchResult]:
            raise ConnectionError

        tools = {t.name: t for t in build_research_tools(settings, web=[("down", boom)])}
        out = tools["web_search"].invoke({"query": "anything"})
        assert out.startswith("ERROR: web search unavailable")
        assert set(tools) == {"web_search", "search_papers", "search_wikipedia", "fetch_page"}


class TestFactCheckerLogic:
    """Synthetic fixtures with planted problems, as in notebook 06."""

    def _findings(self) -> list[Finding]:
        return [
            Finding(
                sub_question="adoption",
                summary="s",
                confidence="high",
                retrieved_urls=["https://survey.example.org"],
                claims=[
                    Claim(
                        statement="58% use agents daily.",
                        source_urls=["https://survey.example.org"],
                    )
                ],
            ),
            Finding(
                sub_question="studies",
                summary="s",
                confidence="medium",
                retrieved_urls=["https://arxiv.org/abs/1"],
                claims=[
                    Claim(
                        statement="Under 30% use agents daily.",
                        source_urls=["https://arxiv.org/abs/1"],
                    ),
                    Claim(
                        statement="Invented stat.", source_urls=["https://never-retrieved.example"]
                    ),
                ],
            ),
        ]

    def test_ungrounded_citation_is_unverified(self) -> None:
        checked = ground_claims(self._findings())
        assert [c.grounded for c in checked] == [True, True, False]
        assert checked[1].credibility == 0.9

    def test_conflict_marks_both_claims_contested(self) -> None:
        checked = ground_claims(self._findings())
        conflicts = ConflictReport(
            conflicts=[Conflict(claim_ids=[0, 1], explanation="58% vs <30%")]
        )
        report = build_report(checked, conflicts)
        assert [c.status for c in report.claims] == ["contested", "contested", "unverified"]
        assert report.conflicts == ["58% vs <30%"]
        assert len(report.usable_claims()) == 2

    def test_out_of_range_conflict_ids_are_ignored(self) -> None:
        checked = ground_claims(self._findings())
        report = build_report(
            checked, ConflictReport(conflicts=[Conflict(claim_ids=[0, 9], explanation="x")])
        )
        assert report.claims[1].status == "supported"
