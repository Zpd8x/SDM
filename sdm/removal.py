from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from sdm.models import DownloadRecord


def segmented_parts_path(record: DownloadRecord) -> Path:
    return record.final_path.with_name(
        f".{record.filename}.sdm.parts"
    )


def download_artifact_paths(record: DownloadRecord) -> tuple[Path, ...]:
    return (
        record.final_path,
        record.temporary_path,
        segmented_parts_path(record),
    )


def destination_key(record: DownloadRecord) -> str:
    return str(record.final_path.resolve(strict=False)).casefold()


def destination_is_shared(
    record: DownloadRecord,
    records: Iterable[DownloadRecord],
) -> bool:
    selected_key = destination_key(record)
    return any(
        other.id != record.id and destination_key(other) == selected_key
        for other in records
    )


def delete_download_artifacts(record: DownloadRecord) -> tuple[Path, ...]:
    deleted: list[Path] = []
    for path in (record.final_path, record.temporary_path):
        if path.is_symlink() or path.is_file():
            path.unlink()
            deleted.append(path)
        elif path.exists():
            raise IsADirectoryError(
                f"Expected a file but found a directory: {path}"
            )

    parts_path = segmented_parts_path(record)
    if parts_path.is_symlink():
        parts_path.unlink()
        deleted.append(parts_path)
    elif parts_path.is_dir():
        shutil.rmtree(parts_path)
        deleted.append(parts_path)
    elif parts_path.exists():
        raise NotADirectoryError(
            f"Expected a parts directory but found a file: {parts_path}"
        )

    if record.media_kind != "direct":
        stem = record.final_path.stem
        for path in sorted(record.final_path.parent.glob(f"{stem}.*")):
            if path in deleted or not path.is_file():
                continue
            if ".part" in path.name or path.name.endswith(".ytdl"):
                path.unlink()
                deleted.append(path)
    return tuple(deleted)
