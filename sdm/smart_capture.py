from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sdm.database import normalize_media_kind


MAX_CANDIDATES = 24
MAX_URL_LENGTH = 8192
TRUSTED_DIRECT_SOURCES = frozenset(
    {
        "dom",
        "metadata",
        "jsonld",
        "media-session",
        "performance",
        "webrequest",
    }
)
MANIFEST_SUFFIXES = (".m3u8", ".mpd")


@dataclass(frozen=True, slots=True)
class CaptureDecision:
    url: str
    media_kind: str
    referer: str
    mime_type: str
    filename: str
    total_bytes: int
    method: str


def resolve_smart_capture(payload: dict[str, Any]) -> CaptureDecision:
    """Choose a high-confidence browser media candidate safely.

    The extension gathers evidence from the DOM, metadata, Media Session and
    Resource Timing. Python repeats the security-sensitive validation and only
    promotes candidates explicitly marked as direct by a trusted collector.
    """

    page_url = _http_url(payload.get("page_url") or payload.get("referer"))
    original_url = _http_url(payload.get("url"))
    media_kind = normalize_media_kind(payload.get("media_kind", "direct"))
    best: tuple[int, str, str, str, int] | None = None

    candidates = payload.get("capture_candidates")
    if isinstance(candidates, list):
        for candidate in candidates[:MAX_CANDIDATES]:
            if not isinstance(candidate, dict):
                continue
            url = _http_url(candidate.get("url"))
            source = str(candidate.get("source", "")).strip().casefold()
            if (
                not url
                or source not in TRUSTED_DIRECT_SOURCES
                or not bool(candidate.get("direct"))
                or _is_manifest(url)
            ):
                continue
            try:
                score = max(0, min(1000, int(candidate.get("score", 0))))
            except (TypeError, ValueError):
                score = 0
            mime_type = str(candidate.get("mime_type", "")).strip()[:255]
            filename = str(candidate.get("filename", "")).strip()[:260]
            try:
                total_bytes = max(0, int(candidate.get("total_bytes", 0)))
            except (TypeError, ValueError):
                total_bytes = 0
            ranked = (score, url, mime_type, filename, total_bytes)
            if best is None or ranked[0] > best[0]:
                best = ranked

    if best is not None:
        return CaptureDecision(
            url=best[1],
            media_kind="direct",
            referer=page_url or original_url,
            mime_type=best[2],
            filename=best[3],
            total_bytes=best[4],
            method="smart-direct",
        )

    return CaptureDecision(
        url=original_url,
        media_kind=media_kind,
        referer=page_url if page_url != original_url else "",
        mime_type=str(payload.get("mime_type", "")).strip()[:255],
        filename="",
        total_bytes=0,
        method="platform-extractor" if media_kind != "direct" else "direct",
    )


def _http_url(value: object) -> str:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > MAX_URL_LENGTH:
        return ""
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return ""
    return candidate


def _is_manifest(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return path.endswith(MANIFEST_SUFFIXES)
