"""The model Simulated mode simulates, chosen before the main window opens. The choice made last is chosen again."""

from PySide6.QtWidgets import QApplication, QButtonGroup, QDialog, QDialogButtonBox, QRadioButton, QVBoxLayout

from .taskdialog import TaskDialog

KEY = "simulated/model"                          # the setting that holds the choice made last
HEADING = "Choose the ADI-2 to simulate"
# the options as in a Windows task dialog: indented under the heading, one every 22 px
OPTIONS_GAP = 29                                 # from the heading
OPTION_INDENT = 10
OPTION_HEIGHT = 21
OPTION_SPACING = 1
BUTTONS_GAP = 20                                 # from the options


class ModelChoice(TaskDialog):
    """choices: (key, name) of each model. Start, the default, or Cancel; Escape and closing the window are
    Cancel."""

    def __init__(self, choices, chosen):
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
        self.start = self.add_button("Start", QDialogButtonBox.AcceptRole, self.accept)
        self.add_button("Cancel", QDialogButtonBox.RejectRole, self.reject)
        self.start.setDefault(True)
        self.group.checkedButton().setFocus()

    def chosen(self):
        return self.keys[self.group.checkedId()]


def choose(settings, choices, ask=lambda dialog: dialog.exec() == QDialog.Accepted):
    """The key of the model the user chooses, remembered in settings; None when cancelled."""
    dialog = ModelChoice(choices, settings.value(KEY))
    if not ask(dialog):
        return None
    settings.setValue(KEY, dialog.chosen())
    return dialog.chosen()
