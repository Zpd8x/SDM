from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
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
from sdm.ui.icons import application_icon
from sdm.utils import guess_filename, sanitize_filename, validate_download_url


class AddDownloadDialog(QDialog):
    def __init__(self, parent=None, *, default_connections: int = 4) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Download")
        self.setWindowIcon(application_icon())
        self.setMinimumWidth(620)
        self._filename_was_edited = False

        title = QLabel("Add a new download")
        title.setObjectName("sectionTitle")
        help_text = QLabel(
            "Paste a direct HTTP or HTTPS file URL. SDM will preserve partial "
            "data if the transfer is interrupted."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #93a1b7;")

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        self.url_edit.textChanged.connect(self._update_suggested_filename)

        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("file.zip")
        self.filename_edit.textEdited.connect(self._mark_filename_edited)

        self.folder_edit = QLineEdit(str(default_download_folder()))
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_folder)

        folder_layout = QHBoxLayout()
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.addWidget(self.folder_edit, 1)
        folder_layout.addWidget(browse_button)

        self.connections_combo = QComboBox()
        for value in (1, 2, 4, 8, 16):
            label = "1 connection" if value == 1 else f"{value} connections"
            self.connections_combo.addItem(label, value)
        selected_index = self.connections_combo.findData(default_connections)
        self.connections_combo.setCurrentIndex(
            selected_index if selected_index >= 0 else 2
        )
        self.connections_combo.setToolTip(
            "SDM automatically falls back to one connection when the "
            "server does not support byte ranges."
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(12)
        form.addRow("URL:", self.url_edit)
        form.addRow("File name:", self.filename_edit)
        form.addRow("Save to:", folder_layout)
        form.addRow("Connections:", self.connections_combo)

        self.category_combo = QComboBox()
        self.category_combo.addItem("Auto detect", "Auto")
        for category in DOWNLOAD_CATEGORIES:
            self.category_combo.addItem(category, category)
        form.addRow("Category:", self.category_combo)

        self.checksum_edit = QLineEdit()
        self.checksum_edit.setPlaceholderText(
            "Optional: expected 64-character SHA-256"
        )
        self.checksum_edit.setMaxLength(64)
        self.checksum_edit.setToolTip(
            "When provided, SDM verifies the completed file before marking "
            "the download as completed."
        )
        form.addRow("SHA-256:", self.checksum_edit)

        self.start_checkbox = QCheckBox("Start download immediately")
        self.start_checkbox.setChecked(True)
        self.schedule_checkbox = QCheckBox("Schedule for later")
        self.schedule_datetime = QDateTimeEdit(
            QDateTime.currentDateTime().addSecs(300)
        )
        self.schedule_datetime.setCalendarPopup(True)
        self.schedule_datetime.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.schedule_datetime.setMinimumDateTime(
            QDateTime.currentDateTime().addSecs(60)
        )
        self.schedule_datetime.setEnabled(False)
        self.schedule_checkbox.toggled.connect(self._schedule_toggled)

        schedule_layout = QHBoxLayout()
        schedule_layout.setContentsMargins(0, 0, 0, 0)
        schedule_layout.addWidget(self.schedule_checkbox)
        schedule_layout.addWidget(self.schedule_datetime)
        schedule_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add Download")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(help_text)
        layout.addSpacing(4)
        layout.addLayout(form)
        layout.addWidget(self.start_checkbox)
        layout.addLayout(schedule_layout)
        layout.addSpacing(6)
        layout.addWidget(buttons)

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
