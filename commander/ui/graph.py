"""The response graph: per channel the curve of every band and their sum, left and right together, as the
device runs them (commander.device.filters); with Dual EQ off one set for both, in the shared colour. A point
per band to drag (frequency, and gain where it has an effect) and to wheel (Q); Bass and Treble are shared and
drawn once.

    drag a point        frequency and gain, on the device's grid
    wheel on a point    Q (Shift large, Ctrl finest steps)
    click a point       selects its row in the table
    its label           in the lane below, at f0: as the point, but a drag changes the frequency only
    wheel elsewhere     zoom; drag elsewhere: pan; double-click: back to the full view
    on an axis          the wheel and a drag zoom and pan that axis only

What is shown (commander.ui.legend): the channels EQ Left, EQ Right and Bass/Treble, and the layers Sum, Compare (the
sums at the rate the device runs at, dashed, when it is known and not the chosen one; off at first), Bands and Handles
(the points); a point shows when both its channel and Handles are on. The band labels show with their channel; with
Handles off they only inform and take no mouse. The curves are computed at a chosen sample rate. Visibility never
changes the sums: they are what the device runs.

The lines: colour is the channel; weight is rank, the sum strongest and none so thick that one looks for its middle;
the line style is the layer, solid for what the device runs, dashed for the comparison. Out of the path (EQ or
Bass/Treble off) a band is grey, as a switch that is off; on but bypassed (DSD) faded. A band shows where it does
something and fades out in its tails. Nothing grows to stand out: the rest steps back.

Two marks per band, each with one meaning. Chosen (1.5 px, full, a fill to 0 dB): the row one works in, shared with
the table; set by pressing a point or its label, by any edit from the graph (drag, wheel), or by a cell. Attention
(all but its band steps back): only in the graph, while the mouse is on a point or its label or its button is down.
Pointing at a legend item sets back what does not belong to it.
"""

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QLinearGradient, QPen
from PySide6.QtWidgets import QToolTip

from ..device import filters as F
from ..device import models
from ..device import params as P
from . import theme

F_LO, F_HI = 20.0, 20000.0
X_LO, X_HI = math.log10(F_LO), math.log10(F_HI)
Y_LO, Y_HI = -15.0, 15.0
X_PAD = 0.035                                    # room for the axis labels at 20 Hz and 20 kHz
POINTS_PER_PIXEL = 2                             # curves are computed over the frequencies in view
MIN_POINTS = 400
GRAB = 12                                        # pixels: how close the mouse must be to take a point
RING = 11                                        # pixels: the drawn point, smaller than where it can be taken
LANE_PX = 4                                      # pixels: the label lane above the bottom of the view
OFF_CURVE_DB = 0.5                               # a chosen point this far from its own curve gets a centre dot
                                                 # (shelf, High Pass/Cut); on a Peak the curve marks it already
DOT = 3                                          # pixels: that centre dot
# pyqtgraph draws a symbol into an image ceil(size + pen width) wide, where no pen counts as 1 px. An odd width puts
# the symbol's centre on a pixel's centre, as the ring's (11 + 2): the dot gets an invisible pen of 2 px for 3 + 2.
DOT_PEN = QPen(Qt.NoPen)
DOT_PEN.setWidthF(2)
# the lines, in pixels at 100 % scaling: the sum the strongest, none so thick that one looks for its middle to read
SUM_W, CHOSEN_W, BAND_W, COMPARE_W = 2.0, 1.5, 1.0, 1.5     # bands: Qt draws exactly 1 px three times as fast
INPUT_W, INPUT_ALPHA = 3 * SUM_W, 0.5           # a curve fitted to (Import): wide and see-through, under the sum
BAND_ALPHA = 0.6                                 # a band beside the sum
DEVIATION_W, DEVIATION_FILL = 1.0, 0.2           # how far the sum is off the input (Import): a thin edge to an area
BAND_FLOOR, BAND_FULL = 0.02, 0.5               # dB: in its tails a band fades in from this much to this much:
                                                 # on 0 dB the tails of all bands would add up to a line of their own
FADE_STOPS = 60                                  # colour stops along a band's line: about one per 20 px
DIMMED = 0.35                                    # what steps back: all but the band with the attention, or what a
                                                 # legend item pointed at does not show
CHANNEL = [theme.LEFT, theme.RIGHT]
pg.setConfigOptions(antialias=True)

SAMPLE_RATES = P.SAMPLE_RATES
CHANNEL_KEY = {0: "L", 1: "R", None: "BT"}


def _ticks():
    major = [(math.log10(f), t) for f, t in ((20, "20"), (50, "50"), (100, "100"), (200, "200"), (500, "500"),
                                             (1000, "1k"), (2000, "2k"), (5000, "5k"), (10000, "10k"),
                                             (20000, "20k"))]
    minor = [(math.log10(m * d), "") for d in (10, 100, 1000) for m in (3, 4, 6, 7, 8, 9)]
    return [major, minor]


# pixels left of and under the plot area: the values and the axis title, the title as close to the values on both
# to the eye: under, 3 px more, as a line under a line reads closer than a column beside a column
AXIS_WIDTH, AXIS_HEIGHT = 41, 34
# a graph lies in a zone of its own, darker than what is beside it
ZONE_INK = 16                                    # pixels from the graph's zone to what is drawn in it: left,
                                                 # right and below; the head stays on the line of the columns
TITLE_ROOM = 3, 1                                # pixels pyqtgraph leaves left of the dB axis title, below the other
LEGEND_GAP = 8                                   # a graph's legend line over it: part of the graph
AXIS_TIPS = {"bottom": "Frequency: wheel to zoom, drag to pan",
             "left": "Gain: wheel to zoom, drag to pan"}


def title_axes(plot_item, y_title):
    """Classic axis titles, small and grey as the values: the frequency below, the dB axis along it. And a line on
    the right that closes the plot area, as the dB axis does on the left."""
    for name, title in (("bottom", "Frequency (Hz)"), ("left", y_title)):
        plot_item.getAxis(name).setLabel(title, color=theme.SECONDARY.name(), **{"font-size": "8pt"})
    plot_item.getAxis("left").setWidth(AXIS_WIDTH)
    plot_item.getAxis("bottom").setHeight(AXIS_HEIGHT)
    plot_item.showAxis("right")
    right = plot_item.getAxis("right")
    right.setStyle(showValues=False, tickLength=0)
    right.setGrid(False)                         # the grid is the dB axis's
    right.setPen(theme.DISPLAY_GRID)
    right.setWidth(1)


def side_color(side, dual):
    """Per channel its own colour; with Dual EQ off the one EQ for both in the shared colour; None: Bass/Treble."""
    return theme.BT if side is None else CHANNEL[side] if dual else theme.SHARED


def _pen(color, width=1.0, alpha=1.0, style=Qt.SolidLine):
    c = QColor(color)
    c.setAlphaF(alpha)
    p = QPen(c, width)
    p.setStyle(style)
    p.setCosmetic(True)
    return p


def _tail_fade(y):
    """Per frequency the share of a band's opacity: whole from the first to the last frequency where it does
    something (BAND_FULL, or half its own peak when that is less), so a dip through 0 dB or a small gain stays;
    outside that, in its tails, rising out of the 0 dB line from BAND_FLOOR, on a log scale of dB. A band that
    does nothing at all is not drawn: its point shows it."""
    m = np.abs(y)
    top = m.max()
    if top < BAND_FLOOR:
        return np.zeros_like(m)
    full = min(BAND_FULL, top / 2)
    lo, hi = math.log10(BAND_FLOOR), math.log10(full)
    a = np.clip((np.log10(np.maximum(m, 1e-9)) - lo) / ((hi - lo) or 1.0), 0.0, 1.0)
    inside = np.nonzero(m >= full)[0]
    a[inside[0]:inside[-1] + 1] = 1.0
    return a


def _fading_pen(color, width, alpha, x, y):
    """A band's pen whose opacity fades in its tails (_tail_fade)."""
    a = _tail_fade(y) * alpha
    gradient = QLinearGradient(x[0], 0, x[-1], 0)       # in data coordinates: along the frequency axis
    span = (x[-1] - x[0]) or 1.0
    c = QColor(color)
    for i in range(0, len(x), max(1, len(x) // FADE_STOPS)):
        c.setAlphaF(float(a[i]))
        gradient.setColorAt(float((x[i] - x[0]) / span), QColor(c))
    p = QPen(QBrush(gradient), width)
    p.setCosmetic(True)
    return p


class Point:
    """A draggable point: one filter of one channel (side 0 left, 1 right, None shared)."""

    def __init__(self, flt, side, x, y):
        self.flt, self.side, self.x, self.y = flt, side, x, y
        self.key = (flt.address, flt.name)       # identifies the point across redraws


class _View(pg.ViewBox):
    """Mouse handling: on a point the gestures edit, elsewhere they zoom and pan as usual."""

    def __init__(self, graph):
        super().__init__(enableMenu=False)
        self.graph = graph
        self._drag = None                        # (point, offset x, offset y) while a point is dragged

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() != Qt.LeftButton:
            return super().mouseDragEvent(ev, axis)
        if ev.isStart():
            pt = self.graph.point_at(self, ev.buttonDownPos(), labels=False)
            by_label = pt is None
            if by_label:
                pt = self.graph.point_at(self, ev.buttonDownPos())
            if pt is not None:
                down = self.mapToView(ev.buttonDownPos())
                self._drag = (pt, pt.x - down.x(), pt.y - down.y(), by_label)
                self.setCursor(Qt.SizeHorCursor if by_label else Qt.SizeAllCursor)   # for the whole drag
                self.graph.pick(pt)
                self.graph.hold(pt.key)
        if self._drag is None:
            return super().mouseDragEvent(ev, axis)
        ev.accept()
        pt, dx, dy, by_label = self._drag
        here = self.mapToView(ev.pos())
        self.graph.drag_to(pt, here.x() + dx, None if by_label else here.y() + dy)
        if ev.isFinish():
            self._drag = None
            self.graph.hold(None)

    def mousePressEvent(self, ev):
        """Pressing a point chooses it at once and keeps the attention on it until the button is up; the press
        goes on, for the click or the drag."""
        if ev.button() == Qt.LeftButton:
            pt = self.graph.point_at(self, ev.pos())
            if pt is not None:
                self.graph.pick(pt)
                self.graph.hold(pt.key)
        ev.ignore()

    def wheelEvent(self, ev, axis=None):
        pt = self.graph.point_at(self, ev.pos())
        if pt is None:
            return super().wheelEvent(ev, axis)
        ev.accept()
        mods = ev.modifiers()
        size = "large" if mods & Qt.ShiftModifier else "finest" if mods & Qt.ControlModifier else "small"
        if pt.key != self.graph.current:
            self.graph.pick(pt)                  # who edits, has chosen
        self.graph.step_q(pt, 1 if ev.delta() > 0 else -1, size)

    def mouseClickEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return super().mouseClickEvent(ev)
        ev.accept()
        pt = self.graph.point_at(self, ev.pos())
        if pt is not None:
            self.graph.pick(pt)
        elif ev.double():
            self.graph.reset_view()

    def hoverEvent(self, ev):
        if self._drag is not None:
            return                               # the cursor of the drag stays, wherever the mouse goes
        pt = by_label = None
        if not ev.isExit():
            pt = self.graph.point_at(self, ev.pos(), labels=False)
            by_label = pt is None
            if by_label:
                pt = self.graph.point_at(self, ev.pos())
        self.setCursor(Qt.ArrowCursor if pt is None else Qt.SizeHorCursor if by_label else Qt.SizeAllCursor)
        self.graph.hover(pt, bool(by_label))


class ResponseGraph(pg.PlotWidget):
    edited = Signal(object, int, bool)           # key, value, rounded: like the table delegates
    picked = Signal(object)                      # key of the point's frequency: select it in the table

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if self.view._drag is None:
            self.hold(None)                      # the button up, also without a drag: the attention follows the mouse

    def __init__(self, session):
        self.view = _View(self)
        super().__init__(viewBox=self.view, background=theme.DISPLAY)
        self.session = session
        self.prefer_side = 0                     # which channel wins when a left and a right point coincide
        self.current = None                      # (address, filter name) of the table's current row
        self.points = []
        self.hovered = None                      # key of the point under the mouse
        self.hovered_by_label = False            # ... through its label
        self.dual = True
        self.has_bt = True                       # the output shown has Bass/Treble; the input has none
        self.visible = {"L": True, "R": True, "BT": True, "sum": True, "compare": False, "bands": True, "handles": True}
        self.emphasis = None                     # a legend item under the mouse: its curves light up
        self.held = None                         # the key of a point while the mouse button is down on it
        self._off = set()                        # (side, filter name) set but out of the path: EQ or B/T off
        self.fs = 48000
        self.fs_compare = None                   # the rate the device runs at, when known and not fs; or None
        self.no_bt_from = models.DAC.no_bt_from  # of the model: no Bass/Treble from this rate on

        pi = self.getPlotItem()
        pi.hideButtons()
        pi.setMenuEnabled(False)
        pi.showGrid(x=True, y=True, alpha=0.6)
        for name in ("bottom", "left"):
            ax = pi.getAxis(name)
            ax.setPen(theme.DISPLAY_GRID)
            ax.setTextPen(theme.SECONDARY)
            ax.setStyle(tickFont=theme.ui_font(8))
            ax.setZValue(self.view.zValue() - 1)        # the axes draw the grid; it lies behind the curves
        pi.getAxis("bottom").setTicks(_ticks())
        pi.getAxis("left").setTickSpacing(levels=[(6, 0), (3, 0), (1, 0)])   # a faint line per dB, without a value
        pi.getAxis("left").setStyle(maxTextLevel=1)
        title_axes(pi, "Gain (dB)")
        pi.getAxis("bottom").setToolTip(AXIS_TIPS["bottom"])
        pi.getAxis("left").setToolTip(AXIS_TIPS["left"])
        self.view.setLimits(xMin=X_LO - X_PAD, xMax=X_HI + X_PAD, yMin=-60, yMax=40, minXRange=0.3, minYRange=3)
        self.reset_view()
        self.addItem(pg.InfiniteLine(pos=0, angle=0, pen=_pen(theme.SECONDARY, alpha=0.6)))

        # a fixed set of items, updated in place: a refresh comes with every step of a drag
        self.output = None
        self.x = x = np.linspace(X_LO, X_HI, MIN_POINTS)
        self.freqs = 10 ** x
        self.band_items = {}                     # (side, name) -> curve of one band
        for side in (0, 1):
            for name in "12345":
                self.band_items[(side, name)] = self.plot(x, np.zeros_like(x))
        for name in "BT":
            self.band_items[(None, name)] = self.plot(x, np.zeros_like(x))
        self.sum_items = [self.plot(x, np.zeros_like(x)) for _ in (0, 1)]
        self.compare_items = [self.plot(x, np.zeros_like(x)) for _ in (0, 1)]
        for item in list(self.band_items.values()) + self.sum_items + self.compare_items:
            item.setVisible(False)
        self.scatter = pg.ScatterPlotItem(pxMode=True)
        self.scatter.sigClicked.connect(self._scatter_clicked)   # the scatter takes clicks on its spots itself
        self.addItem(self.scatter)
        self.scatter.setZValue(0.5)                               # under the curves: they run through the rings
        self.dots = pg.ScatterPlotItem(pxMode=True)              # the centre of the chosen point
        self.dots.setAcceptedMouseButtons(Qt.NoButton)
        self.addItem(self.dots)
        self.dots.setZValue(11)                                   # off its own curve: nothing to cover
        self._label_font = theme.ui_font(8)
        self._label_font_lit = theme.ui_font(8)
        self._label_font_lit.setBold(True)
        self.labels = []
        for _ in range(12):
            t = pg.TextItem(anchor=(0.5, 1.0))
            t.setFont(self._label_font)
            t.setVisible(False)
            t.setZValue(11)
            self.addItem(t)
            self.labels.append(t)
        self.view.sigRangeChanged.connect(self._resample)
        self.view.sigResized.connect(self._resample)
        self.view.sigRangeChanged.connect(self._place_labels)
        self.view.sigResized.connect(self._place_labels)

    # -- drawing ------------------------------------------------------------------------------
    def reset_view(self):
        self.view.setRange(xRange=(X_LO - X_PAD, X_HI + X_PAD), yRange=(Y_LO, Y_HI), padding=0)

    def _sample(self):
        """The frequencies to compute: the part of 20 Hz .. 20 kHz in view, POINTS_PER_PIXEL per pixel. True
        when they changed."""
        lo, hi = self.view.viewRange()[0]
        lo, hi = max(lo, X_LO), min(hi, X_HI)
        n = max(MIN_POINTS, int(self.view.width() * POINTS_PER_PIXEL))
        if hi <= lo or (len(self.x) == n and self.x[0] == lo and self.x[-1] == hi):
            return False
        self.x = np.linspace(lo, hi, n)
        self.freqs = 10 ** self.x
        return True

    def _resample(self, *_):
        if self._sample() and self.output is not None:
            self.update_from(self.output)

    def redraw(self):
        if self.output is not None:
            self.update_from(self.output)

    def _bt_at(self, bt, fs):
        """Bass/Treble as the device runs it at this sample rate: not at all from no_bt_from on."""
        return [f._replace(active=False) for f in bt] if fs >= self.no_bt_from else bt

    def _lit(self, *keys):
        return self.emphasis is not None and self.emphasis in keys

    def _attention(self):
        """The key of the band the mouse is on: held while its button is down, else pointed at; or None."""
        return self.held if self.held is not None else self.hovered

    def _dimmed(self, *keys, band=None):
        """Whether this steps back: a band has the attention and this is not that band (band: its key, address and
        filter name), or a legend item is pointed at and it is none of keys."""
        if self._attention() is not None:
            return band != self._attention()
        return self.emphasis is not None and self.emphasis not in keys

    def hold(self, key):
        """The mouse button is down on a point (key), or up (None): meanwhile the attention stays on it, wherever
        the mouse goes."""
        if key != self.held:
            self.held = key
            self.redraw()

    def _color(self, key, flt, color):
        """Out of the path (EQ or Bass/Treble off): grey, as a switch that is off; on but bypassed (DSD): faded."""
        return theme.OFF if key in self._off else color if flt.active else theme.faded(color)

    def update_from(self, output):
        """Redraw from the session state for this output (name, out, left address, right address)."""
        self.output = output
        self._sample()
        s = self.session.state
        _, out, left, right = output
        ready = self.session.ready()
        dual = self.dual = s.get(P.dual_eq_key(out)) == 1
        sides = [(0, left)] + ([(1, right)] if dual else []) if ready else []
        bt = self._bt_at(F.bt_filters(s, left), self.fs) if ready else []
        self.has_bt = not ready or bool(bt)
        self._off = {(None, f.name) for f in bt if not f.active}     # set, but out of the path
        bypassed = ready and self.session.bypassed()
        bt = [f._replace(active=False) for f in bt] if bypassed else bt
        bands_bypassed = bypassed or ready and self.session.eq_bypassed(out)
        shown = set()
        self.points = []
        for side, address in sides:
            bands = F.band_filters(s, address, left)
            if not bands:
                continue
            self._off |= {(side, f.name) for f in bands if not f.active}
            bands = [f._replace(active=False) for f in bands] if bands_bypassed else bands
            ch = CHANNEL_KEY[side]
            color = side_color(side, dual)
            for flt in bands:
                if self.visible[ch] and self.visible["bands"]:
                    self._band_curve((side, flt.name), flt, color, (address, flt.name) == self.current,
                                     (ch, "bands"))
                    shown.add((side, flt.name))
                if self.visible[ch]:
                    self.points.append(Point(flt, side, math.log10(flt.freq), self._point_y(flt)))
            item = self.sum_items[side]
            item.setData(self.x, F.total_db(bands + bt, self.freqs, self.fs))
            item.setPen(_pen(color, SUM_W, DIMMED if self._dimmed(ch, "sum") else 1.0))
            item.setVisible(self.visible[ch] and self.visible["sum"])
            item.setZValue(5)
            cmp = self.compare_items[side]
            if self.fs_compare is not None:
                bt2 = self._bt_at(F.bt_filters(s, left), self.fs_compare)
                cmp.setData(self.x, F.total_db(bands + bt2, self.freqs, self.fs_compare))
                cmp.setPen(_pen(color, COMPARE_W, DIMMED if self._dimmed(ch, "compare") else 0.9, Qt.DashLine))
            cmp.setVisible(self.fs_compare is not None and self.visible[ch] and self.visible["compare"])
            cmp.setZValue(4)
        for flt in bt if sides else []:
            if self.visible["BT"] and self.visible["bands"]:
                self._band_curve((None, flt.name), flt, theme.BT, (left, flt.name) == self.current,
                                 ("BT", "bands"))
                shown.add((None, flt.name))
            if self.visible["BT"]:
                self.points.append(Point(flt, None, math.log10(flt.freq), self._point_y(flt)))
        for side in (0, 1):
            if not any(sd == side for sd, _ in sides):
                self.sum_items[side].setVisible(False)
                self.compare_items[side].setVisible(False)
        for key, item in self.band_items.items():
            if key not in shown:
                item.setVisible(False)
        self._draw_points()
        pt = self._hovered()
        if pt is not None:                                 # an open tooltip shows the new values
            self.view.setToolTip(self._describe(pt))
            if QToolTip.isVisible():
                QToolTip.showText(QCursor.pos(), self.view.toolTip(), self.viewport())
        elif self.hovered is not None:
            self.hover(None)

    def _hovered(self):
        return next((p for p in self.points if p.key == self.hovered), None)

    def _band_curve(self, key, flt, color, current, keys):
        """One band: thinner and fainter than the sum; the chosen one full, with a fill to 0 dB. keys: the legend
        items it belongs to."""
        item = self.band_items[key]
        y = F.response_db(flt, self.freqs, self.fs)
        item.setData(self.x, y)
        color = self._color(key, flt, color)
        band = (flt.address, flt.name)
        dimmed = self._dimmed(*keys, band=band)
        alpha = DIMMED if dimmed else 1.0 if current or band == self._attention() or self._lit(*keys) else BAND_ALPHA
        item.setPen(_fading_pen(color, CHOSEN_W if current else BAND_W, alpha, self.x, y))
        if current:
            fill = QColor(color)
            fill.setAlphaF(0.14 * (DIMMED if dimmed else 1.0))      # stepping back, the fill goes with it
            item.setFillLevel(0)
            item.setBrush(fill)
        else:
            item.setFillLevel(None)
            item.setBrush(None)
        item.setZValue(3 if current else 1)
        item.setVisible(True)

    @staticmethod
    def _point_y(flt):
        """At the gain. A High Pass or High Cut has no gain: its point sits on the 0 dB line, independent of Q."""
        return 0.0 if flt.kind in ("HP", "LP") else flt.gain

    def _draw_points(self):
        """A ring per point, open so the curve shows through; its number in the label lane below, at f0.
        Pointing at Handles in the legend lights them all: thicker rings, labels at full colour."""
        rings, dots = [], []
        all_lit = self._lit("handles")
        for pt in self.points if self.visible["handles"] else []:
            c = QColor(self._color((pt.side, pt.flt.name), pt.flt, side_color(pt.side, self.dual)))
            if self._dimmed("handles", CHANNEL_KEY[pt.side], band=pt.key):
                c.setAlphaF(DIMMED)
            chosen, hovered = pt.key == self.current, pt.key == self.hovered
            rings.append({"pos": (pt.x, pt.y), "size": RING + 2 if hovered else RING, "brush": QColor(0, 0, 0, 0),
                          "pen": _pen(c, 2.0 if chosen else 1.5, c.alphaF())})
            if chosen and abs(F.response_db(pt.flt, [pt.flt.freq], self.fs)[0] - pt.y) > OFF_CURVE_DB:
                dots.append({"pos": (pt.x, pt.y), "size": DOT, "brush": c, "pen": DOT_PEN})
        self.scatter.setData(rings)
        self.dots.setData(dots)
        for i, t in enumerate(self.labels):
            if i < len(self.points):
                pt = self.points[i]
                lit = pt.key in (self.current, self.hovered)
                c = QColor(self._color((pt.side, pt.flt.name), pt.flt, side_color(pt.side, self.dual)))
                if self._dimmed("handles", CHANNEL_KEY[pt.side], band=pt.key):
                    c.setAlphaF(DIMMED)
                elif not lit and not all_lit:
                    c.setAlphaF(0.75)
                t.setText(pt.flt.name)
                t.setColor(c)
                t.setFont(self._label_font_lit if lit else self._label_font)
                t.setVisible(True)
            else:
                t.setVisible(False)
        self._place_labels()

    def _place_labels(self, *_):
        """The lane sits a few pixels above the bottom of the view, wherever the view is panned or zoomed."""
        (_, _), (y0, y1) = self.view.viewRange()
        h = max(self.view.height(), 1)
        y = y0 + (y1 - y0) * LANE_PX / h
        for pt, t in zip(self.points, self.labels):
            t.setPos(pt.x, y)

    # -- interaction --------------------------------------------------------------------------
    def point_at(self, view, pos, labels=True):
        """The point under pos (view item coordinates), or None; its label in the lane counts as the point too.
        A left and a right point (or label) on the same spot: the channel last worked on in the tables wins.
        With Handles off nothing can be taken: the labels only inform."""
        if not self.visible["handles"]:
            return None
        best, best_d = None, GRAB
        for pt in self.points:
            p = view.mapFromView(QPointF(pt.x, pt.y))
            d = math.hypot(p.x() - pos.x(), p.y() - pos.y())
            if d < best_d - 0.5 or (best is not None and abs(d - best_d) <= 0.5 and pt.side == self.prefer_side):
                best, best_d = pt, d
        if best is not None or not labels:
            return best
        on_label = [pt for pt, t in zip(self.points, self.labels)
                    if t.isVisible() and view.mapRectFromScene(t.sceneBoundingRect()).contains(pos)]
        return next((pt for pt in on_label if pt.side == self.prefer_side), on_label[0] if on_label else None)

    def hover(self, pt, by_label=False):
        key = pt.key if pt is not None else None
        if (key, by_label) != (self.hovered, self.hovered_by_label):
            self.hovered, self.hovered_by_label = key, by_label
            self.view.setToolTip(self._describe(pt) if pt is not None else "")
            if pt is None:
                QToolTip.hideText()
            self.redraw()                        # the attention: the rest steps back, or comes back

    def _describe(self, pt):
        """What the point is, its values and ranges, whether it is in the path, and what the mouse does."""
        f = pt.flt
        _, _, fi, qi = f.indices
        who = {None: "shared L/R", 0: "LEFT" if self.dual else "shared L/R", 1: "RIGHT"}[pt.side]
        name = {"B": "Bass", "T": "Treble"}.get(f.name, "Band " + f.name)
        kind = {"PK": "Peak", "LS": "Low Shelf", "HS": "High Shelf", "HP": "High Pass", "LP": "High Cut"}[f.kind]
        no_gain = f.kind in ("HP", "LP")
        flo, fhi = P.EQ_RANGES[fi]
        qlo, qhi = P.EQ_RANGES[qi]
        lines = ["%s · %s" % (name, who),
                 "%s  %d Hz%s  Q %.1f" % (kind, f.freq, "" if no_gain else "  %+.1f dB" % f.gain, f.q),
                 "%d … %d Hz%s · Q %.1f … %.1f" % (flo, fhi, "" if no_gain else " · ±12 dB", qlo / 10, qhi / 10)]
        if no_gain:
            lines.append("No gain; Q sets the resonance.")
        if f.band is None and self.fs >= self.no_bt_from:
            lines.append("Not available at %g kHz" % (self.fs / 1000))
        elif self.session.bypassed():
            lines.append("DSD input: no DSP, not in the signal path")
        elif f.band is not None and (pt.side, f.name) not in self._off and self.session.eq_bypassed(self.output[1]):
            lines.append("EQ of the input on at %g kHz: not in the signal path"
                         % (P.SAMPLE_RATES[self.session.state[P.SAMPLE_RATE]] / 1000))
        elif not f.active:
            lines.append("%s off: not in the signal path" % ("Bass/Treble" if f.band is None else "EQ"))
        lines.append("Drag: frequency · Wheel: Q" if self.hovered_by_label else "Wheel: Q")
        return "\n".join(lines)

    def _scatter_clicked(self, scatter, spots, ev):
        if ev.button() == Qt.LeftButton:
            pt = self.point_at(self.view, self.view.mapFromScene(ev.scenePos()))
            if pt is not None:
                self.pick(pt)

    def pick(self, pt):
        if pt.side is not None and self.dual:            # with Dual EQ off the point is of both channels
            self.prefer_side = pt.side
        self.current = pt.key
        self.redraw()
        self.picked.emit((pt.flt.address, pt.flt.indices[2]))

    def drag_to(self, pt, x, y):
        """Frequency from x; gain from y, unless y is None (dragged by its label: frequency only)."""
        f = pt.flt
        ti, gi, fi, qi = f.indices
        s = self.session.state
        freq = P.snap_freq(10 ** x, fi)
        if freq != s.get((f.address, fi)):
            self.edited.emit((f.address, fi), freq, False)
        if y is not None and f.kind not in ("HP", "LP"):
            lo, hi = P.EQ_RANGES[gi]
            gain = min(max(int(math.floor(y * 2 + 0.5)), lo), hi)
            if gain != s.get((f.address, gi)):
                self.edited.emit((f.address, gi), gain, False)

    def step_q(self, pt, direction, size):
        qi = pt.flt.indices[3]
        key = (pt.flt.address, qi)
        v = self.session.state.get(key)
        if v is None:
            return
        new = P.step(qi, v, direction, size)
        if new != v:
            self.edited.emit(key, new, False)
