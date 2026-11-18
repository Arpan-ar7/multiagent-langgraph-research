"""Citations, source credibility and retry classification."""

from __future__ import annotations

import pytest

from research_system.schemas import FactCheckReport, VerifiedClaim
from research_system.utils.citations import assemble_report, number_sources, validate_citations
from research_system.utils.errors import is_quota_exhausted, is_retryable
from research_system.utils.sources import credibility, domain


def _claim(url: str, status: str = "supported") -> VerifiedClaim:
    return VerifiedClaim(statement=f"s {url}", source_urls=[url], status=status, credibility=0.5)  # type: ignore[arg-type]


class TestCitations:
    def test_numbers_unique_urls_in_order_and_skips_unverified(self) -> None:
        fc = FactCheckReport(
            claims=[
                _claim("https://a"),
                _claim("https://b", "unverified"),
                _claim("https://c"),
                _claim("https://a"),
            ]
        )
        assert number_sources(fc) == {"https://a": 1, "https://c": 2}

    def test_validate_reports_invalid_and_unused_markers(self) -> None:
        problems = validate_citations("Text [1] and [3].", {"https://a": 1, "https://b": 2})
        assert problems == ["invalid citation [3]", "source [2] never cited"]

    def test_assemble_report_appends_references_and_deduplicated_limitations(self) -> None:
        report, problems = assemble_report("# T\n\nFact [1].", {"https://a": 1}, ["gap", "gap"])
        assert problems == []
        assert "## References\n1. https://a" in report
        assert report.count("- gap") == 1


class TestSources:
    @pytest.mark.parametrize(
        ("url", "score"),
        [
            ("https://arxiv.org/abs/1", 0.9),
            ("https://data.gov/x", 0.9),
            ("https://en.wikipedia.org/wiki/X", 0.7),
            ("https://someblog.example.com/post", 0.5),
        ],
    )
    def test_credibility(self, url: str, score: float) -> None:
        assert credibility(url) == score

    def test_domain_strips_www(self) -> None:
        assert domain("https://www.Example.com/a") == "example.com"


class _HTTPError(Exception):
    def __init__(self, status_code: int, msg: str = "") -> None:
        super().__init__(msg)
        self.status_code = status_code


class TestRetryClassification:
    @pytest.mark.parametrize(
        "exc",
        [ConnectionError("x"), TimeoutError("x"), _HTTPError(429, "slow down"), _HTTPError(503)],
    )
    def test_transient_errors_are_retried(self, exc: Exception) -> None:
        assert is_retryable(exc)

    @pytest.mark.parametrize(
        "exc",
        [
            _HTTPError(429, "Rate limit exceeded: free-models-per-day"),
            _HTTPError(400, "bad request"),
            ValueError("schema mismatch"),
        ],
    )
    def test_permanent_errors_are_not_retried(self, exc: Exception) -> None:
        assert not is_retryable(exc)

    def test_daily_quota_detection(self) -> None:
        assert is_quota_exhausted(RuntimeError("Rate limit exceeded: free-models-per-day"))


def test_describe_is_short_and_log_safe() -> None:
    from research_system.utils.errors import describe

    err = RuntimeError("Rate limit exceeded: free-models-per-day\nheaders={'set-cookie': 'secret'}")
    assert describe(err) == "RuntimeError: Rate limit exceeded: free-models-per-day"
    assert describe(ValueError()) == "ValueError"
