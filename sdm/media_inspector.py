from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class MediaInspectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaFormat:
    format_id: str
    extension: str
    resolution: str
    fps: float
    video_codec: str
    audio_codec: str
    bitrate_kbps: float
    size_bytes: int
    protocol: str
    language: str = ""
    hdr: bool = False

    @property
    def has_video(self) -> bool:
        return bool(self.video_codec and self.video_codec != "none")

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_codec and self.audio_codec != "none")

    @property
    def kind(self) -> str:
        if self.has_video and self.has_audio:
            return "Video + Audio"
        if self.has_video:
            return "Video only"
        if self.has_audio:
            return "Audio only"
        return "Unknown"


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    language: str
    name: str
    extensions: tuple[str, ...]
    automatic: bool = False


@dataclass(slots=True)
class MediaInspection:
    url: str
    title: str
    extractor: str
    duration_seconds: int
    thumbnail: str
    is_live: bool
    is_playlist: bool
    drm: bool
    formats: list[MediaFormat] = field(default_factory=list)
    subtitles: list[SubtitleTrack] = field(default_factory=list)
    entries: int = 0

    @property
    def downloadable(self) -> bool:
        return not self.drm and bool(self.formats)


def inspect_media(url: str, *, allow_playlist: bool = True) -> MediaInspection:
    try:
        import yt_dlp
    except ImportError as error:
        raise MediaInspectionError(
            "yt-dlp is not installed. Run START_SDM.bat while online."
        ) from error

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": not allow_playlist,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
    except Exception as error:
        message = " ".join(str(error).replace("\n", " ").split())
        raise MediaInspectionError(message or error.__class__.__name__) from error
    if not isinstance(info, dict):
        raise MediaInspectionError("The extractor returned no media information.")
    return inspection_from_info(url, info)


def inspection_from_info(url: str, info: dict[str, Any]) -> MediaInspection:
    entries_data = info.get("entries")
    is_playlist = bool(entries_data is not None or info.get("_type") == "playlist")
    entries = 0
    if entries_data is not None:
        try:
            entries = len([item for item in entries_data if item])
        except TypeError:
            entries = 0

    formats: list[MediaFormat] = []
    for item in info.get("formats") or ():
        if not isinstance(item, dict) or not item.get("format_id"):
            continue
        video_codec = str(item.get("vcodec") or "none")
        audio_codec = str(item.get("acodec") or "none")
        if video_codec == "none" and audio_codec == "none":
            continue
        width = _int(item.get("width"))
        height = _int(item.get("height"))
        resolution = str(item.get("resolution") or "")
        if not resolution or resolution == "audio only":
            resolution = f"{width}x{height}" if width and height else "Audio"
        dynamic_range = str(item.get("dynamic_range") or "").upper()
        formats.append(MediaFormat(
            format_id=str(item["format_id"]),
            extension=str(item.get("ext") or ""),
            resolution=resolution,
            fps=_float(item.get("fps")),
            video_codec=video_codec,
            audio_codec=audio_codec,
            bitrate_kbps=_float(item.get("tbr") or item.get("abr") or item.get("vbr")),
            size_bytes=_int(item.get("filesize") or item.get("filesize_approx")),
            protocol=str(item.get("protocol") or ""),
            language=str(item.get("language") or ""),
            hdr=dynamic_range not in {"", "SDR", "NONE"},
        ))

    subtitles: list[SubtitleTrack] = []
    subtitles.extend(_subtitle_tracks(info.get("subtitles"), automatic=False))
    subtitles.extend(_subtitle_tracks(info.get("automatic_captions"), automatic=True))
    drm = bool(info.get("is_drm") or info.get("_has_drm"))
    availability = str(info.get("availability") or "").lower()
    if availability in {"premium_only", "subscriber_only", "needs_auth"} and not formats:
        drm = True
    return MediaInspection(
        url=url,
        title=str(info.get("title") or info.get("playlist_title") or "Untitled media"),
        extractor=str(info.get("extractor_key") or info.get("extractor") or "Unknown"),
        duration_seconds=_int(info.get("duration")),
        thumbnail=str(info.get("thumbnail") or ""),
        is_live=bool(info.get("is_live") or info.get("live_status") == "is_live"),
        is_playlist=is_playlist,
        drm=drm,
        formats=formats,
        subtitles=subtitles,
        entries=entries,
    )


def build_format_selector(format_id: str, kind: str) -> str:
    format_id = str(format_id or "").strip()
    if format_id:
        return format_id
    if kind == "audio":
        return "bestaudio/best"
    return "bestvideo+bestaudio/best"


def _subtitle_tracks(raw: Any, *, automatic: bool) -> list[SubtitleTrack]:
    result: list[SubtitleTrack] = []
    if not isinstance(raw, dict):
        return result
    for language, variants in raw.items():
        extensions = sorted({str(v.get("ext") or "") for v in (variants or ()) if isinstance(v, dict) and v.get("ext")})
        result.append(SubtitleTrack(str(language), str(language), tuple(extensions), automatic))
    return result


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0

MEDIA_OPTIONS_PREFIX = "sdm-media:"


def encode_media_options(
    *,
    selector: str = "",
    container: str = "auto",
    audio_format: str = "original",
    thumbnail: bool = True,
    metadata: bool = True,
    chapters: bool = True,
    subtitle_mode: str = "none",
    subtitle_language: str = "all",
    embed_subtitles: bool = True,
) -> str:
    """Store Smart Media Center choices in the existing media_format field.

    The prefix keeps old database records compatible: plain values remain valid
    yt-dlp selectors, while new values carry a compact JSON settings document.
    """
    import json

    payload = {
        "f": str(selector or ""),
        "c": str(container or "auto"),
        "a": str(audio_format or "original"),
        "t": bool(thumbnail),
        "m": bool(metadata),
        "h": bool(chapters),
        "s": str(subtitle_mode or "none"),
        "l": str(subtitle_language or "all"),
        "e": bool(embed_subtitles),
    }
    return MEDIA_OPTIONS_PREFIX + json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def decode_media_options(value: str) -> dict[str, object]:
    import json

    raw = str(value or "")
    defaults: dict[str, object] = {
        "selector": raw,
        "container": "auto",
        "audio_format": "original",
        "thumbnail": False,
        "metadata": False,
        "chapters": False,
        "subtitle_mode": "none",
        "subtitle_language": "all",
        "embed_subtitles": False,
    }
    if not raw.startswith(MEDIA_OPTIONS_PREFIX):
        return defaults
    try:
        data = json.loads(raw[len(MEDIA_OPTIONS_PREFIX):])
    except (TypeError, ValueError, json.JSONDecodeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    defaults.update({
        "selector": str(data.get("f") or ""),
        "container": str(data.get("c") or "auto"),
        "audio_format": str(data.get("a") or "original"),
        "thumbnail": bool(data.get("t", True)),
        "metadata": bool(data.get("m", True)),
        "chapters": bool(data.get("h", True)),
        "subtitle_mode": str(data.get("s") or "none"),
        "subtitle_language": str(data.get("l") or "all"),
        "embed_subtitles": bool(data.get("e", True)),
    })
    return defaults
