from __future__ import annotations

from dataclasses import dataclass

from sdm.database import DownloadRepository
from sdm.models import DownloadRecord


@dataclass(frozen=True, slots=True)
class ContentFingerprintResult:
    sha256: str
    status: str
    duplicate: DownloadRecord | None = None

    @property
    def duplicate_of_id(self) -> str:
        return self.duplicate.id if self.duplicate is not None else ""


def classify_content_fingerprint(
    repository: DownloadRepository,
    sha256: str,
    *,
    record_id: str,
) -> ContentFingerprintResult:
    duplicate = repository.find_completed_by_content_sha256(
        sha256,
        exclude_id=record_id,
    )
    return ContentFingerprintResult(
        sha256=sha256,
        status="Duplicate" if duplicate is not None else "Unique",
        duplicate=duplicate,
    )
