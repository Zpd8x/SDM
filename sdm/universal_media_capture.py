from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac", ".weba"}
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".webm", ".mov", ".mkv", ".avi", ".ts", ".m2ts"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}
SUBTITLE_EXTENSIONS = {".vtt", ".srt", ".ass", ".ssa", ".ttml"}
MANIFEST_EXTENSIONS = {".m3u8", ".mpd"}
TRACKING_QUERY_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}

SITE_PROFILES = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "fb.watch": "Facebook",
    "x.com": "X / Twitter",
    "twitter.com": "X / Twitter",
    "vimeo.com": "Vimeo",
    "dailymotion.com": "Dailymotion",
    "soundcloud.com": "SoundCloud",
    "twitch.tv": "Twitch",
    "drive.google.com": "Google Drive",
    "dropbox.com": "Dropbox",
    "onedrive.live.com": "OneDrive",
}

@dataclass(frozen=True, slots=True)
class MediaCandidate:
    url: str
    kind: str = "other"
    source: str = "network"
    score: int = 0
    direct: bool = False
    mime_type: str = ""
    filename: str = ""
    total_bytes: int = 0
    quality: str = ""
    codec: str = ""
    duration_seconds: float = 0.0
    requires_ffmpeg: bool = False
    site_profile: str = "Generic"
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.casefold() not in TRACKING_QUERY_KEYS]
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path, urlencode(query, doseq=True), ""))


def site_profile_for_url(url: str) -> str:
    host = urlsplit(url).hostname or ""
    host = host.casefold()
    for domain, label in SITE_PROFILES.items():
        if host == domain or host.endswith("." + domain):
            return label
    return "Generic"


def classify_media(url: str, mime_type: str = "") -> tuple[str, bool, bool]:
    path = PurePosixPath(urlsplit(url).path.casefold())
    suffix = path.suffix
    mime = mime_type.casefold().split(";", 1)[0].strip()
    if suffix in MANIFEST_EXTENSIONS or mime in {"application/vnd.apple.mpegurl", "application/x-mpegurl", "application/dash+xml"}:
        return "stream", False, True
    if suffix in AUDIO_EXTENSIONS or mime.startswith("audio/"):
        return "audio", True, False
    if suffix in VIDEO_EXTENSIONS or mime.startswith("video/"):
        return "video", True, False
    if suffix in SUBTITLE_EXTENSIONS or mime.startswith("text/vtt"):
        return "subtitle", True, False
    if suffix in IMAGE_EXTENSIONS or mime.startswith("image/"):
        return "image", True, False
    return "other", False, False


def normalize_candidate(raw: Mapping[str, Any]) -> MediaCandidate | None:
    url = canonicalize_url(str(raw.get("url", "")))
    if not url:
        return None
    detected_kind, detected_direct, requires_ffmpeg = classify_media(url, str(raw.get("mime_type", "")))
    kind = str(raw.get("kind") or detected_kind).casefold()
    if kind not in {"audio", "video", "image", "subtitle", "stream", "other"}:
        kind = detected_kind
    direct = bool(raw.get("direct", detected_direct)) and not requires_ffmpeg
    signature = "\n".join((url, kind, str(raw.get("quality", "")), str(raw.get("codec", ""))))
    return MediaCandidate(
        url=url,
        kind=kind,
        source=str(raw.get("source", "network"))[:40],
        score=max(0, min(1000, int(raw.get("score", 0) or 0))),
        direct=direct,
        mime_type=str(raw.get("mime_type", ""))[:255],
        filename=str(raw.get("filename", ""))[:260],
        total_bytes=max(0, int(raw.get("total_bytes", 0) or 0)),
        quality=str(raw.get("quality", ""))[:80],
        codec=str(raw.get("codec", ""))[:80],
        duration_seconds=max(0.0, float(raw.get("duration_seconds", 0) or 0)),
        requires_ffmpeg=requires_ffmpeg or bool(raw.get("requires_ffmpeg", False)),
        site_profile=site_profile_for_url(url),
        fingerprint=sha256(signature.encode("utf-8")).hexdigest()[:20],
    )


def deduplicate_candidates(items: Iterable[Mapping[str, Any]], limit: int = 96) -> list[MediaCandidate]:
    best: dict[tuple[str, str, str, str], MediaCandidate] = {}
    for raw in items:
        candidate = normalize_candidate(raw)
        if candidate is None:
            continue
        key = (candidate.url, candidate.kind, candidate.quality.casefold(), candidate.codec.casefold())
        previous = best.get(key)
        if previous is None or (candidate.score, candidate.total_bytes) > (previous.score, previous.total_bytes):
            best[key] = candidate
    return sorted(best.values(), key=lambda item: (item.score, item.total_bytes), reverse=True)[:max(1, limit)]


def summarize_candidates(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = deduplicate_candidates(items)
    counts = {kind: 0 for kind in ("video", "audio", "stream", "image", "subtitle", "other")}
    for item in candidates:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return {
        "total": len(candidates),
        "counts": counts,
        "requires_ffmpeg": sum(1 for item in candidates if item.requires_ffmpeg),
        "profiles": sorted({item.site_profile for item in candidates}),
        "items": [item.to_dict() for item in candidates],
    }
