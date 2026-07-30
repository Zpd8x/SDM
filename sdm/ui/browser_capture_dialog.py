from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileInfo, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFileIconProvider,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from sdm.categories import (
    DOWNLOAD_CATEGORIES,
    category_folder_setting_key,
)
from sdm.database import DownloadRepository
from sdm.models import DownloadRecord
from sdm.session_auth import session_auth_path
from sdm.site_adapters import (
    ADAPTER_DIRECT,
    ADAPTER_LABELS,
    recommended_connection_limit,
)
from sdm.ui.icons import application_icon
from sdm.ui.window_activation import configure_attention_window
from sdm.utils import format_bytes, sanitize_filename, validate_download_url


class BrowserCaptureDialog(QDialog):
    ACTION_START = "start"
    ACTION_LATER = "later"
    ACTION_CANCEL = "cancel"

    def __init__(
        self,
        repository: DownloadRepository,
        record: DownloadRecord,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.record = record
        self.result_action = self.ACTION_CANCEL
        self._validated_path = record.final_path

        self.setWindowTitle("Download File Info")
        self.setWindowIcon(application_icon())
        configure_attention_window(self, application_modal=True)
        self.setMinimumWidth(720)
        self.setModal(True)

        title = QLabel("Download File Info")
        title.setObjectName("sectionTitle")
        source_text = (
            "Captured media page from your browser"
            if record.media_kind != "direct"
            else "Captured from your browser"
        )
        if session_auth_path(repository.database_path, record.id).exists():
            source_text += "  •  Secure browser session protected"
        if record.site_adapter != ADAPTER_DIRECT:
            source_text += (
                "  •  Smart adapter: "
                + ADAPTER_LABELS.get(record.site_adapter, record.site_adapter)
            )
        if record.rule_reason:
            source_text += f"  •  {record.rule_reason}"
        source = QLabel(source_text)
        source.setStyleSheet("color: #65a5ff; font-weight: 600;")
        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title_column.addWidget(title)
        title_column.addWidget(source)

        icon_label = QLabel()
        icon_label.setFixedSize(58, 58)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        provider = QFileIconProvider()
        icon = provider.icon(QFileInfo(str(record.final_path)))
        icon_label.setPixmap(icon.pixmap(48, 48))

        size_text = (
            format_bytes(record.total_bytes)
            if record.total_bytes
            else "Size: detected when download starts"
        )
        self.size_label = QLabel(size_text)
        self.size_label.setStyleSheet("color: #aab7ca;")

        info_layout = QHBoxLayout()
        info_layout.addLayout(title_column, 1)
        info_layout.addWidget(icon_label)
        info_layout.addWidget(self.size_label)

        self.url_edit = QLineEdit(record.url)
        self.url_edit.setCursorPosition(0)
        self.url_edit.setToolTip(
            (
                "Media page address. SDM will extract a public video or audio "
                "stream when the download starts."
                if record.media_kind != "direct"
                else "Direct HTTP or HTTPS address captured by the browser."
            )
        )

        self.category_combo = QComboBox()
        for category in DOWNLOAD_CATEGORIES:
            self.category_combo.addItem(category, category)
        category_index = self.category_combo.findData(record.category)
        self.category_combo.setCurrentIndex(
            category_index if category_index >= 0 else len(DOWNLOAD_CATEGORIES) - 1
        )

        self.connections_combo = QComboBox()
        for value in (1, 2, 4, 8, 16):
            label = "1 connection" if value == 1 else f"{value} connections"
            self.connections_combo.addItem(label, value)
        connections_index = self.connections_combo.findData(record.connections)
        self.connections_combo.setCurrentIndex(
            connections_index if connections_index >= 0 else 2
        )

        category_row = QHBoxLayout()
        category_row.setContentsMargins(0, 0, 0, 0)
        category_row.addWidget(self.category_combo, 1)
        category_row.addSpacing(12)
        connection_label = "Connections:"
        if record.site_adapter != ADAPTER_DIRECT:
            connection_label = (
                "Connections "
                f"(smart max {recommended_connection_limit(record.site_adapter)}):"
            )
        category_row.addWidget(QLabel(connection_label))
        category_row.addWidget(self.connections_combo)

        self.save_as_edit = QLineEdit(str(record.final_path))
        self.save_as_edit.textChanged.connect(self._update_folder_preview)
        browse_button = QPushButton("…")
        browse_button.setFixedWidth(44)
        browse_button.setToolTip("Choose the output file and folder.")
        browse_button.clicked.connect(self._browse_save_as)

        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 0, 0, 0)
        save_row.addWidget(self.save_as_edit, 1)
        save_row.addWidget(browse_button)

        self.remember_path_checkbox = QCheckBox()
        self.folder_preview = QLineEdit(record.folder)
        self.folder_preview.setReadOnly(True)
        self.folder_preview.setToolTip(
            "The folder SDM will remember for the selected category."
        )
        remember_layout = QVBoxLayout()
        remember_layout.setContentsMargins(0, 0, 0, 0)
        remember_layout.setSpacing(7)
        remember_layout.addWidget(self.remember_path_checkbox)
        remember_layout.addWidget(self.folder_preview)

        self.description_edit = QLineEdit(record.description)
        self.description_edit.setPlaceholderText(
            "Optional note about this download"
        )
        self.description_edit.setMaxLength(500)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(12)
        form.addRow("URL:", self.url_edit)
        form.addRow("Category:", category_row)
        form.addRow("Save As:", save_row)
        form.addRow("", remember_layout)
        form.addRow("Description:", self.description_edit)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #303b50;")

        later_button = QPushButton("Download Later")
        later_button.clicked.connect(self._download_later)
        start_button = QPushButton("Start Download")
        start_button.setObjectName("primaryButton")
        start_button.clicked.connect(self._start_download)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.addWidget(later_button)
        button_layout.addStretch()
        button_layout.addWidget(start_button)
        button_layout.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        layout.addLayout(info_layout)
        layout.addWidget(separator)
        layout.addLayout(form)
        layout.addSpacing(4)
        layout.addLayout(button_layout)

        self.category_combo.currentIndexChanged.connect(
            self._category_changed
        )
        self._update_remember_label()
        self._category_changed()
        if record.auto_start:
            start_button.setDefault(True)
            start_button.setFocus()
        else:
            later_button.setDefault(True)
            later_button.setFocus()

    @property
    def download_data(self) -> dict[str, str | int]:
        return {
            "url": self.url_edit.text().strip(),
            "filename": self._validated_path.name,
            "folder": str(self._validated_path.parent),
            "category": str(self.category_combo.currentData()),
            "connections": int(self.connections_combo.currentData()),
            "description": self.description_edit.text().strip(),
        }

    def _browse_save_as(self) -> None:
        selected, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Download As",
            self.save_as_edit.text(),
        )
        if selected:
            self.save_as_edit.setText(selected)

    def _update_folder_preview(self, value: str) -> None:
        candidate = Path(value.strip()).expanduser()
        self.folder_preview.setText(str(candidate.parent))

    def _category_changed(self) -> None:
        self._update_remember_label()
        category = str(self.category_combo.currentData())
        remembered = self.repository.get_setting(
            category_folder_setting_key(category),
            "",
        ).strip()
        if remembered:
            current_name = sanitize_filename(
                Path(self.save_as_edit.text()).name,
                self.record.filename,
            )
            self.save_as_edit.setText(str(Path(remembered) / current_name))

    def _update_remember_label(self) -> None:
        category = str(self.category_combo.currentData())
        self.remember_path_checkbox.setText(
            f'Remember this path for "{category}" category'
        )

    def _start_download(self) -> None:
        if self._validate():
            self.result_action = self.ACTION_START
            self.accept()

    def _download_later(self) -> None:
        if self._validate():
            self.result_action = self.ACTION_LATER
            self.accept()

    def _validate(self) -> bool:
        valid, error = validate_download_url(self.url_edit.text())
        if not valid:
            QMessageBox.warning(self, "Invalid URL", error)
            self.url_edit.setFocus()
            return False

        save_text = self.save_as_edit.text().strip()
        if not save_text:
            QMessageBox.warning(
                self,
                "Invalid Save Path",
                "Choose the file name and folder for this download.",
            )
            self.save_as_edit.setFocus()
            return False

        requested_path = Path(save_text).expanduser()
        filename = sanitize_filename(
            requested_path.name,
            self.record.filename,
        )
        folder = requested_path.parent
        if not str(folder).strip():
            QMessageBox.warning(
                self,
                "Invalid Folder",
                "Choose a folder for this download.",
            )
            return False

        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(
                self,
                "Folder Error",
                "SDM could not create or access this folder.\n\n"
                f"{error}",
            )
            return False

        final_path = folder / filename
        target = str(final_path.resolve(strict=False)).casefold()
        for other in self.repository.list_all():
            if other.id == self.record.id:
                continue
            other_path = str(
                other.final_path.resolve(strict=False)
            ).casefold()
            if other_path == target:
                QMessageBox.warning(
                    self,
                    "Path Already Used",
                    "Another SDM download already uses this file path.\n"
                    "Choose a different file name.",
                )
                self.save_as_edit.setFocus()
                return False

        if final_path.exists() and final_path != self.record.final_path:
            QMessageBox.warning(
                self,
                "File Already Exists",
                "A file with this name already exists.\n"
                "Choose a different file name.",
            )
            self.save_as_edit.setFocus()
            return False

        self._validated_path = final_path
        self.save_as_edit.setText(str(final_path))
        if self.remember_path_checkbox.isChecked():
            category = str(self.category_combo.currentData())
            self.repository.set_setting(
                category_folder_setting_key(category),
                str(folder),
            )
        return True
