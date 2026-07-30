from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from browser_host.native_host import (
    launch_application,
    process_message,
    read_native_message,
    write_native_message,
)


class NativeHostProtocolTests(unittest.TestCase):
    def test_native_message_round_trip(self) -> None:
        stream = io.BytesIO()
        payload = {"ok": True, "filename": "ملف.zip"}
        write_native_message(stream, payload)
        stream.seek(0)
        self.assertEqual(read_native_message(stream), payload)

    def test_rejects_oversized_native_message(self) -> None:
        stream = io.BytesIO(struct.pack("<I", 2 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, "size limit"):
            read_native_message(stream)

    def test_rejects_incomplete_native_message(self) -> None:
        body = json.dumps({"action": "ping"}).encode("utf-8")
        stream = io.BytesIO(struct.pack("<I", len(body) + 1) + body)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            read_native_message(stream)

    def test_browser_launch_uses_capture_only_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            pythonw = root / "pythonw.exe"
            main_path = root / "main.py"
            pythonw.touch()
            main_path.touch()
            config = {
                "pythonw_path": str(pythonw),
                "main_path": str(main_path),
                "working_directory": str(root),
            }
            with (
                patch("browser_host.native_host.sys.platform", "win32"),
                patch("browser_host.native_host.subprocess.Popen") as popen,
            ):
                self.assertTrue(launch_application(config))
            command = popen.call_args.args[0]
            self.assertEqual(command[-1], "--capture-only")

    def test_secure_session_skips_unauthenticated_metadata_probe(self) -> None:
        payload = {
            "action": "download",
            "url": "https://chatgpt.com/private/file",
            "session_auth": {"enabled": True, "cookies": [{}]},
        }
        with (
            patch(
                "browser_host.native_host.enrich_download_payload"
            ) as enrich,
            patch(
                "browser_host.native_host.handle_native_message",
                return_value={"ok": False, "error": "test boundary"},
            ) as handle,
        ):
            process_message(payload, {"database_path": "test.db"})

        enrich.assert_not_called()
        forwarded = handle.call_args.args[1]
        self.assertEqual(forwarded["url"], payload["url"])
        self.assertEqual(forwarded["session_auth"], payload["session_auth"])
        self.assertEqual(forwarded["source_url"], payload["url"])

    def test_original_source_survives_metadata_redirect_enrichment(self) -> None:
        payload = {
            "action": "download",
            "url": "https://drive.google.com/uc?id=stable",
        }
        signed_url = "https://signed.example/file?sig=temporary"
        with (
            patch(
                "browser_host.native_host.enrich_download_payload",
                side_effect=lambda incoming: {
                    **incoming,
                    "url": signed_url,
                    "filename": "file.zip",
                },
            ),
            patch(
                "browser_host.native_host.handle_native_message",
                return_value={"ok": False, "error": "test boundary"},
            ) as handle,
        ):
            process_message(payload, {"database_path": "test.db"})

        forwarded = handle.call_args.args[1]
        self.assertEqual(forwarded["url"], signed_url)
        self.assertEqual(
            forwarded["source_url"],
            "https://drive.google.com/uc?id=stable",
        )


if __name__ == "__main__":
    unittest.main()
