"""main.py - start the app:  python main.py"""
import sys

from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget

from movies_tab import MoviesTab
from scraper_panel import ScraperWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Movie Explorer - CS200 Project 1")
        self.resize(1250, 780)

        self.movies_tab = MoviesTab()
        self.scraper_tab = ScraperWindow()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.movies_tab, "Movies")
        self.tabs.addTab(self.scraper_tab, "Scraper")
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self.on_tab_changed)

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
