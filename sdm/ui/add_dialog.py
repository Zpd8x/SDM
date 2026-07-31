from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QDateTime, QTimer, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from sdm.categories import DOWNLOAD_CATEGORIES
from sdm.checksum import is_valid_sha256, normalize_sha256
from sdm.config import default_download_folder
from sdm.intelligent_analysis import LinkAnalysis, analyze_link
from sdm.models import DownloadRecord
from sdm.ui.icons import application_icon
from sdm.utils import format_bytes, guess_filename, sanitize_filename, validate_download_url


class _LinkAnalyzerThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, filename: str, folder: str, records, parent=None) -> None:
        super().__init__(parent)
        self.url = url
        self.filename = filename
        self.folder = folder
        self.records = tuple(records)

    def run(self) -> None:
        try:
            result = analyze_link(
                self.url,
                filename=self.filename,
                folder=self.folder,
                records=self.records,
            )
        except Exception as error:
            self.failed.emit(" ".join(str(error).replace("\n", " ").split()) or error.__class__.__name__)
        else:
            self.completed.emit(result)


class AddDownloadDialog(QDialog):
    def __init__(self, parent=None, *, default_connections: int = 4, existing_records=()) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Download")
        self.setWindowIcon(application_icon())
        self.setMinimumSize(720, 680)
        self._filename_was_edited = False
        self._existing_records = tuple(existing_records)
        self._analysis: LinkAnalysis | None = None
        self._analysis_thread: _LinkAnalyzerThread | None = None

        self._auto_analyze_timer = QTimer(self)
        self._auto_analyze_timer.setSingleShot(True)
        self._auto_analyze_timer.setInterval(650)
        self._auto_analyze_timer.timeout.connect(self._auto_analyze_if_valid)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        heading_box = QVBoxLayout()
        heading_box.setSpacing(3)
        title = QLabel("Add Download")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Paste a link and let SDM inspect it before the transfer starts.")
        subtitle.setObjectName("dialogSubtitle")
        heading_box.addWidget(title)
        heading_box.addWidget(subtitle)
        header.addLayout(heading_box, 1)

        self.stage_badge = QLabel("WAITING FOR LINK")
        self.stage_badge.setObjectName("analysisStageBadge")
        self.stage_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.stage_badge, 0, Qt.AlignmentFlag.AlignTop)

        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)
        source_layout.setContentsMargins(16, 14, 16, 16)
        source_layout.setSpacing(10)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.textChanged.connect(self._url_changed)
        source_layout.addWidget(self.url_edit)
        auto_row = QHBoxLayout()
        auto_row.setContentsMargins(0, 0, 0, 0)
        self.auto_analyze_checkbox = QCheckBox("Analyze automatically")
        self.auto_analyze_checkbox.setChecked(True)
        auto_hint = QLabel("Reads headers, media type, resume support and duplicate status.")
        auto_hint.setObjectName("mutedText")
        auto_row.addWidget(self.auto_analyze_checkbox)
        auto_row.addStretch()
        auto_row.addWidget(auto_hint)
        source_layout.addLayout(auto_row)

        preview = QFrame()
        preview.setObjectName("mediaPreviewCard")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(16, 14, 16, 14)
        preview_layout.setSpacing(8)
        preview_title = QLabel("Media Preview")
        preview_title.setObjectName("sectionTitle")
        preview_layout.addWidget(preview_title)
        self.analysis_status = QLabel("Paste a link to begin analysis.")
        self.analysis_status.setObjectName("analysisHeadline")
        self.analysis_status.setWordWrap(True)
        self.analysis_details = QLabel("Title, website, file type and estimated size will appear here.")
        self.analysis_details.setObjectName("mutedText")
        self.analysis_details.setWordWrap(True)
        preview_layout.addWidget(self.analysis_status)
        preview_layout.addWidget(self.analysis_details)

        destination_group = QGroupBox("Download Options")
        form = QFormLayout(destination_group)
        form.setContentsMargins(16, 14, 16, 16)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(11)

        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("file.zip")
        self.filename_edit.textEdited.connect(self._mark_filename_edited)
        form.addRow("File name:", self.filename_edit)

        self.folder_edit = QLineEdit(str(default_download_folder()))
        browse_button = QPushButton("Browse…")
        browse_button.setObjectName("secondaryButton")
        browse_button.clicked.connect(self._browse_folder)
        folder_layout = QHBoxLayout()
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.addWidget(self.folder_edit, 1)
        folder_layout.addWidget(browse_button)
        form.addRow("Save to:", folder_layout)

        self.connections_combo = QComboBox()
        self.connections_combo.addItem("Auto (recommended)", default_connections)
        for value in (1, 2, 4, 8, 16):
            label = "1 connection" if value == 1 else f"{value} connections"
            self.connections_combo.addItem(label, value)
        self.connections_combo.setToolTip("SDM reduces this automatically when the server does not support ranges.")
        form.addRow("Connections:", self.connections_combo)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Balanced", "balanced")
        self.preset_combo.addItem("Fast download", "fast")
        self.preset_combo.addItem("Low bandwidth", "mobile")
        self.preset_combo.addItem("Archive / reliability", "archive")
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        form.addRow("Preset:", self.preset_combo)

        self.category_combo = QComboBox()
        self.category_combo.addItem("Auto detect", "Auto")
        for category in DOWNLOAD_CATEGORIES:
            self.category_combo.addItem(category, category)
        form.addRow("Category:", self.category_combo)

        self.checksum_edit = QLineEdit()
        self.checksum_edit.setPlaceholderText("Optional 64-character SHA-256")
        self.checksum_edit.setMaxLength(64)
        form.addRow("SHA-256:", self.checksum_edit)

        behavior_row = QHBoxLayout()
        behavior_row.setContentsMargins(0, 0, 0, 0)
        self.start_checkbox = QCheckBox("Start download immediately")
        self.start_checkbox.setChecked(True)
        self.schedule_checkbox = QCheckBox("Schedule for later")
        self.schedule_datetime = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        self.schedule_datetime.setCalendarPopup(True)
        self.schedule_datetime.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.schedule_datetime.setMinimumDateTime(QDateTime.currentDateTime().addSecs(60))
        self.schedule_datetime.setEnabled(False)
        self.schedule_checkbox.toggled.connect(self._schedule_toggled)
        behavior_row.addWidget(self.start_checkbox)
        behavior_row.addSpacing(12)
        behavior_row.addWidget(self.schedule_checkbox)
        behavior_row.addWidget(self.schedule_datetime)
        behavior_row.addStretch()

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 4, 0, 0)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.clicked.connect(self.reject)
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setObjectName("secondaryButton")
        self.analyze_button.clicked.connect(self._analyze_link)
        self.download_button = QPushButton("Download")
        self.download_button.setObjectName("primaryButton")
        self.download_button.clicked.connect(self._validate_and_accept)
        footer.addStretch()
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.analyze_button)
        footer.addWidget(self.download_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addWidget(source_group)
        layout.addWidget(preview)
        layout.addWidget(destination_group)
        layout.addLayout(behavior_row)
        layout.addStretch()
        layout.addLayout(footer)

        self.url_edit.setFocus()

    @property
    def download_data(self) -> dict[str, str | bool | int]:
        scheduled_at = ""
        if self.schedule_checkbox.isChecked():
            timestamp = self.schedule_datetime.dateTime().toSecsSinceEpoch()
            scheduled_at = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            ).isoformat(timespec="seconds")
        return {
            "url": self.url_edit.text().strip(),
            "filename": sanitize_filename(self.filename_edit.text()),
            "folder": str(Path(self.folder_edit.text().strip()).expanduser()),
            "start_immediately": self.start_checkbox.isChecked(),
            "connections": int(self.connections_combo.currentData()),
            "category": str(self.category_combo.currentData()),
            "scheduled_at": scheduled_at,
            "checksum_sha256": normalize_sha256(
                self.checksum_edit.text()
            ),
        }

    def _url_changed(self, url: str) -> None:
        self._update_suggested_filename(url)
        self._analysis = None
        self.stage_badge.setText("WAITING FOR LINK" if not url.strip() else "READY TO ANALYZE")
        if self.auto_analyze_checkbox.isChecked():
            self._auto_analyze_timer.start()

    def _auto_analyze_if_valid(self) -> None:
        valid, _ = validate_download_url(self.url_edit.text())
        if valid and (self._analysis_thread is None or not self._analysis_thread.isRunning()):
            self._analyze_link()

    def _apply_preset(self) -> None:
        preset = str(self.preset_combo.currentData())
        values = {
            "balanced": (4, True),
            "fast": (16, True),
            "mobile": (1, True),
            "archive": (2, False),
        }
        connections, start = values.get(preset, (4, True))
        index = self.connections_combo.findData(connections)
        if index >= 0:
            self.connections_combo.setCurrentIndex(index)
        if not self.schedule_checkbox.isChecked():
            self.start_checkbox.setChecked(start)

    def _analyze_link(self) -> None:
        valid, error = validate_download_url(self.url_edit.text())
        if not valid:
            QMessageBox.warning(self, "Invalid URL", error)
            return
        self.analyze_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.stage_badge.setText("ANALYZING")
        self.analysis_status.setText("Inspecting link, server metadata and duplicates…")
        self.analysis_details.clear()
        self._analysis_thread = _LinkAnalyzerThread(
            self.url_edit.text().strip(),
            self.filename_edit.text().strip(),
            self.folder_edit.text().strip(),
            self._existing_records,
            self,
        )
        self._analysis_thread.completed.connect(self._analysis_loaded)
        self._analysis_thread.failed.connect(self._analysis_failed)
        self._analysis_thread.finished.connect(self._analysis_finished)
        self._analysis_thread.start()

    def _analysis_loaded(self, result: LinkAnalysis) -> None:
        self._analysis = result
        if result.filename and not self._filename_was_edited:
            self.filename_edit.setText(result.filename)
        capped = min(result.strategy.connections, result.connection_limit)
        index = self.connections_combo.findData(capped)
        if index >= 0:
            self.connections_combo.setCurrentIndex(index)
        duplicate_text = "No duplicate found"
        if result.duplicate is not None:
            duplicate_text = f"Duplicate: {result.duplicate.record.filename} ({result.duplicate.disposition.value})"
        auth_text = "Authentication may be required" if result.requires_auth else "No sign-in detected"
        self.stage_badge.setText("READY")
        self.analysis_status.setText(f"Ready · {result.link_kind} · {result.platform}")
        self.analysis_details.setText(
            f"File: {result.filename or 'Unknown'}  •  Size: {format_bytes(result.total_bytes) if result.total_bytes else 'Unknown'}\n"
            f"Type: {result.mime_type or 'Unknown'}  •  Resume: {'Yes' if result.strategy.resume_supported else 'Not confirmed'}  •  {auth_text}\n"
            f"Smart strategy: {result.strategy.name} · {result.strategy.connections} connection(s) · {result.strategy.transfer_mode}\n"
            f"Health: {result.strategy.health_label} ({result.strategy.health_score}/100) · {result.strategy.retry_profile}\n"
            f"{result.strategy.reason}\n{duplicate_text}"
        )

    def _analysis_failed(self, message: str) -> None:
        self._analysis = None
        self.stage_badge.setText("ANALYSIS FAILED")
        self.analysis_status.setText("Analysis could not be completed.")
        self.analysis_details.setText(message)

    def _analysis_finished(self) -> None:
        self.analyze_button.setEnabled(True)
        self.download_button.setEnabled(True)

    def _schedule_toggled(self, checked: bool) -> None:
        self.schedule_datetime.setEnabled(checked)
        self.start_checkbox.setEnabled(not checked)
        if checked:
            self.start_checkbox.setChecked(False)

    def _mark_filename_edited(self) -> None:
        self._filename_was_edited = True

    def _update_suggested_filename(self, url: str) -> None:
        if self._filename_was_edited:
            return
        self.filename_edit.setText(guess_filename(url))

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Download Folder",
            self.folder_edit.text(),
        )
        if folder:
            self.folder_edit.setText(folder)

    def _validate_and_accept(self) -> None:
        valid, error = validate_download_url(self.url_edit.text())
        if not valid:
            QMessageBox.warning(self, "Invalid URL", error)
            self.url_edit.setFocus()
            return

        filename = sanitize_filename(self.filename_edit.text())
        if not filename:
            QMessageBox.warning(self, "Invalid File Name", "Enter a file name.")
            self.filename_edit.setFocus()
            return
        self.filename_edit.setText(filename)

        folder_text = self.folder_edit.text().strip()
        if not folder_text:
            QMessageBox.warning(
                self,
                "Invalid Folder",
                "Choose a folder for the downloaded file.",
            )
            return

        folder = Path(folder_text).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(
                self,
                "Folder Error",
                f"SDM could not create or access this folder:\n{error}",
            )
            return

        if not is_valid_sha256(self.checksum_edit.text()):
            QMessageBox.warning(
                self,
                "Invalid SHA-256",
                "SHA-256 must contain exactly 64 hexadecimal characters.",
            )
            self.checksum_edit.setFocus()
            return

        if (
            self.schedule_checkbox.isChecked()
            and self.schedule_datetime.dateTime().toSecsSinceEpoch()
            <= QDateTime.currentDateTime().toSecsSinceEpoch()
        ):
            QMessageBox.warning(
                self,
                "Invalid Schedule",
                "Choose a future date and time for the download.",
            )
            self.schedule_datetime.setFocus()
            return

        self.accept()
