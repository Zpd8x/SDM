from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

from PySide6.QtCore import QByteArray, QThread, Signal, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSplitter, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from sdm.config import default_download_folder
from sdm.media_inspector import (
    MediaInspection, MediaInspectionError, encode_media_options, inspect_media,
)
from sdm.ui.icons import application_icon
from sdm.utils import format_bytes, sanitize_filename


class _InspectorThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.completed.emit(inspect_media(self.url))
        except MediaInspectionError as error:
            self.failed.emit(str(error))


class _ThumbnailThread(QThread):
    completed = Signal(bytes)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            request = Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=12) as response:
                data = response.read(8 * 1024 * 1024)
            if data:
                self.completed.emit(data)
        except Exception:
            pass


def _duration_text(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


class MediaInspectorDialog(QDialog):
    """Smart Media Center: inspect metadata, formats and subtitle tracks before adding."""

    def __init__(self, parent=None, *, initial_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Smart Media Center")
        self.setWindowIcon(application_icon())
        self.resize(1120, 760)
        self.setMinimumSize(820, 560)
        self.inspection: MediaInspection | None = None
        self._thread = None
        self._thumbnail_thread = None

        self.url_edit = QLineEdit(initial_url)
        self.url_edit.setPlaceholderText("Paste a public video, audio, or playlist URL")
        self.url_edit.returnPressed.connect(self._inspect)
        self.inspect_button = QPushButton("Analyze media")
        self.inspect_button.clicked.connect(self._inspect)
        top = QHBoxLayout()
        top.addWidget(self.url_edit, 1)
        top.addWidget(self.inspect_button)

        self.thumbnail = QLabel("No preview")
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setMinimumSize(300, 170)
        self.thumbnail.setMaximumHeight(260)
        self.thumbnail.setStyleSheet("QLabel { background:#111821; border:1px solid #263443; border-radius:8px; color:#7f8c98; }")

        self.title_label = QLabel("Analyze a media URL to view its available streams.")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size:18px; font-weight:600;")
        self.meta_label = QLabel("Metadata will appear here.")
        self.meta_label.setWordWrap(True)
        self.meta_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_box = QVBoxLayout()
        summary_box.addWidget(self.title_label)
        summary_box.addWidget(self.meta_label)
        summary_box.addStretch(1)
        summary_widget = QWidget()
        summary_widget.setLayout(summary_box)

        preview_split = QSplitter(Qt.Orientation.Horizontal)
        preview_split.addWidget(self.thumbnail)
        preview_split.addWidget(summary_widget)
        preview_split.setStretchFactor(0, 0)
        preview_split.setStretchFactor(1, 1)
        preview_split.setSizes([340, 650])

        self.tabs = QTabWidget()
        self.formats_tab = QWidget()
        self.subtitles_tab = QWidget()
        self.details_tab = QWidget()
        self.tabs.addTab(self.formats_tab, "Formats")
        self.tabs.addTab(self.subtitles_tab, "Subtitles")
        self.tabs.addTab(self.details_tab, "Details")

        self.kind_filter = QComboBox()
        self.kind_filter.addItem("All streams", "all")
        self.kind_filter.addItem("Video + audio", "muxed")
        self.kind_filter.addItem("Video only", "video")
        self.kind_filter.addItem("Audio only", "audio")
        self.kind_filter.currentIndexChanged.connect(self._populate_formats)
        self.quality_filter = QComboBox()
        self.quality_filter.addItem("All qualities", 0)
        for label, value in (("4K+", 2160), ("1440p+", 1440), ("1080p+", 1080), ("720p+", 720)):
            self.quality_filter.addItem(label, value)
        self.quality_filter.currentIndexChanged.connect(self._populate_formats)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Stream:"))
        filters.addWidget(self.kind_filter)
        filters.addWidget(QLabel("Quality:"))
        filters.addWidget(self.quality_filter)
        filters.addStretch(1)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "ID", "Kind", "Resolution", "FPS", "Ext", "Video codec",
            "Audio codec", "Bitrate", "Size", "Language", "Protocol",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        formats_layout = QVBoxLayout(self.formats_tab)
        formats_layout.addLayout(filters)
        formats_layout.addWidget(self.table, 1)

        self.subtitle_table = QTableWidget(0, 4)
        self.subtitle_table.setHorizontalHeaderLabels(["Language", "Name", "Type", "Formats"])
        self.subtitle_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.subtitle_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.subtitle_table.horizontalHeader().setStretchLastSection(True)
        subtitle_layout = QVBoxLayout(self.subtitles_tab)
        subtitle_layout.addWidget(self.subtitle_table)

        self.details_label = QLabel("No media has been analyzed.")
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        details_layout = QVBoxLayout(self.details_tab)
        details_layout.addWidget(self.details_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Smart recommended", "smart")
        self.mode_combo.addItem("Selected format", "selected")
        self.mode_combo.addItem("Best video + audio", "video")
        self.mode_combo.addItem("Best audio", "audio")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)

        self.container_combo = QComboBox()
        self.container_combo.addItem("Automatic", "auto")
        self.container_combo.addItem("MP4 (best compatibility)", "mp4")
        self.container_combo.addItem("MKV (best flexibility)", "mkv")
        self.container_combo.addItem("WebM", "webm")

        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItem("Original stream", "original")
        self.audio_format_combo.addItem("MP3 · 192 kb/s", "mp3")
        self.audio_format_combo.addItem("M4A · 192 kb/s", "m4a")
        self.audio_format_combo.addItem("Opus · 192 kb/s", "opus")
        self.audio_format_combo.addItem("FLAC (lossless)", "flac")

        self.subtitle_mode_combo = QComboBox()
        self.subtitle_mode_combo.addItem("Do not download", "none")
        self.subtitle_mode_combo.addItem("Manual subtitles", "manual")
        self.subtitle_mode_combo.addItem("Automatic captions", "automatic")
        self.subtitle_mode_combo.addItem("Manual + automatic", "all")
        self.subtitle_mode_combo.currentIndexChanged.connect(self._subtitle_mode_changed)
        self.subtitle_language_combo = QComboBox()
        self.subtitle_language_combo.addItem("All available languages", "all")
        self.subtitle_language_combo.setEnabled(False)
        self.embed_subtitles = QCheckBox("Embed subtitles into the media file")
        self.embed_subtitles.setChecked(True)
        self.embed_subtitles.setEnabled(False)

        self.embed_thumbnail = QCheckBox("Embed thumbnail when supported")
        self.embed_thumbnail.setChecked(True)
        self.embed_metadata = QCheckBox("Write title, artist and source metadata")
        self.embed_metadata.setChecked(True)
        self.embed_chapters = QCheckBox("Keep chapter markers")
        self.embed_chapters.setChecked(True)
        self.folder_edit = QLineEdit(str(default_download_folder()))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        options_group = QGroupBox("Download options")
        form = QFormLayout(options_group)
        form.addRow("Selection:", self.mode_combo)
        form.addRow("Container:", self.container_combo)
        form.addRow("Audio conversion:", self.audio_format_combo)
        form.addRow("Subtitles:", self.subtitle_mode_combo)
        form.addRow("Subtitle language:", self.subtitle_language_combo)
        form.addRow("", self.embed_subtitles)
        form.addRow("Save to:", folder_row)
        form.addRow("", self.embed_thumbnail)
        form.addRow("", self.embed_metadata)
        form.addRow("", self.embed_chapters)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add to SDM")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(preview_split)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(options_group)
        layout.addWidget(buttons)
        self._mode_changed()
        self._subtitle_mode_changed()
        if initial_url:
            self._inspect()

    @property
    def download_data(self) -> dict[str, str]:
        assert self.inspection is not None
        mode = str(self.mode_combo.currentData())
        format_id = ""
        media_kind = "video"
        if mode == "selected":
            row = self.table.currentRow()
            if row >= 0:
                item = self.table.item(row, 0)
                format_id = item.text() if item else ""
                kind_item = self.table.item(row, 1)
                kind = kind_item.text() if kind_item else ""
                media_kind = "audio" if kind == "Audio only" else "video"
        elif mode == "audio":
            media_kind = "audio"
        elif mode == "smart":
            media_kind = "video"
            format_id = self._smart_selector()
        title = sanitize_filename(self.inspection.title) or "media"
        encoded_options = encode_media_options(
            selector=format_id,
            container=str(self.container_combo.currentData()),
            audio_format=str(self.audio_format_combo.currentData()),
            thumbnail=self.embed_thumbnail.isChecked(),
            metadata=self.embed_metadata.isChecked(),
            chapters=self.embed_chapters.isChecked(),
            subtitle_mode=str(self.subtitle_mode_combo.currentData()),
            subtitle_language=str(self.subtitle_language_combo.currentData()),
            embed_subtitles=self.embed_subtitles.isChecked(),
        )
        return {
            "url": self.inspection.url,
            "filename": title,
            "folder": self.folder_edit.text().strip(),
            "media_kind": media_kind,
            "media_format": encoded_options,
            "thumbnail": "1" if self.embed_thumbnail.isChecked() else "0",
        }

    def _inspect(self):
        url = self.url_edit.text().strip()
        if not url:
            return
        self.inspect_button.setEnabled(False)
        self.title_label.setText("Analyzing media…")
        self.meta_label.setText("Reading metadata, formats, subtitles and availability.")
        self.table.setRowCount(0)
        self.subtitle_table.setRowCount(0)
        self.ok_button.setEnabled(False)
        self.thumbnail.clear()
        self.thumbnail.setText("Loading preview…")
        self._thread = _InspectorThread(url, self)
        self._thread.completed.connect(self._loaded)
        self._thread.failed.connect(self._failed)
        self._thread.finished.connect(lambda: self.inspect_button.setEnabled(True))
        self._thread.start()

    def _loaded(self, result):
        self.inspection = result
        live = "LIVE" if result.is_live else "On demand"
        playlist = f"Playlist · {result.entries} entries" if result.is_playlist else "Single item"
        protection = "Protected / unavailable" if result.drm else "Downloadable"
        self.title_label.setText(result.title)
        self.meta_label.setText(
            f"{result.extractor}  •  {_duration_text(result.duration_seconds)}  •  {live}\n"
            f"{playlist}  •  {len(result.formats)} formats  •  {len(result.subtitles)} subtitle tracks  •  {protection}"
        )
        self.details_label.setText(
            f"Source URL\n{result.url}\n\nExtractor\n{result.extractor}\n\n"
            f"Duration\n{_duration_text(result.duration_seconds)}\n\n"
            f"Media type\n{'Playlist' if result.is_playlist else 'Single item'}\n\n"
            f"Live status\n{'Live stream' if result.is_live else 'Not live'}\n\n"
            f"Availability\n{'DRM or protected' if result.drm else 'Available for download'}\n\n"
            f"Thumbnail\n{result.thumbnail or 'Not provided'}"
        )
        self._populate_formats()
        self._populate_subtitles()
        self._populate_subtitle_languages()
        self.ok_button.setEnabled(result.downloadable)
        if result.thumbnail:
            self._thumbnail_thread = _ThumbnailThread(result.thumbnail, self)
            self._thumbnail_thread.completed.connect(self._thumbnail_loaded)
            self._thumbnail_thread.start()
        else:
            self.thumbnail.setText("No preview")

    def _populate_formats(self):
        if not self.inspection:
            return
        kind_filter = str(self.kind_filter.currentData())
        minimum_height = int(self.quality_filter.currentData() or 0)
        formats = []
        for fmt in self.inspection.formats:
            if kind_filter == "muxed" and fmt.kind != "Video + Audio":
                continue
            if kind_filter == "video" and not (fmt.has_video and not fmt.has_audio):
                continue
            if kind_filter == "audio" and fmt.kind != "Audio only":
                continue
            height = 0
            if "x" in fmt.resolution:
                try:
                    height = int(fmt.resolution.rsplit("x", 1)[1].split("p", 1)[0])
                except ValueError:
                    height = 0
            if minimum_height and height < minimum_height:
                continue
            formats.append(fmt)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(formats))
        for row, fmt in enumerate(formats):
            values = [
                fmt.format_id, fmt.kind, fmt.resolution + (" HDR" if fmt.hdr else ""),
                str(fmt.fps or ""), fmt.extension, fmt.video_codec, fmt.audio_codec,
                f"{fmt.bitrate_kbps:.0f} kb/s" if fmt.bitrate_kbps else "",
                format_bytes(fmt.size_bytes) if fmt.size_bytes else "Unknown",
                fmt.language or "—", fmt.protocol,
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.setSortingEnabled(True)
        if formats:
            self.table.selectRow(0)

    def _populate_subtitles(self):
        tracks = self.inspection.subtitles if self.inspection else []
        self.subtitle_table.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            values = [track.language, track.name, "Automatic" if track.automatic else "Manual", ", ".join(track.extensions) or "Unknown"]
            for col, value in enumerate(values):
                self.subtitle_table.setItem(row, col, QTableWidgetItem(value))

    def _thumbnail_loaded(self, data: bytes):
        pixmap = QPixmap()
        if pixmap.loadFromData(QByteArray(data)):
            self.thumbnail.setPixmap(pixmap.scaled(self.thumbnail.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.thumbnail.setText("Preview unavailable")

    def _mode_changed(self):
        mode = str(self.mode_combo.currentData())
        self.table.setEnabled(mode == "selected")
        self.audio_format_combo.setEnabled(mode == "audio")
        if mode != "audio":
            self.audio_format_combo.setCurrentIndex(0)

    def _subtitle_mode_changed(self):
        enabled = self.subtitle_mode_combo.currentData() != "none"
        self.subtitle_language_combo.setEnabled(enabled)
        self.embed_subtitles.setEnabled(enabled)

    def _populate_subtitle_languages(self):
        current = str(self.subtitle_language_combo.currentData() or "all")
        self.subtitle_language_combo.clear()
        self.subtitle_language_combo.addItem("All available languages", "all")
        seen = set()
        for track in (self.inspection.subtitles if self.inspection else []):
            if track.language in seen:
                continue
            seen.add(track.language)
            label = track.name if track.name and track.name != track.language else track.language
            self.subtitle_language_combo.addItem(f"{label} ({track.language})", track.language)
        index = self.subtitle_language_combo.findData(current)
        self.subtitle_language_combo.setCurrentIndex(max(0, index))

    def _smart_selector(self) -> str:
        """Prefer a compatible muxed stream, then merge best video and audio."""
        if not self.inspection:
            return "bestvideo*+bestaudio/best"
        muxed = [fmt for fmt in self.inspection.formats if fmt.has_video and fmt.has_audio]
        compatible = [
            fmt for fmt in muxed
            if fmt.extension == "mp4" and (fmt.video_codec.startswith(("avc", "h264")) or fmt.video_codec == "none")
        ]
        candidates = compatible or muxed
        if candidates:
            def score(fmt):
                height = 0
                if "x" in fmt.resolution:
                    try:
                        height = int(fmt.resolution.rsplit("x", 1)[1].split("p", 1)[0])
                    except ValueError:
                        pass
                return (height, fmt.bitrate_kbps, fmt.size_bytes)
            return max(candidates, key=score).format_id
        return "bestvideo*+bestaudio/best"

    def _failed(self, message):
        self.title_label.setText("Media analysis failed")
        self.meta_label.setText(message)
        self.thumbnail.setText("No preview")
        QMessageBox.critical(self, "Smart Media Center", message)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def _accept_selection(self):
        if not self.inspection or not self.inspection.downloadable:
            return
        if self.mode_combo.currentData() == "selected" and self.table.currentRow() < 0:
            QMessageBox.information(self, "Select a format", "Choose a media format or use an automatic Best mode.")
            return
        folder = Path(self.folder_edit.text().strip()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(self, "Folder Error", str(error))
            return
        self.accept()
