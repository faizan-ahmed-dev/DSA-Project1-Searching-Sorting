"""movies_tab.py - the Movies tab: table + tool tabs + result panels.

Tool tabs:  Sort | Multi-level sort | Search / filter | Composite filter (AND / OR / NOT)

All the algorithms live in sorting.py, searching.py, filters.py and composite.py. This
file only
  * shows the records in a table,
  * collects what the user chose,
  * runs the work in a background thread (bubble sort on 16k rows takes ~25 s, which
    would freeze the window if it ran in the main thread),
  * shows time, comparisons, swaps and match counts afterwards.

TWO LISTS OF RECORDS
--------------------
all_records : the full dataset
filtered    : what the table shows. Equal to all_records until a search/filter is applied.
filter_ids  : None (no filter) or the set of movie ids that passed the last search/filter.
              Whenever the full dataset is re-sorted, `filtered` is rebuilt from it, so an
              active filter stays active and in the new order.
Sort scope (next to the row count) decides whether a sort works on all_records or only
on the filtered rows.
"""
import random

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
                             QTableView, QTabWidget, QVBoxLayout, QWidget)

from benchmark_dialog import BenchmarkDialog
from composite import evaluate
from composite_panel import CompositePanel
from filters import NUMERIC_OPERATORS, TEXT_OPERATORS, filter_records, parse_value
from multilevel_panel import MultiLevelPanel
from searching import SEARCH_ALGORITHMS, search_label, search_records
from sorting import ALGORITHMS, label, multi_level_sort, sort_records
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
    """Runs one function (a sort, a search...) in the background and reports the result."""
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
        self.sample_size = None    # set while the table shows a sorted random sample
        self.full_order = None     # (column, descending) the FULL dataset is currently sorted by

        # ================= tool tab 1: single-column sort =================
        self.column_combo = QComboBox()
        self.algo_combo = QComboBox()
        self.order_combo = QComboBox()
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

        sort_page = QWidget()
        grid = QGridLayout(sort_page)
        grid.addWidget(QLabel("Column:"), 0, 0)
        grid.addWidget(self.column_combo, 0, 1)
        grid.addWidget(QLabel("Order:"), 0, 2)
        grid.addWidget(self.order_combo, 0, 3)
        grid.addWidget(self.sort_btn, 0, 4)
        grid.addWidget(self.benchmark_btn, 0, 5)
        grid.addWidget(QLabel("Algorithm:"), 1, 0)
        grid.addWidget(self.algo_combo, 1, 1, 1, 5)
        grid.addWidget(self.algo_info, 2, 0, 1, 6)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(3, 1)

        # ================= tool tab 2: multi-level sort =================
        self.multi_panel = MultiLevelPanel(COLUMNS)

        # ================= tool tab 3: single-condition search / filter =================
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

        search_page = QWidget()
        sgrid = QGridLayout(search_page)
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
        sgrid.setRowStretch(3, 1)

        # ================= tool tab 4: composite filter =================
        self.composite_panel = CompositePanel(COLUMNS)

        self.tools = QTabWidget()
        self.tools.addTab(sort_page, "Sort")
        self.tools.addTab(self.multi_panel, "Multi-level sort")
        self.tools.addTab(search_page, "Search / filter")
        self.tools.addTab(self.composite_panel, "Composite filter (AND / OR / NOT)")

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
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.time_label = _metric_label()
        self.comp_label = _metric_label()
        self.swap_label = _metric_label()
        sort_result = QGroupBox("Last sort result")
        sv = QVBoxLayout(sort_result)
        sv.addWidget(self.summary_label)
        sh = QHBoxLayout()
        for lbl in (self.time_label, self.comp_label, self.swap_label):
            sh.addWidget(lbl)
        sv.addLayout(sh)

        self.search_summary = QLabel()
        self.search_summary.setWordWrap(True)
        self.s_time_label = _metric_label()
        self.s_comp_label = _metric_label()
        self.s_match_label = _metric_label()
        search_result = QGroupBox("Last search / filter result")
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
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["Sort everything", "Sort only filtered rows"])
        self.scope_combo.setToolTip(
            "Only matters while a search or filter is active.\n"
            "Sort everything: all rows are sorted (the filter stays applied).\n"
            "Sort only filtered rows: just the rows currently shown are sorted.\n"
            "Greyed out while nothing is filtered, because both would mean 'all rows'.")
        self.scope_combo.setEnabled(False)
        self.rows_combo = QComboBox()
        self.rows_combo.setEditable(True)
        self.rows_combo.setInsertPolicy(QComboBox.NoInsert)
        self.rows_combo.addItems(["All rows", "100", "500", "1,000", "2,000", "5,000", "10,000"])
        self.rows_combo.setFixedWidth(110)
        self.rows_combo.setToolTip(
            "How many rows the Sort and Multi-level sort buttons use. Pick a size or type any number.\n"
            "If it is smaller than the scope, a random sample is sorted and shown (fixed seed, so it is "
            "repeatable).\nClick 'Show all rows' to go back. (The Benchmark has its own size choice.)")
        self.show_all_btn = QPushButton("Show all rows")
        self.show_all_btn.setEnabled(False)
        self.reload_btn = QPushButton("Reload data")
        status = QHBoxLayout()
        status.addWidget(self.count_label)
        status.addWidget(self.hint_label, 1)
        status.addWidget(QLabel("Sort scope:"))
        status.addWidget(self.scope_combo)
        status.addWidget(QLabel("Rows:"))
        status.addWidget(self.rows_combo)
        status.addWidget(self.show_all_btn)
        status.addWidget(self.reload_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tools)
        layout.addLayout(status)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.progress)
        layout.addLayout(results)

        # ================= signals =================
        self.sort_btn.clicked.connect(self.start_sort)
        self.benchmark_btn.clicked.connect(self.open_benchmark)
        self.reload_btn.clicked.connect(self.load_data)
        self.show_all_btn.clicked.connect(self.clear_search)
        self.header.sectionClicked.connect(self.on_header_clicked)
        self.column_combo.currentIndexChanged.connect(self.update_algorithm_availability)
        self.algo_combo.currentIndexChanged.connect(self.update_algo_info)
        self.multi_panel.sort_requested.connect(self.start_multisort)
        self.search_col_combo.currentIndexChanged.connect(self.update_search_controls)
        self.op_combo.currentIndexChanged.connect(self.update_search_info)
        self.search_algo_combo.currentIndexChanged.connect(self.update_search_info)
        self.search_btn.clicked.connect(self.start_search)
        self.value_edit.returnPressed.connect(self.start_search)
        self.value2_edit.returnPressed.connect(self.start_search)
        self.clear_btn.clicked.connect(self.clear_search)
        self.composite_panel.apply_requested.connect(self.start_composite)
        self.composite_panel.clear_requested.connect(self.clear_search)

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
        self.sample_size = None
        self.full_order = None
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
        if self.sample_size is not None:
            note = f"  (random sample of {self.sample_size:,} rows)"
        elif self.filter_ids is not None:
            note = "  (filter active)"
        else:
            note = ""
        self.count_label.setText(f"Showing {len(self.filtered):,} of {len(self.all_records):,} "
                                 f"movies{note}")
        filter_active = self.filter_ids is not None
        self.scope_combo.setItemText(1, f"Sort only filtered rows ({len(self.filtered):,})"
                                     if filter_active else "Sort only filtered rows")
        if not filter_active:
            self.scope_combo.setCurrentIndex(0)          # nothing to choose between
        self.scope_combo.setEnabled(not self._busy and filter_active)
        self.show_all_btn.setEnabled(not self._busy and filter_active)

    def reset_result_labels(self):
        self.summary_label.setText("No sort run yet. Choose a column and algorithm, then press Sort "
                                   "(or click a column header).")
        self.time_label.setText("Time: -")
        self.comp_label.setText("Comparisons: -")
        self.swap_label.setText("Swaps: -")
        self.search_summary.setText("No search run yet.")
        self.s_time_label.setText("Time: -")
        self.s_comp_label.setText("Comparisons: -")
        self.s_match_label.setText("Matches: -")

    def _rebuild_filtered(self):
        """Re-apply the active filter to the (possibly re-sorted) full dataset."""
        if self.filter_ids is None:
            self.filtered = self.all_records
        else:
            self.filtered = [r for r in self.all_records if r["id"] in self.filter_ids]

    def _scope(self):
        """Which rows a sort works on. With no active filter, both scopes are the same."""
        full = self.scope_combo.currentIndex() == 0 or self.filter_ids is None
        return full, (self.all_records if full else self.filtered)

    def _row_limit(self):
        """How many rows to sort: None means all of them. Raises ValueError for bad input."""
        text = self.rows_combo.currentText().strip().lower().replace(",", "").replace("rows", "").strip()
        if text in ("", "all"):
            return None
        if not text.isdigit() or int(text) < 1:
            raise ValueError("Rows must be a whole number of 1 or more, or 'All rows'.")
        return int(text)

    def _sort_input(self):
        """(scope_full, rows, sampled) for a sort. If fewer rows than the scope holds were asked
        for, take a random sample (fixed seed 42: repeatable, and it avoids the bias of 'the first
        N rows' when the data happens to be sorted already)."""
        full, pool = self._scope()
        limit = self._row_limit()
        if limit is None or limit >= len(pool):
            return full, pool, False
        sample = list(pool)
        random.Random(42).shuffle(sample)
        return False, sample[:limit], True

    def _scope_text(self, scope_full, sampled):
        if sampled:
            return "random sample"
        return "full dataset" if scope_full else "filtered results"

    def _apply_sorted_records(self, records, scope_full, sampled=False):
        if sampled:
            self.filter_ids = {r["id"] for r in records}     # the table now shows just this sample
            self.sample_size = len(records)
            self.filtered = records
        elif scope_full:
            self.all_records = records
            self._rebuild_filtered()        # an active filter stays active, in the new order
        else:
            self.filtered = records         # only the filtered rows were reordered
        self.model.set_records(self.filtered)
        self.table.scrollToTop()
        self.update_counts()

    def _show_indicator(self, column, descending):
        self.header.setSortIndicator(self.column_combo.findData(column),
                                     Qt.DescendingOrder if descending else Qt.AscendingOrder)
        self.header.setSortIndicatorShown(True)
        self.last_sorted = (column, descending)

    def _restore_indicator(self):
        """After a filter / 'Show all rows' the table follows the order of the full dataset,
        so the header arrow must show that order (or nothing if it was never sorted)."""
        if self.full_order is not None:
            self._show_indicator(*self.full_order)
        else:
            self.last_sorted = None
            self.header.setSortIndicatorShown(False)

    # ------------------------------------------------------------------
    # sort tab controls
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
    # search tab controls
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
        self.search_algo_combo.setEnabled(is_equals)
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
    # single-column sorting
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

    def _confirm_slow(self, algorithms, rows):
        """Warn before running an O(n²) algorithm on lots of rows. True = go ahead."""
        slow = [a for a in algorithms if ALGORITHMS[a]["average"] == "O(n²)"]
        if not slow or rows <= 5000:
            return True
        seconds = int(rows ** 2 * 1e-7 * len(slow)) + 1
        answer = QMessageBox.question(
            self, "This may take a while",
            f"{', '.join(slow)} {'is' if len(slow) == 1 else 'are'} O(n²). On {rows:,} rows this can "
            f"take roughly {seconds} seconds (it cannot be cancelled once started).\n\nContinue?")
        return answer == QMessageBox.Yes

    def start_sort(self):
        if self._busy:
            return
        column = self.column_combo.currentData()
        algorithm = self.algo_combo.currentData()
        descending = self.order_combo.currentIndex() == 1
        try:
            scope_full, data, sampled = self._sort_input()
        except ValueError as error:
            QMessageBox.warning(self, "Check the number of rows", str(error))
            return
        if not data:
            QMessageBox.information(self, "Nothing to sort", "There are no movies to sort.")
            return
        if not self._confirm_slow([algorithm], len(data)):
            return

        self._pending = ("sort", column, descending, scope_full, sampled)
        self._set_busy(True, f"Sorting {len(data):,} rows with {algorithm}...")
        self.worker = TaskWorker(sort_records, data, column, algorithm, descending)
        self.worker.done.connect(self.on_sort_done)
        self.worker.failed.connect(self.on_task_failed)
        self.worker.start()

    def on_sort_done(self, result):
        _, column, descending, scope_full, sampled = self._pending
        records = result["records"]
        self._apply_sorted_records(records, scope_full, sampled)
        self._show_indicator(column, descending)
        if scope_full and not sampled:
            self.full_order = (column, descending)

        name = result["algorithm"]
        info = ALGORITHMS[name]
        self.summary_label.setText(
            f"{name} ({'stable' if info['stable'] else 'unstable'}, average {info['average']}) on "
            f"'{COLUMN_TITLE[column]}', {'descending' if descending else 'ascending'}, "
            f"{len(records):,} rows ({self._scope_text(scope_full, sampled)})")
        self.time_label.setText(f"Time: {result['time_ms']:,.2f} ms")
        self.comp_label.setText(f"Comparisons: {result['comparisons']:,}")
        self.swap_label.setText(f"Swaps: {result['swaps']:,}")
        self._set_busy(False)

    # ------------------------------------------------------------------
    # multi-level sorting
    # ------------------------------------------------------------------
    def start_multisort(self, levels):
        if self._busy:
            return
        try:
            scope_full, data, sampled = self._sort_input()
        except ValueError as error:
            QMessageBox.warning(self, "Check the number of rows", str(error))
            return
        if not data:
            QMessageBox.information(self, "Nothing to sort", "There are no movies to sort.")
            return
        if not self._confirm_slow([algorithm for _, algorithm, _ in levels], len(data)):
            return
        self._pending = ("multi", levels, scope_full, sampled)
        self._set_busy(True, f"Multi-level sort of {len(data):,} rows ({len(levels)} levels)...")
        self.worker = TaskWorker(multi_level_sort, data, levels)
        self.worker.done.connect(self.on_multisort_done)
        self.worker.failed.connect(self.on_task_failed)
        self.worker.start()

    def on_multisort_done(self, result):
        _, levels, scope_full, sampled = self._pending
        records = result["records"]
        self._apply_sorted_records(records, scope_full, sampled)
        self._show_indicator(levels[0][0], levels[0][2])
        if scope_full and not sampled:
            self.full_order = (levels[0][0], levels[0][2])

        lines = [f"Multi-level sort, {len(records):,} rows "
                 f"({self._scope_text(scope_full, sampled)}). "
                 f"Passes run from the last level to the first:"]
        for s in result["steps"]:
            lines.append(f"  Level {s['level']}: {COLUMN_TITLE[s['column']]} "
                         f"{'descending' if s['descending'] else 'ascending'} - {s['algorithm']}: "
                         f"{s['time_ms']:,.1f} ms, {s['comparisons']:,} comparisons, {s['swaps']:,} swaps")
        self.summary_label.setText("\n".join(lines))
        self.time_label.setText(f"Total time: {result['time_ms']:,.2f} ms")
        self.comp_label.setText(f"Comparisons: {result['comparisons']:,}")
        self.swap_label.setText(f"Swaps: {result['swaps']:,}")
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
    # single-condition search / filter
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

    def _show_filter_result(self, result):
        """Common to single and composite filters: apply the matching ids to the table."""
        self.filter_ids = {r["id"] for r in result["records"]}
        self.sample_size = None
        self._rebuild_filtered()
        self.model.set_records(self.filtered)
        self.table.scrollToTop()
        self._restore_indicator()
        self.s_time_label.setText(f"Time: {result['time_ms']:,.3f} ms")
        self.s_comp_label.setText(f"Comparisons: {result['comparisons']:,}")
        self.s_match_label.setText(f"Matches: {result['matches']:,}")
        self.update_counts()

    def on_search_done(self, result):
        column, operator, text, text2 = self._pending
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
        self._show_filter_result(result)
        self._set_busy(False)

    # ------------------------------------------------------------------
    # composite filter (AND / OR / NOT)
    # ------------------------------------------------------------------
    def start_composite(self, terms, algorithm):
        if self._busy:
            return
        if not self.all_records:
            QMessageBox.information(self, "Nothing to filter", "There are no movies to filter.")
            return
        self._pending = ("composite",)
        self._set_busy(True, "Applying composite filter...")
        self.worker = TaskWorker(evaluate, self.all_records, terms, algorithm, COLUMN_TITLE)
        self.worker.done.connect(self.on_composite_done)
        self.worker.failed.connect(self.on_task_failed)
        self.worker.start()

    def on_composite_done(self, result):
        lines = [f"Composite filter: {result['expression']}  ->  {result['matches']:,} "
                 f"match{'es' if result['matches'] != 1 else ''} among {result['rows']:,} rows."]
        lines += ["  - " + detail for detail in result["details"]]
        presort = result["presort"]
        if presort:
            lines.append(f"  {presort['count']} 'equals' condition(s) needed the column sorted first "
                         f"({presort['algorithm']}: {presort['time_ms']:,.1f} ms, "
                         f"{presort['comparisons']:,} comparisons in total) - not included in the time.")
        self.search_summary.setText("\n".join(lines))
        self._show_filter_result(result)
        self._set_busy(False)

    def clear_search(self):
        if self._busy:
            return
        self.filter_ids = None
        self.sample_size = None
        self._rebuild_filtered()
        self.model.set_records(self.filtered)
        self._restore_indicator()
        self.value_edit.clear()
        self.value2_edit.clear()
        self.search_summary.setText("Filter cleared.")
        self.s_time_label.setText("Time: -")
        self.s_comp_label.setText("Comparisons: -")
        self.s_match_label.setText("Matches: -")
        self.update_counts()

    # ------------------------------------------------------------------
    # shared
    # ------------------------------------------------------------------
    def on_task_failed(self, message):
        self._set_busy(False)
        QMessageBox.warning(self, "Cannot complete this action", message)

    def _set_busy(self, busy, text=""):
        self._busy = busy
        self.tools.setEnabled(not busy)         # disables every tab at once
        self.scope_combo.setEnabled(not busy and self.filter_ids is not None)
        self.rows_combo.setEnabled(not busy)
        self.show_all_btn.setEnabled(not busy and self.filter_ids is not None)
        self.reload_btn.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.hint_label.setText(text if busy else "")

    def is_busy(self):
        return self._busy