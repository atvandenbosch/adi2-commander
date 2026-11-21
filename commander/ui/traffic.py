"""The MIDI traffic with the device, as it went (commander.device.traffic): one row per message sent, buffer
received or change of the port, the newest at the bottom, followed while the list is scrolled to the end.

    time        when Commander sent the message, collected the buffer from the port, or the port changed
    →  ←  ·     sent (violet), received (lime), the port (grey)
    bytes       in hex; for the port, what happened to it

A row whose buffer is not exactly one SysEx message has its bytes in amber, and where it is not in its tooltip. The
selected row shows below in full: the bytes 8 or 16 to a line, as many as fit, with their place and as ASCII, and
where it is not one message. The grip on the panel's right edge makes it wider.

Above the list, which rows: all, sent, received, the port, or irregular (not exactly one SysEx message); and a
filter: terms separated by commas, each looked for in the row as it reads (time, bytes in hex or the port's text)
and in its bytes as ASCII; Show keeps the rows with any of them, Hide the rows with none. Below the list: Pause
holds the list, the recording goes on; Clear deletes the recording; Copy and Save take the selected rows, or all
rows shown when none is selected, one line each with the bytes in full. Serial numbers in port names show as #1,
#2, …: one number each, the same for as long as Commander runs.

Opened by Ctrl+click on the connection light or Ctrl+Shift+T (the window); closing it hides its tab again.
"""

import datetime
import platform
import re
import time

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QStyledItemDelegate, QTableView, QVBoxLayout, QWidget)

from .. import __version__
from ..device.traffic import ENTRIES, irregular
from . import theme
from .widgets import ATTACHED_GAP, INNER_GAP, TITLE_STYLE, Action, Segmented, head

ARROWS = {"out": "→", "in": "←", "port": "·"}
COLORS = {"out": theme.SENT, "in": theme.RECEIVED, "port": theme.SECONDARY}
KIND_NAMES = {"out": "sent", "in": "received", "port": "port"}
# which rows: (name, tooltip, kind or 'irregular' or None for all)
SHOWN = (("All", "", None), ("Sent", "Messages Commander sent", "out"),
         ("Received", "Buffers Commander received", "in"),
         ("Port", "Opening, closing and failures of the port", "port"),
         ("Irregular", "Not exactly one SysEx message, f0 to f7", "irregular"))
PAUSE_TIP, RESUME_TIP = "Holds the list; recording goes on", "Follows the recording again"
FLUSH = 100                                      # ms between bringing new rows into the list
TYPED = 250                                      # ms after the last key before the filter applies: a full
                                                 # recording takes a moment to go through
PER_LINE = (16, 8)                               # bytes on a line of the selected row: the most that fit
FONT = 8.5
# a serial number in a port name: letters and digits, at least one digit, in parentheses at the end of a name
SERIAL = re.compile(r"\((?=[0-9A-Za-z]*\d)([0-9A-Za-z]{4,})\)")


def clock(t):
    """The time of day of t, to the millisecond. Formatted by hand: the filter does this for every row."""
    s = time.localtime(t)
    return "%02d:%02d:%02d.%03d" % (s.tm_hour, s.tm_min, s.tm_sec, int(t % 1 * 1000))


def cross_icon(ratio, size=16, arm=3.5):
    """A plain ×, in the labels' colour, in the text's under the mouse; ratio: the screen's device pixel ratio."""
    icon = QIcon()
    for mode, color in ((QIcon.Normal, theme.LABEL), (QIcon.Active, theme.TEXT)):
        pixmap = QPixmap(round(size * ratio), round(size * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(color, 1.3, Qt.SolidLine, Qt.RoundCap))
        c = size / 2
        p.drawLine(QPointF(c - arm, c - arm), QPointF(c + arm, c + arm))
        p.drawLine(QPointF(c - arm, c + arm), QPointF(c + arm, c - arm))
        p.end()
        icon.addPixmap(pixmap, mode)
    return icon


class Serials:
    """#1, #2, … for the serial numbers in a text, one each, in the order they are first seen."""

    def __init__(self):
        self.seen = {}

    def __call__(self, text):
        return SERIAL.sub(lambda m: "(#%d)" % self.seen.setdefault(m.group(1), len(self.seen) + 1), text)


def hex_bytes(data):
    return bytes(data).hex(" ")


NO_CHARACTER = {b: "·" for b in range(256) if not 0x20 <= b < 0x7F}


def ascii_bytes(data):
    """Each byte as its ASCII character, · where it has none that prints: so . is always 2e."""
    return bytes(data).decode("latin-1").translate(NO_CHARACTER)


class TrafficModel(QAbstractTableModel):
    def __init__(self, traffic, serials):
        super().__init__()
        self.traffic, self.serials = traffic, serials
        self.rows = []                           # the entries shown
        self.shown, self.paused = None, False
        self.terms, self.hide = [], False        # the filter's terms, lower case; whether it hides what they find
        self.times = False                       # whether a term can be part of a time
        self.waiting = []                        # entries recorded since the last flush
        traffic.on_entry.append(self._recorded)

    def _recorded(self, entry):
        if not self.paused:
            self.waiting.append(entry)

    def text(self, entry):
        return self.serials(entry.data) if entry.kind == "port" else hex_bytes(entry.data)

    def irregular(self, entry):
        return [] if entry.kind == "port" else irregular(entry.data)

    def shows(self, entry):
        if self.shown == "irregular":
            if not self.irregular(entry):
                return False
        elif self.shown is not None and entry.kind != self.shown:
            return False
        if not self.terms:
            return True
        reads = [ARROWS[entry.kind], self.text(entry)]
        if self.times:                               # the time only where a term can be part of one
            reads.append(clock(entry.t))
        if entry.kind != "port":
            reads.append(ascii_bytes(entry.data))
        reads = " ".join(reads).lower()
        return any(t in reads for t in self.terms) != self.hide

    def set_filter(self, text, hide):
        self.terms = [t.strip().lower() for t in text.split(",") if t.strip()]
        self.times = any(re.fullmatch(r"[\d:.]+", t) for t in self.terms)
        self.hide = hide

    def refilter(self):
        self.beginResetModel()
        self.rows = [e for e in self.traffic.entries if self.shows(e)]
        self.waiting = []
        self.endResetModel()

    def clear(self):
        self.traffic.clear()
        self.refilter()

    def flush(self):
        """The rows recorded since the last flush; the oldest go where there are more than ENTRIES."""
        new, self.waiting = [e for e in self.waiting if self.shows(e)], []
        if new:
            self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows) + len(new) - 1)
            self.rows += new
            self.endInsertRows()
        if len(self.rows) > ENTRIES:
            self.beginRemoveRows(QModelIndex(), 0, len(self.rows) - ENTRIES - 1)
            del self.rows[:len(self.rows) - ENTRIES]
            self.endRemoveRows()
        return bool(new)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def data(self, index, role=Qt.DisplayRole):
        e = self.rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return (clock(e.t), ARROWS[e.kind], self.text(e))[col]
        if role == Qt.ForegroundRole:
            if col == 0:
                return theme.SECONDARY
            return theme.WARN if col == 2 and self.irregular(e) else COLORS[e.kind]
        if role == Qt.ToolTipRole:
            if col == 1:
                return KIND_NAMES[e.kind].capitalize()
            return "\n".join(self.irregular(e)) or None if col == 2 else None
        return None

    def line(self, entry):
        """One line of Copy and Save: the time, the arrow, the bytes or the port's text, where it is irregular."""
        irregular = self.irregular(entry)
        return "%s  %s  %s%s" % (clock(entry.t), ARROWS[entry.kind], self.text(entry),
                                 "  [%s]" % "; ".join(irregular) if irregular else "")

    def detail(self, entry, per_line):
        """The selected row in full, per_line bytes to a line; what it is, its content, where it is irregular, each
        apart."""
        head = "%s  %s" % (clock(entry.t), KIND_NAMES[entry.kind])
        if entry.kind == "port":
            return head + "\n\n" + self.text(entry)
        lines = [head + ", %d bytes" % len(entry.data), ""]
        for at in range(0, len(entry.data), per_line):
            chunk = entry.data[at:at + per_line]
            lines.append("%04d  %-*s  %s" % (at, per_line * 3 - 1, hex_bytes(chunk), ascii_bytes(chunk)))
        irregular = self.irregular(entry)
        return "\n".join(lines + ([""] + irregular if irregular else []))


class KeepColor(QStyledItemDelegate):
    """A selected row keeps the colour of its text: only its background shows the selection."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        color = index.data(Qt.ForegroundRole)
        if color is not None:
            option.palette.setColor(QPalette.HighlightedText, color)


class Grip(QWidget):
    """The panel's right edge, to drag it wider or narrower: dragged emits the width it asks for."""

    dragged = Signal(int)
    released = Signal()
    WIDTH = 6

    def __init__(self, panel):
        super().__init__()
        self.panel, self.start, self.hover = panel, None, False
        self.setFixedWidth(self.WIDTH)
        self.setCursor(Qt.SplitHCursor)
        self.setToolTip("Drag to resize")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.start = (e.globalPosition().x(), self.panel.width())

    def mouseMoveEvent(self, e):
        if self.start is not None:
            x, width = self.start
            self.dragged.emit(round(width + e.globalPosition().x() - x))

    def mouseReleaseEvent(self, e):
        if self.start is not None:
            self.start = None
            self.released.emit()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def paintEvent(self, e):
        if self.hover or self.start is not None:
            QPainter(self).fillRect(self.width() // 2 - 1, 0, 2, self.height(), theme.BORDER)


class TrafficPanel(QWidget):
    def __init__(self, traffic, note, folder):
        """note(text, color): a line in the status bar; folder(): where Save offers to save."""
        super().__init__()
        self.note, self.folder = note, folder
        self.model = TrafficModel(traffic, Serials())
        title = QLabel("MIDI")
        title.setStyleSheet(TITLE_STYLE)
        self.shown = Segmented([name for name, _, _ in SHOWN], padding="2px 7px")
        for button, (_, tip, _) in zip(self.shown.buttons, SHOWN):
            button.setToolTip(tip)
        self.shown.changed.connect(self.show_rows)
        self.way = Segmented(["Show", "Hide"], padding="2px 7px")
        self.way.buttons[0].setToolTip("Rows with any of the terms")
        self.way.buttons[1].setToolTip("Rows with none of the terms")
        self.way.changed.connect(lambda _: self.set_filter())
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter")
        self.filter.setToolTip("Terms separated by commas")
        self.empty = self.filter.addAction(cross_icon(self.devicePixelRatioF()), QLineEdit.TrailingPosition)
        self.empty.setToolTip("Clear the filter")
        self.empty.setVisible(False)
        self.empty.triggered.connect(self.filter.clear)
        self.filter.textChanged.connect(lambda text: self.empty.setVisible(bool(text)))
        self.typed = QTimer(self, singleShot=True, interval=TYPED, timeout=self.set_filter)
        self.filter.textChanged.connect(self.typed.start)
        self.pause, self.clear, self.copy, self.save = (Action(compact=True) for _ in range(4))
        for action, text, tip, slot in ((self.pause, "Pause", PAUSE_TIP, self.toggle_pause),
                                        (self.clear, "Clear", "Deletes what was recorded", self.clear_rows),
                                        (self.copy, "Copy", "The selected rows, or all rows shown", self.copy_rows),
                                        (self.save, "Save…", "The selected rows, or all rows shown, as a text file",
                                         self.save_rows)):
            action.setText(text)
            action.setToolTip(tip)
            action.clicked.connect(slot)
        self.pause.setText("Resume")                     # as wide as its longer name: Clear stays where it is
        self.pause.setFixedWidth(self.pause.sizeHint().width())
        self.pause.setText("Pause")

        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(KeepColor(self.view))
        selection = self.view.palette()                  # dark enough for the colours of the rows to stay apart
        for group in (QPalette.Active, QPalette.Inactive):
            selection.setColor(group, QPalette.Highlight, theme.BORDER)
        self.view.setPalette(selection)
        self.view.setFont(theme.mono_font(FONT))
        self.view.setShowGrid(False)
        self.view.setWordWrap(False)
        self.view.setTextElideMode(Qt.ElideRight)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.verticalHeader().hide()
        self.view.horizontalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(self.view.fontMetrics().height() + 4)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        fm = self.view.fontMetrics()
        self.view.setColumnWidth(0, fm.horizontalAdvance("00:00:00.000") + 10)
        self.view.setColumnWidth(1, fm.horizontalAdvance("→") + 10)
        self.view.selectionModel().selectionChanged.connect(self.show_detail)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFont(theme.mono_font(FONT))
        self.detail.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.detail.setFixedHeight(fm.height() * 7 + 12)

        actions = QHBoxLayout()
        actions.setSpacing(6)                            # as Import and Export, in a head line
        actions.addWidget(self.pause)
        actions.addWidget(self.clear)
        actions.addSpacing(INNER_GAP)
        actions.addWidget(self.copy)
        actions.addWidget(self.save)
        actions.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(head(title))
        lay.addSpacing(ATTACHED_GAP)
        lay.addWidget(self.shown)
        lay.addSpacing(ATTACHED_GAP)
        filtering = QHBoxLayout()
        filtering.setSpacing(6)
        filtering.addWidget(self.way)
        filtering.addWidget(self.filter, 1)
        lay.addLayout(filtering)
        lay.addSpacing(ATTACHED_GAP)
        lay.addWidget(self.view, 1)
        lay.addSpacing(ATTACHED_GAP)
        lay.addWidget(self.detail)
        lay.addSpacing(ATTACHED_GAP)
        lay.addLayout(actions)

        self.timer = QTimer(self, interval=FLUSH, timeout=self.flush)
        self.timer.start()
        self.model.refilter()

    def show_rows(self, i):
        self.model.shown = SHOWN[i][2]
        self.refilter()

    def set_filter(self):
        self.model.set_filter(self.filter.text(), self.way.current == 1)
        self.refilter()

    def toggle_pause(self):
        self.model.paused = not self.model.paused
        self.pause.setText("Resume" if self.model.paused else "Pause")
        self.pause.setToolTip(RESUME_TIP if self.model.paused else PAUSE_TIP)
        if not self.model.paused:
            self.refilter()

    def clear_rows(self):
        self.model.clear()
        self.show_detail()

    def refilter(self):
        self.model.refilter()
        self.view.scrollToBottom()

    def flush(self):
        if not self.isVisible() or self.model.paused:
            return
        bar = self.view.verticalScrollBar()
        at_end = bar.value() == bar.maximum()
        if self.model.flush() and at_end:
            self.view.scrollToBottom()

    def showEvent(self, e):
        super().showEvent(e)
        if not self.model.paused:
            self.refilter()                      # what was recorded while it was closed

    def per_line(self):
        """The most bytes to a line of the detail that fit its width."""
        room = self.detail.viewport().width() - 8
        char = self.detail.fontMetrics().horizontalAdvance("0")
        return next((n for n in PER_LINE if (4 + 2 + 3 * n - 1 + 2 + n) * char <= room), PER_LINE[-1])

    def show_detail(self):
        rows = self.view.selectionModel().selectedRows()
        self.detail.setPlainText(self.model.detail(self.model.rows[rows[-1].row()], self.per_line())
                                 if len(rows) == 1 else "")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.show_detail()

    def chosen(self):
        rows = sorted(i.row() for i in self.view.selectionModel().selectedRows())
        return [self.model.rows[r] for r in rows] if rows else list(self.model.rows)

    def copy_rows(self):
        rows = self.chosen()
        QApplication.clipboard().setText("\n".join(self.model.line(e) for e in rows) + "\n")
        self.note("%d rows of MIDI traffic copied" % len(rows))

    def save_rows(self):
        rows = self.chosen()
        if not rows:
            return
        start = datetime.datetime.fromtimestamp(rows[0].t)
        name = "ADI-2 Commander MIDI %s.txt" % start.strftime("%Y-%m-%d %H%M%S")
        path, _ = QFileDialog.getSaveFileName(self, "Save MIDI traffic", "%s/%s" % (self.folder(), name),
                                              "Text (*.txt)")
        if not path:
            return
        header = ["ADI-2 Commander %s, Windows %s" % (__version__, platform.version()),
                  "MIDI traffic of %s, %d rows" % (start.strftime("%Y-%m-%d"), len(rows)),
                  "time: when Commander sent a message, collected a buffer from the port, or the port changed",
                  "→ sent  ← received  · the port; serial numbers in port names as #1, #2", ""]
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(header + [self.model.line(e) for e in rows]) + "\n")
        except OSError as e:
            self.note("MIDI traffic not saved: %s" % e, theme.WARN)
            return
        self.note("%d rows of MIDI traffic saved" % len(rows))
