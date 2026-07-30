from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sdm.bandwidth import BandwidthLimiter
from sdm.browser_bridge import release_launch_guard
from sdm.site_adapters import build_adapter_plan
from sdm.categories import DOWNLOAD_CATEGORIES
from sdm.config import (
    APP_VERSION,
    DEFAULT_CONNECTIONS_PER_DOWNLOAD,
    DEFAULT_MAX_ACTIVE_DOWNLOADS,
)
from sdm.database import DownloadRepository
from sdm.duplicate_intelligence import (
    DuplicateCandidate,
    choose_copy_filename,
    find_duplicate,
)
from sdm.models import DownloadRecord, DownloadStatus
from sdm.presentation import build_status_message, build_summary_text
from sdm.queue import DownloadQueue
from sdm.removal import (
    delete_download_artifacts,
    destination_is_shared,
)
from sdm.schedule import format_scheduled_local, schedule_is_due
from sdm.ui.add_dialog import AddDownloadDialog
from sdm.ui.browser_capture_dialog import BrowserCaptureDialog
from sdm.ui.download_progress_dialog import DownloadProgressDialog
from sdm.ui.duplicate_dialog import DuplicateDownloadDialog
from sdm.ui.icons import application_icon
from sdm.ui.smart_rules_dialog import SmartRulesDialog
from sdm.ui.storage_manager_dialog import StorageManagerDialog
from sdm.ui.media_inspector_dialog import MediaInspectorDialog
from sdm.ui.system_center_dialog import SystemCenterDialog
from sdm.diagnostics import DiagnosticsService
from sdm.plugins import PluginManager
from sdm.ui.window_activation import (
    bring_window_to_front,
    schedule_window_activation,
)
from sdm.utils import format_bytes, format_eta, format_speed
from sdm.worker import DownloadWorker
from sdm.smart_rules import RuleContext, evaluate_rules, load_rules


STATUS_LABELS = {
    DownloadStatus.SCHEDULED: "Scheduled",
    DownloadStatus.QUEUED: "Queued",
    DownloadStatus.DOWNLOADING: "Downloading",
    DownloadStatus.PAUSED: "Paused",
    DownloadStatus.RETRYING: "Retrying",
    DownloadStatus.VERIFYING: "Verifying",
    DownloadStatus.COMPLETED: "Completed",
    DownloadStatus.FAILED: "Failed",
    DownloadStatus.CANCELED: "Canceled",
}

STATUS_COLORS = {
    DownloadStatus.SCHEDULED: "#b79cff",
    DownloadStatus.QUEUED: "#aab4c5",
    DownloadStatus.DOWNLOADING: "#65a5ff",
    DownloadStatus.PAUSED: "#ffc766",
    DownloadStatus.RETRYING: "#ffac5f",
    DownloadStatus.VERIFYING: "#56d5de",
    DownloadStatus.COMPLETED: "#63d69f",
    DownloadStatus.FAILED: "#ff707d",
    DownloadStatus.CANCELED: "#c68cff",
}

CHECKSUM_COLORS = {
    "Pending": "#aab4c5",
    "Verifying": "#56d5de",
    "Verified": "#63d69f",
    "Mismatch": "#ff707d",
    "Error": "#ff707d",
}

SPEED_LIMITS = (
    ("Unlimited", 0),
    ("512 KB/s", 512 * 1024),
    ("1 MB/s", 1024 * 1024),
    ("2 MB/s", 2 * 1024 * 1024),
    ("5 MB/s", 5 * 1024 * 1024),
    ("10 MB/s", 10 * 1024 * 1024),
)


class MainWindow(QMainWindow):
    COL_FILE = 0
    COL_CATEGORY = 1
    COL_SIZE = 2
    COL_PROGRESS = 3
    COL_STATUS = 4
    COL_MODE = 5
    COL_SPEED = 6
    COL_ETA = 7
    COL_CHECKSUM = 8
    COL_FOLDER = 9

    def __init__(
        self,
        repository: DownloadRepository,
        *,
        heartbeat_path: str | Path | None = None,
        show_manager_request_path: str | Path | None = None,
        capture_only: bool = False,
    ) -> None:
        super().__init__()
        self.repository = repository
        self._heartbeat_path = (
            Path(heartbeat_path) if heartbeat_path is not None else None
        )
        self._show_manager_request_path = (
            Path(show_manager_request_path)
            if show_manager_request_path is not None
            else None
        )
        self._capture_only = bool(capture_only)
        self.workers: dict[str, DownloadWorker] = {}
        self.progress_dialogs: dict[str, DownloadProgressDialog] = {}
        self._restart_after_finish: set[str] = set()
        self.row_for_id: dict[str, int] = {}
        self._closing_application = False
        self._capture_dialog_open = False
        self._active_capture_id: str | None = None
        self._pending_capture_ids: list[str] = []

        try:
            max_active = int(
                repository.get_setting(
                    "max_active_downloads",
                    str(DEFAULT_MAX_ACTIVE_DOWNLOADS),
                )
            )
        except ValueError:
            max_active = DEFAULT_MAX_ACTIVE_DOWNLOADS
        self.download_queue = DownloadQueue(max_active=max_active)

        try:
            speed_limit = int(
                repository.get_setting("global_speed_limit_bps", "0")
            )
        except ValueError:
            speed_limit = 0
        if speed_limit < 0:
            speed_limit = 0
        self.bandwidth_limiter = BandwidthLimiter(speed_limit)

        self.setWindowTitle(f"SDM - Smart Download Manager {APP_VERSION}")
        self.setWindowIcon(application_icon())
        self.resize(1320, 760)
        self.setMinimumSize(1120, 580)
        self._build_interface()
        self._load_downloads()
        self._apply_category_filter()
        self._update_action_states()
        self._update_summary()
        self._write_heartbeat()

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(2_000)
        self._heartbeat_timer.timeout.connect(self._write_heartbeat)
        self._heartbeat_timer.start()

        self._show_manager_timer = QTimer(self)
        self._show_manager_timer.setInterval(500)
        self._show_manager_timer.timeout.connect(
            self._poll_show_manager_request
        )
        self._show_manager_timer.start()

        self._browser_poll_timer = QTimer(self)
        self._browser_poll_timer.setInterval(750)
        self._browser_poll_timer.timeout.connect(self._poll_browser_downloads)
        self._browser_poll_timer.start()

        self._schedule_timer = QTimer(self)
        self._schedule_timer.setInterval(1_000)
        self._schedule_timer.timeout.connect(self._check_scheduled_downloads)
        if not self._capture_only:
            self._schedule_timer.start()

        self._capture_idle_timer = QTimer(self)
        self._capture_idle_timer.setInterval(8_000)
        self._capture_idle_timer.timeout.connect(self._check_capture_idle)
        if self._capture_only:
            self._capture_idle_timer.start()

        QTimer.singleShot(100, self._show_next_browser_capture)
        if not self._capture_only:
            QTimer.singleShot(300, self._restore_queued_downloads)
            QTimer.singleShot(500, self._check_scheduled_downloads)

    def _build_interface(self) -> None:
        container = QWidget()
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(18, 18, 18, 12)
        root_layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)

        title_column = QVBoxLayout()
        title = QLabel("SDM")
        title.setObjectName("appTitle")
        subtitle = QLabel(
            f"Smart Download Manager  •  Final Architecture  •  Version {APP_VERSION}"
        )
        subtitle.setObjectName("appSubtitle")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        header_layout.addLayout(title_column)
        header_layout.addStretch()
        self.summary_label = QLabel("No downloads")
        self.summary_label.setStyleSheet("color: #9eabc0; font-weight: 600;")
        header_layout.addWidget(self.summary_label)
        root_layout.addWidget(header)

        actions = QFrame()
        actions.setObjectName("actionCard")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(12, 10, 12, 10)
        action_layout.setSpacing(8)

        self.add_button = QPushButton("＋  Add URL")
        self.add_button.setObjectName("primaryButton")
        self.add_button.clicked.connect(self._add_download)
        self.start_button = QPushButton("▶  Start / Resume")
        self.start_button.clicked.connect(self._start_selected)
        self.start_all_button = QPushButton("Start All")
        self.start_all_button.clicked.connect(self._start_all)
        self.pause_button = QPushButton("Ⅱ  Pause")
        self.pause_button.clicked.connect(self._pause_selected)
        self.pause_all_button = QPushButton("Pause All")
        self.pause_all_button.clicked.connect(self._pause_all)
        self.cancel_button = QPushButton("■  Cancel")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self._cancel_selected)
        self.delete_button = QPushButton("✕  Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.clicked.connect(self._delete_selected)
        self.delete_all_button = QPushButton("Delete All")
        self.delete_all_button.setObjectName("dangerButton")
        self.delete_all_button.clicked.connect(self._delete_all)
        self.folder_button = QPushButton("Open Folder")
        self.folder_button.clicked.connect(self._open_selected_folder)
        self.storage_button = QPushButton("Duplicate Manager")
        self.storage_button.clicked.connect(self._open_storage_manager)
        self.media_inspector_button = QPushButton("Media Inspector")
        self.media_inspector_button.clicked.connect(self._open_media_inspector)
        self.system_center_button = QPushButton("System Center")
        self.system_center_button.clicked.connect(self._open_system_center)

        for button in (
            self.add_button,
            self.start_button,
            self.start_all_button,
            self.pause_button,
            self.pause_all_button,
            self.cancel_button,
            self.delete_button,
            self.delete_all_button,
            self.folder_button,
            self.storage_button,
            self.media_inspector_button,
            self.system_center_button,
        ):
            action_layout.addWidget(button)
        action_layout.addStretch()
        root_layout.addWidget(actions)

        controls = QFrame()
        controls.setObjectName("controlCard")
        control_layout = QHBoxLayout(controls)
        control_layout.setContentsMargins(12, 9, 12, 9)
        control_layout.setSpacing(9)

        category_label = QLabel("Category:")
        category_label.setStyleSheet("color: #93a1b7;")
        self.category_filter_combo = QComboBox()
        self.category_filter_combo.setMinimumWidth(130)
        self.category_filter_combo.addItem("All categories", "")
        for category in DOWNLOAD_CATEGORIES:
            self.category_filter_combo.addItem(category, category)
        self.category_filter_combo.currentIndexChanged.connect(
            self._category_filter_changed
        )
        self.category_filter_combo.setToolTip(
            "Show all downloads or only one automatically detected category."
        )

        speed_label = QLabel("Global speed:")
        speed_label.setStyleSheet("color: #93a1b7;")
        self.speed_limit_combo = QComboBox()
        self.speed_limit_combo.setMinimumWidth(115)
        for label, value in SPEED_LIMITS:
            self.speed_limit_combo.addItem(label, value)
        selected_speed = self.speed_limit_combo.findData(
            self.bandwidth_limiter.limit_bytes_per_second
        )
        self.speed_limit_combo.setCurrentIndex(
            selected_speed if selected_speed >= 0 else 0
        )
        self.speed_limit_combo.currentIndexChanged.connect(
            self._speed_limit_changed
        )
        self.speed_limit_combo.setToolTip(
            "Aggregate speed shared by every active file and connection."
        )

        concurrent_label = QLabel("Concurrent:")
        concurrent_label.setStyleSheet("color: #93a1b7;")
        self.concurrent_combo = QComboBox()
        self.concurrent_combo.setFixedWidth(68)
        for value in (1, 2, 3, 4):
            self.concurrent_combo.addItem(str(value), value)
        selected_index = self.concurrent_combo.findData(
            self.download_queue.max_active
        )
        self.concurrent_combo.setCurrentIndex(
            selected_index if selected_index >= 0 else 1
        )
        self.concurrent_combo.currentIndexChanged.connect(
            self._max_active_changed
        )
        self.concurrent_combo.setToolTip(
            "Maximum number of files downloaded at the same time."
        )
        self.smart_rules_button = QPushButton("Smart Rules")
        self.smart_rules_button.setToolTip(
            "Automatically choose folders, categories, connections, and "
            "start behavior."
        )
        self.smart_rules_button.clicked.connect(self._open_smart_rules)

        control_layout.addWidget(category_label)
        control_layout.addWidget(self.category_filter_combo)
        control_layout.addSpacing(12)
        control_layout.addWidget(speed_label)
        control_layout.addWidget(self.speed_limit_combo)
        control_layout.addSpacing(12)
        control_layout.addWidget(self.smart_rules_button)
        control_layout.addStretch()
        control_layout.addWidget(concurrent_label)
        control_layout.addWidget(self.concurrent_combo)
        root_layout.addWidget(controls)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            [
                "File",
                "Category",
                "Size",
                "Progress",
                "Status",
                "Mode",
                "Speed",
                "ETA",
                "SHA-256",
                "Folder",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.itemSelectionChanged.connect(self._update_action_states)
        self.table.itemDoubleClicked.connect(
            lambda _item: self._open_selected_folder()
        )

        header_view = self.table.horizontalHeader()
        header_view.setStretchLastSection(True)
        header_view.setSectionResizeMode(
            self.COL_FILE, QHeaderView.ResizeMode.Stretch
        )
        for column in (
            self.COL_CATEGORY,
            self.COL_SIZE,
            self.COL_STATUS,
            self.COL_MODE,
            self.COL_SPEED,
            self.COL_ETA,
            self.COL_CHECKSUM,
        ):
            header_view.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        header_view.setSectionResizeMode(
            self.COL_PROGRESS, QHeaderView.ResizeMode.Fixed
        )
        header_view.resizeSection(self.COL_PROGRESS, 175)
        header_view.setSectionResizeMode(
            self.COL_FOLDER, QHeaderView.ResizeMode.Stretch
        )
        root_layout.addWidget(self.table, 1)

        self.setCentralWidget(container)
        self.statusBar().showMessage(
            "Ready. Add a direct HTTP or HTTPS file URL to begin."
        )

    def _open_system_center(self) -> None:
        app_root = Path(__file__).resolve().parents[2]
        plugin_root = self.repository.database_path.parent / "plugins"
        dialog = SystemCenterDialog(
            DiagnosticsService(self.repository.database_path, app_root),
            PluginManager(plugin_root),
            self,
        )
        dialog.exec()

    def _load_downloads(self) -> None:
        for record in self.repository.list_all():
            self._append_record(record)
            if record.source == "browser" and record.capture_pending:
                self._queue_browser_capture(record.id)

    def _append_record(
        self,
        record: DownloadRecord,
        *,
        at_top: bool = False,
    ) -> None:
        row = 0 if at_top else self.table.rowCount()
        self.table.insertRow(row)
        if at_top:
            self._rebuild_row_index()

        file_item = QTableWidgetItem(record.filename)
        file_item.setData(Qt.ItemDataRole.UserRole, record.id)
        file_item.setToolTip(self._record_tooltip(record))
        self.table.setItem(row, self.COL_FILE, file_item)
        self.table.setItem(
            row,
            self.COL_CATEGORY,
            QTableWidgetItem(record.category),
        )
        self.table.setItem(row, self.COL_SIZE, QTableWidgetItem(""))

        progress = QProgressBar()
        progress.setMinimumWidth(145)
        self.table.setCellWidget(row, self.COL_PROGRESS, progress)

        self.table.setItem(row, self.COL_STATUS, QTableWidgetItem(""))
        self.table.setItem(
            row,
            self.COL_MODE,
            QTableWidgetItem(record.transfer_mode),
        )
        self.table.setItem(row, self.COL_SPEED, QTableWidgetItem("—"))
        self.table.setItem(row, self.COL_ETA, QTableWidgetItem("—"))
        self.table.setItem(row, self.COL_CHECKSUM, QTableWidgetItem("—"))
        folder_item = QTableWidgetItem(record.folder)
        folder_item.setToolTip(record.folder)
        self.table.setItem(row, self.COL_FOLDER, folder_item)
        self.row_for_id[record.id] = row
        self._render_record(row, record)

    def _render_record(self, row: int, record: DownloadRecord) -> None:
        file_item = self.table.item(row, self.COL_FILE)
        file_item.setText(record.filename)
        file_item.setToolTip(self._record_tooltip(record))
        size_text = (
            format_bytes(record.total_bytes) if record.total_bytes else "Unknown"
        )
        self.table.item(row, self.COL_SIZE).setText(size_text)
        self.table.item(row, self.COL_CATEGORY).setText(record.category)
        mode_item = self.table.item(row, self.COL_MODE)
        mode_item.setText(record.transfer_mode)
        mode_item.setToolTip(
            record.adaptive_reason
            or "Adaptive mode learns a safe connection count for each server."
        )
        folder_item = self.table.item(row, self.COL_FOLDER)
        folder_item.setText(record.folder)
        folder_item.setToolTip(record.folder)

        progress = self.table.cellWidget(row, self.COL_PROGRESS)
        if isinstance(progress, QProgressBar):
            if record.total_bytes > 0:
                value = int(record.progress * 1000)
                progress.setRange(0, 1000)
                progress.setValue(value)
                progress.setFormat(f"{record.progress * 100:.1f}%")
            elif record.status in {
                DownloadStatus.DOWNLOADING,
                DownloadStatus.RETRYING,
            }:
                progress.setRange(0, 0)
                progress.setFormat("")
            else:
                progress.setRange(0, 1000)
                progress.setValue(0)
                progress.setFormat("0.0%")

        status_item = self.table.item(row, self.COL_STATUS)
        if record.capture_pending:
            status_item.setText("Confirm")
            status_item.setForeground(QColor("#65a5ff"))
            status_tooltip = "Waiting for confirmation in Download File Info."
        else:
            status_item.setText(STATUS_LABELS[record.status])
            status_item.setForeground(QColor(STATUS_COLORS[record.status]))
            status_tooltip = record.error
        if record.status == DownloadStatus.SCHEDULED and record.scheduled_at:
            status_tooltip = (
                f"Scheduled for {format_scheduled_local(record.scheduled_at)}"
            )
        status_item.setToolTip(status_tooltip)

        checksum_item = self.table.item(row, self.COL_CHECKSUM)
        checksum_text = (
            record.checksum_status
            if record.checksum_sha256
            else "—"
        )
        checksum_item.setText(checksum_text)
        checksum_item.setForeground(
            QColor(CHECKSUM_COLORS.get(record.checksum_status, "#aab4c5"))
        )
        if record.checksum_sha256:
            checksum_tooltip = f"Expected: {record.checksum_sha256}"
            if record.checksum_actual:
                checksum_tooltip += f"\nActual: {record.checksum_actual}"
            checksum_item.setToolTip(checksum_tooltip)
        else:
            checksum_item.setToolTip("No SHA-256 checksum was provided.")

        if record.status not in {
            DownloadStatus.DOWNLOADING,
            DownloadStatus.RETRYING,
        }:
            self.table.item(row, self.COL_SPEED).setText("—")
            self.table.item(row, self.COL_ETA).setText(
                "00:00"
                if record.status == DownloadStatus.COMPLETED
                else "—"
            )


    def _open_storage_manager(self) -> None:
        dialog = StorageManagerDialog(self.repository, self)
        dialog.exec()
        self._load_downloads()
        self._apply_category_filter()
        self._update_summary()


    def _open_media_inspector(self) -> None:
        dialog = MediaInspectorDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.download_data
        record = self.repository.create_download(
            url=str(data["url"]),
            filename=str(data["filename"]),
            folder=str(data["folder"]),
            connections=int(self.repository.get_setting("connections_per_download", 4)),
            start_immediately=True,
            category="Video" if data["media_kind"] == "video" else "Audio",
            media_kind=str(data["media_kind"]),
            media_format=str(data["media_format"]),
            source="media_inspector",
        )
        self._append_record(record, at_top=True)
        self._apply_category_filter()
        self._update_summary()
        self._request_start(record.id)
        self.statusBar().showMessage(f"Added media selection: {record.filename}.")

    def _add_download(self) -> None:
        try:
            default_connections = int(
                self.repository.get_setting(
                    "connections_per_download",
                    str(DEFAULT_CONNECTIONS_PER_DOWNLOAD),
                )
            )
        except ValueError:
            default_connections = DEFAULT_CONNECTIONS_PER_DOWNLOAD
        dialog = AddDownloadDialog(
            self,
            default_connections=default_connections,
        )
        if dialog.exec() != AddDownloadDialog.DialogCode.Accepted:
            return

        data = dict(dialog.download_data)
        rule = evaluate_rules(
            load_rules(self.repository),
            RuleContext(
                url=str(data["url"]),
                filename=str(data["filename"]),
                category=str(data["category"]),
            ),
        )
        if rule.folder:
            rule_folder = Path(rule.folder).expanduser()
            try:
                rule_folder.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                QMessageBox.warning(
                    self,
                    "Smart Rule Folder",
                    "The matched smart rule folder is unavailable, so SDM "
                    f"will keep the selected folder.\n\n{error}",
                )
            else:
                data["folder"] = str(rule_folder)
        if rule.category:
            data["category"] = rule.category
        if rule.filename:
            data["filename"] = rule.filename
        if rule.connections:
            data["connections"] = rule.connections
        if rule.start_immediately is not None:
            data["start_immediately"] = rule.start_immediately
            if rule.start_immediately:
                data["scheduled_at"] = ""

        duplicate = find_duplicate(
            self.repository.list_all(),
            DuplicateCandidate(
                url=str(data["url"]),
                filename=str(data["filename"]),
                folder=str(data["folder"]),
            ),
        )
        if duplicate is not None:
            duplicate_dialog = DuplicateDownloadDialog(duplicate, self)
            duplicate_dialog.exec()
            action = duplicate_dialog.result_action
            if action == DuplicateDownloadDialog.ACTION_COPY:
                data["filename"] = choose_copy_filename(
                    str(data["folder"]),
                    str(data["filename"]),
                    self.repository.list_all(),
                )
            else:
                self._handle_existing_duplicate(duplicate.record, action)
                return
        elif (
            Path(str(data["folder"])).expanduser() / str(data["filename"])
        ).exists():
            answer = QMessageBox.question(
                self,
                "File Already Exists",
                "This path contains a file that is not tracked by SDM.\n"
                "Add the download as a safely renamed copy?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            data["filename"] = choose_copy_filename(
                str(data["folder"]),
                str(data["filename"]),
                self.repository.list_all(),
            )

        record = self.repository.create_download(
            url=str(data["url"]),
            filename=str(data["filename"]),
            folder=str(data["folder"]),
            connections=int(data["connections"]),
            start_immediately=bool(data["start_immediately"]),
            category=str(data["category"]),
            scheduled_at=str(data["scheduled_at"]),
            checksum_sha256=str(data["checksum_sha256"]),
            rule_id=rule.rule_id,
            rule_reason=rule.reason if rule.matched else "",
        )
        self.repository.set_setting(
            "connections_per_download",
            int(data["connections"]),
        )
        self._append_record(record, at_top=True)
        self._apply_category_filter()
        if not self.table.isRowHidden(self.row_for_id[record.id]):
            self.table.selectRow(self.row_for_id[record.id])
        self._update_summary()
        if (
            bool(data["start_immediately"])
            and record.status != DownloadStatus.SCHEDULED
        ):
            self._request_start(record.id)
        elif record.status == DownloadStatus.SCHEDULED:
            self.statusBar().showMessage(
                f"Scheduled {record.filename} for "
                f"{format_scheduled_local(record.scheduled_at)}."
            )
        else:
            message = f"Added {record.filename}."
            if rule.matched:
                message += f" {rule.reason}"
            self.statusBar().showMessage(message)
        self._update_action_states()

    def _record_tooltip(self, record: DownloadRecord) -> str:
        lines = [record.url]
        if record.rule_reason:
            lines.append(f"Smart decision: {record.rule_reason}")
        if record.source_url and record.source_url != record.url:
            lines.append(f"Stable source: {record.source_url}")
        return "\n".join(lines)

    def _handle_existing_duplicate(
        self,
        record: DownloadRecord,
        action: str,
    ) -> None:
        row = self.row_for_id.get(record.id)
        if row is not None:
            if self.table.isRowHidden(row):
                self.category_filter_combo.setCurrentIndex(0)
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, self.COL_FILE))
        if action == DuplicateDownloadDialog.ACTION_RESUME:
            self._request_start(record.id)
            self.statusBar().showMessage(
                f"Resuming the existing download: {record.filename}."
            )
        elif action == DuplicateDownloadDialog.ACTION_OPEN:
            target = record.final_path
            if target.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
            else:
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(Path(record.folder)))
                )
            self.statusBar().showMessage(
                f"Opened the existing download: {record.filename}."
            )
        elif action == DuplicateDownloadDialog.ACTION_FOCUS:
            self.statusBar().showMessage(
                f"The existing download is already active: {record.filename}."
            )

    def _open_smart_rules(self) -> None:
        dialog = SmartRulesDialog(self.repository, self)
        if dialog.exec() == SmartRulesDialog.DialogCode.Accepted:
            self.statusBar().showMessage(
                "Smart Rules saved. New downloads will use the updated order."
            )

    def _selected_record_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0 or self.table.isRowHidden(row):
            return None
        item = self.table.item(row, self.COL_FILE)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _selected_record(self) -> DownloadRecord | None:
        record_id = self._selected_record_id()
        return self.repository.get(record_id) if record_id else None

    def _start_selected(self) -> None:
        record_id = self._selected_record_id()
        if record_id:
            self._request_start(record_id)

    def _request_start(self, record_id: str) -> None:
        record = self.repository.get(record_id)
        if record is None:
            return
        if record.capture_pending:
            self._queue_browser_capture(record_id)
            QTimer.singleShot(0, self._show_next_browser_capture)
            self.statusBar().showMessage(
                f"Waiting for confirmation: {record.filename}."
            )
            return
        if record.status == DownloadStatus.COMPLETED:
            QMessageBox.information(
                self,
                "Already Completed",
                "This download has already completed.",
            )
            return
        if record.status == DownloadStatus.VERIFYING:
            return

        if record.status == DownloadStatus.SCHEDULED or record.scheduled_at:
            self.repository.update(
                record_id,
                status=DownloadStatus.QUEUED,
                scheduled_at="",
                auto_start=False,
                error="",
            )
            record = self.repository.get(record_id)
            if record is None:
                return

        if self.download_queue.request(record_id):
            self._activate_download(record_id)
            return

        self.repository.update(
            record_id,
            status=DownloadStatus.QUEUED,
            error="",
        )
        refreshed = self.repository.get(record_id)
        row = self.row_for_id.get(record_id)
        if refreshed and row is not None:
            self._render_record(row, refreshed)
        self.statusBar().showMessage(f"Queued {record.filename}.")
        self._update_action_states()
        self._update_summary()

    def _activate_download(self, record_id: str) -> None:
        record = self.repository.get(record_id)
        if record is None:
            for promoted in self.download_queue.release(record_id):
                self._activate_download(promoted)
            return

        active_worker = self.workers.get(record_id)
        if active_worker and active_worker.isRunning():
            if record.status in {
                DownloadStatus.FAILED,
                DownloadStatus.CANCELED,
            }:
                self._restart_after_finish.add(record_id)
                self.repository.update(
                    record_id,
                    status=DownloadStatus.QUEUED,
                    error="",
                )
                refreshed = self.repository.get(record_id)
                if refreshed is not None:
                    self._refresh_record_and_progress(refreshed)
                self.statusBar().showMessage(
                    f"Preparing to resume {record.filename}…"
                )
                return
            if active_worker.control.is_cancelled:
                return
            active_worker.resume_download()
            return

        if record.source == "browser":
            self._ensure_progress_dialog(record)

        worker = DownloadWorker(
            record_id,
            self.repository,
            self.bandwidth_limiter,
            self,
        )
        worker.progress_changed.connect(self._on_progress)
        worker.metadata_changed.connect(self._on_metadata)
        worker.output_path_changed.connect(self._on_output_path_changed)
        worker.mode_changed.connect(self._on_mode_changed)
        worker.connection_progress_changed.connect(
            self._on_connection_progress
        )
        worker.state_changed.connect(self._on_state_changed)
        worker.content_duplicate_found.connect(
            self._on_content_duplicate_found
        )
        worker.finished.connect(
            lambda record_id=record_id: self._on_worker_finished(record_id)
        )
        self.workers[record_id] = worker
        worker.start()
        self.statusBar().showMessage(f"Starting {record.filename}…")
        self._update_action_states()

    def _pause_selected(self) -> None:
        record = self._selected_record()
        if record is None or record.status == DownloadStatus.VERIFYING:
            return
        worker = self.workers.get(record.id)
        if worker and worker.isRunning():
            worker.pause_download()
            for promoted in self.download_queue.release(record.id):
                self._activate_download(promoted)

    def _start_all(self) -> None:
        if self.download_queue.is_busy:
            self.statusBar().showMessage(
                "Start All ignored: the download queue is already running."
            )
            return
        for record in reversed(self.repository.list_all()):
            if record.status not in {
                DownloadStatus.COMPLETED,
                DownloadStatus.SCHEDULED,
                DownloadStatus.VERIFYING,
            } and not record.capture_pending:
                self._request_start(record.id)

    def _pause_all(self) -> None:
        active_ids = tuple(self.download_queue.active_ids)
        pending_ids = self.download_queue.pending_ids
        verifying_ids: list[str] = []
        pausable_ids: list[str] = []
        for record_id in active_ids:
            record = self.repository.get(record_id)
            if record and record.status == DownloadStatus.VERIFYING:
                verifying_ids.append(record_id)
            else:
                pausable_ids.append(record_id)

        self.download_queue.pause_all()
        for record_id in verifying_ids:
            self.download_queue.request(record_id)
        for record_id in pausable_ids:
            worker = self.workers.get(record_id)
            if worker and worker.isRunning():
                worker.pause_download()
        for record_id in pending_ids:
            self.repository.update(
                record_id,
                status=DownloadStatus.PAUSED,
                error="",
            )
            record = self.repository.get(record_id)
            row = self.row_for_id.get(record_id)
            if record and row is not None:
                self._render_record(row, record)
        self._update_action_states()
        self._update_summary()

    def _cancel_selected(self) -> None:
        record = self._selected_record()
        if record is None or record.status == DownloadStatus.VERIFYING:
            return
        worker = self.workers.get(record.id)
        if not worker or not worker.isRunning():
            self.download_queue.remove_pending(record.id)
            self.repository.update(
                record.id,
                status=DownloadStatus.CANCELED,
                scheduled_at="",
                auto_start=False,
                error="",
            )
            refreshed = self.repository.get(record.id)
            if refreshed:
                self._render_record(self.row_for_id[record.id], refreshed)
            self._update_action_states()
            self._update_summary()
            return

        answer = QMessageBox.question(
            self,
            "Cancel Download",
            "Cancel this download?\n\n"
            "The partial file will be kept so it can be resumed later.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.download_queue.remove_pending(record.id)
            worker.cancel_download()

    def _delete_selected(self) -> None:
        record = self._selected_record()
        if record is None:
            return

        worker = self.workers.get(record.id)
        is_busy = (
            record.id in self.download_queue.active_ids
            or worker is not None
        )
        if is_busy:
            QMessageBox.information(
                self,
                "Download Is Active",
                "Cancel this download first, then press Delete again.",
            )
            return

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Delete Download")
        dialog.setText(f"Delete {record.filename} from SDM?")
        dialog.setInformativeText(
            "Remove from List keeps downloaded and partial files.\n"
            "Delete Files + Record also removes the final file and "
            "saved partial data."
        )
        remove_button = dialog.addButton(
            "Remove from List",
            QMessageBox.ButtonRole.AcceptRole,
        )
        delete_files_button = dialog.addButton(
            "Delete Files + Record",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()

        clicked_button = dialog.clickedButton()
        if clicked_button not in (remove_button, delete_files_button):
            return

        delete_files = clicked_button is delete_files_button
        if delete_files and destination_is_shared(
            record,
            self.repository.list_all(),
        ):
            QMessageBox.warning(
                self,
                "Shared File Path",
                "Another download record uses the same file path.\n\n"
                "The file was not deleted. Choose Remove from List instead.",
            )
            return

        if delete_files:
            try:
                delete_download_artifacts(record)
            except OSError as error:
                QMessageBox.critical(
                    self,
                    "Delete Failed",
                    "SDM could not delete all associated files.\n\n"
                    f"{error}",
                )
                return

        self.download_queue.remove_pending(record.id)
        self.repository.delete(record.id)
        row = self.row_for_id.pop(record.id, None)
        if row is not None:
            self.table.removeRow(row)
            self._rebuild_row_index()
            self._select_nearest_visible_row(row)

        action = "Deleted files and removed" if delete_files else "Removed"
        self.statusBar().showMessage(
            f"{action} {record.filename} from SDM."
        )
        self._update_action_states()
        self._update_summary()

    def _delete_all(self) -> None:
        records = self.repository.list_all()
        if not records:
            return
        if self.download_queue.is_busy or self.workers:
            QMessageBox.information(
                self,
                "Downloads Are Active",
                "Pause or cancel all active downloads before using Delete All.",
            )
            return

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Delete All Downloads")
        dialog.setText(
            f"Delete all {len(records)} download records from SDM?"
        )
        dialog.setInformativeText(
            "Remove All from List keeps every downloaded and partial file.\n"
            "Delete All Files + Records permanently removes final files, "
            "partial files, and download records."
        )
        remove_button = dialog.addButton(
            "Remove All from List",
            QMessageBox.ButtonRole.AcceptRole,
        )
        delete_files_button = dialog.addButton(
            "Delete All Files + Records",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()

        clicked_button = dialog.clickedButton()
        if clicked_button not in (remove_button, delete_files_button):
            return

        delete_files = clicked_button is delete_files_button
        if delete_files:
            try:
                for record in records:
                    delete_download_artifacts(record)
            except OSError as error:
                QMessageBox.critical(
                    self,
                    "Delete All Failed",
                    "SDM could not delete all associated files. "
                    "The download records were kept.\n\n"
                    f"{error}",
                )
                return

        removed_count = self.repository.delete_all()
        self.download_queue.pause_all()
        self.table.clearSelection()
        self.table.setRowCount(0)
        self.row_for_id.clear()
        action = (
            "Deleted all files and removed"
            if delete_files
            else "Removed"
        )
        self.statusBar().showMessage(
            f"{action} {removed_count} download record(s)."
        )
        self._update_action_states()
        self._update_summary()

    def _open_selected_folder(self) -> None:
        record = self._selected_record()
        if record:
            QDesktopServices.openUrl(QUrl.fromLocalFile(record.folder))

    def _ensure_progress_dialog(
        self,
        record: DownloadRecord,
    ) -> DownloadProgressDialog:
        existing = self.progress_dialogs.get(record.id)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return existing

        show_completion = (
            self.repository.get_setting(
                "show_download_complete_dialog",
                "1",
            )
            != "0"
        )
        open_folder = (
            self.repository.get_setting(
                "open_folder_on_completion",
                "0",
            )
            == "1"
        )
        dialog = DownloadProgressDialog(
            record,
            speed_limit_bps=(
                self.bandwidth_limiter.limit_bytes_per_second
            ),
            show_completion_dialog=show_completion,
            open_folder_on_completion=open_folder,
            parent=None,
        )
        dialog.pause_requested.connect(self._pause_record)
        dialog.resume_requested.connect(self._request_start)
        dialog.cancel_requested.connect(self._cancel_record)
        dialog.open_manager_requested.connect(self._show_manager)
        dialog.speed_limit_changed.connect(
            self._set_speed_limit_from_progress
        )
        dialog.completion_options_changed.connect(
            self._save_completion_options
        )
        dialog.finished.connect(
            lambda _result, record_id=record.id: (
                self._progress_dialog_closed(record_id)
            )
        )
        self.progress_dialogs[record.id] = dialog
        bring_window_to_front(dialog)
        return dialog

    def _pause_record(self, record_id: str) -> None:
        record = self.repository.get(record_id)
        if record is None or record.status == DownloadStatus.VERIFYING:
            return
        worker = self.workers.get(record_id)
        if worker and worker.isRunning():
            worker.pause_download()
            for promoted in self.download_queue.release(record_id):
                self._activate_download(promoted)
            return
        self.download_queue.remove_pending(record_id)
        self.repository.update(
            record_id,
            status=DownloadStatus.PAUSED,
            error="",
        )
        refreshed = self.repository.get(record_id)
        if refreshed:
            self._refresh_record_and_progress(refreshed)

    def _cancel_record(self, record_id: str) -> None:
        record = self.repository.get(record_id)
        if record is None or record.status == DownloadStatus.VERIFYING:
            return
        self.download_queue.remove_pending(record_id)
        worker = self.workers.get(record_id)
        if worker and worker.isRunning():
            worker.cancel_download()
            return
        self.repository.update(
            record_id,
            status=DownloadStatus.CANCELED,
            scheduled_at="",
            auto_start=False,
            error="",
        )
        refreshed = self.repository.get(record_id)
        if refreshed:
            self._refresh_record_and_progress(refreshed)

    def _refresh_record_and_progress(
        self,
        record: DownloadRecord,
        *,
        message: str = "",
    ) -> None:
        row = self.row_for_id.get(record.id)
        if row is not None:
            self._render_record(row, record)
        progress_dialog = self.progress_dialogs.get(record.id)
        if progress_dialog is not None:
            progress_dialog.set_state(record.status, message)
        self._update_action_states()
        self._update_summary()

    def _set_speed_limit_from_progress(self, value: int) -> None:
        self.repository.set_setting("global_speed_limit_bps", value)
        self.bandwidth_limiter.set_limit(value)
        index = self.speed_limit_combo.findData(value)
        if index >= 0 and index != self.speed_limit_combo.currentIndex():
            self.speed_limit_combo.blockSignals(True)
            self.speed_limit_combo.setCurrentIndex(index)
            self.speed_limit_combo.blockSignals(False)

    def _save_completion_options(
        self,
        show_dialog: bool,
        open_folder: bool,
    ) -> None:
        self.repository.set_setting(
            "show_download_complete_dialog",
            int(show_dialog),
        )
        self.repository.set_setting(
            "open_folder_on_completion",
            int(open_folder),
        )

    def _progress_dialog_closed(self, record_id: str) -> None:
        self.progress_dialogs.pop(record_id, None)

    def _on_progress(
        self,
        record_id: str,
        downloaded: int,
        total: int,
        speed: float,
        eta: int | None,
    ) -> None:
        progress_dialog = self.progress_dialogs.get(record_id)
        if progress_dialog is not None:
            progress_dialog.set_progress(
                downloaded,
                total,
                speed,
                eta,
            )
        row = self.row_for_id.get(record_id)
        if row is None:
            return

        self.table.item(row, self.COL_SIZE).setText(
            format_bytes(total) if total else "Unknown"
        )
        progress = self.table.cellWidget(row, self.COL_PROGRESS)
        if isinstance(progress, QProgressBar):
            if total > 0:
                fraction = min(1.0, downloaded / total)
                progress.setRange(0, 1000)
                progress.setValue(int(fraction * 1000))
                progress.setFormat(f"{fraction * 100:.1f}%")
            else:
                progress.setRange(0, 0)
                progress.setFormat("")
        self.table.item(row, self.COL_SPEED).setText(format_speed(speed))
        self.table.item(row, self.COL_ETA).setText(format_eta(eta))

    def _on_metadata(
        self,
        record_id: str,
        total: int,
        _etag: str,
        _last_modified: str,
    ) -> None:
        row = self.row_for_id.get(record_id)
        if row is not None:
            self.table.item(row, self.COL_SIZE).setText(
                format_bytes(total) if total else "Unknown"
            )

    def _on_output_path_changed(
        self,
        record_id: str,
        filename: str,
        folder: str,
    ) -> None:
        progress_dialog = self.progress_dialogs.get(record_id)
        if progress_dialog is not None:
            progress_dialog.set_output_path(filename, folder)
        record = self.repository.get(record_id)
        row = self.row_for_id.get(record_id)
        if record is not None and row is not None:
            self._render_record(row, record)

    def _on_mode_changed(
        self,
        record_id: str,
        mode: str,
        active_connections: int,
    ) -> None:
        progress_dialog = self.progress_dialogs.get(record_id)
        if progress_dialog is not None:
            progress_dialog.set_mode(mode, active_connections)
        row = self.row_for_id.get(record_id)
        if row is not None:
            self.table.item(row, self.COL_MODE).setText(mode)

    def _on_connection_progress(
        self,
        record_id: str,
        snapshot: object,
    ) -> None:
        progress_dialog = self.progress_dialogs.get(record_id)
        if progress_dialog is None or not isinstance(snapshot, tuple):
            return
        progress_dialog.set_connection_progress(snapshot)

    def _on_state_changed(
        self,
        record_id: str,
        _status_value: str,
        message: str,
    ) -> None:
        row = self.row_for_id.get(record_id)
        record = self.repository.get(record_id)
        if record is None:
            return
        if row is not None:
            self._render_record(row, record)
        progress_dialog = self.progress_dialogs.get(record_id)
        if progress_dialog is not None:
            progress_dialog.set_state(record.status, message)
        self.statusBar().showMessage(
            build_status_message(record, detail=message)
        )
        self._update_action_states()
        self._update_summary()

    def _on_content_duplicate_found(
        self,
        record_id: str,
        duplicate_id: str,
    ) -> None:
        record = self.repository.get(record_id)
        existing = self.repository.get(duplicate_id)
        if record is None or existing is None:
            return
        QMessageBox.warning(
            self,
            "Identical File Detected",
            "SDM computed the SHA-256 content fingerprint and found an "
            "identical completed file. Both files were kept.\n\n"
            f"New file: {record.final_path}\n"
            f"Existing file: {existing.final_path}\n\n"
            "Review the files and decide manually whether to keep both.",
        )

    def _on_worker_finished(self, record_id: str) -> None:
        restart_requested = record_id in self._restart_after_finish
        self._restart_after_finish.discard(record_id)
        worker = self.workers.pop(record_id, None)
        if worker:
            worker.deleteLater()
        promoted = self.download_queue.release(record_id)
        if not self._closing_application:
            for promoted_id in promoted:
                self._activate_download(promoted_id)
            if restart_requested:
                QTimer.singleShot(
                    0,
                    lambda record_id=record_id: (
                        self._request_start(record_id)
                    ),
                )
        self._update_action_states()
        self._update_summary()

    def _update_action_states(self) -> None:
        record = self._selected_record()
        selected = record is not None
        active_worker = self.workers.get(record.id) if record else None
        is_running = bool(active_worker and active_worker.isRunning())
        is_paused = bool(record and record.status == DownloadStatus.PAUSED)
        is_verifying = bool(
            record and record.status == DownloadStatus.VERIFYING
        )
        is_busy = bool(
            record
            and (
                record.id in self.download_queue.active_ids
                or active_worker is not None
            )
        )

        can_start = bool(
            selected
            and record.status
            not in {
                DownloadStatus.COMPLETED,
                DownloadStatus.DOWNLOADING,
                DownloadStatus.RETRYING,
                DownloadStatus.VERIFYING,
            }
        )
        if is_running and is_paused:
            can_start = True
        self.start_button.setEnabled(can_start)
        self.pause_button.setEnabled(
            bool(
                is_running
                and record.status
                in {
                    DownloadStatus.DOWNLOADING,
                    DownloadStatus.RETRYING,
                }
            )
        )
        self.cancel_button.setEnabled(
            bool(
                selected
                and record.status != DownloadStatus.COMPLETED
                and not is_verifying
            )
        )
        self.delete_button.setEnabled(bool(selected and not is_busy))
        self.delete_button.setToolTip(
            "Cancel the active download before deleting it."
            if is_busy
            else "Remove the selected download or delete its files."
        )
        self.folder_button.setEnabled(selected)
        records = self.repository.list_all()
        self.start_all_button.setEnabled(
            any(
                item.status
                not in {
                    DownloadStatus.COMPLETED,
                    DownloadStatus.SCHEDULED,
                    DownloadStatus.VERIFYING,
                }
                and not item.capture_pending
                for item in records
            )
            and not self.download_queue.is_busy
        )
        self.pause_all_button.setEnabled(
            any(
                item.status
                in {
                    DownloadStatus.DOWNLOADING,
                    DownloadStatus.RETRYING,
                    DownloadStatus.QUEUED,
                }
                for item in records
            )
            and self.download_queue.is_busy
        )
        delete_all_busy = self.download_queue.is_busy or bool(self.workers)
        self.delete_all_button.setEnabled(
            bool(records) and not delete_all_busy
        )
        self.delete_all_button.setToolTip(
            "Pause or cancel active downloads before deleting all."
            if delete_all_busy
            else "Remove every record, with an option to delete all files."
        )

    def _update_summary(self) -> None:
        self.summary_label.setText(
            build_summary_text(self.repository.list_all())
        )

    def _rebuild_row_index(self) -> None:
        self.row_for_id.clear()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILE)
            if item:
                record_id = item.data(Qt.ItemDataRole.UserRole)
                if record_id:
                    self.row_for_id[str(record_id)] = row

    def _select_nearest_visible_row(self, preferred_row: int = 0) -> None:
        if self.table.rowCount() == 0:
            return
        candidates = list(range(preferred_row, self.table.rowCount()))
        candidates.extend(range(min(preferred_row - 1, self.table.rowCount() - 1), -1, -1))
        for row in candidates:
            if not self.table.isRowHidden(row):
                self.table.selectRow(row)
                return

    def _category_filter_changed(self) -> None:
        self._apply_category_filter()
        self._update_action_states()

    def _apply_category_filter(self) -> None:
        selected_category = str(
            self.category_filter_combo.currentData() or ""
        )
        selected_id = self._selected_record_id()
        for row in range(self.table.rowCount()):
            category_item = self.table.item(row, self.COL_CATEGORY)
            category = category_item.text() if category_item else ""
            self.table.setRowHidden(
                row,
                bool(selected_category and category != selected_category),
            )
        if selected_id:
            selected_row = self.row_for_id.get(selected_id)
            if selected_row is not None and self.table.isRowHidden(selected_row):
                self.table.clearSelection()
        if self._selected_record_id() is None:
            self._select_nearest_visible_row(0)

    def _speed_limit_changed(self) -> None:
        value = int(self.speed_limit_combo.currentData() or 0)
        self.repository.set_setting("global_speed_limit_bps", value)
        self.bandwidth_limiter.set_limit(value)
        label = str(self.speed_limit_combo.currentText())
        self.statusBar().showMessage(f"Global speed limit: {label}.")

    def _max_active_changed(self) -> None:
        value = int(self.concurrent_combo.currentData())
        self.repository.set_setting("max_active_downloads", value)
        for promoted in self.download_queue.set_max_active(value):
            self._activate_download(promoted)
        self._update_action_states()

    def _check_scheduled_downloads(self) -> None:
        due_records = [
            record
            for record in self.repository.list_all()
            if record.status == DownloadStatus.SCHEDULED
            and schedule_is_due(record.scheduled_at)
        ]
        for record in reversed(due_records):
            self.repository.update(
                record.id,
                status=DownloadStatus.QUEUED,
                scheduled_at="",
                auto_start=False,
                error="",
            )
            refreshed = self.repository.get(record.id)
            row = self.row_for_id.get(record.id)
            if refreshed and row is not None:
                self._render_record(row, refreshed)
            self._request_start(record.id)
        if due_records:
            self._update_summary()
            self._update_action_states()

    def _restore_queued_downloads(self) -> None:
        for record in reversed(self.repository.list_all()):
            if (
                record.status == DownloadStatus.QUEUED
                and not record.capture_pending
            ):
                if record.auto_start:
                    self.repository.update(record.id, auto_start=False)
                self._request_start(record.id)

    def _poll_browser_downloads(self) -> None:
        records = self.repository.list_all()
        new_records = [
            record for record in records if record.id not in self.row_for_id
        ]
        if not new_records:
            recaptured = 0
            for record in records:
                if record.source == "browser" and record.capture_pending:
                    was_queued = (
                        record.id == self._active_capture_id
                        or record.id in self._pending_capture_ids
                    )
                    self._queue_browser_capture(record.id)
                    if not was_queued:
                        recaptured += 1
                    row = self.row_for_id.get(record.id)
                    if row is not None:
                        self._render_record(row, record)
            if recaptured:
                self.statusBar().showMessage(
                    "A repeated browser request matched an existing download."
                )
                QTimer.singleShot(0, self._show_next_browser_capture)
            return

        for record in reversed(new_records):
            self._append_record(record, at_top=True)
        self._apply_category_filter()

        started = 0
        captured = 0
        for record in reversed(new_records):
            if record.source == "browser" and record.capture_pending:
                self._queue_browser_capture(record.id)
                captured += 1
            elif record.source == "browser" and record.auto_start:
                self.repository.update(record.id, auto_start=False)
                self._request_start(record.id)
                started += 1

        self._update_action_states()
        self._update_summary()
        if captured:
            self.statusBar().showMessage(
                f"Received {captured} browser capture request(s)."
            )
            QTimer.singleShot(0, self._show_next_browser_capture)
        elif started:
            self.statusBar().showMessage(
                f"Received {started} download request(s) from the browser."
            )
        else:
            self.statusBar().showMessage(
                f"Added {len(new_records)} browser download request(s)."
            )

    def _queue_browser_capture(self, record_id: str) -> None:
        if (
            record_id == self._active_capture_id
            or record_id in self._pending_capture_ids
        ):
            return
        self._pending_capture_ids.append(record_id)

    def _show_next_browser_capture(self) -> None:
        if self._capture_dialog_open or self._closing_application:
            return

        record: DownloadRecord | None = None
        while self._pending_capture_ids:
            candidate_id = self._pending_capture_ids.pop(0)
            candidate = self.repository.get(candidate_id)
            if candidate and candidate.capture_pending:
                record = candidate
                break
        if record is None:
            return

        self._capture_dialog_open = True
        self._active_capture_id = record.id
        dialog = BrowserCaptureDialog(self.repository, record, parent=None)
        schedule_window_activation(dialog)
        dialog.exec()

        if dialog.result_action == BrowserCaptureDialog.ACTION_CANCEL:
            self.repository.delete(record.id)
            row = self.row_for_id.pop(record.id, None)
            if row is not None:
                self.table.removeRow(row)
                self._rebuild_row_index()
                self._select_nearest_visible_row(row)
            self.statusBar().showMessage(
                f"Canceled browser capture: {record.filename}."
            )
        else:
            data = dialog.download_data
            adapter_plan = build_adapter_plan(
                str(data["url"]),
                source_url=record.source_url,
                page_url=record.referer,
            )
            start_now = (
                dialog.result_action == BrowserCaptureDialog.ACTION_START
            )
            self.repository.update(
                record.id,
                url=str(data["url"]),
                source_url=adapter_plan.source_url,
                site_adapter=adapter_plan.adapter,
                adapter_status="Ready",
                resolved_at="",
                filename=str(data["filename"]),
                folder=str(data["folder"]),
                category=str(data["category"]),
                connections=min(
                    int(data["connections"]),
                    adapter_plan.connection_limit,
                ),
                description=str(data["description"]),
                status=(
                    DownloadStatus.QUEUED
                    if start_now
                    else DownloadStatus.PAUSED
                ),
                capture_pending=False,
                auto_start=False,
                error="",
            )
            refreshed = self.repository.get(record.id)
            row = self.row_for_id.get(record.id)
            if refreshed and row is not None:
                self._render_record(row, refreshed)
                self.table.selectRow(row)
            self._apply_category_filter()
            if start_now:
                if refreshed:
                    self._ensure_progress_dialog(refreshed)
                self._request_start(record.id)
            elif refreshed:
                self.statusBar().showMessage(
                    f"Added for later: {refreshed.filename}."
                )

        self._capture_dialog_open = False
        self._active_capture_id = None
        self._update_action_states()
        self._update_summary()
        QTimer.singleShot(0, self._show_next_browser_capture)

    def _poll_show_manager_request(self) -> None:
        path = self._show_manager_request_path
        if path is None or not path.exists():
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        self._show_manager()

    def _show_manager(self) -> None:
        was_capture_only = self._capture_only
        self._capture_only = False
        self._capture_idle_timer.stop()
        if was_capture_only:
            QApplication.instance().setQuitOnLastWindowClosed(True)
            self._schedule_timer.start()
            QTimer.singleShot(0, self._restore_queued_downloads)
            QTimer.singleShot(0, self._check_scheduled_downloads)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _check_capture_idle(self) -> None:
        if not self._capture_only or self._closing_application:
            return
        if (
            self._capture_dialog_open
            or self._pending_capture_ids
            or self.workers
            or self.download_queue.is_busy
            or self.progress_dialogs
            or (
                self._show_manager_request_path is not None
                and self._show_manager_request_path.exists()
            )
        ):
            return
        if any(
            record.capture_pending
            for record in self.repository.list_all()
        ):
            return

        self._capture_idle_timer.stop()
        self.close()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def _write_heartbeat(self) -> None:
        if self._heartbeat_path is None:
            return
        try:
            self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            self._heartbeat_path.touch(exist_ok=True)
            release_launch_guard(
                self._heartbeat_path.with_name("app.launching")
            )
        except OSError:
            pass

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing_application = True
        self._heartbeat_timer.stop()
        self._show_manager_timer.stop()
        self._browser_poll_timer.stop()
        self._schedule_timer.stop()
        self._capture_idle_timer.stop()
        active_workers = [
            worker for worker in self.workers.values() if worker.isRunning()
        ]
        for worker in active_workers:
            worker.shutdown()
        for worker in active_workers:
            if not worker.wait(10_000):
                worker.terminate()
                worker.wait(2_000)
        if self._heartbeat_path is not None:
            try:
                self._heartbeat_path.unlink(missing_ok=True)
            except OSError:
                pass
        event.accept()
