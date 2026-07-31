from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from sdm.config import default_download_folder
from sdm.intelligent_analysis import analyze_link
from sdm.models import DownloadRecord
from sdm.ui.icons import application_icon
from sdm.utils import format_bytes, validate_download_url


class _BatchAnalysisThread(QThread):
    item_ready = Signal(int, object)
    item_failed = Signal(int, str)

    def __init__(self, urls: list[str], folder: str, records, parent=None) -> None:
        super().__init__(parent)
        self.urls = urls
        self.folder = folder
        self.records = tuple(records)

    def run(self) -> None:
        for index, url in enumerate(self.urls):
            try:
                result = analyze_link(url, folder=self.folder, records=self.records, timeout=5.0)
            except Exception as error:
                self.item_failed.emit(index, " ".join(str(error).split()) or error.__class__.__name__)
            else:
                self.item_ready.emit(index, result)


class BatchPreviewDialog(QDialog):
    def __init__(self, parent=None, *, existing_records=()) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Preview")
        self.setWindowIcon(application_icon())
        self.setMinimumSize(880, 600)
        self._records: tuple[DownloadRecord, ...] = tuple(existing_records)
        self._results: dict[int, object] = {}
        self._thread: _BatchAnalysisThread | None = None

        title = QLabel("Batch Preview")
        title.setObjectName("sectionTitle")
        info = QLabel("Paste one HTTP or HTTPS link per line. Analyze the list, review duplicates and add only checked items.")
        info.setWordWrap(True)
        info.setObjectName("summaryText")

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("https://example.com/file-1.zip\nhttps://example.com/file-2.iso")
        self.input_edit.setMaximumHeight(130)

        self.analyze_button = QPushButton("Analyze all")
        self.analyze_button.setObjectName("primaryButton")
        self.analyze_button.clicked.connect(self._start_analysis)
        self.status_label = QLabel("No links analyzed.")

        top_actions = QHBoxLayout()
        top_actions.addWidget(self.analyze_button)
        top_actions.addWidget(self.status_label, 1)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("Add", "Title / file", "Platform", "Type", "Size", "Duplicate", "Status"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 52)
        self.table.setColumnWidth(1, 260)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 115)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add selected")
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(self.input_edit)
        layout.addLayout(top_actions)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)

    @property
    def selected_downloads(self) -> list[dict[str, object]]:
        selected: list[dict[str, object]] = []
        folder = str(default_download_folder())
        for row, result in sorted(self._results.items()):
            item = self.table.item(row, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            selected.append({
                "url": result.url,
                "filename": result.filename,
                "folder": folder,
                "connections": min(4, max(1, result.connection_limit)),
                "start_immediately": True,
                "category": "Auto",
                "scheduled_at": "",
                "checksum_sha256": "",
            })
        return selected

    def _urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for raw in self.input_edit.toPlainText().splitlines():
            url = raw.strip()
            if not url or url in seen:
                continue
            valid, _ = validate_download_url(url)
            if valid:
                seen.add(url)
                urls.append(url)
        return urls

    def _start_analysis(self) -> None:
        urls = self._urls()
        if not urls:
            QMessageBox.warning(self, "No valid links", "Paste at least one valid HTTP or HTTPS link.")
            return
        self._results.clear()
        self.table.setRowCount(len(urls))
        for row, url in enumerate(urls):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(url))
            self.table.setItem(row, 6, QTableWidgetItem("Analyzing…"))
        self.analyze_button.setEnabled(False)
        self.status_label.setText(f"Analyzing 0/{len(urls)}…")
        self._thread = _BatchAnalysisThread(urls, str(default_download_folder()), self._records, self)
        self._thread.item_ready.connect(self._item_ready)
        self._thread.item_failed.connect(self._item_failed)
        self._thread.finished.connect(self._analysis_finished)
        self._thread.start()

    def _item_ready(self, row: int, result) -> None:
        self._results[row] = result
        duplicate = "No"
        if result.duplicate is not None:
            duplicate = result.duplicate.kind.replace("_", " ").title()
        values = (
            result.filename or result.url,
            result.platform,
            result.link_kind,
            format_bytes(result.total_bytes) if result.total_bytes else "Unknown",
            duplicate,
            result.warning or "Ready",
        )
        for column, value in enumerate(values, start=1):
            self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked if result.warning or result.duplicate else Qt.CheckState.Checked)
        self.status_label.setText(f"Analyzed {len(self._results)}/{self.table.rowCount()}…")

    def _item_failed(self, row: int, error: str) -> None:
        self.table.setItem(row, 6, QTableWidgetItem(f"Failed: {error}"))

    def _analysis_finished(self) -> None:
        self.analyze_button.setEnabled(True)
        ready = sum(1 for row in self._results if self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
        self.status_label.setText(f"Analysis complete — {ready} item(s) selected.")

    def _accept_selected(self) -> None:
        if not self.selected_downloads:
            QMessageBox.information(self, "Nothing selected", "Select at least one analyzed item to add.")
            return
        self.accept()
