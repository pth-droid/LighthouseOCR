"""
Lighthouse OCR – Main App (PyQt5 Edition)
Bản hiện đại hoá giao diện, thay thế customtkinter.
Tính năng:
  - Browse chọn thư mục chứa ảnh đầu vào (không bắt buộc phải cùng thư mục .py)
  - Khu vực log rộng, cuộn được, timestamp dạng inline
  - Thanh tiến trình trực quan
  - Nút Dừng khẩn cấp
  - Thiết lập Admin (HWID lock + API Key) được bảo vệ mật khẩu
  - Toàn bộ logic OCR/Excel giữ nguyên như bản cũ
"""

import os
import sys

# Suppress harmless Qt font enumeration warnings (e.g. Bricolage Grotesque variants)
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"

import time
import json
import base64
import uuid
import shutil
import threading
import math
import logging
from path_utils import get_asset_path, get_root_dir
from constants import ROUTING_CONF_THRESHOLD

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QProgressBar,
    QFileDialog, QDialog, QDialogButtonBox, QMessageBox,
    QSizePolicy, QFrame, QGroupBox, QSpacerItem, QGridLayout, QComboBox, QScrollArea,
    QMenu
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QSize
from PyQt5.QtGui import (
    QFont, QColor, QPalette, QIcon, QTextCursor, QFontDatabase, QPixmap
)

# ──────────────────────────────────────────────
#  Custom Widgets
# ──────────────────────────────────────────────
class ClickableLineEdit(QLineEdit):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

# ──────────────────────────────────────────────
#  Constants / Config
# ──────────────────────────────────────────────
ADMIN_PASSWORD = "admin"
CONFIG_FILE    = get_asset_path(os.path.join("env", "lighthouse_config.json"))
GEMINI_API_KEY = ""
STATIC_SALT    = "lh_app_secure_v1"  # Cố định cho password để không bị sai khi đổi máy
APP_VERSION    = "v7.3"

# ──────────────────────────────────────────────
#  Color Palette (Ocean Blue)
#    Darkest  #001D39   ▸ deep navy
#    Dark     #0A4174   ▸ rich blue
#    Mid      #49769F   ▸ steel blue
#    Teal     #4E8EA2   ▸ teal accent
#    LightT   #6EA2B3   ▸ light teal
#    Sky      #7BBDE8   ▸ sky blue (primary accent)
#    Lightest #BDD8E9   ▸ ice blue / text on dark
# ──────────────────────────────────────────────

APP_STYLE = """
/* ── Global ── */
QWidget {
    background: transparent;
    color: #BDD8E9;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 15px;
}

/* ── Group-box cards (glassmorphism feel) ── */
QGroupBox {
    background-color: rgba(10, 65, 116, 0.45);
    border: 1px solid rgba(123, 189, 232, 0.18);
    border-radius: 14px;
    margin-top: 14px;
    padding: 16px 12px 10px 12px;
    color: #7BBDE8;
    font-size: 13px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: #6EA2B3;
}

/* ── Inputs ── */
QLineEdit {
    background-color: rgba(0, 29, 57, 0.65);
    border: 1px solid rgba(123, 189, 232, 0.25);
    border-radius: 10px;
    padding: 9px 14px;
    color: #BDD8E9;
    selection-background-color: #49769F;
    min-height: 38px;
}
QLineEdit:focus {
    border: 1px solid #7BBDE8;
}
QLineEdit:read-only {
    color: #6EA2B3;
}

/* ── Log area ── */
QTextEdit {
    background-color: rgba(0, 29, 57, 0.7);
    border: 1px solid rgba(123, 189, 232, 0.12);
    border-radius: 12px;
    padding: 12px;
    color: #6EA2B3;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    selection-background-color: #0A4174;
}

/* ── Buttons (shared) ── */
QPushButton {
    border-radius: 10px;
    padding: 8px 20px;
    font-weight: 600;
    font-size: 15px;
    min-height: 34px;
}

/* Start */
QPushButton#btn_start {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #0A4174, stop:0.5 #49769F, stop:1 #7BBDE8);
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    min-height: 48px;
    border-radius: 12px;
    border: 1px solid rgba(123, 189, 232, 0.35);
}
QPushButton#btn_start:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #49769F, stop:0.5 #7BBDE8, stop:1 #BDD8E9);
    color: #001D39;
}
QPushButton#btn_start:disabled {
    background: rgba(10, 65, 116, 0.35);
    color: #49769F;
    border-color: rgba(73, 118, 159, 0.2);
}

/* Stop */
QPushButton#btn_stop {
    background-color: rgba(180, 50, 50, 0.15);
    color: #fca5a5;
    border: 1px solid rgba(200, 70, 70, 0.4);
    font-size: 16px;
    font-weight: 700;
    min-height: 48px;
    border-radius: 12px;
}
QPushButton#btn_stop:hover {
    background-color: rgba(200, 60, 60, 0.75);
    color: white;
}
QPushButton#btn_stop:disabled {
    background-color: rgba(0, 29, 57, 0.3);
    color: #49769F;
    border-color: rgba(73, 118, 159, 0.15);
}

/* Browse & Open Result */
QPushButton#btn_browse, QPushButton#btn_open_output {
    background-color: rgba(0, 29, 57, 0.5);
    color: #7BBDE8;
    border: 1px solid rgba(123, 189, 232, 0.25);
    padding: 9px 16px;
    border-radius: 10px;
    min-height: 38px;
}
QPushButton#btn_browse:hover, QPushButton#btn_open_output:hover {
    background-color: rgba(10, 65, 116, 0.6);
    border-color: #7BBDE8;
    color: #BDD8E9;
}

/* Settings */
QPushButton#btn_settings {
    background-color: rgba(0, 29, 57, 0.3);
    color: #49769F;
    border: 1px solid rgba(73, 118, 159, 0.2);
    font-size: 13px;
    padding: 6px 14px;
    min-height: 28px;
    border-radius: 8px;
}
QPushButton#btn_settings:hover {
    color: #7BBDE8;
    border-color: rgba(123, 189, 232, 0.35);
    background-color: rgba(10, 65, 116, 0.35);
}

/* Clear log */
QPushButton#btn_clear_log {
    background-color: transparent;
    color: #49769F;
    border: 1px solid rgba(73, 118, 159, 0.2);
    font-size: 13px;
    padding: 5px 12px;
    min-height: 26px;
    border-radius: 8px;
}
QPushButton#btn_clear_log:hover {
    color: #7BBDE8;
    border-color: rgba(123, 189, 232, 0.35);
}

/* ── Progress bar ── */
QProgressBar {
    background-color: rgba(0, 29, 57, 0.5);
    border: 1px solid rgba(123, 189, 232, 0.15);
    border-radius: 4px;
    text-align: center;
    height: 8px;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #0A4174, stop:0.5 #4E8EA2, stop:1 #7BBDE8);
    border-radius: 3px;
}

/* ── Title labels ── */
QLabel#lbl_title {
    font-size: 26px;
    font-weight: 800;
    color: #BDD8E9;
}
QLabel#lbl_subtitle {
    font-size: 14px;
    color: #49769F;
}

/* ── Divider ── */
QFrame#h_divider {
    color: rgba(123, 189, 232, 0.12);
    background-color: rgba(123, 189, 232, 0.12);
    max-height: 1px;
}

/* ── ScrollBar ── */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:vertical {
    background: rgba(123, 189, 232, 0.2);
    min-height: 30px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(123, 189, 232, 0.4);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

/* ── Scrollbar (log area) ── */
QTextEdit QScrollBar:vertical {
    background: rgba(0, 29, 57, 0.3);
    width: 8px;
    border-radius: 4px;
    margin: 2px;
}
QTextEdit QScrollBar::handle:vertical {
    background: rgba(123, 189, 232, 0.25);
    border-radius: 4px;
    min-height: 30px;
}
QTextEdit QScrollBar::handle:vertical:hover {
    background: rgba(123, 189, 232, 0.45);
}
QTextEdit QScrollBar::add-line:vertical,
QTextEdit QScrollBar::sub-line:vertical {
    height: 0;
}

/* ── ToolTips ── */
QToolTip {
    background-color: #001D39;
    color: #BDD8E9;
    border: 1px solid #7BBDE8;
    padding: 5px;
    border-radius: 4px;
    font-size: 13px;
}

/* ── Message boxes ── */
QMessageBox {
    background: #001D39;
}
QMessageBox QLabel {
    color: #BDD8E9;
}
QMessageBox QPushButton {
    background: #0A4174;
    color: #BDD8E9;
    border: 1px solid rgba(123, 189, 232, 0.25);
    border-radius: 8px;
    padding: 6px 20px;
    min-width: 80px;
}
QMessageBox QPushButton:hover {
    background: #49769F;
    color: white;
}
"""


# ──────────────────────────────────────────────
#  Security helpers  (giữ nguyên như bản cũ)
# ──────────────────────────────────────────────
def get_hardware_id():
    return str(uuid.getnode())

def obscure_data(data_str, salt):
    if not data_str: return ""
    if not salt: salt = "default_salt"
    salt_bytes = salt.encode('utf-8')
    data_bytes = data_str.encode('utf-8')
    obscured = bytearray()
    for i, b in enumerate(data_bytes):
        obscured.append(b ^ salt_bytes[i % len(salt_bytes)])
    return base64.b64encode(obscured).decode('utf-8')

def unobscure_data(obscured_str, salt):
    if not obscured_str: return ""
    if not salt: salt = "default_salt"
    try:
        salt_bytes = salt.encode('utf-8')
        data_bytes = base64.b64decode(obscured_str.encode('utf-8'))
        out = bytearray()
        for i, b in enumerate(data_bytes):
            out.append(b ^ salt_bytes[i % len(salt_bytes)])
        return out.decode('utf-8')
    except:
        return ""


# ──────────────────────────────────────────────
#  Worker Thread  (chạy pipeline OCR riêng)
# ──────────────────────────────────────────────
class WorkerSignals(QObject):
    log        = pyqtSignal(str)           # normal log line
    log_ow     = pyqtSignal(str)           # overwrite last line
    progress   = pyqtSignal(int, int)      # current, total
    status_txt = pyqtSignal(str, str)      # text, style_name
    finished   = pyqtSignal(str)           # output path or ""
    error      = pyqtSignal(str, str)      # title, message


class OCRWorker(QThread):
    def __init__(self, input_dir: str, stop_event: threading.Event,
                 api_key: str, signals: WorkerSignals):
        super().__init__()
        self.input_dir  = input_dir
        self.stop_event = stop_event
        self.api_key    = api_key
        self.s          = signals

    # Thin wrappers so callbacks work identically to CTk version
    def _log(self, msg):
        self.s.log.emit(msg)

    def run(self):
        try:
            self._run_pipeline()
        except Exception as e:
            self.s.error.emit("Lỗi Ứng Dụng Khẩn", f"Đã xảy ra lỗi nặng:\n{e}")
        finally:
            self.s.finished.emit(self._output_path)

    def _run_pipeline(self):
        self._output_path = ""

        root_dir  = self.input_dir.rstrip(os.sep).rstrip('/')
        done_dir  = os.path.join(os.path.dirname(root_dir), "DONE")

        valid_ext = ('.png', '.jpg', '.jpeg')
        files = [f for f in os.listdir(root_dir) if f.lower().endswith(valid_ext)]

        if not files:
            self._log("⚠️ Không tìm thấy ảnh nào trong thư mục đã chọn.")
            self.s.status_txt.emit("Không có ảnh!", "error")
            return

        os.makedirs(done_dir, exist_ok=True)
        self._log(f"📁 Thư mục đầu vào: {root_dir}")
        self._log(f"📦 Đã phát hiện {len(files)} hình ảnh chờ xử lý.")

        total = len(files)
        all_results = []

        for i, filename in enumerate(files, 1):
            if self.stop_event.is_set():
                break

            source_path   = os.path.join(root_dir, filename)
            stem          = os.path.splitext(filename)[0]
            dest_img_path = os.path.join(done_dir, filename)
            dest_json     = os.path.join(done_dir, stem + ".json")
            processed_ok  = False

            self._log(f"⏳ [{i}/{total}] Đang OCR: {filename}")
            self.s.progress.emit(i - 1, total)
            self.s.status_txt.emit(f"Đang xử lý {i}/{total}...", "running")

            try:
                from data_manager import app_data
                from module_paddle_ocr import get_paddle_engine
                from module_flash_ocr import get_flash_structurer
                from module_pro_ocr import get_pro_ocr
                from module_calculator import get_calculator
                from image_processor import prepare_image
                from core_rate_limiter import EngineCancellationError

                if not app_data.is_loaded:
                    app_data.load_all()

                image = prepare_image(source_path)

                paddle_engine = get_paddle_engine()
                
                # Convert PIL Image to OpenCV BGR array for PaddleOCR
                import cv2
                import numpy as np
                paddle_input_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                
                raw_text, avg_conf = paddle_engine.extract_raw_text(
                    paddle_input_img, stop_event=self.stop_event,
                    status_callback=self._log
                )

                if avg_conf > ROUTING_CONF_THRESHOLD:
                    self._log("🔀 Phân luồng In (1A): Độ tin cậy cao → Flash Structurer")
                    flash_engine = get_flash_structurer(self.api_key, app_data)
                    json_rough = flash_engine.structure_text_to_json(
                        raw_text, avg_conf,
                        stop_event=self.stop_event, status_callback=self._log
                    )

                    # Safety fallback: dùng hard-case score để quyết định Pro Vision
                    raw_lines = [line for line in (raw_text or "").splitlines() if line.strip()]
                    raw_line_count = len(raw_lines)
                    invoice_type = str((json_rough.get("document_info", {}) or {}).get("invoice_type", "") or "").upper()
                    item_count = len(json_rough.get("items", []) or [])

                    hard_case_score = 0
                    if raw_line_count >= 9:
                        hard_case_score += 1
                    if avg_conf < 0.90:
                        hard_case_score += 1
                    if not invoice_type or invoice_type.startswith("HANDWRITTEN"):
                        hard_case_score += 1

                    if hard_case_score >= 2:
                        self._log(
                            "🔁 Hard-case score >= 2 "
                            f"(lines={raw_line_count}, conf={avg_conf:.1%}, type={invoice_type or 'UNKNOWN'}, items={item_count}) "
                            "→ fallback Pro Vision"
                        )
                        pro_engine = get_pro_ocr(self.api_key, app_data)
                        json_rough = pro_engine.extract_image_directly(
                            image, stop_event=self.stop_event, status_callback=self._log
                        )
                else:
                    if raw_text == "":
                        self._log("🔀 Phân luồng Ảnh (1B): Không đọc được chữ → AI Pro Vision")
                    else:
                        self._log(f"🔀 Phân luồng Viết tay (1B): Tin cậy {avg_conf:.1%} → AI Pro")
                    pro_engine = get_pro_ocr(self.api_key, app_data)
                    json_rough = pro_engine.extract_image_directly(
                        image, stop_event=self.stop_event, status_callback=self._log
                    )

                calc_engine  = get_calculator(self.api_key, app_data)
                invoice_json = calc_engine.run_calculation(
                    json_rough, stop_event=self.stop_event, status_callback=self._log
                )

                with open(dest_json, "w", encoding="utf-8") as jf:
                    json.dump(invoice_json, jf, ensure_ascii=False, indent=2)

                invoice_json["_source_filename"] = filename  # Tag for image preview; after dump — stays in-memory only
                all_results.append(invoice_json)
                confidence = invoice_json.get("document_info", {}).get("confidence_score", 1.0)
                supplier   = invoice_json.get("supplier_info", {}).get("supplier_name_code", "?")
                conf_str   = f"{confidence:.0%}" if isinstance(confidence, (float, int)) else str(confidence)
                self._log(f"✅ Xong: {filename} | NCC: {supplier} | Confidence: {conf_str}")
                processed_ok = True

            except Exception as e:
                err_name = type(e).__name__
                # Check cancellation by name to avoid import issues
                if err_name == "EngineCancellationError":
                    self._log("🛑 Đã dừng theo lệnh người dùng.")
                    break
                if os.path.exists(dest_json):
                    try:
                        os.remove(dest_json)
                    except OSError:
                        pass
                self._log(f"❌ Lỗi [{filename}]: {str(e).splitlines()[0] or 'Lỗi không xác định'}")

            if processed_ok:
                try:
                    # Save the enhanced PIL image to DONE folder (overwrites if re-run)
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in (".jpg", ".jpeg"):
                        image.save(dest_img_path, quality=95)
                    else:
                        image.save(dest_img_path)
                    if os.path.normpath(source_path) != os.path.normpath(dest_img_path):
                        os.remove(source_path)
                except Exception as mv_err:
                    self._log(f"⚠️ Không lưu được ảnh xử lý '{filename}': {mv_err}")
            else:
                self._log(f"↩️ Giữ lại ảnh lỗi trong thư mục đầu vào: {filename}")

            self.s.progress.emit(i, total)

            # Delay between images
            if i < total and not self.stop_event.is_set():
                delay = 1
                self._log(f"⏸ Chờ {delay}s trước khi tiếp tục...")
                for remaining in range(delay, 0, -1):
                    if self.stop_event.is_set():
                        break
                    self.s.status_txt.emit(f"Nghỉ {remaining}s...", "running")
                    time.sleep(1)

        # --- END OF LOOP ---
        # Write Excel (Only once at the end)
        output_path = ""
        if all_results:
            self._log(f"📊 Đang ghi {len(all_results)} hóa đơn vào Excel...")
            try:
                from core_excel_mapper import append_invoices_to_excel
                from data_manager import app_data
                output_raw = append_invoices_to_excel(
                    all_results, data_store=app_data, api_key=self.api_key,
                    output_dir=done_dir,
                    status_callback=self._log
                )
                # Xử lý trường hợp trả về nhiều file
                output_list = output_raw.split('|')
                for f_path in output_list:
                    self._log(f"✅ File kết quả: {os.path.basename(f_path)}")
                
                output_path = output_raw
            except PermissionError as pe:
                self.s.error.emit("Lỗi File Excel", str(pe))
                return
            except FileNotFoundError as fnf:
                self.s.error.emit("Thiếu File Mẫu", str(fnf))
                return
        else:
            if not self.stop_event.is_set():
                self._log("⚠️ Không có hóa đơn nào được xử lý thành công.")

        if output_path:
            self._log("🎉 Hoàn tất! Đang mở giao diện rà soát kết quả...")
            self.s.status_txt.emit(f"Hoàn thành — {len(all_results)}/{total} hóa đơn", "done")
        else:
            if not self.stop_event.is_set():
                self.s.status_txt.emit("Đã dừng.", "idle")

        self._output_path = output_path


# ──────────────────────────────────────────────
#  Admin Login Dialog
# ──────────────────────────────────────────────
class AdminLoginDialog(QDialog):
    def __init__(self, parent, app_config: dict, is_boot_check=True):
        super().__init__(parent)
        self.app_config    = app_config
        self.is_boot_check = is_boot_check
        self.authenticated = False

        self.setWindowTitle("Khóa Bảo Mật Admin")
        self.setFixedSize(360, 200)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(30, 24, 30, 24)

        lbl = QLabel("🔐  Nhập mật khẩu Quản trị viên")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size:16px; font-weight:700; color:#BDD8E9;")
        layout.addWidget(lbl)

        self.entry = QLineEdit()
        self.entry.setEchoMode(QLineEdit.Password)
        self.entry.setPlaceholderText("Mật khẩu...")
        self.entry.returnPressed.connect(self._verify)
        layout.addWidget(self.entry)

        btn = QPushButton("🔓  Mở khóa Setting")
        btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0A4174, stop:1 #49769F);
                color: white; border: 1px solid rgba(123,189,232,0.3);
                border-radius: 10px; padding: 10px;
                font-size: 16px; font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #49769F, stop:1 #7BBDE8);
                color: #001D39;
            }
        """)
        btn.clicked.connect(self._verify)
        layout.addWidget(btn)

    def _verify(self):
        true_pass = self.app_config.get("admin_password") or ADMIN_PASSWORD
        if self.entry.text() == true_pass:
            self.authenticated = True
            self.accept()
        else:
            QMessageBox.critical(self, "Sai Mật khẩu", "Bạn không có quyền truy cập!")
            self.entry.clear()


# ──────────────────────────────────────────────
#  Admin Config Dialog
# ──────────────────────────────────────────────
class AdminConfigDialog(QDialog):
    config_saved = pyqtSignal(dict)   # emits new config dict

    def __init__(self, parent, app_config: dict):
        super().__init__(parent)
        self.app_config = app_config
        self.setWindowTitle("Thiết lập Hệ thống & AI Models")
        self.setMinimumWidth(600)
        self.setModal(True)
        self._build_ui()
        self._apply_default_dialog_size()

    def _build_ui(self):
        main_v_layout = QVBoxLayout(self)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setMinimumHeight(1)
        self.scroll_area = scroll
        
        container = QWidget()
        self.scroll_container = container
        layout = QVBoxLayout(container)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 24, 30, 24)

        # Title
        title = QLabel("⚙️  CẤU HÌNH API KEY (GEMINI)")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:17px; font-weight:800; color:#BDD8E9;")
        layout.addWidget(title)

        # HWID
        hwid_lbl = QLabel(f"Mã Máy Hiện Tại:  {get_hardware_id()}")
        hwid_lbl.setAlignment(Qt.AlignCenter)
        hwid_lbl.setStyleSheet("font-size:13px; color:#7BBDE8;")
        layout.addWidget(hwid_lbl)

        # API Key
        layout.addWidget(QLabel("Gemini API Key:"))
        self.entry_api = QLineEdit()
        self.entry_api.setPlaceholderText("Gắn Gemini API Key vào đây...")
        current_api = self.app_config.get("api_key", "")
        if current_api:
            self.entry_api.setText(current_api)
        layout.addWidget(self.entry_api)

        # New password
        layout.addWidget(QLabel("Đổi mật khẩu Admin (để trống = giữ nguyên):"))
        self.entry_pass = QLineEdit()
        self.entry_pass.setEchoMode(QLineEdit.Password)
        self.entry_pass.setPlaceholderText("Nhập mật khẩu mới...")
        layout.addWidget(self.entry_pass)

        # --- AI MODELS SECTION ---
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background-color: rgba(123, 189, 232, 0.2);")
        layout.addWidget(div)

        title_models = QLabel("🤖  CẤU HÌNH AI MODELS (ALIAS)")
        title_models.setAlignment(Qt.AlignCenter)
        title_models.setStyleSheet("font-size:16px; font-weight:800; color:#BDD8E9; margin-top:10px;")
        layout.addWidget(title_models)

        # Helper to list models
        self.btn_list_models = QPushButton("🔍  Dynamic Model Discovery (Lấy danh sách mới nhất)")
        self.btn_list_models.setStyleSheet("background: #0A4174; color: #7BBDE8; font-size:12px;")
        self.btn_list_models.clicked.connect(self._list_models_from_api)
        layout.addWidget(self.btn_list_models)

        # Model Grid
        grid = QGridLayout()
        grid.setSpacing(10)
        
        from data_manager import app_data
        app_data.load_config() # Đảm bảo load config mới nhất
        m = app_data.models

        # Light Primary
        grid.addWidget(QLabel("Model Nhẹ (Primary):"), 0, 0)
        self.cb_light_p = QComboBox()
        self.cb_light_p.setEditable(True)
        self.cb_light_p.addItem(m.get("light_primary"))
        grid.addWidget(self.cb_light_p, 0, 1)

        # Light Fallback
        grid.addWidget(QLabel("Model Nhẹ (Fallback):"), 1, 0)
        self.cb_light_f = QComboBox()
        self.cb_light_f.setEditable(True)
        self.cb_light_f.addItem(m.get("light_fallback"))
        grid.addWidget(self.cb_light_f, 1, 1)

        # Pro Primary
        grid.addWidget(QLabel("Model Mạnh (Primary):"), 2, 0)
        self.cb_pro_p = QComboBox()
        self.cb_pro_p.setEditable(True)
        self.cb_pro_p.addItem(m.get("pro_primary"))
        grid.addWidget(self.cb_pro_p, 2, 1)

        # Pro Fallback
        grid.addWidget(QLabel("Model Mạnh (Fallback):"), 3, 0)
        self.cb_pro_f = QComboBox()
        self.cb_pro_f.setEditable(True)
        self.cb_pro_f.addItem(m.get("pro_fallback"))
        grid.addWidget(self.cb_pro_f, 3, 1)

        layout.addLayout(grid)
        
        msg_hint = QLabel("💡 Chiến lược: [Nhẹ] Dùng Flash-Lite 3.1 → 2.5 Flash | [Mạnh] Dùng Flash 3.1 → 2.5 Pro.\nMinimal Thinking tự động bật cho các model đời mới (2.0+).")
        msg_hint.setWordWrap(True)
        msg_hint.setStyleSheet("color: #49769F; font-size: 12px; font-style: italic; line-height: 1.4;")
        layout.addWidget(msg_hint)

        div_ocr = QFrame()
        div_ocr.setFrameShape(QFrame.HLine)
        div_ocr.setStyleSheet("background-color: rgba(123, 189, 232, 0.2);")
        layout.addWidget(div_ocr)

        title_ocr = QLabel("OCR Cục bộ (Tốc độ / Độ ổn định)")
        title_ocr.setAlignment(Qt.AlignCenter)
        title_ocr.setStyleSheet("font-size:16px; font-weight:800; color:#BDD8E9; margin-top:10px;")
        layout.addWidget(title_ocr)

        grid_ocr = QGridLayout()
        grid_ocr.setSpacing(10)
        grid_ocr.addWidget(QLabel("Chế độ chạy OCR:"), 0, 0)
        self.cb_ocr_mode = QComboBox()
        self.cb_ocr_mode.addItem("Ổn định (khuyến nghị)", "stable")
        self.cb_ocr_mode.addItem("CPU nhanh", "cpu_fast")
        self.cb_ocr_mode.addItem("GPU", "gpu")
        current_ocr_mode = getattr(app_data, "ocr_mode", "stable")
        current_index = self.cb_ocr_mode.findData(current_ocr_mode)
        self.cb_ocr_mode.setCurrentIndex(current_index if current_index >= 0 else 0)
        grid_ocr.addWidget(self.cb_ocr_mode, 0, 1)
        layout.addLayout(grid_ocr)

        msg_ocr_hint = QLabel(
            "Ổn định: an toàn nhất, hợp cho đa số máy. "
            "CPU nhanh: có thể nhanh hơn nhưng kén máy hơn. "
            "GPU: nhanh nhất nếu máy có card và driver phù hợp; nếu thiếu, hệ thống sẽ tự quay về ổn định."
        )
        msg_ocr_hint.setWordWrap(True)
        msg_ocr_hint.setStyleSheet("color: #49769F; font-size: 12px; font-style: italic; line-height: 1.4;")
        layout.addWidget(msg_ocr_hint)

        scroll.setWidget(container)
        main_v_layout.addWidget(scroll)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(30, 8, 30, 24)

        # Save button
        self.btn_save = QPushButton("💾  Lưu Cấu Hình & Khóa Máy")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0A4174, stop:1 #49769F);
                color: white; border: 1px solid rgba(123,189,232,0.3);
                border-radius: 10px; padding: 10px;
                font-size: 16px; font-weight: 700;
                margin-top: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #49769F, stop:1 #7BBDE8);
                color: #001D39;
            }
        """)
        self.btn_save.clicked.connect(self._save)
        footer_layout.addWidget(self.btn_save)
        main_v_layout.addLayout(footer_layout)

    def _apply_default_dialog_size(self):
        desired_width = 680
        desired_height = self.scroll_container.sizeHint().height() + self.btn_save.sizeHint().height() + 120
        self.resize(max(desired_width, self.minimumWidth()), max(desired_height, 860))

    def _list_models_from_api(self):
        api_key = self.entry_api.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập API Key trước khi quét model!")
            return
        
        self.btn_list_models.setText("⏳ Đang quét danh sách model...")
        self.btn_list_models.setEnabled(False)
        QApplication.processEvents()

        from data_manager import app_data
        model_names = app_data.list_available_models(api_key)
        
        if not model_names:
            QMessageBox.warning(self, "Lỗi", "Không lấy được danh sách model. Kiểm tra API Key.")
        else:
            for cb in [self.cb_light_p, self.cb_light_f, self.cb_pro_p, self.cb_pro_f]:
                current = cb.currentText()
                cb.clear()
                cb.addItems(model_names)
                cb.setCurrentText(current)
            QMessageBox.information(self, "Thành công", f"Đã tìm thấy {len(model_names)} models Gemini.")
            
        self.btn_list_models.setText("🔍  Dynamic Model Discovery (Lấy danh sách mới nhất)")
        self.btn_list_models.setEnabled(True)

    def _save(self):
        api_key  = self.entry_api.text().strip()
        new_pass = self.entry_pass.text().strip()

        if not api_key:
            QMessageBox.warning(self, "Thiếu dữ liệu", "Phải cung cấp API Key!")
            return

        old_pass     = self.app_config.get("admin_password") or ADMIN_PASSWORD
        final_pass   = new_pass if new_pass else old_pass
        hwid         = get_hardware_id()

        config_data = {
            "hardware_id":  hwid,
            "api_key":      api_key,
            "admin_password": final_pass,
            "ocr_mode":     self.cb_ocr_mode.currentData() or "stable",
            "models": {
                "light_primary":  self.cb_light_p.currentText().strip(),
                "light_fallback": self.cb_light_f.currentText().strip(),
                "pro_primary":    self.cb_pro_p.currentText().strip(),
                "pro_fallback":   self.cb_pro_f.currentText().strip(),
            }
        }
        
        file_data = {
            "hardware_id":  hwid,
            "api_key":      obscure_data(api_key, hwid),
            "admin_password": obscure_data(final_pass, STATIC_SALT),
            "ocr_mode":     config_data["ocr_mode"],
            "models": config_data["models"]
        }

        try:
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(file_data, f, indent=2)
            
            from data_manager import app_data
            app_data.models.update(config_data["models"])
            app_data.ocr_mode = config_data["ocr_mode"]
            
            QMessageBox.information(self, "Thành công",
                "Đã lưu API Key, Mật khẩu, AI Models và chế độ Local OCR!")
            self.config_saved.emit(config_data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể lưu file config:\n{e}")


# ──────────────────────────────────────────────
#  Main Window
# ──────────────────────────────────────────────
class LighthouseOCRApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_config  = {}
        self.is_running  = False
        self._stop_event = threading.Event()
        self._worker     = None
        self._worker_signals = None
        self._last_validation_signature = None
        
        # Animation state for background
        self._bg_timer = QTimer(self)
        self._bg_timer.timeout.connect(self._animate_background)
        self._bg_angle = 0
        self.setAutoFillBackground(True) # Required for QPalette background
        self._bg_timer.start(60) # ~16fps is enough for smooth motion

        self.setWindowTitle("Lighthouse OCR — Nhập Hàng")
        self._set_logo_icon()
        
        # --- Responsive Sizing Strategy ---
        screen = QApplication.primaryScreen().availableGeometry()
        screen_h = screen.height()
        # Target height: optimized for Full HD (1080p) to avoid scrolling
        target_h = min(int(screen_h * 0.95), 980) 
        target_w = 540 # Expanded width to fit full title
        
        self.setMinimumSize(450, 400) 
        self.resize(target_w, target_h)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # Scroll Area for responsiveness
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        self._root_layout.addWidget(self.scroll_area)

        # Security check before showing main UI
        QTimer.singleShot(200, self._security_check)

    def _animate_background(self):
        # Tối ưu: Sử dụng QPalette thay vì setStyleSheet để tránh re-parsing CSS liên tục gây lag UI
        self._bg_angle = (self._bg_angle + 0.4) % 360
        rad = math.radians(self._bg_angle)
        
        # Tính toán tọa độ gradient (ObjectBoundingMode: 0.0 -> 1.0)
        x1 = 0.5 - 0.5 * math.cos(rad)
        y1 = 0.5 - 0.5 * math.sin(rad)
        x2 = 0.5 + 0.5 * math.cos(rad)
        y2 = 0.5 + 0.5 * math.sin(rad)
        
        from PyQt5.QtGui import QLinearGradient, QBrush
        from PyQt5.QtCore import QPointF
        
        gradient = QLinearGradient(QPointF(x1, y1), QPointF(x2, y2))
        gradient.setCoordinateMode(QLinearGradient.ObjectBoundingMode)
        gradient.setColorAt(0, QColor("#001D39"))
        gradient.setColorAt(0.6, QColor("#0A4174"))
        gradient.setColorAt(1, QColor("#2E4057"))
        
        palette = self.palette()
        palette.setBrush(QPalette.Window, QBrush(gradient))
        self.setPalette(palette)

    # ── Security ──────────────────────────────
    def _security_check(self):
        hwid_current = get_hardware_id()
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)

        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    raw = json.load(f)
                hwid_saved = raw.get("hardware_id", "")
                # API Key dùng mã máy làm salt (bảo mật cao)
                # Password dùng STATIC_SALT (để có thể mang sang máy khác vẫn gõ được)
                self.app_config = {
                    "hardware_id":    hwid_saved,
                    "api_key":        unobscure_data(raw.get("api_key", ""), hwid_saved),
                    "admin_password": unobscure_data(raw.get("admin_password", ""), STATIC_SALT),
                }
                # Load models config if exists
                from data_manager import app_data
                app_data.load_config()
            except:
                self.app_config = {}

        hwid_saved = self.app_config.get("hardware_id", "")
        global GEMINI_API_KEY
        GEMINI_API_KEY = self.app_config.get("api_key", "")

        # THÉP: Chế độ Setup lần đầu (Nếu chưa có HWID hoặc chưa có API Key)
        if not hwid_saved or not GEMINI_API_KEY:
            self._open_admin_config(is_boot=True)
            return

        if hwid_saved == hwid_current:
            self._load_main_ui()
        else:
            # Máy mới/đổi máy: Báo lỗi nhưng cho phép login admin để re-bind
            QMessageBox.critical(self, "CẢNH BÁO BẢO MẬT !!!",
                f"Phát hiện phần mềm bị sao chép sang máy khác!\n"
                f"Mã máy gốc:      {hwid_saved}\n"
                f"Mã máy hiện tại: {hwid_current}\n\n"
                "Hệ thống API đã bị tạm khóa. Vui lòng đăng nhập Admin để kích hoạt lại trên máy này."
            )
            self._do_admin_login(is_boot=True)

    def _warm_cache(self):
        try:
            from data_manager import app_data
            app_data.load_all()
        except Exception:
            pass

    def _do_admin_login(self, is_boot=False):
        dlg = AdminLoginDialog(self, self.app_config, is_boot_check=is_boot)
        if dlg.exec_() == QDialog.Accepted:
            self._open_admin_config(is_boot=is_boot)
        else:
            if is_boot:
                self.close()

    def _open_hard_case_browser_with_auth(self):
        from admin_dialogs import AdminLoginDialog as _LoginDlg
        login = _LoginDlg(self, self.app_config, is_boot_check=False)
        if login.exec_() != QDialog.Accepted:
            return
        try:
            from hard_case_browser import HardCaseBrowserDialog
            HardCaseBrowserDialog(self).exec_()
        except Exception as e:
            self._show_error("Lỗi", f"Không thể mở Hard Cases:\n{e}")

    def _open_admin_config(self, is_boot=False):
        dlg = AdminConfigDialog(self, self.app_config)
        dlg.config_saved.connect(self._on_config_saved)

        def _on_close_boot(result):
            if result == QDialog.Rejected and is_boot:
                self.close()

        dlg.finished.connect(_on_close_boot)

        if dlg.exec_() == QDialog.Accepted and is_boot:
            self._load_main_ui()

    def _on_config_saved(self, new_config: dict):
        self.app_config = new_config
        global GEMINI_API_KEY
        GEMINI_API_KEY = new_config.get("api_key", "")

    def _set_logo_icon(self):
        logo_path = get_asset_path("app_logo.png")
        icon_path = get_asset_path("icon.ico")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        elif os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    # ── Main UI ───────────────────────────────
    def _load_main_ui(self):
        # Build the full UI inside a container for the scroll area
        self.main_content = QWidget()
        self.main_content.setObjectName("main_content")
        layout = QVBoxLayout(self.main_content)
        layout.setContentsMargins(22, 14, 22, 12) # Further compact margins
        layout.setSpacing(8) # Further compact spacing
        
        self.scroll_area.setWidget(self.main_content)

        # ── Header: icon + status ──
        header_top = QHBoxLayout()
        header_top.setSpacing(10)

        logo_path = get_asset_path("app_logo.png")
        if os.path.exists(logo_path):
            icon_lbl = QLabel()
            pix = QPixmap(logo_path).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_lbl.setPixmap(pix)
        else:
            icon_lbl = QLabel("🔦")
            icon_lbl.setStyleSheet("font-size:34px;")
            
        header_top.addWidget(icon_lbl)
        header_top.addStretch()

        self.lbl_status = QLabel("● Sẵn sàng")
        self.lbl_status.setObjectName("lbl_status_idle")
        self.lbl_status.setStyleSheet(
            "color:#49769F; font-size:14px; font-weight:600;"
        )
        header_top.addWidget(self.lbl_status)

        layout.addLayout(header_top)

        # ── Header: title + subtitle (full width, wrapping) ──
        title = QLabel("HỆ THỐNG TRÍCH XUẤT HÓA ĐƠN")
        title.setObjectName("lbl_title")
        title.setWordWrap(True)
        layout.addWidget(title)

        subtitle = QLabel("Lighthouse OCR  ·  Nhập hàng tự động")
        subtitle.setObjectName("lbl_subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── Horizontal divider ──
        div = QFrame()
        div.setObjectName("h_divider")
        div.setFrameShape(QFrame.HLine)
        layout.addWidget(div)

        # ── Master data health ──
        master_group = QGroupBox("Tình trạng dữ liệu tham khảo")
        mg_layout = QVBoxLayout(master_group)
        mg_layout.setSpacing(2)
        mg_layout.setContentsMargins(10, 5, 10, 5)

        self.lbl_master_data_body = QLabel("Đang kiểm tra Master List...")
        self.lbl_master_data_body.setStyleSheet("color:#7BBDE8; font-size:13px; line-height:1.4; margin-bottom: 4px;")
        self.lbl_master_data_body.setWordWrap(True)
        mg_layout.addWidget(self.lbl_master_data_body)

        mg_buttons_layout = QHBoxLayout()
        mg_buttons_layout.setSpacing(12)
        
        self.btn_reload_master = QPushButton("🔄 Nạp lại Master")
        self.btn_reload_master.setObjectName("btn_open_output") 
        self.btn_reload_master.setToolTip("Nạp lại dữ liệu Master List từ file Excel (sau khi bạn đã chỉnh sửa)")
        self.btn_reload_master.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_reload_master.clicked.connect(self._reload_master_data)
        mg_buttons_layout.addWidget(self.btn_reload_master, 1)

        self.btn_edit_alias = QPushButton("📝 Từ điển tiếng lóng")
        self.btn_edit_alias.setObjectName("btn_open_output")
        self.btn_edit_alias.setToolTip("Xem và chỉnh sửa Từ điển Tiếng lóng (Alias Dictionary)")
        self.btn_edit_alias.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_edit_alias.clicked.connect(self._open_alias_editor)
        mg_buttons_layout.addWidget(self.btn_edit_alias, 1)

        mg_buttons_layout.addStretch()
        mg_layout.addLayout(mg_buttons_layout)

        layout.addWidget(master_group)

        # ── Input folder group (Horizontal row for browse) ──
        folder_group = QGroupBox("Thư mục chứa ảnh đầu vào")
        fg_layout = QHBoxLayout(folder_group)
        fg_layout.setSpacing(10)

        self.entry_folder = ClickableLineEdit()
        self.entry_folder.setReadOnly(True) 
        self.entry_folder.setPlaceholderText("Bấm vào đây để chọn thư mục...")
        self.entry_folder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        default_dir = os.path.join(get_root_dir(), "INPUT")
        if not os.path.exists(default_dir):
            try: os.makedirs(default_dir, exist_ok=True)
            except: pass
        self.entry_folder.setText(default_dir)
        self.entry_folder.clicked.connect(self._browse_folder)
        fg_layout.addWidget(self.entry_folder, 1)

        self.btn_open_result = QPushButton("📂  Open Result")
        self.btn_open_result.setObjectName("btn_open_output")
        self.btn_open_result.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_open_result.clicked.connect(self._open_output_folder)
        fg_layout.addWidget(self.btn_open_result, 1)

        layout.addWidget(folder_group)

        # ── Action buttons row ──
        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)

        self.btn_start = QPushButton("🚀  Scan")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self._start_processing)
        actions_row.addWidget(self.btn_start, 1) 

        self.btn_stop = QPushButton("⏹  Stop")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._request_stop)
        actions_row.addWidget(self.btn_stop, 1)

        layout.addLayout(actions_row)

        # ── Progress Section (Flat) ──
        progress_container = QWidget()
        pg_layout = QVBoxLayout(progress_container)
        pg_layout.setContentsMargins(0, 5, 0, 5)
        pg_layout.setSpacing(8)

        self.lbl_progress_text = QLabel("Sẵn sàng thực thi...")
        self.lbl_progress_text.setStyleSheet("color:#7BBDE8; font-size:13px; font-weight:600;")
        self.lbl_progress_text.setAlignment(Qt.AlignCenter)
        pg_layout.addWidget(self.lbl_progress_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        pg_layout.addWidget(self.progress_bar)

        layout.addWidget(progress_container)

        # ── Log group ──
        log_group = QGroupBox("Nhật ký hoạt động")
        log_layout = QVBoxLayout(log_group)
        log_layout.setSpacing(6)

        # Toolbar row
        log_toolbar = QHBoxLayout()
        log_toolbar.addStretch()

        btn_clear = QPushButton("🗑  Xóa log")
        btn_clear.setObjectName("btn_clear_log")
        btn_clear.clicked.connect(self._clear_log)
        log_toolbar.addWidget(btn_clear)

        log_layout.addLayout(log_toolbar)

        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setMinimumHeight(260) # Significantly reduced to fit Full HD (360 -> 260)
        self.text_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout.addWidget(self.text_log)

        layout.addWidget(log_group, stretch=1)

        # ── Footer row ──
        footer = QHBoxLayout()
        lbl_version = QLabel(f"Phiên bản: {APP_VERSION}")
        lbl_version.setStyleSheet("color:#6EA2B3; font-size:12px;")
        footer.addWidget(lbl_version)
        footer.addStretch()

        btn_settings = QPushButton("⚙️  Thiết lập Hệ thống  ▾")
        btn_settings.setObjectName("btn_settings")

        def _show_settings_menu():
            menu = QMenu(self)
            menu.setStyleSheet(
                "QMenu { background-color: #0A2740; color: #BDD8E9; border: 1px solid #49769F; }"
                "QMenu::item { padding: 8px 20px; }"
                "QMenu::item:selected { background-color: #0A4174; color: #ffffff; }"
            )
            act_cfg = menu.addAction("⚙️  Cấu hình hệ thống")
            menu.addSeparator()
            act_hc  = menu.addAction("🗂  Xem Hard Cases")
            chosen = menu.exec_(btn_settings.mapToGlobal(
                btn_settings.rect().topLeft()
            ))
            if chosen == act_cfg:
                self._do_admin_login(is_boot=False)
            elif chosen == act_hc:
                self._open_hard_case_browser_with_auth()

        btn_settings.clicked.connect(_show_settings_menu)
        footer.addWidget(btn_settings)

        layout.addLayout(footer)

        self._run_preflight_validation(show_dialog=False)
        QTimer.singleShot(100, self._check_ocr_env)

    def _check_ocr_env(self):
        python_exe = os.path.join(get_root_dir(), "env", "python.exe")
        if not os.path.exists(python_exe):
            QMessageBox.warning(
                self,
                "Chưa cài đặt môi trường OCR",
                "Không tìm thấy môi trường Python OCR tại:\n"
                "  env\\python.exe\n\n"
                "Hãy chạy file Setup_Moi_Truong.bat để cài đặt trước khi sử dụng tính năng OCR.\n"
                "Sau khi hoàn tất, khởi động lại ứng dụng."
            )

    def _set_master_data_status(self, warnings: list[str], has_critical: bool):
        if not warnings:
            self.lbl_master_data_body.setText("Đã kiểm tra thư mục Data structure. Master List sẵn sàng.")
            self.lbl_master_data_body.setStyleSheet("color:#7BBDE8; font-size:13px; line-height:1.4;")
            return

        accent = "#f87171" if has_critical else "#fbbf24"
        self.lbl_master_data_body.setText("\n".join(warnings))
        self.lbl_master_data_body.setStyleSheet(f"color:{accent}; font-size:13px; line-height:1.4;")

    def _reload_master_data(self):
        from data_manager import app_data
        try:
            self._set_status("Đang nạp lại Master List...", "#7BBDE8")
            self.lbl_master_data_body.setText("Đang nạp lại Master List...")
            self.lbl_master_data_body.setStyleSheet("color:#7BBDE8; font-size:13px; line-height:1.4;")
            
            QApplication.processEvents() # UI update
            
            app_data.load_all()
            self._run_preflight_validation(show_dialog=True)
            self._set_status("● Sẵn sàng", "#BDD8E9")
            self._append_log("🔄 Đã cập nhật lại Master List từ Excel.")
        except Exception as e:
            self._show_error("Lỗi", f"Không thể nạp lại Master List:\n{e}")

    def _open_alias_editor(self):
        try:
            from alias_dictionary_dialog import AliasDictionaryDialog
            from data_manager import app_data
            dlg = AliasDictionaryDialog(app_data, self)
            dlg.exec_()
        except Exception as e:
            self._show_error("Lỗi", f"Không thể mở trình chỉnh sửa Alias:\n{e}")

    def _run_preflight_validation(self, show_dialog: bool = False) -> bool:
        try:
            from data_manager import validate_data_files
            warnings = validate_data_files()
        except Exception as exc:
            warnings = [f"❌ LỖI KIỂM TRA DỮ LIỆU: {exc}"]

        has_critical = any(msg.startswith("❌") for msg in warnings)
        self._set_master_data_status(warnings, has_critical)

        if not warnings:
            if hasattr(self, "btn_start") and not self.is_running:
                self.btn_start.setEnabled(True)
            if hasattr(self, "lbl_status"):
                self._update_status_txt("Sẵn sàng", "idle")
            return True

        dialog_text = "\n".join(warnings)
        signature = tuple(warnings)

        if hasattr(self, "text_log") and signature != self._last_validation_signature:
            self._append_log("⚠️ Kiểm tra dữ liệu đầu vào phát hiện vấn đề:")
            for msg in warnings:
                self._append_log(msg)
            self._last_validation_signature = signature

        if hasattr(self, "btn_start") and not self.is_running:
            self.btn_start.setEnabled(not has_critical)

        if hasattr(self, "lbl_status"):
            style = "error" if has_critical else "idle"
            text = "Lỗi dữ liệu đầu vào" if has_critical else "Cảnh báo dữ liệu đầu vào"
            self._update_status_txt(text, style)

        if show_dialog:
            if has_critical:
                QMessageBox.critical(
                    self,
                    "Thiếu dữ liệu hệ thống",
                    "Không thể bắt đầu OCR vì dữ liệu master chưa hợp lệ.\n\n" + dialog_text,
                )
            else:
                QMessageBox.warning(
                    self,
                    "Cảnh báo dữ liệu hệ thống",
                    "Dữ liệu master vẫn cho phép chạy, nhưng cần kiểm tra lại.\n\n" + dialog_text,
                )

        return not has_critical

    # ── Folder browse ─────────────────────────
    def _browse_folder(self):
        start = self.entry_folder.text() or os.path.dirname(os.path.abspath(__file__))
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục chứa ảnh hóa đơn", start,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            self.entry_folder.setText(folder)

    def _open_output_folder(self):
        base_dir = self.entry_folder.text().strip()
        if not base_dir or not os.path.exists(base_dir):
            QMessageBox.warning(self, "Lỗi", "Thư mục đầu vào không hợp lệ.")
            return
            
        # Thư mục DONE nằm ngang hàng (sibling) với thư mục ảnh đầu vào
        root_dir = base_dir.rstrip(os.sep).rstrip('/')
        done_dir = os.path.join(os.path.dirname(root_dir), "DONE")
        
        if not os.path.exists(done_dir):
            try: os.makedirs(done_dir, exist_ok=True)
            except: pass
            
        try:
            os.startfile(done_dir)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể mở thư mục: {e}")

    # ── Log helpers ───────────────────────────
    def _append_log(self, msg: str):
        ts = time.strftime("[%H:%M:%S]")
        # Color-code by emoji prefix — ocean palette
        if msg.startswith("✅"):
            color = "#7BBDE8"  # sky blue – success
        elif msg.startswith("❌"):
            color = "#f87171"  # red – error
        elif msg.startswith("⚠️"):
            color = "#fbbf24"  # amber – warning
        elif msg.startswith("🎉"):
            color = "#BDD8E9"  # ice blue – celebration
        elif msg.startswith("📊") or msg.startswith("📁"):
            color = "#6EA2B3"  # light teal – info
        elif msg.startswith("🛑"):
            color = "#f97316"  # orange – stop
        elif msg.startswith("🔀"):
            color = "#4E8EA2"  # teal – routing
        elif msg.startswith("⏳"):
            color = "#49769F"  # steel – processing
        elif msg.startswith("🚀"):
            color = "#BDD8E9"  # ice blue – launch
        else:
            color = "#6EA2B3"  # default light teal

        html = (
            f'<span style="color:#49769F;">{ts} </span>'
            f'<span style="color:{color};">{msg}</span><br>'
        )
        self.text_log.moveCursor(QTextCursor.End)
        self.text_log.insertHtml(html)
        self.text_log.moveCursor(QTextCursor.End)

    def _clear_log(self):
        self.text_log.clear()

    # ── Processing ────────────────────────────
    def _start_processing(self):
        if self.is_running:
            return

        if not self._run_preflight_validation(show_dialog=True):
            return

        input_dir = self.entry_folder.text().strip()
        if not input_dir or not os.path.isdir(input_dir):
            QMessageBox.warning(self, "Lỗi đường dẫn",
                "Thư mục đầu vào không hợp lệ. Vui lòng chọn lại!")
            return

        self.is_running = True
        self._stop_event.clear()
        self.btn_start.setEnabled(False)
        self.btn_start.setText("ĐANG XỬ LÝ...")
        self.btn_stop.setEnabled(True)
        self.btn_stop.setText("⏹  DỪNG XỬ LÝ")
        self.btn_reload_master.setEnabled(False)  # Lock reload during scan
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(1)
        self._set_status("● Đang chạy...", "#7BBDE8")
        self.text_log.clear()
        self._append_log("🚀 Bắt đầu phiên OCR mới...")
        self._append_log(f"📁 Thư mục: {input_dir}")

        signals = WorkerSignals()
        signals.log.connect(self._append_log)
        signals.progress.connect(self._update_progress)
        signals.status_txt.connect(self._update_status_txt)
        signals.finished.connect(self._on_finished)
        signals.error.connect(self._show_error)
        self._worker_signals = signals

        self._worker = OCRWorker(
            input_dir=input_dir,
            stop_event=self._stop_event,
            api_key=GEMINI_API_KEY,
            signals=signals
        )
        self._worker.start()

    def _request_stop(self):
        self._stop_event.set()
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText("⏹  Đang dừng...")
        self._append_log("🛑 Yêu cầu dừng — sẽ dừng sau khi kết thúc ảnh hiện tại.")

    def _update_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.lbl_progress_text.setText(f"Đã xử lý: {current} / {total} ảnh")

    def _update_status_txt(self, text: str, style: str):
        colors = {
            "idle":    "#49769F",
            "running": "#7BBDE8",
            "done":    "#BDD8E9",
            "error":   "#f87171",
        }
        color = colors.get(style, "#49769F")
        self.lbl_status.setText(f"● {text}")
        self.lbl_status.setStyleSheet(f"color:{color}; font-size:12px; font-weight:600;")
        if style not in ("running",):
            self.lbl_progress_text.setText(text)

    def _set_status(self, text: str, color: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color:{color}; font-size:12px; font-weight:600;")

    def _on_finished(self, output_path: str):
        self.is_running = False
        self.btn_start.setEnabled(True)
        self.btn_start.setText("🚀  Scan")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText("⏹  DỪNG XỬ LÝ")
        self.btn_reload_master.setEnabled(True)  # Unlock reload after scan

        # Nhấp nháy cửa sổ khi chạy xong
        QApplication.alert(self)

        if output_path:
            self._set_status("● Hoàn thành!", "#BDD8E9")

            output_list = output_path.split('|')

            # Auto-pop PostProcessDialog để rà soát PNMH
            try:
                from post_process_dialog import PostProcessDialog
                from data_manager import app_data

                # Phân loại file PNMH và Chi phí từ output_list
                pnmh_file = None
                chiphi_file = None
                
                for p in output_list:
                    fname = os.path.basename(p)
                    if "Chi_Phi" in fname or "ChiPhi" in fname:
                        chiphi_file = p
                    elif "PNMH" in fname:
                        pnmh_file = p

                # Fallback nếu không có prefix chuẩn
                if not pnmh_file and output_list:
                    pnmh_file = output_list[0]

                if pnmh_file and os.path.exists(pnmh_file):
                    self._append_log("🖥️ Đang hiển thị giao diện rà soát dữ liệu...")
                    dlg = PostProcessDialog(
                        pnmh_path   = pnmh_file,
                        chiphi_path = chiphi_file,
                        app_data    = app_data,
                        parent      = self
                    )
                    res = dlg.exec_()
                    if res == QDialog.Rejected:
                        self._append_log("🚫 Đã đóng (Không lưu) — Xoá các file Excel tạm vừa tạo.")
                        try:
                            if pnmh_file and os.path.exists(pnmh_file): os.remove(pnmh_file)
                            if chiphi_file and os.path.exists(chiphi_file): os.remove(chiphi_file)
                            self._set_status("● Đã hủy lưu", "#f87171")
                        except Exception as e:
                            self._append_log(f"⚠️ Lỗi khi xoá file: {e}")
                    else:
                        self._append_log("✅ Đã lưu kết quả rà soát vào Excel.")
                        self._set_status("● Đã lưu", "#86efac")
                else:
                    self._append_log(f"⚠️ Không tìm thấy file PNMH để rà soát: {pnmh_file}")
            except Exception as e:
                self._append_log(f"❌ Lỗi khi mở giao diện rà soát: {e}")
                logging.error(f"[PostProcess] Error: {e}", exc_info=True)
        else:
            self._set_status("● Sẵn sàng", "#49769F")

    def _show_error(self, title: str, message: str):
        QMessageBox.critical(self, title, message)

    def closeEvent(self, event):
        if self.is_running:
            self._stop_event.set()
        event.accept()


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────
def main():
    # Enable HiDPI on Windows
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")       # consistent cross-platform base
    app.setStyleSheet(APP_STYLE)

    window = LighthouseOCRApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
