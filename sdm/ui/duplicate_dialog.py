from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from sdm.duplicate_intelligence import (
    DuplicateDisposition,
    DuplicateMatch,
)
from sdm.ui.icons import application_icon
from sdm.utils import format_bytes


class DuplicateDownloadDialog(QDialog):
    ACTION_CANCEL = "cancel"
    ACTION_FOCUS = "focus"
    ACTION_RESUME = "resume"
    ACTION_OPEN = "open"
    ACTION_COPY = "copy"

    def __init__(self, match: DuplicateMatch, parent=None) -> None:
        super().__init__(parent)
        self.match = match
        self.result_action = self.ACTION_CANCEL
        record = match.record

        self.setWindowTitle("Duplicate Download")
        self.setWindowIcon(application_icon())
        self.setMinimumWidth(520)

        title = QLabel("SDM found this download already")
        title.setObjectName("sectionTitle")
        explanation = QLabel(match.explanation)
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color: #93a1b7;")
        size = format_bytes(record.total_bytes) if record.total_bytes else "Unknown"
        details = QLabel(
            f"File: {record.filename}\n"
            f"Status: {record.status.value.title()}\n"
            f"Size: {size}\n"
            f"Folder: {record.folder}"
        )
        details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        details.setStyleSheet(
            "background: #151b25; border: 1px solid #303b50; "
            "padding: 12px;"
        )

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        copy_button = QPushButton("Add as Copy")
        copy_button.clicked.connect(
            lambda: self._finish(self.ACTION_COPY)
        )
        button_layout.addWidget(copy_button)

        if match.disposition == DuplicateDisposition.COMPLETED:
            primary = QPushButton("Open Existing")
            action = self.ACTION_OPEN
        elif match.disposition == DuplicateDisposition.RESUMABLE:
            primary = QPushButton("Resume Existing")
            action = self.ACTION_RESUME
        else:
            primary = QPushButton("Show Existing")
            action = self.ACTION_FOCUS
        primary.setObjectName("primaryButton")
        primary.clicked.connect(lambda: self._finish(action))
        button_layout.addWidget(primary)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(13)
        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addWidget(details)
        layout.addLayout(button_layout)

    def _finish(self, action: str) -> None:
        self.result_action = action
        self.accept()
