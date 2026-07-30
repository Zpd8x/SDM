from __future__ import annotations

import http.client
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable

from sdm.bandwidth import BandwidthLimiter
from sdm.config import USER_AGENT
from sdm.models import DownloadRecord, DownloadStatus
from sdm.retry_policy import is_rate_limited, retry_delay_seconds
from sdm.session_auth import (
    BrowserSession,
    open_session_url,
    session_user_agent,
)


ProgressCallback = Callable[[int, int, float, int | None], None]
StatusCallback = Callable[[DownloadStatus, str], None]
MetadataCallback = Callable[[int, str, str], None]


class DownloadError(RuntimeError):
    """A recoverable or final download error."""


class DownloadCancelled(RuntimeError):
    """Raised when a user or application stops an active transfer."""


@dataclass(frozen=True, slots=True)
class DownloadResult:
    final_path: Path
    downloaded_bytes: int
    total_bytes: int


class DownloadControl:
    """Thread-safe pause, resume, and cancel controls."""

    def __init__(self) -> None:
        self._run_event = threading.Event()
        self._run_event.set()
        self._cancel_event = threading.Event()
        self._response_lock = threading.Lock()
        self._active_responses: set = set()

    @property
    def is_paused(self) -> bool:
        return not self._run_event.is_set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def pause(self) -> None:
        self._run_event.clear()

    def resume(self) -> None:
        self._run_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._run_event.set()
        self.close_active_responses()

    def close_active_responses(self) -> None:
        with self._response_lock:
            responses = tuple(self._active_responses)
        for response in responses:
            try:
                response.close()
            except OSError:
                pass

    def bind_response(self, response) -> None:
        with self._response_lock:
            self._active_responses.add(response)

    def release_response(self, response) -> None:
        with self._response_lock:
            self._active_responses.discard(response)

    def wait_until_running(self) -> None:
        while not self._run_event.wait(timeout=0.1):
            if self.is_cancelled:
                raise DownloadCancelled("Download canceled.")
        if self.is_cancelled:
            raise DownloadCancelled("Download canceled.")


class DownloadEngine:
    def __init__(
        self,
        *,
        chunk_size: int = 256 * 1024,
        timeout: float = 30.0,
        max_retries: int = 3,
        bandwidth_limiter: BandwidthLimiter | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.max_retries = max_retries
        self.bandwidth_limiter = bandwidth_limiter

    def download(
        self,
        record: DownloadRecord,
        control: DownloadControl,
        *,
        on_progress: ProgressCallback | None = None,
        on_status: StatusCallback | None = None,
        on_metadata: MetadataCallback | None = None,
        session: BrowserSession | None = None,
    ) -> DownloadResult:
        progress_callback = on_progress or (lambda *_: None)
        status_callback = on_status or (lambda *_: None)
        metadata_callback = on_metadata or (lambda *_: None)

        final_path = record.final_path
        part_path = record.temporary_path
        final_path.parent.mkdir(parents=True, exist_ok=True)

        if final_path.exists():
            raise DownloadError(
                f"A file with this name already exists: {final_path.name}"
            )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            control.wait_until_running()

            try:
                return self._download_once(
                    record,
                    final_path,
                    part_path,
                    control,
                    progress_callback,
                    metadata_callback,
                    session,
                )
            except DownloadCancelled:
                raise
            except (
                DownloadError,
                urllib.error.URLError,
                http.client.HTTPException,
                socket.timeout,
                TimeoutError,
                OSError,
            ) as error:
                if control.is_cancelled:
                    raise DownloadCancelled("Download canceled.") from error
                last_error = error
                if attempt >= self.max_retries:
                    break
                delay = retry_delay_seconds(error, attempt)
                if is_rate_limited(error):
                    message = (
                        "Server rate limit; waiting "
                        f"{delay:.0f}s before retry "
                        f"{attempt + 1}/{self.max_retries}"
                    )
                else:
                    message = (
                        f"Retry {attempt + 1}/{self.max_retries} "
                        f"after {delay:.0f}s"
                    )
                status_callback(DownloadStatus.RETRYING, message)
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                end_time = time.monotonic() + delay
                while time.monotonic() < end_time:
                    control.wait_until_running()
                    time.sleep(0.1)

        message = str(last_error) if last_error else "Download failed."
        raise DownloadError(message) from last_error

    def _download_once(
        self,
        record: DownloadRecord,
        final_path: Path,
        part_path: Path,
        control: DownloadControl,
        on_progress: ProgressCallback,
        on_metadata: MetadataCallback,
        session: BrowserSession | None,
    ) -> DownloadResult:
        offset = part_path.stat().st_size if part_path.exists() else 0
        headers = {
            "User-Agent": session_user_agent(session, USER_AGENT),
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if record.referer:
            headers["Referer"] = record.referer
        if offset:
            headers["Range"] = f"bytes={offset}-"
            validator = record.etag or record.last_modified
            if validator:
                headers["If-Range"] = validator

        request = urllib.request.Request(record.url, headers=headers, method="GET")
        try:
            response = open_session_url(
                request,
                session=session,
                timeout=self.timeout,
            )
        except urllib.error.HTTPError as error:
            if error.code == 416 and offset:
                total = self._total_from_content_range(error.headers) or offset
                if offset == total:
                    os.replace(part_path, final_path)
                    on_progress(total, total, 0.0, 0)
                    return DownloadResult(final_path, total, total)
            if is_rate_limited(error):
                raise
            raise DownloadError(f"HTTP error {error.code}: {error.reason}") from error

        control.bind_response(response)
        try:
            status_code = int(response.getcode() or 0)
            if status_code not in {200, 206}:
                raise DownloadError(f"Unexpected HTTP status: {status_code}")

            if offset and status_code == 200:
                offset = 0
                write_mode = "wb"
            else:
                write_mode = "ab" if offset else "wb"

            total_bytes = self._resolve_total_size(
                response.headers,
                status_code=status_code,
                offset=offset,
            )
            etag = response.headers.get("ETag", "")
            last_modified = response.headers.get("Last-Modified", "")
            on_metadata(total_bytes, etag, last_modified)

            downloaded = offset
            started_at = time.monotonic()
            last_report_at = started_at
            last_reported_bytes = downloaded
            on_progress(downloaded, total_bytes, 0.0, None)

            with part_path.open(write_mode) as destination:
                downloaded = self._stream_response(
                    response=response,
                    destination=destination,
                    control=control,
                    downloaded=downloaded,
                    total_bytes=total_bytes,
                    started_at=started_at,
                    last_report_at=last_report_at,
                    last_reported_bytes=last_reported_bytes,
                    on_progress=on_progress,
                )

            if total_bytes and downloaded < total_bytes:
                raise DownloadError(
                    f"Connection ended early ({downloaded}/{total_bytes} bytes)."
                )
            if total_bytes and downloaded > total_bytes:
                raise DownloadError(
                    f"Received more data than expected ({downloaded}/{total_bytes})."
                )

            if final_path.exists():
                raise DownloadError(
                    f"A file with this name already exists: {final_path.name}"
                )
            os.replace(part_path, final_path)
            final_total = total_bytes or downloaded
            on_progress(downloaded, final_total, 0.0, 0)
            return DownloadResult(final_path, downloaded, final_total)
        finally:
            control.release_response(response)
            response.close()

    def _stream_response(
        self,
        *,
        response,
        destination: BinaryIO,
        control: DownloadControl,
        downloaded: int,
        total_bytes: int,
        started_at: float,
        last_report_at: float,
        last_reported_bytes: int,
        on_progress: ProgressCallback,
    ) -> int:
        del started_at
        current_speed = 0.0

        while True:
            control.wait_until_running()
            try:
                chunk = response.read(self.chunk_size)
            except (ValueError, AttributeError) as error:
                if control.is_cancelled:
                    raise DownloadCancelled("Download canceled.") from error
                raise

            if not chunk:
                break
            if self.bandwidth_limiter is not None:
                self.bandwidth_limiter.throttle(
                    len(chunk),
                    control.wait_until_running,
                )
            destination.write(chunk)
            downloaded += len(chunk)

            now = time.monotonic()
            interval = now - last_report_at
            if interval >= 0.25:
                current_speed = (downloaded - last_reported_bytes) / interval
                remaining = max(0, total_bytes - downloaded)
                eta = (
                    int(remaining / current_speed)
                    if total_bytes > 0 and current_speed > 0
                    else None
                )
                on_progress(downloaded, total_bytes, current_speed, eta)
                last_report_at = now
                last_reported_bytes = downloaded

        if downloaded != last_reported_bytes:
            remaining = max(0, total_bytes - downloaded)
            eta = (
                int(remaining / current_speed)
                if total_bytes > 0 and current_speed > 0
                else 0 if total_bytes and remaining == 0 else None
            )
            on_progress(downloaded, total_bytes, current_speed, eta)
        return downloaded

    @staticmethod
    def _total_from_content_range(headers) -> int:
        content_range = headers.get("Content-Range", "")
        match = re.search(r"/(\d+)$", content_range)
        return int(match.group(1)) if match else 0

    @classmethod
    def _resolve_total_size(
        cls,
        headers,
        *,
        status_code: int,
        offset: int,
    ) -> int:
        range_total = cls._total_from_content_range(headers)
        if range_total:
            return range_total

        content_length = headers.get("Content-Length", "")
        try:
            length = int(content_length)
        except (TypeError, ValueError):
            return 0
        if status_code == 206:
            return offset + length
        return length
