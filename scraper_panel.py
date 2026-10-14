"""scraper_panel.py - the Scraper tab.

Two ways to scrape, one set of controls:
  * Start        : the bulk scrape (years 1980-2025) up to the target number of movies
  * Scrape URL   : BONUS - paste a TMDB URL (movie, collection, person, genre, search...)
Pause / Resume / Stop, the progress bar and the log work for whichever one is running.
"""
import os

from PyQt5.QtWidgets import (QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                             QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from scraper import ScraperWorker
from storage import MovieStore
from url_scraper import UrlScraperWorker, parse_tmdb_url


class ScraperWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Movie Scraper - CS200 Project 1")
        self.resize(600, 480)
        self.worker = None
        self.mode = "bulk"          # "bulk" or "url": decides how progress is worded

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

        # ---- bonus: scrape from a URL ----
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a TMDB URL, e.g. https://www.themoviedb.org/collection/10")
        self.url_edit.setToolTip(
            "Supported: movie, collection, person, genre, keyword, company and search pages on "
            "themoviedb.org, plus api.themoviedb.org/3 lists such as discover/movie.\n"
            "Movies already in the database are skipped.")
        self.max_spin = QSpinBox()
        self.max_spin.setRange(1, 2000)
        self.max_spin.setValue(100)
        self.max_spin.setToolTip("Most movies to take from this URL")
        self.url_btn = QPushButton("Scrape URL")

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

        url_box = QGroupBox("Scrape from a URL (bonus)")
        url_layout = QHBoxLayout(url_box)
        url_layout.addWidget(self.url_edit, 1)
        url_layout.addWidget(QLabel("Max movies:"))
        url_layout.addWidget(self.max_spin)
        url_layout.addWidget(self.url_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(buttons)
        layout.addWidget(url_box)
        layout.addWidget(self.bar)
        layout.addWidget(self.label)
        layout.addWidget(self.log)

        self.start_btn.clicked.connect(self.start)
        self.url_btn.clicked.connect(self.start_url)
        self.url_edit.returnPressed.connect(self.start_url)
        self.pause_btn.clicked.connect(lambda: self.worker and self.worker.pause())
        self.resume_btn.clicked.connect(lambda: self.worker and self.worker.resume())
        self.stop_btn.clicked.connect(lambda: self.worker and self.worker.stop())
        self.export_btn.clicked.connect(self.export_csv)

        self.set_running(False)
        self.show_saved_progress()

    def set_running(self, running):
        for widget in (self.start_btn, self.url_btn, self.url_edit, self.max_spin,
                       self.key_edit, self.target_spin):
            widget.setEnabled(not running)
        for b in (self.pause_btn, self.resume_btn, self.stop_btn):
            b.setEnabled(running)

    def _launch(self, worker, mode):
        self.mode = mode
        self.worker = worker
        worker.progress.connect(self.on_progress)
        worker.status.connect(self.log.appendPlainText)
        worker.finished_signal.connect(self.on_finished)
        self.set_running(True)
        worker.start()

    def start(self):
        if not self.key_edit.text().strip():
            self.log.appendPlainText("Enter your TMDB API key first.")
            return
        self._launch(ScraperWorker(self.key_edit.text(), self.target_spin.value()), "bulk")

    def start_url(self):
        if not self.key_edit.text().strip():
            self.log.appendPlainText("Enter your TMDB API key first.")
            return
        try:
            plan = parse_tmdb_url(self.url_edit.text())
        except ValueError as error:
            self.log.appendPlainText(f"URL not usable: {error}")
            return
        self._launch(UrlScraperWorker(self.key_edit.text(), plan, self.max_spin.value()), "url")

    def show_saved_progress(self):
        """Idle display: how many movies are in the database versus the bulk target."""
        store = MovieStore()
        saved = store.count()
        store.close()
        self.mode = "bulk"
        self.on_progress(saved, self.target_spin.value())

    def on_progress(self, done, target):
        self.bar.setMaximum(max(target, 1))
        self.bar.setValue(min(done, target))
        if self.mode == "url":
            self.label.setText(f"URL scrape: {done} / {target} movies processed")
        else:
            self.label.setText(f"{done} / {target} movies saved")

    def on_finished(self, outcome):
        self.log.appendPlainText(f"Finished: {outcome}")
        self.set_running(False)
        if self.mode == "url":
            self.show_saved_progress()         # bar goes back to "movies in database / target"

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
