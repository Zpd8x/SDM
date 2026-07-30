from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from sdm.diagnostics import DiagnosticsService
from sdm.plugins import PluginManager


class SystemCenterDialog(QDialog):
    def __init__(self, diagnostics: DiagnosticsService, plugins: PluginManager, parent=None):
        super().__init__(parent)
        self.diagnostics = diagnostics
        self.plugins = plugins
        self.setWindowTitle("SDM System Center")
        self.resize(820, 520)
        root = QVBoxLayout(self)
        title = QLabel("System Center — Diagnostics & Plugins")
        title.setObjectName("sectionTitle")
        root.addWidget(title)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        diag_tab = QWidget(); diag_layout = QVBoxLayout(diag_tab)
        self.diag_table = QTableWidget(0, 3)
        self.diag_table.setHorizontalHeaderLabels(["Component", "Status", "Details"])
        self.diag_table.horizontalHeader().setStretchLastSection(True)
        diag_layout.addWidget(self.diag_table)
        diag_actions = QHBoxLayout()
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh_diagnostics)
        export = QPushButton("Export report"); export.clicked.connect(self.export_report)
        diag_actions.addWidget(refresh); diag_actions.addWidget(export); diag_actions.addStretch()
        diag_layout.addLayout(diag_actions)
        tabs.addTab(diag_tab, "Diagnostics")

        plugin_tab = QWidget(); plugin_layout = QVBoxLayout(plugin_tab)
        self.plugin_table = QTableWidget(0, 6)
        self.plugin_table.setHorizontalHeaderLabels(["Plugin", "Version", "Enabled", "Loaded", "Capabilities", "Status"])
        self.plugin_table.horizontalHeader().setStretchLastSection(True)
        plugin_layout.addWidget(self.plugin_table)
        plugin_actions = QHBoxLayout()
        enable = QPushButton("Enable selected"); enable.clicked.connect(lambda: self.set_selected_plugin(True))
        disable = QPushButton("Disable selected"); disable.clicked.connect(lambda: self.set_selected_plugin(False))
        reload_button = QPushButton("Reload list"); reload_button.clicked.connect(self.refresh_plugins)
        plugin_actions.addWidget(enable); plugin_actions.addWidget(disable); plugin_actions.addWidget(reload_button); plugin_actions.addStretch()
        plugin_layout.addLayout(plugin_actions)
        tabs.addTab(plugin_tab, "Plugins")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh_diagnostics(); self.refresh_plugins()

    def refresh_diagnostics(self) -> None:
        items = self.diagnostics.collect()
        self.diag_table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, value in enumerate((item.name, item.status, item.details)):
                self.diag_table.setItem(row, col, QTableWidgetItem(value))

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
