"""The notice when a model Commander has not been tested with is connected: once per run, unless the user chose
not to see it again in this version of Commander. Not in Simulated mode."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLayout, QStyle,
                               QVBoxLayout)

from .. import __version__
from . import theme

ORGANIZATION, APPLICATION = "ADI-2 Commander", "Commander"   # where QSettings keeps what the app remembers
TITLE = "Not tested with the %(name)s"
TEXT = ("Commander has not been tested with an actual %(name)s.\n\n"
        "It is recommended to save the device's state with ADI-2 Remote before continuing: "
        "File → Save Setup As…\n\n"
        "To explore the app first, or to convert filter sets and curves for your %(name)s, no device is needed: "
        "start ADI-2 Commander (simulated) from the Start menu.")
# kept on one line each when the text wraps
WHOLE = ("ADI-2 Remote", "File → Save Setup As…", "ADI-2 Commander (simulated)")
NBSP = " "
TITLE_PT = 12                                    # a dialog's title on Windows, over text of 9 pt
# the layout of a Windows task dialog, in pixels at 100 %: the icon in the corner, title and text beside it in one
# column, the check box at the left of the row of buttons
ICON = 32
MARGINS = (10, 10, 11, 10)                       # left, top, right, bottom
ICON_GAP = 10                                    # from the icon to the column of title and text
TEXT_WIDTH = 287
TITLE_GAP = 14                                   # from the title to the text
BUTTONS_GAP = 24                                 # from the text to the row of buttons
CHECK_INDENT = 2                                 # the check box's square under the icon's


def _whole(text, name):
    for part in WHOLE + (name,):
        text = text.replace(part, part.replace(" ", NBSP))
    return text


def key(model):
    """The setting that holds the version of Commander in which the user chose not to see it again for model."""
    return "untested/%02x" % model.id


def due(settings, model):
    """Whether the notice is to be shown for model: not tested, and not put aside in this version."""
    return not model.tested and settings.value(key(model)) != __version__


class UntestedBox(QDialog):
    """Not tested with the model, laid out as a Windows task dialog, with the app's name in the title bar. Continue
    or Quit, and Don't show this again. Escape and closing the window are Continue."""

    def __init__(self, parent, model):
        super().__init__(parent)
        self.setWindowTitle("ADI-2 Commander")
        self.quitting = False
        self.title = TITLE % {"name": model.name}

        icon = QLabel()
        icon.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxWarning, None, self).pixmap(ICON, ICON))
        icon.setFixedSize(ICON, ICON)
        self.heading = QLabel('<span style="font-size: %dpt; color: %s;">%s</span>'
                              % (TITLE_PT, theme.TEXT.name(), _whole(self.title, model.name)))
        self.body = QLabel(_whole(TEXT % {"name": model.name}, model.name))
        for label in (self.heading, self.body):
            label.setWordWrap(True)
            label.setFixedWidth(TEXT_WIDTH)
        column = QVBoxLayout()
        column.setSpacing(TITLE_GAP)
        column.addWidget(self.heading)
        column.addWidget(self.body)
        top = QHBoxLayout()
        top.setSpacing(ICON_GAP)
        top.addWidget(icon, 0, Qt.AlignTop)
        top.addLayout(column)

        self.keep = QCheckBox("Don't show this again")
        buttons = QDialogButtonBox()
        self.go = buttons.addButton("Continue", QDialogButtonBox.AcceptRole)
        self.quit = buttons.addButton("Quit", QDialogButtonBox.RejectRole)
        self.go.setDefault(True)
        self.go.clicked.connect(self.accept)
        self.quit.clicked.connect(self.leave)
        bottom = QHBoxLayout()
        bottom.setSpacing(self.style().pixelMetric(QStyle.PM_LayoutHorizontalSpacing))
        bottom.setContentsMargins(CHECK_INDENT, 0, 0, 0)
        bottom.addWidget(self.keep)
        bottom.addStretch()
        bottom.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(*MARGINS)
        lay.setSpacing(BUTTONS_GAP)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        lay.addLayout(top)
        lay.addLayout(bottom)
        self.go.setFocus()

    def leave(self):
        self.quitting = True
        self.reject()
