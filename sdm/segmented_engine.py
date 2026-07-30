from __future__ import annotations

import json
import os
import re
import shutil
import socket
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from sdm.adaptive_connections import (
    AdaptiveConnectionController,
    AdaptiveConnectionEvent,
)
from sdm.bandwidth import BandwidthLimiter
from sdm.config import USER_AGENT
from sdm.engine import (
    DownloadCancelled,
    DownloadControl,
    DownloadEngine,
    DownloadError,
    DownloadResult,
    MetadataCallback,
    ProgressCallback,
    StatusCallback,
)
from sdm.models import DownloadRecord, DownloadStatus
from sdm.retry_policy import is_rate_limited, retry_delay_seconds
from sdm.session_auth import (
    BrowserSession,
    open_session_url,
    session_user_agent,
)


ModeCallback = Callable[[str, int], None]
AdaptiveCallback = Callable[[AdaptiveConnectionEvent], None]


@dataclass(frozen=True, slots=True)
class DownloadProbe:
    total_bytes: int
    supports_ranges: bool
    etag: str = ""
    last_modified: str = ""


@dataclass(frozen=True, slots=True)
class Segment:
    index: int
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


class SegmentAborted(RuntimeError):
    pass


class ProgressAggregator:
    def __init__(
        self,
        *,
        initial_bytes: int,
        total_bytes: int,
        callback: ProgressCallback,
    ) -> None:
        self._downloaded = initial_bytes
        self._total = total_bytes
        self._callback = callback
        self._lock = threading.Lock()
        self._last_report_at = time.monotonic()
        self._last_reported_bytes = initial_bytes
        self._callback(initial_bytes, total_bytes, 0.0, None)

    def add(self, byte_count: int) -> None:
        with self._lock:
            self._downloaded += byte_count
            now = time.monotonic()
            interval = now - self._last_report_at
            if interval < 0.25 and self._downloaded < self._total:
                return

            speed = (
                (self._downloaded - self._last_reported_bytes) / interval
                if interval > 0
                else 0.0
            )
            remaining = max(0, self._total - self._downloaded)
            eta = int(remaining / speed) if speed > 0 else None
            self._callback(
                self._downloaded,
                self._total,
                speed,
                eta,
            )
            self._last_report_at = now
            self._last_reported_bytes = self._downloaded

    def finish(self) -> None:
        with self._lock:
            self._downloaded = self._total
            self._callback(self._total, self._total, 0.0, 0)


class SmartDownloadEngine:
    """Select segmented or single-connection transfer safely."""

    def __init__(
        self,
        *,
        chunk_size: int = 256 * 1024,
        timeout: float = 30.0,
        max_retries: int = 3,
        minimum_segment_size: int = 256 * 1024,
        bandwidth_limiter: BandwidthLimiter | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.max_retries = max_retries
        self.minimum_segment_size = minimum_segment_size
        self.bandwidth_limiter = bandwidth_limiter
        self.single_engine = DownloadEngine(
            chunk_size=chunk_size,
            timeout=timeout,
            max_retries=max_retries,
            bandwidth_limiter=bandwidth_limiter,
        )

    def download(
        self,
        record: DownloadRecord,
        control: DownloadControl,
        *,
        on_progress: ProgressCallback | None = None,
        on_status: StatusCallback | None = None,
        on_metadata: MetadataCallback | None = None,
        on_mode: ModeCallback | None = None,
        on_adaptive: AdaptiveCallback | None = None,
        session: BrowserSession | None = None,
    ) -> DownloadResult:
        progress_callback = on_progress or (lambda *_: None)
        status_callback = on_status or (lambda *_: None)
        metadata_callback = on_metadata or (lambda *_: None)
        mode_callback = on_mode or (lambda *_: None)
        adaptive_callback = on_adaptive or (lambda *_: None)

        if record.final_path.exists():
            raise DownloadError(
                f"A file with this name already exists: {record.final_path.name}"
            )

        probe = self.probe(
            record.url,
            control,
            status_callback,
            referer=record.referer,
            session=session,
        )
        metadata_callback(
            probe.total_bytes,
            probe.etag,
            probe.last_modified,
        )
        record.total_bytes = probe.total_bytes
        record.etag = probe.etag
        record.last_modified = probe.last_modified

        legacy_partial = (
            record.temporary_path.exists()
            and record.temporary_path.stat().st_size > 0
        )
        requested_connections = max(1, min(16, record.connections))
        requested_connections = self._effective_connections(
            requested_connections,
            probe.total_bytes,
        )
        starting_connections = self._effective_connections(
            max(
                1,
                min(
                    requested_connections,
                    int(record.adaptive_connections or requested_connections),
                ),
            ),
            probe.total_bytes,
        )

        if (
            legacy_partial
            or not probe.supports_ranges
            or requested_connections <= 1
            or probe.total_bytes <= 0
        ):
            if legacy_partial:
                mode = "Single • legacy resume"
            elif not probe.supports_ranges:
                mode = "Single • no Range support"
            else:
                mode = "Single"
            mode_callback(mode, 1)
            status_callback(DownloadStatus.DOWNLOADING, mode)
            result = self.single_engine.download(
                record,
                control,
                on_progress=progress_callback,
                on_status=status_callback,
                on_metadata=metadata_callback,
                session=session,
            )
            stale_parts = self.part_directory(record)
            if stale_parts.exists():
                shutil.rmtree(stale_parts)
            return result

        def adaptive_changed(event: AdaptiveConnectionEvent) -> None:
            mode_callback(
                f"Adaptive {event.effective}/{event.requested}",
                event.effective,
            )
            adaptive_callback(event)

        controller = AdaptiveConnectionController(
            requested=requested_connections,
            initial=starting_connections,
            on_change=adaptive_changed,
        )
        mode = (
            f"Adaptive {controller.effective}/{requested_connections}"
        )
        mode_callback(mode, controller.effective)
        status_callback(DownloadStatus.DOWNLOADING, mode)
        return self._download_segmented(
            record,
            probe,
            requested_connections,
            control,
            progress_callback,
            status_callback,
            controller,
            session,
        )

    def probe(
        self,
        url: str,
        control: DownloadControl,
        on_status: StatusCallback | None = None,
        *,
        referer: str = "",
        session: BrowserSession | None = None,
    ) -> DownloadProbe:
        status_callback = on_status or (lambda *_: None)
        headers = {
            "User-Agent": session_user_agent(session, USER_AGENT),
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Range": "bytes=0-0",
            "Connection": "close",
        }
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(
            url,
            headers=headers,
            method="GET",
        )

        for attempt in range(self.max_retries + 1):
            control.wait_until_running()
            try:
                response = open_session_url(
                    request,
                    session=session,
                    timeout=self.timeout,
                )
            except urllib.error.HTTPError as error:
                if control.is_cancelled:
                    raise DownloadCancelled("Download canceled.") from error
                if is_rate_limited(error) and attempt < self.max_retries:
                    delay = retry_delay_seconds(error, attempt)
                    status_callback(
                        DownloadStatus.RETRYING,
                        "Server rate limit; waiting "
                        f"{delay:.0f}s before inspection retry "
                        f"{attempt + 1}/{self.max_retries}",
                    )
                    try:
                        error.close()
                    except OSError:
                        pass
                    self._wait_for_retry(delay, control)
                    continue
                raise DownloadError(
                    f"HTTP error {error.code}: {error.reason}"
                ) from error
            except (urllib.error.URLError, socket.timeout, OSError) as error:
                if control.is_cancelled:
                    raise DownloadCancelled("Download canceled.") from error
                raise DownloadError(
                    f"Could not inspect the server: {error}"
                ) from error

            control.bind_response(response)
            try:
                status = int(response.getcode() or 0)
                content_range = response.headers.get("Content-Range", "")
                range_match = re.search(r"bytes\s+0-0/(\d+)", content_range)
                supports_ranges = status == 206 and range_match is not None
                if range_match:
                    total_bytes = int(range_match.group(1))
                else:
                    try:
                        total_bytes = int(
                            response.headers.get("Content-Length", "0")
                        )
                    except ValueError:
                        total_bytes = 0
                return DownloadProbe(
                    total_bytes=total_bytes,
                    supports_ranges=supports_ranges,
                    etag=response.headers.get("ETag", ""),
                    last_modified=response.headers.get("Last-Modified", ""),
                )
            finally:
                control.release_response(response)
                response.close()

        raise DownloadError("Could not inspect the server.")

    def _download_segmented(
        self,
        record: DownloadRecord,
        probe: DownloadProbe,
        connections: int,
        control: DownloadControl,
        on_progress: ProgressCallback,
        on_status: StatusCallback,
        controller: AdaptiveConnectionController,
        session: BrowserSession | None,
    ) -> DownloadResult:
        final_path = record.final_path
        part_directory = self.part_directory(record)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        segments = self._compatible_resume_segments(
            part_directory,
            record,
            probe,
        )
        if not segments:
            segments = self.build_segments(probe.total_bytes, connections)
        self._prepare_part_directory(
            part_directory,
            record,
            probe,
            segments,
        )
        for segment in segments:
            path = self.segment_path(part_directory, segment)
            if path.exists() and path.stat().st_size > segment.length:
                path.unlink()

        initial_bytes = sum(
            self.segment_path(part_directory, segment).stat().st_size
            if self.segment_path(part_directory, segment).exists()
            else 0
            for segment in segments
        )
        tracker = ProgressAggregator(
            initial_bytes=initial_bytes,
            total_bytes=probe.total_bytes,
            callback=on_progress,
        )
        abort_event = threading.Event()

        executor = ThreadPoolExecutor(
            max_workers=len(segments),
            thread_name_prefix="sdm-segment",
        )
        futures = [
            executor.submit(
                self._download_segment,
                record,
                probe,
                segment,
                part_directory,
                control,
                abort_event,
                tracker,
                on_status,
                controller,
                session,
            )
            for segment in segments
        ]

        first_error: Exception | None = None
        try:
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    first_error = error
                    abort_event.set()
                    control.close_active_responses()
                    for pending in futures:
                        pending.cancel()
                    break
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        if control.is_cancelled:
            raise DownloadCancelled("Download canceled.")
        if first_error is not None:
            if isinstance(first_error, DownloadCancelled):
                raise first_error
            if isinstance(first_error, DownloadError):
                raise first_error
            raise DownloadError(str(first_error)) from first_error

        self._verify_segments(part_directory, segments)
        self._merge_segments(record, part_directory, segments, control)
        tracker.finish()
        shutil.rmtree(part_directory)
        return DownloadResult(
            final_path=final_path,
            downloaded_bytes=probe.total_bytes,
            total_bytes=probe.total_bytes,
        )

    def _download_segment(
        self,
        record: DownloadRecord,
        probe: DownloadProbe,
        segment: Segment,
        part_directory: Path,
        control: DownloadControl,
        abort_event: threading.Event,
        tracker: ProgressAggregator,
        on_status: StatusCallback,
        controller: AdaptiveConnectionController,
        session: BrowserSession | None,
    ) -> None:
        part_path = self.segment_path(part_directory, segment)
        last_error: Exception | None = None

        initial_size = part_path.stat().st_size if part_path.exists() else 0
        if initial_size == segment.length:
            return
        if segment.index > 0:
            self._wait_for_retry(
                min(segment.index * 0.15, 1.2),
                control,
                abort_event,
            )

        for attempt in range(self.max_retries + 1):
            control.wait_until_running()
            if abort_event.is_set():
                raise SegmentAborted("Another segment failed.")

            current_size = part_path.stat().st_size if part_path.exists() else 0
            if current_size == segment.length:
                return
            if current_size > segment.length:
                part_path.unlink()
                current_size = 0

            request_start = segment.start + current_size
            headers = {
                "User-Agent": session_user_agent(session, USER_AGENT),
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Range": f"bytes={request_start}-{segment.end}",
                "Connection": "close",
            }
            if record.referer:
                headers["Referer"] = record.referer
            validator = probe.etag or probe.last_modified
            if validator:
                headers["If-Range"] = validator

            request = urllib.request.Request(
                record.url,
                headers=headers,
                method="GET",
            )
            response = None
            acquired = False
            try:
                acquired = controller.acquire(
                    control.wait_until_running,
                    abort_event.is_set,
                )
                if not acquired:
                    raise SegmentAborted("Another segment failed.")
                response = open_session_url(
                    request,
                    session=session,
                    timeout=self.timeout,
                )
                control.bind_response(response)
                self._validate_segment_response(
                    response,
                    request_start=request_start,
                    segment=segment,
                    total_bytes=probe.total_bytes,
                )
                self._stream_segment(
                    response,
                    part_path,
                    segment,
                    control,
                    abort_event,
                    tracker,
                )
                if part_path.stat().st_size == segment.length:
                    controller.record_success()
                    return
                raise DownloadError(
                    f"Segment {segment.index + 1} ended early."
                )
            except DownloadCancelled:
                raise
            except SegmentAborted:
                raise
            except (
                DownloadError,
                urllib.error.URLError,
                socket.timeout,
                TimeoutError,
                OSError,
                ValueError,
            ) as error:
                if control.is_cancelled:
                    raise DownloadCancelled("Download canceled.") from error
                if abort_event.is_set():
                    raise SegmentAborted("Another segment failed.") from error
                last_error = error
                if attempt >= self.max_retries:
                    break
                delay = retry_delay_seconds(error, attempt)
                if is_rate_limited(error):
                    status_code = int(getattr(error, "code", 429))
                    controller.record_rate_limit(
                        status_code=status_code,
                        retry_after=delay,
                    )
                    delay += min(segment.index * 0.2, 1.4)
                    message = (
                        f"Segment {segment.index + 1}: rate limited; "
                        f"adaptive limit {controller.effective}/"
                        f"{controller.requested}; waiting {delay:.0f}s "
                        f"(retry {attempt + 1}/{self.max_retries})"
                    )
                else:
                    message = (
                        f"Segment {segment.index + 1}: "
                        f"retry {attempt + 1}/{self.max_retries} "
                        f"after {delay:.0f}s"
                    )
                on_status(DownloadStatus.RETRYING, message)
                if isinstance(error, urllib.error.HTTPError):
                    try:
                        error.close()
                    except OSError:
                        pass
                self._wait_for_retry(delay, control, abort_event)
            finally:
                if response is not None:
                    control.release_response(response)
                    response.close()
                if acquired:
                    controller.release()

        raise DownloadError(
            f"Segment {segment.index + 1} failed: {last_error}"
        ) from last_error

    def _stream_segment(
        self,
        response,
        part_path: Path,
        segment: Segment,
        control: DownloadControl,
        abort_event: threading.Event,
        tracker: ProgressAggregator,
    ) -> None:
        current_size = part_path.stat().st_size if part_path.exists() else 0
        remaining = segment.length - current_size
        with part_path.open("ab") as destination:
            while remaining > 0:
                control.wait_until_running()
                if abort_event.is_set():
                    raise SegmentAborted("Another segment failed.")
                try:
                    chunk = response.read(min(self.chunk_size, remaining))
                except (ValueError, AttributeError, OSError) as error:
                    if control.is_cancelled:
                        raise DownloadCancelled("Download canceled.") from error
                    if abort_event.is_set():
                        raise SegmentAborted("Another segment failed.") from error
                    raise
                if not chunk:
                    break
                if self.bandwidth_limiter is not None:
                    self.bandwidth_limiter.throttle(
                        len(chunk),
                        control.wait_until_running,
                    )
                destination.write(chunk)
                remaining -= len(chunk)
                tracker.add(len(chunk))

    @staticmethod
    def _validate_segment_response(
        response,
        *,
        request_start: int,
        segment: Segment,
        total_bytes: int,
    ) -> None:
        status = int(response.getcode() or 0)
        if status != 206:
            raise DownloadError(
                "The server stopped honoring byte-range requests."
            )

        content_range = response.headers.get("Content-Range", "")
        match = re.fullmatch(
            r"bytes\s+(\d+)-(\d+)/(\d+|\*)",
            content_range.strip(),
        )
        if not match:
            raise DownloadError("Invalid Content-Range response.")

        returned_start = int(match.group(1))
        returned_end = int(match.group(2))
        returned_total = match.group(3)
        if returned_start != request_start or returned_end > segment.end:
            raise DownloadError("The server returned an unexpected byte range.")
        if returned_total != "*" and int(returned_total) != total_bytes:
            raise DownloadError("The remote file changed during download.")

    def _merge_segments(
        self,
        record: DownloadRecord,
        part_directory: Path,
        segments: list[Segment],
        control: DownloadControl,
    ) -> None:
        if record.final_path.exists():
            raise DownloadError(
                f"A file with this name already exists: {record.filename}"
            )

        merge_path = record.temporary_path
        with merge_path.open("wb") as destination:
            for segment in segments:
                with self.segment_path(part_directory, segment).open("rb") as source:
                    while True:
                        control.wait_until_running()
                        chunk = source.read(self.chunk_size)
                        if not chunk:
                            break
                        destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())

        expected_size = sum(segment.length for segment in segments)
        if merge_path.stat().st_size != expected_size:
            raise DownloadError("Merged file size verification failed.")
        os.replace(merge_path, record.final_path)

    @staticmethod
    def _verify_segments(
        part_directory: Path,
        segments: list[Segment],
    ) -> None:
        for segment in segments:
            path = SmartDownloadEngine.segment_path(part_directory, segment)
            actual_size = path.stat().st_size if path.exists() else -1
            if actual_size != segment.length:
                raise DownloadError(
                    f"Segment {segment.index + 1} size verification failed."
                )

    def _prepare_part_directory(
        self,
        part_directory: Path,
        record: DownloadRecord,
        probe: DownloadProbe,
        segments: list[Segment],
    ) -> None:
        expected_manifest = {
            "version": 1,
            # Signed CDN URLs may change while the file identity remains the
            # same. Preserve resumable parts against the stable adapter source.
            "url": record.source_url or record.url,
            "total_bytes": probe.total_bytes,
            "etag": probe.etag,
            "last_modified": probe.last_modified,
            "connections": len(segments),
            "segments": [asdict(segment) for segment in segments],
        }
        manifest_path = part_directory / "manifest.json"

        current_manifest = None
        if manifest_path.exists():
            try:
                current_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                current_manifest = None

        if part_directory.exists() and current_manifest != expected_manifest:
            shutil.rmtree(part_directory)
        part_directory.mkdir(parents=True, exist_ok=True)

        temporary_manifest = manifest_path.with_suffix(".json.tmp")
        temporary_manifest.write_text(
            json.dumps(expected_manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary_manifest, manifest_path)

    def _compatible_resume_segments(
        self,
        part_directory: Path,
        record: DownloadRecord,
        probe: DownloadProbe,
    ) -> list[Segment]:
        """Reuse valid segment boundaries when the adaptive limit changed."""
        manifest_path = part_directory / "manifest.json"
        if not manifest_path.exists():
            return []
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        expected_source = record.source_url or record.url
        if (
            manifest.get("url") != expected_source
            or int(manifest.get("total_bytes", 0)) != probe.total_bytes
            or str(manifest.get("etag", "")) != probe.etag
            or str(manifest.get("last_modified", "")) != probe.last_modified
        ):
            return []
        raw_segments = manifest.get("segments")
        if not isinstance(raw_segments, list) or not raw_segments:
            return []
        try:
            segments = [
                Segment(
                    index=int(item["index"]),
                    start=int(item["start"]),
                    end=int(item["end"]),
                )
                for item in raw_segments
                if isinstance(item, dict)
            ]
        except (KeyError, TypeError, ValueError):
            return []
        if len(segments) != len(raw_segments) or len(segments) > 16:
            return []
        expected_start = 0
        for index, segment in enumerate(segments):
            if (
                segment.index != index
                or segment.start != expected_start
                or segment.end < segment.start
            ):
                return []
            expected_start = segment.end + 1
        if expected_start != probe.total_bytes:
            return []
        return segments

    @staticmethod
    def _wait_for_retry(
        delay: float,
        control: DownloadControl,
        abort_event: threading.Event | None = None,
    ) -> None:
        end_time = time.monotonic() + max(0.0, delay)
        while time.monotonic() < end_time:
            control.wait_until_running()
            if abort_event is not None and abort_event.is_set():
                raise SegmentAborted("Another segment failed.")
            time.sleep(0.1)

    def _effective_connections(
        self,
        requested: int,
        total_bytes: int,
    ) -> int:
        if total_bytes <= 0:
            return 1
        useful_connections = max(1, total_bytes // self.minimum_segment_size)
        return max(1, min(requested, useful_connections))

    @staticmethod
    def build_segments(total_bytes: int, connections: int) -> list[Segment]:
        if total_bytes <= 0:
            raise ValueError("total_bytes must be positive")
        connections = max(1, min(connections, total_bytes))
        base_size, remainder = divmod(total_bytes, connections)
        segments: list[Segment] = []
        start = 0
        for index in range(connections):
            length = base_size + (1 if index < remainder else 0)
            end = start + length - 1
            segments.append(Segment(index=index, start=start, end=end))
            start = end + 1
        return segments

    @staticmethod
    def part_directory(record: DownloadRecord) -> Path:
        return record.final_path.with_name(
            f".{record.filename}.sdm.parts"
        )

    @staticmethod
    def segment_path(part_directory: Path, segment: Segment) -> Path:
        return part_directory / f"segment_{segment.index:03d}.part"
