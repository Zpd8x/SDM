from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sdm.content_fingerprint import classify_content_fingerprint
from sdm.database import DownloadRepository
from sdm.models import DownloadStatus


class ContentFingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = DownloadRepository(self.root / "downloads.db")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_repository_finds_completed_identical_content(self) -> None:
        digest = "a" * 64
        first = self.repository.create_download(
            url="https://one.example/first.bin",
            filename="first.bin",
            folder=str(self.root),
        )
        self.repository.update(
            first.id,
            status=DownloadStatus.COMPLETED,
            content_sha256=digest,
            content_fingerprint_status="Unique",
        )
        second = self.repository.create_download(
            url="https://two.example/renamed.data",
            filename="renamed.data",
            folder=str(self.root / "other"),
        )

        result = classify_content_fingerprint(
            self.repository,
            digest,
            record_id=second.id,
        )

        self.assertEqual(result.status, "Duplicate")
        self.assertEqual(result.duplicate_of_id, first.id)

    def test_incomplete_records_are_not_content_matches(self) -> None:
        digest = "b" * 64
        record = self.repository.create_download(
            url="https://example.com/pending.bin",
            filename="pending.bin",
            folder=str(self.root),
        )
        self.repository.update(record.id, content_sha256=digest)

        result = classify_content_fingerprint(
            self.repository,
            digest,
            record_id="another-record",
        )

        self.assertEqual(result.status, "Unique")
        self.assertEqual(result.duplicate_of_id, "")

    def test_fingerprint_fields_persist_across_reopen(self) -> None:
        digest = "c" * 64
        record = self.repository.create_download(
            url="https://example.com/file.bin",
            filename="file.bin",
            folder=str(self.root),
        )
        self.repository.update(
            record.id,
            content_sha256=digest,
            content_fingerprint_status="Duplicate",
            duplicate_of_id="older-record",
        )

        reopened = DownloadRepository(self.repository.database_path)
        saved = reopened.get(record.id)

        assert saved is not None
        self.assertEqual(saved.content_sha256, digest)
        self.assertEqual(saved.content_fingerprint_status, "Duplicate")
        self.assertEqual(saved.duplicate_of_id, "older-record")


if __name__ == "__main__":
    unittest.main()
