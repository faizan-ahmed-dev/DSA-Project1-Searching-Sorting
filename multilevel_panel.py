"""multilevel_panel.py - the 'Multi-level sort' tab: up to 3 columns, each with its own
order and algorithm. It only collects the choices; movies_tab.py runs the sort."""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QGridLayout, QLabel, QMessageBox, QPushButton, QWidget

from sorting import ALGORITHMS, label

LEVEL_NAMES = ["Level 1 (primary)", "Level 2 (then by)", "Level 3 (then by)"]


class MultiLevelPanel(QWidget):
    sort_requested = pyqtSignal(list)       # [(column key, algorithm name, descending), ...]

    def __init__(self, columns):
        super().__init__()
        self.kinds = {key: kind for key, _, kind, _ in columns}
        self._refreshing = False
        self.col_combos, self.order_combos, self.algo_combos = [], [], []

        grid = QGridLayout(self)
        for c, text in enumerate(["", "Column", "Order", "Algorithm"]):
            grid.addWidget(QLabel(f"<b>{text}</b>"), 0, c)
        for i, name in enumerate(LEVEL_NAMES):
            col = QComboBox()
            if i > 0:
                col.addItem("- none -", None)
            for key, title, _, _ in columns:
                col.addItem(title, key)
            order = QComboBox()
            order.addItems(["Ascending", "Descending"])
            algo = QComboBox()
            for algorithm in ALGORITHMS:
                algo.addItem(label(algorithm), algorithm)
            algo.setCurrentIndex(algo.findData("Merge Sort"))
            grid.addWidget(QLabel(name), i + 1, 0)
            grid.addWidget(col, i + 1, 1)
            grid.addWidget(order, i + 1, 2)
            grid.addWidget(algo, i + 1, 3)
            self.col_combos.append(col)
            self.order_combos.append(order)
            self.algo_combos.append(algo)
            col.currentIndexChanged.connect(self.refresh)
            algo.currentIndexChanged.connect(self.refresh)

        # sensible starting example: year ascending, then rating descending
        self.col_combos[0].setCurrentIndex(self.col_combos[0].findData("release_year"))
        self.col_combos[1].setCurrentIndex(self.col_combos[1].findData("vote_average"))
        self.order_combos[1].setCurrentIndex(1)

        self.run_btn = QPushButton("Multi-level sort")
        self.run_btn.setProperty("accent", True)
        self.run_btn.clicked.connect(self.run)
        grid.addWidget(self.run_btn, 1, 4)
        self.info = QLabel("The sort runs from the LAST level to the FIRST, one stable pass per level, so "
                           "the order of the later columns survives inside each group of the earlier ones. "
                           "That is why only the last level (sorted first) may use an unstable algorithm.")
        self.info.setWordWrap(True)
        self.info.setProperty("muted", True)
        grid.addWidget(self.info, 4, 0, 1, 5)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 2)
        self.refresh()

    def refresh(self):
        """Grey out algorithms a level cannot use (wrong column type, or unstable on a
        level that is not the last one)."""
        if self._refreshing:
            return
        self._refreshing = True
        active = [i for i in range(3) if self.col_combos[i].currentData() is not None]
        last = active[-1]
        for i in range(3):
            column = self.col_combos[i].currentData()
            is_active = column is not None
            self.order_combos[i].setEnabled(is_active)
            self.algo_combos[i].setEnabled(is_active)
            if not is_active:
                continue
            kind = self.kinds[column]
            combo = self.algo_combos[i]
            model = combo.model()
            for j in range(combo.count()):
                name = combo.itemData(j)
                info = ALGORITHMS[name]
                reason = ""
                if info["kind"] == "numeric":
                    if kind == "text":
                        reason = f"{name} needs a numeric column"
                    elif info["integers_only"] and kind == "float":
                        reason = f"{name} needs whole numbers; this column has decimals"
                if reason == "" and not info["stable"] and i != last:
                    reason = f"{name} is unstable: only the last level may use an unstable algorithm"
                model.item(j).setEnabled(reason == "")
                model.item(j).setToolTip(reason)
            if not model.item(combo.currentIndex()).isEnabled():
                combo.setCurrentIndex(combo.findData("Merge Sort"))
        self._refreshing = False

    def run(self):
        levels, seen = [], set()
        for i in range(3):
            column = self.col_combos[i].currentData()
            if column is None:
                continue
            if column in seen:
                QMessageBox.warning(self, "Check the levels", "Each level needs a different column.")
                return
            seen.add(column)
            levels.append((column, self.algo_combos[i].currentData(),
                           self.order_combos[i].currentIndex() == 1))
        self.sort_requested.emit(levels)
