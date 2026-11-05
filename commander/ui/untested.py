"""The notice when a model Commander has not been tested with is connected: once per run, unless the user chose
not to see it again in this version of Commander. Not in Simulated mode."""

from PySide6.QtWidgets import QCheckBox, QMessageBox

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
NBSP = "\u00a0"
TITLE_PT = 12                                    # a dialog's title on Windows, over text of 9 pt


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


class UntestedBox(QMessageBox):
    """Not tested with the model: a title over the text, as Windows lays out such a notice, and the app's name in
    the title bar. Continue or Quit, and Don't show this again."""

    def __init__(self, parent, model):
        super().__init__(QMessageBox.Warning, "ADI-2 Commander", "", parent=parent)
        self.title = TITLE % {"name": model.name}
        self.setText('<span style="font-size: %dpt; color: %s;">%s</span>'
                     % (TITLE_PT, theme.TEXT.name(), _whole(self.title, model.name)))
        self.setInformativeText(_whole(TEXT % {"name": model.name}, model.name))
        self.keep = QCheckBox("Don't show this again")
        self.setCheckBox(self.keep)
        self.go = self.addButton("Continue", QMessageBox.AcceptRole)
        self.quit = self.addButton("Quit", QMessageBox.RejectRole)
        self.setDefaultButton(self.go)
        self.setEscapeButton(self.go)              # dismissed: on, as with Continue
