"""Dialogs laid out as a Windows task dialog, in pixels at 100 %: the icon in the corner, the heading and what goes
with it in one column beside it, and at the bottom a row with the buttons at the right. Escape and closing the
window reject the dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLayout, QStyle, QVBoxLayout)

from . import theme

ICON = 32
MARGINS = (10, 10, 11, 10)                       # left, top, right, bottom
ICON_GAP = 10                                    # from the icon to the column
WIDTH = 287                                      # of the column
HEADING_PT = 12                                  # over text of 9 pt


class TaskDialog(QDialog):
    """heading over column, which the dialog fills; content_gap below the heading, buttons_gap above the buttons."""

    def __init__(self, parent, title, icon, heading, content_gap, buttons_gap):
        super().__init__(parent)
        self.setWindowTitle(title)
        mark = QLabel()
        mark.setPixmap(icon.pixmap(ICON, ICON))
        mark.setFixedSize(ICON, ICON)
        self.heading = QLabel('<span style="font-size: %dpt; color: %s;">%s</span>'
                              % (HEADING_PT, theme.TEXT.name(), heading))
        self.heading.setWordWrap(True)
        self.heading.setFixedWidth(WIDTH)
        self.column = QVBoxLayout()
        self.column.setSpacing(content_gap)
        self.column.addWidget(self.heading)
        top = QHBoxLayout()
        top.setSpacing(ICON_GAP)
        top.addWidget(mark, 0, Qt.AlignTop)
        top.addLayout(self.column)

        self.buttons = QDialogButtonBox()
        self.bottom = QHBoxLayout()
        self.bottom.setSpacing(self.style().pixelMetric(QStyle.PM_LayoutHorizontalSpacing))
        self.bottom.addStretch()
        self.bottom.addWidget(self.buttons)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(*MARGINS)
        lay.setSpacing(buttons_gap)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        lay.addLayout(top)
        lay.addLayout(self.bottom)

    def add_button(self, text, role, slot):
        """A button in the row at the bottom, in the order of Windows for its role, calling slot when clicked."""
        button = self.buttons.addButton(text, role)
        button.clicked.connect(slot)
        return button
