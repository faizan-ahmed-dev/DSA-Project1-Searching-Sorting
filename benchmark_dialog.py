"""benchmark_dialog.py - the Benchmark window.

Runs EVERY sorting algorithm on the selected column and fills a comparison table
(time, comparisons, swaps). It runs in a background thread and fills the table one
row at a time, so you can watch it work. Bubble/selection/insertion sort are O(n²),
so on all 16,000 rows they take most of the total time.

Fairness: every algorithm sorts the SAME copy of the data, shuffled in a fixed random
order (seed 42). Without the shuffle, data that is already sorted would flatter
bubble and insertion sort (their best case) and mislead the comparison.
"""
import random

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView,
                             QLabel, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout)

from sorting import ALGORITHMS, sort_records

HEADERS = ["Algorithm", "Average", "Worst", "Stable", "Time (ms)", "Comparisons", "Swaps", "Rank"]
TIME, COMPS, SWAPS, RANK = 4, 5, 6, 7


class BenchmarkWorker(QThread):
    row_started = pyqtSignal(int)
    row_done = pyqtSignal(int, object)      # row number, result dict
    all_done = pyqtSignal(bool)             # True if it was cancelled

    def __init__(self, records, column, descending):
        super().__init__()
        self.records = records
        self.column = column
        self.descending = descending
        self._cancel = False

    def cancel(self):
        self._cancel = True                 # checked between algorithms

    def run(self):
        for i, name in enumerate(ALGORITHMS):
            if self._cancel:
                break
            self.row_started.emit(i)
            try:
                r = sort_records(self.records, self.column, name, self.descending)
                row = {"ok": True, "time_ms": r["time_ms"],
                       "comparisons": r["comparisons"], "swaps": r["swaps"]}
            except ValueError as e:         # e.g. radix sort on a text column
                row = {"ok": False, "message": str(e)}
            self.row_done.emit(i, row)
        self.all_done.emit(self._cancel)


def _cell(text, align_right=False, bold=False, italic=False):
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled)
    item.setTextAlignment(int((Qt.AlignRight if align_right else Qt.AlignLeft) | Qt.AlignVCenter))
    if bold or italic:
        font = QFont()
        font.setBold(bold)
        font.setItalic(italic)
        item.setFont(font)
    return item


class BenchmarkDialog(QDialog):
    def __init__(self, records, column, column_title, descending, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Benchmark - all sorting algorithms")
        self.resize(900, 520)
        self.records = records
        self.column = column
        self.descending = descending
        self.worker = None
        self._running = False
        self.names = list(ALGORITHMS)
        n = len(records)

        self.info = QLabel(f"Column: <b>{column_title}</b> ({'descending' if descending else 'ascending'})"
                           f" &nbsp;|&nbsp; {n:,} rows available. Every algorithm sorts the same "
                           f"randomly shuffled copy.")
        self.size_combo = QComboBox()
        self.size_combo.addItem(f"All {n:,} rows", n)
        for size in (10000, 5000, 2000, 1000):
            if size < n:
                self.size_combo.addItem(f"{size:,} rows (random sample)", size)
        self.size_combo.currentIndexChanged.connect(self.update_estimate)
        self.estimate = QLabel()
        self.start_btn = QPushButton("Run benchmark")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.close_btn = QPushButton("Close")

        top = QHBoxLayout()
        top.addWidget(QLabel("Rows to use:"))
        top.addWidget(self.size_combo)
        top.addWidget(self.start_btn)
        top.addWidget(self.cancel_btn)
        top.addStretch(1)
        top.addWidget(self.close_btn)

        self.table = QTableWidget(len(self.names), len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.reset_table()

        self.progress = QProgressBar()
        self.progress.setRange(0, len(self.names))
        self.status = QLabel("Press 'Run benchmark'.")

        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addLayout(top)
        layout.addWidget(self.estimate)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)

        self.start_btn.clicked.connect(self.start)
        self.cancel_btn.clicked.connect(self.cancel)
        self.close_btn.clicked.connect(self.reject)
        self.update_estimate()

    # ------------------------------------------------------------------
    def update_estimate(self):
        size = self.size_combo.currentData()
        seconds = int(size * size * 2e-7) + 1          # bubble + selection + insertion dominate
        self.estimate.setText(f"Estimated time: roughly {seconds} second{'s' if seconds != 1 else ''} "
                              f"(the three O(n²) algorithms take most of it).")
        self.estimate.setStyleSheet("color: #444;")

    def reset_table(self):
        self.table.clearSpans()
        for i, name in enumerate(self.names):
            info = ALGORITHMS[name]
            self.table.setItem(i, 0, _cell(name, bold=True))
            self.table.setItem(i, 1, _cell(info["average"]))
            self.table.setItem(i, 2, _cell(info["worst"]))
            self.table.setItem(i, 3, _cell("yes" if info["stable"] else "no"))
            for col in (TIME, COMPS, SWAPS, RANK):
                self.table.setItem(i, col, _cell("", align_right=True))

    def start(self):
        size = self.size_combo.currentData()
        sample = list(self.records)
        random.Random(42).shuffle(sample)              # fixed seed -> repeatable benchmark
        sample = sample[:size]
        self.reset_table()
        self.results = {}
        self.progress.setValue(0)
        self._set_running(True)
        self.status.setText(f"Benchmarking {len(sample):,} rows...")
        self.worker = BenchmarkWorker(sample, self.column, self.descending)
        self.worker.row_started.connect(self.on_row_started)
        self.worker.row_done.connect(self.on_row_done)
        self.worker.all_done.connect(self.on_all_done)
        self.worker.start()

    def cancel(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status.setText("Cancelling after the current algorithm finishes...")

    def _set_running(self, running):
        self._running = running
        self.start_btn.setEnabled(not running)
        self.size_combo.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.close_btn.setEnabled(not running)

    def reject(self):
        if self._running:                              # never close while the thread runs
            return
        super().reject()

    # ------------------------------------------------------------------
    def on_row_started(self, i):
        self.table.setItem(i, TIME, _cell("running...", align_right=True, italic=True))
        self.status.setText(f"Running {self.names[i]}...")

    def on_row_done(self, i, row):
        self.results[i] = row
        if row["ok"]:
            self.table.setItem(i, TIME, _cell(f"{row['time_ms']:,.2f}", align_right=True))
            self.table.setItem(i, COMPS, _cell(f"{row['comparisons']:,}", align_right=True))
            self.table.setItem(i, SWAPS, _cell(f"{row['swaps']:,}", align_right=True))
        else:
            self.table.setSpan(i, TIME, 1, 4)          # message across the metric columns
            self.table.setItem(i, TIME, _cell(f"not possible: {row['message']}", italic=True))
        self.progress.setValue(self.progress.value() + 1)

    def on_all_done(self, cancelled):
        self._set_running(False)
        times = {i: r["time_ms"] for i, r in self.results.items() if r["ok"]}
        for i, t in times.items():
            rank = 1 + sum(1 for other in times.values() if other < t)    # 1 = fastest
            self.table.setItem(i, RANK, _cell(str(rank), align_right=True, bold=(rank == 1)))
        if times:
            fastest = [i for i, t in times.items() if 1 + sum(1 for o in times.values() if o < t) == 1][0]
            for col in range(len(HEADERS)):
                item = self.table.item(fastest, col)
                if item is not None:
                    item.setBackground(QBrush(QColor("#d4edda")))
                    item.setForeground(QBrush(QColor("#000000")))
            msg = f"Fastest: {self.names[fastest]} ({times[fastest]:,.2f} ms)."
        else:
            msg = "No results."
        if cancelled:
            msg = f"Cancelled after {len(self.results)} of {len(self.names)} algorithms. " + msg
        self.status.setText(msg)
