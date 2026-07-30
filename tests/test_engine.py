from __future__ import annotations

import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sdm.engine import DownloadCancelled, DownloadControl, DownloadEngine
from sdm.models import DownloadRecord, DownloadStatus
from sdm.segmented_engine import SmartDownloadEngine
from sdm.session_auth import BrowserSession, SessionCookie


PAYLOAD = bytes(range(256)) * 4096


class RangeRequestHandler(BaseHTTPRequestHandler):
    payload = PAYLOAD
    range_headers: list[str] = []
    referer_headers: list[str] = []
    cookie_headers: list[str] = []
    requests_seen: list[tuple[str, str]] = []
    state_lock = threading.Lock()
    probe_rate_limits_remaining = 1
    segment_rate_limits_remaining = 1

    def do_GET(self) -> None:
        range_header = self.headers.get("Range", "")
        type(self).range_headers.append(range_header)
        type(self).referer_headers.append(self.headers.get("Referer", ""))
        type(self).cookie_headers.append(self.headers.get("Cookie", ""))
        type(self).requests_seen.append(
            (self.path, self.headers.get("Cookie", ""))
        )

        if self.path.startswith("/redirect-cross-domain"):
            _host, port = self.server.server_address
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://localhost:{port}/redirect-target.bin",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if (
            self.path.startswith("/private")
            and self.headers.get("Cookie", "") != "session=allowed"
        ):
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        should_rate_limit = False
        with type(self).state_lock:
            if (
                self.path.startswith("/probe-rate-limit")
                and type(self).probe_rate_limits_remaining > 0
            ):
                type(self).probe_rate_limits_remaining -= 1
                should_rate_limit = True
            elif (
                self.path.startswith("/segment-rate-limit")
                and range_header != "bytes=0-0"
                and type(self).segment_rate_limits_remaining > 0
            ):
                type(self).segment_rate_limits_remaining -= 1
                should_rate_limit = True
        if should_rate_limit:
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        ignore_range = self.path.startswith("/ignore-range")
        if range_header.startswith("bytes=") and not ignore_range:
            range_value = range_header.removeprefix("bytes=")
            start_text, end_text = range_value.split("-", 1)
            start = int(start_text)
            if start >= len(self.payload):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(self.payload)}")
                self.end_headers()
                return
            end = int(end_text) if end_text else len(self.payload) - 1
            end = min(end, len(self.payload) - 1)
            body = self.payload[start : end + 1]
            self.send_response(206)
            self.send_header(
                "Content-Range",
                f"bytes {start}-{end}/{len(self.payload)}",
            )
        else:
            body = self.payload
            self.send_response(200)

        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", '"sdm-test-etag"')
        self.end_headers()
        for index in range(0, len(body), 16 * 1024):
            if self.path.startswith("/slow"):
                time.sleep(0.04)
            try:
                self.wfile.write(body[index : index + 16 * 1024])
            except (BrokenPipeError, ConnectionResetError):
                break

    def log_message(self, _format: str, *_args) -> None:
        return


class DownloadEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        RangeRequestHandler.range_headers.clear()
        RangeRequestHandler.referer_headers.clear()
        RangeRequestHandler.cookie_headers.clear()
        RangeRequestHandler.requests_seen.clear()
        RangeRequestHandler.probe_rate_limits_remaining = 1
        RangeRequestHandler.segment_rate_limits_remaining = 1
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RangeRequestHandler)
        cls.server.daemon_threads = True
        cls.server_thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.server_thread.start()
        host, port = cls.server.server_address
        cls.url = f"http://{host}:{port}/test.bin"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def _record(
        self,
        folder: str,
        filename: str,
        *,
        url: str | None = None,
    ) -> DownloadRecord:
        return DownloadRecord(
            id="test-download",
            url=url or self.url,
            filename=filename,
            folder=folder,
        )

    def test_complete_download(self) -> None:
        with TemporaryDirectory() as folder:
            record = self._record(folder, "complete.bin")
            progress_events: list[tuple[int, int]] = []
            result = DownloadEngine(max_retries=0).download(
                record,
                DownloadControl(),
                on_progress=lambda downloaded, total, _speed, _eta: (
                    progress_events.append((downloaded, total))
                ),
            )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            self.assertFalse(record.temporary_path.exists())
            self.assertEqual(result.total_bytes, len(PAYLOAD))
            self.assertEqual(progress_events[-1], (len(PAYLOAD), len(PAYLOAD)))

    def test_browser_referer_is_sent_with_direct_transfer(self) -> None:
        with TemporaryDirectory() as folder:
            record = self._record(folder, "referer.bin")
            record.referer = "https://music.example/player"
            DownloadEngine(max_retries=0).download(
                record,
                DownloadControl(),
            )
            self.assertIn(
                "https://music.example/player",
                RangeRequestHandler.referer_headers,
            )

    def test_secure_browser_session_supports_segmented_downloads(self) -> None:
        with TemporaryDirectory() as folder:
            host, port = self.server.server_address
            url = f"http://{host}:{port}/private.bin"
            record = self._record(folder, "private.bin", url=url)
            record.connections = 4
            now = time.time()
            session = BrowserSession(
                cookies=(
                    SessionCookie(
                        name="session",
                        value="allowed",
                        domain=host,
                        path="/",
                        secure=False,
                        host_only=True,
                    ),
                ),
                source_urls=(url,),
                user_agent="SDM Browser Session Test",
                created_at=now,
                expires_at=now + 3600,
            )

            result = SmartDownloadEngine(max_retries=0).download(
                record,
                DownloadControl(),
                session=session,
            )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            self.assertGreaterEqual(
                RangeRequestHandler.cookie_headers.count("session=allowed"),
                2,
            )

    def test_session_cookie_is_removed_on_cross_domain_redirect(self) -> None:
        with TemporaryDirectory() as folder:
            host, port = self.server.server_address
            url = f"http://{host}:{port}/redirect-cross-domain.bin"
            record = self._record(folder, "redirected.bin", url=url)
            record.connections = 1
            now = time.time()
            session = BrowserSession(
                cookies=(
                    SessionCookie(
                        name="session",
                        value="allowed",
                        domain=host,
                        path="/",
                        secure=False,
                        host_only=True,
                    ),
                ),
                source_urls=(url,),
                user_agent="SDM Redirect Test",
                created_at=now,
                expires_at=now + 3600,
            )

            result = SmartDownloadEngine(max_retries=0).download(
                record,
                DownloadControl(),
                session=session,
            )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            redirected_requests = [
                cookie
                for path, cookie in RangeRequestHandler.requests_seen
                if path.startswith("/redirect-target")
            ]
            self.assertTrue(redirected_requests)
            self.assertEqual(set(redirected_requests), {""})

    def test_resume_from_partial_file(self) -> None:
        with TemporaryDirectory() as folder:
            record = self._record(folder, "resume.bin")
            partial_size = 225_000
            record.temporary_path.write_bytes(PAYLOAD[:partial_size])

            result = DownloadEngine(max_retries=0).download(
                record,
                DownloadControl(),
            )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            self.assertIn(
                f"bytes={partial_size}-",
                RangeRequestHandler.range_headers,
            )

    def test_restart_safely_when_server_ignores_range(self) -> None:
        with TemporaryDirectory() as folder:
            host, port = self.server.server_address
            record = self._record(
                folder,
                "range-ignored.bin",
                url=f"http://{host}:{port}/ignore-range.bin",
            )
            record.temporary_path.write_bytes(PAYLOAD[:100_000])

            result = DownloadEngine(max_retries=0).download(
                record,
                DownloadControl(),
            )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)

    def test_paused_download_waits_until_resumed(self) -> None:
        with TemporaryDirectory() as folder:
            record = self._record(folder, "paused.bin")
            control = DownloadControl()
            control.pause()
            failures: list[Exception] = []

            def run_download() -> None:
                try:
                    DownloadEngine(max_retries=0).download(record, control)
                except Exception as error:
                    failures.append(error)

            thread = threading.Thread(target=run_download)
            thread.start()
            time.sleep(0.2)
            self.assertTrue(thread.is_alive())

            control.resume()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual((Path(folder) / "paused.bin").read_bytes(), PAYLOAD)

    def test_segmented_download_uses_four_connections(self) -> None:
        with TemporaryDirectory() as folder:
            record = self._record(folder, "segmented.bin")
            record.connections = 4
            modes: list[tuple[str, int]] = []

            result = SmartDownloadEngine(max_retries=0).download(
                record,
                DownloadControl(),
                on_mode=lambda mode, count: modes.append((mode, count)),
            )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            self.assertIn(("Adaptive 4/4", 4), modes)
            self.assertFalse(
                SmartDownloadEngine.part_directory(record).exists()
            )

    def test_segment_boundaries_cover_every_byte_once(self) -> None:
        segments = SmartDownloadEngine.build_segments(10, 3)
        self.assertEqual(
            [(segment.start, segment.end) for segment in segments],
            [(0, 3), (4, 6), (7, 9)],
        )
        self.assertEqual(sum(segment.length for segment in segments), 10)

    def test_segmented_download_resumes_saved_parts(self) -> None:
        with TemporaryDirectory() as folder:
            host, port = self.server.server_address
            record = self._record(
                folder,
                "segmented-resume.bin",
                url=f"http://{host}:{port}/slow.bin",
            )
            record.connections = 4
            first_control = DownloadControl()
            engine = SmartDownloadEngine(
                chunk_size=16 * 1024,
                max_retries=0,
            )

            def cancel_after_progress(
                downloaded: int,
                _total: int,
                _speed: float,
                _eta: int | None,
            ) -> None:
                if downloaded >= 200_000 and not first_control.is_cancelled:
                    first_control.cancel()

            with self.assertRaises(DownloadCancelled):
                engine.download(
                    record,
                    first_control,
                    on_progress=cancel_after_progress,
                )

            part_directory = SmartDownloadEngine.part_directory(record)
            partial_size = sum(
                path.stat().st_size
                for path in part_directory.glob("segment_*.part")
            )
            self.assertGreater(partial_size, 0)
            self.assertLess(partial_size, len(PAYLOAD))

            record.adaptive_connections = 1
            prepared_segment_counts: list[int] = []
            original_prepare = engine._prepare_part_directory

            def capture_segments(part_directory, item, probe, segments):
                prepared_segment_counts.append(len(segments))
                return original_prepare(
                    part_directory,
                    item,
                    probe,
                    segments,
                )

            with patch.object(
                engine,
                "_prepare_part_directory",
                side_effect=capture_segments,
            ):
                result = engine.download(
                    record,
                    DownloadControl(),
                )
            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            self.assertEqual(prepared_segment_counts, [4])
            self.assertFalse(part_directory.exists())

    def test_smart_engine_falls_back_without_range_support(self) -> None:
        with TemporaryDirectory() as folder:
            host, port = self.server.server_address
            record = self._record(
                folder,
                "single-fallback.bin",
                url=f"http://{host}:{port}/ignore-range.bin",
            )
            record.connections = 8
            modes: list[tuple[str, int]] = []

            result = SmartDownloadEngine(max_retries=0).download(
                record,
                DownloadControl(),
                on_mode=lambda mode, count: modes.append((mode, count)),
            )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            self.assertEqual(modes, [("Single • no Range support", 1)])

    def test_probe_retries_after_server_rate_limit(self) -> None:
        with TemporaryDirectory() as folder:
            host, port = self.server.server_address
            record = self._record(
                folder,
                "probe-rate-limit.bin",
                url=f"http://{host}:{port}/probe-rate-limit.bin",
            )
            record.connections = 1
            statuses: list[tuple[DownloadStatus, str]] = []
            engine = SmartDownloadEngine(max_retries=1)

            with patch.object(engine, "_wait_for_retry", return_value=None):
                result = engine.download(
                    record,
                    DownloadControl(),
                    on_status=lambda status, message: statuses.append(
                        (status, message)
                    ),
                )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            self.assertTrue(
                any(
                    status == DownloadStatus.RETRYING
                    and "rate limit" in message.lower()
                    for status, message in statuses
                )
            )
    def test_segment_retries_after_server_rate_limit(self) -> None:
        with TemporaryDirectory() as folder:
            host, port = self.server.server_address
            record = self._record(
                folder,
                "segment-rate-limit.bin",
                url=f"http://{host}:{port}/segment-rate-limit.bin",
            )
            record.connections = 4
            statuses: list[tuple[DownloadStatus, str]] = []
            adaptive_events = []
            engine = SmartDownloadEngine(max_retries=1)

            with patch.object(engine, "_wait_for_retry", return_value=None):
                result = engine.download(
                    record,
                    DownloadControl(),
                    on_status=lambda status, message: statuses.append(
                        (status, message)
                    ),
                    on_adaptive=adaptive_events.append,
                )

            self.assertEqual(result.final_path.read_bytes(), PAYLOAD)
            self.assertTrue(
                any(
                    status == DownloadStatus.RETRYING
                    and "rate limited" in message.lower()
                    for status, message in statuses
                )
            )
            self.assertTrue(
                any(event.kind == "rate_limit" for event in adaptive_events)
            )


if __name__ == "__main__":
    unittest.main()
