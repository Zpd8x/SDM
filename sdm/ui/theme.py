DARK_STYLESHEET = """
QWidget {
    background-color: #10141d;
    color: #e8edf5;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QLabel, QCheckBox, QDialogButtonBox {
    background-color: transparent;
}
QMainWindow {
    background-color: #0c1017;
}
QFrame#headerCard, QFrame#actionCard, QFrame#controlCard {
    background-color: #171d29;
    border: 1px solid #273044;
    border-radius: 12px;
}
QLabel#appTitle {
    color: #ffffff;
    font-size: 20pt;
    font-weight: 700;
}
QLabel#appSubtitle {
    color: #93a1b7;
    font-size: 9.5pt;
}
QLabel#sectionTitle {
    color: #ffffff;
    font-size: 12pt;
    font-weight: 600;
}
QPushButton {
    background-color: #222b3a;
    border: 1px solid #33405a;
    border-radius: 7px;
    padding: 8px 14px;
    min-height: 18px;
}
QPushButton:hover {
    background-color: #2b374a;
    border-color: #4d6287;
}
QPushButton:pressed {
    background-color: #182131;
}
QPushButton:disabled {
    color: #667085;
    background-color: #181e29;
    border-color: #252d3d;
}
QPushButton#primaryButton {
    color: #ffffff;
    background-color: #377cf6;
    border-color: #4a8aff;
    font-weight: 600;
}
QPushButton#primaryButton:hover {
    background-color: #4387ff;
}
QPushButton#dangerButton {
    color: #ffced3;
    background-color: #3a2028;
    border-color: #63303d;
}
QPushButton#dangerButton:disabled {
    color: #6f6570;
    background-color: #211a21;
    border-color: #342833;
}
QTableWidget {
    background-color: #151b25;
    alternate-background-color: #18202c;
    border: 1px solid #273044;
    border-radius: 10px;
    gridline-color: #273044;
    selection-background-color: #243d68;
    selection-color: #ffffff;
}
QTableWidget::item {
    padding: 7px;
    border-bottom: 1px solid #222b3a;
}
QHeaderView::section {
    color: #9eabc0;
    background-color: #1c2431;
    border: none;
    border-right: 1px solid #2a3446;
    border-bottom: 1px solid #2a3446;
    padding: 9px 7px;
    font-weight: 600;
}
QProgressBar {
    color: #f6f8fc;
    background-color: #202938;
    border: 1px solid #2f3a4e;
    border-radius: 0px;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk {
    background-color: #22c55e;
    border-radius: 0px;
}
QLineEdit, QComboBox, QDateTimeEdit {
    color: #ffffff;
    background-color: #111722;
    border: 1px solid #354159;
    border-radius: 7px;
    padding: 8px;
    selection-background-color: #377cf6;
}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus {
    border-color: #4a8aff;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox QAbstractItemView {
    color: #ffffff;
    background-color: #171f2b;
    border: 1px solid #354159;
    selection-background-color: #377cf6;
}
QDialog {
    background-color: #111722;
}
QTabWidget::pane {
    border: 1px solid #303b50;
    background-color: #151b25;
}
QTabBar::tab {
    color: #aab7ca;
    background-color: #1c2431;
    border: 1px solid #303b50;
    border-bottom: none;
    padding: 7px 12px;
}
QTabBar::tab:selected {
    color: #ffffff;
    background-color: #263249;
}
QGroupBox {
    border: 1px solid #303b50;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #aab7ca;
}
QCheckBox {
    spacing: 7px;
}
QStatusBar {
    color: #94a2b8;
    background-color: #0c1017;
}
QToolTip {
    color: #ffffff;
    background-color: #252f40;
    border: 1px solid #45536c;
}
"""
