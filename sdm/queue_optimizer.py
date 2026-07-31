from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sdm.models import DownloadRecord, DownloadStatus


_PRIORITY_WEIGHT = {
    "Highest": 0,
    "High": 1,
    "Normal": 2,
    "Low": 3,
    "Background": 4,
}

_STATUS_WEIGHT = {
    DownloadStatus.RETRYING: 0,
    DownloadStatus.QUEUED: 1,
    DownloadStatus.PAUSED: 2,
    DownloadStatus.SCHEDULED: 3,
}


@dataclass(frozen=True, slots=True)
class QueueOptimizationResult:
    ordered_ids: tuple[str, ...]
    changed: bool
    explanation: str


def optimize_queue(records: Iterable[DownloadRecord]) -> QueueOptimizationResult:
    """Return a deterministic, conservative queue order.

    Active and completed records are excluded. Waiting items are ordered by
    priority, retry state, smaller known size, then creation time. Unknown
    sizes stay behind known small files at the same priority.
    """
    candidates = [
        record
        for record in records
        if record.status in {
            DownloadStatus.QUEUED,
            DownloadStatus.RETRYING,
            DownloadStatus.PAUSED,
            DownloadStatus.SCHEDULED,
        }
    ]
    current = tuple(record.id for record in candidates)

    def key(record: DownloadRecord):
        size_unknown = 1 if int(record.total_bytes or 0) <= 0 else 0
        size = int(record.total_bytes or 0)
        return (
            _PRIORITY_WEIGHT.get(record.priority, 2),
            _STATUS_WEIGHT.get(record.status, 9),
            size_unknown,
            size,
            record.created_at,
            record.filename.casefold(),
        )

    ordered = tuple(record.id for record in sorted(candidates, key=key))
    return QueueOptimizationResult(
        ordered_ids=ordered,
        changed=ordered != current,
        explanation=(
            "Priority first, then retry/queued state, known smaller files, "
            "and creation time. Active downloads are never interrupted."
        ),
    )
