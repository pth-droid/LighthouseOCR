"""
admin_dialogs.py
AdminLoginDialog and AdminConfigDialog for the Lighthouse OCR application.
"""

import os
import json

from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox,
    QScrollArea, QFrame, QWidget, QComboBox,
)
from PyQt5.QtCore import Qt, pyqtSignal

from path_utils import get_asset_path
from security_helpers import get_hardware_id, obscure_data

# Duplicated here to avoid circular imports with main_app_qt
ADMIN_PASSWORD = "admin"
STATIC_SALT    = "lh_app_secure_v1"
CONFIG_FILE    = get_asset_path("lighthouse_config.json")


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
        self.resize(600, 780)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        main_v_layout = QVBoxLayout(self)
        main_v_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
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
        app_data.load_config()  # Đảm bảo load config mới nhất
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

        # Save button
        btn = QPushButton("💾  Lưu Cấu Hình & Khóa Máy")
        btn.setStyleSheet("""
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
        btn.clicked.connect(self._save)
        layout.addWidget(btn)

        scroll.setWidget(container)
        main_v_layout.addWidget(scroll)

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

        old_pass   = self.app_config.get("admin_password") or ADMIN_PASSWORD
        final_pass = new_pass if new_pass else old_pass
        hwid       = get_hardware_id()

        config_data = {
            "hardware_id":    hwid,
            "api_key":        api_key,
            "admin_password": final_pass,
            "models": {
                "light_primary":  self.cb_light_p.currentText().strip(),
                "light_fallback": self.cb_light_f.currentText().strip(),
                "pro_primary":    self.cb_pro_p.currentText().strip(),
                "pro_fallback":   self.cb_pro_f.currentText().strip(),
            }
        }

        file_data = {
            "hardware_id":    hwid,
            "api_key":        obscure_data(api_key, hwid),
            "admin_password": obscure_data(final_pass, STATIC_SALT),
            "models":         config_data["models"]
        }

        try:
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(file_data, f, indent=2)

            from data_manager import app_data
            app_data.models.update(config_data["models"])

            QMessageBox.information(self, "Thành công",
                "Đã lưu API Key, Mật khẩu và cấu hình AI Models!")
            self.config_saved.emit(config_data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể lưu file config:\n{e}")
