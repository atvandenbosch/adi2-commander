"""The model Simulated mode simulates, chosen before the main window opens, unless the user chose not to be asked
again in this version of Commander, and from the menu. The choice made last is chosen again."""

from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QRadioButton,
                               QVBoxLayout)

from .. import __version__
from .taskdialog import TaskDialog

KEY = "simulated/model"                          # the setting that holds the choice made last
NOT_ASKED = "simulated/not-asked"                # the version of Commander in which the user chose not to be asked
HEADING = "Choose the ADI-2 to simulate"
MENU_TIP = "Start with this device without asking\nTo change that later, go to Menu › Simulated device…"
# the options as in a Windows task dialog: indented under the heading, one every 22 px
OPTIONS_GAP = 29                                 # from the heading
OPTION_INDENT = 10
OPTION_HEIGHT = 21
OPTION_SPACING = 1
BUTTONS_GAP = 20                                 # from the options


class ModelChoice(TaskDialog):
    """choices: (key, name) of each model. Above Start, the default, and Cancel whether to ask at the start of the app:
    at the start Don't ask again, from the menu Ask at startup, checked as asked. Escape and closing the window are
    Cancel."""

    def __init__(self, choices, chosen, from_menu=False, asked=True):
        super().__init__(None, "ADI-2 Commander (simulated)", QApplication.windowIcon(), HEADING, OPTIONS_GAP,
                         BUTTONS_GAP)
        options = QVBoxLayout()
        options.setContentsMargins(OPTION_INDENT, 0, 0, 0)
        options.setSpacing(OPTION_SPACING)
        self.group = QButtonGroup(self)
        self.keys = [k for k, _ in choices]
        for i, (k, name) in enumerate(choices):
            option = QRadioButton(name)
            option.setFixedHeight(OPTION_HEIGHT)
            option.setChecked(k == chosen or (i == 0 and chosen not in self.keys))
            self.group.addButton(option, i)
            options.addWidget(option)
        self.column.addLayout(options)
        self.from_menu = from_menu
        self.check = QCheckBox("Ask at startup" if from_menu else "Don't ask again")
        self.check.setChecked(asked if from_menu else not asked)
        if not from_menu:
            self.check.setToolTip(MENU_TIP)
        self.column.addWidget(self.check)
        self.start = self.add_button("Start", QDialogButtonBox.AcceptRole, self.accept)
        self.add_button("Cancel", QDialogButtonBox.RejectRole, self.reject)
        self.start.setDefault(True)
        self.group.checkedButton().setFocus()

    def chosen(self):
        return self.keys[self.group.checkedId()]

    def asks(self):
        """Whether to ask at the start of the app."""
        return self.check.isChecked() == self.from_menu


def not_asked(settings):
    return settings.value(NOT_ASKED) == __version__


def remembered(settings, choices):
    """The key of the model chosen last when the user chose not to be asked again in this version, else None."""
    key = settings.value(KEY)
    return key if not_asked(settings) and key in dict(choices) else None


def choose(settings, choices, ask=lambda dialog: dialog.exec() == QDialog.Accepted, from_menu=False):
    """The key of the model the user chooses, remembered in settings with whether to ask at the start of the app;
    None when cancelled."""
    dialog = ModelChoice(choices, settings.value(KEY), from_menu, not not_asked(settings))
    if not ask(dialog):
        return None
    settings.setValue(KEY, dialog.chosen())
    if dialog.asks():
        settings.remove(NOT_ASKED)
    else:
        settings.setValue(NOT_ASKED, __version__)
    return dialog.chosen()
