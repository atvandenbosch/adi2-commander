"""The veil over the window while a preset is edited: a dialog that does not pop up. What belongs to the edit stays
clear, the page (the stage and the sound column) and its tab (the preset's row, joined to the page); the rest lies
under the veil, drawn but out of reach. An outline goes around what stays clear. The tab stands a little higher than
the row, over the edges of the rows beside it, on the ground of the page's column.

The veil only draws: mouse events go through it. What lies under it is disabled by the window, so that neither the
mouse nor the keyboard reaches it.

Without the veil (veil False) only the outline and the tab are drawn: the preview of a preset, which joins its row in
the same way but puts nothing out of reach."""

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme

VEIL = QColor(0, 0, 0, 150)
OUTLINE = theme.SECONDARY
GROUND = theme.BACKGROUND                        # of the sound column, and of the tab
MARGIN = 6                                       # px between the page's widgets and its outline
RADIUS = 4
RISE = 4                                         # px the tab stands out above and below its row


class Scrim(QWidget):
    outline = True                               # the line around what stays clear
    veil = True                                  # False: no veil, only the outline and the tab
    margin = MARGIN                              # px between the page's widgets and the outline

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.page, self.tab = [], None
        self.watched = []
        parent.installEventFilter(self)
        self.hide()

    def cover(self, page, tab=None):
        """page: the widgets that make the clear area, as one rectangle; tab: a widget beside it, joined to it, or
        None."""
        self.page, self.tab = page, tab
        for w in self.watched:
            w.removeEventFilter(self)
        self.watched = list(page) + ([tab] + self._ancestors(tab) if tab is not None else [])
        for w in self.watched:
            w.installEventFilter(self)
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def uncover(self):
        for w in self.watched:
            w.removeEventFilter(self)
        self.watched, self.page, self.tab = [], [], None
        self.hide()

    def _ancestors(self, w):
        """Up to the window: a row moves when its panel scrolls, without a move of its own."""
        out, p = [], w.parentWidget()
        while p is not None and p is not self.parentWidget():
            out.append(p)
            p = p.parentWidget()
        return out

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Resize, QEvent.Move, QEvent.Show, QEvent.Hide, QEvent.LayoutRequest):
            if obj is self.parentWidget():
                self.setGeometry(obj.rect())
            if self.isVisible():
                self.update()
        return False

    def _rect(self, w):
        top_left = w.mapTo(self.parentWidget(), w.rect().topLeft())
        return QRectF(top_left.x(), top_left.y(), w.width(), w.height())

    def clear_area(self):
        """What stays clear, as a path in the veil's coordinates; and the part of the tab beyond its row, to be
        covered, as a path too."""
        path, beyond = QPainterPath(), QPainterPath()
        shown = [w for w in self.page if w.isVisible()]
        if not shown:
            return path, beyond
        page = self._rect(shown[0])
        for w in shown[1:]:
            page = page.united(self._rect(w))
        page = page.adjusted(-self.margin, -self.margin, self.margin, self.margin)
        page = page.intersected(QRectF(self.rect()).adjusted(0, 0, -1, -1))       # the outline all around
        path.addRoundedRect(page, RADIUS, RADIUS)
        seen = self.tab.visibleRegion().boundingRect() if self.tab is not None else None
        if seen is not None and seen.height() == self.tab.height():        # a row half scrolled away is no tab
            row = self._rect(self.tab)
            tab = QPainterPath()
            # into the page past both rounded corners: where an edge of the tab runs on as the page's, no notch
            tab.addRoundedRect(QRectF(row.left(), row.top() - RISE, page.left() - row.left() + 2 * RADIUS,
                                      row.height() + 2 * RISE), RADIUS, RADIUS)
            path = path.united(tab).simplified()
            inside = QPainterPath()
            inside.addRect(row)
            left = QPainterPath()
            left.addRect(QRectF(row.left(), row.top() - RISE, page.left() - row.left(), row.height() + 2 * RISE))
            beyond = tab.subtracted(inside).intersected(left)
        return path, beyond

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        clear, beyond = self.clear_area()
        p.fillPath(beyond, GROUND)
        if self.veil:
            veil = QPainterPath()
            veil.setFillRule(Qt.OddEvenFill)
            veil.addRect(QRectF(self.rect()))
            veil.addPath(clear)
            p.fillPath(veil, VEIL)
        if self.outline:
            p.setPen(QPen(OUTLINE, 1))
            p.drawPath(clear.translated(0.5, 0.5))
