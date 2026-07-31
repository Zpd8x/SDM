DARK_STYLESHEET = """
QWidget {
    background-color: #07110c;
    color: #edf8f1;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QLabel, QCheckBox, QDialogButtonBox { background-color: transparent; }
QMainWindow, QWidget#appShell { background-color: #050c08; }
QFrame#heroCard {
    background-color: #0b1a12;
    border: 1px solid #1b4b31;
    border-radius: 14px;
}
QLabel#brandMark {
    color: #052111;
    background-color: #54e895;
    border-radius: 12px;
    font-size: 23pt;
    font-weight: 900;
}
QLabel#appTitle { color: #f4fff7; font-size: 19pt; font-weight: 750; }
QLabel#appSubtitle { color: #8cae99; font-size: 9.5pt; }
QLabel#healthBadge {
    color: #70f0a5;
    background-color: #0d2a19;
    border: 1px solid #1c5a35;
    border-radius: 11px;
    padding: 8px 12px;
    font-size: 8.5pt;
    font-weight: 700;
}
QFrame#metricsCard, QFrame#actionCard, QFrame#controlCard, QFrame#tableCard {
    background-color: #09160f;
    border: 1px solid #173d29;
    border-radius: 12px;
}
QFrame#metricItem { background-color: transparent; border-right: 1px solid #173d29; }
QLabel#metricValue { color: #66f0a0; font-size: 17pt; font-weight: 750; }
QLabel#metricLabel, QLabel#fieldLabel, QLabel#summaryText { color: #83a892; font-size: 9pt; }
QFrame#tableTitleBar { background-color: #0c1c13; border-bottom: 1px solid #173d29; }
QLabel#sectionTitle { color: #f1fff5; font-size: 11.5pt; font-weight: 700; }
QPushButton {
    color: #dff7e8;
    background-color: #10251a;
    border: 1px solid #23583b;
    border-radius: 8px;
    padding: 8px 13px;
    min-height: 19px;
    font-weight: 600;
}
QPushButton:hover { background-color: #173724; border-color: #3b8b5d; }
QPushButton:pressed { background-color: #0c1d14; }
QPushButton:disabled { color: #52665a; background-color: #0b1510; border-color: #18271e; }
QPushButton#primaryButton { color: #04210f; background-color: #58e99a; border-color: #70f0a5; font-weight: 750; }
QPushButton#primaryButton:hover { background-color: #72f2aa; }
QPushButton#dangerButton { color: #ffced3; background-color: #291419; border-color: #5b2a34; }
QPushButton#dangerButton:hover { background-color: #3a1b22; border-color: #814050; }
QTableWidget {
    background-color: #08130d;
    alternate-background-color: #0b1811;
    border: none;
    border-bottom-left-radius: 11px;
    border-bottom-right-radius: 11px;
    gridline-color: #143522;
    selection-background-color: #153e27;
    selection-color: #ffffff;
}
QTableWidget::item { padding: 8px; border-bottom: 1px solid #12301f; }
QHeaderView::section {
    color: #8fb09b;
    background-color: #0d1d14;
    border: none;
    border-right: 1px solid #173d29;
    border-bottom: 1px solid #173d29;
    padding: 10px 7px;
    font-weight: 650;
}
QProgressBar {
    color: #ecfff3;
    background-color: #163022;
    border: 1px solid #214832;
    border-radius: 0px;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk { background-color: #22c55e; border-radius: 0px; }
QLineEdit, QComboBox, QDateTimeEdit {
    color: #f4fff7;
    background-color: #07120c;
    border: 1px solid #25553a;
    border-radius: 8px;
    padding: 8px;
    selection-background-color: #2ebf70;
}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus { border-color: #59e99a; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView {
    color: #f4fff7;
    background-color: #0a1810;
    border: 1px solid #25553a;
    selection-background-color: #1c5534;
}
QDialog { background-color: #07110c; }
QTabWidget::pane { border: 1px solid #214832; background-color: #09160f; }
QTabBar::tab { color: #90ad9b; background-color: #0c1c13; border: 1px solid #214832; border-bottom: none; padding: 8px 13px; }
QTabBar::tab:selected { color: #f4fff7; background-color: #153522; }
QGroupBox { border: 1px solid #214832; border-radius: 9px; margin-top: 12px; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #a4c4b0; }
QStatusBar { color: #82a68f; background-color: #050c08; border-top: 1px solid #12301f; }
QToolTip { color: #f4fff7; background-color: #10251a; border: 1px solid #34724d; }
QScrollBar:vertical { background: #07110c; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #24573a; min-height: 28px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #347a50; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

# Phase 2 workspace refinements are intentionally appended so every dialog keeps
# the same base palette while the main window gains a more compact search field.

# Phase 3 — selection details workspace.
DARK_STYLESHEET += """
QSplitter#workspaceSplitter::handle {
    background-color: #102b1c;
    width: 5px;
    margin: 8px 2px;
    border-radius: 2px;
}
QFrame#detailsPanel {
    background-color: #09160f;
    border: 1px solid #173d29;
    border-radius: 12px;
}
QLabel#panelEyebrow {
    color: #57e797;
    font-size: 8pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#panelTitle {
    color: #f4fff7;
    font-size: 14pt;
    font-weight: 750;
}
QLabel#detailsFilename {
    color: #dff7e8;
    font-size: 10.5pt;
    font-weight: 650;
}
QLabel#detailsStatus {
    color: #aab4c5;
    background-color: #13251a;
    border: 1px solid #294635;
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 8.5pt;
    font-weight: 800;
}
QLabel#detailsStatus[status="downloading"], QLabel#detailsStatus[status="completed"] {
    color: #75f3aa;
    background-color: #0d2a19;
    border-color: #256a40;
}
QLabel#detailsStatus[status="queued"], QLabel#detailsStatus[status="scheduled"] {
    color: #f7d685;
    background-color: #2b2411;
    border-color: #6b5721;
}
QLabel#detailsStatus[status="paused"], QLabel#detailsStatus[status="retrying"] {
    color: #ffc57c;
    background-color: #2d1c10;
    border-color: #72401d;
}
QLabel#detailsStatus[status="failed"], QLabel#detailsStatus[status="canceled"] {
    color: #ff9ba4;
    background-color: #2c151a;
    border-color: #74313c;
}
QLabel#detailsStatus[status="verifying"] {
    color: #78e7ee;
    background-color: #10292c;
    border-color: #28666c;
}
QFrame#detailsForm {
    background-color: #07120c;
    border: 1px solid #173d29;
    border-radius: 9px;
}
QFrame#detailsForm QLabel {
    color: #7fa08c;
    background-color: transparent;
    font-size: 8.8pt;
}
QLabel#detailValue {
    color: #edf8f1;
    font-weight: 600;
}
QLabel#detailsError {
    color: #ffadb5;
    background-color: #281419;
    border: 1px solid #63303a;
    border-radius: 8px;
    padding: 9px;
}
QLabel#panelSectionTitle {
    color: #cfe9d8;
    font-size: 9pt;
    font-weight: 700;
}
"""

# Phase 4 — live workspace metrics and activity timeline.
DARK_STYLESHEET += """
QFrame#activityPanel {
    background-color: #09160f;
    border: 1px solid #173d29;
    border-radius: 12px;
}
QListWidget#activityList {
    color: #cfe9d8;
    background-color: #07120c;
    alternate-background-color: #0a1810;
    border: 1px solid #173d29;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QListWidget#activityList::item {
    padding: 7px 9px;
    border-bottom: 1px solid #102b1c;
}
QListWidget#activityList::item:selected {
    color: #f4fff7;
    background-color: #153e27;
}
QPushButton#compactButton {
    min-height: 14px;
    padding: 5px 10px;
    font-size: 8.5pt;
}
"""

# Phase 5 — compact workspace, context menu actions and calm row selection.
DARK_STYLESHEET += """
QTableWidget {
    outline: 0;
    selection-background-color: #12351f;
    selection-color: #f4fff7;
}
QTableWidget::item:selected {
    color: #f4fff7;
    background-color: #12351f;
    border-top: 1px solid #26613e;
    border-bottom: 1px solid #26613e;
}
QTableWidget::item:selected:active,
QTableWidget::item:selected:!active {
    color: #f4fff7;
    background-color: #12351f;
}
QMenu {
    color: #edf8f1;
    background-color: #0b1811;
    border: 1px solid #24573a;
    padding: 6px;
}
QMenu::item {
    padding: 8px 30px 8px 12px;
    border-radius: 5px;
}
QMenu::item:selected { background-color: #1a4a2d; }
QMenu::item:disabled { color: #586d60; }
QMenu::separator {
    height: 1px;
    background-color: #214832;
    margin: 5px 8px;
}
QFrame#activityPanel { max-height: 155px; }
QLabel#appTitle { font-size: 17pt; }
QLabel#appSubtitle { font-size: 9pt; }
QLabel#brandMark { font-size: 20pt; border-radius: 10px; }
"""

# Phase B — sessions sidebar and denser workspace navigation.
DARK_STYLESHEET += """
QFrame#sessionsSidebar {
    background-color: #09160f;
    border: 1px solid #173d29;
    border-radius: 12px;
}
QListWidget#sessionsList {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget#sessionsList::item {
    color: #a9c8b5;
    border-radius: 8px;
    padding: 9px 10px;
    margin: 2px 0;
}
QListWidget#sessionsList::item:hover { background-color: #10271a; color: #e8fff0; }
QListWidget#sessionsList::item:selected {
    background-color: #17462b;
    color: #7cf2ac;
    border: 1px solid #2b7147;
}
"""

# Phase C — card workspace, column manager and pro status bar.
DARK_STYLESHEET += """
QListWidget#downloadCardList {
    background-color: #07110c;
    border: none;
    padding: 10px;
    outline: none;
}
QListWidget#downloadCardList::item { border: none; }
QListWidget#downloadCardList::item:selected { background: transparent; }
QFrame#downloadCard {
    background-color: #0c1d14;
    border: 1px solid #1d4b31;
    border-radius: 12px;
}
QFrame#downloadCard:hover { border-color: #43a868; background-color: #10271a; }
QLabel#downloadCardTitle { color: #f2fff6; font-size: 10.5pt; font-weight: 700; }
QLabel#downloadCardMeta { color: #8fb7a0; font-size: 8.5pt; }
QComboBox#viewModeCombo { min-width: 105px; }
QLabel#statusMetric { color: #8fb7a0; padding: 0 7px; }
"""


# v2.7.1 — responsive workspace and card-based System Center.
DARK_STYLESHEET += """
QFrame#toolsHintCard {
    background-color: #0d2117;
    border: 1px solid #24573a;
    border-radius: 10px;
}
QScrollArea#toolsScroll, QScrollArea#toolsScroll > QWidget > QWidget {
    background-color: transparent;
    border: none;
}
QFrame#toolCard {
    background-color: #0b1a12;
    border: 1px solid #1e4c33;
    border-radius: 12px;
}
QFrame#toolCard:hover { border-color: #34845a; background-color: #0e2117; }
QLabel#toolName { color: #f4fff7; font-size: 12pt; font-weight: 750; }
QLabel#toolDetails {
    color: #94b7a1;
    background-color: #07120c;
    border: 1px solid #183c29;
    border-radius: 8px;
    padding: 9px;
}
QLabel#toolStatus {
    color: #b7c7bd;
    background-color: #17251d;
    border: 1px solid #33493b;
    border-radius: 8px;
    padding: 5px 9px;
    font-size: 8.5pt;
    font-weight: 800;
}
QLabel#toolStatus[state="ok"], QLabel#toolStatus[state="warning"] {
    color: #72f2aa;
    background-color: #0d2a19;
    border-color: #276b42;
}
QLabel#toolStatus[state="missing"], QLabel#toolStatus[state="error"] {
    color: #ff9aa5;
    background-color: #2b151a;
    border-color: #71313c;
}
QFrame#controlCard QLineEdit, QFrame#controlCard QComboBox {
    min-height: 20px;
}
QFrame#controlCard QLabel#fieldLabel { padding-left: 2px; }
"""


# v2.8.0 — Modern UI Rebuild: compact, content-first main workspace.
DARK_STYLESHEET += """
QFrame#compactHeader {
    background-color: #08140e;
    border: 1px solid #173d29;
    border-radius: 10px;
}
QLabel#compactBrandMark {
    color: #052111;
    background-color: #54e895;
    border-radius: 9px;
    font-size: 18pt;
    font-weight: 900;
}
QLabel#compactAppTitle { color: #f4fff7; font-size: 13pt; font-weight: 750; }
QLabel#compactAppSubtitle { color: #7fa08c; font-size: 8.5pt; }
QPushButton#headerToolButton {
    background: transparent;
    border: none;
    color: #b6d1c0;
    padding: 7px 9px;
}
QPushButton#headerToolButton:hover { color: #72f2aa; background-color: #10251a; }
QFrame#compactToolbar {
    background-color: #09160f;
    border: 1px solid #173d29;
    border-radius: 10px;
}
QFrame#compactToolbar QPushButton { padding: 7px 11px; }
QLineEdit#toolbarSearch {
    min-height: 20px;
    padding: 7px 11px;
    border-radius: 8px;
}
QPushButton#filterToggleButton:checked {
    color: #052111;
    background-color: #54e895;
    border-color: #70f0a5;
}
QFrame#filterPanel {
    background-color: #09160f;
    border: 1px solid #173d29;
    border-radius: 10px;
}
QFrame#compactTableTitleBar {
    background-color: #0b1a12;
    border-bottom: 1px solid #173d29;
}
QFrame#tableCard { border-radius: 10px; }
QStatusBar QLabel#statusMetric {
    color: #9bb9a7;
    padding: 0 8px;
    border-left: 1px solid #173d29;
}

/* v2.8.1 integrated window and inspector */
QFrame#integratedTitleBar {
    background: #07110d;
    border: 1px solid #123d29;
    border-radius: 8px;
}
QLabel#titleBrandMark {
    background: #52e99a;
    color: #04120b;
    border-radius: 7px;
    font-size: 17px;
    font-weight: 800;
}
QLabel#titleBrandText { color: #f1fff7; font-size: 16px; font-weight: 800; }
QLabel#titleBrandSubtitle { color: #89b9a0; font-size: 12px; }
QPushButton#windowControlButton, QPushButton#windowCloseButton {
    background: transparent;
    border: none;
    border-radius: 5px;
    color: #d8eee1;
    font-size: 16px;
}
QPushButton#windowControlButton:hover { background: #123525; }
QPushButton#windowCloseButton:hover { background: #b93845; color: white; }
QPushButton#panelCloseButton {
    background: transparent;
    border: none;
    color: #a9c9b5;
    font-size: 20px;
}
QPushButton#panelCloseButton:hover { background: #173c2a; color: white; }
QSplitter#workspaceSplitter::handle { background: #123d29; width: 1px; }
QFrame#detailsPanel { background: #071b12; border: 1px solid #174f34; border-radius: 10px; }

"""

# v2.8.2 — faithful single-header desktop layout and icon-led controls.
DARK_STYLESHEET += """
QWidget { font-size: 9.5pt; }
QWidget#appShell { background-color: #050b0f; }
QFrame#integratedTitleBar {
    background-color: #061014;
    border: 1px solid #16362a;
    border-radius: 0px;
}
QLabel#titleBrandMark {
    color: #041c0e;
    background-color: #55e59a;
    border-radius: 8px;
    font-size: 18pt;
    font-weight: 900;
}
QLabel#titleBrandText { color: #f5fff8; font-size: 15pt; font-weight: 800; }
QLabel#titleBrandSubtitle { color: #9bb0a5; font-size: 9pt; }
QPushButton#titleToolButton {
    color: #e8f4ed;
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 7px 10px;
    min-height: 22px;
    font-weight: 550;
}
QPushButton#titleToolButton:hover { background-color: #10231b; color: #72efaa; }
QPushButton#titleToolButton:checked { background-color: #123322; color: #6df0a6; }
QPushButton#windowControlButton, QPushButton#windowCloseButton {
    color: #d8e6de;
    background: transparent;
    border: none;
    border-radius: 5px;
    padding: 0;
    min-height: 0;
}
QPushButton#windowControlButton:hover { background-color: #18231f; }
QPushButton#windowCloseButton:hover { background-color: #a52a35; color: white; }
QFrame#compactToolbar {
    background-color: #071216;
    border: none;
    border-bottom: 1px solid #16362a;
    border-radius: 0px;
}
QFrame#tableCard, QFrame#detailsPanel, QFrame#activityPanel {
    background-color: #071217;
    border: 1px solid #18382d;
    border-radius: 8px;
}
QFrame#compactTableTitleBar { background-color: #09171b; border-bottom: 1px solid #18382d; }
QPushButton {
    border-radius: 6px;
    padding: 7px 12px;
    min-height: 22px;
}
QPushButton#primaryButton { background-color: #55e59a; color: #031b0d; }
QLineEdit#toolbarSearch {
    background-color: #071216;
    border: 1px solid #203f35;
    border-radius: 7px;
    padding: 8px 12px;
}
QTableWidget {
    background-color: #071217;
    alternate-background-color: #09171b;
    selection-background-color: #102e24;
}
QTableWidget::item { padding: 9px 8px; border-bottom: 1px solid #142f27; }
QHeaderView::section {
    background-color: #09171b;
    color: #b2c7bc;
    padding: 10px 7px;
    border-right: 1px solid #16362a;
    border-bottom: 1px solid #16362a;
}
QProgressBar { background-color: #18272a; border: 1px solid #29443d; border-radius: 0px; }
QProgressBar::chunk { background-color: #31d47f; border-radius: 0px; }
QFrame#detailsPanel { background-color: #07161a; }
QLabel#panelTitle { font-size: 13pt; }
QFrame#detailsForm { background-color: #061115; border-color: #18382d; }
QFrame#activityPanel { max-height: 185px; }
QListWidget#activityList { background-color: #061115; border: none; border-top: 1px solid #17372d; border-radius: 0px; }
QPushButton#drawerToggleButton {
    background: transparent; border: none; color: #a7bdb1; padding: 3px 8px; min-height: 16px;
}
QStatusBar { background-color: #050b0f; border-top: 1px solid #17372d; }


/* SDM 2.8.4 Activity Center */
QPushButton#activityTab, QPushButton#activityTabActive {
    border: none;
    border-radius: 0px;
    padding: 7px 12px;
    background: transparent;
    color: #a8beb5;
    font-weight: 600;
}
QPushButton#activityTab:hover { color: #e5f4ed; }
QPushButton#activityTabActive {
    color: #eafff5;
    border-bottom: 2px solid #51e69a;
}
QPushButton#activityHeaderButton {
    min-width: 28px;
    padding: 5px 8px;
    border: none;
    background: transparent;
}
QLabel#activityBadge {
    min-width: 20px;
    padding: 2px 6px;
    border-radius: 9px;
    background: #2ddf8c;
    color: #06130d;
    font-weight: 800;
}
QTableWidget#activityTable {
    border: 1px solid #163e2d;
    border-radius: 6px;
    background: #071510;
    alternate-background-color: #091a14;
}
QTableWidget#activityTable::item { padding: 5px 7px; }
QTableWidget#activityTable QHeaderView::section {
    padding: 6px 8px;
    background: #091a14;
    border: none;
    border-bottom: 1px solid #163e2d;
    color: #8fb4a4;
}

/* SDM 2.8.6 — Media Inspector Advanced Tabs */
QTabWidget#inspectorTabs::pane {
    border: 1px solid #173f2c;
    border-radius: 8px;
    background-color: #061510;
    top: -1px;
}
QTabWidget#inspectorTabs QTabBar::tab {
    background: transparent;
    color: #a8bdb2;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 9px 8px;
    min-width: 54px;
}
QTabWidget#inspectorTabs QTabBar::tab:selected {
    color: #51e69a;
    border-bottom-color: #51e69a;
}
QTabWidget#inspectorTabs QTabBar::tab:hover { color: #eef8f2; }
QTableWidget#inspectorTable {
    background-color: #061115;
    border: 1px solid #18382d;
    border-radius: 7px;
    gridline-color: #173629;
}
QTableWidget#inspectorTable::item { padding: 6px; }
QTextEdit#inspectorText {
    background-color: #061115;
    border: 1px solid #18382d;
    border-radius: 7px;
    color: #bcd0c6;
    font-family: Consolas, "Cascadia Mono", monospace;
    padding: 10px;
}

"""

# SDM 2.9.1 — Design System Foundation.
# This final layer normalizes component geometry, interaction states and focus.
DARK_STYLESHEET += """
QWidget {
    font-family: "Segoe UI Variable", "Segoe UI";
    font-size: 9.5pt;
}
QPushButton {
    min-height: 20px;
    padding: 7px 12px;
    border: 1px solid #285543;
    border-radius: 6px;
    background-color: #0d2119;
    color: #e9f8ef;
    font-weight: 600;
}
QPushButton:hover { background-color: #153427; border-color: #3b8060; }
QPushButton:pressed { background-color: #091812; padding-top: 8px; padding-bottom: 6px; }
QPushButton:focus { border: 1px solid #55e59a; }
QPushButton#primaryButton {
    background-color: #55e59a;
    border-color: #55e59a;
    color: #04190d;
    font-weight: 750;
}
QPushButton#primaryButton:hover { background-color: #72efaa; border-color: #72efaa; }
QPushButton#dangerButton { background-color: #27161b; border-color: #60303a; color: #ffbdc4; }
QPushButton#dangerButton:hover { background-color: #3a1c24; border-color: #8a4351; }
QPushButton#titleToolButton, QPushButton#windowControlButton,
QPushButton#windowCloseButton, QPushButton#activityHeaderButton,
QPushButton#drawerToggleButton {
    padding-top: 0px;
    padding-bottom: 0px;
}
QLineEdit, QComboBox, QDateTimeEdit {
    min-height: 20px;
    padding: 7px 10px;
    border-radius: 6px;
    border: 1px solid #285543;
    background-color: #061115;
}
QLineEdit:hover, QComboBox:hover, QDateTimeEdit:hover { border-color: #376c55; }
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus { border: 1px solid #55e59a; }
QTableWidget::item { padding: 8px; }
QTableWidget::item:hover { background-color: #0e261d; }
QHeaderView::section { font-size: 9pt; font-weight: 650; }
QProgressBar {
    min-height: 8px;
    max-height: 8px;
    border: none;
    border-radius: 0px;
    background-color: #172923;
    color: transparent;
}
QProgressBar::chunk { background-color: #31d47f; border-radius: 0px; }
QFrame#tableCard, QFrame#detailsPanel, QFrame#activityPanel {
    border-radius: 8px;
    border-color: #18382d;
}
QToolTip {
    padding: 6px 8px;
    border-radius: 4px;
    background-color: #10251d;
    border: 1px solid #376c55;
}
"""

DARK_STYLESHEET += """
/* SDM 2.9.3 — Smart Download Engine Phase 1 */
QLabel#dialogTitle {
    font-size: 22px;
    font-weight: 700;
    color: #f4f8f6;
}
QLabel#dialogSubtitle, QLabel#mutedText {
    color: #8fa39a;
}
QLabel#analysisStageBadge {
    min-width: 126px;
    padding: 6px 10px;
    border: 1px solid #2e6f50;
    background: #112a20;
    color: #67d391;
    font-size: 10px;
    font-weight: 700;
}
QFrame#mediaPreviewCard {
    background: #101814;
    border: 1px solid #25352e;
}
QLabel#analysisHeadline {
    color: #e7f0eb;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#primaryButton {
    min-width: 112px;
    background: #29a35a;
    border: 1px solid #35b96a;
    color: #07140c;
    font-weight: 700;
}
QPushButton#primaryButton:hover { background: #35b96a; }
QPushButton#primaryButton:pressed { background: #238e4e; }
QPushButton#secondaryButton {
    background: #17211c;
    border: 1px solid #314139;
}
QPushButton#secondaryButton:hover { background: #202d26; }

"""


DARK_STYLESHEET += """
/* v3.0 RC3 — documentation-site brand identity and arrowless menus. */
QLabel#titleBrandMark {
    min-width: 52px;
    max-width: 52px;
    font-size: 12pt;
    letter-spacing: 0.5px;
}
QToolButton#menuOnlyButton::menu-indicator,
QToolButton#rowActionsButton::menu-indicator {
    image: none;
    width: 0px;
    height: 0px;
    subcontrol-origin: padding;
    subcontrol-position: right center;
}
QToolButton#rowActionsButton { padding-right: 0px; }
"""


DARK_STYLESHEET += """
/* SDM 3.1.1 — primary workspace UX polish. */
QFrame#compactToolbar {
    min-height: 52px;
    background-color: #071712;
    border: 1px solid #17392c;
    border-radius: 8px;
}
QFrame#compactToolbar QPushButton,
QFrame#compactToolbar QToolButton,
QFrame#compactToolbar QLineEdit {
    min-height: 40px;
    max-height: 40px;
}
QFrame#compactToolbar QPushButton { padding-left: 13px; padding-right: 13px; }
QFrame#compactToolbar QPushButton:disabled {
    color: #61756c;
    background-color: #0a1712;
    border-color: #193128;
}
QLineEdit#toolbarSearch {
    padding-left: 12px;
    padding-right: 12px;
    background-color: #050f0c;
    border-color: #234b3a;
}
QLineEdit#toolbarSearch:focus { background-color: #071712; border-color: #55e59a; }
QPushButton#filterToggleButton:checked {
    background-color: #173b2c;
    border-color: #55e59a;
    color: #dffff0;
}
QToolButton#menuOnlyButton {
    min-width: 38px;
    padding: 0px 10px;
    border: 1px solid #285543;
    border-radius: 6px;
    background-color: #0d2119;
    color: #e9f8ef;
    font-weight: 650;
}
QToolButton#menuOnlyButton:hover { background-color: #153427; border-color: #3b8060; }
QToolButton#menuOnlyButton:pressed { background-color: #091812; }
QFrame#compactTableTitleBar {
    min-height: 42px;
    background-color: #091913;
    border-bottom: 1px solid #18382d;
}
QTableWidget {
    outline: 0;
    selection-background-color: #163d2c;
    selection-color: #f2fff7;
}
QTableWidget::item {
    padding: 7px 9px;
    border-bottom: 1px solid #10291f;
}
QTableWidget::item:hover { background-color: #0f2b20; }
QTableWidget::item:selected {
    background-color: #163d2c;
    color: #f2fff7;
    border-bottom: 1px solid #2b6b4d;
}
QHeaderView::section {
    min-height: 36px;
    padding: 0px 9px;
    background-color: #0b1d16;
    color: #a9c1b5;
    border: none;
    border-right: 1px solid #17372b;
    border-bottom: 1px solid #214737;
}
QHeaderView::section:hover { background-color: #10291f; color: #e9f8ef; }
QProgressBar {
    min-height: 7px;
    max-height: 7px;
    border: none;
    border-radius: 0px;
    background-color: #173027;
}
QProgressBar::chunk { background-color: #31d47f; border-radius: 0px; }
QStatusBar { min-height: 28px; }
QLabel#statusMetric { padding: 0px 8px; color: #9eb5aa; }
"""


DARK_STYLESHEET += """
/* SDM 3.1.2 — Media Inspector, Activity Center and Status Bar polish. */
QFrame#activityPanel {
    background-color: #071510;
    border: 1px solid #183d2e;
    border-radius: 8px;
}
QLineEdit#activitySearch {
    min-height: 28px;
    max-height: 28px;
    padding: 3px 9px;
    background-color: #050f0c;
    border: 1px solid #234b3a;
    border-radius: 5px;
}
QLineEdit#activitySearch:focus { border-color: #51e69a; background-color: #081813; }
QTableWidget#activityTable::item { padding: 5px 8px; border-bottom: 1px solid #10291f; }
QTableWidget#activityTable::item:selected { background-color: #163d2c; color: #f2fff7; }
QLabel#activityBadge { min-width: 24px; border-radius: 10px; }
QFrame#detailsPanel { background-color: #071510; }
QLabel#detailsFilename {
    color: #f2fff7;
    font-size: 12pt;
    font-weight: 700;
    padding: 2px 0px;
}
QLabel#detailsStatus {
    min-height: 24px;
    padding: 3px 9px;
    border: 1px solid #285543;
    border-radius: 4px;
    background-color: #0b2018;
    color: #b9cec4;
    font-weight: 750;
}
QLabel#detailsStatus[status="downloading"], QLabel#detailsStatus[status="retrying"] { color: #83b9ff; border-color: #315f8f; background-color: #0d2135; }
QLabel#detailsStatus[status="completed"] { color: #71e3aa; border-color: #327354; background-color: #0c281b; }
QLabel#detailsStatus[status="failed"] { color: #ff9099; border-color: #7a3942; background-color: #2c1419; }
QLabel#detailsStatus[status="paused"] { color: #ffd27a; border-color: #765d2c; background-color: #2b2312; }
QLabel#inspectorSectionTitle { color: #a9c1b5; font-size: 9pt; font-weight: 700; text-transform: uppercase; }
QFrame#detailsForm { background-color: #081a14; border: 1px solid #173d2e; border-radius: 7px; }
QLabel#detailValue { color: #e3f1e9; }
QTabWidget#inspectorTabs QTabBar::tab { min-height: 30px; padding: 7px 8px; }
QTableWidget#inspectorTable::item { border-bottom: 1px solid #10291f; }
QStatusBar {
    min-height: 30px;
    background-color: #050d0a;
    border-top: 1px solid #183d2e;
}
QLabel#statusMetric {
    min-height: 22px;
    padding: 0px 9px;
    border-left: 1px solid #17372b;
    color: #9eb5aa;
}
QLabel#statusMetric[metric="running"] { color: #83b9ff; }
QLabel#statusMetric[metric="completed"] { color: #71e3aa; }
QLabel#statusMetric[metric="failed"] { color: #ff9099; }
QLabel#statusMetric[metric="speed"] { color: #51e69a; font-weight: 700; }
"""
