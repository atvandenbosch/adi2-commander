"""The parameter tables: a model over the session state, a delegate that draws what a cell is doing, and a
view that turns keys, wheel and drag into steps.

A cell shows its state before any text does:
    flash        the value was rounded or clamped before sending, or changed on the device itself
    spinners     up/down buttons on the right; the one pointing past a band limit is greyed out
    red border   read-back differs from what was sent, until a later write verifies
    dimmed       the value has no effect now (B/T or Loudness off, gain of a High Pass / High Cut) or is not
                 writable
"""

import time

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHeaderView, QLineEdit, QStyle,
                               QStyledItemDelegate, QTableView)

from ..device import filters as F
from ..device import params as P
from . import theme

KEY_ROLE = Qt.UserRole + 1
FLASH_TIME = 0.6
SPIN_WIDTH = 16                                  # the up/down buttons at the right of every cell
CELL_FONT = 10.5                                 # pt: the values; 14 px at 96 dpi
CHOSEN_ALPHA = 0.5                               # the chosen cell while its table has no focus: the focus colour


class Cell:
    """What one cell shows: a parameter key, or a fixed text (band 2-4 type, Loudness Freq and Q; a number
    is aligned right, as the values around it)."""

    def __init__(self, key=None, band=None, fixed=None, number=False):
        self.key, self.band, self.fixed, self.number = key, band, fixed, number


def band_address(out, side, session):
    """Where one channel's EQ is (side 0 = left, 1 = right). With Dual EQ off both channels have the one EQ, on
    the left address: both tables and both switches work on it, alike."""
    return out[2 + side] if session.dual(out[1]) else out[2]


def band_rows(side):
    """Rows for one channel's table (side 0 = left, 1 = right): a band per row, Type, Freq, Gain, Q."""
    def build(out, session):
        a = band_address(out, side, session)
        rows = []
        for band, (ti, gi, fi, qi) in P.BANDS.items():
            cells = [Cell((a, ti), band) if ti is not None else Cell(fixed="PK"),
                     Cell((a, fi), band), Cell((a, gi), band), Cell((a, qi), band)]
            rows.append(("Band %d" % band, cells))
        return rows
    return build


# (header, its tooltip): the unit names the column, the tooltip in words
BAND_COLUMNS = [("Type", "Filter type"), ("Hz", "Frequency"), ("dB", "Gain"), ("Q", "Q")]
BAND_WIDTHS = [72, 88, 88, 88]                   # Type, then Hz, dB and Q alike


def bt_rows(out, session):
    _, o, left, right = out
    return [("Bass", [Cell((left, i)) for i in (P.BASS[1], P.BASS[0], P.BASS[2])]),
            ("Treble", [Cell((left, i)) for i in (P.TREBLE[1], P.TREBLE[0], P.TREBLE[2])])]


BT_COLUMNS = [("Hz", "Frequency"), ("dB", "Gain"), ("Q", "Q")]
BT_WIDTHS = [88, 88, 88]


def loudness_rows(out, session):
    """As Bass/Treble, but Freq and Q are fixed in the device (filters.LOUDNESS_SHELVES); Low Vol Ref below."""
    o = out[1]
    rows = []
    for row, (_, _, freq, q), gi in zip(("Bass", "Treble"), F.LOUDNESS_SHELVES, (P.LD_BASS, P.LD_TREBLE)):
        rows.append((row, [Cell(fixed="%d" % freq, number=True), Cell((o, gi)),
                           Cell(fixed="%.1f" % q, number=True)]))
    rows.append(("Low Vol Ref", [Cell(fixed=""), Cell((o, P.LD_LOW_VOL_REF)), Cell(fixed="")]))
    return rows


LOUDNESS_COLUMNS = [("Hz", "Frequency, fixed in the device"),
                    ("dB", "Bass and Treble: the boost at Low Vol Ref and below\nLow Vol Ref: a volume"),
                    ("Q", "Q, fixed in the device")]
NOTES = {("out", P.LD_BASS): "Maximum boost, at and below Low Vol Ref",
         ("out", P.LD_TREBLE): "Maximum boost, at and below Low Vol Ref",
         ("out", P.LD_LOW_VOL_REF): "Volume with the full Bass and Treble Gain;\nno boost 20 dB above it"}


class ParamModel(QAbstractTableModel):
    def __init__(self, session, marks, build_rows, columns):
        super().__init__()
        self.session, self.marks = session, marks
        self.build_rows, self.columns = build_rows, columns
        self.rows = []

    def set_output(self, out):
        self.beginResetModel()
        self.out = out
        self.rows = self.build_rows(out, self.session)
        self.endResetModel()

    def refresh(self):
        """The keys can follow the state (Dual EQ); the shape of the table does not, so the cursor stays."""
        if self.rows:
            self.rows = self.build_rows(self.out, self.session)
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, self.columnCount() - 1))

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.rows[0][1]) if self.rows else len(self.columns)

    def cell(self, index):
        return self.rows[index.row()][1][index.column()]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role in (Qt.DisplayRole, Qt.ToolTipRole):
            return self.columns[section][role == Qt.ToolTipRole]
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return self.rows[section][0]
        return None

    def value(self, cell):
        return self.session.state.get(cell.key) if cell.key else None

    def inactive(self, cell):
        """True when the value has no effect now."""
        if cell.key is None or self.session.bypassed():
            return True
        a, i = cell.key
        s = self.session.state
        if a in P.OUTPUT_ADDRESSES:
            return s.get((a, P.LOUDNESS_ENABLE)) == 0
        if i in (P.BASS + P.TREBLE) and s.get((a, P.BT_ENABLE)) == 0:
            return True
        if cell.band is not None and s.get((a, P.EQ_ENABLE)) == 0:      # this channel's EQ is off
            return True
        if cell.band is not None and self.session.eq_bypassed(self.out[1]):
            return True
        if cell.band in P.NO_GAIN_TYPES and i == P.BANDS[cell.band][1]:
            return s.get((a, P.BANDS[cell.band][0])) in P.NO_GAIN_TYPES[cell.band]
        return False

    def can_step(self, cell, direction):
        """Whether the up (+1) or down (-1) button does anything: editable and not at the band limit."""
        if not self.editable(cell):
            return False
        v = self.value(cell)
        if P.kind(P.spec(cell.key)) == "type":
            return 0 <= v + direction < len(P.BAND_TYPES[cell.band])
        if P.kind(P.spec(cell.key)) == "switch":
            return False
        return P.at_limit(P.spec(cell.key), v) != direction

    def editable(self, cell):
        """Editable even when it has no effect now (B/T off, gain of HP/LP): it can be set in advance."""
        return cell.key is not None and self.session.writable(cell.key)

    def data(self, index, role=Qt.DisplayRole):
        cell = self.cell(index)
        if role == Qt.DisplayRole:
            if cell.fixed:
                return cell.fixed if self.session.ready() else ""
            v = self.value(cell)
            return "" if v is None else P.to_text(P.spec(cell.key), v, cell.band)
        if role == KEY_ROLE:
            return cell
        if role == Qt.TextAlignmentRole:
            return int((Qt.AlignLeft if (cell.fixed and not cell.number)
                        or (cell.key and P.kind(P.spec(cell.key)) == "type")
                        else Qt.AlignRight) | Qt.AlignVCenter)
        if role == Qt.ToolTipRole and cell.key:
            return self.marks.tooltip(cell)
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.editable(self.cell(index)):
            f |= Qt.ItemIsEditable
        return f


class Marks:
    """Per-key visual state that is not in the device: flashes and read-back mismatches."""

    def __init__(self):
        self.flash = {}          # key -> start time
        self.mismatch = {}       # key -> (sent, actual)
        self.on_flash = []       # called when a flash starts: the tables that let it fade

    def start_flash(self, key):
        self.flash[key] = time.monotonic()
        for f in self.on_flash:
            f()

    def flashing(self):
        """A flash is still fading."""
        now = time.monotonic()
        return any(now - t < FLASH_TIME for t in self.flash.values())

    def flash_level(self, key):
        t = self.flash.get(key)
        if t is None:
            return 0.0
        x = 1 - (time.monotonic() - t) / FLASH_TIME
        if x <= 0:
            del self.flash[key]
            return 0.0
        return x

    def tooltip(self, cell):
        i = P.spec(cell.key)
        lo, hi = P.RANGES[i]
        k = P.kind(i)
        if k == "type":
            text = "\n".join("%s  %s" % t for t in zip(P.TYPE_ABBR[cell.band], P.TYPE_LONG[cell.band]))
        else:
            step = {"freq": "1 Hz up to 2040 Hz, 10 Hz above", "gain": "0.5 dB", "q": "0.1"}.get(k, "")
            text = "%s … %s, step %s" % (P.to_text(i, lo), P.to_text(i, hi), step)
            if i in NOTES:
                text = NOTES[i] + "\n" + text
        if cell.key in self.mismatch:
            sent, actual = self.mismatch[cell.key]
            text += "\nSent %s, device has %s" % (P.to_text(i, sent, cell.band), P.to_text(i, actual, cell.band))
        return text


class CellDelegate(QStyledItemDelegate):
    edited = Signal(object, int, bool)             # key, value, rounded or clamped
    spinners = True                                 # off for a table that only shows

    def __init__(self, model, marks, color=theme.LEFT, parent=None):
        super().__init__(parent)
        self.model, self.marks = model, marks
        self.color = color                              # focus and flash, in the colour of the channel
        self.editor = None
        self.hover = None                               # (row, column, +1 / -1) under the mouse

    def paint(self, painter, option, index):
        cell = index.data(KEY_ROLE)
        r = option.rect
        painter.save()
        # Two different greys, kept apart: a cell that is no field at all (fixed PK of band 2-4) looks like a
        # label: no field background, no spinners. A field whose value has no effect now (EQ or B/T off, gain of
        # HP/LP) stays a field with working spinners; only its text is dimmed. Without a device every cell
        # is simply empty, so the table has no holes.
        field = cell.fixed is None or not self.model.session.ready()
        painter.fillRect(r, theme.CELL if field else theme.BACKGROUND)
        if field and option.state & QStyle.State_HasFocus:
            painter.fillRect(r, self.color.darker(300))
        elif field and getattr(option.widget, "chosen", False) and index == option.widget.currentIndex():
            c = self.color.darker(300)
            c.setAlphaF(CHOSEN_ALPHA)
            painter.fillRect(r, c)
        if cell.key:
            level = self.marks.flash_level(cell.key)
            if level:
                c = QColor(self.color)
                c.setAlphaF(0.45 * level)
                painter.fillRect(r, c)
        painter.setFont(theme.mono_font(CELL_FONT))
        painter.setPen(index.data(Qt.ForegroundRole) or (theme.OFF if self.model.inactive(cell) else
                                                         theme.TEXT if field else theme.SECONDARY))
        text = index.data(Qt.DisplayRole) or ""
        painter.drawText(r.adjusted(8, 0, -8 - SPIN_WIDTH, 0), index.data(Qt.TextAlignmentRole), text)
        if text and field and self.spinners:
            for d in (1, -1):
                self._spinner(painter, r, d, self.model.can_step(cell, d),
                              self.hover == (index.row(), index.column(), d))
        if cell.key and cell.key in self.marks.mismatch:
            painter.setPen(QPen(theme.BAD, 2))
            painter.drawRect(r.adjusted(1, 1, -2, -2))
        painter.restore()

    @staticmethod
    def spinner_at(rect, pos):
        """+1 over the up button, -1 over the down button, 0 elsewhere."""
        if pos.x() < rect.right() - SPIN_WIDTH:
            return 0
        return 1 if pos.y() < rect.center().y() else -1

    @staticmethod
    def _spinner(painter, r, direction, enabled, hovered):
        """Up (+1) or down (-1) button at the right edge; greyed out when it cannot go further."""
        half = r.height() // 2
        box = QRect(r.right() - SPIN_WIDTH + 1, r.top() if direction > 0 else r.top() + half, SPIN_WIDTH - 1, half)
        if hovered and enabled:
            painter.fillRect(box, theme.GRID)
        cx, cy, s = box.center().x(), box.center().y(), 4
        pts = ([QPoint(cx - s, cy + 2), QPoint(cx + s, cy + 2), QPoint(cx, cy - 2)] if direction > 0 else
               [QPoint(cx - s, cy - 2), QPoint(cx + s, cy - 2), QPoint(cx, cy + 2)])
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.TEXT if hovered and enabled else theme.SPIN if enabled else theme.SPIN_OFF)
        painter.drawPolygon(QPolygon(pts))

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect.adjusted(0, 0, -SPIN_WIDTH, 0))    # the spinners stay usable

    def createEditor(self, parent, option, index):
        cell = index.data(KEY_ROLE)
        if P.kind(P.spec(cell.key)) == "type":
            e = QComboBox(parent)
            e.addItems(["%s — %s" % t for t in zip(P.TYPE_ABBR[cell.band], P.TYPE_LONG[cell.band])])
            e.view().setMinimumWidth(220)                 # the list shows the full names
            e.activated.connect(lambda _: self.commitData.emit(e))
        else:
            e = QLineEdit(parent)
            e.setAlignment(Qt.AlignRight)
        e.setFont(theme.mono_font(CELL_FONT))
        self.editor = e
        e.destroyed.connect(lambda *_: setattr(self, "editor", None))
        return e

    def setEditorData(self, editor, index):
        cell = index.data(KEY_ROLE)
        v = self.model.value(cell)
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(v or 0)
            editor.showPopup()
        elif not editor.text():
            editor.setText(index.data(Qt.DisplayRole) or "")
            editor.selectAll()

    def setModelData(self, editor, model, index):
        cell = index.data(KEY_ROLE)
        if isinstance(editor, QComboBox):
            self.edited.emit(cell.key, editor.currentIndex(), False)
            return
        try:
            value, adjusted = P.parse(P.spec(cell.key), editor.text())
        except ValueError:
            return                                      # not a number: the old value stays
        self.edited.emit(cell.key, value, adjusted)


class ParamView(QTableView):
    """Keys: arrows up/down step the value (Ctrl finest, PgUp/PgDn large), left/right move cell by cell
    within the row, Alt+up/down move between rows (into the table above or below at the edge; the window
    decides which), Tab/Shift+Tab walk the editable fields of all tables in reading order (the window decides
    the order). Enter commits and stays.
    Spinners: click steps (Shift large, Ctrl finest), holding repeats. Wheel steps only the cell that has
    focus. Drag: see DRAG_TO_CHANGE."""

    stepped = Signal(object, int, bool)             # key, value, rounded
    walked_off = Signal(int, int)                   # direction, column: Alt+up/down past the first or last row
    tabbed = Signal(int)                            # Tab (+1) or Shift+Tab (-1): next field, possibly elsewhere
    DRAG_TO_CHANGE = True                           # drag up/down on the focused cell; can be switched off
    DRAG_PIXELS = 6
    HEADER_WIDTH = 80
    corner = None                                   # a widget above the row names, on the line of the column names
    chosen = False                                  # the table last worked in: its current cell stays coloured

    def __init__(self, model, delegate, header_width=HEADER_WIDTH):
        super().__init__()
        self.header_width = header_width
        self.setModel(model)
        self.setItemDelegate(delegate)
        self.model_, self.delegate = model, delegate
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.AnyKeyPressed)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(30)
        self.verticalHeader().setFixedWidth(self.header_width)
        self.setShowGrid(True)
        self.setCornerButtonEnabled(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._drag = None
        self._flash_timer = QTimer(self, interval=40, timeout=self._fade)     # only while a flash fades
        delegate.marks.on_flash.append(self._flash_timer.start)
        self.setMouseTracking(True)
        self._spin = None                               # (index, direction, size) while a spinner is held
        self._repeat = QTimer(self, timeout=self._spin_repeat)

    def _fade(self):
        self.viewport().update()
        if not self.delegate.marks.flashing():           # drawn once more without it, then still
            self._flash_timer.stop()

    def set_corner(self, widget):
        """The table's switch in the corner: it heads the table, and stays bright when the cells are dimmed. Out of
        the Tab order; a click gives it the focus for a moment, the window passes it on. Without focus, the click
        would give it to the table."""
        self.corner = widget
        widget.setParent(self)
        widget.raise_()
        widget.setFocusPolicy(Qt.ClickFocus)
        self.updateGeometries()

    def take_focus(self):
        """Focus on the current cell, or else on the first that can be edited: where Tab enters the table."""
        if not self.currentIndex().isValid():
            m = self.model()
            first = next((m.index(r, c) for r in range(m.rowCount()) for c in range(m.columnCount())
                          if self.model_.editable(m.cell(m.index(r, c)))), None)
            if first is not None:
                self.setCurrentIndex(first)
        self.setFocus()

    def updateGeometries(self):
        super().updateGeometries()
        if self.corner is not None:
            head = self.horizontalHeader()
            self.corner.move(0, head.y() + (head.height() - self.corner.height()) // 2)

    def fit(self, widths):
        for c, w in enumerate(widths):
            self.setColumnWidth(c, w)
        w = self.header_width + sum(widths) + 2
        h = self.horizontalHeader().height() + 30 * self.model().rowCount() + 2
        self.setFixedSize(w, h)

    def _step(self, index, direction, size):
        cell = index.data(KEY_ROLE)
        if not index.isValid() or not self.model_.editable(cell) or P.kind(P.spec(cell.key)) == "switch":
            return
        v = self.model_.value(cell)
        if P.kind(P.spec(cell.key)) == "type":
            n = len(P.BAND_TYPES[cell.band])
            new = min(max(v + direction, 0), n - 1)
        else:
            new = P.step(P.spec(cell.key), v, direction, size)
        if new != v:
            self.stepped.emit(cell.key, new, False)

    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        idx = self.currentIndex()
        if k in (Qt.Key_Up, Qt.Key_Down) and mods & Qt.AltModifier:
            direction = -1 if k == Qt.Key_Up else 1
            row = idx.row() + direction
            if 0 <= row < self.model().rowCount():
                self.setCurrentIndex(self.model().index(row, idx.column()))
            else:
                self.walked_off.emit(direction, idx.column())
            return
        if k in (Qt.Key_Up, Qt.Key_Down):
            self._step(idx, 1 if k == Qt.Key_Up else -1, "finest" if mods & Qt.ControlModifier else "small")
            return
        if k in (Qt.Key_PageUp, Qt.Key_PageDown):
            self._step(idx, 1 if k == Qt.Key_PageUp else -1, "large")
            return
        last = self.model().columnCount() - 1
        if (k == Qt.Key_Right and idx.column() == last) or (k == Qt.Key_Left and idx.column() == 0):
            return                                      # the edge of the row: stay, and keep the key from scrolling
        if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_F2) and self.state() != QAbstractItemView.EditingState:
            self.edit(idx)
            return
        super().keyPressEvent(e)

    def event(self, e):
        # Tab would otherwise move focus to the next widget or wrap inside this table; the window owns the
        # order across the tables. Ctrl+Tab is left alone: it switches outputs.
        if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Tab, Qt.Key_Backtab) \
                and not e.modifiers() & Qt.ControlModifier:
            self.tabbed.emit(-1 if e.key() == Qt.Key_Backtab or e.modifiers() & Qt.ShiftModifier else 1)
            return True
        return super().event(e)

    def closeEditor(self, editor, hint):
        """Tab while typing: commit, then go to the next field in the window's order."""
        if hint in (QStyledItemDelegate.EditNextItem, QStyledItemDelegate.EditPreviousItem):
            super().closeEditor(editor, QStyledItemDelegate.NoHint)
            self.tabbed.emit(1 if hint == QStyledItemDelegate.EditNextItem else -1)
            return
        super().closeEditor(editor, hint)

    def wheelEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        if self.hasFocus() and idx.isValid() and idx == self.currentIndex():
            mods = e.modifiers()
            self._step(idx, 1 if e.angleDelta().y() > 0 else -1, self._size(mods))
            e.accept()
            return
        e.ignore()                                    # not the focused cell: leave the value alone

    @staticmethod
    def _size(mods):
        return "large" if mods & Qt.ShiftModifier else "finest" if mods & Qt.ControlModifier else "small"

    def _spinner_under(self, pos):
        idx = self.indexAt(pos)
        if not idx.isValid():
            return idx, 0
        return idx, CellDelegate.spinner_at(self.visualRect(idx), pos)

    def _spin_repeat(self):
        idx, d, size = self._spin
        self._step(idx, d, size)
        self._repeat.setInterval(70)

    def mousePressEvent(self, e):
        idx, d = self._spinner_under(e.position().toPoint())
        if d and e.button() == Qt.LeftButton:
            self.setCurrentIndex(idx)
            self.setFocus()
            if self.model_.can_step(idx.data(KEY_ROLE), d):
                self._spin = (idx, d, self._size(e.modifiers()))
                self._step(idx, d, self._spin[2])
                self._repeat.start(400)                 # hold to repeat
            return
        if self.DRAG_TO_CHANGE and e.button() == Qt.LeftButton and idx.isValid() and idx == self.currentIndex():
            self._drag = (e.position().y(), 0)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        idx, d = self._spinner_under(e.position().toPoint())
        hover = (idx.row(), idx.column(), d) if d else None
        if hover != self.delegate.hover:
            self.delegate.hover = hover
            self.viewport().update()
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            y0, done = self._drag
            steps = int((y0 - e.position().y()) / self.DRAG_PIXELS)
            while done != steps:
                d = 1 if steps > done else -1
                self._step(self.currentIndex(), d, "small")
                done += d
            self._drag = (y0, done)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        if self._spin is not None:
            self._spin = None
            self._repeat.stop()
            return
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self.delegate.hover = None
        self.viewport().update()
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self._spinner_under(e.position().toPoint())[1]:
            self.mousePressEvent(e)                     # a quick second click on a spinner is a second step
            return
        super().mouseDoubleClickEvent(e)

    def cancel_edit_if(self, keys):
        """A value changed on the device while it is being edited here: the device wins, the edit goes."""
        if self.state() == QAbstractItemView.EditingState and self.delegate.editor is not None:
            cell = self.currentIndex().data(KEY_ROLE)
            if cell and cell.key in keys:
                self.closeEditor(self.delegate.editor, QStyledItemDelegate.RevertModelCache)
