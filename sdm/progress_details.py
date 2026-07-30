from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sdm.models import DownloadRecord, DownloadStatus
from sdm.removal import segmented_parts_path


@dataclass(frozen=True, slots=True)
class ConnectionProgress:
    index: int
    downloaded_bytes: int
    total_bytes: int
    status: str

    @property
    def fraction(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, self.downloaded_bytes / self.total_bytes)


@dataclass(frozen=True, slots=True)
class ProgressActionState:
    can_pause: bool
    can_resume: bool
    terminal: bool
    cancel_label: str


def progress_action_state(status: DownloadStatus) -> ProgressActionState:
    """Describe the progress-window actions for a download state."""
    can_pause = status in {
        DownloadStatus.QUEUED,
        DownloadStatus.DOWNLOADING,
        DownloadStatus.RETRYING,
    }
    can_resume = status in {
        DownloadStatus.PAUSED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELED,
    }
    terminal = status in {
        DownloadStatus.COMPLETED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELED,
    }
    return ProgressActionState(
        can_pause=can_pause,
        can_resume=can_resume,
        terminal=terminal,
        cancel_label="Close" if terminal else "Cancel",
    )


def read_connection_progress(
    record: DownloadRecord,
    *,
    downloaded_bytes: int | None = None,
    total_bytes: int | None = None,
    status: DownloadStatus | None = None,
) -> tuple[ConnectionProgress, ...]:
    """Read safe per-connection progress from SDM segment part files."""
    current_downloaded = max(
        0,
        int(
            record.downloaded_bytes
            if downloaded_bytes is None
            else downloaded_bytes
        ),
    )
    current_total = max(
        0,
        int(record.total_bytes if total_bytes is None else total_bytes),
    )
    current_status = status or record.status

    part_directory = segmented_parts_path(record)
    manifest = _read_manifest(part_directory / "manifest.json")
    segments = manifest.get("segments") if manifest else None
    if isinstance(segments, list) and segments:
        progress: list[ConnectionProgress] = []
        for index, raw_segment in enumerate(segments):
            if not isinstance(raw_segment, dict):
                return _single_connection(
                    current_downloaded,
                    current_total,
                    current_status,
                )
            try:
                start = int(raw_segment["start"])
                end = int(raw_segment["end"])
            except (KeyError, TypeError, ValueError):
                return _single_connection(
                    current_downloaded,
                    current_total,
                    current_status,
                )
            length = max(0, end - start + 1)
            part_path = part_directory / f"segment_{index:03d}.part"
            try:
                downloaded = min(length, max(0, part_path.stat().st_size))
            except OSError:
                downloaded = 0
            progress.append(
                ConnectionProgress(
                    index=index + 1,
                    downloaded_bytes=downloaded,
                    total_bytes=length,
                    status=_connection_status(
                        downloaded,
                        length,
                        current_status,
                    ),
                )
            )
        return tuple(progress)

    return _single_connection(
        current_downloaded,
        current_total,
        current_status,
    )


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _single_connection(
    downloaded: int,
    total: int,
    status: DownloadStatus,
) -> tuple[ConnectionProgress, ...]:
    return (
        ConnectionProgress(
            index=1,
            downloaded_bytes=downloaded,
            total_bytes=total,
            status=_connection_status(downloaded, total, status),
        ),
    )


def _connection_status(
    downloaded: int,
    total: int,
    status: DownloadStatus,
) -> str:
    if total > 0 and downloaded >= total:
        return "Completed"
    labels = {
        DownloadStatus.QUEUED: "Waiting",
        DownloadStatus.DOWNLOADING: "Downloading",
        DownloadStatus.PAUSED: "Paused",
        DownloadStatus.RETRYING: "Retrying",
        DownloadStatus.VERIFYING: "Verifying",
        DownloadStatus.COMPLETED: "Completed",
        DownloadStatus.FAILED: "Failed",
        DownloadStatus.CANCELED: "Canceled",
        DownloadStatus.SCHEDULED: "Scheduled",
    }
    return labels[status]
