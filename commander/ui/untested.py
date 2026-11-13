"""The notice when a model Commander has not been tested with is connected: once per run, unless the user chose
not to see it again in this version of Commander. Not in Simulated mode."""

from PySide6.QtWidgets import QApplication, QCheckBox, QDialogButtonBox, QLabel, QPushButton, QStyle

from .. import __version__
from .taskdialog import WIDTH, TaskDialog

ORGANIZATION, APPLICATION = "ADI-2 Commander", "Commander"   # where QSettings keeps what the app remembers
TITLE = "Not tested with the %(name)s"
TEXT = ("Commander has not been tested with an actual %(name)s.\n\n"
        "Commander keeps a copy of the device's state as it was when connected, in the backups folder. "
        "Restore it with ADI-2 Remote: File › Open Setup File…\n\n"
        "To explore the app first, or to convert filter sets and curves for your %(name)s, no device is needed: "
        "start ADI-2 Commander (simulated) from the Start menu.")
# kept on one line each when the text wraps
WHOLE = ("ADI-2 Remote", "File › Open Setup File…", "ADI-2 Commander (simulated)")
NBSP = " "
TEXT_GAP = 14                                    # from the title to the text
BUTTONS_GAP = 24                                 # from the text to the row of buttons


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


class UntestedBox(TaskDialog):
    """Not tested with the model, with the app's name in the title bar. Continue or Quit, Don't show this again above
    them. Escape and closing the window are Continue. open_folder: shows the backups folder, from View backups at the
    left of the buttons, which leaves the notice open."""

    def __init__(self, parent, model, open_folder=None):
        title = TITLE % {"name": model.name}
        warning = QApplication.style().standardIcon(QStyle.SP_MessageBoxWarning)
        super().__init__(parent, "ADI-2 Commander", warning, _whole(title, model.name), TEXT_GAP, BUTTONS_GAP)
        self.title = title
        self.quitting = False
        self.body = QLabel(_whole(TEXT % {"name": model.name}, model.name))
        self.body.setWordWrap(True)
        self.body.setFixedWidth(WIDTH)
        self.column.addWidget(self.body)
        self.keep = QCheckBox("Don't show this again")
        self.column.addWidget(self.keep)
        self.folder = None
        if open_folder is not None:
            self.folder = QPushButton("View backups")
            self.folder.setAutoDefault(False)
            self.folder.clicked.connect(open_folder)
            self.bottom.insertWidget(0, self.folder)
        self.go = self.add_button("Continue", QDialogButtonBox.AcceptRole, self.accept)
        self.quit = self.add_button("Quit", QDialogButtonBox.RejectRole, self.leave)
        self.go.setDefault(True)
        self.go.setFocus()

    def leave(self):
        self.quitting = True
        self.reject()
