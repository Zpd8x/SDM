from __future__ import annotations

import tempfile
import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sdm.database import DownloadRepository
from sdm.models import DownloadStatus


class DownloadRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "downloads.db"
        self.repository = DownloadRepository(database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_update_and_read_download(self) -> None:
        record = self.repository.create_download(
            url="https://example.com/file.zip",
            filename="file.zip",
            folder=self.temporary_directory.name,
        )
        self.repository.update(
            record.id,
            status=DownloadStatus.DOWNLOADING,
            downloaded_bytes=1234,
            total_bytes=5678,
        )

        saved = self.repository.get(record.id)
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.status, DownloadStatus.DOWNLOADING)
        self.assertEqual(saved.downloaded_bytes, 1234)
        self.assertEqual(saved.total_bytes, 5678)

    def test_recover_interrupted_download(self) -> None:
        record = self.repository.create_download(
            url="https://example.com/large.iso",
            filename="large.iso",
            folder=self.temporary_directory.name,
        )
        self.repository.update(record.id, status=DownloadStatus.RETRYING)

        reopened = DownloadRepository(self.repository.database_path)
        recovered = reopened.get(record.id)
        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertEqual(recovered.status, DownloadStatus.PAUSED)

    def test_settings_are_persistent(self) -> None:
        self.repository.set_setting("max_active_downloads", 3)
        reopened = DownloadRepository(self.repository.database_path)
        self.assertEqual(
            reopened.get_setting("max_active_downloads", "2"),
            "3",
        )

    def test_adaptive_server_profile_is_learned_and_reused(self) -> None:
        first = self.repository.create_download(
            url="https://cdn.example.com/first.bin",
            filename="first.bin",
            folder=self.temporary_directory.name,
            connections=8,
        )
        self.repository.record_adaptive_feedback(
            first.id,
            effective=4,
            kind="rate_limit",
            reason="HTTP 429",
        )

        second = self.repository.create_download(
            url="https://cdn.example.com/second.bin",
            filename="second.bin",
            folder=self.temporary_directory.name,
            connections=8,
        )
        prepared = self.repository.prepare_adaptive_download(second.id)
        assert prepared is not None
        self.assertEqual(prepared.connections, 8)
        self.assertEqual(prepared.adaptive_connections, 4)
        self.assertEqual(prepared.transfer_mode, "Adaptive 4/8")

        profile = self.repository.get_server_profile(second.url)
        assert profile is not None
        self.assertEqual(profile.preferred_connections, 4)
        self.assertEqual(profile.rate_limit_events, 1)

    def test_delete_removes_only_the_selected_record(self) -> None:
        first = self.repository.create_download(
            url="https://example.com/first.bin",
            filename="first.bin",
            folder=self.temporary_directory.name,
        )
        second = self.repository.create_download(
            url="https://example.com/second.bin",
            filename="second.bin",
            folder=self.temporary_directory.name,
        )

        self.repository.delete(first.id)

        self.assertIsNone(self.repository.get(first.id))
        self.assertIsNotNone(self.repository.get(second.id))

    def test_delete_all_removes_every_record(self) -> None:
        for index in range(3):
            self.repository.create_download(
                url=f"https://example.com/{index}.bin",
                filename=f"{index}.bin",
                folder=self.temporary_directory.name,
            )

        self.assertEqual(self.repository.delete_all(), 3)
        self.assertEqual(self.repository.list_all(), [])

    def test_stage_four_fields_are_persisted(self) -> None:
        scheduled_at = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat(timespec="seconds")
        checksum = "A" * 64
        record = self.repository.create_download(
            url="https://example.com/manual.pdf",
            filename="manual.pdf",
            folder=self.temporary_directory.name,
            start_immediately=False,
            category="Auto",
            scheduled_at=scheduled_at,
            checksum_sha256=checksum,
        )

        saved = self.repository.get(record.id)
        assert saved is not None
        self.assertEqual(saved.status, DownloadStatus.SCHEDULED)
        self.assertEqual(saved.category, "Documents")
        self.assertEqual(saved.scheduled_at, scheduled_at)
        self.assertEqual(saved.checksum_sha256, checksum.lower())
        self.assertEqual(saved.checksum_status, "Pending")

    def test_capture_dialog_fields_are_persisted(self) -> None:
        record = self.repository.create_download(
            url="https://example.com/captured.zip",
            filename="captured.zip",
            folder=self.temporary_directory.name,
            source="browser",
            description="Browser capture",
            capture_pending=True,
            media_kind="video",
            mime_type="video/mp4",
            referer="https://example.com/watch",
            rule_id="video-rule",
            rule_reason='Matched rule "Video".',
        )

        saved = self.repository.get(record.id)
        assert saved is not None
        self.assertEqual(saved.description, "Browser capture")
        self.assertTrue(saved.capture_pending)
        self.assertEqual(saved.media_kind, "video")
        self.assertEqual(saved.mime_type, "video/mp4")
        self.assertEqual(saved.referer, "https://example.com/watch")
        self.assertTrue(saved.identity_key)
        self.assertEqual(saved.rule_id, "video-rule")
        self.assertIn("Video", saved.rule_reason)

        self.repository.update(
            record.id,
            description="Ready for later",
            capture_pending=False,
            status=DownloadStatus.PAUSED,
        )
        updated = self.repository.get(record.id)
        assert updated is not None
        self.assertEqual(updated.description, "Ready for later")
        self.assertFalse(updated.capture_pending)

    def test_download_without_auto_start_is_paused(self) -> None:
        record = self.repository.create_download(
            url="https://example.com/later.bin",
            filename="later.bin",
            folder=self.temporary_directory.name,
            start_immediately=False,
        )
        self.assertEqual(record.status, DownloadStatus.PAUSED)

    def test_legacy_database_is_migrated(self) -> None:
        legacy_path = Path(self.temporary_directory.name) / "legacy.db"
        with closing(sqlite3.connect(legacy_path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE downloads (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    total_bytes INTEGER NOT NULL DEFAULT 0,
                    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    etag TEXT NOT NULL DEFAULT '',
                    last_modified TEXT NOT NULL DEFAULT ''
                )
                """
            )

        migrated = DownloadRepository(legacy_path)
        record = migrated.create_download(
            url="https://example.com/new.bin",
            filename="new.bin",
            folder=self.temporary_directory.name,
            connections=8,
        )
        saved = migrated.get(record.id)
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.connections, 8)
        self.assertEqual(saved.transfer_mode, "Auto")
        self.assertEqual(saved.source, "manual")
        self.assertFalse(saved.auto_start)
        self.assertEqual(saved.category, "Other")
        self.assertEqual(saved.scheduled_at, "")
        self.assertEqual(saved.checksum_status, "Not set")
        self.assertEqual(saved.mime_type, "")
        self.assertEqual(saved.referer, "")


if __name__ == "__main__":
    unittest.main()
