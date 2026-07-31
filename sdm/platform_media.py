from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from sdm.config import USER_AGENT
from sdm.engine import (
    DownloadCancelled,
    DownloadControl,
    DownloadError,
    DownloadResult,
    MetadataCallback,
    ProgressCallback,
    StatusCallback,
)
from sdm.models import DownloadRecord, DownloadStatus
from sdm.media_inspector import decode_media_options


ModeCallback = Callable[[str, int], None]


class PlatformMediaEngine:
    """Download public media pages supported by yt-dlp.

    Direct file URLs continue to use SDM's native segmented engine. This
    adapter is reserved for browser pages whose media URL is hidden behind a
    blob, HLS/DASH manifest, or a platform extractor.
    """

    def download(
        self,
        record: DownloadRecord,
        control: DownloadControl,
        *,
        on_progress: ProgressCallback | None = None,
        on_status: StatusCallback | None = None,
        on_metadata: MetadataCallback | None = None,
        on_mode: ModeCallback | None = None,
    ) -> DownloadResult:
        progress_callback = on_progress or (lambda *_: None)
        status_callback = on_status or (lambda *_: None)
        metadata_callback = on_metadata or (lambda *_: None)
        mode_callback = on_mode or (lambda *_: None)

        try:
            import yt_dlp
        except ImportError as error:
            raise DownloadError(
                "The platform media component is missing. "
                "Run START_SDM.bat once while connected to the internet."
            ) from error

        control.wait_until_running()
        record.final_path.parent.mkdir(parents=True, exist_ok=True)
        output_template, output_stem = self._output_template(record)
        active_fragments = max(1, min(4, int(record.connections)))
        mode_callback("Platform media", active_fragments)

        last_total = 0
        reported_path = ""

        def progress_hook(data: dict[str, Any]) -> None:
            nonlocal last_total, reported_path
            control.wait_until_running()
            if control.is_cancelled:
                raise DownloadCancelled("Download canceled.")

            raw_filename = data.get("filename") or data.get("tmpfilename")
            if raw_filename:
                reported_path = str(raw_filename)
            downloaded = _safe_int(data.get("downloaded_bytes"))
            total = _safe_int(
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
            )
            speed = _safe_float(data.get("speed"))
            eta_value = data.get("eta")
            eta = _safe_int(eta_value) if eta_value is not None else None
            if total and total != last_total:
                last_total = total
                metadata_callback(total, "", "")
            progress_callback(downloaded, total, speed, eta)

        http_headers = {"User-Agent": USER_AGENT}
        if record.referer:
            http_headers["Referer"] = record.referer
        media_options = decode_media_options(record.media_format)
        selector = str(media_options.get("selector") or "")
        options: dict[str, Any] = {
            "format": selector or self._format_for(record.media_kind),
            "outtmpl": {"default": str(output_template)},
            "noplaylist": True,
            "continuedl": True,
            "nopart": False,
            "overwrites": False,
            "quiet": True,
            "no_warnings": True,
            "retries": 5,
            "fragment_retries": 5,
            "file_access_retries": 3,
            "concurrent_fragment_downloads": active_fragments,
            "progress_hooks": [progress_hook],
            "http_headers": http_headers,
        }
        self._apply_media_options(options, media_options, record.media_kind)

        status_callback(
            DownloadStatus.DOWNLOADING,
            "Inspecting the media page and selecting a downloadable stream.",
        )
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(record.url, download=True)
                final_path = self._resolve_output_path(
                    downloader,
                    info,
                    output_stem,
                    reported_path,
                )
        except DownloadCancelled:
            raise
        except Exception as error:
            if control.is_cancelled:
                raise DownloadCancelled("Download canceled.") from error
            message = _clean_error(error)
            advice = _failure_advice(record.url, message)
            raise DownloadError(
                "Could not extract this media page. "
                f"{advice} Details: {message}"
            ) from error

        if not final_path.is_file():
            raise DownloadError(
                "The media extractor finished without creating an output file."
            )
        total = final_path.stat().st_size
        metadata_callback(total, "", "")
        progress_callback(total, total, 0.0, 0)
        return DownloadResult(
            final_path=final_path,
            downloaded_bytes=total,
            total_bytes=total,
        )


    @staticmethod
    def _apply_media_options(
        options: dict[str, Any],
        media_options: dict[str, object],
        media_kind: str,
    ) -> None:
        """Translate Smart Media Center choices into yt-dlp options."""
        postprocessors: list[dict[str, Any]] = []
        container = str(media_options.get("container") or "auto").lower()
        if container in {"mp4", "mkv", "webm"}:
            options["merge_output_format"] = container

        audio_format = str(media_options.get("audio_format") or "original").lower()
        if media_kind == "audio" and audio_format in {"mp3", "m4a", "opus", "wav", "flac"}:
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "0" if audio_format in {"wav", "flac"} else "192",
            })

        if bool(media_options.get("thumbnail")):
            options["writethumbnail"] = True
            postprocessors.append({"key": "EmbedThumbnail"})
        keep_metadata = bool(media_options.get("metadata"))
        keep_chapters = bool(media_options.get("chapters"))
        if keep_metadata or keep_chapters:
            postprocessors.append({
                "key": "FFmpegMetadata",
                "add_metadata": keep_metadata,
                "add_chapters": keep_chapters,
            })

        subtitle_mode = str(media_options.get("subtitle_mode") or "none").lower()
        if subtitle_mode != "none":
            options["writesubtitles"] = subtitle_mode in {"manual", "all"}
            options["writeautomaticsub"] = subtitle_mode in {"automatic", "all"}
            language = str(media_options.get("subtitle_language") or "all")
            if language and language != "all":
                options["subtitleslangs"] = [language]
            options["subtitlesformat"] = "best"
            if bool(media_options.get("embed_subtitles")):
                postprocessors.append({"key": "FFmpegEmbedSubtitle"})

        if postprocessors:
            options["postprocessors"] = postprocessors

    @staticmethod
    def _format_for(media_kind: str) -> str:
        if media_kind == "audio":
            return "bestaudio/best"
        return (
            "best[acodec!=none][vcodec!=none]/"
            "best[vcodec!=none]/best"
        )

    @staticmethod
    def _output_template(record: DownloadRecord) -> tuple[Path, Path]:
        requested = record.final_path
        output_stem = requested.with_suffix("") if requested.suffix else requested
        return (
            output_stem.with_name(f"{output_stem.name}.%(ext)s"),
            output_stem,
        )

    @staticmethod
    def _resolve_output_path(
        downloader: Any,
        info: Any,
        output_stem: Path,
        reported_path: str,
    ) -> Path:
        candidates: list[Path] = []
        if reported_path:
            candidates.append(Path(reported_path))
        if isinstance(info, dict):
            for item in info.get("requested_downloads") or ():
                if isinstance(item, dict) and item.get("filepath"):
                    candidates.append(Path(str(item["filepath"])))
            if info.get("filepath"):
                candidates.append(Path(str(info["filepath"])))
            if info.get("_filename"):
                candidates.append(Path(str(info["_filename"])))
            try:
                candidates.append(Path(str(downloader.prepare_filename(info))))
            except (AttributeError, KeyError, TypeError, ValueError):
                pass

        for candidate in candidates:
            if candidate.suffix == ".part":
                candidate = candidate.with_suffix("")
            if candidate.is_file():
                return candidate

        matches = sorted(
            (
                path
                for path in output_stem.parent.glob(f"{output_stem.name}.*")
                if path.is_file()
                and not path.name.endswith((".part", ".ytdl", ".temp"))
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]
        return candidates[0] if candidates else output_stem


def _safe_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _clean_error(error: Exception) -> str:
    message = str(error).strip().replace("\r", " ").replace("\n", " ")
    return " ".join(message.split()) or error.__class__.__name__


def _failure_advice(url: str, message: str) -> str:
    host = ""
    try:
        from urllib.parse import urlsplit

        host = urlsplit(url).hostname or ""
    except ValueError:
        pass
    if host == "audiomack.com" or host.endswith(".audiomack.com"):
        return (
            "Audiomack changed its extractor API. Play the track in the "
            "browser for a few seconds, then press the SDM mini box again so "
            "Smart Capture can use the real stream. "
        )
    if "unsupported url" in message.casefold():
        return (
            "This platform is not supported by the fallback extractor. "
            "Play the media first so Smart Capture can detect its stream. "
        )
    return "The media may be private, login-protected, or DRM-protected. "
