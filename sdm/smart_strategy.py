from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class DownloadStrategy:
    name: str
    connections: int
    transfer_mode: str
    resume_supported: bool
    health_score: int
    health_label: str
    reason: str
    retry_profile: str


def _health_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Limited"


def choose_download_strategy(
    *,
    url: str,
    total_bytes: int,
    mime_type: str,
    connection_limit: int,
    accept_ranges: bool,
    latency_ms: float | None = None,
    requires_auth: bool = False,
) -> DownloadStrategy:
    """Choose a conservative transfer strategy from link metadata.

    The decision is deterministic and intentionally avoids aggressive connection
    counts when the server does not advertise byte ranges or the object is small.
    """
    limit = max(1, min(16, int(connection_limit or 1)))
    size = max(0, int(total_bytes or 0))
    mime = (mime_type or "").casefold()
    host = (urlsplit(url).hostname or "").casefold()

    if not accept_ranges or limit == 1:
        connections = 1
        name = "Reliable single stream"
        mode = "Single connection"
        reason = "The server did not confirm byte-range support, so SDM selected the safest resumable path."
    elif size and size < 8 * 1024 * 1024:
        connections = min(2, limit)
        name = "Low-overhead transfer"
        mode = "Light segmented"
        reason = "The file is small; fewer connections avoid unnecessary setup overhead."
    elif size >= 1024 * 1024 * 1024:
        connections = min(12, limit)
        name = "Large-file acceleration"
        mode = "Adaptive segmented"
        reason = "The server supports ranges and the file is large, so SDM can scale parallel segments safely."
    elif size >= 128 * 1024 * 1024:
        connections = min(8, limit)
        name = "Balanced acceleration"
        mode = "Adaptive segmented"
        reason = "The file size and range support make a balanced multi-connection transfer appropriate."
    else:
        connections = min(4, limit)
        name = "Balanced transfer"
        mode = "Adaptive segmented" if connections > 1 else "Single connection"
        reason = "SDM selected a moderate connection count for stable speed and low server pressure."

    if any(token in mime for token in ("mpegurl", "dash+xml")):
        name = "Media stream pipeline"
        mode = "Stream-aware"
        connections = min(connections, 4)
        reason = "A streaming manifest was detected; SDM limited concurrency for ordered media processing."

    score = 55
    score += 20 if accept_ranges else -15
    score += 8 if size > 0 else -3
    score += 6 if mime else 0
    score += 4 if host else 0
    score -= 8 if requires_auth else 0
    if latency_ms is not None:
        if latency_ms <= 150:
            score += 7
        elif latency_ms >= 800:
            score -= 8
    score = max(10, min(100, score))

    retry_profile = "Standard exponential backoff"
    if requires_auth:
        retry_profile = "Session-aware retry"
    elif not accept_ranges:
        retry_profile = "Conservative reconnect"

    return DownloadStrategy(
        name=name,
        connections=connections,
        transfer_mode=mode,
        resume_supported=bool(accept_ranges),
        health_score=score,
        health_label=_health_label(score),
        reason=reason,
        retry_profile=retry_profile,
    )
