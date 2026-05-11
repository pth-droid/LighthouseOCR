from PyQt5.QtWidgets import QStyledItemDelegate, QComboBox, QCompleter
from PyQt5.QtCore import Qt


# ── Delegate cho Combobox có thể gõ ──
class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        items_list = self.items(index) if callable(self.items) else self.items
        editor.addItems(items_list)
        editor.setEditable(True)
        # Tắt tự động điền để không bị nhảy chữ khi gõ
        editor.setInsertPolicy(QComboBox.NoInsert)

        # Thiết lập QCompleter để hỗ trợ gợi ý khi gõ
        completer = QCompleter(items_list, editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)  # Tìm kiếm chuỗi con
        completer.setCompletionMode(QCompleter.PopupCompletion)
        editor.setCompleter(completer)

        editor.setStyleSheet("""
            QComboBox { background:#0A2740; color:#BDD8E9; border:1px solid #49769F; padding:2px; }
            QComboBox QAbstractItemView { background:#0A2740; color:#BDD8E9; selection-background-color:#0A4174; }
        """)

        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        text = str(value) if value is not None else ""
        editor.setCurrentText(text)

        # Tự động chọn toàn bộ text.
        # QCompleter sẽ tự động hiện popup danh sách gợi ý khi người dùng bắt đầu gõ.
        line_edit = editor.lineEdit()
        if line_edit:
            line_edit.selectAll()

    def setModelData(self, editor, model, index):
        value = editor.currentText()
        model.setData(index, value, Qt.EditRole)
