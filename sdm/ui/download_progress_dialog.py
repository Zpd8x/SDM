from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sdm.models import DownloadRecord, DownloadStatus
from sdm.progress_details import (
    ConnectionProgress,
    progress_action_state,
)
from sdm.ui.completion_dialog import DownloadCompleteDialog
from sdm.ui.icons import application_icon
from sdm.ui.window_activation import (
    configure_attention_window,
    schedule_window_activation,
)
from sdm.utils import format_bytes, format_eta, format_speed


SPEED_LIMITS = (
    ("Unlimited", 0),
    ("512 KB/s", 512 * 1024),
    ("1 MB/s", 1024 * 1024),
    ("2 MB/s", 2 * 1024 * 1024),
    ("5 MB/s", 5 * 1024 * 1024),
    ("10 MB/s", 10 * 1024 * 1024),
)

STATUS_TEXT = {
    DownloadStatus.QUEUED: "Waiting",
    DownloadStatus.DOWNLOADING: "Downloading",
    DownloadStatus.PAUSED: "Paused",
    DownloadStatus.RETRYING: "Retrying",
    DownloadStatus.VERIFYING: "Verifying SHA-256",
    DownloadStatus.COMPLETED: "Completed",
    DownloadStatus.FAILED: "Failed",
    DownloadStatus.CANCELED: "Canceled",
    DownloadStatus.SCHEDULED: "Scheduled",
}


class DownloadProgressDialog(QDialog):
    pause_requested = Signal(str)
    resume_requested = Signal(str)
    cancel_requested = Signal(str)
    open_manager_requested = Signal()
    speed_limit_changed = Signal(int)
    completion_options_changed = Signal(bool, bool)

    def __init__(
        self,
        record: DownloadRecord,
        *,
        speed_limit_bps: int = 0,
        show_completion_dialog: bool = True,
        open_folder_on_completion: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.record_id = record.id
        self.folder = record.folder
        self.url = record.url
        self.filename = record.filename
        self.final_path = record.final_path
        self._downloaded_bytes = record.downloaded_bytes
        self._total_bytes = record.total_bytes
        self._status = record.status
        self._terminal = record.status in {
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
            DownloadStatus.CANCELED,
        }
        self._completion_shown = False
        self._details_visible = True
        self._has_connection_snapshot = False

        self.setWindowTitle(f"0%  {record.filename}")
        self.setWindowIcon(application_icon())
        configure_attention_window(self)
        self.resize(770, 570)
        self.setMinimumSize(700, 340)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        tabs = QTabWidget()
        tabs.addTab(self._build_status_tab(record), "Download status")
        tabs.addTab(
            self._build_speed_tab(speed_limit_bps),
            "Speed Limiter",
        )
        tabs.addTab(
            self._build_completion_tab(
                record,
                show_completion_dialog,
                open_folder_on_completion,
            ),
            "Options on completion",
        )

        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 1000)
        self.overall_progress.setValue(int(record.progress * 1000))
        self.overall_progress.setFormat(f"{record.progress * 100:.1f}%")
        self.overall_progress.setMinimumHeight(24)

        self.details_button = QPushButton("Hide details")
        self.details_button.clicked.connect(self._toggle_details)
        self.open_manager_button = QPushButton("Open SDM")
        self.open_manager_button.clicked.connect(
            self.open_manager_requested.emit
        )
        self.resume_button = QPushButton("Resume")
        self.resume_button.clicked.connect(self._resume_download)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._pause_download)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self._cancel_or_close)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.details_button)
        action_layout.addWidget(self.open_manager_button)
        action_layout.addStretch()
        action_layout.addWidget(self.resume_button)
        action_layout.addWidget(self.pause_button)
        action_layout.addWidget(self.cancel_button)

        self.details_frame = QFrame()
        details_layout = QVBoxLayout(self.details_frame)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)

        connection_title = QLabel(
            "Start positions and download progress by connections"
        )
        connection_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        connection_title.setStyleSheet("color: #aab7ca; font-weight: 600;")
        details_layout.addWidget(connection_title)

        self.connection_strip = QWidget()
        self.connection_strip_layout = QHBoxLayout(self.connection_strip)
        self.connection_strip_layout.setContentsMargins(0, 0, 0, 0)
        self.connection_strip_layout.setSpacing(3)
        details_layout.addWidget(self.connection_strip)

        self.connection_table = QTableWidget(0, 4)
        self.connection_table.setHorizontalHeaderLabels(
            ["N.", "Downloaded", "Progress", "Info"]
        )
        self.connection_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.connection_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.connection_table.verticalHeader().setVisible(False)
        self.connection_table.verticalHeader().setDefaultSectionSize(34)
        header = self.connection_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        details_layout.addWidget(self.connection_table, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        root.addWidget(tabs)
        root.addWidget(self.overall_progress)
        root.addLayout(action_layout)
        root.addWidget(self.details_frame, 1)

        self.set_state(record.status, record.error)
        self.set_connection_progress(
            (
                ConnectionProgress(
                    index=1,
                    downloaded_bytes=record.downloaded_bytes,
                    total_bytes=record.total_bytes,
                    status=STATUS_TEXT[record.status],
                ),
            )
        )
        self._has_connection_snapshot = False

    def _build_status_tab(self, record: DownloadRecord) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)

        self.url_edit = QLineEdit(record.url)
        self.url_edit.setReadOnly(True)

        status_group = QGroupBox()
        grid = QGridLayout(status_group)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        self.status_value = QLabel(STATUS_TEXT[record.status])
        self.size_value = QLabel(
            format_bytes(record.total_bytes)
            if record.total_bytes
            else "Unknown"
        )
        self.downloaded_value = QLabel(
            format_bytes(record.downloaded_bytes)
        )
        self.speed_value = QLabel("—")
        self.eta_value = QLabel("—")
        self.resume_value = QLabel("Yes")
        self.error_value = QLabel("")
        self.error_value.setWordWrap(True)
        self.error_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.error_value.setStyleSheet(
            "color: #ff7c8a; background: #181f2b; "
            "border: 1px solid #5b2d3a; border-radius: 6px; padding: 7px;"
        )
        self.error_value.hide()

        rows = (
            ("Status", self.status_value),
            ("File size", self.size_value),
            ("Downloaded", self.downloaded_value),
            ("Transfer rate", self.speed_value),
            ("Time left", self.eta_value),
            ("Resume capability", self.resume_value),
        )
        for row, (label, value) in enumerate(rows):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)

        layout.addWidget(self.url_edit)
        layout.addWidget(status_group)
        layout.addWidget(self.error_value)
        layout.addStretch()
        return tab

    def _build_speed_tab(self, speed_limit_bps: int) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        description = QLabel(
            "Choose the aggregate SDM speed limit. The value is shared "
            "between every active download and all of its connections."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #aab7ca;")
        self.speed_limit_combo = QComboBox()
        for label, value in SPEED_LIMITS:
            self.speed_limit_combo.addItem(label, value)
        index = self.speed_limit_combo.findData(speed_limit_bps)
        self.speed_limit_combo.setCurrentIndex(index if index >= 0 else 0)
        self.speed_limit_combo.currentIndexChanged.connect(
            lambda _index: self.speed_limit_changed.emit(
                int(self.speed_limit_combo.currentData() or 0)
            )
        )
        layout.addWidget(description)
        layout.addWidget(self.speed_limit_combo)
        layout.addStretch()
        return tab

    def _build_completion_tab(
        self,
        record: DownloadRecord,
        show_dialog: bool,
        open_folder: bool,
    ) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        save_label = QLabel(f"Save To:  {record.final_path}")
        save_label.setWordWrap(True)
        self.show_completion_checkbox = QCheckBox(
            "Show download complete dialog"
        )
        self.show_completion_checkbox.setChecked(show_dialog)
        self.open_folder_checkbox = QCheckBox(
            "Open download folder when done"
        )
        self.open_folder_checkbox.setChecked(open_folder)
        self.show_completion_checkbox.toggled.connect(
            self._completion_options_updated
        )
        self.open_folder_checkbox.toggled.connect(
            self._completion_options_updated
        )
        layout.addWidget(save_label)
        layout.addSpacing(12)
        layout.addWidget(self.show_completion_checkbox)
        layout.addWidget(self.open_folder_checkbox)
        layout.addStretch()
        return tab

    def set_progress(
        self,
        downloaded: int,
        total: int,
        speed: float,
        eta: int | None,
    ) -> None:
        self._downloaded_bytes = max(0, int(downloaded))
        self._total_bytes = max(0, int(total))
        if total > 0:
            fraction = min(1.0, downloaded / total)
            self.overall_progress.setRange(0, 1000)
            self.overall_progress.setValue(int(fraction * 1000))
            self.overall_progress.setFormat(f"{fraction * 100:.1f}%")
            percent = int(fraction * 100)
            self.setWindowTitle(
                f"{percent}%  {self.windowTitle().split('  ', 1)[-1]}"
            )
            self.size_value.setText(format_bytes(total))
        else:
            self.overall_progress.setRange(0, 0)
            self.overall_progress.setFormat("")
        self.downloaded_value.setText(format_bytes(downloaded))
        self.speed_value.setText(format_speed(speed))
        self.eta_value.setText(format_eta(eta))

    def set_output_path(self, filename: str, folder: str) -> None:
        self.filename = filename
        self.folder = folder
        self.final_path = Path(folder) / filename
        percent = (
            int(min(1.0, self._downloaded_bytes / self._total_bytes) * 100)
            if self._total_bytes > 0
            else 0
        )
        self.setWindowTitle(f"{percent}%  {filename}")

    def set_mode(self, mode: str, active_connections: int) -> None:
        self.resume_value.setText(
            f"Yes  •  {mode}"
            if active_connections > 0
            else "Yes"
        )
        if self._has_connection_snapshot or active_connections <= 0:
            return
        self.set_connection_progress(
            tuple(
                ConnectionProgress(
                    index=index + 1,
                    downloaded_bytes=0,
                    total_bytes=0,
                    status="Connecting",
                )
                for index in range(active_connections)
            )
        )
        self._has_connection_snapshot = False

    def set_connection_progress(
        self,
        snapshot: tuple[ConnectionProgress, ...],
    ) -> None:
        if not snapshot:
            return
        self._has_connection_snapshot = True
        self._clear_connection_strip()
        self.connection_table.setRowCount(len(snapshot))
        for row, item in enumerate(snapshot):
            strip = QProgressBar()
            strip.setRange(0, 1000)
            strip.setValue(int(item.fraction * 1000))
            strip.setFormat("")
            strip.setMinimumHeight(12)
            self.connection_strip_layout.addWidget(strip, 1)

            self.connection_table.setItem(
                row,
                0,
                QTableWidgetItem(str(item.index)),
            )
            self.connection_table.setItem(
                row,
                1,
                QTableWidgetItem(format_bytes(item.downloaded_bytes)),
            )
            progress = QProgressBar()
            progress.setRange(0, 1000)
            progress.setValue(int(item.fraction * 1000))
            progress.setFormat(f"{item.fraction * 100:.1f}%")
            self.connection_table.setCellWidget(row, 2, progress)
            self.connection_table.setItem(
                row,
                3,
                QTableWidgetItem(item.status),
            )

    def set_state(
        self,
        status: DownloadStatus,
        message: str = "",
    ) -> None:
        self._status = status
        self.status_value.setText(STATUS_TEXT[status])
        self.status_value.setToolTip(message)
        if status == DownloadStatus.FAILED and message:
            self.error_value.setText(f"Why it failed: {message}")
            self.error_value.setToolTip(message)
            self.error_value.show()
        else:
            self.error_value.clear()
            self.error_value.hide()
        actions = progress_action_state(status)
        self._terminal = actions.terminal
        self.pause_button.setEnabled(actions.can_pause)
        self.resume_button.setEnabled(actions.can_resume)
        self.cancel_button.setText(actions.cancel_label)

        if status == DownloadStatus.COMPLETED:
            self.overall_progress.setRange(0, 1000)
            self.overall_progress.setValue(1000)
            self.overall_progress.setFormat("100.0%")
            self.speed_value.setText("—")
            self.eta_value.setText("00:00")
            self._mark_all_connections_completed()
            self._handle_completion()

    def _pause_download(self) -> None:
        if progress_action_state(self._status).can_pause:
            self.pause_button.setEnabled(False)
            self.pause_requested.emit(self.record_id)

    def _resume_download(self) -> None:
        if not progress_action_state(self._status).can_resume:
            return
        self.set_state(DownloadStatus.QUEUED)
        self.resume_requested.emit(self.record_id)

    def _cancel_or_close(self) -> None:
        if self._terminal:
            self.close()
            return
        answer = QMessageBox.question(
            self,
            "Cancel Download",
            "Cancel this download?\n\n"
            "The partial data will be kept so it can be resumed later.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.cancel_requested.emit(self.record_id)

    def _toggle_details(self) -> None:
        self._details_visible = not self._details_visible
        self.details_frame.setVisible(self._details_visible)
        self.details_button.setText(
            "Hide details" if self._details_visible else "Show details"
        )
        self.resize(
            self.width(),
            570 if self._details_visible else 360,
        )

    def _completion_options_updated(self) -> None:
        self.completion_options_changed.emit(
            self.show_completion_checkbox.isChecked(),
            self.open_folder_checkbox.isChecked(),
        )

    def _handle_completion(self) -> None:
        if self._completion_shown:
            return
        self._completion_shown = True
        if self.open_folder_checkbox.isChecked():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.folder))
        if self.show_completion_checkbox.isChecked():
            self.hide()
            dialog = DownloadCompleteDialog(
                url=self.url,
                final_path=self.final_path,
                downloaded_bytes=self._downloaded_bytes,
                parent=None,
            )
            schedule_window_activation(dialog)
            dialog.exec()
            if dialog.dont_show_again:
                self.show_completion_checkbox.setChecked(False)
        self.close()

    def _mark_all_connections_completed(self) -> None:
        for row in range(self.connection_table.rowCount()):
            progress = self.connection_table.cellWidget(row, 2)
            if isinstance(progress, QProgressBar):
                progress.setValue(1000)
                progress.setFormat("100.0%")
            info = self.connection_table.item(row, 3)
            if info:
                info.setText("Completed")
        for index in range(self.connection_strip_layout.count()):
            widget = self.connection_strip_layout.itemAt(index).widget()
            if isinstance(widget, QProgressBar):
                widget.setValue(1000)

    def _clear_connection_strip(self) -> None:
        while self.connection_strip_layout.count():
            item = self.connection_strip_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.accept()
