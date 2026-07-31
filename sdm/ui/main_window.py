from __future__ import annotations

from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl, QByteArray, QPoint, QSize
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices, QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QToolButton,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QSizeGrip,
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
from sdm.queue_optimizer import optimize_queue
from sdm.removal import (
    delete_download_artifacts,
    destination_is_shared,
)
from sdm.schedule import format_scheduled_local, schedule_is_due
from sdm.ui.add_dialog import AddDownloadDialog
from sdm.ui.batch_preview_dialog import BatchPreviewDialog
from sdm.ui.browser_capture_dialog import BrowserCaptureDialog
from sdm.ui.download_progress_dialog import DownloadProgressDialog
from sdm.ui.duplicate_dialog import DuplicateDownloadDialog
from sdm.ui.design_system import METRICS, SPACING
from sdm.ui.icons import application_icon, glyph_icon
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
from sdm.performance import LatestValueBuffer


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

STATUS_FILTERS = (
    ("All statuses", ""),
    ("Active", "active"),
    ("Waiting", "waiting"),
    ("Completed", "completed"),
    ("Failed", "failed"),
    ("Paused", "paused"),
)


SPEED_LIMITS = (
    ("Unlimited", 0),
    ("512 KB/s", 512 * 1024),
    ("1 MB/s", 1024 * 1024),
    ("2 MB/s", 2 * 1024 * 1024),
    ("5 MB/s", 5 * 1024 * 1024),
    ("10 MB/s", 10 * 1024 * 1024),
)


class _IntegratedTitleBar(QFrame):
    """Single integrated application header matching the SDM 2.8 design language."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._drag_offset = QPoint()
        self.setObjectName("integratedTitleBar")
        self.setFixedHeight(METRICS.title_bar_height)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.sm, SPACING.xs, SPACING.xs, SPACING.xs)
        layout.setSpacing(SPACING.xs)

        mark = QLabel("SDM")
        mark.setObjectName("titleBrandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(52, 36)
        mark.setToolTip("Smart Download Manager")
        layout.addWidget(mark)

        title = QLabel(f"SDM {APP_VERSION}")
        title.setObjectName("titleBrandText")
        layout.addWidget(title)
        subtitle = QLabel("Smart Download Manager")
        subtitle.setObjectName("titleBrandSubtitle")
        layout.addWidget(subtitle)
        layout.addStretch(1)

        self.health_badge = QLabel("●  SYSTEM READY")
        self.health_badge.setObjectName("healthBadge")
        layout.addWidget(self.health_badge)

        self.media_button = QPushButton("Media inspector")
        self.media_button.setIcon(glyph_icon("media"))
        self.duplicates_button = QPushButton("Duplicates")
        self.duplicates_button.setIcon(glyph_icon("duplicate"))
        self.system_button = QPushButton("System center")
        self.system_button.setIcon(glyph_icon("settings"))
        for button in (self.media_button, self.duplicates_button, self.system_button):
            button.setObjectName("titleToolButton")
            button.setFlat(True)
            button.setIconSize(QSize(METRICS.icon_size, METRICS.icon_size))
            layout.addWidget(button)
        self.media_button.setCheckable(True)
        self.media_button.clicked.connect(window._toggle_media_inspector)
        self.duplicates_button.clicked.connect(window._open_storage_manager)
        self.system_button.clicked.connect(window._open_system_center)

        self.minimize_button = QPushButton()
        self.minimize_button.setIcon(glyph_icon("minimize"))
        self.maximize_button = QPushButton()
        self.maximize_button.setIcon(glyph_icon("maximize"))
        self.close_button = QPushButton()
        self.close_button.setIcon(glyph_icon("close"))
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            button.setObjectName("windowControlButton")
            button.setFixedSize(38, 30)
            layout.addWidget(button)
        self.close_button.setObjectName("windowCloseButton")
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_maximize)
        self.close_button.clicked.connect(window.close)

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
            self.maximize_button.setIcon(glyph_icon("maximize"))
        else:
            self._window.showMaximized()
            self.maximize_button.setIcon(glyph_icon("restore"))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and not self._window.isMaximized():
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()


class MainWindow(QMainWindow):
    COL_FILE = 0
    COL_SESSION = 1
    COL_PRIORITY = 2
    COL_CATEGORY = 3
    COL_SIZE = 4
    COL_PROGRESS = 5
    COL_STATUS = 6
    COL_MODE = 7
    COL_SPEED = 8
    COL_ETA = 9
    COL_CHECKSUM = 10
    COL_FOLDER = 11
    COL_ACTIONS = 12

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
        self._live_speeds: dict[str, float] = {}
        self._progress_buffer: LatestValueBuffer[tuple[int, int, float, int | None]] = LatestValueBuffer()
        self._activity_refresh_pending = False
        self._card_items: dict[str, QListWidgetItem] = {}

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
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(application_icon())
        self.resize(1320, 760)
        self.setMinimumSize(860, 560)
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

        # Coalesce worker progress to 12 FPS. This prevents a fast connection
        # from forcing hundreds of full table repaints per second.
        self._ui_flush_timer = QTimer(self)
        self._ui_flush_timer.setInterval(83)
        self._ui_flush_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._ui_flush_timer.timeout.connect(self._flush_progress_updates)
        self._ui_flush_timer.start()

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
        container.setObjectName("appShell")
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(SPACING.sm, SPACING.xs, SPACING.sm, SPACING.xs)
        root_layout.setSpacing(SPACING.xs)

        self.integrated_title_bar = _IntegratedTitleBar(self)
        root_layout.addWidget(self.integrated_title_bar)

        # The title bar is the only application header. Tool aliases keep the
        # existing action/update code connected without a duplicated second row.
        self.health_badge = self.integrated_title_bar.health_badge
        self.media_inspector_button = self.integrated_title_bar.media_button
        self.storage_button = self.integrated_title_bar.duplicates_button
        self.system_center_button = self.integrated_title_bar.system_button

        # Keep metric objects for the existing update engine; values are now
        # presented in the status bar rather than large dashboard cards.
        self.total_metric = self._create_metric("0", "Total downloads")
        self.active_metric = self._create_metric("0", "Active now")
        self.queued_metric = self._create_metric("0", "Waiting")
        self.completed_metric = self._create_metric("0", "Completed")
        self.failed_metric = self._create_metric("0", "Failed")
        self.speed_metric = self._create_metric("0 B/s", "Live transfer")
        for metric in (self.total_metric, self.active_metric, self.queued_metric,
                       self.completed_metric, self.failed_metric, self.speed_metric):
            metric.hide()

        actions = QFrame()
        actions.setObjectName("compactToolbar")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(SPACING.sm, SPACING.xs, SPACING.sm, SPACING.xs)
        action_layout.setSpacing(SPACING.xs)

        self.add_button = QPushButton("Add")
        self.add_button.setIcon(glyph_icon("add", "#092216"))
        self.add_button.setObjectName("primaryButton")
        self.add_button.clicked.connect(self._add_download)
        self.start_button = QPushButton("Resume")
        self.start_button.setIcon(glyph_icon("resume"))
        self.start_button.clicked.connect(self._start_selected)
        self.start_all_button = QPushButton("Start all")
        self.start_all_button.clicked.connect(self._start_all)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setIcon(glyph_icon("pause"))
        self.pause_button.clicked.connect(self._pause_selected)
        self.pause_all_button = QPushButton("Pause all")
        self.pause_all_button.clicked.connect(self._pause_all)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(glyph_icon("stop", "#ffb7c0"))
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self._cancel_selected)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setIcon(glyph_icon("trash", "#ffb7c0"))
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.clicked.connect(self._delete_selected)
        self.delete_all_button = QPushButton("Delete all")
        self.delete_all_button.setObjectName("dangerButton")
        self.delete_all_button.clicked.connect(self._delete_all)
        self.folder_button = QPushButton("Folder")
        self.folder_button.setIcon(glyph_icon("folder"))
        self.folder_button.clicked.connect(self._open_selected_folder)

        toolbar_buttons = (
            self.add_button, self.start_button, self.pause_button,
            self.cancel_button, self.delete_button, self.folder_button,
        )
        toolbar_tooltips = {
            self.add_button: "Add a new download (Ctrl+N)",
            self.start_button: "Start or resume the selected download (Ctrl+R)",
            self.pause_button: "Pause the selected download (Ctrl+P)",
            self.cancel_button: "Cancel the selected download",
            self.delete_button: "Delete the selected download (Delete)",
            self.folder_button: "Open the selected download folder (Ctrl+O)",
        }
        for button in toolbar_buttons:
            button.setIconSize(QSize(METRICS.icon_size, METRICS.icon_size))
            button.setFixedHeight(METRICS.toolbar_height)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(toolbar_tooltips[button])
            action_layout.addWidget(button)
        action_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setObjectName("toolbarSearch")
        self.search_input.setPlaceholderText("Search downloads…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._workspace_filter_changed)
        self.search_input.setMinimumWidth(220)
        self.search_input.setFixedHeight(METRICS.toolbar_height)
        self.search_input.setToolTip("Filter downloads by file name, URL, folder, category, session or tag (Ctrl+F)")
        action_layout.addWidget(self.search_input, 1)

        self.filters_button = QPushButton("Filters")
        self.filters_button.setIcon(glyph_icon("filter"))
        self.filters_button.setObjectName("filterToggleButton")
        self.filters_button.setCheckable(True)
        self.filters_button.clicked.connect(self._toggle_filters_panel)
        self.filters_button.setFixedHeight(METRICS.toolbar_height)
        self.filters_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filters_button.setToolTip("Show or hide advanced filters")
        action_layout.addWidget(self.filters_button)

        self.more_button = QToolButton()
        self.more_button.setObjectName("menuOnlyButton")
        self.more_button.setText("⋯")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(self.more_button)
        self.more_menu.addAction("Batch preview", self._open_batch_preview)
        self.more_menu.addAction("Optimize waiting queue", self._optimize_waiting_queue)
        self.more_button.setMenu(self.more_menu)
        self.more_button.setFixedSize(METRICS.toolbar_height, METRICS.toolbar_height)
        self.more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_button.setToolTip("More download tools")
        action_layout.addWidget(self.more_button)
        root_layout.addWidget(actions)

        self._install_workspace_shortcuts()

        # Collapsible filters: available when needed, absent from the primary flow.
        self.filter_panel = QFrame()
        self.filter_panel.setObjectName("filterPanel")
        control_layout = QGridLayout(self.filter_panel)
        control_layout.setContentsMargins(12, 10, 12, 10)
        control_layout.setHorizontalSpacing(10)
        control_layout.setVerticalSpacing(7)

        self.category_filter_combo = QComboBox()
        self.category_filter_combo.addItem("All categories", "")
        for category in DOWNLOAD_CATEGORIES:
            self.category_filter_combo.addItem(category, category)
        self.category_filter_combo.currentIndexChanged.connect(self._workspace_filter_changed)

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItem("All statuses", "")
        for status in DownloadStatus:
            self.status_filter_combo.addItem(status.value.title(), status.value)
        self.status_filter_combo.currentIndexChanged.connect(self._workspace_filter_changed)

        self.session_filter_combo = QComboBox()
        self.session_filter_combo.currentIndexChanged.connect(self._workspace_filter_changed)
        self.new_session_button = QPushButton("＋ New session")
        self.new_session_button.setObjectName("compactButton")
        self.new_session_button.clicked.connect(self._create_empty_session)
        self.manage_sessions_button = QPushButton("Manage sessions")
        self.manage_sessions_button.setObjectName("compactButton")
        self.manage_sessions_button.clicked.connect(self._open_session_manager)

        self.priority_filter_combo = QComboBox()
        self.priority_filter_combo.addItem("All priorities", "")
        for priority in ("Highest", "High", "Normal", "Low", "Background"):
            self.priority_filter_combo.addItem(priority, priority)
        self.priority_filter_combo.currentIndexChanged.connect(self._workspace_filter_changed)

        self.speed_limit_combo = QComboBox()
        for label, value in SPEED_LIMITS:
            self.speed_limit_combo.addItem(label, value)
        selected_speed = self.speed_limit_combo.findData(self.bandwidth_limiter.limit_bytes_per_second)
        self.speed_limit_combo.setCurrentIndex(selected_speed if selected_speed >= 0 else 0)
        self.speed_limit_combo.currentIndexChanged.connect(self._speed_limit_changed)

        self.concurrent_combo = QComboBox()
        for value in (1, 2, 3, 4):
            self.concurrent_combo.addItem(str(value), value)
        selected_index = self.concurrent_combo.findData(self.download_queue.max_active)
        self.concurrent_combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.concurrent_combo.currentIndexChanged.connect(self._max_active_changed)
        self.smart_rules_button = QPushButton("Smart rules")
        self.smart_rules_button.clicked.connect(self._open_smart_rules)

        fields = [
            ("Session", self.session_filter_combo), ("Category", self.category_filter_combo),
            ("Status", self.status_filter_combo), ("Priority", self.priority_filter_combo),
            ("Speed limit", self.speed_limit_combo), ("Concurrent", self.concurrent_combo),
        ]
        for index, (label_text, widget) in enumerate(fields):
            row, col = divmod(index, 3)
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            control_layout.addWidget(label, row * 2, col)
            control_layout.addWidget(widget, row * 2 + 1, col)
        session_actions = QHBoxLayout()
        session_actions.addWidget(self.new_session_button)
        session_actions.addWidget(self.manage_sessions_button)
        session_actions.addStretch()
        session_actions.addWidget(self.smart_rules_button)
        control_layout.addLayout(session_actions, 4, 0, 1, 3)
        for col in range(3):
            control_layout.setColumnStretch(col, 1)
        self.filter_panel.hide()
        root_layout.addWidget(self.filter_panel)

        table_card = QFrame()
        table_card.setObjectName("tableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        table_title_bar = QFrame()
        table_title_bar.setObjectName("compactTableTitleBar")
        table_title_layout = QHBoxLayout(table_title_bar)
        table_title_layout.setContentsMargins(12, 7, 12, 7)
        table_title = QLabel("Downloads")
        table_title.setObjectName("sectionTitle")
        self.summary_label = QLabel("No downloads")
        self.summary_label.setObjectName("summaryText")
        table_title_layout.addWidget(table_title)
        table_title_layout.addWidget(self.summary_label)
        table_title_layout.addStretch()

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.setObjectName("viewModeCombo")
        self.view_mode_combo.addItem("Table", "table")
        self.view_mode_combo.addItem("Cards", "cards")
        saved_view = self.repository.get_setting("workspace_view_mode", "table")
        view_index = self.view_mode_combo.findData(saved_view)
        self.view_mode_combo.setCurrentIndex(view_index if view_index >= 0 else 0)
        self.view_mode_combo.currentIndexChanged.connect(self._view_mode_changed)
        table_title_layout.addWidget(self.view_mode_combo)

        self.columns_button = QToolButton()
        self.columns_button.setObjectName("menuOnlyButton")
        self.columns_button.setText("Columns")
        self.columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.columns_menu = QMenu(self.columns_button)
        self.columns_button.setMenu(self.columns_menu)
        table_title_layout.addWidget(self.columns_button)

        self.activity_toggle = QPushButton("Activity (0)")
        self.activity_toggle.setObjectName("compactButton")
        self.activity_toggle.setIcon(glyph_icon("activity", "#51e69a", 18))
        self.activity_toggle.clicked.connect(self._toggle_activity_panel)
        table_title_layout.addWidget(self.activity_toggle)
        table_layout.addWidget(table_title_bar)

        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels([
            "File", "Session", "Priority", "Category", "Size", "Progress",
            "Status", "Mode", "Speed", "ETA", "SHA-256", "Folder", "",
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.verticalHeader().setMinimumSectionSize(52)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_download_context_menu)
        self.table.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.table.itemDoubleClicked.connect(lambda _item: self._open_selected_folder())

        header_view = self.table.horizontalHeader()
        header_view.setStretchLastSection(True)
        header_view.setMinimumHeight(38)
        header_view.setHighlightSections(False)
        header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_view.setSectionResizeMode(self.COL_FILE, QHeaderView.ResizeMode.Stretch)
        for column in (self.COL_SESSION, self.COL_PRIORITY, self.COL_CATEGORY, self.COL_SIZE,
                       self.COL_STATUS, self.COL_MODE, self.COL_SPEED, self.COL_ETA,
                       self.COL_CHECKSUM):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(self.COL_PROGRESS, QHeaderView.ResizeMode.Fixed)
        header_view.resizeSection(self.COL_PROGRESS, 220)
        header_view.setSectionResizeMode(self.COL_FOLDER, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        header_view.resizeSection(self.COL_ACTIONS, 46)
        header_view.setSectionsMovable(True)
        header_view.sectionResized.connect(self._save_workspace_layout)
        header_view.sectionMoved.connect(self._save_workspace_layout)

        self.card_list = QListWidget()
        self.card_list.setObjectName("downloadCardList")
        self.card_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.card_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.card_list.setMovement(QListWidget.Movement.Static)
        self.card_list.setSpacing(12)
        self.card_list.setUniformItemSizes(False)
        self.card_list.itemDoubleClicked.connect(self._card_item_activated)

        self.workspace_views = QStackedWidget()
        self.empty_state = QLabel("No downloads yet\nAdd a link or file to start downloading")
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.empty_state.setParent(self.table.viewport())
        self.empty_state.hide()

        self.workspace_views.addWidget(self.table)
        self.workspace_views.addWidget(self.card_list)
        table_layout.addWidget(self.workspace_views, 1)
        self._build_columns_menu()
        self._restore_workspace_layout()
        for column in (self.COL_MODE, self.COL_CHECKSUM, self.COL_FOLDER):
            self.table.setColumnHidden(column, True)
        self._view_mode_changed()
        self.activity_panel = self._build_activity_panel()
        self.activity_panel.show()

        workspace_left = QWidget()
        workspace_left_layout = QVBoxLayout(workspace_left)
        workspace_left_layout.setContentsMargins(0, 0, 0, 0)
        workspace_left_layout.setSpacing(8)
        workspace_left_layout.addWidget(table_card, 1)
        workspace_left_layout.addWidget(self.activity_panel)

        self.media_inspector_panel = self._build_details_panel()
        self.media_inspector_panel.setMinimumWidth(360)
        self.media_inspector_panel.setMaximumWidth(470)
        self.media_inspector_panel.hide()

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setObjectName("workspaceSplitter")
        self.workspace_splitter.addWidget(workspace_left)
        self.workspace_splitter.addWidget(self.media_inspector_panel)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        self.workspace_splitter.setSizes([1000, 360])
        root_layout.addWidget(self.workspace_splitter, 1)

        self.setCentralWidget(container)
        self.status_total = QLabel("Total: 0")
        self.status_running = QLabel("Running: 0")
        self.status_queue = QLabel("Waiting: 0")
        self.status_completed = QLabel("Completed: 0")
        self.status_failed = QLabel("Failed: 0")
        self.status_speed = QLabel("Speed: 0 B/s")
        status_metrics = (
            (self.status_total, "total"),
            (self.status_running, "running"),
            (self.status_queue, "waiting"),
            (self.status_completed, "completed"),
            (self.status_failed, "failed"),
            (self.status_speed, "speed"),
        )
        for label, metric_kind in status_metrics:
            label.setObjectName("statusMetric")
            label.setProperty("metric", metric_kind)
            label.setToolTip(f"Current {metric_kind} download metric")
            self.statusBar().addPermanentWidget(label)
        self.statusBar().addPermanentWidget(QSizeGrip(self))
        self.statusBar().showMessage("Ready — add a direct URL or capture a download from your browser.")

    def _install_workspace_shortcuts(self) -> None:
        """Install discoverable keyboard shortcuts for the primary workflow."""
        shortcuts = (
            ("Ctrl+N", self._add_download),
            ("Ctrl+F", lambda: (self.search_input.setFocus(), self.search_input.selectAll())),
            ("Ctrl+R", self._start_selected),
            ("Ctrl+P", self._pause_selected),
            ("Ctrl+O", self._open_selected_folder),
            ("Delete", self._delete_selected),
            ("Escape", lambda: self.search_input.clear() if self.search_input.hasFocus() else None),
        )
        self._workspace_shortcut_actions = []
        for key, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(key)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self._workspace_shortcut_actions.append(action)

    def _toggle_filters_panel(self) -> None:
        visible = not self.filter_panel.isVisible()
        self.filter_panel.setVisible(visible)
        self.filters_button.setChecked(visible)
        self.filters_button.setText("Hide filters" if visible else "Filters")


    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _apply_responsive_layout(self, width: int) -> None:
        if not hasattr(self, "table"):
            return
        compact = width < 1180
        very_compact = width < 980

        for button in (self.media_inspector_button, self.storage_button, self.system_center_button):
            button.setVisible(not compact)
        self.more_button.setVisible(True)

        self.health_badge.setVisible(not very_compact)
        if very_compact and hasattr(self, "media_inspector_panel") and self.media_inspector_panel.isVisible():
            self.media_inspector_panel.hide()
            self.media_inspector_button.setChecked(False)
        self.search_input.setMaximumWidth(420 if width >= 1300 else 300 if width >= 1050 else 240)
        self.columns_button.setVisible(width >= 900)
        self.view_mode_combo.setVisible(width >= 820)
        self.status_failed.setVisible(width >= 980)
        self.status_queue.setVisible(width >= 900)
        card_width = 360 if width >= 1300 else 310 if width >= 1050 else 270
        self.card_list.setGridSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(card_width + 14, 170))
        self._update_empty_state()

        hidden = {
            self.COL_CHECKSUM: width < 1420,
            self.COL_FOLDER: width < 1260,
            self.COL_MODE: width < 1120,
            self.COL_CATEGORY: width < 1040,
            self.COL_SESSION: width < 940,
            self.COL_PRIORITY: width < 900,
        }
        for column, should_hide in hidden.items():
            self.table.setColumnHidden(column, should_hide)
        progress_width = 185 if width >= 1180 else 145 if width >= 980 else 120
        self.table.horizontalHeader().resizeSection(self.COL_PROGRESS, progress_width)



    def _build_columns_menu(self) -> None:
        self.columns_menu.clear()
        labels = [
            "File", "Session", "Priority", "Category", "Size", "Progress",
            "Status", "Mode", "Speed", "ETA", "SHA-256", "Folder", "Actions",
        ]
        for column, label in enumerate(labels):
            if column == self.COL_ACTIONS:
                continue
            action = self.columns_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(column))
            action.toggled.connect(lambda checked, col=column: self._set_column_visible(col, checked))
        self.columns_menu.addSeparator()
        self.columns_menu.addAction("Reset layout", self._reset_workspace_layout)

    def _set_column_visible(self, column: int, visible: bool) -> None:
        self.table.setColumnHidden(column, not visible)
        self._save_workspace_layout()

    def _save_workspace_layout(self, *_args) -> None:
        if not hasattr(self, "table"):
            return
        state = bytes(self.table.horizontalHeader().saveState().toBase64()).decode("ascii")
        hidden = ",".join(str(i) for i in range(self.table.columnCount()) if self.table.isColumnHidden(i))
        self.repository.set_setting("workspace_header_state", state)
        self.repository.set_setting("workspace_hidden_columns", hidden)

    def _restore_workspace_layout(self) -> None:
        state = self.repository.get_setting("workspace_header_state", "")
        if state:
            self.table.horizontalHeader().restoreState(QByteArray.fromBase64(state.encode("ascii")))
        hidden = self.repository.get_setting("workspace_hidden_columns", "")
        for value in hidden.split(","):
            if value.strip().isdigit():
                self.table.setColumnHidden(int(value), True)

    def _reset_workspace_layout(self) -> None:
        self.repository.set_setting("workspace_header_state", "")
        self.repository.set_setting("workspace_hidden_columns", "")
        for column in range(self.table.columnCount()):
            self.table.setColumnHidden(column, False)
        self.table.horizontalHeader().resetDefaultSectionSize()
        self.table.horizontalHeader().resizeSection(self.COL_PROGRESS, 185)
        self._build_columns_menu()
        self.statusBar().showMessage("Workspace layout reset.", 2500)

    def _view_mode_changed(self) -> None:
        mode = str(self.view_mode_combo.currentData() or "table")
        self.repository.set_setting("workspace_view_mode", mode)
        self.workspace_views.setCurrentIndex(1 if mode == "cards" else 0)
        if mode == "cards":
            self._refresh_card_view()

    def _refresh_card_view(self) -> None:
        if not hasattr(self, "card_list"):
            return
        self.card_list.clear()
        self._card_items.clear()
        for record in self.repository.list_all():
            if not self._record_matches_workspace(record):
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setSizeHint(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(310, 154))
            card = QFrame()
            card.setObjectName("downloadCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(7)
            title = QLabel(record.filename)
            title.setObjectName("downloadCardTitle")
            title.setWordWrap(True)
            meta = QLabel(f"{record.session_name}  •  {record.priority}  •  {STATUS_LABELS[record.status]}")
            meta.setObjectName("downloadCardMeta")
            progress = QProgressBar()
            progress.setRange(0, 1000)
            progress.setValue(int(record.progress * 1000) if record.total_bytes else 0)
            progress.setFormat(f"{record.progress * 100:.1f}%" if record.total_bytes else "Waiting")
            detail = QLabel(f"{format_bytes(record.total_bytes) if record.total_bytes else 'Unknown size'}    {format_speed(self._live_speeds.get(record.id, 0.0))}")
            detail.setObjectName("downloadCardMeta")
            layout.addWidget(title)
            layout.addWidget(meta)
            layout.addWidget(progress)
            layout.addWidget(detail)
            self.card_list.addItem(item)
            self.card_list.setItemWidget(item, card)
            self._card_items[record.id] = item

    def _record_matches_workspace(self, record: DownloadRecord) -> bool:
        query = self.search_input.text().strip().casefold()
        category = str(self.category_filter_combo.currentData() or "")
        status_filter = str(self.status_filter_combo.currentData() or "")
        session = str(self.session_filter_combo.currentData() or "")
        priority = str(self.priority_filter_combo.currentData() or "")
        haystack = " ".join((record.filename, record.url, record.folder, record.category, record.session_name, record.priority, record.tags or "")).casefold()
        if query and query not in haystack:
            return False
        if category and record.category != category:
            return False
        if session and record.session_name != session:
            return False
        if priority and record.priority != priority:
            return False
        if status_filter == "active" and record.status not in {DownloadStatus.DOWNLOADING, DownloadStatus.RETRYING, DownloadStatus.VERIFYING}:
            return False
        if status_filter == "waiting" and record.status not in {DownloadStatus.QUEUED, DownloadStatus.SCHEDULED}:
            return False
        if status_filter == "completed" and record.status != DownloadStatus.COMPLETED:
            return False
        if status_filter == "failed" and record.status != DownloadStatus.FAILED:
            return False
        if status_filter == "paused" and record.status != DownloadStatus.PAUSED:
            return False
        return True

    def _card_item_activated(self, item: QListWidgetItem) -> None:
        record_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        row = self.row_for_id.get(record_id)
        if row is not None:
            self.table.selectRow(row)
            self._open_selected_folder()

    def _show_session_context_menu(self, position) -> None:
        item = self.sessions_list.itemAt(position)
        if item is None:
            return
        session_name = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not session_name:
            return
        menu = QMenu(self)
        rename_action = menu.addAction("Rename session")
        delete_action = menu.addAction("Delete session")
        delete_action.setEnabled(session_name != "Today")
        chosen = menu.exec(self.sessions_list.viewport().mapToGlobal(position))
        if chosen is rename_action:
            self._rename_session(session_name)
        elif chosen is delete_action:
            self._delete_session(session_name)

    def _rename_session(self, old_name: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        new_name, accepted = QInputDialog.getText(self, "Rename Session", "Session name:", text=old_name)
        new_name = new_name.strip()[:80]
        if not accepted or not new_name or new_name == old_name:
            return
        for record in self.repository.list_all():
            if record.session_name == old_name:
                self.repository.update(record.id, session_name=new_name)
        self._refresh_session_filter()
        self._update_empty_state()
        self._reload_workspace_records()
        self._append_activity(f"Session renamed: {old_name} → {new_name}")

    def _delete_session(self, session_name: str) -> None:
        answer = QMessageBox.question(self, "Delete Session", f"Move all downloads from '{session_name}' to Today?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        for record in self.repository.list_all():
            if record.session_name == session_name:
                self.repository.update(record.id, session_name="Today")
        self._refresh_session_filter()
        self._reload_workspace_records()
        self._append_activity(f"Session removed: {session_name}")

    def _reload_workspace_records(self) -> None:
        self.table.setRowCount(0)
        self.row_for_id.clear()
        for record in self.repository.list_all():
            self._append_record(record)
        self._apply_category_filter()
        self._refresh_card_view()



    def _build_activity_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("activityPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(4)

        self._activity_events: list[dict[str, str]] = []
        self._activity_filter = "Activity"
        self._activity_query = ""

        header = QHBoxLayout()
        header.setSpacing(4)
        self.activity_tab_buttons = {}
        for tab_name in ("Activity", "Completed", "Errors", "Browser", "System"):
            button = QPushButton(tab_name)
            button.setObjectName("activityTabActive" if tab_name == "Activity" else "activityTab")
            button.setCheckable(True)
            button.setChecked(tab_name == "Activity")
            button.clicked.connect(lambda checked=False, name=tab_name: self._set_activity_filter(name))
            self.activity_tab_buttons[tab_name] = button
            header.addWidget(button)
        header.addStretch()

        self.activity_search = QLineEdit()
        self.activity_search.setObjectName("activitySearch")
        self.activity_search.setPlaceholderText("Search activity…")
        self.activity_search.setClearButtonEnabled(True)
        self.activity_search.setMaximumWidth(220)
        self.activity_search.setToolTip("Filter events by source, message, type or details")
        self.activity_search.textChanged.connect(self._activity_search_changed)
        header.addWidget(self.activity_search)

        self.activity_count = QLabel("0")
        self.activity_count.setObjectName("activityBadge")
        header.addWidget(self.activity_count)

        clear_button = QPushButton("Clear")
        clear_button.setObjectName("activityHeaderButton")
        clear_button.setIcon(glyph_icon("trash", "#dce8e2", 16))
        clear_button.setToolTip("Clear all activity events")
        clear_button.clicked.connect(self._clear_activity_events)
        header.addWidget(clear_button)

        self.activity_collapse_button = QPushButton()
        self.activity_collapse_button.setObjectName("activityHeaderButton")
        self.activity_collapse_button.setIcon(glyph_icon("minimize", "#dce8e2", 16))
        self.activity_collapse_button.setToolTip("Collapse Activity Center")
        self.activity_collapse_button.clicked.connect(self._toggle_activity_panel)
        header.addWidget(self.activity_collapse_button)
        layout.addLayout(header)

        self.activity_table = QTableWidget(0, 5)
        self.activity_table.setObjectName("activityTable")
        self.activity_table.setHorizontalHeaderLabels(["Time", "Type", "Source", "Message", "Details"])
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.setShowGrid(False)
        self.activity_table.setAlternatingRowColors(True)
        self.activity_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.activity_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.activity_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.activity_table.setWordWrap(False)
        self.activity_table.setSortingEnabled(False)
        self.activity_table.verticalHeader().setDefaultSectionSize(34)
        self.activity_table.setMaximumHeight(190)
        activity_header = self.activity_table.horizontalHeader()
        activity_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        activity_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        activity_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        activity_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        activity_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.activity_table)

        self._append_activity("SDM workspace ready", event_type="System", source="Workspace", details="Ready")
        return panel

    def _activity_search_changed(self, text: str) -> None:
        self._activity_query = text.strip().casefold()
        self._schedule_activity_refresh()

    def _set_activity_filter(self, name: str) -> None:
        self._activity_filter = name
        for tab_name, button in self.activity_tab_buttons.items():
            active = tab_name == name
            button.setChecked(active)
            button.setObjectName("activityTabActive" if active else "activityTab")
            button.style().unpolish(button)
            button.style().polish(button)
        self._refresh_activity_table()

    def _clear_activity_events(self) -> None:
        self._activity_events.clear()
        self._refresh_activity_table()

    def _toggle_activity_panel(self) -> None:
        visible = self.activity_panel.isVisible()
        self.activity_panel.setVisible(not visible)
        count = len(getattr(self, "_activity_events", []))
        self.activity_toggle.setText(f"Activity ({count})")

    def _append_activity(
        self,
        message: str,
        *,
        event_type: str | None = None,
        source: str = "SDM",
        details: str = "—",
    ) -> None:
        if not hasattr(self, "_activity_events"):
            return
        lower = message.casefold()
        if event_type is None:
            if any(word in lower for word in ("failed", "error", "reset", "mismatch")):
                event_type = "Error"
            elif any(word in lower for word in ("completed", "verified", "finished")):
                event_type = "Completed"
            elif any(word in lower for word in ("browser", "capture", "extension")):
                event_type = "Browser"
            elif any(word in lower for word in ("system", "engine", "tool", "workspace", "session")):
                event_type = "System"
            else:
                event_type = "Download"
        self._activity_events.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": event_type,
            "source": source,
            "message": message,
            "details": details,
        })
        del self._activity_events[100:]
        self._schedule_activity_refresh()

    def _schedule_activity_refresh(self) -> None:
        if self._activity_refresh_pending:
            return
        self._activity_refresh_pending = True
        QTimer.singleShot(75, self._flush_activity_refresh)

    def _flush_activity_refresh(self) -> None:
        self._activity_refresh_pending = False
        self._refresh_activity_table()

    def _refresh_activity_table(self) -> None:
        if not hasattr(self, "activity_table"):
            return
        selected = self._activity_filter
        query = getattr(self, "_activity_query", "")
        def matches(event: dict[str, str]) -> bool:
            if selected == "Completed":
                category_match = event["type"] in {"Completed", "Success"}
            elif selected == "Errors":
                category_match = event["type"] in {"Error", "Warning"}
            elif selected == "Activity":
                category_match = True
            else:
                category_match = event["type"] == selected
            if not category_match:
                return False
            if not query:
                return True
            searchable = " ".join((event["type"], event["source"], event["message"], event["details"])).casefold()
            return query in searchable

        events = [event for event in self._activity_events if matches(event)]
        self.activity_table.setRowCount(len(events))
        type_colors = {
            "Completed": "#51e69a",
            "Success": "#51e69a",
            "Warning": "#ffc766",
            "Error": "#ff626d",
            "Browser": "#65a5ff",
            "System": "#b79cff",
            "Download": "#dce8e2",
        }
        for row, event in enumerate(events):
            values = (event["time"], event["type"], event["source"], event["message"], event["details"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 1:
                    event_color = type_colors.get(event["type"], "#dce8e2")
                    item.setForeground(QColor(event_color))
                    item.setIcon(glyph_icon("activity", event_color, 14))
                if column == 3 and event["type"] in {"Error", "Warning"}:
                    item.setForeground(QColor(type_colors[event["type"]]))
                self.activity_table.setItem(row, column, item)
        total = len(self._activity_events)
        self.activity_count.setText(str(total))
        if hasattr(self, "activity_toggle"):
            self.activity_toggle.setText(f"Activity ({total})")

    def _show_download_context_menu(self, position) -> None:
        item = self.table.itemAt(position)
        if item is None:
            return
        self.table.selectRow(item.row())
        record = self._selected_record()
        if record is None:
            return

        menu = QMenu(self)
        download_menu = menu.addMenu("Download")
        start_action = download_menu.addAction("Start / Resume")
        pause_action = download_menu.addAction("Pause")
        cancel_action = download_menu.addAction("Cancel")

        priority_menu = menu.addMenu("Priority")
        priority_actions = {}
        for priority in ("Highest", "High", "Normal", "Low", "Background"):
            action = priority_menu.addAction(priority)
            action.setCheckable(True)
            action.setChecked(record.priority == priority)
            priority_actions[action] = priority

        session_menu = menu.addMenu("Move to session")
        session_names = self._known_sessions()
        session_actions = {}
        for session_name in session_names:
            action = session_menu.addAction(session_name)
            action.setCheckable(True)
            action.setChecked(record.session_name == session_name)
            session_actions[action] = session_name
        session_menu.addSeparator()
        new_session_action = session_menu.addAction("New session…")

        menu.addSeparator()
        file_menu = menu.addMenu("File")
        open_folder_action = file_menu.addAction("Open folder")
        copy_url_action = file_menu.addAction("Copy URL")
        copy_path_action = file_menu.addAction("Copy file path")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        start_action.setEnabled(record.status not in {DownloadStatus.DOWNLOADING, DownloadStatus.VERIFYING})
        pause_action.setEnabled(record.status in {DownloadStatus.DOWNLOADING, DownloadStatus.RETRYING})
        cancel_action.setEnabled(record.status not in {DownloadStatus.COMPLETED, DownloadStatus.CANCELED})
        open_folder_action.setEnabled(bool(record.folder))

        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen is start_action:
            self._start_selected()
        elif chosen is pause_action:
            self._pause_selected()
        elif chosen is cancel_action:
            self._cancel_selected()
        elif chosen in priority_actions:
            self._set_selected_priority(priority_actions[chosen])
        elif chosen in session_actions:
            self._move_selected_to_session(session_actions[chosen])
        elif chosen is new_session_action:
            self._create_session_for_selected()
        elif chosen is open_folder_action:
            self._open_selected_folder()
        elif chosen is copy_url_action:
            QApplication.clipboard().setText(record.url)
            self.statusBar().showMessage("Download URL copied.", 2500)
        elif chosen is copy_path_action:
            QApplication.clipboard().setText(str(record.final_path))
            self.statusBar().showMessage("File path copied.", 2500)
        elif chosen is delete_action:
            self._delete_selected()

    def _known_sessions(self) -> list[str]:
        sessions = {record.session_name for record in self.repository.list_all()}
        sessions.add("Today")
        return sorted(sessions, key=lambda value: (value != "Today", value.casefold()))

    def _refresh_session_filter(self) -> None:
        current = str(self.session_filter_combo.currentData() or "")
        self.session_filter_combo.blockSignals(True)
        self.session_filter_combo.clear()
        self.session_filter_combo.addItem("All sessions", "")
        for session_name in self._known_sessions():
            self.session_filter_combo.addItem(session_name, session_name)
        index = self.session_filter_combo.findData(current)
        self.session_filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self.session_filter_combo.blockSignals(False)

    def _refresh_sessions_sidebar(self) -> None:
        if not hasattr(self, "sessions_list"):
            return
        current = str(self.session_filter_combo.currentData() or "")
        records = self.repository.list_all()
        counts: dict[str, int] = {}
        for record in records:
            counts[record.session_name] = counts.get(record.session_name, 0) + 1
        self.sessions_list.blockSignals(True)
        self.sessions_list.clear()
        all_item = QListWidgetItem(f"All downloads   {len(records)}")
        all_item.setData(Qt.ItemDataRole.UserRole, "")
        self.sessions_list.addItem(all_item)
        for session_name in self._known_sessions():
            item = QListWidgetItem(f"{session_name}   {counts.get(session_name, 0)}")
            item.setData(Qt.ItemDataRole.UserRole, session_name)
            item.setToolTip(f"Show downloads in {session_name}")
            self.sessions_list.addItem(item)
        for index in range(self.sessions_list.count()):
            item = self.sessions_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == current:
                self.sessions_list.setCurrentItem(item)
                break
        self.sessions_list.blockSignals(False)

    def _sidebar_session_changed(self, current, _previous) -> None:
        if current is None:
            return
        session_name = str(current.data(Qt.ItemDataRole.UserRole) or "")
        index = self.session_filter_combo.findData(session_name)
        self.session_filter_combo.setCurrentIndex(index if index >= 0 else 0)

    def _create_empty_session(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, accepted = QInputDialog.getText(self, "New Session", "Session name:")
        if not accepted:
            return
        session_name = name.strip()[:80]
        if not session_name:
            return
        # Sessions are materialized when the first download is moved to them.
        if self.session_filter_combo.findData(session_name) < 0:
            self.session_filter_combo.addItem(session_name, session_name)
        self.session_filter_combo.setCurrentIndex(self.session_filter_combo.findData(session_name))
        self.statusBar().showMessage(f"Session ready: {session_name}. Move a download into it.", 3500)

    def _open_session_manager(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Session Manager")
        dialog.setMinimumSize(460, 390)
        layout = QVBoxLayout(dialog)
        title = QLabel("Sessions")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        info = QLabel("Create, rename or remove sessions without reducing the download workspace.")
        info.setWordWrap(True)
        info.setObjectName("summaryText")
        layout.addWidget(info)
        session_list = QListWidget()
        records = self.repository.list_all()
        counts: dict[str, int] = {}
        for record in records:
            counts[record.session_name] = counts.get(record.session_name, 0) + 1
        for name in self._known_sessions():
            item = QListWidgetItem(f"{name}    {counts.get(name, 0)} download(s)")
            item.setData(Qt.ItemDataRole.UserRole, name)
            session_list.addItem(item)
        layout.addWidget(session_list, 1)
        buttons = QHBoxLayout()
        create_button = QPushButton("＋ New session")
        rename_button = QPushButton("Rename")
        delete_button = QPushButton("Delete")
        close_button = QPushButton("⌃")
        buttons.addWidget(create_button)
        buttons.addWidget(rename_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        def selected_name() -> str:
            item = session_list.currentItem()
            return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

        def rebuild() -> None:
            session_list.clear()
            current_records = self.repository.list_all()
            current_counts: dict[str, int] = {}
            for record in current_records:
                current_counts[record.session_name] = current_counts.get(record.session_name, 0) + 1
            for name in self._known_sessions():
                item = QListWidgetItem(f"{name}    {current_counts.get(name, 0)} download(s)")
                item.setData(Qt.ItemDataRole.UserRole, name)
                session_list.addItem(item)

        def create_session() -> None:
            self._create_empty_session()
            rebuild()

        def rename_session() -> None:
            name = selected_name()
            if name:
                self._rename_session(name)
                rebuild()

        def delete_session() -> None:
            name = selected_name()
            if name and name != "Today":
                self._delete_session(name)
                rebuild()

        create_button.clicked.connect(create_session)
        rename_button.clicked.connect(rename_session)
        delete_button.clicked.connect(delete_session)
        close_button.clicked.connect(dialog.accept)
        dialog.exec()

    def _set_selected_priority(self, priority: str) -> None:
        record = self._selected_record()
        if record is None:
            return
        self.repository.update(record.id, priority=priority)
        refreshed = self.repository.get(record.id)
        if refreshed is not None:
            self._render_record(self.row_for_id[record.id], refreshed)
        self._apply_category_filter()
        self._append_activity(f"{record.filename} — priority changed to {priority}")
        self.statusBar().showMessage(f"Priority set to {priority}.", 2500)

    def _move_selected_to_session(self, session_name: str) -> None:
        record = self._selected_record()
        if record is None:
            return
        self.repository.update(record.id, session_name=session_name)
        refreshed = self.repository.get(record.id)
        if refreshed is not None:
            self._render_record(self.row_for_id[record.id], refreshed)
        self._refresh_session_filter()
        self._apply_category_filter()
        self._append_activity(f"{record.filename} — moved to {session_name}")
        self.statusBar().showMessage(f"Moved to session: {session_name}.", 2500)

    def _create_session_for_selected(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, accepted = QInputDialog.getText(
            self, "New Session", "Session name:"
        )
        if not accepted:
            return
        session_name = name.strip()[:80]
        if not session_name:
            return
        self._move_selected_to_session(session_name)

    def _build_details_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("detailsPanel")
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(470)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        panel_header = QHBoxLayout()
        title = QLabel("Media inspector")
        title.setObjectName("panelTitle")
        close_button = QPushButton()
        close_button.setObjectName("panelCloseButton")
        close_button.setIcon(glyph_icon("close", "#dce8e2", 16))
        close_button.setToolTip("Close media inspector")
        close_button.setFixedSize(30, 30)
        close_button.clicked.connect(self._toggle_media_inspector)
        panel_header.addWidget(title)
        panel_header.addStretch(1)
        panel_header.addWidget(close_button)

        self.details_filename = QLabel("Select a download")
        self.details_filename.setObjectName("detailsFilename")
        self.details_filename.setWordWrap(True)
        self.details_filename.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_status = QLabel("No selection")
        self.details_status.setObjectName("detailsStatus")
        self.details_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(panel_header)
        layout.addWidget(self.details_filename)
        layout.addWidget(self.details_status)

        self.inspector_tabs = QTabWidget()
        self.inspector_tabs.setObjectName("inspectorTabs")
        self.inspector_tabs.setDocumentMode(True)

        # General tab
        general_page = QWidget()
        general_layout = QVBoxLayout(general_page)
        general_layout.setContentsMargins(0, 8, 0, 0)
        form_frame = QFrame()
        form_frame.setObjectName("detailsForm")
        form = QFormLayout(form_frame)
        form.setContentsMargins(12, 12, 12, 12)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.detail_values: dict[str, QLabel] = {}
        for key, label in (
            ("progress", "Progress"),
            ("size", "Transferred"),
            ("connections", "Connections"),
            ("mode", "Mode"),
            ("category", "Category"),
            ("source", "Source"),
            ("checksum", "SHA-256"),
            ("folder", "Folder"),
        ):
            value = QLabel("—")
            value.setObjectName("detailValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.detail_values[key] = value
            form.addRow(label, value)
        general_layout.addWidget(form_frame)
        general_layout.addStretch(1)
        self.inspector_tabs.addTab(general_page, glyph_icon("info", "#51e69a", 16), "General")

        # Connections tab
        connections_page = QWidget()
        connections_layout = QVBoxLayout(connections_page)
        connections_layout.setContentsMargins(0, 8, 0, 0)
        connections_frame = QFrame()
        connections_frame.setObjectName("detailsForm")
        connections_form = QFormLayout(connections_frame)
        connections_form.setContentsMargins(12, 12, 12, 12)
        connections_form.setVerticalSpacing(10)
        self.connection_values: dict[str, QLabel] = {}
        for key, label in (
            ("configured", "Configured"),
            ("active", "Adaptive active"),
            ("strategy", "Strategy"),
            ("reason", "Adaptive reason"),
            ("resume", "Resume support"),
            ("etag", "ETag"),
            ("last_modified", "Last modified"),
        ):
            value = QLabel("—")
            value.setObjectName("detailValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.connection_values[key] = value
            connections_form.addRow(label, value)
        connections_layout.addWidget(connections_frame)
        connections_layout.addStretch(1)
        self.inspector_tabs.addTab(connections_page, glyph_icon("connections", "#dce8e2", 16), "Connections")

        # Chunks tab
        chunks_page = QWidget()
        chunks_layout = QVBoxLayout(chunks_page)
        chunks_layout.setContentsMargins(0, 8, 0, 0)
        self.chunks_table = QTableWidget(0, 3)
        self.chunks_table.setObjectName("inspectorTable")
        self.chunks_table.setHorizontalHeaderLabels(["Segment", "State", "Progress"])
        self.chunks_table.verticalHeader().hide()
        self.chunks_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.chunks_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.chunks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.chunks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.chunks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        chunks_layout.addWidget(self.chunks_table)
        self.inspector_tabs.addTab(chunks_page, glyph_icon("chunks", "#dce8e2", 16), "Chunks")

        # Headers tab
        headers_page = QWidget()
        headers_layout = QVBoxLayout(headers_page)
        headers_layout.setContentsMargins(0, 8, 0, 0)
        self.headers_text = QTextEdit()
        self.headers_text.setObjectName("inspectorText")
        self.headers_text.setReadOnly(True)
        self.headers_text.setPlaceholderText("No response metadata is available.")
        headers_layout.addWidget(self.headers_text)
        self.inspector_tabs.addTab(headers_page, glyph_icon("document", "#dce8e2", 16), "Headers")

        # More tab
        more_page = QWidget()
        more_layout = QVBoxLayout(more_page)
        more_layout.setContentsMargins(0, 8, 0, 0)
        more_frame = QFrame()
        more_frame.setObjectName("detailsForm")
        more_form = QFormLayout(more_frame)
        more_form.setContentsMargins(12, 12, 12, 12)
        more_form.setVerticalSpacing(9)
        self.more_values: dict[str, QLabel] = {}
        for key, label in (
            ("url", "URL"),
            ("created", "Added"),
            ("updated", "Updated"),
            ("media_kind", "Media kind"),
            ("mime", "MIME type"),
            ("adapter", "Site adapter"),
            ("priority", "Priority"),
            ("session", "Session"),
            ("tags", "Tags"),
        ):
            value = QLabel("—")
            value.setObjectName("detailValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.more_values[key] = value
            more_form.addRow(label, value)
        more_layout.addWidget(more_frame)
        more_layout.addStretch(1)
        self.inspector_tabs.addTab(more_page, glyph_icon("more", "#dce8e2", 16), "More")

        layout.addWidget(self.inspector_tabs, 1)

        self.details_error = QLabel("")
        self.details_error.setObjectName("detailsError")
        self.details_error.setWordWrap(True)
        self.details_error.hide()
        layout.addWidget(self.details_error)

        quick_title = QLabel("Quick actions")
        quick_title.setObjectName("panelSectionTitle")
        layout.addWidget(quick_title)
        quick_actions_title = QLabel("Quick actions")
        quick_actions_title.setObjectName("inspectorSectionTitle")
        layout.addWidget(quick_actions_title)
        quick_grid = QGridLayout()
        quick_grid.setHorizontalSpacing(8)
        quick_grid.setVerticalSpacing(8)
        quick_grid.setSpacing(8)
        self.details_start_button = QPushButton("Start / Resume")
        self.details_start_button.setIcon(glyph_icon("resume", "#07160f", 16))
        self.details_start_button.setObjectName("primaryButton")
        self.details_start_button.setToolTip("Start or resume the selected download")
        self.details_start_button.clicked.connect(self._start_selected)
        self.details_pause_button = QPushButton("Pause")
        self.details_pause_button.setIcon(glyph_icon("pause", "#dce8e2", 16))
        self.details_pause_button.setToolTip("Pause the selected download")
        self.details_pause_button.clicked.connect(self._pause_selected)
        self.details_folder_button = QPushButton("Open folder")
        self.details_folder_button.setIcon(glyph_icon("folder", "#dce8e2", 16))
        self.details_folder_button.setToolTip("Open the destination folder")
        self.details_folder_button.clicked.connect(self._open_selected_folder)
        self.details_delete_button = QPushButton("Delete")
        self.details_delete_button.setIcon(glyph_icon("trash", "#ffd5da", 16))
        self.details_delete_button.setObjectName("dangerButton")
        self.details_delete_button.setToolTip("Remove the selected download")
        self.details_delete_button.clicked.connect(self._delete_selected)
        quick_grid.addWidget(self.details_start_button, 0, 0)
        quick_grid.addWidget(self.details_pause_button, 0, 1)
        quick_grid.addWidget(self.details_folder_button, 1, 0)
        quick_grid.addWidget(self.details_delete_button, 1, 1)
        layout.addLayout(quick_grid)
        return panel

    def _selection_changed(self) -> None:
        self._update_action_states()
        self._update_details_panel()

    def _update_details_panel(self) -> None:
        if not hasattr(self, "details_filename"):
            return
        record = self._selected_record()
        has_record = record is not None
        for button in (
            self.details_start_button,
            self.details_pause_button,
            self.details_folder_button,
            self.details_delete_button,
        ):
            button.setEnabled(has_record)
        if record is None:
            self.details_filename.setText("Select a download")
            self.details_status.setText("No selection")
            self.details_status.setProperty("status", "none")
            for mapping in (self.detail_values, self.connection_values, self.more_values):
                for value in mapping.values():
                    value.setText("—")
            self.chunks_table.setRowCount(0)
            self.headers_text.clear()
            self.details_error.hide()
            self.details_status.style().unpolish(self.details_status)
            self.details_status.style().polish(self.details_status)
            return

        self.details_filename.setText(record.filename)
        self.details_filename.setToolTip(record.filename)
        status_text = "Confirm" if record.capture_pending else STATUS_LABELS[record.status]
        self.details_status.setText(status_text.upper())
        self.details_status.setProperty("status", record.status.value)
        self.details_status.style().unpolish(self.details_status)
        self.details_status.style().polish(self.details_status)

        percent = record.progress * 100 if record.total_bytes else 0.0
        transferred = format_bytes(record.downloaded_bytes)
        if record.total_bytes:
            transferred += f" / {format_bytes(record.total_bytes)}"
        connections = record.adaptive_connections or record.connections
        self.detail_values["progress"].setText(f"{percent:.1f}%")
        self.detail_values["size"].setText(transferred)
        self.detail_values["connections"].setText(str(connections))
        self.detail_values["mode"].setText(record.transfer_mode or "Auto")
        self.detail_values["category"].setText(record.category or "Other")
        self.detail_values["source"].setText(record.source or "manual")
        checksum = record.checksum_status if record.checksum_sha256 else "Not provided"
        self.detail_values["checksum"].setText(checksum)
        self.detail_values["checksum"].setToolTip(record.checksum_sha256 or checksum)
        self.detail_values["folder"].setText(record.folder)
        self.detail_values["folder"].setToolTip(record.folder)

        self.connection_values["configured"].setText(str(record.connections))
        self.connection_values["active"].setText(str(connections))
        self.connection_values["strategy"].setText(record.transfer_mode or "Auto")
        adaptive_reason = record.adaptive_reason or "No adaptive decision recorded"
        self.connection_values["reason"].setText(adaptive_reason)
        self.connection_values["reason"].setToolTip(adaptive_reason)
        resume_supported = "Yes" if (record.etag or record.last_modified or record.downloaded_bytes > 0) else "Unknown"
        self.connection_values["resume"].setText(resume_supported)
        self.connection_values["etag"].setText(record.etag or "Not available")
        self.connection_values["last_modified"].setText(record.last_modified or "Not available")

        # The database stores aggregate segment state, not per-worker internals.
        # Present a truthful high-level view derived from the active connection plan.
        segment_count = max(1, int(connections or 1))
        self.chunks_table.setRowCount(segment_count)
        completed_segments = int(segment_count * record.progress)
        for row in range(segment_count):
            if record.status == DownloadStatus.COMPLETED or row < completed_segments:
                state, chunk_progress = "Complete", "100%"
            elif record.status in {DownloadStatus.DOWNLOADING, DownloadStatus.RETRYING} and row == completed_segments:
                state, chunk_progress = "Active", f"{percent:.1f}%"
            elif record.status in {DownloadStatus.FAILED, DownloadStatus.CANCELED}:
                state, chunk_progress = STATUS_LABELS[record.status], "—"
            else:
                state, chunk_progress = "Waiting", "0%"
            self.chunks_table.setItem(row, 0, QTableWidgetItem(f"Segment {row + 1}"))
            self.chunks_table.setItem(row, 1, QTableWidgetItem(state))
            self.chunks_table.setItem(row, 2, QTableWidgetItem(chunk_progress))

        headers = []
        if record.mime_type:
            headers.append(f"Content-Type: {record.mime_type}")
        if record.etag:
            headers.append(f"ETag: {record.etag}")
        if record.last_modified:
            headers.append(f"Last-Modified: {record.last_modified}")
        if record.referer:
            headers.append(f"Referer: {record.referer}")
        if record.source_url and record.source_url != record.url:
            headers.append(f"Source-URL: {record.source_url}")
        self.headers_text.setPlainText("\n".join(headers))

        self.more_values["url"].setText(record.url or "—")
        self.more_values["url"].setToolTip(record.url or "")
        self.more_values["created"].setText(record.created_at or "—")
        self.more_values["updated"].setText(record.updated_at or "—")
        self.more_values["media_kind"].setText(record.media_kind or "direct")
        self.more_values["mime"].setText(record.mime_type or "Not detected")
        self.more_values["adapter"].setText(record.site_adapter or "direct")
        self.more_values["priority"].setText(record.priority or "Normal")
        self.more_values["session"].setText(record.session_name or "Today")
        self.more_values["tags"].setText(record.tags or "None")

        if record.error:
            self.details_error.setText(record.error)
            self.details_error.show()
        else:
            self.details_error.hide()

    def _create_metric(self, value: str, label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("metricItem")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(2)
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        label_widget = QLabel(label)
        label_widget.setObjectName("metricLabel")
        layout.addWidget(value_label)
        layout.addWidget(label_widget)
        card.value_label = value_label
        return card

    def _open_system_center(self) -> None:
        app_root = Path(__file__).resolve().parents[2]
        plugin_root = self.repository.database_path.parent / "plugins"
        dialog = SystemCenterDialog(
            DiagnosticsService(self.repository.database_path, app_root),
            PluginManager(plugin_root),
            self,
        )
        dialog.exec()


    def _file_type_icon(self, filename: str):
        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix in {"mp4", "mkv", "webm", "avi", "mov", "m4v"}:
            return glyph_icon("file_video", "#65a5ff", 20)
        if suffix in {"mp3", "wav", "flac", "m4a", "opus", "aac", "ogg"}:
            return glyph_icon("file_audio", "#d58cff", 20)
        if suffix in {"zip", "rar", "7z", "tar", "gz", "bz2"}:
            return glyph_icon("file_archive", "#ffb84d", 20)
        if suffix in {"pdf", "doc", "docx", "txt", "md", "rtf"}:
            return glyph_icon("file_document", "#ff7d8d", 20)
        if suffix in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}:
            return glyph_icon("file_image", "#50d890", 20)
        return glyph_icon("file", "#b9c8c1", 20)

    def _run_row_action(self, record_id: str, callback) -> None:
        row = self.row_for_id.get(record_id)
        if row is None:
            return
        self.table.selectRow(row)
        callback()

    def _update_empty_state(self) -> None:
        if not hasattr(self, "empty_state"):
            return
        visible = self.table.rowCount() == 0 and self.workspace_views.currentWidget() is self.table
        self.empty_state.setVisible(visible)
        if visible:
            self.empty_state.setGeometry(self.table.viewport().rect())
            self.empty_state.raise_()

    def _load_downloads(self) -> None:
        for record in self.repository.list_all():
            self._append_record(record)
            if record.source == "browser" and record.capture_pending:
                self._queue_browser_capture(record.id)
        self._refresh_session_filter()

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
        self.table.setItem(row, self.COL_SESSION, QTableWidgetItem(record.session_name))
        self.table.setItem(row, self.COL_PRIORITY, QTableWidgetItem(record.priority))
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

        actions_button = QToolButton()
        actions_button.setObjectName("rowActionsButton")
        actions_button.setIcon(glyph_icon("more", "#dce8e2", 18))
        actions_button.setToolTip("Download actions")
        actions_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        actions_menu = QMenu(actions_button)
        actions_menu.addAction(glyph_icon("resume", "#51e69a", 16), "Start / Resume", lambda checked=False, rid=record.id: self._run_row_action(rid, self._start_selected))
        actions_menu.addAction(glyph_icon("pause", "#dce8e2", 16), "Pause", lambda checked=False, rid=record.id: self._run_row_action(rid, self._pause_selected))
        actions_menu.addAction(glyph_icon("folder", "#dce8e2", 16), "Open folder", lambda checked=False, rid=record.id: self._run_row_action(rid, self._open_selected_folder))
        actions_menu.addSeparator()
        actions_menu.addAction(glyph_icon("stop", "#ff8e9b", 16), "Cancel", lambda checked=False, rid=record.id: self._run_row_action(rid, self._cancel_selected))
        actions_menu.addAction(glyph_icon("trash", "#ff8e9b", 16), "Delete", lambda checked=False, rid=record.id: self._run_row_action(rid, self._delete_selected))
        actions_button.setMenu(actions_menu)
        self.table.setCellWidget(row, self.COL_ACTIONS, actions_button)
        self.row_for_id[record.id] = row
        self._render_record(row, record)
        self._update_empty_state()

    def _render_record(self, row: int, record: DownloadRecord) -> None:
        file_item = self.table.item(row, self.COL_FILE)
        file_item.setText(record.filename)
        file_item.setIcon(self._file_type_icon(record.filename))
        file_item.setToolTip(self._record_tooltip(record))
        size_text = (
            format_bytes(record.total_bytes) if record.total_bytes else "Unknown"
        )
        self.table.item(row, self.COL_SIZE).setText(size_text)
        self.table.item(row, self.COL_SESSION).setText(record.session_name)
        self.table.item(row, self.COL_PRIORITY).setText(record.priority)
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
    def _toggle_media_inspector(self) -> None:
        visible = not self.media_inspector_panel.isVisible()
        self.media_inspector_panel.setVisible(visible)
        if visible:
            self.workspace_splitter.setSizes([max(640, self.width() - 390), 370])
            self._update_details_panel()
        self.media_inspector_button.setChecked(visible)
        self.statusBar().showMessage(
            "Media inspector opened." if visible else "Media inspector closed.", 1800
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

    def _open_batch_preview(self) -> None:
        dialog = BatchPreviewDialog(
            self,
            existing_records=self.repository.list_all(),
        )
        if dialog.exec() != BatchPreviewDialog.DialogCode.Accepted:
            return
        added = 0
        skipped = 0
        for data in dialog.selected_downloads:
            duplicate = find_duplicate(
                self.repository.list_all(),
                DuplicateCandidate(
                    url=str(data["url"]),
                    filename=str(data["filename"]),
                    folder=str(data["folder"]),
                ),
            )
            if duplicate is not None:
                skipped += 1
                continue
            record = self.repository.create_download(
                url=str(data["url"]),
                filename=str(data["filename"]),
                folder=str(data["folder"]),
                connections=int(data["connections"]),
                start_immediately=bool(data["start_immediately"]),
                category=str(data["category"]),
                scheduled_at=str(data["scheduled_at"]),
                checksum_sha256=str(data["checksum_sha256"]),
                source="batch_preview",
            )
            self._append_record(record, at_top=True)
            added += 1
            if record.status == DownloadStatus.QUEUED:
                self._request_start(record.id)
        self._apply_category_filter()
        self._update_summary()
        self.statusBar().showMessage(
            f"Batch added: {added}; skipped duplicates: {skipped}.",
            5000,
        )

    def _optimize_waiting_queue(self) -> None:
        records = self.repository.list_all()
        result = optimize_queue(records)
        self.queue.reorder_pending(result.ordered_ids)
        rank = {record_id: index for index, record_id in enumerate(result.ordered_ids)}
        waiting_rows = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILE)
            if item is None:
                continue
            record_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if record_id in rank:
                waiting_rows.append((rank[record_id], record_id))
        # Rebuilding the table through the normal refresh path preserves filters
        # while making the optimized order visible.
        if result.changed:
            self._reload_records_with_preferred_order(result.ordered_ids)
        QMessageBox.information(
            self,
            "Queue Optimizer",
            ("The waiting queue was optimized.\n\n" if result.changed else "The waiting queue is already optimized.\n\n")
            + result.explanation,
        )

    def _reload_records_with_preferred_order(self, preferred_ids) -> None:
        preferred = {record_id: index for index, record_id in enumerate(preferred_ids)}
        records = self.repository.list_all()
        records.sort(key=lambda record: (preferred.get(record.id, 10**9), record.created_at), reverse=False)
        self.table.setRowCount(0)
        self.row_for_id.clear()
        for record in records:
            self._append_record(record, at_top=False)
        self._apply_category_filter()
        self._update_summary()

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
            existing_records=self.repository.list_all(),
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
        # Worker signals can arrive much faster than the display refresh rate.
        # Store the newest snapshot and let the UI timer render it in batches.
        self._progress_buffer.put(
            record_id,
            (int(downloaded), int(total), max(0.0, float(speed)), eta),
        )

    def _flush_progress_updates(self) -> None:
        updates = self._progress_buffer.drain()
        if not updates:
            return

        cards_visible = (
            hasattr(self, "view_mode_combo")
            and self.view_mode_combo.currentData() == "cards"
        )
        for record_id, (downloaded, total, speed, eta) in updates.items():
            progress_dialog = self.progress_dialogs.get(record_id)
            if progress_dialog is not None:
                progress_dialog.set_progress(downloaded, total, speed, eta)

            row = self.row_for_id.get(record_id)
            if row is not None:
                size_item = self.table.item(row, self.COL_SIZE)
                if size_item is not None:
                    size_item.setText(format_bytes(total) if total else "Unknown")
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
                speed_item = self.table.item(row, self.COL_SPEED)
                eta_item = self.table.item(row, self.COL_ETA)
                if speed_item is not None:
                    speed_item.setText(format_speed(speed))
                if eta_item is not None:
                    eta_item.setText(format_eta(eta))
            self._live_speeds[record_id] = speed

        total_speed = sum(self._live_speeds.values())
        self.speed_metric.value_label.setText(format_speed(total_speed))
        if hasattr(self, "status_speed"):
            self.status_speed.setText(f"Speed: {format_speed(total_speed)}")
        if cards_visible:
            self._refresh_card_view()

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
        self._append_activity(
            f"{record.filename} — {STATUS_LABELS[record.status]}"
            + (f": {message}" if message else "")
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
        self._live_speeds.pop(record_id, None)
        if hasattr(self, "speed_metric"):
            self.speed_metric.value_label.setText(
                format_speed(sum(self._live_speeds.values()))
            )
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
        records = self.repository.list_all()
        self.summary_label.setText(build_summary_text(records))
        active = sum(
            record.status in {
                DownloadStatus.DOWNLOADING,
                DownloadStatus.RETRYING,
                DownloadStatus.VERIFYING,
            }
            for record in records
        )
        queued = sum(
            record.status in {
                DownloadStatus.QUEUED,
                DownloadStatus.SCHEDULED,
                DownloadStatus.PAUSED,
            }
            for record in records
        )
        completed = sum(
            record.status == DownloadStatus.COMPLETED for record in records
        )
        failed = sum(
            record.status == DownloadStatus.FAILED for record in records
        )
        self.total_metric.value_label.setText(str(len(records)))
        self.active_metric.value_label.setText(str(active))
        self.queued_metric.value_label.setText(str(queued))
        self.completed_metric.value_label.setText(str(completed))
        self.failed_metric.value_label.setText(str(failed))
        total_speed = sum(self._live_speeds.values())
        self.speed_metric.value_label.setText(format_speed(total_speed))
        if hasattr(self, "status_total"):
            self.status_total.setText(f"Total: {len(records)}")
            self.status_running.setText(f"Running: {active}")
            self.status_queue.setText(f"Waiting: {queued}")
            if hasattr(self, "status_completed"):
                self.status_completed.setText(f"Completed: {completed}")
            self.status_failed.setText(f"Failed: {failed}")
            self.status_speed.setText(f"Speed: {format_speed(total_speed)}")
        if hasattr(self, "view_mode_combo") and self.view_mode_combo.currentData() == "cards":
            self._refresh_card_view()
        if (
            self.search_input.text().strip()
            or self.category_filter_combo.currentData()
            or self.status_filter_combo.currentData()
        ):
            self._apply_category_filter()

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
        self._workspace_filter_changed()

    def _workspace_filter_changed(self) -> None:
        self._apply_category_filter()
        if hasattr(self, "view_mode_combo") and self.view_mode_combo.currentData() == "cards":
            self._refresh_card_view()
        self._update_action_states()

    @staticmethod
    def _matches_status_filter(status: DownloadStatus, filter_key: str) -> bool:
        if not filter_key:
            return True
        if filter_key == "active":
            return status in {
                DownloadStatus.DOWNLOADING,
                DownloadStatus.RETRYING,
                DownloadStatus.VERIFYING,
            }
        if filter_key == "waiting":
            return status in {
                DownloadStatus.QUEUED,
                DownloadStatus.SCHEDULED,
            }
        if filter_key == "completed":
            return status == DownloadStatus.COMPLETED
        if filter_key == "failed":
            return status in {DownloadStatus.FAILED, DownloadStatus.CANCELED}
        if filter_key == "paused":
            return status == DownloadStatus.PAUSED
        return True

    def _apply_category_filter(self) -> None:
        selected_category = str(
            self.category_filter_combo.currentData() or ""
        )
        selected_status = str(self.status_filter_combo.currentData() or "")
        selected_session = str(self.session_filter_combo.currentData() or "")
        selected_priority = str(self.priority_filter_combo.currentData() or "")
        search_text = self.search_input.text().strip().casefold()
        records = {record.id: record for record in self.repository.list_all()}
        selected_id = self._selected_record_id()
        visible_count = 0
        for row in range(self.table.rowCount()):
            file_item = self.table.item(row, self.COL_FILE)
            category_item = self.table.item(row, self.COL_CATEGORY)
            record_id = str(
                file_item.data(Qt.ItemDataRole.UserRole) if file_item else ""
            )
            record = records.get(record_id)
            category = category_item.text() if category_item else ""
            category_match = not selected_category or category == selected_category
            status_match = bool(
                record and self._matches_status_filter(record.status, selected_status)
            )
            session_match = bool(
                record and (not selected_session or record.session_name == selected_session)
            )
            priority_match = bool(
                record and (not selected_priority or record.priority == selected_priority)
            )
            searchable = " ".join(
                part for part in (
                    record.filename if record else "",
                    record.url if record else "",
                    record.folder if record else "",
                    record.category if record else "",
                    record.session_name if record else "",
                    record.priority if record else "",
                    record.tags if record else "",
                ) if part
            ).casefold()
            search_match = not search_text or search_text in searchable
            hidden = not (
                category_match and status_match and session_match
                and priority_match and search_match
            )
            self.table.setRowHidden(row, hidden)
            if not hidden:
                visible_count += 1

        total_count = self.table.rowCount()
        if (
            search_text or selected_category or selected_status
            or selected_session or selected_priority
        ):
            self.summary_label.setText(
                f"Showing {visible_count} of {total_count} downloads"
            )
        else:
            self._update_summary()

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
