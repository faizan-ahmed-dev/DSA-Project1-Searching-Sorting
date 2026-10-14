"""movies_tab.py - the Movies tab: table + sort panel + search panel + result panels.

All the algorithms live in sorting.py, searching.py and filters.py. This file only
  * shows the records in a table,
  * lets the user choose what to sort / search,
  * runs the work in a background thread (bubble sort on 16k rows takes ~25 s, which
    would freeze the window if it ran in the main thread),
  * shows time, comparisons, swaps and match counts afterwards.

TWO LISTS OF RECORDS
--------------------
all_records : the full dataset
filtered    : what the table shows. Equal to all_records until a search/filter is applied.
filter_ids  : None (no filter) or the set of movie ids that passed the last search.
              Whenever the full dataset is re-sorted, `filtered` is rebuilt from it, so an
              active filter stays active and in the new order.
"""
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
                             QTableView, QVBoxLayout, QWidget)

from benchmark_dialog import BenchmarkDialog
from filters import NUMERIC_OPERATORS, TEXT_OPERATORS, filter_records, parse_value
from searching import SEARCH_ALGORITHMS, search_label, search_records
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
COLUMN_TITLE = {key: title for key, title, _, _ in COLUMNS}
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


class TaskWorker(QThread):
    """Runs one function (a sort or a search) in the background and reports the result."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)       # error text (e.g. radix sort on a text column)

    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args

    def run(self):
        try:
            self.done.emit(self.func(*self.args))
        except Exception as e:
            self.failed.emit(str(e))


def _metric_label():
    lbl = QLabel()
    lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
    return lbl


class MoviesTab(QWidget):
    def __init__(self):
        super().__init__()
        self.all_records = []
        self.filtered = []
        self.filter_ids = None
        self.worker = None
        self._busy = False
        self._pending = None
        self.last_sorted = None    # (column key, descending) of the last finished sort

        # ================= sort panel =================
        self.column_combo = QComboBox()
        self.algo_combo = QComboBox()
        self.order_combo = QComboBox()
        self.scope_combo = QComboBox()
        self.sort_btn = QPushButton("Sort")
        self.benchmark_btn = QPushButton("Benchmark")
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
        grid.addWidget(self.benchmark_btn, 1, 5)
        grid.addWidget(self.algo_info, 2, 0, 1, 6)
        grid.setColumnStretch(1, 1)

        # ================= search / filter panel =================
        self.search_col_combo = QComboBox()
        self.op_combo = QComboBox()
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("value to search for")
        self.value2_edit = QLineEdit()
        self.value2_edit.setPlaceholderText("and...")
        self.value2_edit.setVisible(False)
        self.search_algo_combo = QComboBox()
        self.search_btn = QPushButton("Search")
        self.clear_btn = QPushButton("Clear search")
        self.search_info = QLabel()
        self.search_info.setStyleSheet("color: #444;")
        self.search_info.setWordWrap(True)

        for key, title, _, _ in COLUMNS:
            self.search_col_combo.addItem(title, key)
        for name in SEARCH_ALGORITHMS:
            self.search_algo_combo.addItem(search_label(name), name)
        self.search_algo_combo.setCurrentIndex(self.search_algo_combo.findData("Binary Search"))

        search_box = QGroupBox("Search / filter")
        sgrid = QGridLayout(search_box)
        sgrid.addWidget(QLabel("Column:"), 0, 0)
        sgrid.addWidget(self.search_col_combo, 0, 1)
        sgrid.addWidget(QLabel("Operator:"), 0, 2)
        sgrid.addWidget(self.op_combo, 0, 3)
        sgrid.addWidget(QLabel("Value:"), 0, 4)
        sgrid.addWidget(self.value_edit, 0, 5)
        sgrid.addWidget(self.value2_edit, 0, 6)
        sgrid.addWidget(QLabel("Algorithm:"), 1, 0)
        sgrid.addWidget(self.search_algo_combo, 1, 1, 1, 3)
        sgrid.addWidget(self.search_btn, 1, 4)
        sgrid.addWidget(self.clear_btn, 1, 5)
        sgrid.addWidget(self.search_info, 2, 0, 1, 7)
        sgrid.setColumnStretch(1, 1)
        sgrid.setColumnStretch(5, 1)

        # ================= table =================
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

        # ================= result panels =================
        self.summary_label = QLabel("No sort run yet. Choose a column and algorithm, then press Sort "
                                    "(or click a column header).")
        self.time_label = _metric_label()
        self.comp_label = _metric_label()
        self.swap_label = _metric_label()
        sort_result = QGroupBox("Last sort result")
        sv = QVBoxLayout(sort_result)
        self.summary_label.setWordWrap(True)
        sv.addWidget(self.summary_label)
        sh = QHBoxLayout()
        for lbl in (self.time_label, self.comp_label, self.swap_label):
            sh.addWidget(lbl)
        sv.addLayout(sh)

        self.search_summary = QLabel("No search run yet.")
        self.search_summary.setWordWrap(True)
        self.s_time_label = _metric_label()
        self.s_comp_label = _metric_label()
        self.s_match_label = _metric_label()
        search_result = QGroupBox("Last search result")
        rv = QVBoxLayout(search_result)
        rv.addWidget(self.search_summary)
        rh = QHBoxLayout()
        for lbl in (self.s_time_label, self.s_comp_label, self.s_match_label):
            rh.addWidget(lbl)
        rv.addLayout(rh)
        self.reset_result_labels()

        results = QHBoxLayout()
        results.addWidget(sort_result, 1)
        results.addWidget(search_result, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)           # endless "busy" animation
        self.progress.setVisible(False)
        self.count_label = QLabel()
        self.hint_label = QLabel()
        self.hint_label.setStyleSheet("color: #b04000;")
        self.reload_btn = QPushButton("Reload data")
        status = QHBoxLayout()
        status.addWidget(self.count_label)
        status.addWidget(self.hint_label, 1)
        status.addWidget(self.reload_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(sort_box)
        layout.addWidget(search_box)
        layout.addLayout(status)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.progress)
        layout.addLayout(results)

        # ================= signals =================
        self.sort_btn.clicked.connect(self.start_sort)
        self.benchmark_btn.clicked.connect(self.open_benchmark)
        self.reload_btn.clicked.connect(self.load_data)
        self.header.sectionClicked.connect(self.on_header_clicked)
        self.column_combo.currentIndexChanged.connect(self.update_algorithm_availability)
        self.algo_combo.currentIndexChanged.connect(self.update_algo_info)
        self.search_col_combo.currentIndexChanged.connect(self.update_search_controls)
        self.op_combo.currentIndexChanged.connect(self.update_search_info)
        self.search_algo_combo.currentIndexChanged.connect(self.update_search_info)
        self.search_btn.clicked.connect(self.start_search)
        self.value_edit.returnPressed.connect(self.start_search)
        self.value2_edit.returnPressed.connect(self.start_search)
        self.clear_btn.clicked.connect(self.clear_search)

        self.update_algorithm_availability()
        self.update_algo_info()
        self.update_search_controls()
        self.load_data()

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    def load_data(self):
        if self._busy:
            return
        store = MovieStore()
        self.all_records = store.load_all()
        store.close()
        self.filter_ids = None
        self.filtered = self.all_records
        self.model.set_records(self.filtered)
        self.last_sorted = None
        self.header.setSortIndicatorShown(False)
        self.reset_result_labels()
        self.hint_label.setText("" if self.all_records else
                                f"No movies found in {DEFAULT_DB} - run the scraper first, "
                                f"and make sure movies.db is next to the .py files.")
        self.update_counts()

    def refresh_hint(self):
        """Called when the user switches back to this tab: did the scraper add movies?"""
        if self._busy:
            return
        store = MovieStore()
        n = store.count()
        store.close()
        if n != len(self.all_records):
            self.hint_label.setText(f"The database now has {n:,} movies - click 'Reload data'.")

    def update_counts(self):
        filtered_note = "  (search active)" if self.filter_ids is not None else ""
        self.count_label.setText(f"Showing {len(self.filtered):,} of {len(self.all_records):,} "
                                 f"movies{filtered_note}")
        self.scope_combo.setItemText(1, f"Filtered results ({len(self.filtered):,} rows)")

    def reset_result_labels(self):
        self.time_label.setText("Time: -")
        self.comp_label.setText("Comparisons: -")
        self.swap_label.setText("Swaps: -")
        self.s_time_label.setText("Time: -")
        self.s_comp_label.setText("Comparisons: -")
        self.s_match_label.setText("Matches: -")
        self.search_summary.setText("No search run yet.")

    def _rebuild_filtered(self):
        """Re-apply the active filter to the (possibly re-sorted) full dataset."""
        if self.filter_ids is None:
            self.filtered = self.all_records
        else:
            self.filtered = [r for r in self.all_records if r["id"] in self.filter_ids]

    def _scope(self):
        """Which rows an action works on. With no active filter, both scopes are the same."""
        full = self.scope_combo.currentIndex() == 0 or self.filter_ids is None
        return full, (self.all_records if full else self.filtered)

    # ------------------------------------------------------------------
    # sort controls
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
    # search controls
    # ------------------------------------------------------------------
    def update_search_controls(self):
        """Operators depend on the column type; interpolation search needs a numeric column."""
        kind = COLUMN_KIND[self.search_col_combo.currentData()]
        operators = TEXT_OPERATORS if kind == "text" else NUMERIC_OPERATORS
        previous = self.op_combo.currentText()
        self.op_combo.blockSignals(True)
        self.op_combo.clear()
        self.op_combo.addItems(operators)
        if previous in operators:
            self.op_combo.setCurrentIndex(operators.index(previous))
        self.op_combo.blockSignals(False)

        model = self.search_algo_combo.model()
        for i in range(self.search_algo_combo.count()):
            name = self.search_algo_combo.itemData(i)
            reason = ""
            if SEARCH_ALGORITHMS[name]["numeric_only"] and kind == "text":
                reason = f"{name} needs a numeric column"
            model.item(i).setEnabled(reason == "")
            model.item(i).setToolTip(reason)
        if not model.item(self.search_algo_combo.currentIndex()).isEnabled():
            self.search_algo_combo.setCurrentIndex(self.search_algo_combo.findData("Binary Search"))
        self.update_search_info()

    def update_search_info(self):
        operator = self.op_combo.currentText()
        self.value2_edit.setVisible(operator == "between")
        is_equals = operator == "equals"
        self.search_algo_combo.setEnabled(is_equals and not self._busy)
        name = self.search_algo_combo.currentData()
        if not is_equals or name is None:
            self.search_info.setText("Filter operators (contains, starts with, greater than, ...) check "
                                     "every row once. Choose 'equals' to use a search algorithm.")
            return
        info = SEARCH_ALGORITHMS[name]
        sorted_note = ("needs SORTED data (if the column isn't sorted, a copy is sorted first with Merge Sort)"
                       if info["needs_sorted"] else "works on unsorted data")
        self.search_info.setText(f"{name}:  best {info['best']}  |  average {info['average']}  |  "
                                 f"worst {info['worst']}  |  {sorted_note}")

    # ------------------------------------------------------------------
    # sorting
    # ------------------------------------------------------------------
    def on_header_clicked(self, section):
        """Clicking a column header sorts by that column with the chosen algorithm;
        clicking the same column again flips ascending/descending."""
        if self._busy:
            return
        key = COLUMNS[section][0]
        descending = bool(self.last_sorted and self.last_sorted[0] == key and not self.last_sorted[1])
        self.column_combo.setCurrentIndex(self.column_combo.findData(key))
        self.order_combo.setCurrentIndex(1 if descending else 0)
        self.start_sort()

    def start_sort(self):
        if self._busy:
            return
        column = self.column_combo.currentData()
        algorithm = self.algo_combo.currentData()
        descending = self.order_combo.currentIndex() == 1
        scope_full, data = self._scope()
        if not data:
            QMessageBox.information(self, "Nothing to sort", "There are no movies to sort.")
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
        self.worker = TaskWorker(sort_records, data, column, algorithm, descending)
        self.worker.done.connect(self.on_sort_done)
        self.worker.failed.connect(self.on_task_failed)
        self.worker.start()

    def on_sort_done(self, result):
        column, descending, scope_full = self._pending
        records = result["records"]
        if scope_full:
            self.all_records = records
            self._rebuild_filtered()        # an active search stays active, in the new order
        else:
            self.filtered = records         # only the filtered rows were reordered
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

    # ------------------------------------------------------------------
    # benchmark
    # ------------------------------------------------------------------
    def open_benchmark(self):
        if self._busy:
            return
        _, data = self._scope()
        if not data:
            QMessageBox.information(self, "Nothing to benchmark", "There are no movies to sort.")
            return
        column = self.column_combo.currentData()
        dialog = BenchmarkDialog(data, column, COLUMN_TITLE[column],
                                 self.order_combo.currentIndex() == 1, self)
        dialog.exec_()

    # ------------------------------------------------------------------
    # searching
    # ------------------------------------------------------------------
    def start_search(self):
        if self._busy:
            return
        if not self.all_records:
            QMessageBox.information(self, "Nothing to search", "There are no movies to search.")
            return
        column = self.search_col_combo.currentData()
        kind = COLUMN_KIND[column]
        operator = self.op_combo.currentText()
        text = self.value_edit.text().strip()
        text2 = self.value2_edit.text().strip()
        try:
            value = parse_value(kind, text)
            value2 = parse_value(kind, text2) if operator == "between" else None
        except ValueError as e:
            QMessageBox.warning(self, "Check your value", str(e))
            return

        self._pending = (column, operator, text, text2)
        if operator == "equals":
            algorithm = self.search_algo_combo.currentData()
            self._set_busy(True, f"Searching with {algorithm}...")
            self.worker = TaskWorker(search_records, self.all_records, column, algorithm, value)
        else:
            self._set_busy(True, "Filtering...")
            self.worker = TaskWorker(filter_records, self.all_records, column, operator, value, value2)
        self.worker.done.connect(self.on_search_done)
        self.worker.failed.connect(self.on_task_failed)
        self.worker.start()

    def on_search_done(self, result):
        column, operator, text, text2 = self._pending
        self.filter_ids = {r["id"] for r in result["records"]}
        self._rebuild_filtered()
        self.model.set_records(self.filtered)
        self.table.scrollToTop()

        condition = f"{COLUMN_TITLE[column]} {operator} '{text}'"
        if operator == "between":
            condition = f"{COLUMN_TITLE[column]} between '{text}' and '{text2}'"
        summary = (f"{result['algorithm']}: {condition} - {result['matches']:,} "
                   f"match{'es' if result['matches'] != 1 else ''} among {result['rows']:,} rows with a value.")
        presort = result["presort"]
        if presort:
            summary += (f"  The column wasn't sorted, so a copy was first sorted with {presort['algorithm']} "
                        f"({presort['time_ms']:,.2f} ms, {presort['comparisons']:,} comparisons) - "
                        f"not included in the search time.")
        elif SEARCH_ALGORITHMS.get(result["algorithm"], {}).get("needs_sorted"):
            summary += "  The column was already sorted ascending, so no pre-sort was needed."
        self.search_summary.setText(summary)
        self.s_time_label.setText(f"Time: {result['time_ms']:,.3f} ms")
        self.s_comp_label.setText(f"Comparisons: {result['comparisons']:,}")
        self.s_match_label.setText(f"Matches: {result['matches']:,}")
        self.update_counts()
        self._set_busy(False)

    def clear_search(self):
        if self._busy:
            return
        self.filter_ids = None
        self._rebuild_filtered()
        self.model.set_records(self.filtered)
        self.value_edit.clear()
        self.value2_edit.clear()
        self.s_time_label.setText("Time: -")
        self.s_comp_label.setText("Comparisons: -")
        self.s_match_label.setText("Matches: -")
        self.search_summary.setText("Search cleared.")
        self.update_counts()

    # ------------------------------------------------------------------
    # shared
    # ------------------------------------------------------------------
    def on_task_failed(self, message):
        self._set_busy(False)
        QMessageBox.warning(self, "Cannot complete this action", message)

    def _set_busy(self, busy, text=""):
        self._busy = busy
        for widget in (self.column_combo, self.algo_combo, self.order_combo, self.scope_combo,
                       self.sort_btn, self.benchmark_btn, self.reload_btn, self.search_col_combo,
                       self.op_combo, self.value_edit, self.value2_edit, self.search_btn,
                       self.clear_btn):
            widget.setEnabled(not busy)
        self.search_algo_combo.setEnabled(not busy and self.op_combo.currentText() == "equals")
        self.progress.setVisible(busy)
        self.hint_label.setText(text if busy else "")

    def is_busy(self):
        return self._busy
