from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from sdm.models import DownloadRecord, DownloadStatus


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    sha256: str
    records: tuple[DownloadRecord, ...]
    existing_paths: tuple[Path, ...]
    reclaimable_bytes: int


@dataclass(frozen=True, slots=True)
class StorageReport:
    tracked_files: int
    existing_files: int
    missing_files: int
    modified_files: int
    duplicate_groups: int
    duplicate_files: int
    total_bytes: int
    reclaimable_bytes: int


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def duplicate_groups(records: Iterable[DownloadRecord]) -> list[DuplicateGroup]:
    buckets: dict[str, list[DownloadRecord]] = {}
    for record in records:
        digest = record.content_sha256.strip().lower()
        if record.status != DownloadStatus.COMPLETED or len(digest) != 64:
            continue
        if not record.final_path.is_file():
            continue
        buckets.setdefault(digest, []).append(record)

    groups: list[DuplicateGroup] = []
    for digest, members in buckets.items():
        if len(members) < 2:
            continue
        ordered = tuple(sorted(members, key=lambda item: (item.created_at, item.id)))
        paths = tuple(item.final_path for item in ordered)
        sizes = [path.stat().st_size for path in paths]
        groups.append(
            DuplicateGroup(
                sha256=digest,
                records=ordered,
                existing_paths=paths,
                reclaimable_bytes=sum(sizes) - max(sizes),
            )
        )
    return sorted(groups, key=lambda item: item.reclaimable_bytes, reverse=True)


def build_storage_report(records: Iterable[DownloadRecord]) -> StorageReport:
    records = list(records)
    groups = duplicate_groups(records)
    existing = 0
    missing = 0
    modified = 0
    total = 0
    for record in records:
        if record.status != DownloadStatus.COMPLETED:
            continue
        path = record.final_path
        if not path.is_file():
            missing += 1
            continue
        existing += 1
        size = path.stat().st_size
        total += size
        expected = record.total_bytes or record.downloaded_bytes
        if expected > 0 and size != expected:
            modified += 1
    return StorageReport(
        tracked_files=sum(1 for item in records if item.status == DownloadStatus.COMPLETED),
        existing_files=existing,
        missing_files=missing,
        modified_files=modified,
        duplicate_groups=len(groups),
        duplicate_files=sum(len(group.records) - 1 for group in groups),
        total_bytes=total,
        reclaimable_bytes=sum(group.reclaimable_bytes for group in groups),
    )


def scan_completed_records(
    repository,
    *,
    progress: Callable[[int, int, DownloadRecord], None] | None = None,
    stop_requested: Callable[[], bool] | None = None,
) -> StorageReport:
    records = repository.list_all()
    candidates = [item for item in records if item.status == DownloadStatus.COMPLETED]
    digest_owner: dict[str, str] = {}
    for item in candidates:
        digest = item.content_sha256.strip().lower()
        if len(digest) == 64 and item.final_path.is_file():
            digest_owner.setdefault(digest, item.id)

    for index, record in enumerate(candidates, start=1):
        if stop_requested and stop_requested():
            break
        path = record.final_path
        if progress:
            progress(index, len(candidates), record)
        if not path.is_file():
            repository.update(
                record.id,
                content_fingerprint_status="Missing",
                duplicate_of_id="",
            )
            continue
        try:
            size = path.stat().st_size
            digest = sha256_file(path)
            owner = digest_owner.get(digest)
            duplicate_of = owner if owner and owner != record.id else ""
            if not owner:
                digest_owner[digest] = record.id
            repository.update(
                record.id,
                total_bytes=size,
                downloaded_bytes=size,
                content_sha256=digest,
                content_fingerprint_status=("Duplicate" if duplicate_of else "Unique"),
                duplicate_of_id=duplicate_of,
            )
        except OSError:
            repository.update(
                record.id,
                content_fingerprint_status="Error",
                duplicate_of_id="",
            )
    return build_storage_report(repository.list_all())


def choose_keeper(group: DuplicateGroup, policy: str = "oldest") -> DownloadRecord:
    if policy == "newest":
        return max(group.records, key=lambda item: (item.created_at, item.id))
    return min(group.records, key=lambda item: (item.created_at, item.id))


def replace_with_hardlink(source: str | Path, target: str | Path) -> None:
    source_path = Path(source)
    target_path = Path(target)
    if not source_path.is_file() or not target_path.is_file():
        raise FileNotFoundError("Both source and target files must exist.")
    if source_path.stat().st_dev != target_path.stat().st_dev:
        raise OSError("Hard links require both files to be on the same volume.")
    temporary = target_path.with_name(target_path.name + ".sdm-linking")
    if temporary.exists():
        temporary.unlink()
    os.link(source_path, temporary)
    target_path.unlink()
    temporary.replace(target_path)
