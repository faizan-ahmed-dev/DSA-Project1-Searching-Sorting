"""main.py - scraper control window (Day 1-2). The table/sort/search UI comes later."""
import os
import sys

from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit,
                             QPlainTextEdit, QProgressBar, QPushButton,
                             QSpinBox, QVBoxLayout, QWidget)

from scraper import ScraperWorker
from storage import MovieStore


class ScraperWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Movie Scraper - CS200 Project 1")
        self.resize(600, 420)
        self.worker = None

        self.key_edit = QLineEdit(os.environ.get("TMDB_API_KEY", ""))
        self.key_edit.setPlaceholderText("TMDB API key (v3)")
        self.target_spin = QSpinBox()
        self.target_spin.setRange(1000, 18000)
        self.target_spin.setValue(16000)

        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        self.resume_btn = QPushButton("Resume")
        self.stop_btn = QPushButton("Stop")
        self.export_btn = QPushButton("Export CSV")

        self.bar = QProgressBar()
        self.label = QLabel("Idle")
        self.log = QPlainTextEdit(readOnly=True)

        top = QHBoxLayout()
        top.addWidget(QLabel("API key:"))
        top.addWidget(self.key_edit, 1)
        top.addWidget(QLabel("Target:"))
        top.addWidget(self.target_spin)
        buttons = QHBoxLayout()
        for b in (self.start_btn, self.pause_btn, self.resume_btn,
                  self.stop_btn, self.export_btn):
            buttons.addWidget(b)
        layout = QVBoxLayout(self)
        for item in (top, buttons):
            layout.addLayout(item)
        layout.addWidget(self.bar)
        layout.addWidget(self.label)
        layout.addWidget(self.log)

        self.start_btn.clicked.connect(self.start)
        self.pause_btn.clicked.connect(lambda: self.worker and self.worker.pause())
        self.resume_btn.clicked.connect(lambda: self.worker and self.worker.resume())
        self.stop_btn.clicked.connect(lambda: self.worker and self.worker.stop())
        self.export_btn.clicked.connect(self.export_csv)

        self.set_running(False)
        store = MovieStore()
        saved = store.count()
        store.close()
        self.on_progress(saved, self.target_spin.value())

    def set_running(self, running):
        self.start_btn.setEnabled(not running)
        self.key_edit.setEnabled(not running)
        self.target_spin.setEnabled(not running)
        for b in (self.pause_btn, self.resume_btn, self.stop_btn):
            b.setEnabled(running)

    def start(self):
        if not self.key_edit.text().strip():
            self.log.appendPlainText("Enter your TMDB API key first.")
            return
        self.worker = ScraperWorker(self.key_edit.text(), self.target_spin.value())
        self.worker.progress.connect(self.on_progress)
        self.worker.status.connect(self.log.appendPlainText)
        self.worker.finished_signal.connect(self.on_finished)
        self.set_running(True)
        self.worker.start()

    def on_progress(self, done, target):
        self.bar.setMaximum(target)
        self.bar.setValue(min(done, target))
        self.label.setText(f"{done} / {target} movies saved")

    def on_finished(self, outcome):
        self.log.appendPlainText(f"Finished: {outcome}")
        self.set_running(False)

    def export_csv(self):
        store = MovieStore()
        store.export_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "movies.csv"))
        store.close()
        self.log.appendPlainText("Exported movies.csv")

    def shutdown(self):
        """Called by the main window when the app closes: stop the scraper and
        wait so the last batch of movies is saved."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
