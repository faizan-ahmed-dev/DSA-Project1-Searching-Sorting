"""main.py - start the app:  python main.py"""
import sys

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QPushButton, QTabWidget

import theme

from movies_tab import MoviesTab
from scraper_panel import ScraperWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Movie Explorer - CS200 Project 1")
        self.resize(1280, 840)

        self.movies_tab = MoviesTab()
        self.scraper_tab = ScraperWindow()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.movies_tab, "Movies")
        self.tabs.addTab(self.scraper_tab, "Scraper")
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # dark / light toggle in the top-right corner; the choice is remembered between runs
        self.settings = QSettings("CS200", "MovieExplorer")
        self.theme_btn = QPushButton()
        self.theme_btn.setToolTip("Switch between the dark (Cinema Noir) and light look")
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.tabs.setCornerWidget(self.theme_btn, Qt.TopRightCorner)
        self.theme = "dark"
        self.apply_theme(self.settings.value("theme", "dark"))

    def apply_theme(self, mode):
        if mode not in theme.SCHEMES:
            mode = "dark"
        theme.apply(QApplication.instance(), mode)
        self.theme = mode
        self.movies_tab.set_theme(mode)                  # the rating colours depend on the theme
        self.theme_btn.setText("Light mode" if mode == "dark" else "Dark mode")
        self.settings.setValue("theme", mode)

    def toggle_theme(self):
        self.apply_theme("light" if self.theme == "dark" else "dark")

    def on_tab_changed(self, index):
        if index == 0:                       # back on the Movies tab
            self.movies_tab.refresh_hint()   # tells the user if the scraper added movies

    def closeEvent(self, event):
        if self.movies_tab.is_busy():
            QMessageBox.information(self, "Sort in progress",
                                    "A sort is still running. Please wait for it to finish, then close.")
            event.ignore()
            return
        self.scraper_tab.shutdown()          # stop the scraper and save the last batch
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
