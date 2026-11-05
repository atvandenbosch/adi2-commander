"""What Loudness does, for the settings of this output: the full boost, and the response at the current volume, each
line at its own volume (dB to the reference, 0 dB) plus the boost of the two shelves there
(commander.device.filters.loudness_filters). Shown in the place of the response graph while one works in the
Loudness table.

The axis spans 30 dB around Low Vol Ref, as high as the response graph: from 5 dB below it to 5 dB above the
lowest volume without boost, so where Loudness acts is always in the same place. The reference and the current
volume can lie outside it.

    Loudness            thin, as a band in the response graph: the full boost, at Low Vol Ref; the main curve
    No boost            as the Loudness curve: flat at Low Vol Ref + 20 dB, the lowest volume without boost
    Handles             as in the response graph
    At current volume   the line of the family at the output's volume, lit, when it is in view (if only in part)
    behind them the family: the response at every 0.5 dB of volume, faint and dotted, to show how Loudness
    follows the volume; in the legend as the response graph's: the curves as its channels, then the layers

    a point per shelf as the handles of the response graph: a ring at its frequency and full gain above Low Vol
    Ref, and B or T in the label lane; and one for Low Vol Ref, at the lowest of the full boost (the middle of it,
    where it is flat)

    press a point       selects its row in the table (also on its label)
    drag a shelf        its gain, on the device's grid; frequency and Q are fixed in the device
    drag Low Vol Ref    as a joystick: the point and the curves stay, the scale and the grid move, the faster the
                        further the mouse is from where it was pressed, as long as the button is down
    the Loudness lines dimmed with Loudness off, as the table, and from 705.6 kHz, where the device has no
    Loudness; a legend above the graph (self.legend)
"""

import math
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolTip, QWidget

from ..device import filters as F
from ..device import models
from ..device import params as P
from . import theme
from .graph import (BAND_ALPHA, BAND_W, GRAB, LANE_PX, RING, X_HI, X_LO, X_PAD, Y_HI, Y_LO,
                    _pen, _ticks, title_axes)
from .legend import GROUP_GAP, ITEM_PAD, MARK_H, MARK_W, mark_pixmap

FLAT_DB = 0.01                                   # dB: this close to its lowest, the full boost counts as flat
FAMILY_STEP = 0.5                                # dB between the curves of the family, over the whole view: the
                                                 # device's step of volume, so the current volume is one of them
FAMILY_BELOW = P.OUTPUT_RANGES[P.LD_BASS][1] / 2   # dB below the view: the most boost brings these into it
FAMILY_ALPHA = 0.25
FAMILY_DOTS = [1, 3]                             # px on, off: dotted, unlike the grid
NOW_ALPHA = 1.0                                  # the family's line at the current volume: lit
STICK_TICK = 40                                  # ms between the steps of the joystick, at the least
STICK_PX = 6                                     # pixels further per dB/s, up to STICK_MAX dB/s
STICK_MAX = 20.0
BELOW = 5.0                                      # dB in view below Low Vol Ref; above it the rest of the
                                                 # response graph's height
MARK_GAP, ITEM_GAP = 5, 16                       # pixels, as in the legend of the response graph
POINTS = 400


class Legend(QWidget):
    """Per line its mark, drawn as in the legend of the response graph, and its name: all labels as high as the row,
    the row in the middle. In groups as there: the curves, then the layers. Placed by the window's graph head as
    the response graph's legend is, on one row."""

    def __init__(self):
        super().__init__()
        self.shown = []                          # [(colour, mark kind, name)], None between groups
        self._row = QWidget()
        self._lay = QHBoxLayout(self._row)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(ITEM_PAD, 0, ITEM_PAD, 0)    # as the room around the response legend's items
        lay.addWidget(self._row, 0, Qt.AlignCenter)

    def names(self):
        return [item[2] for item in self.shown if item]

    def size_for(self, stacked):
        return self.sizeHint()

    def first_row_height(self):
        return self.sizeHint().height()

    def set_stacked(self, on, right=False):
        """Always one row: there are too few items to stack."""

    def show_items(self, items):
        if items == self.shown:
            return
        self.shown = items
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
        gap = 0
        for item in items:
            if item is None:
                gap = GROUP_GAP
                continue
            color, kind, name = item
            if self._lay.count():
                self._lay.addSpacing(gap or ITEM_GAP)
            gap = 0
            mark = QLabel()
            mark.setFixedSize(MARK_W, MARK_H)
            mark.setPixmap(mark_pixmap(kind, QColor(color)))
            label = QLabel(name)
            label.setStyleSheet("color: %s;" % theme.LABEL.name())
            for w, gap in ((mark, MARK_GAP), (label, 0)):
                self._lay.addWidget(w)
                self._lay.addSpacing(gap)


class _View(pg.ViewBox):
    """Mouse handling: a press on a point or its label chooses it, a drag of a point moves its gain. The view itself
    stays where it is."""

    def __init__(self, graph):
        super().__init__(enableMenu=False)
        self.graph = graph
        self._drag = None                        # (key, offset y; for Low Vol Ref the pixel y of the press)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            key = self.graph.handle_at(self, ev.pos())
            if key is not None:
                self.graph.pick(key)
        ev.ignore()

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() != Qt.LeftButton:
            return ev.ignore()
        if ev.isStart():
            key = self.graph.handle_at(self, ev.buttonDownPos(), labels=False)
            if key is not None and key[1] == P.LD_LOW_VOL_REF:
                self._drag = (key, ev.buttonDownPos().y())     # the scale moves: count in pixels
                self.graph.stick_start(key)
            elif key is not None:
                self._drag = (key, self.graph.handle_y(key) - self.mapToView(ev.buttonDownPos()).y())
        if self._drag is None:
            return ev.ignore()
        ev.accept()
        key, start = self._drag
        if key[1] == P.LD_LOW_VOL_REF:
            self.graph.stick(ev.pos().y() - start)
        else:
            self.graph.drag_to(key, self.mapToView(ev.pos()).y() + start)
        if ev.isFinish():
            self._drag = None
            self.graph.stick_stop()

    def mouseClickEvent(self, ev):
        ev.accept() if ev.button() == Qt.LeftButton else ev.ignore()   # chosen on the press already

    def wheelEvent(self, ev, axis=None):
        ev.ignore()                              # nothing to zoom, and Q is fixed

    def hoverEvent(self, ev):
        if self._drag is not None:
            return                               # the cursor of the drag stays, wherever the mouse goes
        key = point = None
        if not ev.isExit():
            point = self.graph.handle_at(self, ev.pos(), labels=False)
            key = point or self.graph.handle_at(self, ev.pos())
        self.setCursor(Qt.SizeVerCursor if point else Qt.PointingHandCursor if key else Qt.ArrowCursor)
        self.graph.hover(key)


class LoudnessGraph(pg.PlotWidget):
    edited = Signal(object, int, bool)           # key, value, rounded: as the response graph
    picked = Signal(object)                      # key of the point's gain: select it in the table

    def __init__(self):
        self.view = _View(self)
        super().__init__(viewBox=self.view, background=theme.DISPLAY)
        self.no_bt_from = models.DAC.no_bt_from  # of the model: no Loudness from this rate on
        pi = self.getPlotItem()
        pi.hideButtons()
        pi.setMenuEnabled(False)
        pi.setMouseEnabled(False, False)
        pi.showGrid(x=True, y=True, alpha=0.6)
        for name in ("bottom", "left"):
            ax = pi.getAxis(name)
            ax.setPen(theme.DISPLAY_GRID)
            ax.setTextPen(theme.SECONDARY)
            ax.setStyle(tickFont=theme.ui_font(8))
            ax.setZValue(pi.getViewBox().zValue() - 1)    # the axes draw the grid; it lies behind the curves
        pi.getAxis("bottom").setTicks(_ticks())
        pi.getAxis("left").setTickSpacing(levels=[(10, 0), (5, 0), (1, 0)])  # per dB as in the response graph
        pi.getAxis("left").setStyle(maxTextLevel=1)
        title_axes(pi, "Volume (dB)")                    # the values are those of the device's volume
        self.x = np.linspace(X_LO, X_HI, POINTS)
        self.freqs = 10 ** self.x
        # the family: the response at every FAMILY_STEP of volume in view, behind the curves; one item, the
        # curves apart where it is not finite: one path to draw
        self.family = self.plot(self.x, np.zeros_like(self.x))
        self.family.setZValue(-1)
        self.family_levels = []                  # the volumes of its curves
        self.no_boost = self.plot(self.x, np.zeros_like(self.x))
        self.full_boost = self.plot(self.x, np.zeros_like(self.x))
        self.now = self.plot(self.x, np.zeros_like(self.x))
        self.handles = pg.ScatterPlotItem(pxMode=True)
        self.handles.setAcceptedMouseButtons(Qt.NoButton)
        self.handles.setZValue(0.5)                      # under the curves: they run through the rings
        self.addItem(self.handles)
        self.handle_labels = [pg.TextItem(anchor=(0.5, 1.0)) for _ in range(2)]   # B, T
        for t in self.handle_labels:
            t.setFont(theme.ui_font(8))
            t.setZValue(11)
            self.addItem(t)
        pi.getViewBox().sigResized.connect(self._place_labels)
        self.state, self.ref, self.on = {}, 0.0, False
        self._stick = None                       # (key, Low Vol Ref in dB, pixels from the press, time)
        self._stick_timer = QTimer(self, interval=STICK_TICK, timeout=self._stick_tick)
        self.full = []                           # the shelves at the full boost
        self.points = []                         # (key, x, y, label or None) per point: the shelves, Low Vol Ref
        self.current = None                      # key of the table's chosen row, if a shelf's
        self.hovered = None                      # key of the point under the mouse
        self.boost = None                        # (bass, treble) dB at the volume now, or None
        self.legend = Legend()                   # placed by the window, above the graph

    def update_from(self, state, out, fs=F.FS, bypassed=False, draw=True):
        """Draw for one output address at a sample rate; nothing while its values are not known. bypassed: DSD
        plays. draw False, while the graph is not on the stage: only the legend, which the window's head measures
        all the same."""
        shelves = F.loudness_filters(state, out)
        for item in [self.no_boost, self.full_boost, self.now, self.family, self.handles] + self.handle_labels:
            item.setVisible(bool(shelves))
        self.boost, self.full, self.points = None, [], []
        if not shelves:
            self.legend.show_items([])
            return
        on = self.on = shelves[0].active and not bypassed and fs < self.no_bt_from
        ref = self.ref = state[(out, P.LD_LOW_VOL_REF)] / 2
        self.state = state
        volume = state[(out, P.VOLUME)] / 10
        self.boost = (shelves[0].gain, shelves[1].gain)
        color = theme.LOUDNESS if on else theme.OFF
        lo, hi = ref - BELOW, ref - BELOW + (Y_HI - Y_LO)
        now = volume + self._boost_db(state, out, volume, fs)
        in_range = bool(now.max() >= lo and now.min() <= hi)   # in view, if only in part
        # the curves, then the layers, as in the response graph's legend; the current volume last
        items = [(color, "curve", "Loudness"), (color, "line", "No boost"), None, (color, "ring", "Handles")]
        items += [(color, "dotted", "At current volume")] if in_range else []
        self.legend.show_items([item and (item[0].name(), *item[1:]) for item in items])
        if not draw:
            return
        self.no_boost.setData(self.x, np.full_like(self.x, ref + F.LOUDNESS_RANGE))      # flat from here on
        self.no_boost.setPen(_pen(color, BAND_W, alpha=BAND_ALPHA))    # as the Loudness curve
        full = self._boost_db(state, out, ref, fs)
        self.full_boost.setData(self.x, ref + full)
        self.full_boost.setPen(_pen(color, BAND_W, alpha=BAND_ALPHA))  # as a band in the response graph
        levels = [lo - FAMILY_BELOW + k * FAMILY_STEP for k in range(int((hi - lo + FAMILY_BELOW) / FAMILY_STEP) + 1)]
        # Loudness and No boost are two of them, and the current volume is drawn lit
        self.family_levels = [v for v in levels if v not in (ref, ref + F.LOUDNESS_RANGE, volume)]
        ys = np.array(self.family_levels)[:, None] + F.loudness_db(state, out, self.family_levels, self.freqs, fs)
        apart = np.full((len(ys), 1), np.nan)            # each curve a row, ended by a gap
        self.family.setData(np.hstack([np.tile(self.x, (len(ys), 1)), apart]).ravel(),
                            np.hstack([ys, apart]).ravel(), connect="finite")
        pen = _pen(color, 1.0, alpha=FAMILY_ALPHA)
        pen.setDashPattern(FAMILY_DOTS)
        self.family.setPen(pen)
        self.now.setVisible(in_range)
        self.now.setData(self.x, now)
        pen = _pen(color, 1.0, alpha=NOW_ALPHA)
        pen.setDashPattern(FAMILY_DOTS)
        self.now.setPen(pen)
        self.setRange(xRange=(X_LO - X_PAD, X_HI + X_PAD), yRange=(lo, hi), padding=0)
        # the shelves' points, as the handles of the response graph: at the full boost, off its curve; Low Vol
        # Ref's at the lowest of it
        self.full = F.loudness_filters(state, out, volume=ref)
        self.points = [(self._key(f), math.log10(f.freq), ref + f.gain, f.name[-1]) for f in self.full]
        low = np.nonzero(full <= full.min() + FLAT_DB)[0]
        self.points.append(((out, P.LD_LOW_VOL_REF), (self.x[low[0]] + self.x[low[-1]]) / 2, ref + full.min(), None))
        self._draw_handles()
        self.setToolTip("Loudness: the full boost at Low Vol Ref (%.1f dB) and below, none from %.1f dB (No boost);\n"
                        "dotted: per 0.5 dB of volume, lit at the current volume, %.1f dB.\n"
                        "Shelves %g Hz and %g kHz, Q %g, fixed in the device"
                        % (ref, ref + F.LOUDNESS_RANGE, volume, shelves[0].freq, shelves[1].freq / 1000,
                           shelves[0].q))

    def _draw_handles(self):
        """As in the response graph: the chosen point's ring thicker, the one under the mouse larger; their labels
        bold, the others' a little faint."""
        color = theme.LOUDNESS if self.on else theme.OFF
        self.handles.setData([{"pos": (x, y), "size": RING + 2 if key == self.hovered else RING,
                               "brush": QColor(0, 0, 0, 0), "pen": _pen(color, 2.0 if key == self.current else 1.5)}
                              for key, x, y, _ in self.points])
        for t, (key, _, _, text) in zip(self.handle_labels, self._labelled()):
            lit = key in (self.current, self.hovered)
            c = QColor(color)
            c.setAlphaF(1.0 if lit else 0.75)
            font = theme.ui_font(8)
            font.setWeight(QFont.Bold if lit else QFont.Normal)
            t.setText(text)
            t.setColor(c)
            t.setFont(font)
        self._place_labels()

    def _labelled(self):
        return [p for p in self.points if p[3]]

    @staticmethod
    def _key(f):
        return (f.address, f.indices[1])        # the gain: its cell in the table

    def set_current(self, key):
        if key != self.current:
            self.current = key
            self._draw_handles()

    def handle_at(self, view, pos, labels=True):
        """The key of the point under pos (view item coordinates), or None; its label counts too."""
        best, best_d = None, GRAB
        for key, x, y, _ in self.points:
            p = view.mapFromView(QPointF(x, y))
            d = math.hypot(p.x() - pos.x(), p.y() - pos.y())
            if d < best_d:
                best, best_d = key, d
        if best is not None or not labels:
            return best
        return next((key for (key, _, _, _), t in zip(self._labelled(), self.handle_labels)
                     if view.mapRectFromScene(t.sceneBoundingRect()).contains(pos)), None)

    def handle_y(self, key):
        return next(y for k, _, y, _ in self.points if k == key)

    def pick(self, key):
        self.set_current(key)
        self.picked.emit(key)

    def drag_to(self, key, y):
        """The gain from y, the height above Low Vol Ref, on the device's grid of 0.5 dB."""
        lo, hi = P.OUTPUT_RANGES[key[1]]
        value = min(max(int(math.floor((y - self.ref) * 2 + 0.5)), lo), hi)
        if value != self.state.get(key):
            self.edited.emit(key, value, False)

    def stick_start(self, key):
        self._stick = (key, self.ref, 0.0, time.monotonic())
        self._stick_timer.start()

    def stick(self, dy):
        """The mouse is dy pixels below the press (above: negative)."""
        if self._stick is not None:
            key, ref, _, t = self._stick
            self._stick = (key, ref, dy, t)

    def stick_stop(self):
        self._stick = None
        self._stick_timer.stop()

    def _stick_tick(self):
        """Low Vol Ref moves at a speed from how far the mouse is from the press, up raises it; on the device's
        grid of 0.5 dB. Over the time that really passed: a redraw can hold the timer up. The view follows Low Vol
        Ref: the point and the curves stay, the scale moves."""
        if self._stick is None:
            return
        key, ref, dy, t = self._stick
        now = time.monotonic()
        speed = min(abs(dy) / STICK_PX, STICK_MAX)                           # dB/s
        lo, hi = (v / 2 for v in P.OUTPUT_RANGES[P.LD_LOW_VOL_REF])
        ref = min(max(ref - math.copysign(speed, dy) * (now - t), lo), hi)
        self._stick = (key, ref, dy, now)
        value = int(math.floor(ref * 2 + 0.5))
        if value != self.state.get(key):
            self.edited.emit(key, value, False)

    def hover(self, key):
        if key == self.hovered:
            return
        self.hovered = key
        self.view.setToolTip(self._describe(key) if key is not None else "")
        if key is None:
            QToolTip.hideText()
        self._draw_handles()

    def _describe(self, key):
        lo, hi = P.OUTPUT_RANGES[key[1]]
        if key[1] == P.LD_LOW_VOL_REF:
            lines = ["Loudness Low Vol Ref",
                     "%.1f dB: the volume with the full boost; none %g dB above it" % (self.ref, F.LOUDNESS_RANGE),
                     "%.1f … %.1f dB" % (lo / 2, hi / 2),
                     "Drag up or down and hold: Low Vol Ref moves, the faster the further; the curves stay, "
                     "the scale moves"]
            return "\n".join(lines)
        f = next(f for f in self.full if self._key(f) == key)
        lines = ["Loudness %s" % {"B": "Bass", "T": "Treble"}[f.name[-1]],
                 "%s  %d Hz  Q %.1f, fixed in the device" % ({"LS": "Low Shelf", "HS": "High Shelf"}[f.kind],
                                                              f.freq, f.q),
                 "+%.1f dB at and below Low Vol Ref · %.1f … %.1f dB" % (f.gain, lo / 2, hi / 2)]
        if not self.on:
            lines.append("Loudness not in the signal path")
        lines.append("Drag: gain")
        return "\n".join(lines)

    def _place_labels(self, *_):
        """The label lane a few pixels above the bottom of the view, as in the response graph."""
        vb = self.getPlotItem().getViewBox()
        (_, _), (y0, y1) = vb.viewRange()
        y = y0 + (y1 - y0) * LANE_PX / max(vb.height(), 1)
        for t, (_, x, _, _) in zip(self.handle_labels, self._labelled()):
            t.setPos(x, y)

    def _boost_db(self, state, out, volume, fs):
        shelves = [f._replace(active=True) for f in F.loudness_filters(state, out, volume=volume)]
        return F.total_db(shelves, self.freqs, fs)
