from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sdm.models import DownloadRecord, DownloadStatus
from sdm.site_adapters import EXPIRING_QUERY_KEYS, build_adapter_plan
from sdm.utils import sanitize_filename


_TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
    }
)
_ACTIVE_STATUSES = frozenset(
    {
        DownloadStatus.SCHEDULED,
        DownloadStatus.QUEUED,
        DownloadStatus.DOWNLOADING,
        DownloadStatus.RETRYING,
        DownloadStatus.VERIFYING,
    }
)
_RESUMABLE_STATUSES = frozenset(
    {
        DownloadStatus.PAUSED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELED,
    }
)


class DuplicateReason(str, Enum):
    SOURCE = "source"
    TARGET = "target"
    METADATA = "metadata"


class DuplicateDisposition(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    RESUMABLE = "resumable"


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    url: str
    filename: str
    folder: str
    source_url: str = ""
    site_adapter: str = ""
    referer: str = ""
    total_bytes: int = 0
    etag: str = ""
    last_modified: str = ""

    @property
    def identity_key(self) -> str:
        return canonical_download_identity(
            self.url,
            source_url=self.source_url,
            page_url=self.referer,
        )

    @property
    def target_key(self) -> str:
        return normalized_target_path(self.folder, self.filename)


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    record: DownloadRecord
    reason: DuplicateReason
    disposition: DuplicateDisposition

    @property
    def explanation(self) -> str:
        if self.reason == DuplicateReason.SOURCE:
            return "The same download source is already in SDM."
        if self.reason == DuplicateReason.TARGET:
            return "Another SDM item already uses the same output path."
        return "The server metadata matches an existing SDM download."


def canonical_download_identity(
    url: str,
    *,
    source_url: str = "",
    page_url: str = "",
) -> str:
    """Return a stable identity without short-lived signature parameters."""

    plan = build_adapter_plan(
        str(url or ""),
        source_url=str(source_url or ""),
        page_url=str(page_url or ""),
    )
    candidate = plan.source_url or str(source_url or "") or str(url or "")
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return candidate.strip()
    if parsed.scheme.casefold() not in {"http", "https"}:
        return candidate.strip()

    scheme = parsed.scheme.casefold()
    host = (parsed.hostname or "").casefold()
    port = parsed.port
    if port and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    path = parsed.path or "/"
    filtered_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = key.casefold()
        if normalized_key in EXPIRING_QUERY_KEYS:
            continue
        if normalized_key in _TRACKING_QUERY_KEYS:
            continue
        if normalized_key.startswith("utm_"):
            continue
        filtered_query.append((key, value))
    filtered_query.sort(key=lambda item: (item[0].casefold(), item[1]))
    return urlunsplit(
        (
            scheme,
            netloc,
            path,
            urlencode(filtered_query, doseq=True),
            "",
        )
    )


def normalized_target_path(folder: str, filename: str) -> str:
    path = Path(str(folder or "")).expanduser() / str(filename or "")
    resolved = str(path.resolve(strict=False))
    return os.path.normcase(resolved).casefold()


def record_identity_key(record: DownloadRecord) -> str:
    if record.identity_key:
        return record.identity_key
    return canonical_download_identity(
        record.url,
        source_url=record.source_url,
        page_url=record.referer,
    )


def find_duplicate(
    records: Iterable[DownloadRecord],
    candidate: DuplicateCandidate,
    *,
    exclude_id: str = "",
) -> DuplicateMatch | None:
    source_key = candidate.identity_key
    target_key = candidate.target_key
    source_match: DownloadRecord | None = None
    target_match: DownloadRecord | None = None
    metadata_match: DownloadRecord | None = None

    for record in records:
        if record.id == exclude_id:
            continue
        if source_key and record_identity_key(record) == source_key:
            source_match = _prefer_record(source_match, record)
            continue
        if target_key and normalized_target_path(
            record.folder,
            record.filename,
        ) == target_key:
            target_match = _prefer_record(target_match, record)
            continue
        if _metadata_matches(record, candidate):
            metadata_match = _prefer_record(metadata_match, record)

    if source_match is not None:
        return _build_match(source_match, DuplicateReason.SOURCE)
    if target_match is not None:
        return _build_match(target_match, DuplicateReason.TARGET)
    if metadata_match is not None:
        return _build_match(metadata_match, DuplicateReason.METADATA)
    return None


def choose_copy_filename(
    folder: str | Path,
    filename: str,
    records: Iterable[DownloadRecord],
) -> str:
    destination = Path(folder).expanduser()
    requested = sanitize_filename(filename)
    reserved = {
        record.filename.casefold()
        for record in records
        if normalized_folder(record.folder) == normalized_folder(destination)
    }
    suffix = Path(requested).suffix
    stem = Path(requested).stem
    candidate = requested
    index = 1
    while candidate.casefold() in reserved or (destination / candidate).exists():
        candidate = sanitize_filename(f"{stem} ({index}){suffix}")
        index += 1
    return candidate


def normalized_folder(folder: str | Path) -> str:
    return os.path.normcase(
        str(Path(folder).expanduser().resolve(strict=False))
    ).casefold()


def _metadata_matches(
    record: DownloadRecord,
    candidate: DuplicateCandidate,
) -> bool:
    if candidate.etag and record.etag:
        if candidate.etag.strip() == record.etag.strip():
            return True
    if (
        candidate.last_modified
        and record.last_modified
        and candidate.last_modified.strip() == record.last_modified.strip()
        and candidate.total_bytes > 0
        and record.total_bytes == candidate.total_bytes
    ):
        return True
    return (
        candidate.total_bytes > 0
        and record.total_bytes == candidate.total_bytes
        and record.filename.casefold() == candidate.filename.casefold()
        and normalized_folder(record.folder) == normalized_folder(
            candidate.folder
        )
    )


def _prefer_record(
    current: DownloadRecord | None,
    candidate: DownloadRecord,
) -> DownloadRecord:
    if current is None:
        return candidate
    current_rank = _status_rank(current.status)
    candidate_rank = _status_rank(candidate.status)
    if candidate_rank != current_rank:
        return candidate if candidate_rank > current_rank else current
    return candidate if candidate.updated_at > current.updated_at else current


def _status_rank(status: DownloadStatus) -> int:
    if status in _ACTIVE_STATUSES:
        return 3
    if status == DownloadStatus.COMPLETED:
        return 2
    return 1


def _build_match(
    record: DownloadRecord,
    reason: DuplicateReason,
) -> DuplicateMatch:
    if record.status in _ACTIVE_STATUSES:
        disposition = DuplicateDisposition.ACTIVE
    elif record.status == DownloadStatus.COMPLETED:
        disposition = DuplicateDisposition.COMPLETED
    elif record.status in _RESUMABLE_STATUSES:
        disposition = DuplicateDisposition.RESUMABLE
    else:
        disposition = DuplicateDisposition.RESUMABLE
    return DuplicateMatch(
        record=record,
        reason=reason,
        disposition=disposition,
    )
