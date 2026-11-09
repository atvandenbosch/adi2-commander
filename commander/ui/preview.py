"""A preset seen before anything is done with it. Under the mouse a slot's row, Clear or Rumble opens this just past the
names in the presets panel, joined to the row as its tab, as the edit stand is (Scrim, without the veil); the window
places it and keeps it open while the mouse is on the row, on it, or between them. One small graph of what the preset
holds, and under it what can be done with it: Select, Edit, Store.

    the graph   at rest what the slot holds: the EQ, a line per channel, with Dual EQ off one in the shared colour;
                Bass and Treble together as a line of their own. Nothing for an unused slot, nor for a slot not read
                yet. While the mouse is on Select, what Select loads on this output: for an unused slot the factory
                state, as for Clear; the Bass/Treble line grey where Load Bass/Treble with preset is off, as it does
                not come along. The output's switches (EQ, Bass/Treble) are not drawn.
    Select      the preset becomes this output's source, as the device's EQ Preset Select; also when it is already,
                which loads it again as it is now. Amber when it changes more than the graph shows: an unused slot,
                Clear and Rumble switch Bass/Treble on where Load Bass/Treble with preset is on. Its tooltip says
                what it does.
    Edit        opens the edit stand on the slot.
    Store       this output's EQ goes into the slot.

Clear and Rumble have Select only: they are no slots.
"""

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..device import filters as F
from ..device import models
from ..device import params as P
from ..session import built_in, loaded
from . import theme
from .graph import X_HI, X_LO, Y_HI, Y_LO, side_color
from .presets import BUILT_IN, RUMBLE, ROW_HEIGHT
from .scrim import RADIUS, RISE
from .widgets import ATTACHED_GAP, Action, head

GRAPH_SIZE = 264, 112                            # px
POINTS = 240                                     # along the graph: about one per pixel
GRID_DB = (-12, -6, 6, 12)
GRID_HZ = (100, 1000, 10000)
LINE_W = 1.5                                     # px: the EQ and Bass/Treble alike, thinner than in the main graph
PAD = 10                                         # px from the outline to the graph and the actions
ACTIONS_HEIGHT = 20                              # px: as high as an action

EDIT_TIP = "Edit this preset and its name; nothing goes to the device until OK"
EDIT_FREE_TIP = "This preset is unused: it starts as the factory state"
NOT_READ = "Not read from the device yet"
FACTORY = "Select loads the factory state on %s: all bands 0 dB, Dual EQ off"
RUMBLE_LOAD = "Select loads Rumble on %s: a high pass at 35 Hz, -12 dB at 20 Hz, Dual EQ off"


def lines(content, fs, freqs):
    """The lines of what a slot holds ({'dual', 'vals'}, as session.loaded gives it) at the frequencies freqs: the EQ
    as [(side, dB)], one side with Dual EQ off; and Bass and Treble together, in dB."""
    state = dict(content["vals"])
    state.update({(13, P.EQ_ENABLE): 1, (14, P.EQ_ENABLE): 1, (13, P.BT_ENABLE): 1})
    sides = (0, 1) if content["dual"] else (0,)
    eq = [(side, F.total_db(F.band_filters(state, 13 + side, 13), freqs, fs)) for side in sides]
    return eq, F.total_db(F.bt_filters(state, 13), freqs, fs)


def store_tip(slot, stored, output, others):
    """What Store does, a line each. slot: its number; stored: the slot as read, or None; others: the other outputs
    that have the preset selected."""
    lines = ["Store the current EQ of %s in Preset %d, Bass/Treble included" % (output, slot),
             "It replaces what the preset holds; the name stays" if stored is None else
             "It replaces what the graph shows; the name stays" if stored["used"] else
             "Preset %d is unused: it becomes used, with the name it shows" % slot]
    selected = "Afterwards Preset %d is selected on %s" % (slot, output)
    lines.append(selected + (" and loaded again on %s" % " and ".join(others) if others else ""))
    return "\n".join(lines)


def select_tip(value, used, current, output, load_bt):
    """What Select does on this output, a line each. value: its EQ Preset Select value."""
    clear = value in BUILT_IN
    if clear:
        first = (RUMBLE_LOAD if value == RUMBLE else FACTORY) % output
    elif not used:
        first = "This preset is unused\n" + FACTORY % output
    elif current:
        first = "Select it again: %s loads it as it is now" % output
    else:
        first = "Select it on %s: its EQ is loaded there" % output
    if not load_bt:
        second = "Bass/Treble stays as it is: Load Bass/Treble with preset is off"
    elif clear or not used:
        second = "Bass/Treble 0 dB and switched on: Load Bass/Treble with preset is on"
    else:
        second = "Its Bass/Treble comes along: Load Bass/Treble with preset is on"
    return first + "\n" + second


class PreviewGraph(QWidget):
    """The lines of a preset over a grid, from 20 Hz to 20 kHz and -15 to +15 dB as the main graph starts; nothing
    to point at or drag."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(*GRAPH_SIZE)
        self.log_f = np.linspace(X_LO, X_HI, POINTS)       # not x: that is the widget's place
        self.freqs = 10 ** self.log_f
        self.eq = []                             # [(colour, dB)]
        self.bt = None                           # dB of Bass and Treble together, or None
        self.bt_off = False                      # grey: it does not come along, or the device has none at this rate

    def show_lines(self, eq, bt):
        self.eq, self.bt = eq, bt
        self.update()

    def set_bt_off(self, off):
        if off != self.bt_off:
            self.bt_off = off
            self.update()

    def _point(self, x, db):
        w, h = self.width() - 1, self.height() - 1
        return QPointF((x - X_LO) / (X_HI - X_LO) * w, (Y_HI - db) / (Y_HI - Y_LO) * h)

    def _line(self, p, db, color, width):
        path = QPainterPath(self._point(self.log_f[0], db[0]))
        for x, y in zip(self.log_f[1:], db[1:]):
            path.lineTo(self._point(x, y))
        p.setPen(QPen(color, width))
        p.drawPath(path)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.DISPLAY)
        p.setPen(QPen(theme.DISPLAY_GRID, 1))
        for hz in GRID_HZ:
            x = round(self._point(np.log10(hz), 0).x()) + 0.5
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        for db in GRID_DB:
            y = round(self._point(X_LO, db).y()) + 0.5
            p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        zero = QColor(theme.SECONDARY)
        zero.setAlphaF(0.6)
        p.setPen(QPen(zero, 1))
        y = round(self._point(X_LO, 0).y()) + 0.5
        p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        p.setRenderHint(QPainter.Antialiasing)
        p.setClipRect(self.rect())
        if self.bt is not None:
            self._line(p, self.bt, theme.OFF if self.bt_off else theme.BT, LINE_W)
        for color, db in self.eq:
            self._line(p, db, color, LINE_W)


class PresetPreview(QWidget):
    selected = Signal(int)                       # an EQ Preset Select value
    edited = Signal(int)                         # a slot number
    stored = Signal(int)                         # a slot number

    def __init__(self, parent):
        super().__init__(parent)
        self.no_bt_from = models.DAC.no_bt_from  # of the model: no Bass/Treble from this rate on
        self.value = None
        self.load_bt = True
        self.no_bt = False                       # the device has no Bass/Treble at the graph's rate
        self.held = ([], None)                   # the graph's lines at rest: what the slot holds
        self.loads = ([], None)                  # and with the mouse on Select: what Select loads on this output
        self.graph = PreviewGraph()
        self.select, self.edit, self.store = Action(compact=True), Action(compact=True), Action(compact=True)
        self.select.setText("Select")
        self.edit.setText("Edit")
        self.store.setText("Store")
        self.select.clicked.connect(lambda: self.selected.emit(self.value))
        self.edit.clicked.connect(lambda: self.edited.emit(self.value - 1))
        self.store.clicked.connect(lambda: self.stored.emit(self.value - 1))
        for b in (self.select, self.edit, self.store):
            b.setFocusPolicy(Qt.NoFocus)         # the preview closes on a click: the focus stays where it was
        self.select.installEventFilter(self)
        self.actions = head(self.select, self.edit, self.store)
        self.actions.setFixedHeight(ACTIONS_HEIGHT)
        lay = QVBoxLayout(self)
        # below the actions only so much that they lie level with the row while the tab's lower edge runs on as the
        # preview's (the window places it so)
        lay.setContentsMargins(PAD, PAD, PAD, ROW_HEIGHT // 2 + RISE - ACTIONS_HEIGHT // 2)
        lay.setSpacing(ATTACHED_GAP)
        lay.addWidget(self.graph)
        lay.addWidget(self.actions)
        self.hide()

    def page(self):
        """What the outline goes around (Scrim.cover, with no margin): the preview itself."""
        return [self]

    def show_preset(self, value, stored, output, load_bt, current, fs, others=()):
        """value: Clear's, Rumble's or a slot's EQ Preset Select value; stored: the slot as read, None while not read
        (Clear, Rumble: not used); output: the name of this output; load_bt: Load Bass/Treble with preset on this
        output; current: selected on this output; fs: the rate of the main graph; others: the other outputs it is
        selected on."""
        self.value, self.load_bt, self.no_bt = value, load_bt, fs >= self.no_bt_from
        clear = value in BUILT_IN
        known = clear or stored is not None
        used = not clear and known and stored["used"]
        self.loads = ([], None)
        if known:
            eq, bt = lines(loaded(stored) if used else built_in(value == RUMBLE), fs, self.graph.freqs)
            dual = len(eq) == 2
            self.loads = ([(side_color(side, dual), db) for side, db in eq], bt)
        self.held = self.loads if used or clear else ([], None)
        self.show_graph(self.select.underMouse())
        self.select.setEnabled(known)
        self.select.setToolTip(select_tip(value, used, current, output, load_bt) if known else NOT_READ)
        self.select.warn(known and not used and load_bt)        # the factory state: Bass/Treble switched on
        self.edit.setVisible(not clear)
        self.store.setVisible(not clear)
        self.edit.setEnabled(known)
        self.edit.setToolTip(NOT_READ if not known else EDIT_TIP if used else EDIT_TIP + "\n" + EDIT_FREE_TIP)
        if not clear:
            self.store.setToolTip(store_tip(value - 1, stored, output, others))

    def show_graph(self, on_select):
        """At rest what the slot holds; with the mouse on Select what Select loads on this output."""
        self.graph.show_lines(*(self.loads if on_select else self.held))
        self.graph.set_bt_off(self.no_bt or (on_select and not self.load_bt))

    def eventFilter(self, obj, e):
        if obj is self.select and e.type() in (QEvent.Enter, QEvent.Leave):
            self.show_graph(e.type() == QEvent.Enter)
        return False

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.BACKGROUND)
        p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
