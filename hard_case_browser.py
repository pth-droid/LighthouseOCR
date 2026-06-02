import os
import json
import re
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QFrame, QWidget, QAbstractItemView, QTabWidget,
)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QColor, QPixmap, QTransform, QIcon

from path_utils import get_root_dir, get_asset_path

# â”€â”€ Column schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_PNMH_COLS = [
    (2,  "SỐ CHỨNG TỪ"),
    (3,  "NGÀY HOÁ ĐƠN"),
    (6,  "BỘ PHẬN"),
    (8,  "ĐỐI TƯỢNG"),
    (9,  "DIỄN GIẢI"),
    (11, "KHO NHẬP"),
    (12, "MÃ VẬT TƯ"),
    (13, "ĐVT"),
    (16, "SỐ LƯỢNG"),
    (17, "ĐƠN GIÁ"),
    (20, "THÀNH TIỀN"),
    (27, "GHI CHÚ"),
]
_PNMH_MONEY = {17, 20}

_CHIPHI_COLS = [
    (2,  "NGÀY GHI SỔ"),
    (3,  "SỐ CHỨNG TỪ"),
    (4,  "BỘ PHẬN"),
    (7,  "MÃ ĐỐI TƯỢNG"),
    (8,  "DIỄN GIẢI"),
    (9,  "TK NỢ"),
    (10, "TK CÓ"),
    (14, "THÀNH TIỀN"),
    (15, "GHI CHÚ"),
]
_CHIPHI_MONEY = {14}

# â”€â”€ Colors â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_C_TEXT    = QColor("#BDD8E9")
_C_CHG_BFG = QColor("#E8A87F")
_C_CHG_BBG = QColor("#3A1A0A")
_C_CHG_AFG = QColor("#7FD47F")
_C_CHG_ABG = QColor("#0A2A0A")
_C_ROW0_BG = QColor("#0A1828")
_C_ROW1_BG = QColor("#081408")

_IMG_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')


def _fmt_accounting(val: str) -> str:
    try:
        return "{:,.0f}".format(float(val.replace(",", "").replace(" ", "")))
    except (ValueError, AttributeError):
        return val


class HardCaseBrowserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
        )

        self._root_dir = os.path.join(get_root_dir(), "HARD CASE COLLECTED")
        self._pnmh_row_map:   dict[int, tuple] = {}  # row -> (folder_path, images, report)
        self._chiphi_row_map: dict[int, tuple] = {}
        self._original_pixmap  = None
        self._zoom_factor      = 1.0
        self._current_rotation = 0
        self._drag_start    = None
        self._drag_scroll_h = 0
        self._drag_scroll_v = 0

        self.setWindowTitle("Xem Hard Cases đã thu thập")
        self._set_window_icon()
        self.resize(1300, 750)
        self.setWindowState(Qt.WindowMaximized)
        self.setStyleSheet(self._stylesheet())
        self._build_ui()
        self._load_all_cases()

    # â”€â”€ Style â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _stylesheet(self) -> str:
        return """
            QDialog {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #001D39, stop:1 #000E1F);
            }
            QLabel { color: #BDD8E9; font-size: 13px; }
            QTableWidget {
                background-color: rgba(10,39,64,0.82);
                color: #BDD8E9;
                border: 1px solid rgba(123,189,232,0.22);
                border-radius: 4px;
                font-size: 12px;
                gridline-color: rgba(123,189,232,0.15);
            }
            QTableWidget::item { padding: 3px 6px; }
            QHeaderView::section {
                background-color: #0A2740;
                color: #7BBDE8;
                padding: 5px 6px;
                border: none;
                font-weight: 700;
                font-size: 12px;
            }
            QTabWidget::pane {
                border: 1px solid rgba(123,189,232,0.22);
                border-radius: 4px;
                background: transparent;
            }
            QTabBar::tab {
                background: rgba(0,29,57,0.6); color: #6EA2B3;
                border: 1px solid rgba(123,189,232,0.2);
                border-bottom-color: transparent;
                padding: 6px 16px; margin-right: 2px;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
                font-size: 13px;
            }
            QTabBar::tab:selected { background: #0A4174; color: #ffffff;
                border-color: rgba(123,189,232,0.5); }
            QPushButton {
                background-color: #0A4174; color: #BDD8E9;
                border: 1px solid rgba(123,189,232,0.35);
                border-radius: 8px; padding: 7px 12px;
                font-size: 13px; font-weight: 600; min-width: 100px;
            }
            QPushButton:hover  { background-color: #0F548E; }
            QPushButton:pressed{ background-color: #08345C; }
            QSplitter::handle  { background: rgba(123,189,232,0.15); border-radius: 3px; }
        """

    # â”€â”€ Layout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("🗂  Hard Cases đã thu thập  —  mỗi cặp 2 dòng: Gốc (trên) · Đã sửa (dưới)")
        title.setStyleSheet("font-size:14px; font-weight:700; color:#BDD8E9;")
        root.addWidget(title)

        # Status bar: left=note, right=clicked cell content
        status_w = QWidget()
        status_w.setFixedHeight(32)
        status_w.setStyleSheet(
            "background:rgba(10,39,64,0.55); border-radius:4px;"
            " border:1px solid rgba(123,189,232,0.12);"
        )
        sl = QHBoxLayout(status_w)
        sl.setContentsMargins(8, 0, 8, 0)
        sl.setSpacing(10)
        self.lbl_note = QLabel("—")
        self.lbl_note.setStyleSheet(
            "color:#7BBDE8; font-size:14px; border:none; background:transparent;"
        )
        self.lbl_note.setMinimumWidth(0)
        self.lbl_cell = QLabel("")
        self.lbl_cell.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_cell.setStyleSheet(
            "color:#BDD8E9; font-size:14px; border:none; background:transparent;"
        )
        self.lbl_cell.setMinimumWidth(0)
        sl.addWidget(self.lbl_note, 1)
        sl.addWidget(self.lbl_cell, 1)
        root.addWidget(status_w)

        # Main splitter: left=tables, right=image viewer
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet(
            "QSplitter::handle { background: rgba(123,189,232,0.15); border-radius:3px; }"
        )

        # Left: tab widget with separate PNMH and ChiPhi tables
        self.left_tabs = QTabWidget()

        self.pnmh_table = self._make_table(_PNMH_COLS)
        self.pnmh_table.currentCellChanged.connect(
            lambda r, c, pr, _pc: self._on_cell_changed(
                self.pnmh_table, self._pnmh_row_map, r, c, pr
            )
        )
        self.pnmh_table.itemSelectionChanged.connect(
            lambda: self._update_selection_status(self.pnmh_table)
        )

        self.chiphi_table = self._make_table(_CHIPHI_COLS)
        self.chiphi_table.currentCellChanged.connect(
            lambda r, c, pr, _pc: self._on_cell_changed(
                self.chiphi_table, self._chiphi_row_map, r, c, pr
            )
        )
        self.chiphi_table.itemSelectionChanged.connect(
            lambda: self._update_selection_status(self.chiphi_table)
        )

        self.left_tabs.addTab(self.pnmh_table,   "📁 PNMH (0)")
        self.left_tabs.addTab(self.chiphi_table,  "📁 Chi phí (0)")
        splitter.addWidget(self.left_tabs)

        splitter.addWidget(self._build_image_panel())
        splitter.setSizes([880, 420])
        root.addWidget(splitter, 1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        for label, slot in [
            ("🔄  Làm mới",    self._load_all_cases),
            ("📂  Mở thư mục", self._open_current_folder),
            ("✖  Đóng",        self.accept),
        ]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            footer.addWidget(b)
        root.addLayout(footer)

    def _make_table(self, cols) -> QTableWidget:
        t = QTableWidget()
        t.setColumnCount(len(cols) + 1)
        t.setHorizontalHeaderLabels([""] + [lbl for _, lbl in cols])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectItems)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in range(1, len(cols) + 1):
            t.horizontalHeader().setSectionResizeMode(c, QHeaderView.Interactive)
        t.horizontalHeader().setDefaultSectionSize(110)
        t.horizontalHeader().setStretchLastSection(True)
        return t

    def _build_image_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(
            "background:rgba(0,10,20,0.6);"
            " border:1px solid rgba(123,189,232,0.2); border-radius:4px;"
        )
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(6, 6, 6, 6)
        pl.setSpacing(4)

        topbar = QHBoxLayout()
        lbl = QLabel("🖼  Ảnh Hóa Đơn  |  Cuộn: zoom  |  Kéo: di chuyển")
        lbl.setStyleSheet(
            "color:#7BBDE8; font-weight:700; font-size:11px; border:none; background:transparent;"
        )
        topbar.addWidget(lbl, 1)

        _bs = (
            "QPushButton { background:rgba(10,65,116,0.5); color:#7BBDE8;"
            " border:1px solid rgba(123,189,232,0.25); border-radius:5px;"
            " padding:2px 8px; font-size:14px; min-height:22px; min-width:28px; }"
            "QPushButton:hover { background:rgba(73,118,159,0.6); color:#fff; }"
        )
        for symbol, deg in [("↺", 90), ("↻", -90)]:
            b = QPushButton(symbol)
            b.setStyleSheet(_bs)
            b.setFixedSize(30, 24)
            b.clicked.connect(lambda _, d=deg: self._rotate_image(d))
            topbar.addWidget(b)
        pl.addLayout(topbar)

        self.img_scroll = QScrollArea()
        self.img_scroll.setWidgetResizable(False)
        self.img_scroll.setFrameShape(QFrame.NoFrame)
        self.img_scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        self.img_label = QLabel("Nhấp vào một dòng\nđể xem ảnh hóa đơn")
        self.img_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.img_label.setWordWrap(True)
        self.img_label.setStyleSheet("color:#49769F; font-size:12px; background:transparent;")
        self.img_scroll.setWidget(self.img_label)
        self.img_scroll.viewport().installEventFilter(self)
        pl.addWidget(self.img_scroll, 1)
        return panel

    # â”€â”€ Load cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _load_all_cases(self):
        self.pnmh_table.setRowCount(0)
        self.chiphi_table.setRowCount(0)
        self._pnmh_row_map.clear()
        self._chiphi_row_map.clear()
        self._clear_image()
        self.lbl_note.setText("—")
        self.lbl_cell.setText("")

        if not os.path.isdir(self._root_dir):
            return

        # Collect cases from date folders (YYYYMMDD/)
        all_cases = []
        for date_folder in os.listdir(self._root_dir):
            if not re.match(r'^\d{8}$', date_folder):
                continue
            date_path = os.path.join(self._root_dir, date_folder)
            if not os.path.isdir(date_path):
                continue
            for fname in os.listdir(date_path):
                if not fname.endswith('.json'):
                    continue
                json_path = os.path.join(date_path, fname)
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        report = json.load(f)
                except Exception:
                    continue
                # Image: same stem as JSON, any image extension
                stem = os.path.splitext(fname)[0]
                images = []
                for ext in _IMG_EXTS:
                    if os.path.isfile(os.path.join(date_path, stem + ext)):
                        images.append(stem + ext)
                        break
                all_cases.append((date_path, images, report))

        all_cases.sort(key=lambda x: x[2].get("created_at", ""), reverse=True)

        pnmh_n = chiphi_n = 0
        for folder_path, images, report in all_cases:
            if report.get("tab") == "ChiPhi":
                self._append_rows(
                    self.chiphi_table, self._chiphi_row_map,
                    _CHIPHI_COLS, _CHIPHI_MONEY,
                    folder_path, images, report,
                )
                chiphi_n += 1
            else:
                self._append_rows(
                    self.pnmh_table, self._pnmh_row_map,
                    _PNMH_COLS, _PNMH_MONEY,
                    folder_path, images, report,
                )
                pnmh_n += 1

        self.left_tabs.setTabText(0, f"📁 PNMH ({pnmh_n})")
        self.left_tabs.setTabText(1, f"📁 Chi phí ({chiphi_n})")

        if self.pnmh_table.rowCount() > 0:
            self.pnmh_table.setCurrentCell(0, 0)
        elif self.chiphi_table.rowCount() > 0:
            self.left_tabs.setCurrentIndex(1)
            self.chiphi_table.setCurrentCell(0, 0)

    def _append_rows(self, table, row_map, cols, money_cols, folder_path, images, report):
        before = report.get("before", {})
        after  = report.get("after",  {})

        base_row = table.rowCount()
        table.insertRow(base_row)
        table.insertRow(base_row + 1)
        table.setRowHeight(base_row,     28)
        table.setRowHeight(base_row + 1, 28)

        row_map[base_row]     = (folder_path, images, report)
        row_map[base_row + 1] = (folder_path, images, report)

        def _cell(text, fg, bg):
            it = QTableWidgetItem(text)
            it.setForeground(fg)
            it.setBackground(bg)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            return it

        table.setItem(base_row,     0, _cell("📋", QColor("#7BBDE8"), _C_ROW0_BG))
        table.setItem(base_row + 1, 0, _cell("✏️", QColor("#7FD47F"), _C_ROW1_BG))

        for c_idx, (col_num, _) in enumerate(cols, start=1):
            key     = str(col_num)
            b_raw   = str(before.get(key, "") or "")
            a_raw   = str(after.get(key,  "") or "")
            changed  = b_raw != a_raw
            is_money = col_num in money_cols

            b_disp = _fmt_accounting(b_raw) if is_money and b_raw else b_raw
            a_disp = _fmt_accounting(a_raw) if is_money and a_raw else a_raw

            b_it = _cell(b_disp,
                         _C_CHG_BFG if changed else _C_TEXT,
                         _C_CHG_BBG if changed else _C_ROW0_BG)
            a_it = _cell(a_disp,
                         _C_CHG_AFG if changed else _C_TEXT,
                         _C_CHG_ABG if changed else _C_ROW1_BG)
            table.setItem(base_row,     c_idx, b_it)
            table.setItem(base_row + 1, c_idx, a_it)

    # â”€â”€ Cell selection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _on_cell_changed(self, table, row_map, cur_row, cur_col, prev_row):
        if cur_row < 0:
            return

        self._update_selection_status(table)

        case = row_map.get(cur_row)
        if not case:
            return
        folder_path, images, report = case

        prev_case = row_map.get(prev_row) if prev_row >= 0 else None
        if prev_case and prev_case[0] == folder_path:
            return

        note = report.get("note", "")
        self.lbl_note.setText(note if note else "—")

        self._current_rotation = 0
        self._original_pixmap  = None
        if images:
            img_path = os.path.join(folder_path, images[0])
            if os.path.isfile(img_path):
                self._load_image(img_path)
                return
        self._clear_image()
    def _update_selection_status(self, table: QTableWidget):
        indexes = table.selectedIndexes()
        if not indexes:
            self.lbl_cell.setText("")
            return

        first = indexes[0]
        count = len(indexes)
        if count == 1:
            item = table.item(first.row(), first.column())
            self.lbl_cell.setText(item.text() if item else "")
            return

        nums = []
        for idx in indexes:
            item = table.item(idx.row(), idx.column())
            if not item:
                continue
            raw = (item.text() or "").strip()
            if not raw:
                continue
            try:
                nums.append(float(raw.replace(",", "").replace(" ", "")))
            except ValueError:
                pass

        if nums:
            self.lbl_cell.setText(f"Tổng: {sum(nums):,.2f} | {count} ô đã chọn")
        else:
            self.lbl_cell.setText(f"{count} ô đã chọn | Không có ô số để tính tổng")

    def _set_window_icon(self):
        for name in ("app_logo.png", "icon.ico"):
            icon_path = get_asset_path(name)
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                break

    def _open_current_folder(self):
        idx     = self.left_tabs.currentIndex()
        row_map = self._pnmh_row_map if idx == 0 else self._chiphi_row_map
        table   = self.pnmh_table    if idx == 0 else self.chiphi_table
        case = row_map.get(table.currentRow())
        if not case:
            return
        try:
            os.startfile(case[0])
        except (OSError, AttributeError) as exc:
            QMessageBox.critical(self, "Lỗi", f"Không thể mở thư mục:\n{exc}")

    # â”€â”€ Image viewer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _load_image(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            self._clear_image()
            return
        self._original_pixmap = pix
        self._zoom_factor = 1.0
        self._apply_image()

    def _apply_image(self):
        if self._original_pixmap is None:
            return
        pix = self._original_pixmap
        if self._current_rotation:
            pix = pix.transformed(
                QTransform().rotate(self._current_rotation), Qt.SmoothTransformation
            )
        w = int(pix.width()  * self._zoom_factor)
        h = int(pix.height() * self._zoom_factor)
        scaled = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img_label.setPixmap(scaled)
        self.img_label.resize(scaled.width(), scaled.height())

    def _clear_image(self):
        self._original_pixmap = None
        self._zoom_factor = 1.0
        self.img_label.setPixmap(QPixmap())
        self.img_label.setText("Nhấp vào một dòng\nđể xem ảnh hóa đơn")
        self.img_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

    def _rotate_image(self, degrees: int):
        if self._original_pixmap is None:
            return
        self._current_rotation = (self._current_rotation - degrees) % 360
        self._apply_image()

    def eventFilter(self, obj, event):
        if obj is self.img_scroll.viewport():
            et = event.type()
            if et == QEvent.Wheel:
                f = 1.15 if event.angleDelta().y() > 0 else (1 / 1.15)
                self._zoom_factor = max(0.1, min(10.0, self._zoom_factor * f))
                self._apply_image()
                return True
            if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_start    = event.pos()
                self._drag_scroll_h = self.img_scroll.horizontalScrollBar().value()
                self._drag_scroll_v = self.img_scroll.verticalScrollBar().value()
                self.img_scroll.viewport().setCursor(Qt.ClosedHandCursor)
                return True
            if et == QEvent.MouseMove and self._drag_start is not None:
                d = event.pos() - self._drag_start
                self.img_scroll.horizontalScrollBar().setValue(self._drag_scroll_h - d.x())
                self.img_scroll.verticalScrollBar().setValue(self._drag_scroll_v - d.y())
                return True
            if et == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self._drag_start = None
                self.img_scroll.viewport().setCursor(Qt.ArrowCursor)
                return True
        return super().eventFilter(obj, event)

