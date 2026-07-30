from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sdm.remote_metadata import (
    RemoteMetadata,
    enrich_download_payload,
    inspect_download_url,
    is_generic_filename,
    parse_content_disposition,
)


class _MetadataHandler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:  # noqa: N802
        if self.path == "/drive":
            self.send_response(302)
            self.send_header("Location", "/download")
            self.end_headers()
            return
        if self.path == "/download":
            self.send_response(200)
            self.send_header(
                "Content-Disposition",
                "attachment; filename*=UTF-8''YTDM-Documentation-Site.zip",
            )
            self.send_header("Content-Length", "7360")
            self.send_header("Content-Type", "application/zip")
            self.end_headers()
            return
        if self.path == "/range":
            self.send_response(405)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/download":
            self.send_response(200)
            self.send_header(
                "Content-Disposition",
                "attachment; filename*=UTF-8''YTDM-Documentation-Site.zip",
            )
            self.send_header("Content-Length", "7360")
            self.send_header("Content-Type", "application/zip")
            self.end_headers()
            return
        if self.path == "/range":
            self.send_response(206)
            self.send_header(
                "Content-Disposition",
                'attachment; filename="ChatGPT Export.pdf"',
            )
            self.send_header("Content-Range", "bytes 0-0/104857600")
            self.send_header("Content-Length", "1")
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            self.wfile.write(b"x")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


class RemoteMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _MetadataHandler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_google_drive_style_redirect_resolves_name_size_and_type(self) -> None:
        metadata = inspect_download_url(f"{self.base_url}/drive")
        self.assertEqual(metadata.filename, "YTDM-Documentation-Site.zip")
        self.assertEqual(metadata.total_bytes, 7360)
        self.assertEqual(metadata.mime_type, "application/zip")
        self.assertTrue(metadata.final_url.endswith("/download"))

    def test_range_probe_uses_content_range_total(self) -> None:
        metadata = inspect_download_url(f"{self.base_url}/range")
        self.assertEqual(metadata.filename, "ChatGPT Export.pdf")
        self.assertEqual(metadata.total_bytes, 104857600)
        self.assertEqual(metadata.mime_type, "application/pdf")

    def test_rfc5987_and_quoted_filenames_are_parsed(self) -> None:
        self.assertEqual(
            parse_content_disposition(
                "attachment; filename*=UTF-8''My%20Archive.zip"
            ),
            "My Archive.zip",
        )
        self.assertEqual(
            parse_content_disposition('attachment; filename="report.pdf"'),
            "report.pdf",
        )

    def test_generic_browser_name_is_replaced_by_server_name(self) -> None:
        payload = enrich_download_payload(
            {
                "action": "download",
                "url": "https://example.com/signed?id=1",
                "filename": "content",
                "total_bytes": 0,
                "media_kind": "direct",
            },
            inspector=lambda _url: RemoteMetadata(
                final_url="https://cdn.example.com/file",
                filename="Real Name.zip",
                total_bytes=42,
                mime_type="application/zip",
            ),
        )
        self.assertEqual(payload["filename"], "Real Name.zip")
        self.assertEqual(payload["total_bytes"], 42)
        self.assertEqual(payload["mime_type"], "application/zip")
        self.assertEqual(payload["url"], "https://cdn.example.com/file")
        self.assertTrue(is_generic_filename("download"))
        self.assertFalse(is_generic_filename("archive.zip"))

    def test_non_http_payload_is_never_inspected(self) -> None:
        calls: list[str] = []
        payload = enrich_download_payload(
            {
                "action": "download",
                "url": "file:///private.txt",
                "filename": "content",
            },
            inspector=lambda url: calls.append(url) or RemoteMetadata(),
        )
        self.assertEqual(payload["url"], "file:///private.txt")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
