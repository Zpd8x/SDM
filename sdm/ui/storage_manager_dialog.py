from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView
)

from sdm.storage_intelligence import build_storage_report, duplicate_groups, scan_completed_records
from sdm.utils import format_bytes


class _ScanThread(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self._stop = False

    def request_stop(self):
        self._stop = True

    def run(self):
        try:
            report = scan_completed_records(
                self.repository,
                progress=lambda current, total, record: self.progress.emit(current, total, record.filename),
                stop_requested=lambda: self._stop,
            )
            self.completed.emit(report)
        except Exception as exc:
            self.failed.emit(str(exc))


class StorageManagerDialog(QDialog):
    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.worker = None
        self.setWindowTitle("Duplicate Manager & Storage Intelligence")
        self.resize(920, 560)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["SHA-256", "Copies", "Reclaimable", "Keep", "Locations"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        self.scan_button = QPushButton("Scan old downloads")
        self.scan_button.clicked.connect(self._scan)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self.scan_button)
        row.addWidget(refresh)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        records = self.repository.list_all()
        report = build_storage_report(records)
        self.summary.setText(
            f"Tracked: {report.tracked_files}  •  Existing: {report.existing_files}  •  "
            f"Missing: {report.missing_files}  •  Modified size: {report.modified_files}  •  "
            f"Duplicate groups: {report.duplicate_groups}  •  Recoverable: {format_bytes(report.reclaimable_bytes)}"
        )
        groups = duplicate_groups(records)
        self.table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            keeper = group.records[0]
            values = [
                group.sha256[:16] + "…",
                str(len(group.records)),
                format_bytes(group.reclaimable_bytes),
                keeper.filename,
                "\n".join(str(path) for path in group.existing_paths),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeRowsToContents()

    def _scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.scan_button.setText("Stopping…")
            return
        self.worker = _ScanThread(self.repository, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_complete)
        self.worker.failed.connect(self._on_error)
        self.scan_button.setText("Stop scan")
        self.worker.start()

    def _on_progress(self, current, total, filename):
        self.progress.setValue(int(current * 100 / max(1, total)))
        self.progress.setFormat(f"{current}/{total} — {filename}")

    def _on_complete(self, _report):
        self.scan_button.setText("Scan old downloads")
        self.progress.setValue(100)
        self.refresh()

    def _on_error(self, message):
        self.scan_button.setText("Scan old downloads")
        QMessageBox.warning(self, "Storage scan", message)
