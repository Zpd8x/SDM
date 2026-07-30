from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from sdm.browser_bridge import enqueue_browser_download
from sdm.database import DownloadRepository
from sdm.models import DownloadRecord
from sdm.session_auth import BrowserSession
from sdm.segmented_engine import DownloadProbe, SmartDownloadEngine
from sdm.site_adapters import (
    ADAPTER_CHATGPT,
    ADAPTER_DIRECT,
    ADAPTER_DROPBOX,
    ADAPTER_GOOGLE_DRIVE,
    ADAPTER_ONEDRIVE,
    SiteAdapterError,
    build_adapter_plan,
    canonical_source_url,
    detect_site_adapter,
    has_expiring_signature,
    is_stale_link_error,
    onedrive_api_content_url,
    resolve_site_url,
)


class _Response:
    def __init__(self, url: str, headers: dict[str, str]) -> None:
        self._url = url
        self.headers = headers
        self.closed = False

    def geturl(self) -> str:
        return self._url

    def close(self) -> None:
        self.closed = True


class SiteAdapterTests(unittest.TestCase):
    def test_adapter_detection_covers_cloud_and_private_file_sites(self) -> None:
        cases = {
            "https://drive.google.com/file/d/abc12345/view": (
                ADAPTER_GOOGLE_DRIVE
            ),
            "https://www.dropbox.com/scl/fi/a/file.zip?dl=0": (
                ADAPTER_DROPBOX
            ),
            "https://1drv.ms/u/s!example": ADAPTER_ONEDRIVE,
            (
                "https://chatgpt.com/backend-api/estuary/"
                "content?id=file_abcdef"
            ): ADAPTER_CHATGPT,
            "https://example.com/file.zip": ADAPTER_DIRECT,
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(detect_site_adapter(url), expected)

    def test_google_drive_links_are_reduced_to_a_stable_file_identity(self) -> None:
        source = canonical_source_url(
            "https://drive.google.com/file/d/AbC_123456/view?usp=sharing"
        )
        self.assertEqual(
            source,
            "https://drive.google.com/uc?export=download&id=AbC_123456",
        )

    def test_dropbox_and_onedrive_force_download_mode(self) -> None:
        dropbox = canonical_source_url(
            "https://www.dropbox.com/scl/fi/key/report.pdf?rlkey=abc&dl=0"
        )
        onedrive = canonical_source_url(
            "https://1drv.ms/u/s!example?e=123"
        )
        self.assertIn("rlkey=abc", dropbox)
        self.assertIn("dl=1", dropbox)
        self.assertIn("download=1", onedrive)
        self.assertTrue(
            onedrive_api_content_url("https://1drv.ms/u/s!example").startswith(
                "https://api.onedrive.com/v1.0/shares/u!"
            )
        )

    def test_chatgpt_source_drops_temporary_query_fields(self) -> None:
        source = canonical_source_url(
            "https://chatgpt.com/backend-api/estuary/content?"
            "id=file_abcdef123&download_token=temporary&sig=secret"
        )
        self.assertEqual(
            source,
            "https://chatgpt.com/backend-api/estuary/content?"
            "id=file_abcdef123",
        )

    def test_chatgpt_keeps_endpoint_path_and_uses_page_origin_fallback(
        self,
    ) -> None:
        source = canonical_source_url(
            "https://chatgpt.com/backend-api/files/content?"
            "id=file_abcdef123&sig=temporary"
        )
        self.assertEqual(
            source,
            "https://chatgpt.com/backend-api/files/content?"
            "id=file_abcdef123",
        )
        plan = build_adapter_plan(
            "https://cdn.example/file.zip?sig=temporary",
            source_url="https://cdn.example/file.zip?sig=temporary",
            page_url="https://chatgpt.com/c/conversation-id",
        )
        self.assertEqual(plan.adapter, ADAPTER_CHATGPT)
        self.assertEqual(plan.connection_limit, 2)

    def test_cloud_adapters_use_cautious_connection_limits(self) -> None:
        drive = build_adapter_plan(
            "https://drive.google.com/file/d/AbC_123456/view"
        )
        chatgpt = build_adapter_plan(
            "https://chatgpt.com/backend-api/estuary/"
            "content?id=file_abcdef"
        )
        direct = build_adapter_plan("https://example.com/file.bin")
        self.assertEqual(drive.connection_limit, 4)
        self.assertEqual(chatgpt.connection_limit, 2)
        self.assertEqual(direct.connection_limit, 16)

    def test_signature_and_stale_error_detection(self) -> None:
        self.assertTrue(
            has_expiring_signature(
                "https://cdn.example/file?X-Amz-Signature=abc"
            )
        )
        self.assertFalse(
            has_expiring_signature("https://example.com/file?id=1")
        )
        self.assertTrue(is_stale_link_error(RuntimeError("HTTP error 403")))
        self.assertFalse(is_stale_link_error(RuntimeError("HTTP error 500")))

    def test_resolution_follows_redirect_and_extracts_metadata(self) -> None:
        response = _Response(
            "https://cdn.example/report.zip?sig=fresh",
            {
                "Content-Disposition": 'attachment; filename="report.zip"',
                "Content-Range": "bytes 0-0/4096",
                "Content-Type": "application/zip",
            },
        )
        with patch(
            "sdm.site_adapters.open_session_url",
            return_value=response,
        ):
            resolved = resolve_site_url(
                "https://www.dropbox.com/scl/fi/key/report.zip?dl=0",
            )
        self.assertEqual(resolved.url, response.geturl())
        self.assertEqual(resolved.filename, "report.zip")
        self.assertEqual(resolved.total_bytes, 4096)
        self.assertEqual(resolved.mime_type, "application/zip")
        self.assertTrue(response.closed)

    def test_html_landing_page_is_not_cached_as_a_signed_file(self) -> None:
        response = _Response(
            "https://accounts.example/login",
            {"Content-Type": "text/html", "Content-Length": "100"},
        )
        source = "https://1drv.ms/u/s!example"
        with patch(
            "sdm.site_adapters.open_session_url",
            return_value=response,
        ):
            resolved = resolve_site_url(source)
        self.assertIn("download=1", resolved.url)
        self.assertNotIn("accounts.example", resolved.url)

    def test_chatgpt_resolution_requires_the_secure_session(self) -> None:
        with self.assertRaisesRegex(SiteAdapterError, "Secure Browser Session"):
            resolve_site_url(
                "https://chatgpt.com/backend-api/estuary/"
                "content?id=file_abcdef"
            )

    def test_chatgpt_uses_the_exact_browser_request_before_stable_fallback(
        self,
    ) -> None:
        preferred = (
            "https://chatgpt.com/backend-api/estuary/content?"
            "id=file_abcdef&ts=123&p=fs&sig=fresh"
        )
        stable = (
            "https://chatgpt.com/backend-api/estuary/content?"
            "id=file_abcdef"
        )
        response = _Response(
            "https://cdn.example/report.zip?sig=resolved",
            {
                "Content-Disposition": 'attachment; filename="report.zip"',
                "Content-Range": "bytes 0-0/4096",
                "Content-Type": "application/zip",
            },
        )
        expired = HTTPError(preferred, 403, "Forbidden", {}, None)
        session = BrowserSession(
            cookies=(),
            source_urls=(preferred,),
            user_agent="Browser UA",
            created_at=1,
            expires_at=9999999999,
        )
        with patch(
            "sdm.site_adapters.open_session_url",
            side_effect=[expired, response],
        ) as opener:
            resolved = resolve_site_url(
                stable,
                adapter=ADAPTER_CHATGPT,
                session=session,
                preferred_url=preferred,
            )
        requested_urls = [
            call.args[0].full_url for call in opener.call_args_list
        ]
        self.assertEqual(requested_urls, [preferred, stable])
        self.assertEqual(resolved.url, response.geturl())
        self.assertEqual(resolved.source_url, stable)

    def test_browser_bridge_persists_adapter_and_caps_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = enqueue_browser_download(
                root / "downloads.db",
                {
                    "url": (
                        "https://drive.google.com/file/d/"
                        "AbC_123456/view"
                    ),
                    "filename": "report.zip",
                    "connections": 16,
                },
                default_folder=root / "Downloads",
            )
            record = DownloadRepository(root / "downloads.db").get(
                result.record_id
            )
        assert record is not None
        self.assertEqual(record.site_adapter, ADAPTER_GOOGLE_DRIVE)
        self.assertIn("id=AbC_123456", record.source_url)
        self.assertEqual(record.connections, 2)
        self.assertIn("Google Drive files", record.rule_reason)
        self.assertEqual(result.adapter_label, "Google Drive")

    def test_legacy_database_gains_adapter_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = DownloadRepository(
                Path(temporary_directory) / "downloads.db"
            )
            record = repository.create_download(
                url="https://example.com/file.bin",
                filename="file.bin",
                folder=temporary_directory,
            )
            saved = repository.get(record.id)
        assert saved is not None
        self.assertEqual(saved.site_adapter, ADAPTER_DIRECT)
        self.assertEqual(saved.source_url, "https://example.com/file.bin")

    def test_new_signed_url_keeps_segments_for_the_same_stable_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            record = DownloadRecord(
                id="stable",
                url="https://cdn.example/file?sig=first",
                filename="file.bin",
                folder=str(root),
                total_bytes=8,
                source_url="https://drive.google.com/uc?export=download&id=stable",
                site_adapter=ADAPTER_GOOGLE_DRIVE,
            )
            engine = SmartDownloadEngine(minimum_segment_size=1)
            probe = DownloadProbe(total_bytes=8, supports_ranges=True)
            segments = engine.build_segments(8, 2)
            part_directory = engine.part_directory(record)
            engine._prepare_part_directory(
                part_directory,
                record,
                probe,
                segments,
            )
            first_part = engine.segment_path(part_directory, segments[0])
            first_part.write_bytes(b"1234")

            record.url = "https://cdn.example/file?sig=second"
            engine._prepare_part_directory(
                part_directory,
                record,
                probe,
                segments,
            )
            self.assertEqual(first_part.read_bytes(), b"1234")


if __name__ == "__main__":
    unittest.main()
