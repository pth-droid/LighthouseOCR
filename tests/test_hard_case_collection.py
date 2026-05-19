import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("."))


def _ensure_optional_import_stubs():
    if "PIL" not in sys.modules:
        pil_module = types.ModuleType("PIL")
        pil_module.Image = object
        sys.modules["PIL"] = pil_module

    if "PyQt5" not in sys.modules:
        class _Stub:
            def __init__(self, *args, **kwargs):
                pass

        class _MessageBoxStub(_Stub):
            @staticmethod
            def information(*args, **kwargs):
                return None

            @staticmethod
            def critical(*args, **kwargs):
                return None

        class _QtStub:
            def __getattr__(self, name):
                return 0

        qtwidgets = types.ModuleType("PyQt5.QtWidgets")
        for name in [
            "QDialog", "QVBoxLayout", "QHBoxLayout", "QTableWidget", "QTableWidgetItem",
            "QPushButton", "QLabel", "QTabWidget", "QWidget", "QCheckBox",
            "QHeaderView", "QAbstractItemView", "QStyledItemDelegate", "QComboBox", "QApplication",
            "QCompleter", "QSplitter", "QScrollArea", "QFrame", "QSizePolicy",
            "QListWidget", "QTextEdit"
        ]:
            setattr(qtwidgets, name, _Stub)
        qtwidgets.QMessageBox = _MessageBoxStub

        qtcore = types.ModuleType("PyQt5.QtCore")
        qtcore.Qt = _QtStub()
        qtcore.QEvent = _Stub
        qtcore.QPoint = _Stub
        qtcore.QSettings = _Stub
        qtcore.QTimer = _Stub
        qtcore.pyqtSignal = lambda *a, **k: object()

        qtgui = types.ModuleType("PyQt5.QtGui")
        qtgui.QColor = _Stub
        qtgui.QKeyEvent = _Stub
        qtgui.QTextCursor = _Stub
        qtgui.QPixmap = _Stub

        pyqt5 = types.ModuleType("PyQt5")
        sys.modules["PyQt5"] = pyqt5
        sys.modules["PyQt5.QtWidgets"] = qtwidgets
        sys.modules["PyQt5.QtCore"] = qtcore
        sys.modules["PyQt5.QtGui"] = qtgui


_ensure_optional_import_stubs()

from post_process_dialog import PostProcessDialog


class HardCaseCollectionTests(unittest.TestCase):
    def _build_fake_dialog(self, root_dir: str):
        dialog = type("FakeDialog", (), {})()
        dialog.pnmh_path = os.path.join(root_dir, "TEST_PNMH.xlsx")
        dialog.chiphi_path = os.path.join(root_dir, "TEST_ChiPhi.xlsx")
        open(dialog.pnmh_path, "a", encoding="utf-8").close()
        open(dialog.chiphi_path, "a", encoding="utf-8").close()

        dialog._pnmh_row_indices = [12]
        dialog._pnmh_original_by_ws_row = {12: {2: "CT001", 9: "before"}}
        dialog._pnmh_image_filenames = ["invoice.jpg"]
        dialog._chiphi_row_indices = []
        dialog._chiphi_original_by_ws_row = {}
        dialog._chiphi_image_filenames = []

        dialog._read_pnmh_row_from_table = lambda row: {2: "CT001", 9: "after"}
        dialog._read_chiphi_row_from_table = lambda row: {}
        return dialog

    def test_collect_hard_case_writes_report_and_copies_image(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dialog = self._build_fake_dialog(tmp_dir)
            src_image = os.path.join(tmp_dir, "invoice.jpg")
            with open(src_image, "wb") as f:
                f.write(b"image-bytes")

            info_calls = []
            critical_calls = []
            with patch("post_process_dialog.get_root_dir", return_value=tmp_dir), \
                patch("post_process_dialog.QMessageBox.information", side_effect=lambda *a, **k: info_calls.append((a, k))), \
                patch("post_process_dialog.QMessageBox.critical", side_effect=lambda *a, **k: critical_calls.append((a, k))):
                PostProcessDialog._collect_hard_case(dialog, "PNMH", 0)

            self.assertEqual(len(critical_calls), 0)
            self.assertEqual(len(info_calls), 1)

            hard_case_root = os.path.join(tmp_dir, "HARD CASE COLLECTED")
            folders = os.listdir(hard_case_root)
            self.assertEqual(len(folders), 1)
            case_dir = os.path.join(hard_case_root, folders[0])
            report_path = os.path.join(case_dir, "report.json")
            self.assertTrue(os.path.isfile(report_path))

            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["tab"], "PNMH")
            self.assertEqual(report["table_row_index_0_based"], 0)
            self.assertEqual(report["table_row_index_1_based"], 1)
            self.assertEqual(report["worksheet_row_index"], 12)
            self.assertEqual(report["before"]["9"], "before")
            self.assertEqual(report["after"]["9"], "after")
            self.assertEqual(len(report["image_paths"]), 1)
            copied_image = os.path.join(case_dir, report["image_paths"][0])
            self.assertTrue(os.path.isfile(copied_image))

    def test_collect_hard_case_shows_critical_on_copy_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dialog = self._build_fake_dialog(tmp_dir)
            src_image = os.path.join(tmp_dir, "invoice.jpg")
            with open(src_image, "wb") as f:
                f.write(b"image-bytes")

            info_calls = []
            critical_calls = []
            with patch("post_process_dialog.get_root_dir", return_value=tmp_dir), \
                patch("post_process_dialog.shutil.copy2", side_effect=OSError("copy failed")), \
                patch("post_process_dialog.QMessageBox.information", side_effect=lambda *a, **k: info_calls.append((a, k))), \
                patch("post_process_dialog.QMessageBox.critical", side_effect=lambda *a, **k: critical_calls.append((a, k))):
                PostProcessDialog._collect_hard_case(dialog, "PNMH", 0)

            self.assertEqual(len(info_calls), 0)
            self.assertEqual(len(critical_calls), 1)

            hard_case_root = os.path.join(tmp_dir, "HARD CASE COLLECTED")
            if os.path.isdir(hard_case_root):
                for folder in os.listdir(hard_case_root):
                    report_path = os.path.join(hard_case_root, folder, "report.json")
                    self.assertFalse(os.path.isfile(report_path))

    def test_collect_hard_case_rejects_row_state_drift(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dialog = self._build_fake_dialog(tmp_dir)
            dialog._pnmh_original_by_ws_row = {}

            critical_calls = []
            with patch("post_process_dialog.get_root_dir", return_value=tmp_dir), \
                patch("post_process_dialog.QMessageBox.critical", side_effect=lambda *a, **k: critical_calls.append((a, k))):
                PostProcessDialog._collect_hard_case(dialog, "PNMH", 0)

            self.assertEqual(len(critical_calls), 1)
            self.assertFalse(os.path.isdir(os.path.join(tmp_dir, "HARD CASE COLLECTED")))


if __name__ == "__main__":
    unittest.main()
