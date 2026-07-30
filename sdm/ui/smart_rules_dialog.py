from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from sdm.categories import DOWNLOAD_CATEGORIES
from sdm.site_adapters import ADAPTER_LABELS
from sdm.smart_rules import (
    SmartRule,
    default_rules,
    describe_rule,
    load_rules,
    new_rule,
    normalize_rule,
    save_rules,
)
from sdm.ui.icons import application_icon


class SmartRulesDialog(QDialog):
    def __init__(self, repository, parent=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.rules = load_rules(repository)

        self.setWindowTitle("Smart Rules")
        self.setWindowIcon(application_icon())
        self.resize(900, 540)
        self.setMinimumSize(760, 440)

        title = QLabel("Smart Rules")
        title.setObjectName("sectionTitle")
        help_text = QLabel(
            "Rules are evaluated from top to bottom. The first matching rule "
            "chooses the folder, category, connection count, or start mode."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #93a1b7;")

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Enabled", "Rule", "Match", "Action"]
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda _item: self._edit())

        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add)
        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(self._edit)
        delete_button = QPushButton("Delete")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self._delete)
        up_button = QPushButton("Move Up")
        up_button.clicked.connect(lambda: self._move(-1))
        down_button = QPushButton("Move Down")
        down_button.clicked.connect(lambda: self._move(1))
        reset_button = QPushButton("Reset Defaults")
        reset_button.clicked.connect(self._reset)

        tools = QHBoxLayout()
        for button in (
            add_button,
            edit_button,
            delete_button,
            up_button,
            down_button,
            reset_button,
        ):
            tools.addWidget(button)
        tools.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(help_text)
        layout.addLayout(tools)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)
        self._render()

    def _render(self, selected: int | None = None) -> None:
        self.table.setRowCount(0)
        for row, rule in enumerate(self.rules):
            self.table.insertRow(row)
            enabled = QTableWidgetItem("Yes" if rule.enabled else "No")
            enabled.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, enabled)
            self.table.setItem(row, 1, QTableWidgetItem(rule.name))
            match_text, action_text = describe_rule(rule)
            self.table.setItem(row, 2, QTableWidgetItem(match_text))
            self.table.setItem(row, 3, QTableWidgetItem(action_text))
        if self.rules:
            target = (
                min(max(0, selected), len(self.rules) - 1)
                if selected is not None
                else 0
            )
            self.table.selectRow(target)

    def _selected_index(self) -> int:
        return self.table.currentRow()

    def _add(self) -> None:
        editor = SmartRuleEditor(new_rule(), self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            self.rules.append(editor.rule)
            self._render(len(self.rules) - 1)

    def _edit(self) -> None:
        index = self._selected_index()
        if index < 0:
            return
        editor = SmartRuleEditor(self.rules[index], self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            self.rules[index] = editor.rule
            self._render(index)

    def _delete(self) -> None:
        index = self._selected_index()
        if index < 0:
            return
        answer = QMessageBox.question(
            self,
            "Delete Rule",
            f'Delete the rule "{self.rules[index].name}"?',
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.rules.pop(index)
            self._render(index - 1)

    def _move(self, offset: int) -> None:
        index = self._selected_index()
        target = index + offset
        if index < 0 or target < 0 or target >= len(self.rules):
            return
        self.rules[index], self.rules[target] = (
            self.rules[target],
            self.rules[index],
        )
        self._render(target)

    def _reset(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset Smart Rules",
            "Replace the current rules with SDM defaults?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.rules = default_rules()
            self._render()

    def _save(self) -> None:
        save_rules(self.repository, self.rules)
        self.accept()


class SmartRuleEditor(QDialog):
    def __init__(self, rule: SmartRule, parent=None) -> None:
        super().__init__(parent)
        self._original = rule
        self.rule = rule
        self.setWindowTitle("Edit Smart Rule")
        self.setWindowIcon(application_icon())
        self.setMinimumWidth(620)

        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(rule.enabled)
        self.name = QLineEdit(rule.name)
        self.domain = QLineEdit(rule.domain)
        self.domain.setPlaceholderText("example.com or *.example.com")

        self.adapter = QComboBox()
        self.adapter.addItem("Any adapter", "")
        for value, label in ADAPTER_LABELS.items():
            self.adapter.addItem(label, value)
        self._select(self.adapter, rule.adapter)

        self.media = QComboBox()
        self.media.addItem("Any media kind", "")
        self.media.addItem("Direct file", "direct")
        self.media.addItem("Audio", "audio")
        self.media.addItem("Video", "video")
        self._select(self.media, rule.media_kind)

        self.extension = QLineEdit(rule.extension)
        self.extension.setPlaceholderText("zip (without a dot)")
        self.mime = QLineEdit(rule.mime_prefix)
        self.mime.setPlaceholderText("audio/ or application/pdf")
        self.filename_glob = QLineEdit(rule.filename_glob)
        self.filename_glob.setPlaceholderText("*.zip or report-*.pdf")
        self.url_contains = QLineEdit(rule.url_contains)
        self.url_contains.setPlaceholderText("token contained in URL")

        self.match_category = QComboBox()
        self.match_category.addItem("Any category", "")
        for category in DOWNLOAD_CATEGORIES:
            self.match_category.addItem(category, category)
        self._select(self.match_category, rule.category)

        self.minimum_mb = QSpinBox()
        self.minimum_mb.setRange(0, 2_000_000)
        self.minimum_mb.setSuffix(" MB")
        self.minimum_mb.setValue(rule.minimum_bytes // (1024 * 1024))
        self.maximum_mb = QSpinBox()
        self.maximum_mb.setRange(0, 2_000_000)
        self.maximum_mb.setSuffix(" MB")
        self.maximum_mb.setSpecialValueText("No maximum")
        self.maximum_mb.setValue(rule.maximum_bytes // (1024 * 1024))

        self.folder = QLineEdit(rule.target_folder)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse_button)

        self.filename_prefix = QLineEdit(rule.filename_prefix)
        self.filename_prefix.setPlaceholderText("Optional prefix")
        self.filename_suffix = QLineEdit(rule.filename_suffix)
        self.filename_suffix.setPlaceholderText("Optional suffix before extension")
        self.subfolder = QLineEdit(rule.subfolder)
        self.subfolder.setPlaceholderText("Optional subfolder, e.g. Archives\2026")

        self.target_category = QComboBox()
        self.target_category.addItem("Keep detected category", "")
        for category in DOWNLOAD_CATEGORIES:
            self.target_category.addItem(category, category)
        self._select(self.target_category, rule.target_category)

        self.connections = QComboBox()
        self.connections.addItem("Keep selected count", 0)
        for value in (1, 2, 4, 8, 16):
            self.connections.addItem(f"{value} connection(s)", value)
        self._select(self.connections, rule.connections)

        self.start_mode = QComboBox()
        self.start_mode.addItem("Keep selected mode", "inherit")
        self.start_mode.addItem("Start now", "now")
        self.start_mode.addItem("Download later", "later")
        self._select(self.start_mode, rule.start_mode)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("", self.enabled)
        form.addRow("Rule name:", self.name)
        form.addRow("Domain:", self.domain)
        form.addRow("Site adapter:", self.adapter)
        form.addRow("Media kind:", self.media)
        form.addRow("File extension:", self.extension)
        form.addRow("MIME starts with:", self.mime)
        form.addRow("Filename pattern:", self.filename_glob)
        form.addRow("URL contains:", self.url_contains)
        form.addRow("Detected category:", self.match_category)
        form.addRow("Minimum size:", self.minimum_mb)
        form.addRow("Maximum size:", self.maximum_mb)
        form.addRow("Save folder:", folder_row)
        form.addRow("Set category:", self.target_category)
        form.addRow("Filename prefix:", self.filename_prefix)
        form.addRow("Filename suffix:", self.filename_suffix)
        form.addRow("Subfolder:", self.subfolder)
        form.addRow("Connections:", self.connections)
        form.addRow("Start mode:", self.start_mode)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _select(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Rule Folder",
            self.folder.text() or str(Path.home() / "Downloads"),
        )
        if folder:
            self.folder.setText(folder)

    def _accept(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Invalid Rule", "Enter a rule name.")
            return
        minimum_bytes = self.minimum_mb.value() * 1024 * 1024
        maximum_bytes = self.maximum_mb.value() * 1024 * 1024
        if maximum_bytes and maximum_bytes < minimum_bytes:
            QMessageBox.warning(
                self,
                "Invalid Size Range",
                "Maximum size cannot be smaller than minimum size.",
            )
            return
        self.rule = normalize_rule(
            replace(
                self._original,
                name=self.name.text().strip(),
                enabled=self.enabled.isChecked(),
                domain=self.domain.text().strip(),
                adapter=str(self.adapter.currentData()),
                media_kind=str(self.media.currentData()),
                extension=self.extension.text().strip(),
                mime_prefix=self.mime.text().strip(),
                filename_glob=self.filename_glob.text().strip(),
                url_contains=self.url_contains.text().strip(),
                category=str(self.match_category.currentData()),
                minimum_bytes=minimum_bytes,
                maximum_bytes=maximum_bytes,
                target_folder=self.folder.text().strip(),
                target_category=str(self.target_category.currentData()),
                filename_prefix=self.filename_prefix.text().strip(),
                filename_suffix=self.filename_suffix.text().strip(),
                subfolder=self.subfolder.text().strip(),
                connections=int(self.connections.currentData()),
                start_mode=str(self.start_mode.currentData()),
            )
        )
        self.accept()
