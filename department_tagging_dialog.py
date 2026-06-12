"""Pre-scan department tagging: headless TaggingState core + Qt dialog view.

The TaggingState class has no Qt dependency so it is unit-testable. The
DepartmentTaggingDialog (added in a later task) is a thin view over it.
"""

from departments import VALID_DEPARTMENTS


class TaggingState:
    """Ordered list of image filenames + their department assignments."""

    def __init__(self, filenames):
        self.filenames = list(filenames)
        self.assignments = {}          # filename -> dept (UPPER, valid only)
        self.rotations = {}            # filename -> display angle (0/90/180/270)
        self.current_index = 0

    @property
    def total(self):
        return len(self.filenames)

    def current_filename(self):
        if not self.filenames:
            return None
        return self.filenames[self.current_index]

    def _next_unassigned_index(self):
        n = self.total
        for offset in range(1, n + 1):
            idx = (self.current_index + offset) % n
            if self.filenames[idx] not in self.assignments:
                return idx
        return None

    def assign(self, dept):
        dept = str(dept or "").strip().upper()
        if dept not in VALID_DEPARTMENTS:
            return False
        fn = self.current_filename()
        if fn is None:
            return False
        self.assignments[fn] = dept
        nxt = self._next_unassigned_index()
        if nxt is not None:
            self.current_index = nxt
        return True

    def back(self):
        if self.current_index > 0:
            self.current_index -= 1

    def forward(self):
        if self.current_index < self.total - 1:
            self.current_index += 1

    def goto(self, index):
        if 0 <= index < self.total:
            self.current_index = index

    def department_of(self, filename):
        return self.assignments.get(filename)

    def rotation_of(self, filename):
        return self.rotations.get(filename, 0)

    def _rotate(self, delta):
        fn = self.current_filename()
        if fn is None:
            return
        self.rotations[fn] = (self.rotations.get(fn, 0) + delta) % 360

    def rotate_right(self):
        self._rotate(90)

    def rotate_left(self):
        self._rotate(-90)

    def assigned_count(self):
        return len(self.assignments)

    def remaining(self):
        return self.total - self.assigned_count()

    def is_complete(self):
        return self.total > 0 and all(
            fn in self.assignments for fn in self.filenames
        )

    def get_department_map(self):
        return dict(self.assignments)


# --- Qt view (guarded so TaggingState stays importable without PyQt5) ---
try:
    import os

    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QTransform
    from PyQt5.QtWidgets import (
        QApplication, QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
        QListWidget, QListWidgetItem, QWidget, QMessageBox, QSizePolicy, QMenu,
    )

    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False


if _QT_AVAILABLE:
    _DEPT_HOTKEYS = {
        Qt.Key_1: "BEP", Qt.Key_2: "BAR", Qt.Key_3: "BANH", Qt.Key_4: "RANG",
    }

    class DepartmentTaggingDialog(QDialog):
        """Tag each invoice image to a department before scanning.

        image_paths: absolute paths (order is cosmetic; the returned map is keyed
        by basename to line up with how the pipeline iterates os.listdir).
        store_name: label shown at top (forward-compat seam for multi-store).
        """

        def __init__(self, image_paths, store_name="Lighthouse", parent=None):
            super().__init__(parent)
            self._paths_by_name = {os.path.basename(p): p for p in image_paths}
            self.state = TaggingState([os.path.basename(p) for p in image_paths])
            self._start_armed = False   # Down at end-of-list highlights Start
            self.setWindowTitle("Gán bộ phận cho hoá đơn")
            self._size_to_screen()
            self._build_ui(store_name)
            self._refresh()

        def _size_to_screen(self):
            # Open large so the invoice image is easy to read; ~92% of the screen.
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                self.resize(int(geo.width() * 0.92), int(geo.height() * 0.92))
                self.move(
                    geo.x() + (geo.width() - self.width()) // 2,
                    geo.y() + (geo.height() - self.height()) // 2,
                )
            else:
                self.resize(1400, 950)

        # ---- UI construction ----
        def _build_ui(self, store_name):
            # The dialog owns the keyboard: children are non-focusable (below) so
            # they never steal hotkeys (digits / arrows) from keyPressEvent.
            self.setFocusPolicy(Qt.StrongFocus)
            root = QHBoxLayout(self)

            left = QVBoxLayout()
            self.lbl_store = QLabel(f"Cửa hàng: {store_name}")
            self.lbl_store.setStyleSheet("font-weight:600;")
            left.addWidget(self.lbl_store)

            self.lbl_progress = QLabel()
            left.addWidget(self.lbl_progress)

            self._dept_buttons = {}
            for key, dept in _DEPT_HOTKEYS.items():
                label = key - Qt.Key_0
                btn = QPushButton(f"[{label}]  {dept}")
                btn.setMinimumHeight(48)
                btn.setAutoDefault(False)
                btn.setFocusPolicy(Qt.NoFocus)
                btn.clicked.connect(lambda _=False, d=dept: self._assign(d))
                left.addWidget(btn)
                self._dept_buttons[dept] = btn

            self.list_files = QListWidget()
            self.list_files.setFocusPolicy(Qt.NoFocus)   # don't eat digit/arrow keys
            self.list_files.currentRowChanged.connect(self._on_row_changed)
            left.addWidget(self.list_files, 1)

            self.btn_start = QPushButton("✅ Bắt đầu xử lý")
            self.btn_start.setAutoDefault(False)
            self.btn_start.setFocusPolicy(Qt.NoFocus)
            self.btn_start.clicked.connect(self._on_start)
            left.addWidget(self.btn_start)

            left_w = QWidget()
            left_w.setLayout(left)
            left_w.setFixedWidth(360)
            root.addWidget(left_w)

            right = QVBoxLayout()
            top_row = QHBoxLayout()
            self.lbl_header = QLabel()
            self.lbl_header.setStyleSheet("font-weight:600;")
            top_row.addWidget(self.lbl_header, 1)
            self.btn_rot_left = QPushButton("↺ Xoay trái")
            self.btn_rot_right = QPushButton("↻ Xoay phải")
            for b, fn in ((self.btn_rot_left, self._rotate_left),
                          (self.btn_rot_right, self._rotate_right)):
                b.setAutoDefault(False)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(lambda _=False, f=fn: f())
                top_row.addWidget(b)
            right.addLayout(top_row)

            self.lbl_image = QLabel("(không có ảnh)")
            self.lbl_image.setAlignment(Qt.AlignCenter)
            self.lbl_image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            self.lbl_image.setContextMenuPolicy(Qt.CustomContextMenu)
            self.lbl_image.customContextMenuRequested.connect(self._show_image_menu)
            right.addWidget(self.lbl_image, 1)
            root.addLayout(right, 1)

            self.lbl_hint = QLabel(
                "Phím: 1-4 gán bộ phận • ←/→ xoay ảnh • ↑/↓ hoặc Backspace đổi ảnh • "
                "Enter bắt đầu • Esc huỷ"
            )
            self.lbl_hint.setStyleSheet("color:#9bb8d0; font-size:11px;")
            self.lbl_hint.setWordWrap(True)
            left.addWidget(self.lbl_hint)

            for name in self.state.filenames:
                self.list_files.addItem(QListWidgetItem(name))

        # ---- actions ----
        def _assign(self, dept):
            self._start_armed = False
            self.state.assign(dept)
            self._refresh()

        def _on_row_changed(self, row):
            if row >= 0 and row != self.state.current_index:
                self._start_armed = False
                self.state.goto(row)
                self._refresh()

        def _sync_list_selection(self):
            self.list_files.blockSignals(True)
            self.list_files.setCurrentRow(self.state.current_index)
            item = self.list_files.item(self.state.current_index)
            if item is not None:
                self.list_files.scrollToItem(item)
            self.list_files.blockSignals(False)

        def _rotate_left(self):
            self.state.rotate_left()
            self._render_image(self.state.current_filename() or "")

        def _rotate_right(self):
            self.state.rotate_right()
            self._render_image(self.state.current_filename() or "")

        def _show_image_menu(self, pos):
            menu = QMenu(self)
            menu.addAction("↺ Xoay trái", self._rotate_left)
            menu.addAction("↻ Xoay phải", self._rotate_right)
            menu.exec_(self.lbl_image.mapToGlobal(pos))

        def _on_start(self):
            if self.state.is_complete():
                self.accept()

        # ---- rendering ----
        def _refresh(self):
            self._sync_list_selection()
            total = self.state.total
            idx = self.state.current_index
            name = self.state.current_filename() or ""
            self.lbl_header.setText(f"Ảnh {idx + 1} / {total} — {name}")
            self.lbl_progress.setText(
                f"Đã gán: {self.state.assigned_count()} / {total}"
            )
            for i, fn in enumerate(self.state.filenames):
                dept = self.state.department_of(fn)
                self.list_files.item(i).setText(f"{fn}   [{dept or '—'}]")
            cur_dept = self.state.department_of(name)
            for dept, btn in self._dept_buttons.items():
                btn.setStyleSheet(
                    "background:#2f6fb0; color:white; font-weight:700;"
                    if dept == cur_dept else ""
                )
            complete = self.state.is_complete()
            self.btn_start.setEnabled(complete)
            if complete and self._start_armed:
                self.btn_start.setStyleSheet(
                    "background:#1e8f4e; color:white; font-weight:800;"
                    "border:2px solid #7CFFB0; padding:6px;"
                )
                self.btn_start.setText("✅ Bắt đầu xử lý  (Enter)")
            else:
                self.btn_start.setStyleSheet("")
                self.btn_start.setText("✅ Bắt đầu xử lý")
            self._render_image(name)

        def _render_image(self, name):
            path = self._paths_by_name.get(name)
            if not path or not os.path.exists(path):
                self.lbl_image.clear()
                self.lbl_image.setText("Không tải được ảnh")
                return
            from post_process_dialog import _load_invoice_pixmap
            pix = _load_invoice_pixmap(path)
            if pix.isNull():
                self.lbl_image.clear()
                self.lbl_image.setText("Không tải được ảnh")
                return
            angle = self.state.rotation_of(name)
            if angle:
                pix = pix.transformed(QTransform().rotate(angle), Qt.SmoothTransformation)
            # Fit within the panel (both dimensions) so rotated images aren't clipped.
            avail_w = max(200, self.lbl_image.width())
            avail_h = max(200, self.lbl_image.height())
            self.lbl_image.setPixmap(
                pix.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        def showEvent(self, event):
            super().showEvent(event)
            self.setFocus()   # dialog owns the keyboard from the first keypress
            self._render_image(self.state.current_filename() or "")

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._render_image(self.state.current_filename() or "")

        # ---- keys ----
        def keyPressEvent(self, event):
            key = event.key()
            if key in _DEPT_HOTKEYS:
                self._assign(_DEPT_HOTKEYS[key]); return
            if key == Qt.Key_Left:
                self._rotate_left(); return
            if key == Qt.Key_Right:
                self._rotate_right(); return
            if key in (Qt.Key_Up, Qt.Key_Backspace):
                self._start_armed = False
                self.state.back(); self._refresh(); return
            if key == Qt.Key_Down:
                before = self.state.current_index
                self.state.forward()
                # Down at the last image (no move left) arms the Start button so
                # the user can press Enter to begin — only once everything is tagged.
                self._start_armed = (
                    self.state.current_index == before and self.state.is_complete()
                )
                self._refresh(); return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._on_start(); return
            if key == Qt.Key_Escape:
                self._confirm_cancel(); return
            super().keyPressEvent(event)

        def closeEvent(self, event):
            # Treat the window [X] like Esc: confirm, then abort the scan.
            event.ignore()
            self._confirm_cancel()

        def _confirm_cancel(self):
            resp = QMessageBox.question(
                self, "Hủy phiên scan",
                "Hủy toàn bộ phiên scan? Chưa gán đủ bộ phận nên sẽ không xử lý ảnh nào.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if resp == QMessageBox.Yes:
                self.reject()

        def get_department_map(self):
            return self.state.get_department_map()
