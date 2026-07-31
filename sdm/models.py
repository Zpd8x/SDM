from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DownloadStatus(str, Enum):
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    RETRYING = "retrying"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(slots=True)
class DownloadRecord:
    id: str
    url: str
    filename: str
    folder: str
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: DownloadStatus = DownloadStatus.QUEUED
    created_at: str = ""
    updated_at: str = ""
    error: str = ""
    etag: str = ""
    last_modified: str = ""
    connections: int = 4
    adaptive_connections: int = 4
    adaptive_reason: str = ""
    transfer_mode: str = "Auto"
    source: str = "manual"
    auto_start: bool = False
    category: str = "Other"
    scheduled_at: str = ""
    checksum_sha256: str = ""
    checksum_actual: str = ""
    checksum_status: str = "Not set"
    description: str = ""
    capture_pending: bool = False
    media_kind: str = "direct"
    mime_type: str = ""
    referer: str = ""
    source_url: str = ""
    site_adapter: str = "direct"
    adapter_status: str = ""
    resolved_at: str = ""
    identity_key: str = ""
    rule_id: str = ""
    rule_reason: str = ""
    content_sha256: str = ""
    content_fingerprint_status: str = "Pending"
    duplicate_of_id: str = ""
    media_format: str = ""
    session_name: str = "Today"
    priority: str = "Normal"
    tags: str = ""

    @property
    def final_path(self) -> Path:
        return Path(self.folder) / self.filename

    @property
    def temporary_path(self) -> Path:
        return self.final_path.with_name(f"{self.filename}.sdm.part")

    @property
    def progress(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, self.downloaded_bytes / self.total_bytes)
