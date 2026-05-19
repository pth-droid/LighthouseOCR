import os
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QTextEdit,
    QPushButton,
    QMessageBox,
)

from path_utils import get_root_dir


class HardCaseBrowserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_dir = os.path.join(get_root_dir(), "HARD CASE COLLECTED")
        self.setWindowTitle("Hard Cases")
        self.resize(960, 620)
        self.setStyleSheet(self._stylesheet())

        self._build_ui()
        self._load_cases()

    def _stylesheet(self) -> str:
        return """
            QDialog {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #001D39, stop:1 #000E1F
                );
            }
            QLabel {
                color: #BDD8E9;
                font-size: 14px;
                font-weight: 600;
            }
            QListWidget, QTextEdit {
                background-color: rgba(10, 39, 64, 0.82);
                color: #BDD8E9;
                border: 1px solid rgba(123,189,232,0.22);
                border-radius: 10px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 13px;
                padding: 8px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background-color: #0A4174;
                color: #ffffff;
            }
            QPushButton {
                background-color: #0A4174;
                color: #BDD8E9;
                border: 1px solid rgba(123,189,232,0.35);
                border-radius: 10px;
                padding: 9px 14px;
                font-size: 14px;
                font-weight: 600;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #0F548E;
            }
            QPushButton:pressed {
                background-color: #08345C;
            }
        """

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Danh sách Hard Cases")
        layout.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(10)

        self.case_list = QListWidget()
        self.case_list.setMinimumWidth(330)
        self.case_list.currentRowChanged.connect(self._show_selected_report)
        body.addWidget(self.case_list, 1)

        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText("Chọn một hard case để xem report.json")
        body.addWidget(self.report_view, 2)

        layout.addLayout(body, 1)

        footer = QHBoxLayout()
        footer.addStretch()

        self.btn_refresh = QPushButton("Làm mới")
        self.btn_refresh.clicked.connect(self._load_cases)
        footer.addWidget(self.btn_refresh)

        self.btn_open_folder = QPushButton("Mở thư mục")
        self.btn_open_folder.clicked.connect(self._open_selected_folder)
        footer.addWidget(self.btn_open_folder)

        self.btn_close = QPushButton("Đóng")
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)

        layout.addLayout(footer)

    def _load_cases(self):
        self.case_list.clear()
        self.report_view.clear()

        if not os.path.isdir(self._root_dir):
            self.report_view.setPlainText(
                f"Chưa có thư mục hard case.\n\nĐường dẫn: {self._root_dir}"
            )
            return

        folders = []
        for name in os.listdir(self._root_dir):
            path = os.path.join(self._root_dir, name)
            if os.path.isdir(path):
                mtime = os.path.getmtime(path)
                folders.append((name, path, mtime))

        folders.sort(key=lambda x: x[2], reverse=True)
        self._folders = folders

        for name, _, mtime in folders:
            dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            self.case_list.addItem(f"{name}   ({dt})")

        if folders:
            self.case_list.setCurrentRow(0)
        else:
            self.report_view.setPlainText(
                f"Không tìm thấy hard case nào trong:\n{self._root_dir}"
            )

    def _show_selected_report(self, row: int):
        if row < 0 or row >= len(getattr(self, "_folders", [])):
            self.report_view.clear()
            return

        _, folder_path, _ = self._folders[row]
        report_path = os.path.join(folder_path, "report.json")
        if not os.path.isfile(report_path):
            self.report_view.setPlainText(f"Không tìm thấy report.json:\n{report_path}")
            return

        try:
            with open(report_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            self.report_view.setPlainText(json.dumps(content, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.report_view.setPlainText(f"Không thể đọc report.json:\n{exc}")

    def _open_selected_folder(self):
        row = self.case_list.currentRow()
        if row < 0 or row >= len(getattr(self, "_folders", [])):
            return
        _, folder_path, _ = self._folders[row]
        try:
            os.startfile(folder_path)
        except (OSError, AttributeError) as exc:
            QMessageBox.critical(self, "Loi", f"Khong the mo thu muc:\n{exc}")
