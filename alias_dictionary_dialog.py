import os
import csv
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QHeaderView, QAbstractItemView, QMessageBox,
    QComboBox, QStyledItemDelegate
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

# ── Delegate cho Dropdown (Tái sử dụng logic từ post_process) ──
class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.options = options

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.setInsertPolicy(QComboBox.NoInsert)
        
        actual_opts = self.options(index) if callable(self.options) else self.options
        editor.addItems(actual_opts)
        
        # Bật auto-completion cho combobox
        from PyQt5.QtWidgets import QCompleter
        completer = QCompleter(actual_opts, editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        editor.setCompleter(completer)
        
        # [Excel-style] Tự động chọn toàn bộ text để gõ mới là ghi đè
        editor.lineEdit().selectAll()
        
        return editor

    def setEditorData(self, editor, index):
        val = index.data(Qt.EditRole) or index.data(Qt.DisplayRole)
        editor.setCurrentText(str(val))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

class AliasDictionaryDialog(QDialog):
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.alias_file = os.path.join("Data structure", "Tu_dien_alias.csv")
        
        self.setWindowTitle("Quản lý Từ điển Alias (Tiếng lóng)")
        self.resize(1100, 700)
        self.setStyleSheet(self._stylesheet())
        
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- Header & Filter ---
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>TỪ ĐIỂN TIẾNG LÓNG & QUY ĐỔI ĐƠN VỊ</b>"))
        header.addStretch()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Tìm kiếm theo Mã hàng hoặc Alias...")
        self.search_input.setFixedWidth(300)
        self.search_input.textChanged.connect(self._filter_table)
        header.addWidget(self.search_input)
        layout.addLayout(header)

        # --- Table ---
        self.table = QTableWidget()
        headers = ["🔑 Mã Vật Tư", "Alias (Tên trên bill)", "Tên Chuẩn", "ĐVT Kho", "ĐVT Lóng", "Hệ Số"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.AnyKeyPressed | QAbstractItemView.EditKeyPressed)
        self.table.setAlternatingRowColors(True)
        
        # --- Nạp danh mục cho Dropdowns ---
        name_list = sorted([str(v.get("name", "")) for v in self.data_manager.items_dict.values()]) if self.data_manager else []
        unit_list = sorted(list(set(filter(None, [v.get("unit") for v in self.data_manager.items_dict.values()])))) if self.data_manager else []
        
        self.table.setItemDelegateForColumn(2, ComboBoxDelegate(name_list, self.table))
        self.table.setItemDelegateForColumn(3, ComboBoxDelegate(unit_list, self.table))
        
        # layout.addWidget(self.table) # Dòng này đã có ở trên
        layout.addWidget(self.table)

        # --- Footer Actions ---
        footer = QHBoxLayout()
        btn_add = QPushButton("+ Thêm Dòng")
        btn_add.clicked.connect(self._add_row)
        footer.addWidget(btn_add)

        btn_delete = QPushButton("🗑 Xóa Dòng")
        btn_delete.clicked.connect(self._delete_row)
        btn_delete.setStyleSheet("background-color: rgba(180, 50, 50, 0.4); color: #fca5a5;")
        footer.addWidget(btn_delete)

        footer.addStretch()

        btn_cancel = QPushButton("Hủy bỏ")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        btn_save = QPushButton("💾 LƯU THAY ĐỔI")
        btn_save.setFixedWidth(180)
        btn_save.setStyleSheet("""
            QPushButton { background-color: #0A4174; color: white; font-weight: bold; }
            QPushButton:hover { background-color: #49769F; }
        """)
        btn_save.clicked.connect(self._save_to_csv)
        footer.addWidget(btn_save)

        layout.addLayout(footer)

    def _load_data(self):
        if not os.path.exists(self.alias_file):
            return
        self.table.setRowCount(0)
        try:
            with open(self.alias_file, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None) # Skip header
                for row_data in reader:
                    if not any(row_data) or len(row_data) < 2: continue
                    row_idx = self.table.rowCount()
                    self.table.insertRow(row_idx)
                    ui_data = [row_data[1], row_data[0], row_data[2], row_data[3], row_data[4], row_data[5]]
                    for col_idx, val in enumerate(ui_data):
                        item = QTableWidgetItem(str(val))
                        item.setForeground(QColor("#BDD8E9"))
                        if col_idx == 5:
                            item.setTextAlignment(Qt.AlignCenter)
                        self.table.setItem(row_idx, col_idx, item)
            self.table.sortItems(0, Qt.AscendingOrder)
            self.table.setColumnWidth(0, 120)
            self.table.setColumnWidth(1, 350)
            self.table.setColumnWidth(2, 250)
            self.table.setColumnWidth(3, 90)
            self.table.setColumnWidth(4, 90)
            self.table.setColumnWidth(5, 80)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể đọc file alias:\n{e}")

    def _filter_table(self):
        search_text = self.search_input.text().lower()
        for r in range(self.table.rowCount()):
            code = self.table.item(r, 0).text().lower() if self.table.item(r, 0) else ""
            alias = self.table.item(r, 1).text().lower() if self.table.item(r, 1) else ""
            self.table.setRowHidden(r, not (search_text in alias or search_text in code))

    def _add_row(self):
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        for c in range(self.table.columnCount()):
            item = QTableWidgetItem("")
            item.setForeground(QColor("#BDD8E9"))
            self.table.setItem(row_idx, c, item)
        self.table.scrollToBottom()

    def _delete_row(self):
        rows = sorted(list(set(index.row() for index in self.table.selectedIndexes())), reverse=True)
        if not rows:
            QMessageBox.information(self, "Thông báo", "Vui lòng chọn dòng cần xóa.")
            return
        if QMessageBox.question(self, "Xác nhận", f"Xóa {len(rows)} dòng đã chọn?") == QMessageBox.Yes:
            for r in rows:
                self.table.removeRow(r)

    def _save_to_csv(self):
        try:
            self.table.blockSignals(True)
            rows_to_save = []
            for r in range(self.table.rowCount()):
                it_m = self.table.item(r, 0).text().strip() if self.table.item(r, 0) else ""
                it_a = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
                it_t = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else ""
                it_k = self.table.item(r, 3).text().strip() if self.table.item(r, 3) else ""
                it_l = self.table.item(r, 4).text().strip() if self.table.item(r, 4) else ""
                it_h = self.table.item(r, 5).text().strip() if self.table.item(r, 5) else "1"
                if it_a and it_m:
                    rows_to_save.append([it_a, it_m, it_t, it_k, it_l, it_h])
            with open(self.alias_file, mode='w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Alias", "Mã", "Tên", "ĐVT Kho", "ĐVT Lóng", "Hệ số"])
                writer.writerows(rows_to_save)
            self.data_manager.load_all()
            self.table.blockSignals(False)
            QMessageBox.information(self, "Thành công", "Đã lưu từ điển Alias và cập nhật hệ thống.")
            self.accept()
        except Exception as e:
            self.table.blockSignals(False)
            QMessageBox.critical(self, "Lỗi", f"Không thể lưu file:\n{e}")

    def _stylesheet(self):
        return """
        QDialog { background: #001D39; }
        QLabel { color: #BDD8E9; }
        QLineEdit { background: #0A2740; color: #BDD8E9; border: 1px solid #49769F; border-radius: 6px; padding: 5px; }
        QTableWidget { 
            background: transparent; border: 1px solid rgba(123, 189, 232, 0.2); 
            gridline-color: rgba(123,189,232,0.1); color: #BDD8E9; 
            alternate-background-color: rgba(123, 189, 232, 0.05);
        }
        QHeaderView::section { background: #0A2740; color: #7BBDE8; font-weight: bold; border: 1px solid rgba(123, 189, 232, 0.2); padding: 5px; }
        QPushButton { background: rgba(10, 65, 116, 0.4); color: #BDD8E9; border: 1px solid rgba(123, 189, 232, 0.2); border-radius: 8px; padding: 8px 15px; }
        QPushButton:hover { background: #49769F; color: white; border-color: #7BBDE8; }
        """
