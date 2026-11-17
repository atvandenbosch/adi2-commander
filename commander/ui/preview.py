"""A preset seen before anything is done with it. While the mouse is on a slot's row, Clear or Rumble, this lies over the
left of the graph, level with the row; the window places it and closes it when the mouse leaves the row. One small
graph of what the preset holds; nothing in it can be clicked. What can be done with the preset, the row itself offers
while the mouse is on it (commander.ui.presets).

    the graph   at rest what the slot holds: the EQ, a line per channel, with Dual EQ off one in the shared colour;
                Bass and Treble together as a line of their own. Nothing for an unused slot, nor for a slot not read
                yet. While the mouse is on the row's Select, what Select loads on this output: for an unused slot the
                factory state, as for Clear; the Bass/Treble line grey where Load Bass/Treble with preset is off, as
                it does not come along. The output's switches (EQ, Bass/Treble) are not drawn.
"""

import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..device import filters as F
from ..device import models
from ..device import params as P
from ..session import built_in, loaded
from . import theme
from .graph import X_HI, X_LO, Y_HI, Y_LO, side_color
from .presets import BUILT_IN, RUMBLE

GRAPH_SIZE = 266, 107                            # px: 25 dB as long as a decade, one of the ratios of IEC 60263
POINTS = 240                                     # along the graph: at least one per pixel
GRID_DB = (-12, -6, 6, 12)
GRID_HZ = (100, 1000, 10000)
LINE_W = 1.5                                     # px: the EQ and Bass/Treble alike, thinner than in the main graph
PAD = 4                                          # px from the outline to the graph



def lines(content, fs, freqs):
    """The lines of what a slot holds ({'dual', 'vals'}, as session.loaded gives it) at the frequencies freqs: the EQ
    as [(side, dB)], one side with Dual EQ off; and Bass and Treble together, in dB."""
    state = dict(content["vals"])
    state.update({(13, P.EQ_ENABLE): 1, (14, P.EQ_ENABLE): 1, (13, P.BT_ENABLE): 1})
    sides = (0, 1) if content["dual"] else (0,)
    eq = [(side, F.total_db(F.band_filters(state, 13 + side, 13), freqs, fs)) for side in sides]
    return eq, F.total_db(F.bt_filters(state, 13), freqs, fs)


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
    def __init__(self, parent):
        super().__init__(parent)
        self.no_bt_from = models.DAC.no_bt_from  # of the model: no Bass/Treble from this rate on
        self.value = None
        self.load_bt = True
        self.no_bt = False                       # the device has no Bass/Treble at the graph's rate
        self.held = ([], None)                   # the graph's lines at rest: what the slot holds
        self.loads = ([], None)                  # and with the mouse on Select: what Select loads on this output
        self.on_select = False                   # the mouse is on the row's Select
        self.graph = PreviewGraph()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(PAD, PAD, PAD, PAD)
        lay.addWidget(self.graph)
        self.hide()

    def show_preset(self, value, stored, load_bt, fs, has_bt=True):
        """value: Clear's, Rumble's or a slot's EQ Preset Select value; stored: the slot as read, None while not read
        (Clear, Rumble: not used); load_bt: Load Bass/Treble with preset on this output; fs: the rate of the main
        graph; has_bt: this output has Bass/Treble (the input has none: Select leaves the preset's out)."""
        self.value, self.load_bt, self.no_bt = value, load_bt and has_bt, fs >= self.no_bt_from
        clear = value in BUILT_IN
        known = clear or stored is not None
        used = not clear and known and stored["used"]
        self.loads = ([], None)
        if known:
            eq, bt = lines(loaded(stored) if used else built_in(value == RUMBLE), fs, self.graph.freqs)
            dual = len(eq) == 2
            self.loads = ([(side_color(side, dual), db) for side, db in eq], bt)
        self.held = self.loads if used or clear else ([], None)
        self.show_graph(self.on_select)

    def show_graph(self, on_select):
        """At rest what the slot holds; with the mouse on Select what Select loads on this output."""
        self.on_select = on_select
        self.graph.show_lines(*(self.loads if on_select else self.held))
        self.graph.set_bt_off(self.no_bt or (on_select and not self.load_bt))

    def paintEvent(self, e):
        """As a tooltip: it comes and goes with the mouse."""
        p = QPainter(self)
        p.setPen(QPen(theme.GRID, 1))
        p.setBrush(theme.PANEL)
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
