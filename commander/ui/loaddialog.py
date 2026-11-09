"""Load: a filter file or a curve to the device, by Map or by Fit, with the user having the last word. OK writes,
Cancel writes nothing. The conversion itself is eqimport's; this is what the user sees and chooses.

    Input       the file as written. A check box in the margin before every line that can be used; what cannot be
                used is grey, its tooltip says why. In a Commander file the rows of its table are the lines to use
                (Origin ADI-2), or its Filter lines (Origin External). A curve: a summary instead, with the choice
                of the column that is the curve.
    Conversion  Map or Fit, convert again, Close enough (stop the fit and take its best so far), Origin, fs, and with
                Fit Bass/Treble. The graph: per channel the input (wide and see-through), the sum of the result
                and its bands, on the main window's scale; below it, on the same scale, how far the sum is off the
                input. The sum and its bands as the device makes them; a fit's free level moves the input onto
                them ("Input (adj.)"). Only the result counts here, not the device. Its legend works as the main
                window's.
    Output      the result in the tables of the main window, read only; what the input does not set is '—', and
                goes to the device at its factory default. A check box per block says whether it goes to the
                device; a block the input does not set at all starts unchecked. OK and Cancel.
    Status bar  the fit's progress; how far the result is off the input; and what stands in the way of OK.

What the file is decides how the dialog starts (once, on opening): a Commander file maps its table; a file that
fits the device exactly as written maps; any other file fits, and a curve only fits. Every change recomputes; a fit runs in a thread of
its own, again half a second after the last click on a line. OK waits for the fit, or for Close enough. The dialog
follows the device when Dual EQ changes there, and keeps OK off while the device is gone.

Into a preset being edited (the window's edit stand) it works the same, on the preset instead of the device, and says
so in the head of Output.
"""

import itertools
import math
import os

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame, QGraphicsTextItem, QGridLayout, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QProgressBar, QScrollArea, QSplitter,
                               QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionButton, QVBoxLayout, QWidget)

from ..conversion import curvefile as C
from ..conversion import eqfile as E
from ..conversion import eqfit as X
from ..conversion import eqimport as I
from ..device import filters as F
from ..device import params as P
from . import theme
from .graph import (BAND_ALPHA, BAND_W, COMPARE_W, DIMMED, INPUT_ALPHA, INPUT_W, LEGEND_GAP, MIN_POINTS,
                    POINTS_PER_PIXEL, SUM_W, TITLE_ROOM, X_HI, X_LO, X_PAD, Y_HI, Y_LO, ZONE_INK, _fading_pen, _ticks,
                    side_color, title_axes)
from .legend import GROUP_GAP, _Item as LegendItem
from .tables import (BAND_COLUMNS, BAND_WIDTHS, BT_COLUMNS, BT_WIDTHS, CellDelegate, Marks, ParamModel, ParamView,
                     band_rows, bt_rows)
from .widgets import (ATTACHED_GAP, INNER_GAP, SECTION_GAP, SIDE, TITLE_STYLE, Action, Choice, Segmented,
                      dropped_file, head, placement)

MAP, FIT = 0, 1
DIFF_ROOM = 8.0                                  # dB below the main window's scale, for the deviation
DIFF_MID = Y_LO - DIFF_ROOM / 2
REFIT_MS = 500                                   # after the last click on a line, the fit starts again
CANDIDATE_ALPHA = 0.85                           # what the fit tries now: a little faint
CURVES_KEPT = 4000                               # curves kept for drawing again, before they are let go
PROGRESS_MS = 100                                # a fit's best so far is shown at most this often
LEVEL_SHOWN = 0.05                               # dB: a fit's level from here on is said
LABEL_ROOM = 12                                  # px beside 20 Hz and 20 kHz for their labels
BODY_MARGIN = 12                                 # px above and below the columns
ZONE_TOP = 6                                     # px above the legend in the graph's zone, as the main window's
UNDEFINED = "—"
UNDEFINED_TIP = "Not set: factory default"
STATE_ROLE, WARN_ROLE, MARK_ROLE = Qt.UserRole + 1, Qt.UserRole + 2, Qt.UserRole + 3
AGAIN_ICON = 14                                  # px, the round arrow
BOX, LINE_H = 22, 22                             # px: the check box's part of the margin; a line of the file


def read_file(path, fs):
    """A file for Load: a filter file (eqfile.EqFile), else a curve (curvefile.CurveFile), else None. Raises
    OSError."""
    eq = E.load(path, fs)
    return eq if eq.recognised else C.load(path)


# -- input -------------------------------------------------------------------------------------------

class Margin(QStyledItemDelegate):
    """A line of the file with a margin as in an editor: a check box when the line can be used, then its number."""

    def __init__(self, parent):
        super().__init__(parent)
        self.gutter = BOX + 40

    def paint(self, painter, option, index):
        r = option.rect
        state = index.data(STATE_ROLE)                   # 'on', 'off', or None: cannot be used
        painter.save()
        gutter = QRect(r.left(), r.top(), self.gutter, r.height())
        painter.fillRect(gutter, theme.PANEL)
        if state:
            box = QStyleOptionButton()
            box.rect = QRect(gutter.left() + 4, gutter.top() + (gutter.height() - 14) // 2, 14, 14)
            box.state = QStyle.State_Enabled | (QStyle.State_On if state == "on" else QStyle.State_Off)
            if index.data(WARN_ROLE):
                pal = QPalette(option.palette)
                for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
                    pal.setColor(role, theme.WARN)
                box.palette = pal
            QApplication.style().drawPrimitive(QStyle.PE_IndicatorCheckBox, box, painter, option.widget)
            if index.data(WARN_ROLE):
                painter.setPen(QPen(theme.WARN, 1))
                painter.drawRect(box.rect.adjusted(0, 0, -1, -1))
        painter.setFont(theme.mono_font(9))
        painter.setPen(theme.WARN if index.data(MARK_ROLE) else theme.SECONDARY if state else theme.OFF)
        painter.drawText(gutter.adjusted(BOX, 0, -10, 0), int(Qt.AlignRight | Qt.AlignVCenter), str(index.row() + 1))
        painter.setFont(theme.mono_font(10))
        painter.setPen(theme.TEXT if state == "on" else theme.SECONDARY if state else theme.OFF)
        painter.drawText(r.adjusted(self.gutter + 10, 0, 0, 0), int(Qt.AlignLeft | Qt.AlignVCenter),
                         index.data(Qt.DisplayRole))
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(self.gutter + 20 + _mono_width(index.data(Qt.DisplayRole) or ""), LINE_H)


def _mono_width(text):
    return QFontMetrics(theme.mono_font(10)).horizontalAdvance(text)


class InputList(QListWidget):
    """The file, line by line; a click in the margin of a line that can be used, or Space, checks or unchecks it."""

    toggled = Signal(int)                                # the line number

    def __init__(self):
        super().__init__()
        self.margin = Margin(self)
        self.setItemDelegate(self.margin)
        self.setSelectionMode(QListWidget.NoSelection)
        self.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.setStyleSheet("QListWidget { background: %s; border: 1px solid %s; }"
                           % (theme.DISPLAY.name(), theme.GRID.name()))

    def set_lines(self, lines):
        self.clear()
        self.margin.gutter = BOX + 10 + _mono_width("0") * len(str(max(len(lines), 1))) + 10
        for text in lines:
            self.addItem(QListWidgetItem(text))

    def show_line(self, no, state, warn=False, mark=False, tip=""):
        item = self.item(no - 1)
        item.setData(STATE_ROLE, state)
        item.setData(WARN_ROLE, warn)
        item.setData(MARK_ROLE, mark)
        item.setToolTip(tip)

    def mousePressEvent(self, e):
        item = self.itemAt(e.position().toPoint())
        if item is not None and item.data(STATE_ROLE) and e.position().x() < self.margin.gutter:
            self.toggled.emit(self.row(item) + 1)
            return
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        item = self.currentItem()
        if e.key() == Qt.Key_Space and item is not None and item.data(STATE_ROLE):
            self.toggled.emit(self.row(item) + 1)
            return
        super().keyPressEvent(e)


class Summary(QFrame):
    """A curve instead of the text of its file: what the file holds, and which of its columns is the curve."""

    column_chosen = Signal(int)                          # the column, as an index into the file's columns
    ROWS = ("Points", "Frequency", "Gain", "Column", "Comments")

    def __init__(self):
        super().__init__()
        self.setObjectName("summary")
        self.setStyleSheet("QFrame#summary { background: %s; border: 1px solid %s; }"
                           % (theme.DISPLAY.name(), theme.GRID.name()))
        grid = QGridLayout(self)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        self.values = {}
        for r, name in enumerate(self.ROWS):
            grid.addWidget(LoadDialog.label(name), r, 0, Qt.AlignLeft | Qt.AlignTop)
            value = QLabel()
            value.setWordWrap(True)
            grid.addWidget(value, r, 1, Qt.AlignTop)
            self.values[name] = value
        self.choice = Choice()
        self.choice.setPlaceholderText("None")
        self.choice.currentIndexChanged.connect(self.column_chosen)
        grid.addWidget(self.choice, self.ROWS.index("Column"), 1, Qt.AlignLeft | Qt.AlignTop)
        grid.setRowStretch(len(self.ROWS), 1)
        grid.setColumnStretch(1, 1)

    def show_curve(self, cf, column):
        """column: the one chosen, or None when none can serve."""
        lo, hi = cf.freqs[0], cf.freqs[-1]
        short = lo > F.FREQS[0] * 1.001 or hi < F.FREQS[-1] / 1.001
        self._set("Points", "%d" % len(cf.freqs))
        self._set("Frequency", "%s – %s" % (_hz(lo), _hz(hi)), short,
                  "Not all of 20 Hz – 20 kHz: beyond it, its first and last value hold" if short else "")
        y = None if column is None else cf.columns[column]
        self._set("Gain", UNDEFINED if y is None else "%+.1f … %+.1f dB" % (_db(np.min(y)), _db(np.max(y))))
        # all columns; one that cannot serve is grey, and says why
        self.choice.blockSignals(True)
        self.choice.clear()
        self.choice.addItems(cf.names)
        for i in range(len(cf.names)):
            why = C.unusable(cf, i)
            if why:
                self.choice.model().item(i).setEnabled(False)
                self.choice.setItemData(i, why, Qt.ToolTipRole)
        self.choice.setCurrentIndex(-1 if column is None else column)
        self.choice.blockSignals(False)
        none = "No column lies within ±%g dB throughout" % C.RANGE_DB
        self.choice.set_value_color(theme.WARN if column is None else None)
        self.choice.setToolTip(none if column is None else "The column that is the curve")
        many = len(cf.names) > 1
        self.choice.setVisible(many)
        self.values["Column"].setVisible(not many)
        self._set("Column", cf.names[0], column is None, C.unusable(cf, 0) or "")
        self._set("Comments", "\n".join(cf.comments) if cf.comments else "None")

    def _set(self, row, text, amber=False, tip=""):
        value = self.values[row]
        value.setText(text)
        value.setStyleSheet("color: %s;" % (theme.WARN if amber else theme.TEXT).name())
        value.setToolTip(tip)


def _hz(f):
    return "%.3g Hz" % f if f < 1000 else "%.3g kHz" % (f / 1000)


def again_icon(color):
    """A round arrow, clockwise: convert again."""
    size, scale = AGAIN_ICON, 4                  # drawn large, shown small: sharp at any display scaling
    pm = QPixmap(size * scale, size * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 1.0)                       # as thin as the letters of a button
    pen.setCapStyle(Qt.FlatCap)
    p.setPen(pen)
    radius, start, span = size / 2 - 2.6, 60, -300    # degrees: from the top right, clockwise, open at the top
    cx, cy = size / 2, size / 2 + 0.7            # lower: the arrowhead rises above the circle, and all of it centres
    p.drawArc(QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius), start * 16, span * 16)
    end = math.radians(start + span)
    at = QPointF(cx + radius * math.cos(end), cy - radius * math.sin(end))
    ahead = QPointF(math.sin(end), math.cos(end))     # clockwise along the circle, on the screen
    side = QPointF(-ahead.y(), ahead.x())
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPolygon(QPolygonF([at + ahead * 2.2, at - ahead * 0.3 + side * 1.8, at - ahead * 0.3 - side * 1.8]))
    p.end()
    return QIcon(pm)


def enough_icon(color, disabled):
    """A check mark: close enough, take what the fit has found so far. Its own colour when it cannot be pressed."""
    icon = QIcon()
    for c, mode in ((color, QIcon.Normal), (disabled, QIcon.Disabled)):
        size, scale = AGAIN_ICON, 4
        pm = QPixmap(size * scale, size * scale)
        pm.setDevicePixelRatio(scale)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(c, 1.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QPolygonF([QPointF(3.0, 7.4), QPointF(5.8, 10.2), QPointF(11.0, 4.0)]))
        p.end()
        icon.addPixmap(pm, mode)
    return icon


# -- the graph -----------------------------------------------------------------------------------------

class TwoScales(pg.AxisItem):
    """The dB axis with two scales one under the other, each with its title at the height of its own 0."""

    def __init__(self, titles):
        super().__init__("left")
        self.titles = []
        for text, at in titles:
            t = QGraphicsTextItem(text, self)
            t.setRotation(-90)
            t.setFont(theme.ui_font(8))
            t.setDefaultTextColor(theme.SECONDARY)
            self.titles.append((t, at))

    def place(self):
        view = self.linkedView() if hasattr(self, "_linkedView") else None   # also called while being built
        if view is None or not hasattr(self, "titles"):
            return
        for t, at in self.titles:
            y = self.mapFromScene(view.mapViewToScene(QPointF(0, at))).y()
            t.setPos(-5, y + t.boundingRect().width() / 2)

    def resizeEvent(self, ev=None):
        super().resizeEvent(ev)
        self.place()


class CurveGraph(pg.PlotWidget):
    """Per channel the input, the sum and its bands on the main window's scale and at its resolution (freqs: two points
    per pixel); below it the deviation. What the legend hides is not drawn; what it points at stays bright, the rest
    steps back. resolution_changed: the width asks for other frequencies; the curves are to be computed again."""

    resolution_changed = Signal()

    LAYERS = ("input", "sum", "bands", "deviation", "candidate")

    def __init__(self):
        self.axis = TwoScales([("Gain (dB)", 0.0), ("Deviation (dB)", DIFF_MID)])
        super().__init__(background=theme.DISPLAY, axisItems={"left": self.axis})
        pi = self.getPlotItem()
        pi.hideButtons()
        pi.setMenuEnabled(False)
        pi.setMouseEnabled(False, False)
        pi.showGrid(x=True, y=True, alpha=0.6)
        view = pi.getViewBox()
        for name in ("bottom", "left"):
            ax = pi.getAxis(name)
            ax.setPen(theme.DISPLAY_GRID)
            ax.setTextPen(theme.SECONDARY)
            ax.setStyle(tickFont=theme.ui_font(8))
            ax.setZValue(view.zValue() - 1)              # the axes draw the grid; it lies behind the curves
        pi.getAxis("bottom").setTicks(_ticks())
        self.axis.setTicks([[(v, "%d" % v) for v in range(-12, 13, 3)] +
                            [(DIFF_MID + d, "%+d" % d if d else "0") for d in (-3, 0, 3)],
                            [(v, "") for v in range(int(Y_LO), int(Y_HI) + 1) if v % 3] +
                            [(DIFF_MID + d, "") for d in (-2, -1, 1, 2)]])
        title_axes(pi, "")                               # the room and the line on the right of the main window's
        self.axis.showLabel(False)                       # the two titles are TwoScales' own
        view.sigResized.connect(self.axis.place)
        view.sigResized.connect(self.fit_x)
        view.sigResized.connect(self.resized)
        view.sigYRangeChanged.connect(self.axis.place)
        for y, color in ((0, theme.SECONDARY), (Y_LO, theme.GRID), (DIFF_MID, theme.SECONDARY)):
            self.addItem(pg.InfiniteLine(pos=y, angle=0, pen=pg.mkPen(color, width=1)))
        view.disableAutoRange()                          # a fixed scale, as the main window's
        self.fit_x()
        self.setYRange(Y_LO - DIFF_ROOM, Y_HI, padding=0)
        self.points = MIN_POINTS
        self.x = np.linspace(X_LO, X_HI, self.points)
        self.visible = {k: True for k in ("L", "R", "BT") + self.LAYERS}
        self.drawn = {}                                  # {item: (curve, look)} as it is on screen
        self.emphasis = None                             # a legend item pointed at
        self.channels = []
        # a fixed set of items, updated in place: per channel (left last, on top) the input under the rest, its
        # bands, what the fit tries now, the sum and the deviation
        self.items = []
        for _ in (0, 1):
            self.items.append({"input": self.plot(connect="finite"),
                               "bands": [self.plot(connect="finite") for _ in range(7)],
                               "candidate": self.plot(connect="finite"), "sum": self.plot(connect="finite"),
                               "deviation": self.plot(connect="finite")})
        self.items.reverse()

    def fit_x(self):
        """20 Hz to 20 kHz with room for their labels: the main window's room, or more in a narrower graph."""
        width = self.getPlotItem().getViewBox().width()
        pad = max(X_PAD, LABEL_ROOM * (X_HI - X_LO) / max(width - 2 * LABEL_ROOM, 1))
        self.setXRange(X_LO - pad, X_HI + pad, padding=0)

    def freqs(self):
        """Where to compute the curves: as the main window, two points per pixel, at least MIN_POINTS."""
        return 10 ** np.linspace(X_LO, X_HI, self.points)

    def resized(self):
        points = max(MIN_POINTS, int(self.getPlotItem().getViewBox().width() * POINTS_PER_PIXEL))
        if points != self.points:
            self.points = points
            self.resolution_changed.emit()

    def draw(self, channels):
        """channels: per channel (key 'L' or 'R', colour, input, sum or None, [(band curve, colour, key)], what the fit
        tries now or None), at freqs(); the input and what is tried moved to the sum's level already."""
        self.channels = channels
        self.x = np.linspace(X_LO, X_HI, len(channels[0][2])) if channels else self.x
        self.redraw()

    def redraw(self):
        """Only what changed is drawn again: with a fit running, most curves stay as they are from one drawing to the
        next."""
        for k, items in enumerate(self.items):
            everything = items["bands"] + [items["candidate"], items["sum"], items["deviation"], items["input"]]
            if k >= len(self.channels) or not self.visible[self.channels[k][0]]:
                for item in everything:
                    self._clear(item)
                continue
            key, color, given, total, bands, tried = self.channels[k]
            if tried is None:
                self._clear(items["candidate"])
            else:
                self._show(items["candidate"], "candidate", tried, color, COMPARE_W, CANDIDATE_ALPHA,
                           (key, "candidate"), style=Qt.DotLine)
            for item, band in itertools.zip_longest(items["bands"], bands):
                if band is None or not self.visible["bands"] or not self.visible[band[2]]:
                    self._clear(item)
                else:                                    # fading in its tails, as in the main window
                    alpha = BAND_ALPHA * self._dim((band[2], "bands"))
                    self._put(item, band[0], ("band", QColor(band[1]).rgba(), alpha),
                              lambda band=band, alpha=alpha: _fading_pen(band[1], BAND_W, alpha, self.x, band[0]))
            if total is None:
                self._clear(items["sum"])
                self._clear(items["deviation"])
            else:
                self._show(items["sum"], "sum", total, color, SUM_W, 1.0, (key, "sum"))
                diff = np.clip(total - given, -DIFF_ROOM / 2, DIFF_ROOM / 2)
                self._show(items["deviation"], "deviation", DIFF_MID + diff, color, COMPARE_W, 1.0,
                           (key, "deviation"), clip=False)
            first = self.channels[0]
            if k and self.visible[first[0]] and np.array_equal(given, first[2]):
                self._clear(items["input"])              # the same input as the left: once, or it would look darker
            else:
                self._show(items["input"], "input", given, color, INPUT_W, INPUT_ALPHA, (key, "input"))

    def _dim(self, keys):
        return DIMMED if self.emphasis is not None and self.emphasis not in keys else 1.0

    def _show(self, item, layer, y, color, width, alpha, keys, clip=True, style=Qt.SolidLine):
        if not self.visible[layer]:
            self._clear(item)
            return
        c = QColor(color)
        c.setAlphaF(alpha * self._dim(keys))

        def pen():
            p = QPen(c, width)
            p.setCosmetic(True)
            p.setStyle(style)
            return p

        self._put(item, y, (c.rgba(), width, style), pen, clip)

    def _put(self, item, y, look, pen, clip=True):
        """y with the pen pen() makes, unless the item shows that already (look: what decides the pen)."""
        before = self.drawn.get(item)
        if before is not None and before[1] == look and (before[0] is y or np.array_equal(before[0], y)):
            return
        item.setPen(pen())
        item.setData(self.x, np.where(y < Y_LO, np.nan, y) if clip else y)   # clipped: not into the deviation below
        self.drawn[item] = (y, look)

    def _clear(self, item):
        if self.drawn.get(item) is not None:
            item.setData([], [])
            self.drawn[item] = None


class CurveLegend(QWidget):
    """As the main window's legend: the channels, then the layers. A click shows or hides an item, a double-click
    shows only this item of its group (again: the whole group), pointing at it lights its curves."""

    LAYERS = [("input", "wide", "Input"), ("sum", "thick", "Sum"), ("bands", "thin", "Bands"),
              ("deviation", "line", "Deviation"), ("candidate", "dotted", "Candidate")]
    TIPS = {"bands": "Includes Bass and Treble\n", "deviation": "How far the sum is off the input, below\n",
            "candidate": "What the fit is trying now, better or not; while it fits\n"}

    def __init__(self, graph):
        super().__init__()
        self.graph = graph
        self.channels = {}                               # {key: (name, colour)} of the channels there are
        self.fitting = False                             # what the fit tries now is shown only while it fits
        self.input_name, self.input_tip = "Input", ""    # "Input (adj.)" when a fit moved it
        self.items = {k: LegendItem() for k in ("L", "R", "BT") + tuple(k for k, _, _ in self.LAYERS)}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GROUP_GAP)
        for keys in (("L", "R", "BT"), tuple(k for k, _, _ in self.LAYERS)):
            group = QWidget()
            group_lay = QHBoxLayout(group)
            group_lay.setContentsMargins(0, 0, 0, 0)
            group_lay.setSpacing(4)
            for k in keys:
                item = self.items[k]
                item.clicked.connect(lambda k=k: self.toggle(k))
                item.double_clicked.connect(lambda k=k: self.isolate(k))
                item.pointed.connect(lambda on, k=k: self.point(k, on))
                group_lay.addWidget(item)
            lay.addWidget(group)
        self._before = None                              # the group's state before the first click of a double-click
        self.refresh()

    def set_channels(self, channels):
        self.channels = channels
        self.refresh()

    def _group(self, key):
        if key in ("L", "R", "BT"):
            return [k for k in ("L", "R", "BT") if k in self.channels]
        return [k for k, _, _ in self.LAYERS]

    def toggle(self, key):
        v = self.graph.visible
        self._before = {k: v[k] for k in self._group(key)}
        v[key] = not v[key]
        self.apply()

    def isolate(self, key):
        """Only this item of its group; if it already was the only one, the whole group again."""
        v = self.graph.visible
        group = self._group(key)
        before = self._before or {k: v[k] for k in group}
        alone = before.get(key) and not any(before.get(k) for k in group if k != key)
        for k in group:
            v[k] = True if alone else k == key
        self._before = None
        self.apply()

    def point(self, key, on):
        self.graph.emphasis = key if on and self.graph.visible[key] else None
        self.graph.redraw()

    def apply(self):
        self.refresh()
        self.graph.redraw()

    def refresh(self):
        for k, (kind, name, color) in self.marks().items():
            item = self.items[k]
            on = self.graph.visible[k]
            item.show_mark(kind, color if on else theme.OFF)
            item.name.setText(name)
            item.name.setStyleSheet("color: %s;" % (theme.LABEL if on else theme.OFF).name())
            group = ("channel", "channels") if k in ("L", "R", "BT") else ("layer", "layers")
            tip = self.input_tip if k == "input" else self.TIPS.get(k, "")
            item.setToolTip(tip + "Click: show or hide · Double-click: only this %s; again: all %s" % group)
        for k in ("L", "R", "BT"):
            self.items[k].setVisible(k in self.channels)
        self.items["candidate"].setVisible(self.fitting)

    def set_fitting(self, on):
        if on != self.fitting:
            self.fitting = on
            self.refresh()

    def set_input(self, name, tip):
        if (name, tip) != (self.input_name, self.input_tip):
            self.input_name, self.input_tip = name, tip
            self.refresh()

    def marks(self):
        out = {k: ("line", name, color) for k, (name, color) in self.channels.items()}
        out.update({k: (kind, self.input_name if k == "input" else name, theme.SECONDARY)
                    for k, kind, name in self.LAYERS})
        return out


# -- output --------------------------------------------------------------------------------------------

class Shown:
    """Stands in for the Session in the read-only tables: the outcome as its state."""

    def __init__(self, dual):
        self.state, self.dual_on = {}, dual

    def ready(self):
        return True

    def bypassed(self):
        return False

    def eq_bypassed(self, out):
        return False

    def writable(self, key):
        return False

    def dual(self, out):
        return self.dual_on


class ResultModel(ParamModel):
    """A table of the main window, read only: what the outcome does not set is '—'; a limited value says so."""

    def __init__(self, shown, marks, build_rows, columns, notes):
        super().__init__(shown, marks, build_rows, columns)
        self.notes = notes                                  # {key: what was limited}, shared with the dialog

    def data(self, index, role=Qt.DisplayRole):
        cell = self.cell(index)
        undefined = cell.key is not None and self.session.state.get(cell.key) is None
        if role == Qt.DisplayRole and undefined:
            return UNDEFINED
        if role == Qt.ForegroundRole:
            return theme.SECONDARY if undefined else None
        if role == Qt.ToolTipRole:
            return UNDEFINED_TIP if undefined else self.notes.get(cell.key)
        return super().data(index, role)


def output_table(model, delegate_color, marks, header_width=ParamView.HEADER_WIDTH):
    delegate = CellDelegate(model, marks, delegate_color)
    delegate.spinners = False
    view = ParamView(model, delegate, header_width)
    view.setSelectionMode(ParamView.NoSelection)
    view.setFocusPolicy(Qt.NoFocus)
    return view, delegate


class Corner(QWidget):
    """A block's check box and the name of its table, in the colour of its channel: a name, not a switch."""

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.box = QCheckBox()
        self.box.setToolTip("Load into the device")
        self.name = QLabel()
        self.name.setFixedHeight(22)
        lay.addWidget(self.box)
        lay.addWidget(self.name)

    def set_name(self, text, color):
        self.name.setText(text)
        self.name.setStyleSheet("color: %s; font-size: 9pt; letter-spacing: 1px; padding: 0 2px;" % color.name())
        self.adjustSize()


# -- fit -----------------------------------------------------------------------------------------------

class FitThread(QThread):
    """eqfit on each job in turn: (blocks, curve, starts). Progress and the end with {blocks: eqfit.Result}; what it
    tries now with (blocks, eqfit.Result). Owned by its dialog, so that Qt destroys it, in the GUI thread."""

    progressed = Signal(float, object)
    tried = Signal(object, object)
    done = Signal(object)

    def __init__(self, jobs, fs, tone, parent):
        super().__init__(parent)
        self.jobs, self.fs, self.tone = jobs, fs, tone

    def run(self):
        out = {}
        n = len(self.jobs)
        try:
            for k, (blocks, curve, starts) in enumerate(self.jobs):
                def progress(fraction, result, k=k, blocks=blocks):
                    self.progressed.emit((k + fraction) / n, {**out, blocks: result})
                out[blocks] = X.fit(curve, self.fs, tone=self.tone, starts=starts, progress=progress,
                                    cancel=self.isInterruptionRequested,
                                    candidate=lambda result, blocks=blocks: self.tried.emit(blocks, result))
        except X.Cancelled:
            return
        self.done.emit(out)


# -- the dialog ----------------------------------------------------------------------------------------

class LoadDialog(QDialog):
    SIZE = QSize(1500, 780)
    maximized = False                                     # as the last one was closed: the next one opens so too

    def __init__(self, source, path, session, out, live=None, fs=F.FS, parent=None, preset=None, name=None):
        """source: what read_file made of the file at path; session: a Session, or a Draft with preset its number
        and name; name: of the output, as the window shows it (default the name in params.OUTPUTS)."""
        super().__init__(parent)
        self.session, self.out, self.live, self.fs_default = session, out, live, fs
        self.preset = preset
        self.setWindowTitle("Load filters")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)    # a large dialog: it may take the whole screen
        self.setAcceptDrops(True)                           # another file dropped on it: that file instead
        default, _, self.left, self.right = P.channel(out)
        self.name = default if name is None else name
        self.dual = session.dual(out)
        self.connected = session.ready()
        self.mode, self.origin, self.tone = FIT, I.EXTERNAL, False
        self.eq, self.cf, self.column = None, None, None     # a filter file, or a curve and its column
        self.groups, self.chosen, self.problem = {}, [], ""
        self.drop_note = ""                                 # a file dropped on the dialog that is no filter file
        self.outcome, self.levels, self.notes = {}, {}, {}        # {block: {target: Placed}}, {block: dB}, {key: text}
        self.fitting, self.fraction = False, 0.0
        self.threads, self.thread = [], None
        self.values, self.unchanged = {}, False
        self.refit = QTimer(self, singleShot=True, timeout=self.start_fit)
        self.repaint_soon = QTimer(self, singleShot=True, interval=PROGRESS_MS, timeout=self.show_result)
        self.names = None                                   # the channels the legend shows
        self.results, self.job_curves = {}, {}              # the fit's best so far, and what each job fits
        self.tried = {}                                     # {blocks: eqfit.Result} the fit tries now
        self.curves = {}                                    # see curve()

        self.build()
        session.on_connection.append(self.connection)
        session.on_changed.append(self.changed)
        self.finished.connect(self.close_down)
        self.start(source, path)

    def start(self, source, path):
        """A file: how it starts (once per file), as the file decides: a Commander file maps its table, a file
        that fits the device exactly as written maps, any other file fits, and so does a curve, with the column
        proposed."""
        self.stop_fit()
        curve = isinstance(source, C.CurveFile)
        self.eq, self.cf = (None, source) if curve else (source, None)
        self.column = source.chosen if curve else None
        self.path = path
        kind = "curve" if curve else I.category(source)
        self.mode = MAP if kind in ("commander", "fits") else FIT
        self.origin = I.ADI2 if kind == "commander" else I.EXTERNAL
        self.tone = False                                   # Bass/Treble in a fit: off until asked for
        saved = None if curve else source.fs
        self.fs_given = saved or self.live or self.fs_default    # the file's rate, else the one the device runs at
        self.fs_why = ("The file was saved at %g kHz" % (saved / 1000) if saved else
                       "The device runs at %g kHz" % (self.live / 1000) if self.live else "")
        self.fs = self.fs_given
        self.selections = {}                                # {(mode, origin): {line}} the proposals
        self.own = None                                     # {line} once the user changes one: for Map and Fit both
        self.block_on, self.touched = {}, set()
        self.drop_note = ""
        if curve:
            self.summary.show_curve(source, self.column)
            self.input_stack.setCurrentWidget(self.summary)
        else:
            self.input.set_lines(source.lines)
            self.input_stack.setCurrentWidget(self.input)
        self.file_label.setText(os.path.basename(path))
        self.way.set_current(self.mode)
        self.way.set_enabled_at(MAP, not curve, "A curve has no filters to map" if curve else "")
        for box, index in ((self.origin_box, 0 if self.origin == I.ADI2 else 1), (self.fs_box, None)):
            box.blockSignals(True)
            if index is None:
                if box.findData(int(self.fs_given)) < 0:
                    box.addItem("%g" % (self.fs_given / 1000), int(self.fs_given))
                index = box.findData(int(self.fs_given))
            box.setCurrentIndex(index)
            box.blockSignals(False)
        self.recompute(fit_now=True)

    # -- building ----------------------------------------------------------------------------------
    def build(self):
        self.setStyleSheet("QDialog { background: %s; }" % theme.BACKGROUND.name())
        self.input = InputList()
        self.input.toggled.connect(self.toggle_line)
        self.summary = Summary()
        self.summary.column_chosen.connect(self.set_column)
        self.input_stack = QStackedWidget()
        self.input_stack.addWidget(self.input)
        self.input_stack.addWidget(self.summary)
        self.input_note = self.label("", theme.SECONDARY)
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, BODY_MARGIN)
        lay.setSpacing(ATTACHED_GAP)
        self.file_label = self.label("", theme.SECONDARY)
        t = QLabel("INPUT")
        t.setStyleSheet(TITLE_STYLE)
        lay.addWidget(head(t, self.file_label))
        lay.addWidget(self.input_stack, 1)
        lay.addWidget(self.input_note)

        self.way = Segmented(["Map", "Fit"])
        self.way.changed.connect(self.set_mode)
        self.again = Action(compact=True)
        self.again.setIcon(again_icon(theme.BUTTON_TEXT))
        self.again.setIconSize(QSize(AGAIN_ICON, AGAIN_ICON))
        self.again.setFixedSize(self.way.sizeHint().height(), self.way.sizeHint().height())
        self.again.setToolTip("Convert again")
        self.again.clicked.connect(lambda: self.recompute(fit_now=True))
        self.enough = Action(compact=True)
        self.enough.setIcon(enough_icon(theme.BUTTON_TEXT, theme.DISABLED))
        self.enough.setIconSize(QSize(AGAIN_ICON, AGAIN_ICON))
        self.enough.setFixedSize(self.way.sizeHint().height(), self.way.sizeHint().height())
        self.enough.setToolTip("Close enough: stop the fit and take what it has found so far")
        self.enough.clicked.connect(self.good_enough)
        self.origin_label = self.label("Origin")
        self.origin_box = Choice()
        self.origin_box.addItems([I.ADI2, I.EXTERNAL])
        self.origin_box.currentIndexChanged.connect(self.set_origin)
        self.origin_group = QWidget()                     # with its gap after it: gone as a whole for a curve
        origin_lay = QHBoxLayout(self.origin_group)
        origin_lay.setContentsMargins(0, 0, 24 + 6, 0)
        origin_lay.setSpacing(6)
        origin_lay.addWidget(self.origin_label)
        origin_lay.addWidget(self.origin_box)
        self.fs_box = Choice()
        for rate in P.SAMPLE_RATES:
            self.fs_box.addItem("%g" % (rate / 1000), rate)
        self.fs_box.currentIndexChanged.connect(self.set_fs)
        fs_label = self.label("<i>f</i><sub>s</sub>")
        fs_label.setTextFormat(Qt.RichText)
        self.tone_box = QCheckBox("Include Bass/Treble")     # a check box, as everything that takes part
        self.tone_box.setStyleSheet("color: %s;" % theme.LABEL.name())
        self.tone_box.clicked.connect(self.toggle_tone)
        controls = head(self.way, self.again, self.enough, 24, self.origin_group, fs_label, self.fs_box, self.label("kHz"), 24,
                        self.tone_box)
        self.graph = CurveGraph()
        self.graph.resolution_changed.connect(self.show_graph)
        self.legend = CurveLegend(self.graph)
        self.graph.setMinimumSize(360, 300)
        mid = QWidget()
        lay = QVBoxLayout(mid)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.title("CONVERSION"))
        lay.addSpacing(ATTACHED_GAP)
        lay.addWidget(controls)
        lay.addSpacing(INNER_GAP)
        # the graph's zone, as the main window's: darker, from here down to the status bar, the legend in it
        zone = QWidget()
        zone.setAutoFillBackground(True)
        ground = zone.palette()
        ground.setColor(QPalette.Window, theme.DISPLAY)
        zone.setPalette(ground)
        zone_lay = QVBoxLayout(zone)
        zone_lay.setContentsMargins(ZONE_INK - TITLE_ROOM[0], ZONE_TOP, ZONE_INK, ZONE_INK - TITLE_ROOM[1])
        zone_lay.setSpacing(LEGEND_GAP)
        zone_lay.addWidget(self.legend, 0, Qt.AlignHCenter)
        zone_lay.addWidget(self.graph, 1)
        lay.addWidget(zone, 1)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(INNER_GAP)
        split.setChildrenCollapsible(False)
        split.addWidget(left)
        split.addWidget(mid)
        split.setStretchFactor(1, 1)
        split.setSizes([430, 700])

        # output: the tables of the main window, read only
        self.shown = Shown(self.dual)
        self.marks = Marks()
        self.band_models, self.band_delegates, self.band_views, self.corners = [], [], [], []
        for side in (0, 1):
            m = ResultModel(self.shown, self.marks, band_rows(side), BAND_COLUMNS, self.notes)
            v, d = output_table(m, side_color(side, self.dual), self.marks)
            m.set_output((self.name, self.out, self.left, self.right))
            v.fit(BAND_WIDTHS)
            corner = Corner()
            corner.box.clicked.connect(lambda _=False, side=side: self.toggle_block(side))
            v.set_corner(corner)
            self.band_models.append(m)
            self.band_delegates.append(d)
            self.band_views.append(v)
            self.corners.append(corner)
        self.bt_model = ResultModel(self.shown, self.marks, bt_rows, BT_COLUMNS, self.notes)
        self.bt_view, _ = output_table(self.bt_model, theme.BT, self.marks,
                                       ParamView.HEADER_WIDTH + BAND_WIDTHS[0])
        self.bt_model.set_output((self.name, self.out, self.left, self.right))
        self.bt_view.fit(BT_WIDTHS)
        self.bt_corner = Corner()
        self.bt_corner.set_name("BASS/TREBLE", theme.BT)
        self.bt_corner.box.clicked.connect(lambda _=False: self.toggle_block(None))
        self.bt_view.set_corner(self.bt_corner)
        self.ok, cancel = Action(), Action()
        self.ok.setText("OK")
        cancel.setText("Cancel")
        self.ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        # the tables scroll when the dialog is low, as the main window's column; their scroll bar goes in the right
        # margin, against the edge. OK and Cancel stay below them, in sight, as far from them as a channel from the next
        tables = QWidget()
        lay = QVBoxLayout(tables)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.title("PRESET", "%d  %s" % self.preset) if self.preset else self.title("OUTPUT", self.name))
        lay.addSpacing(ATTACHED_GAP)
        lay.addWidget(self.band_views[0])
        lay.addSpacing(INNER_GAP)
        lay.addWidget(self.band_views[1])
        lay.addSpacing(SECTION_GAP)
        lay.addWidget(self.bt_view)
        lay.addStretch(1)
        width = self.band_views[0].width()
        tables.setFixedWidth(width)
        self.tables = QScrollArea()
        self.tables.setWidget(tables)
        self.tables.setWidgetResizable(True)
        self.tables.setFrameShape(QFrame.NoFrame)
        self.tables.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        margin = max(SIDE, self.tables.verticalScrollBar().sizeHint().width())
        self.tables.setFixedWidth(width + margin)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, margin, 0)
        buttons.setSpacing(ATTACHED_GAP)
        buttons.addStretch(1)
        buttons.addWidget(self.ok)
        buttons.addWidget(cancel)
        right = QWidget()
        lay = QVBoxLayout(right)
        lay.setContentsMargins(0, 0, 0, BODY_MARGIN)
        lay.setSpacing(0)
        lay.addWidget(self.tables, 1)
        lay.addSpacing(INNER_GAP)
        lay.addLayout(buttons)

        body = QHBoxLayout()
        body.setContentsMargins(SIDE, BODY_MARGIN, 0, 0)        # the graph's zone down to the status bar
        body.setSpacing(INNER_GAP)                       # as the main window: the tables right beside the graph's zone
        body.addWidget(split, 1)
        body.addWidget(right)

        bar = QWidget()
        bar.setStyleSheet("background: %s;" % theme.PANEL.name())
        blay = QHBoxLayout(bar)
        blay.setContentsMargins(SIDE, 4, SIDE, 4)
        blay.setSpacing(12)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(120, 8)
        self.progress.setStyleSheet("QProgressBar { background: %s; border: none; border-radius: 4px; }"
                                    " QProgressBar::chunk { background: %s; border-radius: 4px; }"
                                    % (theme.CELL.name(), theme.LABEL.name()))
        self.status = QLabel()
        self.status.setTextFormat(Qt.RichText)
        self.fitting_label = self.label("Fitting…")
        blay.addWidget(self.fitting_label)
        blay.addWidget(self.progress)
        blay.addWidget(self.status, 1)
        m = blay.contentsMargins()                       # as high while fitting as not: the graph stays put
        bar.setFixedHeight(m.top() + m.bottom() + max(self.fitting_label.sizeHint().height(),
                                                      self.status.sizeHint().height()))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(body, 1)
        outer.addWidget(bar)
        self.resize(self.SIZE)
        room = (self.parentWidget() or self).screen().availableGeometry()
        if LoadDialog.maximized or placement(self.SIZE, room) is None:
            self.setWindowState(Qt.WindowMaximized)
        self.show_dual()

    # -- a file dropped on it ------------------------------------------------------------------------
    def dragEnterEvent(self, e):
        if dropped_file(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        path = dropped_file(e.mimeData())
        if not path:
            return
        e.acceptProposedAction()
        name = os.path.basename(path)
        try:
            source = read_file(path, self.fs_default)
        except OSError as err:
            self.drop_note = "Not loaded: %s" % err
        else:
            if source is not None:
                self.start(source, path)
                return
            self.drop_note = "Not loaded: %s is not a filter file or a curve" % name
        self.show_result()

    @staticmethod
    def label(text, color=theme.LABEL):
        q = QLabel(text)
        q.setStyleSheet("color: %s;" % color.name())
        return q

    def title(self, text, extra=None):
        t = QLabel(text)
        t.setStyleSheet(TITLE_STYLE)
        return head(t, self.label(extra, theme.SECONDARY)) if extra else head(t)

    def show_dual(self):
        """The output's tables as the main window shows them: with Dual EQ one per channel, else one EQ twice."""
        self.shown.dual_on = self.dual
        names = ("EQ LEFT", "EQ RIGHT") if self.dual else ("EQ L = R", "EQ R = L")
        for side in (0, 1):
            self.corners[side].set_name(names[side], side_color(side, self.dual))
            self.band_delegates[side].color = side_color(side, self.dual)
            self.band_models[side].set_output((self.name, self.out, self.left, self.right))

    # -- what the user changes -----------------------------------------------------------------------
    def set_mode(self, mode):
        self.mode = mode
        self.recompute(fit_now=True)

    def set_origin(self, index):
        self.origin = I.ADI2 if index == 0 else I.EXTERNAL
        self.selections, self.own = {}, None             # other lines are the input now
        self.recompute(fit_now=True)

    def set_fs(self, index):
        self.fs = float(self.fs_box.itemData(index))
        self.recompute(fit_now=True)

    def toggle_tone(self):
        self.tone = not self.tone
        self.recompute(fit_now=True)

    def set_column(self, column):
        self.column = column
        self.summary.show_curve(self.cf, column)
        self.recompute(fit_now=True)

    def toggle_line(self, line):
        self.own = set(self.selection())
        self.own.symmetric_difference_update({line})
        self.recompute(fit_now=False)

    def toggle_block(self, side):
        block = "BT" if side is None else self.eq_blocks()[0 if not self.dual else side]
        self.touched.add(block)
        self.block_on[block] = not self.block_on.get(block, False)
        self.show_result()

    # -- the device ------------------------------------------------------------------------------------
    def connection(self, status, detail):
        was, self.connected = self.connected, status == "ready"
        if self.connected and not was:                   # back: on what the device has now
            self.dual = self.session.dual(self.out)
            self.show_dual()
            self.recompute(fit_now=True)
        else:
            self.show_result()

    def changed(self, keys, origin):
        if P.dual_eq_key(self.out) in keys and self.session.dual(self.out) != self.dual:
            self.dual = self.session.dual(self.out)
            self.show_dual()
            self.recompute(fit_now=True)
        elif any(k[0] in (self.out, self.left, self.right) for k in keys):
            self.show_result()                           # what is on the device already, and what is off there

    # -- computing ---------------------------------------------------------------------------------------
    def eq_blocks(self):
        return ["L", "R"] if self.dual else ["all"]

    def usable(self):
        return I.items(self.eq, self.origin, self.fs)

    def selection(self):
        """The lines checked: once the user has changed one, theirs, with Map and Fit alike; until then the proposal
        for this way and Origin."""
        if self.own is not None:
            return self.own
        key = (self.mode, self.origin)
        if key not in self.selections:
            self.selections[key] = self.proposal()
        return self.selections[key]

    def proposal(self):
        """Everything that can be used, but without Dual EQ only one channel's (the left); with Map, when not all of
        it maps, the filters with the largest effect that do."""
        usable, _ = self.usable()
        chosen = list(usable.values())
        if not self.dual and any(i.channel == "L" for i in chosen) and any(i.channel == "R" for i in chosen):
            chosen = [i for i in chosen if i.channel != "R"]
        if self.mode == MAP:
            groups = I.channel_sets(chosen, self.dual)
            if any(I.mapping(g, self.origin, self.fs).reason for g in groups.values()):
                keep = I.tone_items(chosen)
                for g in groups.values():
                    keep += I.preselect(g, self.origin, self.fs)
                chosen = keep
        return {i.line for i in chosen}

    def recompute(self, fit_now):
        self.problem, self.unmapped, self.unmap_reason = "", set(), ""
        if self.cf is not None:                          # a curve: no lines, only its column
            groups, chosen = {}, []
            if self.column is None:
                self.problem = "Nothing to load"
        else:
            usable, why = self.usable()
            chosen = [usable[n] for n in sorted(self.selection()) if n in usable]
            try:
                groups = I.channel_sets(chosen, self.dual)
            except ValueError as e:
                groups, self.problem = {}, str(e)
                self.unmapped = {i.line for i in chosen if i.channel in ("L", "R")}
            if not usable:
                self.problem = "Nothing to load"
            elif not chosen:
                self.problem = self.problem or "Nothing selected"
        self.groups, self.chosen = groups, chosen
        if self.mode == MAP:
            self.stop_fit()
            self.map_outcome(groups, chosen)
        elif not self.problem:
            self.outcome, self.levels = {}, {}
            if fit_now:
                self.refit.start(0)
            else:
                self.refit.start(REFIT_MS)
            self.fitting = True
        else:
            self.stop_fit()
            self.outcome, self.levels = {}, {}
        if self.cf is None:
            self.show_input(usable, why)
        else:
            self.input_note.setText("")
        self.show_controls()
        self.show_result()

    def map_outcome(self, groups, chosen):
        self.outcome, self.levels = {}, {}
        tone = I.tone_items(chosen)
        if tone:
            self.outcome["BT"] = {i.target: I.on_row(i) for i in tone}
        for block, g in groups.items():
            m = I.mapping(g, self.origin, self.fs)
            if m.reason:
                self.problem = self.problem or "%s: uncheck a filter, or try Fit" % m.reason
                self.unmapped |= {i.line for i in g}
                self.unmap_reason = m.reason
            elif m.placed:
                self.outcome[block] = m.placed

    def jobs(self):
        """What to fit: one curve per EQ block, one only when both channels get the same."""
        if self.cf is not None:
            blocks = tuple(self.eq_blocks())
            return [(blocks, self.given(blocks[0], F.FREQS), [])]
        tone = I.tone_items(self.chosen)
        groups = self.groups
        same = self.dual and len(groups) == 2 and groups["L"] == groups["R"]
        out = []
        for blocks, g in ([(("L", "R"), groups["L"])] if same else [((b,), g) for b, g in groups.items()]):
            m = I.mapping(g, self.origin, self.fs)
            start = I.fit_start(m)
            curve = I.target(g + tone, self.origin, self.fs)
            out.append((blocks, curve, [start] if start else []))
        return out

    def tone_allowed(self):
        groups = self.groups
        return not (self.dual and len(groups) == 2 and groups["L"] != groups["R"])

    def start_fit(self):
        self.stop_fit()
        if self.mode != FIT or self.problem:
            self.fitting = False
            self.show_result()
            return
        jobs = self.jobs()
        if not jobs:
            self.fitting = False
            self.show_result()
            return
        self.results, self.job_curves, self.tried = {}, {blocks: curve for blocks, curve, _ in jobs}, {}
        t = FitThread(jobs, self.fs, self.tone and self.tone_allowed(), self)
        t.progressed.connect(lambda fraction, results, t=t: self.fit_progress(t, fraction, results))
        t.tried.connect(lambda blocks, result, t=t: self.fit_tried(t, blocks, result))
        t.done.connect(lambda results, t=t: self.fit_done(t, results))
        t.finished.connect(lambda t=t: self.thread_ended(t))
        self.threads.append(t)
        self.thread = t
        self.fitting, self.fraction = True, 0.0
        t.start()
        self.show_result()

    def thread_ended(self, t):
        if t in self.threads:
            self.threads.remove(t)

    def stop_fit(self):
        self.refit.stop()
        if self.thread is not None:
            self.thread.requestInterruption()
            self.thread = None
        self.fitting = False

    def fit_progress(self, t, fraction, results):
        if t is not self.thread:
            return
        self.fraction = fraction
        self.results = results
        self.take_fit(results)
        if not self.repaint_soon.isActive():
            self.repaint_soon.start()

    def fit_tried(self, t, blocks, result):
        if t is not self.thread:
            return
        self.tried = {blocks: result}
        if not self.repaint_soon.isActive():
            self.repaint_soon.start()

    def fit_done(self, t, results):
        if t is not self.thread:
            return
        self.thread, self.fitting, self.fraction = None, False, 1.0
        self.take_fit(results)
        self.repaint_soon.stop()
        self.show_result()

    def good_enough(self):
        """Stop the fit and take its best so far, onto the device's grid as a fit ends."""
        if self.thread is None or set(self.results) != set(self.job_curves):
            return
        results = {b: X.to_grid(r.settings, self.job_curves[b], self.fs) for b, r in self.results.items()}
        self.stop_fit()
        self.fraction = 1.0
        self.take_fit(results)
        self.repaint_soon.stop()
        self.show_result()

    def take_fit(self, results):
        self.outcome, self.levels = {}, {}
        for blocks, r in results.items():
            placed = I.from_fit(r)
            eq_part = {t: p for t, p in placed.items() if t in I.BANDS}
            tone = {t: p for t, p in placed.items() if t in I.TONE}
            for b in blocks:
                self.outcome[b] = eq_part
                self.levels[b] = r.level
            if tone:
                self.outcome["BT"] = tone

    # -- showing --------------------------------------------------------------------------------------
    def show_input(self, usable, why):
        checked = self.selection()
        differ = E.disagreeing(self.eq) if self.origin == I.ADI2 else set()
        faults = E.table_faults(self.eq)
        tip = "%s.\nUncheck a filter, or try Fit." % self.unmap_reason if self.unmap_reason else self.problem
        for no in range(1, len(self.eq.lines) + 1):
            if no in usable:
                on = no in checked
                warn = on and no in self.unmapped
                self.input.show_line(no, "on" if on else "off", warn=warn, tip=tip if warn else "")
            else:
                mark = no in differ or no in faults
                self.input.show_line(no, None, mark=mark,
                                     tip="Differs from the table" if no in differ else why.get(no, ""))
        self.input.viewport().update()
        n = len(usable)
        self.input_note.setText("%d of %d checked" % (len(checked & set(usable)), n) if n else "")

    def show_controls(self):
        self.origin_group.setVisible(self.cf is None)
        commander = self.eq is not None and E.table(self.eq) is not None
        self.origin_box.setToolTip("ADI-2: the table loads\nExternal: the Filter lines load, as Cookbook filters"
                                   if commander else "ADI-2: the numbers as the device has them\n"
                                   "External: Cookbook filters, as filter files usually mean them")
        self.tone_box.setVisible(self.mode == FIT)
        allowed = self.tone_allowed()
        self.tone_box.setChecked(self.tone and allowed)
        self.tone_box.setEnabled(allowed)
        self.tone_box.setToolTip("The fit may use Bass and Treble too" if allowed else
                                 "Not with a set of its own per channel: Bass/Treble is shared")
        other = int(self.fs) != int(self.fs_given)
        self.fs_box.set_value_color(theme.WARN if other else None)
        tip = "Sample rate the curves and the Q are computed at"
        self.fs_box.setToolTip(tip + ("\n" + self.fs_why if other and self.fs_why else ""))
        bold = QFont(self.fs_box.font())                 # as in the main window: the rate the device runs at
        bold.setBold(True)
        for i in range(self.fs_box.count()):
            self.fs_box.setItemData(i, bold if self.fs_box.itemData(i) == self.live else None, Qt.FontRole)

    def blocks(self):
        return self.eq_blocks() + ["BT"]

    def defined(self, block):
        return bool(self.outcome.get(block))

    def show_result(self):
        for b in self.blocks():
            if b not in self.touched:
                self.block_on[b] = self.defined(b)
        on = {b for b in self.blocks() if self.block_on.get(b)}
        values = I.shown(self.outcome, self.out, self.dual)
        self.shown.state = values
        self.notes.clear()
        limited = 0
        for block, placed in self.outcome.items():
            addr = self.left if block in ("all", "L", "BT") else self.right
            for t, p in placed.items():
                if p.notes:
                    limited += len(p.notes)
                    for i in I.indices(t):
                        self.notes[(addr, i)] = "; ".join(n[:1].upper() + n[1:] for n in p.notes)
        for m in self.band_models + [self.bt_model]:
            m.refresh()
        for side, corner in enumerate(self.corners):
            corner.box.setChecked(self.eq_blocks()[side if self.dual else 0] in on)
        self.bt_corner.box.setChecked("BT" in on)
        self.show_graph()
        self.values = I.writes(self.outcome, self.out, self.dual, on) if self.outcome else {}
        self.show_status(on, limited)

    def curve(self, x, freqs):
        """The curve of an item of the input or of a placed filter, at freqs; kept, as the same come back with every
        drawing (the input does not change while a fit runs, its best so far seldom)."""
        item = isinstance(x, I.Item)
        key = (x if item else (x.kind, x.freq, x.gain, x.q), self.origin if item else None, self.fs, len(freqs))
        c = self.curves.get(key)
        if c is None:
            if len(self.curves) > CURVES_KEPT:
                self.curves.clear()
            c = self.curves[key] = (I.item_db(x, self.origin, self.fs, freqs) if item else
                                    I.placed_db(x, self.fs, freqs))
        return c

    def summed(self, xs, freqs):
        return sum((self.curve(x, freqs) for x in xs), np.zeros(len(freqs)))

    def given(self, block, freqs):
        """The input of an EQ block at freqs: the curve, or the sum of the lines checked for it; None without."""
        if self.cf is not None:
            return None if self.column is None else C.curve(self.cf, self.column, freqs)
        group, tone = self.groups.get(block), I.tone_items(self.chosen)
        return None if group is None and not tone else self.summed((group or []) + tone, freqs)

    def show_graph(self):
        """The conversion's result, and only that: what it does not set is flat. Which blocks go to the device, and
        what the device has now, do not count here."""
        freqs = self.graph.freqs()
        channels, names, shifts, self.deviation = [], {}, {}, []
        sides = [(0, "L"), (1, "R")] if self.dual else [(0, "all")]
        for side, block in sides:
            # drawn at the graph's resolution; how far off, at the frequencies where curves are compared
            given = self.given(block, freqs)
            if given is None:
                continue
            key = "L" if side == 0 else "R"
            placed = list(self.outcome.get(block, {}).values()) + list(self.outcome.get("BT", {}).values())
            # the sum and its bands as the device makes them; the input moved to their level when a fit chose one
            level = self.levels.get(block, 0.0)
            shifts[key] = level
            color = side_color(side, self.dual)
            shown_bands = [(self.curve(p, freqs), theme.BT if p.target in I.TONE else color,
                            "BT" if p.target in I.TONE else key) for p in placed]
            tried = None
            if self.fitting:
                r = next((r for blocks, r in self.tried.items() if block in blocks), None)
                if r is not None:                        # on the input, with a level of its own
                    tried = self.summed(list(I.from_fit(r).values()), freqs) - r.level + level
            total = None
            if self.outcome:
                total = sum((c for c, _, _ in shown_bands), np.zeros(len(freqs)))
                self.deviation.append((self.summed(placed, F.FREQS) - level, self.given(block, F.FREQS)))
            channels.append((key, color, given + level, total, shown_bands, tried))
            names[key] = (("EQ Left", "EQ Right")[side] if self.dual else "EQ (shared)", color)
        if self.outcome.get("BT"):
            names["BT"] = ("Bass/Treble", theme.BT)
        self.legend.set_input(*_adjusted(shifts))
        self.legend.set_fitting(self.fitting)
        self.graph.draw(channels)
        if names != self.names:
            self.names = names
            self.legend.set_channels(names)

    def show_status(self, on, limited):
        parts = []                                       # (text, amber)
        if not self.connected:
            parts.append(("The device is not connected", True))
        if self.problem:
            parts.append((self.problem, True))
        elif self.outcome and not on:
            parts.append(("Nothing to load into the device", True))
        if self.outcome and not self.problem and not self.fitting:
            worst = max((float(np.max(np.abs(t - g))) for t, g in self.deviation), default=0.0)
            if self.mode == FIT:
                rms = max((float(np.sqrt(np.mean((t - g) ** 2))) for t, g in self.deviation), default=0.0)
                text = "Fitted  ·  %.2f dB RMS, at most %.1f dB off the input" % (rms, worst)
                level = self.levels.get(self.eq_blocks()[0], 0.0)
                if abs(level) >= LEVEL_SHOWN:
                    text += "  ·  %.1f dB %s than the input" % (abs(level), "louder" if level > 0 else "quieter")
                parts.append((text, False))
            else:
                parts.append(("Mapped  ·  at most %.1f dB off the input" % worst, False))
        if limited and not self.fitting:
            parts.append(("%d value%s limited" % (limited, "" if limited == 1 else "s"), False))
        pending = I.changes(self.session.state, self.values) if on else {}
        self.unchanged = bool(on and self.values) and not pending and not self.fitting and not self.problem
        if self.unchanged:
            parts.append(("Already in the preset" if self.preset else "Already on the device", False))
        parts += [(w, True) for w in self.warnings(on)]
        self.status.setText("&nbsp;&nbsp;·&nbsp;&nbsp;".join(
            '<span style="color:%s">%s</span>' % ((theme.WARN if amber else theme.LABEL).name(), _html(t))
            for t, amber in parts))
        self.progress.setVisible(self.fitting)
        self.fitting_label.setVisible(self.fitting)
        self.enough.setEnabled(self.fitting and self.thread is not None and
                               set(self.results) == set(self.job_curves))
        self.progress.setValue(int(self.fraction * 1000))
        self.ok.setEnabled(self.connected and not self.fitting and not self.problem and bool(on) and
                           bool(self.values))

    def warnings(self, on):
        """What is about the file or the device as a whole."""
        eq = self.eq
        w = (list(eq.warnings) if eq else []) + ([self.drop_note] if self.drop_note else [])
        name = self.name.replace("·", "-")
        if eq and eq.output and eq.output != name:
            w.append("Saved from %s" % eq.output)
        if eq and eq.source == "commander" and eq.table and E.table(eq) is None:
            w.append("The table is incomplete or unreadable; the Filter lines load")
        if eq and self.origin == I.ADI2 and E.disagreeing(eq):
            w.append("The Filter lines differ from the table; the table loads")
        s = self.session.state
        tone_on = s.get((self.left, P.BT_ENABLE)) == 1
        bt = self.outcome.get("BT", {})
        if "BT" in on and bt:
            if not tone_on:
                w.append("Bass/Treble is off on the device")
            elif s.get((self.out, P.AUTO_REF_LEVEL)) == 1 and any(p.gain > 0 for p in bt.values()):
                w.append("Auto Ref Level with a positive Bass/Treble gain: Ref Level may change")
        for block in self.eq_blocks():
            addr = self.right if block == "R" else self.left
            if block in on and self.defined(block) and s.get((addr, P.EQ_ENABLE)) == 0:
                w.append("EQ is off on the device" if not self.dual else
                         "EQ %s is off on the device" % ("Left" if block == "L" else "Right"))
        return w

    # -- closing --------------------------------------------------------------------------------------
    def accept(self):
        if not self.ok.isEnabled():
            return
        super().accept()

    def close_down(self, *_):
        LoadDialog.maximized = self.isMaximized()
        self.stop_fit()
        self.repaint_soon.stop()
        for t in self.threads:
            t.requestInterruption()
            t.wait()
        self.threads.clear()
        for callbacks, f in ((self.session.on_connection, self.connection), (self.session.on_changed, self.changed)):
            if f in callbacks:
                callbacks.remove(f)


def _db(x):
    return round(float(x), 1) + 0.0                      # no -0.0


def _adjusted(shifts):
    """The input's name in the legend, and its tooltip: how far a fit moved it, per channel ({'L' or 'R': dB})."""
    if all(abs(v) < LEVEL_SHOWN for v in shifts.values()):
        return "Input", ""
    values = {"%+.1f dB" % _db(v) for v in shifts.values()}
    if len(values) == 1:
        how = values.pop()
    else:
        how = ", ".join("%s %+.1f dB" % ({"L": "left", "R": "right"}[k], _db(v)) for k, v in shifts.items())
    return "Input (adj.)", "Moved %s onto the sum: the fit leaves the level free\n" % how


def _html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
