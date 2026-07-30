from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sdm.browser_bridge import (
    acquire_launch_guard,
    enqueue_browser_download,
    handle_native_message,
    is_application_running,
    release_launch_guard,
)
from sdm.database import DownloadRepository
from sdm.models import DownloadStatus


class BrowserBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database = self.root / "downloads.db"
        self.downloads = self.root / "Downloads"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_browser_request_creates_pending_capture_dialog(self) -> None:
        result = enqueue_browser_download(
            self.database,
            {
                "url": "https://example.com/archive.zip",
                "filename": "archive.zip",
                "connections": 4,
                "start_immediately": True,
                "total_bytes": 7360,
                "mime_type": "application/zip",
            },
            default_folder=self.downloads,
        )

        record = DownloadRepository(self.database).get(result.record_id)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.source, "browser")
        self.assertTrue(record.auto_start)
        self.assertTrue(record.capture_pending)
        self.assertEqual(record.status, DownloadStatus.QUEUED)
        self.assertEqual(record.connections, 4)
        self.assertEqual(record.category, "Archives")
        self.assertEqual(record.total_bytes, 7360)
        self.assertEqual(record.mime_type, "application/zip")

    def test_browser_request_without_auto_start_is_paused(self) -> None:
        result = enqueue_browser_download(
            self.database,
            {
                "url": "https://example.com/later.bin",
                "connections": 2,
                "start_immediately": False,
            },
            default_folder=self.downloads,
        )

        record = DownloadRepository(self.database).get(result.record_id)
        assert record is not None
        self.assertFalse(record.auto_start)
        self.assertTrue(record.capture_pending)
        self.assertEqual(record.status, DownloadStatus.PAUSED)

    def test_platform_media_request_is_marked_for_extraction(self) -> None:
        result = enqueue_browser_download(
            self.database,
            {
                "url": "https://www.instagram.com/reel/example/",
                "filename": "Example reel.mp4",
                "media_kind": "video",
            },
            default_folder=self.downloads,
        )

        record = DownloadRepository(self.database).get(result.record_id)
        assert record is not None
        self.assertEqual(record.media_kind, "video")
        self.assertEqual(record.filename, "Example reel.mp4")

    def test_platform_media_without_name_gets_a_safe_default(self) -> None:
        result = enqueue_browser_download(
            self.database,
            {
                "url": "https://soundcloud.com/artist/track",
                "media_kind": "audio",
            },
            default_folder=self.downloads,
        )
        self.assertEqual(result.filename, "Browser audio.m4a")

    def test_smart_capture_promotes_real_browser_stream_and_referer(self) -> None:
        result = enqueue_browser_download(
            self.database,
            {
                "url": "https://audiomack.com/artist/song/track",
                "page_url": "https://audiomack.com/artist/song/track",
                "filename": "Track.m4a",
                "media_kind": "audio",
                "capture_candidates": [
                    {
                        "url": "https://cdn.example.com/audio/track.m4a?sig=1",
                        "source": "performance",
                        "score": 880,
                        "direct": True,
                        "mime_type": "audio/mp4",
                    }
                ],
            },
            default_folder=self.downloads,
        )
        record = DownloadRepository(self.database).get(result.record_id)
        assert record is not None
        self.assertEqual(record.media_kind, "direct")
        self.assertEqual(
            record.url,
            "https://cdn.example.com/audio/track.m4a?sig=1",
        )
        self.assertEqual(
            record.referer,
            "https://audiomack.com/artist/song/track",
        )
        self.assertEqual(record.mime_type, "audio/mp4")

    def test_network_capture_metadata_reaches_download_record(self) -> None:
        result = enqueue_browser_download(
            self.database,
            {
                "url": "https://music.example/player/track",
                "page_url": "https://music.example/player/track",
                "filename": "fallback.bin",
                "media_kind": "audio",
                "capture_candidates": [
                    {
                        "url": "https://cdn.example/media?id=7",
                        "source": "webrequest",
                        "score": 995,
                        "direct": True,
                        "mime_type": "audio/mpeg",
                        "filename": "Network Track.mp3",
                        "total_bytes": 5242880,
                    }
                ],
            },
            default_folder=self.downloads,
        )
        record = DownloadRepository(self.database).get(result.record_id)
        assert record is not None
        self.assertEqual(record.filename, "Network Track.mp3")
        self.assertEqual(record.total_bytes, 5242880)
        self.assertEqual(record.mime_type, "audio/mpeg")

    def test_existing_filename_gets_safe_numeric_suffix(self) -> None:
        self.downloads.mkdir()
        (self.downloads / "file.bin").write_bytes(b"existing")
        result = enqueue_browser_download(
            self.database,
            {
                "url": "https://example.com/file.bin",
                "filename": "file.bin",
            },
            default_folder=self.downloads,
        )
        self.assertEqual(result.filename, "file (1).bin")

    def test_simultaneous_identical_requests_collapse_to_one_record(self) -> None:
        payload = {
            "url": "https://example.com/same.bin",
            "filename": "same.bin",
        }
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    enqueue_browser_download,
                    self.database,
                    payload,
                    default_folder=self.downloads,
                )
                for _index in range(2)
            ]
        results = [future.result() for future in futures]
        self.assertEqual({result.filename for result in results}, {"same.bin"})
        self.assertEqual(
            len({result.record_id for result in results}),
            1,
        )
        self.assertEqual(
            sum(1 for result in results if result.duplicate),
            1,
        )
        self.assertEqual(
            len(DownloadRepository(self.database).list_all()),
            1,
        )

    def test_completed_browser_duplicate_is_not_added_again(self) -> None:
        first = enqueue_browser_download(
            self.database,
            {
                "url": "https://example.com/release.zip?token=first",
                "filename": "release.zip",
            },
            default_folder=self.downloads,
        )
        repository = DownloadRepository(self.database)
        repository.update(first.record_id, status=DownloadStatus.COMPLETED)

        repeated = enqueue_browser_download(
            self.database,
            {
                "url": "https://example.com/release.zip?token=second",
                "filename": "release.zip",
            },
            default_folder=self.downloads,
        )

        self.assertTrue(repeated.duplicate)
        self.assertEqual(repeated.duplicate_action, "completed")
        self.assertFalse(repeated.capture_pending)
        self.assertEqual(len(repository.list_all()), 1)

    def test_interrupted_browser_duplicate_reuses_record_for_resume(self) -> None:
        first = enqueue_browser_download(
            self.database,
            {
                "url": "https://example.com/resume.bin",
                "filename": "resume.bin",
                "start_immediately": False,
            },
            default_folder=self.downloads,
        )
        repository = DownloadRepository(self.database)
        repository.update(
            first.record_id,
            downloaded_bytes=4096,
            total_bytes=8192,
            status=DownloadStatus.FAILED,
            capture_pending=False,
        )

        repeated = enqueue_browser_download(
            self.database,
            {
                "url": "https://example.com/resume.bin",
                "filename": "resume.bin",
                "start_immediately": True,
            },
            default_folder=self.downloads,
        )
        saved = repository.get(first.record_id)
        assert saved is not None
        self.assertTrue(repeated.duplicate)
        self.assertEqual(repeated.duplicate_action, "resume")
        self.assertEqual(repeated.record_id, first.record_id)
        self.assertTrue(saved.capture_pending)
        self.assertEqual(saved.downloaded_bytes, 4096)
        self.assertEqual(len(repository.list_all()), 1)

    def test_native_message_validates_action_and_url(self) -> None:
        self.assertEqual(
            handle_native_message(self.database, {"action": "ping"}),
            {"ok": True, "action": "pong"},
        )
        response = handle_native_message(
            self.database,
            {"action": "download", "url": "file:///secret.txt"},
            default_folder=self.downloads,
        )
        self.assertFalse(response["ok"])

    def test_native_message_marks_download_for_confirmation(self) -> None:
        response = handle_native_message(
            self.database,
            {
                "action": "download",
                "url": "https://example.com/confirm.bin",
            },
            default_folder=self.downloads,
        )
        self.assertTrue(response["ok"])
        self.assertTrue(response["capture_pending"])

    def test_native_message_explains_duplicate_result(self) -> None:
        payload = {
            "action": "download",
            "url": "https://example.com/duplicate.bin",
        }
        first = handle_native_message(
            self.database,
            payload,
            default_folder=self.downloads,
        )
        second = handle_native_message(
            self.database,
            payload,
            default_folder=self.downloads,
        )
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["record_id"], first["record_id"])

    def test_browser_request_migrates_legacy_database(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
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

        result = enqueue_browser_download(
            self.database,
            {"url": "https://example.com/migrated.zip"},
            default_folder=self.downloads,
        )
        record = DownloadRepository(self.database).get(result.record_id)
        assert record is not None
        self.assertEqual(record.source, "browser")
        self.assertEqual(record.connections, 4)
        self.assertTrue(record.capture_pending)

    def test_heartbeat_detects_running_and_stale_application(self) -> None:
        heartbeat = self.root / "app.heartbeat"
        heartbeat.touch()
        self.assertTrue(is_application_running(heartbeat))
        old_time = time.time() - 30
        os.utime(heartbeat, (old_time, old_time))
        self.assertFalse(
            is_application_running(heartbeat, maximum_age_seconds=8)
        )

    def test_launch_guard_allows_only_one_simultaneous_launcher(self) -> None:
        guard = self.root / "app.launching"
        self.assertTrue(acquire_launch_guard(guard))
        self.assertFalse(acquire_launch_guard(guard))
        release_launch_guard(guard)
        self.assertTrue(acquire_launch_guard(guard))

    def test_secure_session_is_validated_before_record_is_created(self) -> None:
        payload = {
            "url": "https://chatgpt.com/backend-api/files/content?id=7",
            "filename": "private.zip",
            "session_auth": {
                "enabled": True,
                "source_urls": [
                    "https://chatgpt.com/backend-api/files/content?id=7"
                ],
                "user_agent": "Mozilla/5.0",
                "cookies": [
                    {
                        "name": "session",
                        "value": "secret",
                        "domain": "chatgpt.com",
                        "path": "/",
                        "secure": True,
                        "host_only": True,
                    }
                ],
            },
        }
        captured = []
        with patch(
            "sdm.browser_bridge.store_session_auth",
            side_effect=lambda database, record_id, session: captured.append(
                (Path(database), record_id, session)
            ),
        ):
            result = enqueue_browser_download(
                self.database,
                payload,
                default_folder=self.downloads,
            )

        self.assertTrue(result.session_attached)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], self.database)
        self.assertEqual(captured[0][1], result.record_id)

    def test_secure_session_is_rejected_for_platform_extraction(self) -> None:
        response = handle_native_message(
            self.database,
            {
                "action": "download",
                "url": "https://www.youtube.com/watch?v=example",
                "media_kind": "video",
                "session_auth": {
                    "enabled": True,
                    "source_urls": [
                        "https://www.youtube.com/watch?v=example"
                    ],
                    "cookies": [
                        {
                            "name": "session",
                            "value": "secret",
                            "domain": "youtube.com",
                            "path": "/",
                            "secure": True,
                            "host_only": False,
                        }
                    ],
                },
            },
            default_folder=self.downloads,
        )
        self.assertFalse(response["ok"])
        self.assertIn("direct file", response["error"])

    def test_chatgpt_keeps_exact_request_and_stable_file_identity(self) -> None:
        request_url = (
            "https://chatgpt.com/backend-api/estuary/content?"
            "id=file_abcdef&ts=123&p=fs&sig=fresh"
        )
        payload = {
            "url": "https://cdn.example/private.zip?sig=temporary",
            "request_url": request_url,
            "source_url": request_url,
            "filename": "private.zip",
            "session_auth": {
                "enabled": True,
                "source_urls": [
                    request_url,
                    "https://cdn.example/private.zip?sig=temporary",
                ],
                "user_agent": "Mozilla/5.0",
                "cookies": [
                    {
                        "name": "session",
                        "value": "secret",
                        "domain": "chatgpt.com",
                        "path": "/",
                        "secure": True,
                        "host_only": True,
                    }
                ],
            },
        }
        with patch("sdm.browser_bridge.store_session_auth"):
            result = enqueue_browser_download(
                self.database,
                payload,
                default_folder=self.downloads,
            )
        record = DownloadRepository(self.database).get(result.record_id)
        assert record is not None
        self.assertEqual(record.url, request_url)
        self.assertEqual(
            record.source_url,
            "https://chatgpt.com/backend-api/estuary/content?"
            "id=file_abcdef",
        )
        self.assertEqual(record.site_adapter, "chatgpt")
        self.assertEqual(record.connections, 2)


if __name__ == "__main__":
    unittest.main()
