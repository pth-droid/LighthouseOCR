import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QScrollArea

from main_app_qt import AdminConfigDialog


class AdminConfigDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_save_button_is_fixed_footer_not_inside_scroll_content(self):
        dialog = AdminConfigDialog(None, {"api_key": "demo", "admin_password": "admin"})
        self.assertTrue(hasattr(dialog, "btn_save"))
        self.assertIs(dialog.btn_save.parent(), dialog)

    def test_default_size_shows_full_form_without_immediate_scroll(self):
        dialog = AdminConfigDialog(None, {"api_key": "demo", "admin_password": "admin"})
        dialog.show()
        self.app.processEvents()

        scroll = dialog.findChild(QScrollArea)
        self.assertIsNotNone(scroll)
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)


if __name__ == "__main__":
    unittest.main()
