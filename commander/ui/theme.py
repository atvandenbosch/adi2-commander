"""Dark look: Qt's Fusion style with a dark palette, a neutral accent, and a colour for each part of the sound."""

from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette

DISPLAY = QColor("#121314")       # the graph's zone, from line to line: the darkest, as the device's display
DISPLAY_GRID = QColor("#2e3034")
BACKGROUND = QColor("#1b1c1d")    # the ground of the window on either side of the display
PANEL = QColor("#242628")
CELL = QColor("#2c2d30")
GRID = QColor("#383a3e")
RAISED = QColor("#303235")        # the face of an action; a switch or option under the mouse
BORDER = QColor("#45484d")        # the outline of an action
CHOSEN = QColor("#2a2c30")        # the background of the preset selected on this output
TEXT = QColor("#e4e6e8")
BUTTON_TEXT = QColor("#d6dadd")   # the name of an action
LABEL = QColor("#b9bec4")         # titles, column and row names, legend names, tabs, the status bar
SECONDARY = QColor("#868c93")     # what supports: axis numbers, slot numbers, (free), a fixed cell, notes
OFF = QColor("#6c7076")           # a part of the sound out of the path, or a setting that is off
DISABLED = QColor("#34363a")      # what cannot be used now: no device, or busy
SPIN = QColor("#a8adb3")          # a spinner that can go further
SPIN_OFF = QColor("#34363a")      # a spinner at the band limit
ACCENT = QColor("#d6dadd")        # what is chosen: the tab, the preset, the open panel; no part of the sound
LEFT = QColor("#79c0f1")          # blue: the left channel
RIGHT = QColor("#e7a875")         # apricot: the right channel, opposite left on the colour wheel
SHARED = QColor("#ef9ca9")        # rose: one EQ for both channels (Dual EQ off)
BT = QColor("#60ccc5")            # turquoise: Bass/Treble, shared by both channels, in the graph and its switch
LOUDNESS = QColor("#d9d1b4")      # ivory: Loudness, an effect apart with a graph of its own
WARN = QColor("#f0b21b")          # amber: busy, waiting, attention
BAD = QColor("#e0503c")           # read-back differs from what was sent
GOOD = QColor("#4cc46a")
HEADER_PADDING = 8                # px left and right of a column header's text
TAB_LINE = 2                      # px: the line under the chosen tab


def faded(color):
    """The colour of a part of the sound that is on but bypassed: its own colour, faded toward the panel."""
    return QColor(*[round(p + (c - p) * 0.6) for p, c in zip(PANEL.getRgb()[:3], color.getRgb()[:3])])


def apply(app):
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.Window, BACKGROUND)
    p.setColor(QPalette.WindowText, TEXT)
    p.setColor(QPalette.Base, CELL)
    p.setColor(QPalette.AlternateBase, PANEL)
    p.setColor(QPalette.Text, TEXT)
    p.setColor(QPalette.Button, PANEL)
    p.setColor(QPalette.ButtonText, TEXT)
    p.setColor(QPalette.ToolTipBase, PANEL)
    p.setColor(QPalette.ToolTipText, TEXT)
    p.setColor(QPalette.Highlight, ACCENT.darker(160))
    p.setColor(QPalette.HighlightedText, TEXT)
    p.setColor(QPalette.PlaceholderText, SECONDARY)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, SECONDARY)
    app.setPalette(p)
    app.setStyleSheet("""
        QToolTip { color: %(text)s; background: %(panel)s; border: 1px solid %(grid)s; }
        QTabBar::tab { background: %(panel)s; color: %(label)s; padding: 7px 16px; border: none;
                       border-bottom: %(tab_line)dpx solid transparent; }
        QTabBar::tab:selected { color: %(text)s; border-bottom: %(tab_line)dpx solid %(accent)s; }
        QTabBar::tab:disabled { color: %(secondary)s; }
        QTableView { gridline-color: %(grid)s; border: none; }
        QHeaderView::section { background: %(background)s; color: %(label)s; border: none; padding: 4px %(pad)dpx; }
        QTableCornerButton::section { background: %(background)s; border: none; }
        QStatusBar { background: %(panel)s; color: %(label)s; border-top: 1px solid %(grid)s; }
        QStatusBar::item { border: none; }
        QRadioButton { spacing: 3px; }
        QRadioButton::indicator { width: 12px; height: 12px; border-radius: 7px; border: 1px solid %(border)s;
                                  background: %(cell)s; }
        QRadioButton::indicator:hover { border-color: %(label)s; }
        QRadioButton::indicator:checked { background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5,
            stop: 0 %(accent)s, stop: 0.45 %(accent)s, stop: 0.55 %(cell)s, stop: 1 %(cell)s); }
    """ % dict(text=TEXT.name(), panel=PANEL.name(), grid=GRID.name(), label=LABEL.name(), accent=ACCENT.name(),
               secondary=SECONDARY.name(), border=BORDER.name(), cell=CELL.name(),
               background=BACKGROUND.name(), pad=HEADER_PADDING, tab_line=TAB_LINE))


def ui_font(size):
    """The application's font at another size: for what labels, as the values along a graph's axes."""
    f = QFont(QGuiApplication.font())
    f.setPointSizeF(size)
    return f


def mono_font(size=11):
    """For values one sets: the cells of the tables."""
    f = QFont("Consolas")
    if not QFontDatabase.hasFamily("Consolas"):
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    f.setPointSizeF(size)
    return f
