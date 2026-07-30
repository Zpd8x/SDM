from __future__ import annotations

import urllib.error
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping


RATE_LIMIT_STATUS_CODES = frozenset({429, 503})


def is_rate_limited(error: BaseException) -> bool:
    return (
        isinstance(error, urllib.error.HTTPError)
        and error.code in RATE_LIMIT_STATUS_CODES
    )


def retry_delay_seconds(
    error: BaseException,
    attempt: int,
    *,
    now: datetime | None = None,
) -> float:
    """Return a bounded retry delay, honoring Retry-After when available."""
    if not is_rate_limited(error):
        return float(min(2**attempt, 8))

    retry_after = _retry_after_seconds(
        getattr(error, "headers", None),
        now=now,
    )
    if retry_after is not None:
        return min(max(retry_after, 1.0), 120.0)
    return float(min(5 * (2**attempt), 60))


def _retry_after_seconds(
    headers: Mapping[str, str] | None,
    *,
    now: datetime | None = None,
) -> float | None:
    if not headers:
        return None
    value = headers.get("Retry-After", "").strip()
    if not value:
        return None

    try:
        return float(value)
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (retry_at - current).total_seconds()
