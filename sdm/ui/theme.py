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
