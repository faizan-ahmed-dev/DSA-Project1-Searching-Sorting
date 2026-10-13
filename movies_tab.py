"""movies_tab.py - the Movies tab: table + sort panel + results panel.

All the sorting logic lives in sorting.py. This file only
  * shows the records in a table,
  * lets the user choose column / algorithm / order / scope,
  * runs sort_records() in a background thread (bubble sort on 16k rows takes
    ~25 s, which would freeze the window if run in the main thread),
  * shows time, comparisons and swaps afterwards.
"""
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                             QPushButton, QTableView, QVBoxLayout, QWidget)

from sorting import ALGORITHMS, label, sort_records
from storage import DEFAULT_DB, MovieStore

# (database key, column title, kind, pixel width)   kind: "text", "int" or "float"
COLUMNS = [
    ("id", "ID", "int", 70),
    ("title", "Title", "text", 260),
    ("release_year", "Year", "int", 60),
    ("release_date", "Release Date", "text", 95),
    ("genres", "Genres", "text", 200),
    ("director", "Director", "text", 160),
    ("original_language", "Lang", "text", 50),
    ("runtime", "Runtime", "int", 70),
    ("vote_average", "Rating", "float", 65),
    ("vote_count", "Votes", "int", 70),
    ("popularity", "Popularity", "float", 85),
    ("budget", "Budget", "int", 100),
    ("revenue", "Revenue", "int", 110),
]
COLUMN_KIND = {key: kind for key, _, kind, _ in COLUMNS}
THOUSANDS = {"vote_count", "budget", "revenue"}     # shown as 1,234,567


class MovieTableModel(QAbstractTableModel):
    """Tells the QTableView what to show. It does not copy the data: it just
    points at the list of records it is given."""

    def __init__(self):
        super().__init__()
        self.records = []

    def set_records(self, records):
        self.beginResetModel()
        self.records = records
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        key, _, kind, _ = COLUMNS[index.column()]
        if role == Qt.DisplayRole:
            value = self.records[index.row()].get(key)
            if value is None or value == "":
                return ""
            if kind == "float":
                return f"{value:.3f}"
            if key in THOUSANDS:
                return f"{value:,}"
            return str(value)
        if role == Qt.TextAlignmentRole:
            align = Qt.AlignLeft if kind == "text" else Qt.AlignRight
            return int(align | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return COLUMNS[section][1]
        return str(section + 1)


class SortWorker(QThread):
    """Runs one sort in the background and reports the result."""
    done = pyqtSignal(object)      # the dict returned by sort_records()
    failed = pyqtSignal(str)       # error text (e.g. radix sort on a text column)

    def __init__(self, records, column, algorithm, descending):
        super().__init__()
        self.records = records
        self.column = column
        self.algorithm = algorithm
        self.descending = descending

    def run(self):
        try:
            self.done.emit(sort_records(self.records, self.column,
                                        self.algorithm, self.descending))
        except Exception as e:
            self.failed.emit(str(e))


class MoviesTab(QWidget):
    def __init__(self):
        super().__init__()
        self.all_records = []      # the full dataset
        self.filtered = []         # the rows currently shown (== all until filters exist)
        self.sort_worker = None
        self._sorting = False
        self._pending = None       # (column key, descending, scope_full) of the running sort
        self.last_sorted = None    # (column key, descending) of the last finished sort

        # ---------- sort panel ----------
        self.column_combo = QComboBox()
        self.algo_combo = QComboBox()
        self.order_combo = QComboBox()
        self.scope_combo = QComboBox()
        self.sort_btn = QPushButton("Sort")
        self.reload_btn = QPushButton("Reload data")
        self.algo_info = QLabel()
        self.algo_info.setStyleSheet("color: #444;")

        for key, title, _, _ in COLUMNS:
            self.column_combo.addItem(title, key)
        for name in ALGORITHMS:
            self.algo_combo.addItem(label(name), name)
        self.algo_combo.setCurrentIndex(self.algo_combo.findData("Merge Sort"))
        self.order_combo.addItems(["Ascending", "Descending"])
        self.scope_combo.addItems(["Full dataset", "Filtered results"])

        sort_box = QGroupBox("Sort")
        grid = QGridLayout(sort_box)
        grid.addWidget(QLabel("Column:"), 0, 0)
        grid.addWidget(self.column_combo, 0, 1)
        grid.addWidget(QLabel("Order:"), 0, 2)
        grid.addWidget(self.order_combo, 0, 3)
        grid.addWidget(QLabel("Scope:"), 0, 4)
        grid.addWidget(self.scope_combo, 0, 5)
        grid.addWidget(QLabel("Algorithm:"), 1, 0)
        grid.addWidget(self.algo_combo, 1, 1, 1, 3)
        grid.addWidget(self.sort_btn, 1, 4)
        grid.addWidget(self.reload_btn, 1, 5)
        grid.addWidget(self.algo_info, 2, 0, 1, 6)
        grid.setColumnStretch(1, 1)

        # ---------- table ----------
        self.model = MovieTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(24)
        for i, (_, _, _, width) in enumerate(COLUMNS):
            self.table.setColumnWidth(i, width)
        self.header = self.table.horizontalHeader()
        self.header.setSectionsClickable(True)
        self.header.setStretchLastSection(True)
        self.header.setSortIndicatorShown(False)

        # ---------- results panel ----------
        self.summary_label = QLabel("No sort run yet. Choose a column and algorithm, then press Sort "
                                    "(or click a column header).")
        self.time_label = QLabel("Time: -")
        self.comp_label = QLabel("Comparisons: -")
        self.swap_label = QLabel("Swaps: -")
        for lbl in (self.time_label, self.comp_label, self.swap_label):
            lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        result_box = QGroupBox("Last sort result")
        rv = QVBoxLayout(result_box)
        rv.addWidget(self.summary_label)
        rh = QHBoxLayout()
        for lbl in (self.time_label, self.comp_label, self.swap_label):
            rh.addWidget(lbl)
        rv.addLayout(rh)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)           # endless "busy" animation
        self.progress.setVisible(False)
        self.count_label = QLabel()
        self.hint_label = QLabel()
        self.hint_label.setStyleSheet("color: #b04000;")
        status = QHBoxLayout()
        status.addWidget(self.count_label)
        status.addWidget(self.hint_label, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(sort_box)
        layout.addLayout(status)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.progress)
        layout.addWidget(result_box)

        # ---------- signals ----------
        self.sort_btn.clicked.connect(self.start_sort)
        self.reload_btn.clicked.connect(self.load_data)
        self.header.sectionClicked.connect(self.on_header_clicked)
        self.column_combo.currentIndexChanged.connect(self.update_algorithm_availability)
        self.algo_combo.currentIndexChanged.connect(self.update_algo_info)

        self.update_algorithm_availability()
        self.update_algo_info()
        self.load_data()

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    def load_data(self):
        if self._sorting:
            return
        store = MovieStore()
        self.all_records = store.load_all()
        store.close()
        self.filtered = self.all_records
        self.model.set_records(self.filtered)
        self.last_sorted = None
        self.header.setSortIndicatorShown(False)
        self.hint_label.setText("" if self.all_records else
                                f"No movies found in {DEFAULT_DB} - run the scraper first, "
                                f"and make sure movies.db is next to the .py files.")
        self.update_counts()

    def refresh_hint(self):
        """Called when the user switches back to this tab: did the scraper add movies?"""
        if self._sorting:
            return
        store = MovieStore()
        n = store.count()
        store.close()
        if n != len(self.all_records):
            self.hint_label.setText(f"The database now has {n:,} movies - click 'Reload data'.")

    def update_counts(self):
        self.count_label.setText(f"Showing {len(self.filtered):,} of {len(self.all_records):,} movies")
        self.scope_combo.setItemText(1, f"Filtered results ({len(self.filtered):,} rows)")

    # ------------------------------------------------------------------
    # algorithm dropdown
    # ------------------------------------------------------------------
    def update_algorithm_availability(self):
        """Counting/radix/bucket sort need numbers (counting/radix: whole numbers),
        so grey them out for columns they cannot handle."""
        kind = COLUMN_KIND[self.column_combo.currentData()]
        model = self.algo_combo.model()
        for i in range(self.algo_combo.count()):
            name = self.algo_combo.itemData(i)
            info = ALGORITHMS[name]
            reason = ""
            if info["kind"] == "numeric":
                if kind == "text":
                    reason = f"{name} needs a numeric column"
                elif info["integers_only"] and kind == "float":
                    reason = f"{name} needs whole numbers; this column has decimals"
            model.item(i).setEnabled(reason == "")
            model.item(i).setToolTip(reason)
        if not model.item(self.algo_combo.currentIndex()).isEnabled():
            self.algo_combo.setCurrentIndex(self.algo_combo.findData("Merge Sort"))

    def update_algo_info(self):
        name = self.algo_combo.currentData()
        if name is None:
            return
        info = ALGORITHMS[name]
        self.algo_info.setText(
            f"{name}:  best {info['best']}  |  average {info['average']}  |  worst {info['worst']}"
            f"  |  extra space {info['space']}  |  {'STABLE' if info['stable'] else 'UNSTABLE'}")

    # ------------------------------------------------------------------
    # sorting
    # ------------------------------------------------------------------
    def on_header_clicked(self, section):
        """Clicking a column header sorts by that column with the chosen algorithm;
        clicking the same column again flips ascending/descending."""
        if self._sorting:
            return
        key = COLUMNS[section][0]
        descending = bool(self.last_sorted and self.last_sorted[0] == key and not self.last_sorted[1])
        self.column_combo.setCurrentIndex(self.column_combo.findData(key))
        self.order_combo.setCurrentIndex(1 if descending else 0)
        self.start_sort()

    def start_sort(self):
        if self._sorting:
            return
        column = self.column_combo.currentData()
        algorithm = self.algo_combo.currentData()
        descending = self.order_combo.currentIndex() == 1
        scope_full = self.scope_combo.currentIndex() == 0
        data = self.all_records if scope_full else self.filtered
        if not data:
            QMessageBox.information(self, "Nothing to sort", "There are no movies to sort yet.")
            return

        info = ALGORITHMS[algorithm]
        if info["average"] == "O(n²)" and len(data) > 5000:
            seconds = int(len(data) ** 2 * 1e-7) + 1
            answer = QMessageBox.question(
                self, "This may take a while",
                f"{algorithm} is O(n²). On {len(data):,} rows it can take roughly {seconds} seconds "
                f"(it cannot be cancelled once started).\n\nContinue?")
            if answer != QMessageBox.Yes:
                return

        self._pending = (column, descending, scope_full)
        self._set_busy(True, f"Sorting {len(data):,} rows with {algorithm}...")
        self.sort_worker = SortWorker(data, column, algorithm, descending)
        self.sort_worker.done.connect(self.on_sort_done)
        self.sort_worker.failed.connect(self.on_sort_failed)
        self.sort_worker.start()

    def on_sort_done(self, result):
        column, descending, scope_full = self._pending
        records = result["records"]
        if scope_full:
            self.all_records = records
            self.filtered = records        # no filters exist yet; later phases re-apply them here
        else:
            self.filtered = records
        self.model.set_records(self.filtered)
        self.last_sorted = (column, descending)

        col_index = self.column_combo.findData(column)
        self.header.setSortIndicator(col_index, Qt.DescendingOrder if descending else Qt.AscendingOrder)
        self.header.setSortIndicatorShown(True)
        self.table.scrollToTop()

        name = result["algorithm"]
        info = ALGORITHMS[name]
        self.summary_label.setText(
            f"{name} ({'stable' if info['stable'] else 'unstable'}, average {info['average']}) on "
            f"'{COLUMNS[col_index][1]}', {'descending' if descending else 'ascending'}, "
            f"{len(records):,} rows ({'full dataset' if scope_full else 'filtered results'})")
        self.time_label.setText(f"Time: {result['time_ms']:,.2f} ms")
        self.comp_label.setText(f"Comparisons: {result['comparisons']:,}")
        self.swap_label.setText(f"Swaps: {result['swaps']:,}")
        self.update_counts()
        self._set_busy(False)

    def on_sort_failed(self, message):
        self._set_busy(False)
        QMessageBox.warning(self, "Cannot sort with this algorithm", message)

    def _set_busy(self, busy, text=""):
        self._sorting = busy
        for widget in (self.column_combo, self.algo_combo, self.order_combo, self.scope_combo,
                       self.sort_btn, self.reload_btn):
            widget.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            self.hint_label.setText(text)
        else:
            self.hint_label.setText("")

    def is_busy(self):
        return self._sorting
