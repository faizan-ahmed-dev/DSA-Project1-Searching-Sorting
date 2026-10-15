"""theme.py - the look of the app: "Cinema Noir" (dark) and a warm light mode.

A theme is just a handful of colours. apply() gives the whole app a QPalette (the colours
Qt uses by default for windows, tables, text boxes, disabled items...) plus a short
stylesheet for the extras (rounded buttons, red accent tabs, the progress bar...).
Nothing here touches the data or the algorithms.
"""
from PyQt5.QtGui import QColor, QPalette

ACCENT = "#b3202a"        # curtain red
GOLD = "#e0b04a"

SCHEMES = {
    "dark": dict(window="#16161d", base="#1e1e28", alt="#252533", text="#e8e6ea",
                 button="#2b2b3b", border="#3a3a4d", muted="#a09cab", disabled="#6c6877",
                 warn="#ff9a5c", title=GOLD, tooltip="#2b2b3b", accent=ACCENT),
    "light": dict(window="#f4f1ec", base="#ffffff", alt="#f3efe8", text="#1d1b20",
                  button="#e9e4da", border="#cfc8bb", muted="#5d5a63", disabled="#a29e97",
                  warn="#b04000", title="#8a5a00", tooltip="#fffbe8", accent=ACCENT),
}

# Rating colours for the table (text colour). Each theme has its own shades so the text
# stays readable on that background: green = great, amber = good, orange = so-so, red = poor.
RATING_COLORS = {
    "dark": {"great": "#5ed18a", "good": "#f0c24b", "ok": "#f08a3c", "poor": "#ff6b6b", "none": "#8a8794"},
    "light": {"great": "#1f7a42", "good": "#9a6b00", "ok": "#b85a00", "poor": "#c0262d", "none": "#7a7680"},
}

STYLESHEET = """
QPushButton { background: %(button)s; border: 1px solid %(border)s; border-radius: 5px; padding: 5px 12px; }
QPushButton:hover { border-color: %(accent)s; }
QPushButton:pressed { background: %(accent)s; color: #ffffff; }
QPushButton:disabled { background: %(window)s; color: %(disabled)s; }
QPushButton[accent="true"] { background: %(accent)s; border-color: %(accent)s; color: #ffffff; font-weight: bold; }
QPushButton[accent="true"]:hover { background: #cc2f3a; border-color: #cc2f3a; }
QPushButton[accent="true"]:disabled { background: %(border)s; border-color: %(border)s; color: %(disabled)s; }
QPushButton[compact="true"] { padding: 4px 4px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid %(muted)s; border-radius: 3px; background: %(base)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; }
QLineEdit, QPlainTextEdit { border: 1px solid %(border)s; border-radius: 4px; padding: 3px 5px; }
QLineEdit:focus { border-color: %(accent)s; }
QTabWidget::pane { border: 1px solid %(border)s; border-radius: 4px; top: -1px; }
QTabBar::tab { background: %(window)s; color: %(muted)s; padding: 7px 16px; border: 1px solid %(border)s;
               border-bottom: none; border-top-left-radius: 5px; border-top-right-radius: 5px; margin-right: 2px; }
QTabBar::tab:selected { background: %(base)s; color: %(text)s; border-top: 3px solid %(accent)s; }
QTabBar::tab:hover:!selected { color: %(text)s; }
QGroupBox { border: 1px solid %(border)s; border-radius: 6px; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: %(title)s; font-weight: bold; }
QProgressBar { border: 1px solid %(border)s; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: %(accent)s; border-radius: 3px; }
QTableView, QTableWidget { gridline-color: %(border)s; }
QLabel[muted="true"] { color: %(muted)s; }
QLabel[warn="true"] { color: %(warn)s; }
QToolTip { color: %(text)s; background: %(tooltip)s; border: 1px solid %(border)s; padding: 4px; }
QMenu { border: 1px solid %(border)s; }
QMenu::item:selected { background: %(accent)s; color: #ffffff; }
"""
# (The table header is deliberately NOT styled here: styling it would hide the little
#  arrow that shows which column is sorted.)


def make_palette(c):
    palette = QPalette()
    roles = {QPalette.Window: c["window"], QPalette.WindowText: c["text"], QPalette.Base: c["base"],
             QPalette.AlternateBase: c["alt"], QPalette.Text: c["text"], QPalette.Button: c["button"],
             QPalette.ButtonText: c["text"], QPalette.ToolTipBase: c["tooltip"],
             QPalette.ToolTipText: c["text"], QPalette.Highlight: c["accent"],
             QPalette.HighlightedText: "#ffffff", QPalette.BrightText: "#ffffff",
             QPalette.Link: GOLD, QPalette.PlaceholderText: c["muted"]}
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(c["disabled"]))     # greyed-out items
    return palette


def apply(app, mode):
    """Give the whole application the 'dark' or 'light' look."""
    colors = SCHEMES[mode]
    app.setStyle("Fusion")                  # looks the same on every computer
    app.setPalette(make_palette(colors))
    app.setStyleSheet(STYLESHEET % colors)
