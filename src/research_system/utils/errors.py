"""Retry classification for graph nodes (notebook 07).

LangGraph's default `retry_on` skips RuntimeError/ValueError/OSError and retries unknown
exception types. We make the policy explicit instead: retry transient failures, never
retry exhausted daily quotas (retrying cannot help and only wastes time).
"""

from __future__ import annotations


def describe(exc: BaseException, limit: int = 200) -> str:
    """Short, log-safe description: exception type + first line of its message.

    Never log `repr(exc)` for provider errors: it can include response headers,
    cookies and account identifiers.
    """
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {message[:limit]}" if message else type(exc).__name__


QUOTA_MARKERS = ("per-day", "per day", "daily", "quota", "insufficient credits")


def status_code(exc: BaseException) -> int | None:
    """Best-effort HTTP status code from provider SDK / httpx exceptions."""
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def is_quota_exhausted(exc: BaseException) -> bool:
    """True for daily/plan quota errors, which no retry can fix."""
    text = str(exc).lower()
    return any(marker in text for marker in QUOTA_MARKERS)


def is_retryable(exc: BaseException) -> bool:
    """Retry network errors, timeouts, HTTP 5xx and per-minute rate limits (429)."""
    if is_quota_exhausted(exc):
        return False
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    name = type(exc).__name__.lower()
    if any(word in name for word in ("timeout", "connect", "network")):
        return True
    code = status_code(exc)
    if code is not None:
        return code == 429 or 500 <= code < 600
    return "too many requests" in name or "rate limit" in str(exc).lower()
