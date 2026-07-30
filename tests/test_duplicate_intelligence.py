from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sdm.database import DownloadRepository
from sdm.duplicate_intelligence import (
    DuplicateCandidate,
    DuplicateDisposition,
    DuplicateReason,
    canonical_download_identity,
    choose_copy_filename,
    find_duplicate,
)
from sdm.models import DownloadStatus


class DuplicateIntelligenceTests(unittest.TestCase):
    def test_identity_removes_short_lived_and_tracking_query_fields(self) -> None:
        first = canonical_download_identity(
            "https://CDN.example.com/file.zip?id=7&token=abc&utm_source=x"
        )
        second = canonical_download_identity(
            "https://cdn.example.com/file.zip?token=xyz&id=7"
        )
        self.assertEqual(first, "https://cdn.example.com/file.zip?id=7")
        self.assertEqual(first, second)

    def test_same_stable_source_finds_a_resumable_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = DownloadRepository(
                Path(temporary_directory) / "downloads.db"
            )
            record = repository.create_download(
                url="https://example.com/file.bin?sig=old",
                source_url="https://example.com/file.bin",
                filename="file.bin",
                folder=temporary_directory,
                start_immediately=False,
            )
            match = find_duplicate(
                repository.list_all(),
                DuplicateCandidate(
                    url="https://example.com/file.bin?sig=new",
                    source_url="https://example.com/file.bin",
                    filename="another.bin",
                    folder=temporary_directory,
                ),
            )
        assert match is not None
        self.assertEqual(match.record.id, record.id)
        self.assertEqual(match.reason, DuplicateReason.SOURCE)
        self.assertEqual(
            match.disposition,
            DuplicateDisposition.RESUMABLE,
        )

    def test_completed_target_path_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = DownloadRepository(
                Path(temporary_directory) / "downloads.db"
            )
            record = repository.create_download(
                url="https://one.example/a",
                filename="same.zip",
                folder=temporary_directory,
            )
            repository.update(record.id, status=DownloadStatus.COMPLETED)
            match = find_duplicate(
                repository.list_all(),
                DuplicateCandidate(
                    url="https://two.example/b",
                    filename="same.zip",
                    folder=temporary_directory,
                ),
            )
        assert match is not None
        self.assertEqual(match.reason, DuplicateReason.TARGET)
        self.assertEqual(
            match.disposition,
            DuplicateDisposition.COMPLETED,
        )

    def test_copy_name_avoids_database_and_disk_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = DownloadRepository(root / "downloads.db")
            repository.create_download(
                url="https://example.com/a",
                filename="archive.zip",
                folder=str(root),
            )
            (root / "archive (1).zip").write_bytes(b"x")
            filename = choose_copy_filename(
                root,
                "archive.zip",
                repository.list_all(),
            )
        self.assertEqual(filename, "archive (2).zip")


if __name__ == "__main__":
    unittest.main()
