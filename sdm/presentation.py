from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from sdm.models import DownloadRecord, DownloadStatus
from sdm.schedule import format_scheduled_local


def build_summary_text(records: Sequence[DownloadRecord]) -> str:
    if not records:
        return "No downloads"

    counts = Counter(record.status for record in records)
    active_count = (
        counts[DownloadStatus.DOWNLOADING]
        + counts[DownloadStatus.RETRYING]
        + counts[DownloadStatus.VERIFYING]
    )
    return (
        f"{len(records)} total  •  "
        f"{active_count} active  •  "
        f"{counts[DownloadStatus.QUEUED]} queued  •  "
        f"{counts[DownloadStatus.SCHEDULED]} scheduled  •  "
        f"{counts[DownloadStatus.PAUSED]} paused  •  "
        f"{counts[DownloadStatus.COMPLETED]} completed"
    )


def build_status_message(
    record: DownloadRecord,
    *,
    detail: str = "",
) -> str:
    filename = record.filename
    if record.status == DownloadStatus.SCHEDULED:
        scheduled = format_scheduled_local(record.scheduled_at)
        return (
            f"Scheduled {filename} for {scheduled}."
            if scheduled
            else f"Scheduled {filename}."
        )
    if record.status == DownloadStatus.QUEUED:
        return f"Queued {filename}."
    if record.status == DownloadStatus.DOWNLOADING:
        return f"Downloading {filename}…"
    if record.status == DownloadStatus.PAUSED:
        return f"Paused {filename}."
    if record.status == DownloadStatus.RETRYING:
        suffix = f" {detail}" if detail else ""
        return f"Retrying {filename}.{suffix}".strip()
    if record.status == DownloadStatus.VERIFYING:
        return f"Verifying SHA-256 for {filename}…"
    if record.status == DownloadStatus.COMPLETED:
        return f"Completed {filename}."
    if record.status == DownloadStatus.CANCELED:
        return f"Canceled {filename}. The partial file was kept."
    if record.status == DownloadStatus.FAILED:
        suffix = f" Error: {detail}" if detail else ""
        return f"Failed {filename}.{suffix}".strip()
    return detail or "Ready."
