"""The graph's legend, which is also how one chooses what it shows: two groups, the channels (EQ Left, EQ Right,
Bass/Treble), each a line in its colour, and the layers (Sum, Bands, Handles, and the sums at the rate the device runs
at when that is another than the chosen one), each as it looks in the graph.

    click           shows or hides the item
    double-click    shows only this item of its group; again: the whole group
    point at it     its curves light up in the graph

With too little room beside the sample rates, the groups go one under the other (set_stacked).
"""

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QBoxLayout, QHBoxLayout, QLabel, QWidget

from . import theme
from .graph import (BAND_ALPHA, BAND_W, COMPARE_W, DEVIATION_FILL, DEVIATION_W, INPUT_ALPHA, INPUT_W, SUM_W,
                    side_color)

GROUPS = [["L", "R", "BT"], ["sum", "bands", "handles", "compare"]]
GROUP_GAP = 28                                   # pixels between the two groups side by side
ROW_GAP = 4                                      # ... and one under the other
ITEM_PAD = 6                                     # px: room around an item's mark and name, to point at
MARK_W, MARK_H = 12, 10                          # px: every mark as wide, shown or hidden, so nothing moves
MARKS = {"L": "line", "R": "line", "BT": "line", "sum": "thick", "bands": "thin", "handles": "ring",
         "compare": "dashed"}


def mark_pixmap(kind, color):
    """The mark of an item, drawn: a line in a channel's colour, or a layer as it looks in the graph: a thick line
    for Sum, a thin one for Bands, a ring for the handles, dashed for the compared sums. Also the Loudness graph's:
    a small curve for Loudness, high at both ends as its boost, and dotted for the current volume. And Import's
    deviation: a wave about 0 with the area between filled."""
    scale = 4                                    # drawn large, shown small: sharp at any display scaling
    pm = QPixmap(MARK_W * scale, MARK_H * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    cy = MARK_H / 2
    if kind == "ring":
        p.setPen(QPen(color, 1))
        p.drawEllipse(QPointF(MARK_W / 2, cy), 3.5, 3.5)
    elif kind == "area":                         # as the deviation (Import): a wave about 0, the area between filled
        amp, mid = 3.0, MARK_W / 2
        path = QPainterPath(QPointF(0, cy))      # up, then down, each half a sine's shape
        path.cubicTo(QPointF(1.2, cy - amp * 1.33), QPointF(mid - 1.2, cy - amp * 1.33), QPointF(mid, cy))
        path.cubicTo(QPointF(mid + 1.2, cy + amp * 1.33), QPointF(MARK_W - 1.2, cy + amp * 1.33),
                     QPointF(MARK_W, cy))
        area = QColor(color)
        area.setAlphaF(color.alphaF() * DEVIATION_FILL)
        p.fillPath(path, area)
        pen = QPen(color, DEVIATION_W)
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        p.drawPath(path)
    elif kind == "curve":
        pen = QPen(color, 1.5)                   # thinner than a channel's line, or the shape closes up
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        # shallow; a little lower than the straight marks
        top, bottom = cy - 0.5, cy + 1.5
        path = QPainterPath(QPointF(0, top))     # a shoulder, a slope as a shelf's, the bottom, and back up
        path.lineTo(QPointF(1.5, top))
        path.cubicTo(QPointF(3, top), QPointF(3, bottom), QPointF(4.5, bottom))
        path.lineTo(QPointF(MARK_W - 4.5, bottom))
        path.cubicTo(QPointF(MARK_W - 3, bottom), QPointF(MARK_W - 3, top), QPointF(MARK_W - 1.5, top))
        path.lineTo(QPointF(MARK_W, top))
        p.drawPath(path)
    else:
        width = {"line": 2.0, "thick": SUM_W, "thin": BAND_W, "dashed": COMPARE_W, "dotted": 1.0,
                 "wide": INPUT_W}[kind]
        if kind in ("thin", "wide"):             # as faint as a band beside the sum; as see-through as an input
            color = QColor(color)
            color.setAlphaF(color.alphaF() * (BAND_ALPHA if kind == "thin" else INPUT_ALPHA))
        pen = QPen(color, width)
        pen.setCapStyle(Qt.FlatCap)
        if kind == "dashed":
            pen.setDashPattern([2, 1])                                     # 4 px on, 2 off
        elif kind == "dotted":
            pen.setDashPattern([1, 3])                                     # as the Loudness graph's family
        p.setPen(pen)
        p.drawLine(QPointF(1, cy), QPointF(MARK_W - 1, cy))
    p.end()
    return pm


class _Item(QWidget):
    """Its mark, then the name. Hidden: both grey, nothing else changes."""

    clicked = Signal()
    double_clicked = Signal()
    pointed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.mark, self.name = QLabel(), QLabel()
        self.mark.setFixedSize(MARK_W, MARK_H)
        self.color, self._drawn = None, None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(ITEM_PAD, 0, ITEM_PAD, 0)
        lay.setSpacing(5)
        for w in (self.mark, self.name):
            lay.addWidget(w)
        self._after_double = False               # the release that ends a double-click is no click

    def show_mark(self, kind, color):
        self.color = color
        if (kind, color.rgb()) != self._drawn:
            self._drawn = (kind, color.rgb())
            self.mark.setPixmap(mark_pixmap(kind, color))

    def mouseReleaseEvent(self, e):
        if self._after_double:
            self._after_double = False
            return
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._after_double = True
            self.double_clicked.emit()

    def enterEvent(self, e):
        self.pointed.emit(True)

    def leaveEvent(self, e):
        self.pointed.emit(False)


class Legend(QWidget):
    changed = Signal()                           # visibility changed

    def __init__(self, graph):
        super().__init__()
        self.graph = graph
        self.items = {k: _Item() for g in GROUPS for k in g}
        self.groups, self.stacked = [], False
        lay = QBoxLayout(QBoxLayout.LeftToRight, self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GROUP_GAP)
        for keys in GROUPS:
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
            lay.addWidget(group, 0, Qt.AlignHCenter)
            self.groups.append(group)
        self._before = None                      # the group's state before the first click of a double-click
        self.refresh()

    def size_for(self, stacked):
        """The legend's size with its groups side by side, or one under the other."""
        sizes = [g.sizeHint() for g in self.groups]
        if stacked:
            return QSize(max(s.width() for s in sizes), sum(s.height() for s in sizes) + ROW_GAP)
        return QSize(sum(s.width() for s in sizes) + GROUP_GAP, max(s.height() for s in sizes))

    def first_row_height(self):
        return self.groups[0].sizeHint().height()

    def set_stacked(self, on, right=False):
        """The groups one under the other (the channels, then the layers), in the middle or on the right; or side
        by side."""
        lay = self.layout()
        if on != self.stacked:
            self.stacked = on
            lay.setDirection(QBoxLayout.TopToBottom if on else QBoxLayout.LeftToRight)
            lay.setSpacing(ROW_GAP if on else GROUP_GAP)
        for group in self.groups:
            lay.setAlignment(group, Qt.AlignRight if right else Qt.AlignHCenter)

    def _group(self, key):
        return next(g for g in GROUPS if key in g)

    def _shown(self, group):
        """The items of a group that are on screen now: EQ Right is not, with Dual EQ off."""
        return [k for k in group if self.items[k].isVisibleTo(self)]

    def toggle(self, key):
        v = self.graph.visible
        self._before = {k: v[k] for k in self._group(key)}
        v[key] = not v[key]
        self._apply()

    def isolate(self, key):
        """Only this item of its group; if it already was the only one, the whole group again."""
        v = self.graph.visible
        group = self._shown(self._group(key))
        before = self._before or {k: v[k] for k in group}
        alone = before.get(key) and not any(before.get(k) for k in group if k != key)
        for k in group:
            v[k] = True if alone else k == key
        self._before = None
        self._apply()

    def point(self, key, on):
        self.graph.emphasis = key if on and self.graph.visible[key] else None
        self.graph.redraw()

    def _apply(self):
        self.refresh()
        self.graph.redraw()
        self.changed.emit()

    def refresh(self):
        dual, compare = self.graph.dual, self.graph.fs_compare
        names = {"L": "EQ Left" if dual else "EQ (shared)", "R": "EQ Right", "BT": "Bass/Treble",
                 "sum": "Sum", "bands": "Bands", "handles": "Handles",
                 "compare": "<i>f</i><sub>s</sub> %g kHz" % (compare / 1000) if compare else ""}
        colors = {"L": side_color(0, dual), "R": side_color(1, dual), "BT": side_color(None, dual)}
        for k, item in self.items.items():
            on = self.graph.visible[k]
            item.show_mark(MARKS[k], colors.get(k, theme.TEXT) if on else theme.OFF)
            if item.name.text() != names[k]:
                item.name.setText(names[k])
                item.updateGeometry()                # its new width counts now, not after the next event loop pass
            item.name.setStyleSheet("color: %s;" % (theme.LABEL if on else theme.OFF).name())
            group = ("channel", "channels") if k in GROUPS[0] else ("layer", "layers")
            note = {"compare": "The sums at the rate the device runs at\n",
                    "bands": "Includes Bass and Treble\n" if self.graph.has_bt else "",
                    "handles": "The points: drag, wheel and click\n"
                               "Off: the band labels stay, but only inform.\n"}.get(k, "")
            item.setToolTip(note +
                            "Click: show or hide · Double-click: only this %s; again: all %s" % group)
        self.items["R"].setVisible(dual)
        self.items["BT"].setVisible(self.graph.has_bt)
        self.items["compare"].setVisible(compare is not None)
