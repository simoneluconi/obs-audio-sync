"""Base dark theme. Extended in Phase 4 alongside the visual feedback panel."""

DARK_STYLESHEET = """
QWidget {
    background-color: #1e2126;
    color: #e6e6e6;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #1e2126;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #2a2e35;
    border: 1px solid #3a3f47;
    border-radius: 4px;
    padding: 4px 6px;
    color: #e6e6e6;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #5b8cff;
}
QPushButton {
    background-color: #2f3540;
    border: 1px solid #3a3f47;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #3a4150;
}
QPushButton:pressed {
    background-color: #262a31;
}
QPushButton:disabled {
    color: #6b6f76;
}
QTableWidget {
    background-color: #23262c;
    gridline-color: #3a3f47;
    border: 1px solid #3a3f47;
}
QHeaderView::section {
    background-color: #2a2e35;
    color: #b5bac1;
    padding: 4px;
    border: none;
    border-bottom: 1px solid #3a3f47;
}
QRadioButton, QCheckBox {
    spacing: 6px;
}
QLabel {
    color: #e6e6e6;
}
QScrollArea {
    border: none;
}
"""
