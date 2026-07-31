from __future__ import annotations

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHeaderView,
    QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from sdm.diagnostics import DiagnosticsService
from sdm.plugins import PluginManager


TOOL_NAMES = ("yt-dlp", "ffmpeg", "ffprobe", "ffplay")


class SystemCenterDialog(QDialog):
    """Responsive diagnostics and tools hub.

    v2.7.1 replaces the narrow action column with adaptive tool cards. This
    keeps paths readable and prevents controls from overlapping at small sizes.
    """

    def __init__(self, diagnostics: DiagnosticsService, plugins: PluginManager, parent=None):
        super().__init__(parent)
        self.diagnostics = diagnostics
        self.plugins = plugins
        self.tools_process: QProcess | None = None
        self.tool_cards: dict[str, dict[str, QWidget]] = {}
        self.setWindowTitle("SDM System Center")
        self.resize(980, 650)
        self.setMinimumSize(720, 500)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)
        title = QLabel("System Center — Diagnostics, Tools & Plugins")
        title.setObjectName("sectionTitle")
        root.addWidget(title)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_diagnostics_tab()
        self._build_tools_tab()
        self._build_plugins_tab()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh_diagnostics()
        self.refresh_plugins()

    def _build_diagnostics_tab(self) -> None:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.diag_table = QTableWidget(0, 3)
        self.diag_table.setHorizontalHeaderLabels(["Component", "Status", "Details"])
        self.diag_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.diag_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.diag_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.diag_table)
        actions = QHBoxLayout()
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh_diagnostics)
        export = QPushButton("Export report"); export.clicked.connect(self.export_report)
        actions.addWidget(refresh); actions.addWidget(export); actions.addStretch()
        layout.addLayout(actions)
        self.tabs.addTab(tab, "Diagnostics")

    def _build_tools_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        hint_box = QFrame(); hint_box.setObjectName("toolsHintCard")
        hint_layout = QVBoxLayout(hint_box); hint_layout.setContentsMargins(14, 11, 14, 11)
        hint = QLabel(
            "SDM keeps media tools inside the project Tools folder. "
            "Install or repair downloads and verifies the complete toolset."
        )
        hint.setWordWrap(True); hint.setObjectName("summaryText")
        hint_layout.addWidget(hint)
        layout.addWidget(hint_box)

        scroll = QScrollArea()
        scroll.setObjectName("toolsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tools_cards_host = QWidget()
        self.tools_cards_grid = QGridLayout(self.tools_cards_host)
        self.tools_cards_grid.setContentsMargins(0, 0, 0, 0)
        self.tools_cards_grid.setHorizontalSpacing(12)
        self.tools_cards_grid.setVerticalSpacing(12)
        scroll.setWidget(self.tools_cards_host)
        layout.addWidget(scroll, 1)

        self.tools_progress = QProgressBar()
        self.tools_progress.setRange(0, 100)
        self.tools_progress.setValue(0)
        self.tools_progress.hide()
        layout.addWidget(self.tools_progress)

        self.repair_tools_button = QPushButton("Install / Repair all tools")
        self.repair_tools_button.setObjectName("primaryButton")
        self.repair_tools_button.clicked.connect(self.install_or_repair_tools)
        layout.addWidget(self.repair_tools_button)

        secondary = QHBoxLayout()
        refresh = QPushButton("Refresh tools"); refresh.clicked.connect(self.refresh_diagnostics)
        open_folder = QPushButton("Open Tools folder"); open_folder.clicked.connect(self.open_tools_folder)
        secondary.addWidget(refresh)
        secondary.addWidget(open_folder)
        secondary.addStretch()
        layout.addLayout(secondary)
        self.tabs.addTab(tab, "Tools Manager")

    def _build_plugins_tab(self) -> None:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.plugin_table = QTableWidget(0, 6)
        self.plugin_table.setHorizontalHeaderLabels(["Plugin", "Version", "Enabled", "Loaded", "Capabilities", "Status"])
        self.plugin_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.plugin_table)
        actions = QHBoxLayout()
        enable = QPushButton("Enable selected"); enable.clicked.connect(lambda: self.set_selected_plugin(True))
        disable = QPushButton("Disable selected"); disable.clicked.connect(lambda: self.set_selected_plugin(False))
        reload_button = QPushButton("Reload list"); reload_button.clicked.connect(self.refresh_plugins)
        actions.addWidget(enable); actions.addWidget(disable); actions.addWidget(reload_button); actions.addStretch()
        layout.addLayout(actions)
        self.tabs.addTab(tab, "Plugins")

    def _rebuild_tool_cards(self, tools) -> None:
        while self.tools_cards_grid.count():
            item = self.tools_cards_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.tool_cards.clear()

        columns = 2 if self.width() >= 820 else 1
        for index, item in enumerate(tools):
            card = QFrame(); card.setObjectName("toolCard")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 13, 15, 13)
            card_layout.setSpacing(8)

            top = QHBoxLayout()
            name = QLabel(item.name)
            name.setObjectName("toolName")
            status = QLabel(item.status)
            status.setObjectName("toolStatus")
            status.setProperty("state", item.status.lower())
            top.addWidget(name)
            top.addStretch()
            top.addWidget(status)
            card_layout.addLayout(top)

            details = QLabel(item.details)
            details.setObjectName("toolDetails")
            details.setWordWrap(True)
            details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            details.setMinimumHeight(42)
            card_layout.addWidget(details)

            action_row = QHBoxLayout()
            action_row.addStretch()
            action = QPushButton("Repair" if item.status not in {"OK", "WARNING"} else "Recheck")
            action.setObjectName("compactButton")
            action.setMinimumWidth(92)
            action.clicked.connect(
                self.install_or_repair_tools
                if item.status not in {"OK", "WARNING"}
                else self.refresh_diagnostics
            )
            action_row.addWidget(action)
            card_layout.addLayout(action_row)

            row, col = divmod(index, columns)
            self.tools_cards_grid.addWidget(card, row, col)
            self.tool_cards[item.name] = {"card": card, "status": status, "details": details, "action": action}

        for col in range(columns):
            self.tools_cards_grid.setColumnStretch(col, 1)
        self.tools_cards_grid.setRowStretch((len(tools) + columns - 1) // columns, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "tools_cards_grid"):
            tools = [item for item in self.diagnostics.collect() if item.name in TOOL_NAMES]
            desired = 2 if event.size().width() >= 820 else 1
            current = 2 if self.tools_cards_grid.columnCount() >= 2 and self.tools_cards_grid.itemAtPosition(0, 1) else 1
            if desired != current:
                self._rebuild_tool_cards(tools)

    def install_or_repair_tools(self) -> None:
        script = self.diagnostics.root / "packaging" / "windows" / "download_tools.ps1"
        if not script.is_file():
            QMessageBox.warning(self, "SDM", f"Tools installer was not found:\n{script}")
            return
        self.repair_tools_button.setEnabled(False)
        self.repair_tools_button.setText("Installing tools…")
        self.tools_progress.show(); self.tools_progress.setRange(0, 0)
        self.tools_process = QProcess(self)
        self.tools_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.tools_process.setProgram("powershell.exe")
        self.tools_process.setArguments(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)])
        self.tools_process.setWorkingDirectory(str(self.diagnostics.root))
        self.tools_process.finished.connect(self._tools_install_finished)
        self.tools_process.errorOccurred.connect(self._tools_install_error)
        self.tools_process.start()

    def _tools_install_finished(self, exit_code: int, _exit_status) -> None:
        output = bytes(self.tools_process.readAll()).decode(errors="replace") if self.tools_process else ""
        self.repair_tools_button.setEnabled(True); self.repair_tools_button.setText("Install / Repair all tools")
        self.tools_progress.setRange(0, 100); self.tools_progress.setValue(100 if exit_code == 0 else 0); self.tools_progress.hide()
        self.refresh_diagnostics()
        if exit_code == 0:
            missing = [item.name for item in self.diagnostics.collect() if item.name in TOOL_NAMES and item.status != "OK"]
            if missing:
                QMessageBox.warning(self, "SDM", "Installer finished, but these tools are still unavailable:\n" + ", ".join(missing) + "\n\n" + output[-1200:])
            else:
                QMessageBox.information(self, "SDM", "All media tools were installed and detected successfully.")
        else:
            QMessageBox.critical(self, "SDM", f"Tools installation failed (code {exit_code}):\n\n{output[-1800:]}")
        self.tools_process = None

    def _tools_install_error(self, error) -> None:
        if self.tools_process and self.tools_process.state() != QProcess.ProcessState.NotRunning:
            return
        self.repair_tools_button.setEnabled(True); self.repair_tools_button.setText("Install / Repair all tools")
        self.tools_progress.hide()
        QMessageBox.critical(self, "SDM", f"Could not start the tools installer: {error}")

    def open_tools_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        folder = self.diagnostics.root / "Tools"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def refresh_diagnostics(self) -> None:
        items = self.diagnostics.collect()
        self.diag_table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, value in enumerate((item.name, item.status, item.details)):
                self.diag_table.setItem(row, col, QTableWidgetItem(value))
        self._rebuild_tool_cards([item for item in items if item.name in TOOL_NAMES])

    def export_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export diagnostic report", "SDM_Diagnostics.json", "JSON (*.json)")
        if path:
            self.diagnostics.export(path)
            QMessageBox.information(self, "SDM", f"Report saved to:\n{path}")

    def refresh_plugins(self) -> None:
        items = self.plugins.discover()
        self.plugin_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (item.name, item.version, "Yes" if item.enabled else "No", "Yes" if item.loaded else "No", ", ".join(item.capabilities), item.error.splitlines()[-1] if item.error else "Ready")
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value); cell.setData(256, item.plugin_id)
                self.plugin_table.setItem(row, col, cell)

    def set_selected_plugin(self, enabled: bool) -> None:
        row = self.plugin_table.currentRow()
        if row < 0:
            return
        plugin_id = self.plugin_table.item(row, 0).data(256)
        self.plugins.set_enabled(str(plugin_id), enabled)
        self.refresh_plugins()
