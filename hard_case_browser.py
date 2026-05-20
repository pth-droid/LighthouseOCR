import os
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QFrame, QWidget, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QColor, QPixmap, QTransform

from path_utils import get_root_dir

# Columns used as the display schema (PNMH primary; ChiPhi data slots in by key number)
_COLS = [
    (2,  "SỐ CT / NGÀY"),
    (3,  "NGÀY / SỐ CT"),
    (4,  "BỘ PHẬN (CP)"),
    (6,  "BỘ PHẬN"),
    (7,  "MÃ ĐỐI TƯỢNG"),
    (8,  "ĐỐI TƯỢNG"),
    (9,  "DIỄN GIẢI / TK NỢ"),
    (10, "TK CÓ"),
    (11, "KHO NHẬP"),
    (12, "MÃ VẬT TƯ"),
    (13, "ĐVT"),
    (14, "TIỀN (CP)"),
    (15, "GHI CHÚ (CP)"),
    (16, "SỐ LƯỢNG"),
    (17, "ĐƠN GIÁ"),
    (20, "THÀNH TIỀN"),
    (27, "GHI CHÚ"),
]

_C_TEXT    = QColor("#BDD8E9")
_C_CHG_BFG = QColor("#E8A87F")
_C_CHG_BBG = QColor("#3A1A0A")
_C_CHG_AFG = QColor("#7FD47F")
_C_CHG_ABG = QColor("#0A2A0A")
_C_ROW0_BG = QColor("#0A1828")
_C_ROW1_BG = QColor("#081408")

_MONEY_COLS = {14, 17, 20}  # col numbers that should use accounting format


def _fmt_accounting(val: str) -> str:
    try:
        return "{:,.0f}".format(float(val.replace(",", "").replace(" ", "")))
    except (ValueError, AttributeError):
        return val


def _fmt_case_label(folder_name: str, mtime: float) -> str:
    parts = folder_name.split("_")
    dt = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
    tab = parts[-2].upper() if len(parts) >= 2 else "?"
    row = parts[-1] if len(parts) >= 1 else "?"
    return f"{tab} · {row}   {dt}"


class HardCaseBrowserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Enable maximize button
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
        )

        self._root_dir = os.path.join(get_root_dir(), "HARD CASE COLLECTED")
        self._row_case_map: dict[int, tuple] = {}  # table_row -> (folder_path, images)
        self._original_pixmap  = None
        self._zoom_factor      = 1.0
        self._current_rotation = 0
        self._drag_start    = None
        self._drag_scroll_h = 0
        self._drag_scroll_v = 0

        self.setWindowTitle("Xem Hard Cases đã thu thập")
        self.resize(1300, 750)
        self.setStyleSheet(self._stylesheet())
        self._build_ui()
        self._load_all_cases()

    # ── Style ──────────────────────────────────
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
            QPushButton {
                background-color: #0A4174;
                color: #BDD8E9;
                border: 1px solid rgba(123,189,232,0.35);
                border-radius: 8px;
                padding: 7px 12px;
                font-size: 13px;
                font-weight: 600;
                min-width: 100px;
            }
            QPushButton:hover  { background-color: #0F548E; }
            QPushButton:pressed{ background-color: #08345C; }
            QSplitter::handle  { background: rgba(123,189,232,0.15); border-radius: 3px; }
        """

    # ── Layout ─────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("🗂  Hard Cases đã thu thập  —  mỗi cặp 2 dòng: Gốc (trên) · Đã sửa (dưới)")
        title.setStyleSheet("font-size:14px; font-weight:700; color:#BDD8E9;")
        root.addWidget(title)

        # Status bar showing selected case metadata
        self.lbl_info = QLabel("—")
        self.lbl_info.setStyleSheet(
            "color:#7BBDE8; font-size:12px; padding:4px 8px;"
            " background:rgba(10,39,64,0.6); border-radius:4px;"
            " border:1px solid rgba(123,189,232,0.15);"
        )
        self.lbl_info.setWordWrap(True)
        root.addWidget(self.lbl_info)

        # Single horizontal splitter: table | image viewer (mirrors PostProcessDialog)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet(
            "QSplitter::handle { background: rgba(123,189,232,0.15); border-radius:3px; }"
        )

        # Data table
        self.table = QTableWidget()
        self.table.setColumnCount(len(_COLS) + 1)  # +1 for row-label column
        headers = [""] + [lbl for _, lbl in _COLS]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in range(1, len(_COLS) + 1):
            self.table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(110)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setRowCount(0)
        self.table.currentCellChanged.connect(self._on_row_changed)
        splitter.addWidget(self.table)

        # Image panel
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

    # ── Load all cases ──────────────────────────
    def _load_all_cases(self):
        self.table.setRowCount(0)
        self._row_case_map.clear()
        self._clear_image()

        if not os.path.isdir(self._root_dir):
            return

        folders = []
        for name in os.listdir(self._root_dir):
            path = os.path.join(self._root_dir, name)
            if os.path.isdir(path):
                folders.append((name, path, os.path.getmtime(path)))
        folders.sort(key=lambda x: x[2], reverse=True)
        self._folders = folders

        for name, folder_path, mtime in folders:
            report_path = os.path.join(folder_path, "report.json")
            if not os.path.isfile(report_path):
                continue
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)
            except Exception:
                continue
            self._append_case_rows(report, folder_path, name, mtime)

        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def _append_case_rows(self, report: dict, folder_path: str, name: str, mtime: float):
        before  = report.get("before", {})
        after   = report.get("after",  {})
        tab     = report.get("tab", "PNMH")
        images  = report.get("image_paths", [])
        note    = report.get("note", "")
        created = report.get("created_at", "")
        row_n   = report.get("table_row_index_1_based", "?")
        dt      = datetime.fromisoformat(created).strftime("%d/%m %H:%M") if created else datetime.fromtimestamp(mtime).strftime("%d/%m %H:%M")

        base_row = self.table.rowCount()
        self.table.insertRow(base_row)
        self.table.insertRow(base_row + 1)
        self.table.setRowHeight(base_row,     28)
        self.table.setRowHeight(base_row + 1, 28)

        # Register both rows → (folder_path, images, report)
        self._row_case_map[base_row]     = (folder_path, images, report)
        self._row_case_map[base_row + 1] = (folder_path, images, report)

        def _cell(text, fg, bg, tooltip=None):
            it = QTableWidgetItem(text)
            it.setForeground(fg)
            it.setBackground(bg)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if tooltip:
                it.setToolTip(tooltip)
            return it

        self.table.setItem(base_row,     0, _cell("📋", QColor("#7BBDE8"), _C_ROW0_BG))
        self.table.setItem(base_row + 1, 0, _cell("✏️", QColor("#7FD47F"), _C_ROW1_BG))

        # Data cells
        for c_idx, (col_num, _) in enumerate(_COLS, start=1):
            key      = str(col_num)
            b_raw    = str(before.get(key, "") or "")
            a_raw    = str(after.get(key,  "") or "")
            changed  = b_raw != a_raw
            is_money = col_num in _MONEY_COLS

            b_disp = _fmt_accounting(b_raw) if is_money and b_raw else b_raw
            a_disp = _fmt_accounting(a_raw) if is_money and a_raw else a_raw

            b_it = _cell(b_disp,
                         _C_CHG_BFG if changed else _C_TEXT,
                         _C_CHG_BBG if changed else _C_ROW0_BG,
                         tooltip=b_raw if b_raw else None)
            a_it = _cell(a_disp,
                         _C_CHG_AFG if changed else _C_TEXT,
                         _C_CHG_ABG if changed else _C_ROW1_BG,
                         tooltip=a_raw if a_raw else None)
            self.table.setItem(base_row,     c_idx, b_it)
            self.table.setItem(base_row + 1, c_idx, a_it)

    # ── Row selection → image ───────────────────
    def _on_row_changed(self, cur_row, *_):
        if cur_row < 0:
            return
        case = self._row_case_map.get(cur_row)
        if not case:
            return
        folder_path, images, report = case

        # Update status bar
        tab     = report.get("tab", "?")
        row_n   = report.get("table_row_index_1_based", "?")
        created = report.get("created_at", "")
        note    = report.get("note", "")
        source  = report.get("source_file", "") or os.path.basename(folder_path)
        dt_str  = ""
        if created:
            try:
                dt_str = datetime.fromisoformat(created).strftime("%d/%m/%Y %H:%M")
            except ValueError:
                dt_str = created
        parts = [f"Tab: {tab}", f"Dòng: {row_n}"]
        if dt_str:
            parts.append(f"Thời gian: {dt_str}")
        if source:
            parts.append(f"File: {source}")
        if note:
            parts.append(f"📝 {note}")
        self.lbl_info.setText("  ·  ".join(parts))

        self._current_rotation = 0
        self._original_pixmap  = None
        if images:
            img_path = os.path.join(folder_path, images[0])
            if os.path.isfile(img_path):
                self._load_image(img_path)
                return
        self._clear_image()

    def _open_current_folder(self):
        row = self.table.currentRow()
        case = self._row_case_map.get(row)
        if not case:
            return
        folder_path = case[0]
        try:
            os.startfile(folder_path)
        except (OSError, AttributeError) as exc:
            QMessageBox.critical(self, "Lỗi", f"Không thể mở thư mục:\n{exc}")

    # ── Image ──────────────────────────────────
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
