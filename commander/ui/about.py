"""About ADI-2 Commander: its version and what it was tested with; then whose it is, with the notice the GPL asks of
an interactive program and what it uses; last whose it is not. Below, where its source is and its license."""

import os
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from .. import __version__
from ..device import MODEL
from . import theme
from .widgets import INNER_GAP, Action

NAME = "ADI-2 Commander"
REPOSITORY = "https://github.com/atvandenbosch/adi2-commander"
ICON = 48                                        # px
PARAGRAPH_GAP = 12                               # px between paragraphs
LINE_HEIGHT = 125                                # % of the font's line spacing
TESTED_DSP, TESTED_USB = 62, 81                  # the device firmware this version was tested with
PARAGRAPHS = [
    "Tested with the %s, firmware DSP %d and USB %d, on Windows 11." % (MODEL, TESTED_DSP, TESTED_USB),
    "Copyright (C) 2026 Alexander van den Bosch<br>This program comes with ABSOLUTELY NO WARRANTY. It is free "
    "software under the GNU General Public License, version 3 or later; you are welcome to redistribute it under "
    "its conditions.",
    "Uses Qt for Python, Copyright (C) The Qt Company Ltd. and other contributors, under the GNU LGPL, version 3; "
    "NumPy (BSD) and pyqtgraph (MIT). Their licenses are in the licenses folder of the installation.",
    "Not affiliated with or endorsed by RME, the maker of the ADI-2; both names are trademarks of their owner.",
]
# the GPL: beside Commander.exe in an installation (tools/build.py), at the root of the source otherwise
LICENSE = (os.path.join(os.path.dirname(sys.executable), "LICENSE.txt") if getattr(sys, "frozen", False)
           else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "LICENSE"))


def show_file(path):
    """Open a file in the app Windows has for it."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def show_url(url):
    """Open a web page in the browser."""
    QDesktopServices.openUrl(QUrl(url))


class AboutDialog(QDialog):
    def __init__(self, parent=None, icon=None):
        super().__init__(parent)
        self.setWindowTitle("About " + NAME)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(INNER_GAP)

        # the icon, and beside it name and version as one block, centred on the icon
        head = QHBoxLayout()
        head.setSpacing(INNER_GAP)
        if icon is not None and not icon.isNull():
            mark = QLabel()
            mark.setPixmap(icon.pixmap(ICON, ICON))
            mark.setFixedSize(ICON, ICON)
            head.addWidget(mark, 0, Qt.AlignVCenter)
        title = QLabel('<div style="font-size: 13pt; color: %s;">%s</div>'
                       '<div style="color: %s; margin-top: 2px;">Version %s</div>'
                       % (theme.TEXT.name(), NAME, theme.SECONDARY.name(), __version__))
        head.addWidget(title, 1, Qt.AlignVCenter)
        lay.addLayout(head)

        body = QLabel("".join('<p style="margin: 0 0 %dpx 0; line-height: %d%%;">%s</p>'
                              % (PARAGRAPH_GAP, LINE_HEIGHT, t) for t in PARAGRAPHS))
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet("color: %s;" % theme.LABEL.name())
        lay.addWidget(body)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.repository = Action()
        self.repository.setText("GitHub")
        self.repository.setToolTip(REPOSITORY)
        self.repository.clicked.connect(lambda: show_url(REPOSITORY))
        buttons.addWidget(self.repository)
        self.license = Action()
        self.license.setText("License")
        self.license.setEnabled(os.path.exists(LICENSE))
        self.license.clicked.connect(lambda: show_file(LICENSE))
        buttons.addWidget(self.license)
        close = Action()
        close.setText("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        self.setFixedWidth(460)
