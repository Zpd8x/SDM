from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QFileInfo, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileIconProvider,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from sdm.ui.icons import application_icon
from sdm.ui.window_activation import configure_attention_window
from sdm.utils import format_bytes


class DownloadCompleteDialog(QDialog):
    def __init__(
        self,
        *,
        url: str,
        final_path: str | Path,
        downloaded_bytes: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.final_path = Path(final_path)
        self.setWindowTitle("Download complete")
        self.setWindowIcon(application_icon())
        self.setMinimumWidth(600)
        self.setModal(True)
        configure_attention_window(self, application_modal=True)

        file_size = max(0, int(downloaded_bytes))
        if file_size <= 0:
            try:
                file_size = self.final_path.stat().st_size
            except OSError:
                file_size = 0

        icon_label = QLabel()
        icon_label.setFixedSize(58, 58)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        provider = QFileIconProvider()
        icon_label.setPixmap(
            provider.icon(QFileInfo(str(self.final_path))).pixmap(48, 48)
        )

        title = QLabel("Download complete")
        title.setObjectName("sectionTitle")
        summary = QLabel(
            f"Downloaded {format_bytes(file_size)} ({file_size} Bytes)"
        )
        summary.setStyleSheet("color: #9eabc0;")
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(title)
        heading.addWidget(summary)

        header_layout = QHBoxLayout()
        header_layout.addWidget(icon_label)
        header_layout.addLayout(heading, 1)

        self.url_edit = QLineEdit(url)
        self.url_edit.setReadOnly(True)
        self.path_edit = QLineEdit(str(self.final_path))
        self.path_edit.setReadOnly(True)

        form = QGridLayout()
        form.setVerticalSpacing(8)
        form.addWidget(QLabel("Address"), 0, 0)
        form.addWidget(self.url_edit, 1, 0)
        form.addWidget(QLabel("The file saved as"), 2, 0)
        form.addWidget(self.path_edit, 3, 0)

        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("primaryButton")
        self.open_button.clicked.connect(self._open_file)
        self.open_with_button = QPushButton("Open with…")
        self.open_with_button.clicked.connect(self._open_with)
        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.clicked.connect(self._open_folder)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.open_button)
        button_layout.addWidget(self.open_with_button)
        button_layout.addWidget(self.open_folder_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #303b50;")

        self.dont_show_again_checkbox = QCheckBox(
            "Don't show this dialog again"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addLayout(header_layout)
        root.addWidget(separator)
        root.addLayout(form)
        root.addSpacing(4)
        root.addLayout(button_layout)
        root.addWidget(self.dont_show_again_checkbox)

        self.open_button.setDefault(True)
        self.open_button.setFocus()

    @property
    def dont_show_again(self) -> bool:
        return self.dont_show_again_checkbox.isChecked()

    def _open_file(self) -> None:
        if self._open_url(self.final_path):
            self.accept()

    def _open_folder(self) -> None:
        if self._open_url(self.final_path.parent):
            self.accept()

    def _open_with(self) -> None:
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    [
                        "rundll32.exe",
                        "shell32.dll,OpenAs_RunDLL",
                        str(self.final_path),
                    ],
                    close_fds=True,
                )
            elif not self._open_url(self.final_path):
                return
        except OSError as error:
            QMessageBox.warning(
                self,
                "Open With Failed",
                f"Windows could not open the app chooser.\n\n{error}",
            )
            return
        self.accept()

    def _open_url(self, path: Path) -> bool:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            return True
        QMessageBox.warning(
            self,
            "Open Failed",
            f"Windows could not open:\n{path}",
        )
        return False
