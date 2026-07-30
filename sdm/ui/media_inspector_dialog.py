from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from sdm.config import default_download_folder
from sdm.media_inspector import MediaInspection, MediaInspectionError, inspect_media
from sdm.ui.icons import application_icon
from sdm.utils import format_bytes, sanitize_filename


class _InspectorThread(QThread):
    completed = Signal(object)
    failed = Signal(str)
    def __init__(self, url: str, parent=None):
        super().__init__(parent); self.url = url
    def run(self):
        try: self.completed.emit(inspect_media(self.url))
        except MediaInspectionError as error: self.failed.emit(str(error))


class MediaInspectorDialog(QDialog):
    def __init__(self, parent=None, *, initial_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Media Inspector")
        self.setWindowIcon(application_icon())
        self.resize(980, 650)
        self.inspection: MediaInspection | None = None
        self._thread = None

        self.url_edit = QLineEdit(initial_url)
        self.url_edit.setPlaceholderText("Paste a public video, audio, or playlist URL")
        self.inspect_button = QPushButton("Inspect")
        self.inspect_button.clicked.connect(self._inspect)
        top = QHBoxLayout(); top.addWidget(self.url_edit, 1); top.addWidget(self.inspect_button)

        self.summary = QLabel("Inspect a media URL to list its available streams.")
        self.summary.setWordWrap(True)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["ID", "Kind", "Resolution", "FPS", "Ext", "Video codec", "Audio codec", "Bitrate", "Size", "Protocol"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.mode_combo = QComboBox(); self.mode_combo.addItem("Selected format", "selected"); self.mode_combo.addItem("Best video + audio", "video"); self.mode_combo.addItem("Best audio", "audio")
        self.folder_edit = QLineEdit(str(default_download_folder()))
        browse = QPushButton("Browse…"); browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout(); folder_row.addWidget(self.folder_edit, 1); folder_row.addWidget(browse)
        form = QFormLayout(); form.addRow("Download mode:", self.mode_combo); form.addRow("Save to:", folder_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add to SDM")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._accept_selection); buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self); layout.addLayout(top); layout.addWidget(self.summary); layout.addWidget(self.table, 1); layout.addLayout(form); layout.addWidget(buttons)
        if initial_url: self._inspect()

    @property
    def download_data(self) -> dict[str, str]:
        assert self.inspection is not None
        mode = str(self.mode_combo.currentData())
        format_id = ""
        media_kind = "video"
        if mode == "selected":
            row = self.table.currentRow()
            if row >= 0:
                format_id = self.table.item(row, 0).text()
                kind = self.table.item(row, 1).text()
                media_kind = "audio" if kind == "Audio only" else "video"
        elif mode == "audio": media_kind = "audio"
        title = sanitize_filename(self.inspection.title) or "media"
        return {"url": self.inspection.url, "filename": title, "folder": self.folder_edit.text().strip(), "media_kind": media_kind, "media_format": format_id}

    def _inspect(self):
        url = self.url_edit.text().strip()
        if not url: return
        self.inspect_button.setEnabled(False); self.summary.setText("Inspecting media streams…"); self.table.setRowCount(0); self.ok_button.setEnabled(False)
        self._thread = _InspectorThread(url, self); self._thread.completed.connect(self._loaded); self._thread.failed.connect(self._failed); self._thread.finished.connect(lambda: self.inspect_button.setEnabled(True)); self._thread.start()

    def _loaded(self, result):
        self.inspection = result
        live = " • LIVE" if result.is_live else ""
        playlist = f" • Playlist ({result.entries} entries)" if result.is_playlist else ""
        drm = " • DRM/protected" if result.drm else ""
        self.summary.setText(f"{result.title} • {result.extractor}{live}{playlist}{drm} • {len(result.formats)} formats • {len(result.subtitles)} subtitle tracks")
        self.table.setRowCount(len(result.formats))
        for row, fmt in enumerate(result.formats):
            values = [fmt.format_id, fmt.kind, fmt.resolution, str(fmt.fps or ""), fmt.extension, fmt.video_codec, fmt.audio_codec, f"{fmt.bitrate_kbps:.0f} kb/s" if fmt.bitrate_kbps else "", format_bytes(fmt.size_bytes) if fmt.size_bytes else "Unknown", fmt.protocol]
            for col, value in enumerate(values): self.table.setItem(row, col, QTableWidgetItem(value))
        if result.formats: self.table.selectRow(0)
        self.ok_button.setEnabled(result.downloadable)

    def _failed(self, message): self.summary.setText("Inspection failed."); QMessageBox.critical(self, "Media inspection failed", message)
    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.folder_edit.text())
        if folder: self.folder_edit.setText(folder)
    def _accept_selection(self):
        if not self.inspection or not self.inspection.downloadable: return
        folder = Path(self.folder_edit.text().strip()).expanduser()
        try: folder.mkdir(parents=True, exist_ok=True)
        except OSError as error: QMessageBox.critical(self, "Folder Error", str(error)); return
        self.accept()
