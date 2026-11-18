"""Rule-based source credibility (notebook 06): transparent and explainable, not perfect."""

from __future__ import annotations

from urllib.parse import urlparse

HIGH_CREDIBILITY = ("arxiv.org", ".gov", ".edu", "nature.com", "acm.org", "ieee.org", "science.org")
MEDIUM_CREDIBILITY = ("wikipedia.org", "github.com", "reuters.com", "apnews.com", "bbc.co")


def credibility(url: str) -> float:
    """Credibility score in [0, 1] by domain type."""
    host = urlparse(url).netloc.lower()
    if any(h in host for h in HIGH_CREDIBILITY):
        return 0.9
    if any(m in host for m in MEDIUM_CREDIBILITY):
        return 0.7
    return 0.5


def domain(url: str) -> str:
    """Host name without a leading `www.`."""
    return urlparse(url).netloc.lower().removeprefix("www.")
