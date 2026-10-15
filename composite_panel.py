"""composite_panel.py - the 'Composite filter' tab: a list of conditions joined by
AND / OR, each optionally negated with NOT. It only collects and validates the
conditions; movies_tab.py runs them (see composite.py for the logic)."""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from composite import describe
from filters import NUMERIC_OPERATORS, TEXT_OPERATORS, parse_value
from searching import SEARCH_ALGORITHMS, search_label

MAX_CONDITIONS = 5


class ConditionRow(QWidget):
    """One line:  [Where / AND-OR]  [NOT]  [column]  [operator]  [value]  [value 2]  [x]"""
    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)

    def __init__(self, columns):
        super().__init__()
        self.kinds = {key: kind for key, _, kind, _ in columns}
        self.where_label = QLabel("Where")
        self.where_label.setFixedWidth(62)
        self.connector = QComboBox()
        self.connector.addItems(["AND", "OR"])
        self.connector.setFixedWidth(62)
        self.not_box = QCheckBox("NOT")
        self.column_combo = QComboBox()
        for key, title, _, _ in columns:
            self.column_combo.addItem(title, key)
        self.op_combo = QComboBox()
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("value")
        self.value2_edit = QLineEdit()
        self.value2_edit.setPlaceholderText("and...")
        self.value2_edit.setVisible(False)
        self.remove_btn = QPushButton("x")
        self.remove_btn.setFixedWidth(30)
        self.remove_btn.setProperty("compact", True)
        self.remove_btn.setToolTip("Remove this condition")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in (self.where_label, self.connector, self.not_box, self.column_combo,
                       self.op_combo, self.value_edit, self.value2_edit, self.remove_btn):
            layout.addWidget(widget)
        layout.setStretchFactor(self.value_edit, 1)
        layout.setStretchFactor(self.value2_edit, 1)

        self.connector.currentIndexChanged.connect(self.changed)
        self.not_box.toggled.connect(self.changed)
        self.column_combo.currentIndexChanged.connect(self.update_operators)
        self.op_combo.currentIndexChanged.connect(self.on_operator_changed)
        self.value_edit.textChanged.connect(self.changed)
        self.value2_edit.textChanged.connect(self.changed)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        self.update_operators()

    def set_first(self, is_first):
        self.where_label.setVisible(is_first)
        self.connector.setVisible(not is_first)

    def update_operators(self):
        kind = self.kinds[self.column_combo.currentData()]
        operators = TEXT_OPERATORS if kind == "text" else NUMERIC_OPERATORS
        previous = self.op_combo.currentText()
        self.op_combo.blockSignals(True)
        self.op_combo.clear()
        self.op_combo.addItems(operators)
        if previous in operators:
            self.op_combo.setCurrentIndex(operators.index(previous))
        self.op_combo.blockSignals(False)
        self.on_operator_changed()

    def on_operator_changed(self):
        self.value2_edit.setVisible(self.op_combo.currentText() == "between")
        self.changed.emit()

    def preview_term(self):
        """The condition as typed, without checking it (used for the live preview)."""
        return {"connector": self.connector.currentText(), "negate": self.not_box.isChecked(),
                "column": self.column_combo.currentData(),
                "kind": self.kinds[self.column_combo.currentData()],
                "operator": self.op_combo.currentText(),
                "text": self.value_edit.text().strip(), "text2": self.value2_edit.text().strip()}

    def term(self):
        """The condition with typed values. Raises ValueError if the value is not valid."""
        term = self.preview_term()
        term["value"] = parse_value(term["kind"], term["text"])
        term["value2"] = parse_value(term["kind"], term["text2"]) if term["operator"] == "between" else None
        return term


class CompositePanel(QWidget):
    apply_requested = pyqtSignal(list, str)      # terms, algorithm for 'equals' conditions
    clear_requested = pyqtSignal()
    layout_changed = pyqtSignal()                # a condition row was added or removed

    def __init__(self, columns):
        super().__init__()
        self.columns = columns
        self.titles = {key: title for key, title, _, _ in columns}
        self.rows = []

        self.rows_layout = QVBoxLayout()
        self.add_btn = QPushButton("+ Add condition")
        self.algo_combo = QComboBox()
        for name in SEARCH_ALGORITHMS:
            self.algo_combo.addItem(search_label(name), name)
        self.algo_combo.setCurrentIndex(self.algo_combo.findData("Binary Search"))
        self.algo_combo.setToolTip("Used by 'equals' conditions. Interpolation search needs numbers, "
                                   "so text conditions use binary search instead.")
        self.apply_btn = QPushButton("Apply filter")
        self.apply_btn.setProperty("accent", True)
        self.clear_btn = QPushButton("Clear filter")
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.note = QLabel("AND is evaluated before OR (A OR B AND C means A OR (B AND C)). "
                           "NOT also matches movies with an empty value in that column.")
        self.note.setWordWrap(True)
        self.note.setProperty("muted", True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_btn)
        buttons.addWidget(QLabel("Algorithm for 'equals':"))
        buttons.addWidget(self.algo_combo, 1)
        buttons.addWidget(self.apply_btn)
        buttons.addWidget(self.clear_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(self.rows_layout)
        layout.addLayout(buttons)
        layout.addWidget(self.preview)
        layout.addWidget(self.note)

        self.add_btn.clicked.connect(self.add_row)
        self.apply_btn.clicked.connect(self.apply)
        self.clear_btn.clicked.connect(self.clear_requested)
        self.add_row()
        self.add_row()

    def add_row(self):
        if len(self.rows) >= MAX_CONDITIONS:
            return
        row = ConditionRow(self.columns)
        row.changed.connect(self.refresh_preview)
        row.remove_requested.connect(self.remove_row)
        self.rows_layout.addWidget(row)
        self.rows.append(row)
        self.relabel()

    def remove_row(self, row):
        if len(self.rows) <= 1:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self.relabel()

    def relabel(self):
        for i, row in enumerate(self.rows):
            row.set_first(i == 0)
            row.remove_btn.setEnabled(len(self.rows) > 1)
        self.add_btn.setEnabled(len(self.rows) < MAX_CONDITIONS)
        self.refresh_preview()
        self.layout_changed.emit()

    def refresh_preview(self):
        terms = [row.preview_term() for row in self.rows]
        self.preview.setText("<b>Expression:</b> " + describe(terms, self.titles))

    def apply(self):
        terms = []
        for number, row in enumerate(self.rows, start=1):
            try:
                terms.append(row.term())
            except ValueError as error:
                QMessageBox.warning(self, f"Check condition {number}", str(error))
                return
        self.apply_requested.emit(terms, self.algo_combo.currentData())
