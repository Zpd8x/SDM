from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from browser_host.native_host import process_message
from sdm.browser_bridge import handle_native_message


class BrowserIntegrationV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "downloads.db"
        self.folder = self.root / "Downloads"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ping_advertises_protocol_v2_capabilities(self) -> None:
        response = handle_native_message(self.database, {"action": "ping"})
        self.assertTrue(response["ok"])
        self.assertEqual(response, {"ok": True, "action": "pong"})

    def test_batch_download_accepts_multiple_links(self) -> None:
        response = handle_native_message(
            self.database,
            {
                "action": "batch_download",
                "items": [
                    {"url": "https://example.com/a.zip", "filename": "a.zip"},
                    {"url": "https://example.com/b.zip", "filename": "b.zip"},
                ],
            },
            default_folder=self.folder,
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["accepted"], 2)
        self.assertEqual(len(response["results"]), 2)

    def test_batch_download_reports_partial_failure(self) -> None:
        response = handle_native_message(
            self.database,
            {
                "action": "batch_download",
                "items": [
                    {"url": "https://example.com/good.zip"},
                    {"url": "file:///unsafe.zip"},
                ],
            },
            default_folder=self.folder,
        )
        self.assertFalse(response["ok"])
        self.assertTrue(response["partial"])
        self.assertEqual(response["accepted"], 1)
        self.assertEqual(response["failed"], 1)

    def test_browser_status_returns_queue_counts(self) -> None:
        handle_native_message(
            self.database,
            {"action": "download", "url": "https://example.com/q.bin"},
            default_folder=self.folder,
        )
        response = handle_native_message(
            self.database, {"action": "browser_status"}
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["protocol_version"], 2)
        self.assertIn("batch_download", response["capabilities"])
        self.assertGreaterEqual(response["queued"], 1)

    def test_native_host_echoes_persistent_request_id(self) -> None:
        with patch(
            "browser_host.native_host.handle_native_message",
            return_value={"ok": True, "action": "pong"},
        ):
            response = process_message(
                {"action": "ping", "request_id": 77},
                {"database_path": str(self.database)},
            )
        self.assertEqual(response["request_id"], 77)

    def test_extension_manifest_is_v200(self) -> None:
        manifest = json.loads(
            (Path(__file__).parents[1] / "browser_extension" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], "2.0.0")
        self.assertIn("nativeMessaging", manifest["permissions"])


if __name__ == "__main__":
    unittest.main()
