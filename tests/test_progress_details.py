from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sdm.models import DownloadRecord, DownloadStatus
from sdm.progress_details import (
    progress_action_state,
    read_connection_progress,
)
from sdm.removal import segmented_parts_path


class ConnectionProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary_directory.name)
        self.record = DownloadRecord(
            id="progress-test",
            url="https://example.com/file.bin",
            filename="file.bin",
            folder=str(self.folder),
            total_bytes=100,
            status=DownloadStatus.DOWNLOADING,
            connections=4,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_single_connection_fallback_uses_aggregate_progress(self) -> None:
        snapshot = read_connection_progress(
            self.record,
            downloaded_bytes=25,
            total_bytes=100,
        )
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0].downloaded_bytes, 25)
        self.assertEqual(snapshot[0].fraction, 0.25)
        self.assertEqual(snapshot[0].status, "Downloading")

    def test_segment_files_produce_real_connection_progress(self) -> None:
        parts = segmented_parts_path(self.record)
        parts.mkdir()
        manifest = {
            "segments": [
                {"index": 0, "start": 0, "end": 24},
                {"index": 1, "start": 25, "end": 49},
                {"index": 2, "start": 50, "end": 74},
                {"index": 3, "start": 75, "end": 99},
            ]
        }
        (parts / "manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        (parts / "segment_000.part").write_bytes(b"x" * 25)
        (parts / "segment_001.part").write_bytes(b"x" * 10)

        snapshot = read_connection_progress(self.record)

        self.assertEqual(len(snapshot), 4)
        self.assertEqual(snapshot[0].status, "Completed")
        self.assertEqual(snapshot[0].downloaded_bytes, 25)
        self.assertEqual(snapshot[1].downloaded_bytes, 10)
        self.assertEqual(snapshot[1].fraction, 0.4)
        self.assertEqual(snapshot[2].downloaded_bytes, 0)

    def test_invalid_manifest_falls_back_safely(self) -> None:
        parts = segmented_parts_path(self.record)
        parts.mkdir()
        (parts / "manifest.json").write_text("{broken", encoding="utf-8")
        snapshot = read_connection_progress(
            self.record,
            downloaded_bytes=30,
            total_bytes=100,
            status=DownloadStatus.RETRYING,
        )
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0].status, "Retrying")


class ProgressActionStateTests(unittest.TestCase):
    def test_active_download_can_pause_but_cannot_resume(self) -> None:
        for status in (
            DownloadStatus.QUEUED,
            DownloadStatus.DOWNLOADING,
            DownloadStatus.RETRYING,
        ):
            with self.subTest(status=status):
                actions = progress_action_state(status)
                self.assertTrue(actions.can_pause)
                self.assertFalse(actions.can_resume)
                self.assertFalse(actions.terminal)
                self.assertEqual(actions.cancel_label, "Cancel")

    def test_interrupted_download_can_resume(self) -> None:
        for status in (
            DownloadStatus.PAUSED,
            DownloadStatus.FAILED,
            DownloadStatus.CANCELED,
        ):
            with self.subTest(status=status):
                actions = progress_action_state(status)
                self.assertFalse(actions.can_pause)
                self.assertTrue(actions.can_resume)

    def test_failed_and_canceled_downloads_keep_close_action(self) -> None:
        for status in (
            DownloadStatus.FAILED,
            DownloadStatus.CANCELED,
        ):
            with self.subTest(status=status):
                actions = progress_action_state(status)
                self.assertTrue(actions.terminal)
                self.assertEqual(actions.cancel_label, "Close")

    def test_completed_download_cannot_pause_or_resume(self) -> None:
        actions = progress_action_state(DownloadStatus.COMPLETED)
        self.assertFalse(actions.can_pause)
        self.assertFalse(actions.can_resume)
        self.assertTrue(actions.terminal)
        self.assertEqual(actions.cancel_label, "Close")


if __name__ == "__main__":
    unittest.main()
