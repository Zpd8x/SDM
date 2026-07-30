from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from sdm.bandwidth import BandwidthLimiter
from sdm.adaptive_connections import AdaptiveConnectionEvent
from sdm.checksum import compute_sha256
from sdm.content_fingerprint import classify_content_fingerprint
from sdm.database import DownloadRepository, utc_now
from sdm.engine import (
    DownloadCancelled,
    DownloadControl,
    DownloadError,
    DownloadResult,
)
from sdm.models import DownloadStatus
from sdm.categories import categorize_filename
from sdm.platform_media import PlatformMediaEngine
from sdm.progress_details import read_connection_progress
from sdm.segmented_engine import SmartDownloadEngine
from sdm.session_auth import delete_session_auth, load_session_auth
from sdm.site_adapters import (
    ADAPTER_DIRECT,
    ADAPTER_LABELS,
    SiteAdapterError,
    is_stale_link_error,
    resolve_site_url,
)


class DownloadWorker(QThread):
    progress_changed = Signal(str, object, object, float, object)
    metadata_changed = Signal(str, object, str, str)
    mode_changed = Signal(str, str, object)
    connection_progress_changed = Signal(str, object)
    state_changed = Signal(str, str, str)
    output_path_changed = Signal(str, str, str)
    content_duplicate_found = Signal(str, str)

    def __init__(
        self,
        record_id: str,
        repository: DownloadRepository,
        bandwidth_limiter: BandwidthLimiter | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.record_id = record_id
        self.repository = repository
        self.control = DownloadControl()
        self.engine = SmartDownloadEngine(
            bandwidth_limiter=bandwidth_limiter
        )
        self.platform_media_engine = PlatformMediaEngine()
        self._closing_application = False

    def run(self) -> None:
        record = self.repository.get(self.record_id)
        if record is None:
            self.state_changed.emit(
                self.record_id,
                DownloadStatus.FAILED.value,
                "Download record was not found.",
            )
            return

        self._set_state(DownloadStatus.DOWNLOADING, "")
        browser_session = (
            load_session_auth(self.repository.database_path, self.record_id)
            if record.media_kind == "direct"
            else None
        )
        try:
            if record.final_path.exists() and record.checksum_sha256:
                existing_size = record.final_path.stat().st_size
                result = DownloadResult(
                    final_path=record.final_path,
                    downloaded_bytes=existing_size,
                    total_bytes=record.total_bytes or existing_size,
                )
                self.progress_changed.emit(
                    self.record_id,
                    result.downloaded_bytes,
                    result.total_bytes,
                    0.0,
                    0,
                )
                self._emit_connection_progress(
                    downloaded=result.downloaded_bytes,
                    total=result.total_bytes,
                    status=DownloadStatus.DOWNLOADING,
                )
            elif record.media_kind != "direct":
                result = self.platform_media_engine.download(
                    record,
                    self.control,
                    on_progress=self._on_progress,
                    on_status=self._on_engine_status,
                    on_metadata=self._on_metadata,
                    on_mode=self._on_mode,
                )
                if result.final_path != record.final_path:
                    self.repository.update(
                        self.record_id,
                        filename=result.final_path.name,
                        folder=str(result.final_path.parent),
                        category=categorize_filename(result.final_path.name),
                    )
                    self.output_path_changed.emit(
                        self.record_id,
                        result.final_path.name,
                        str(result.final_path.parent),
                    )
            else:
                result = self._download_direct(record, browser_session)

            self.repository.update(
                self.record_id,
                checksum_status=(
                    "Verifying" if record.checksum_sha256 else record.checksum_status
                ),
                content_fingerprint_status="Computing",
            )
            self._set_state(
                DownloadStatus.VERIFYING,
                "Computing SHA-256 content fingerprint.",
            )
            try:
                actual_checksum = compute_sha256(result.final_path)
            except OSError:
                self.repository.update(
                    self.record_id,
                    checksum_status=(
                        "Error" if record.checksum_sha256 else record.checksum_status
                    ),
                    content_fingerprint_status="Error",
                )
                raise

            if record.checksum_sha256 and actual_checksum != record.checksum_sha256:
                message = (
                    "SHA-256 mismatch. "
                    f"Expected {record.checksum_sha256}; "
                    f"actual {actual_checksum}."
                )
                self.repository.update(
                    self.record_id,
                    downloaded_bytes=result.downloaded_bytes,
                    total_bytes=result.total_bytes,
                    status=DownloadStatus.FAILED,
                    error=message,
                    checksum_actual=actual_checksum,
                    checksum_status="Mismatch",
                    content_sha256=actual_checksum,
                    content_fingerprint_status="Computed",
                )
                self.state_changed.emit(
                    self.record_id,
                    DownloadStatus.FAILED.value,
                    message,
                )
                return

            fingerprint = classify_content_fingerprint(
                self.repository,
                actual_checksum,
                record_id=self.record_id,
            )
            duplicate = fingerprint.duplicate
            self.repository.update(
                self.record_id,
                checksum_actual=(
                    actual_checksum if record.checksum_sha256 else record.checksum_actual
                ),
                checksum_status=(
                    "Verified" if record.checksum_sha256 else record.checksum_status
                ),
                content_sha256=actual_checksum,
                content_fingerprint_status=fingerprint.status,
                duplicate_of_id=fingerprint.duplicate_of_id,
            )
        except DownloadCancelled:
            state = (
                DownloadStatus.PAUSED
                if self._closing_application
                else DownloadStatus.CANCELED
            )
            message = (
                "Paused when SDM closed."
                if self._closing_application
                else "Canceled by user."
            )
            self._set_state(state, message)
        except (DownloadError, OSError) as error:
            self._set_state(DownloadStatus.FAILED, str(error))
        except Exception as error:  # Last-resort boundary for the worker thread.
            self._set_state(DownloadStatus.FAILED, f"Unexpected error: {error}")
        else:
            completed_record = self.repository.get(self.record_id)
            if completed_record is not None and completed_record.media_kind == "direct":
                self.repository.record_adaptive_feedback(
                    self.record_id,
                    effective=completed_record.adaptive_connections,
                    kind="completed",
                    reason=(
                        "Adaptive mode: completed successfully; the server "
                        "profile was updated."
                    ),
                )
            self.repository.update(
                self.record_id,
                downloaded_bytes=result.downloaded_bytes,
                total_bytes=result.total_bytes,
                status=DownloadStatus.COMPLETED,
                error="",
            )
            self.progress_changed.emit(
                self.record_id,
                result.downloaded_bytes,
                result.total_bytes,
                0.0,
                0,
            )
            final_record = self.repository.get(self.record_id)
            duplicate_id = final_record.duplicate_of_id if final_record else ""
            completion_message = (
                "Download completed. Identical content already exists in SDM; "
                "no file was deleted."
                if duplicate_id
                else "Download completed."
            )
            self.state_changed.emit(
                self.record_id,
                DownloadStatus.COMPLETED.value,
                completion_message,
            )
            if duplicate_id:
                self.content_duplicate_found.emit(self.record_id, duplicate_id)
            delete_session_auth(
                self.repository.database_path,
                self.record_id,
            )

    def _download_direct(self, record, browser_session):
        self._refresh_adapter_url(record, browser_session)
        record = self._prepare_adaptive_record(record)
        try:
            return self.engine.download(
                record,
                self.control,
                on_progress=self._on_progress,
                on_status=self._on_engine_status,
                on_metadata=self._on_metadata,
                on_mode=self._on_mode,
                on_adaptive=self._on_adaptive,
                session=browser_session,
            )
        except DownloadError as error:
            if (
                record.site_adapter == ADAPTER_DIRECT
                or not is_stale_link_error(error)
            ):
                raise
            self.repository.update(
                self.record_id,
                adapter_status="Refreshing expired link",
            )
            self._set_state(
                DownloadStatus.RETRYING,
                "The signed link expired. Refreshing it from its saved source.",
            )
            previous_url = record.url
            self._refresh_adapter_url(
                record,
                browser_session,
                force=True,
            )
            if record.url == previous_url:
                raise error
            record = self._prepare_adaptive_record(record)
            return self.engine.download(
                record,
                self.control,
                on_progress=self._on_progress,
                on_status=self._on_engine_status,
                on_metadata=self._on_metadata,
                on_mode=self._on_mode,
                on_adaptive=self._on_adaptive,
                session=browser_session,
            )

    def _prepare_adaptive_record(self, record):
        prepared = self.repository.prepare_adaptive_download(self.record_id)
        if prepared is None:
            return record
        record.connections = prepared.connections
        record.adaptive_connections = prepared.adaptive_connections
        record.adaptive_reason = prepared.adaptive_reason
        return record

    def _refresh_adapter_url(
        self,
        record,
        browser_session,
        *,
        force: bool = False,
    ) -> None:
        if (
            record.site_adapter == ADAPTER_DIRECT
            or not record.source_url
        ):
            return
        label = ADAPTER_LABELS.get(
            record.site_adapter,
            record.site_adapter,
        )
        self._on_engine_status(
            DownloadStatus.RETRYING if force else DownloadStatus.DOWNLOADING,
            f"Resolving a fresh {label} link.",
        )
        try:
            resolution = resolve_site_url(
                record.source_url,
                adapter=record.site_adapter,
                session=browser_session,
                preferred_url=record.url,
            )
        except SiteAdapterError as error:
            self.repository.update(
                self.record_id,
                adapter_status="Needs recapture",
            )
            raise DownloadError(str(error)) from error

        fields = {
            "url": resolution.url,
            "source_url": resolution.source_url,
            "site_adapter": resolution.adapter,
            "adapter_status": "Resolved",
            "resolved_at": utc_now(),
        }
        if resolution.total_bytes > 0:
            fields["total_bytes"] = resolution.total_bytes
            record.total_bytes = resolution.total_bytes
        if resolution.mime_type:
            fields["mime_type"] = resolution.mime_type
            record.mime_type = resolution.mime_type
        self.repository.update(self.record_id, **fields)
        record.url = resolution.url
        record.source_url = resolution.source_url
        record.adapter_status = "Resolved"
        record.resolved_at = str(fields["resolved_at"])

    def pause_download(self) -> None:
        if not self.isRunning():
            return
        self.control.pause()
        self._set_state(DownloadStatus.PAUSED, "")

    def resume_download(self) -> None:
        if not self.isRunning():
            return
        self.control.resume()
        self._set_state(DownloadStatus.DOWNLOADING, "")

    def cancel_download(self) -> None:
        self._closing_application = False
        self.control.cancel()

    def shutdown(self) -> None:
        self._closing_application = True
        self.control.cancel()

    def _on_progress(
        self,
        downloaded: int,
        total: int,
        speed: float,
        eta: int | None,
    ) -> None:
        self.repository.update(
            self.record_id,
            downloaded_bytes=downloaded,
            total_bytes=total,
        )
        self.progress_changed.emit(
            self.record_id,
            downloaded,
            total,
            speed,
            eta,
        )
        self._emit_connection_progress(
            downloaded=downloaded,
            total=total,
        )

    def _on_metadata(
        self,
        total: int,
        etag: str,
        last_modified: str,
    ) -> None:
        self.repository.update(
            self.record_id,
            total_bytes=total,
            etag=etag,
            last_modified=last_modified,
        )
        self.metadata_changed.emit(
            self.record_id,
            total,
            etag,
            last_modified,
        )

    def _on_engine_status(
        self,
        status: DownloadStatus,
        message: str,
    ) -> None:
        self._set_state(status, message)

    def _on_mode(self, mode: str, active_connections: int) -> None:
        self.repository.update(
            self.record_id,
            transfer_mode=mode,
        )
        self.mode_changed.emit(
            self.record_id,
            mode,
            active_connections,
        )

    def _on_adaptive(self, event: AdaptiveConnectionEvent) -> None:
        self.repository.record_adaptive_feedback(
            self.record_id,
            effective=event.effective,
            kind=event.kind,
            reason=event.reason,
        )

    def _set_state(self, status: DownloadStatus, message: str) -> None:
        error = message if status == DownloadStatus.FAILED else ""
        self.repository.update(
            self.record_id,
            status=status,
            error=error,
        )
        self._emit_connection_progress(status=status)
        self.state_changed.emit(self.record_id, status.value, message)

    def _emit_connection_progress(
        self,
        *,
        downloaded: int | None = None,
        total: int | None = None,
        status: DownloadStatus | None = None,
    ) -> None:
        record = self.repository.get(self.record_id)
        if record is None:
            return
        snapshot = read_connection_progress(
            record,
            downloaded_bytes=downloaded,
            total_bytes=total,
            status=status,
        )
        self.connection_progress_changed.emit(self.record_id, snapshot)
