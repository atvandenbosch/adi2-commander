"""Small widgets shared by the window and its panels: switches (a part of the sound in or out of the path),
options (a setting that decides how something behaves), a choice between ways (Segmented), steppers (one of a few
values), one of many values in groups, actions (something done once), a list whose chosen value can stand out,
dots, a row of them, the style of a title, the file dropped on a window, and where a window opens on the screen."""

import math
import os

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton, QStyle, QStyleOptionComboBox,
                               QStylePainter, QWidget)

from ..device import params as P
from . import theme

TITLE_STYLE = "color: %s; letter-spacing: 1px;" % theme.LABEL.name()
GROUP_STYLE = "color: %s; letter-spacing: 1px;" % theme.SECONDARY.name()     # a group within a panel
# the room between the parts of a column, from close to apart, each step twice the one before
ATTACHED_GAP = 8                                 # what belongs to a table or list: Share above the bands, Load B/T
INNER_GAP = 16                                   # the parts of a section: under a title line, the channels, a graph
SECTION_GAP = 32                                 # between sections: the EQ, Bass/Treble and Loudness
SIDE = 18                                        # px from a window's left and right edge to what is in it
ACTION_STYLE = ("QPushButton { color: %(text)s; background: %(raised)s; border: 1px solid %(border)s;"
                " border-radius: 3px; padding: 2px 10px; font-size: 9pt; }"
                " QPushButton:hover { color: %(lit)s; border-color: %(dim)s; }"
                " QPushButton:pressed { background: %(panel)s; }"
                " QPushButton:disabled { color: %(disabled)s; background: %(panel)s; border-color: %(grid)s; }"
                % dict(text=theme.BUTTON_TEXT.name(), raised=theme.RAISED.name(), border=theme.BORDER.name(),
                       lit=theme.TEXT.name(), dim=theme.SECONDARY.name(), panel=theme.PANEL.name(),
                       disabled=theme.DISABLED.name(), grid=theme.GRID.name()))


def switch_style(on, color=theme.LEFT, bypassed=False):
    """A switch as a rounded outline: in its colour when on, dim when off; on but bypassed faded and dashed,
    as a curve out of the signal path. Under the mouse only its background lights up: the colour and the dot say
    what it is and whether it is on, and stay as they are."""
    color = theme.faded(color) if on and bypassed else color
    return ("QPushButton { color: %s; background: %s; border: 1px %s %s; border-radius: 11px;"
            " padding: 3px 6px 3px 8px; font-size: 9pt; }"      # 8 px on both sides: Qt adds 2 after the text
            " QPushButton:hover { background: %s; }"
            " QPushButton:disabled { color: %s; border-color: %s; }"
            % ((color if on else theme.OFF).name(), theme.PANEL.name(), "dashed" if on and bypassed else "solid",
               (color if on else theme.GRID).name(), theme.RAISED.name(), theme.DISABLED.name(),
               theme.GRID.name()))


def switch_tip(what, on):
    """What the switch is for and what a click does; the settings stay, off is bypassed, not erased."""
    return "%s: %s\nClick to switch %s; the settings stay as they are." % (what, "on" if on else "off",
                                                                         "off" if on else "on")


DSD_BYPASS = "Bypassed while the input is DSD: the device has no DSP for DSD."


def input_eq_bypass(session):
    """Why the EQ of an output is bypassed while Session.eq_bypassed() says so."""
    return ("Bypassed at %g kHz while the EQ of the input is on: the %s then runs that EQ only."
            % (P.SAMPLE_RATES[session.state[P.SAMPLE_RATE]] / 1000, session.model.name))


def label_color(color):
    """The style of a label whose text is in a colour, for the label alone: a bare 'color' reaches its tooltip too,
    which is a window of its own."""
    return "QLabel:!window { color: %s; }" % color.name()


DOT, DOT_GAP = 5, 5                              # px: every dot in the window (a switch, the lamp, a chosen
                                                 # preset, the legend), and the room after it in a switch
SWITCH_HEIGHT = 22                               # the outline's radius is 11 px: lower, Qt drops the rounding


def dot_pixmap(color, filled=True, alpha=1.0, gap=0):
    """A dot, filled or a ring, drawn rather than the sign ● or ○: a sign sits at the height of lower case and
    hangs low beside capitals, and its size and font differ from system to system. Drawn, every dot is the same
    and in the middle. gap: empty room after it."""
    scale = 4                                    # drawn large, shown small: sharp at any display scaling
    pm = QPixmap((DOT + gap) * scale, DOT * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    c = QColor(color)
    c.setAlphaF(alpha)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(c, 0.8))
    p.setBrush(c if filled else Qt.NoBrush)
    p.drawEllipse(QRectF(0.4, 0.4, DOT - 0.8, DOT - 0.8))
    p.end()
    return pm


def dot_icon(color, filled):
    return QIcon(dot_pixmap(color, filled, gap=DOT_GAP))


class MoreButton(QPushButton):
    """Three dots one above the other: the menu of the app's own commands. Neutral grey as the status bar, lighter
    under the mouse. Drawn, as the dots on the tabs are. Sized and placed by the font of the tab bar beside it: Windows
    pairs 9 pt text with 16 px icons, and draws its signs within 14 of them; the dots are centred on the tabs'
    capitals, as an icon beside text is."""

    def __init__(self, tabs):
        super().__init__()
        fm = QFontMetricsF(tabs.font())
        self.box = round(fm.height()) - 2                # 16 - 2 at Segoe UI 9 pt
        height = tabs.sizeHint().height()
        # a tab's text is centred above its line, as Qt centres a line of text: the baseline follows; the capitals
        # as drawn, on whole pixels, rounded up
        baseline = (height - theme.TAB_LINE - fm.height()) / 2 + fm.ascent()
        self.middle = baseline - math.ceil(fm.capHeight()) / 2
        self.setFixedSize(self.box + 1, height)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)

    def paintEvent(self, event):
        c = theme.TEXT if self.underMouse() else theme.SECONDARY
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = self.box
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        for k in (-1, 0, 1):
            p.drawEllipse(QPointF(self.width() / 2, self.middle + k * d * 0.33), d * 0.09, d * 0.09)
        p.end()


class Dot(QLabel):
    """A dot among other widgets: filled or a ring, in a colour and at a brightness, or none (its place stays)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(DOT, DOT)
        self.on, self.color, self.filled, self.alpha = False, None, True, 1.0
        self.clear()

    def set(self, color, filled=True, alpha=1.0):
        self.on, self.color, self.filled, self.alpha = True, QColor(color), filled, alpha
        self.setPixmap(dot_pixmap(color, filled, alpha))

    def clear(self):
        self.on = False
        pm = QPixmap(DOT, DOT)
        pm.fill(Qt.transparent)
        self.setPixmap(pm)


class Switch(QPushButton):
    """A channel's setting that is on or off: its name, after a dot that is filled when on and a ring when off. A
    rounded outline in the channel's colour, as in the graph."""

    def __init__(self, name, color=theme.LEFT):
        super().__init__()
        self.name, self.color, self.on = name, color, False
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(DOT + DOT_GAP, DOT))
        self.setFixedHeight(SWITCH_HEIGHT)

    def show_state(self, on, enabled, tip, bypassed=None):
        """bypassed: why what it switches is bypassed (DSD_BYPASS, input_eq_bypass()), or None."""
        self.on = on
        self.setText(self.name)
        color = theme.faded(self.color) if bypassed else self.color
        self.setIcon(dot_icon(theme.DISABLED if not enabled else color if on else theme.OFF, on))
        self.setEnabled(enabled)
        self.setToolTip(tip + ("\n" + bypassed if on and bypassed else ""))
        self.setStyleSheet(switch_style(enabled and on, self.color, bool(bypassed)))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.ClickFocus)
        self.adjustSize()                                # as wide as its name

    def show_title(self, tip):
        """No switch, only its name in its colour, as a title: what it heads has no on or off here. A click does
        nothing."""
        self.on = True
        self.setText(self.name)
        self.setIcon(QIcon())
        self.setEnabled(True)
        self.setToolTip(tip)
        self.setStyleSheet("QPushButton { color: %s; background: transparent; border: none; padding: 3px 0px;"
                           " font-size: 9pt; letter-spacing: 1px; }" % self.color.name())
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.adjustSize()


class Choice(QComboBox):
    """A list to choose from whose chosen value can stand in a colour of its own, the arrow and the frame as
    always."""

    def __init__(self):
        super().__init__()
        self.value_color = None

    def set_value_color(self, color):
        self.value_color = color
        self.update()

    def paintEvent(self, e):
        p = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        if self.currentIndex() < 0:                      # nothing chosen: the placeholder, as QComboBox shows it
            opt.currentText = self.placeholderText()
        p.drawComplexControl(QStyle.CC_ComboBox, opt)
        if self.value_color is not None:
            opt.palette.setColor(QPalette.ButtonText, self.value_color)
        p.drawControl(QStyle.CE_ComboBoxLabel, opt)


class Action(QPushButton):
    """A one-off action on the device ('Share', 'Split'): a plain, square button in neutral grey. Switches are
    round and coloured: a state; actions are square and grey: something done once."""

    def __init__(self, compact=False):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.plain = ACTION_STYLE.replace("padding: 2px 10px", "padding: 1px 6px") if compact else ACTION_STYLE
        self.setStyleSheet(self.plain)

    def warn(self, on):
        """Its name in amber, under the mouse too, when a click does more than it seems; its tooltip says what."""
        sheet = self.plain
        if on:
            sheet = sheet.replace("{ color: %s;" % theme.BUTTON_TEXT.name(), "{ color: %s;" % theme.WARN.name())
            sheet = sheet.replace(":hover { color: %s;" % theme.TEXT.name(), ":hover { color: %s;" % theme.WARN.name())
        if self.styleSheet() != sheet:
            self.setStyleSheet(sheet)


class Option(QWidget):
    """A setting that decides how something behaves, on or off: a small track with a knob, then its full name.
    Neutral grey, never a channel's colour: it is no part of the sound (that is a Switch). On: the knob right and
    the name lit; off: the knob left and the name dim. Under the mouse only the track's background lights up, as
    with a Switch. A click, or Space or Enter with the focus, emits clicked. The focus comes with Tab only, not with
    a click, and shows as a grey ring around the track."""

    clicked = Signal()
    TRACK_W, TRACK_H, KNOB, GAP, RING = 26, 14, 8, 8, 2

    def __init__(self, name):
        super().__init__()
        self.name, self.on, self._hover = name, False, False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedHeight(SWITCH_HEIGHT)

    def sizeHint(self):
        w = self.RING + 1 + self.TRACK_W + self.GAP + self.fontMetrics().horizontalAdvance(self.name) + 2
        return QSize(w, SWITCH_HEIGHT)

    def show_state(self, on, enabled, tip):
        self.on = on
        self.setEnabled(enabled)
        self.setToolTip(tip)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled() and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and self.isEnabled():
            self.clicked.emit()
            return
        super().keyPressEvent(e)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off = theme.DISABLED
        line = (theme.TEXT if self.on else theme.OFF) if self.isEnabled() else off
        top, left, radius = (self.height() - self.TRACK_H) / 2, self.RING + 1, self.TRACK_H / 2
        if self.hasFocus():                          # grey, as the rest: the track keeps showing on or off
            p.setPen(QPen(theme.LABEL, 1))
            p.setBrush(Qt.NoBrush)
            r = self.RING
            p.drawRoundedRect(QRectF(0.5, top - r + 0.5, self.TRACK_W + 2 * r + 1, self.TRACK_H + 2 * r - 1),
                              radius + r, radius + r)
        p.setPen(QPen(line, 1))
        p.setBrush(theme.RAISED if self._hover and self.isEnabled() else theme.PANEL)
        p.drawRoundedRect(QRectF(left + 0.5, top + 0.5, self.TRACK_W - 1, self.TRACK_H - 1), radius, radius)
        inset = (self.TRACK_H - self.KNOB) / 2
        x = left + (self.TRACK_W - inset - self.KNOB if self.on else inset)
        p.setPen(Qt.NoPen)
        p.setBrush(line)
        p.drawEllipse(QRectF(x, top + inset, self.KNOB, self.KNOB))
        p.setPen((theme.TEXT if self.on else theme.LABEL) if self.isEnabled() else off)
        p.drawText(QRectF(left + self.TRACK_W + self.GAP, 0, self.width(), self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self.name)


class Segmented(QWidget):
    """A choice between ways of doing one thing, side by side as one control: the chosen one raised and lit, the
    others flat. Neutral grey, as an Option: it is no part of the sound. A click on another emits changed with its
    index; set_current does not."""

    changed = Signal(int)

    def __init__(self, names):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.buttons = []
        for i, name in enumerate(names):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.TabFocus)
            b.clicked.connect(lambda _=False, i=i: self._clicked(i))
            lay.addWidget(b)
            self.buttons.append(b)
        self.current = 0
        self._style()

    def set_current(self, i):
        self.current = i
        self._style()

    def set_enabled_at(self, i, on, tip=""):
        self.buttons[i].setEnabled(on)
        self.buttons[i].setToolTip(tip)
        self._style()

    def _clicked(self, i):
        if i != self.current:
            self.current = i
            self.changed.emit(i)
        self._style()

    def _style(self):
        last = len(self.buttons) - 1
        for i, b in enumerate(self.buttons):
            on = i == self.current
            b.setChecked(on)
            left = "3px" if i == 0 else "0"
            right = "3px" if i == last else "0"
            color = theme.TEXT if on else theme.SECONDARY if b.isEnabled() else theme.DISABLED
            b.setStyleSheet(
                "QPushButton { color: %s; background: %s; border: 1px solid %s; padding: 2px 14px; font-size: 9pt;"
                " border-top-left-radius: %s; border-bottom-left-radius: %s; border-top-right-radius: %s;"
                " border-bottom-right-radius: %s; %s }"
                " QPushButton:hover { background: %s; }"
                % (color.name(), (theme.RAISED if on else theme.PANEL).name(),
                   (theme.ACCENT if on else theme.BORDER).name(), left, left, right, right,
                   "font-weight: bold;" if on else "", theme.RAISED.name()))


class Stepper(QWidget):
    """One of a few values (DA Filter, Polarity): ‹ value ›. The arrows, the arrow keys and, with the focus, the
    wheel step one further; at either end the arrow is grey, as a spinner at a band limit. A click on the value, or
    Space or Enter, shows all values over it, the current one bold and in its place. The value that means off is
    grey, as a part of the sound that is off; a value that is on but bypassed is faded; a value that needs attention
    (Volume that is not what is heard, with Mute or Dim on; Hi-Power before headphones are plugged in) is amber. Read back otherwise than sent: a red border. Held: the device sets
    the value; it stays readable, and only the arrows are grey.

    For a range of numbers rather than a few names, override text, neighbour, widest, and entries or show_menu."""

    chosen = Signal(int)
    ARROW, HEIGHT = 16, 28

    def __init__(self, names, off=None):
        super().__init__()
        self.names, self.off = names, off
        self.value, self.faded, self.bad, self.held, self.warned, self._hover = None, False, False, False, False, 0
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFixedHeight(self.HEIGHT)

    def text(self, value):
        return self.names[value] if 0 <= value < len(self.names) else str(value)

    def neighbour(self, value, direction, fine):
        """The value one step further, or None past the end. fine: with Ctrl."""
        v = value + direction
        return v if 0 <= v < len(self.names) else None

    def entries(self):
        """The values in the list."""
        return list(range(len(self.names)))

    def widest(self):
        return self.names

    def sizeHint(self):
        return QSize(max(self.fontMetrics().horizontalAdvance(n) for n in self.widest()) + 2 * self.ARROW + 16,
                     self.HEIGHT)

    def show_state(self, value, enabled, tip, faded=False, bad=False, held=False, warned=False):
        self.value, self.faded, self.bad, self.held, self.warned = value, faded, bad, held, warned
        self.setEnabled(enabled and not held)
        self.setToolTip(tip)
        self.update()

    def can_step(self, direction):
        return (self.isEnabled() and self.value is not None
                and self.neighbour(self.value, direction, False) is not None)

    def step(self, direction, fine=False):
        v = self.neighbour(self.value, direction, fine) if self.isEnabled() and self.value is not None else None
        if v is not None:
            self.chosen.emit(v)

    def menu(self):
        """All values, the current one bold; choosing another emits chosen."""
        m = QMenu(self)
        m.setMinimumWidth(self.width())
        for v in self.entries():
            a = m.addAction(self.text(v))
            if v == self.value:
                bold = a.font()
                bold.setBold(True)
                a.setFont(bold)
            a.triggered.connect(lambda _=False, v=v: v != self.value and self.chosen.emit(v))
        return m

    def show_menu(self):
        """Over the stepper, the current value where it stands, as a list box opens."""
        m = self.menu()
        current = m.actions()[self.entries().index(self.value)]
        m.exec(self.mapToGlobal(QPoint(0, 0)), current)

    def _zone(self, x):
        return -1 if x < self.ARROW else 1 if x >= self.width() - self.ARROW else 0

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.isEnabled() or self.value is None:
            return
        self.setFocus()
        zone = self._zone(e.position().x())
        if zone:
            self.step(zone, bool(e.modifiers() & Qt.ControlModifier))
        else:
            self.show_menu()

    def wheelEvent(self, e):
        if self.hasFocus():
            self.step(1 if e.angleDelta().y() > 0 else -1, bool(e.modifiers() & Qt.ControlModifier))
            e.accept()
            return
        e.ignore()                                   # without the focus: leave the value alone, let the panel scroll

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up):
            self.step(1 if k in (Qt.Key_Right, Qt.Key_Up) else -1, bool(e.modifiers() & Qt.ControlModifier))
        elif k in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_F4):
            if self.isEnabled() and self.value is not None:
                self.show_menu()
        else:
            super().keyPressEvent(e)

    def mouseMoveEvent(self, e):
        zone = self._zone(e.position().x())
        if zone != self._hover:
            self._hover = zone
            self.update()

    def leaveEvent(self, e):
        self._hover = 0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), theme.CELL)
        for d in (-1, 1):
            box = QRectF(0 if d < 0 else w - self.ARROW, 0, self.ARROW, h)
            lit = self._hover == d and self.can_step(d)
            if lit:
                p.fillRect(box, theme.GRID)
            cx, cy, s = box.center().x(), box.center().y(), 3.5
            back, tip = cx - d * s / 2, cx + d * s / 2
            p.setPen(Qt.NoPen)
            p.setBrush(theme.TEXT if lit else theme.SPIN if self.can_step(d) else theme.SPIN_OFF)
            p.drawPolygon([QPointF(back, cy - s), QPointF(back, cy + s), QPointF(tip, cy)])
        if self.value is not None:
            color = (theme.DISABLED if not self.isEnabled() and not self.held else theme.WARN if self.warned
                     else theme.OFF if self.value == self.off else theme.faded(theme.TEXT) if self.faded else theme.TEXT)
            p.setPen(color)
            p.drawText(QRectF(self.ARROW, 0, w - 2 * self.ARROW, h), Qt.AlignCenter, self.text(self.value))
        if self.bad or self.hasFocus():
            p.setPen(QPen(theme.BAD, 2) if self.bad else QPen(theme.LABEL, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(1, 1, w - 2, h - 2) if self.bad else QRectF(0.5, 0.5, w - 1, h - 1))


class GroupedChoice(Stepper):
    """One of many values, in groups (the function of a key): value ▾. A click, or Space, Enter or F4, opens a menu:
    the values before the groups, then a submenu per group, over the field with the current value's entry where the
    field is. The current value is bold, and so is the group it is in. Its colours are those of a stepper.

    names: per value its name, None where it has none; groups: (title, (value, ...)) each, None for a line; top: the
    values before the groups; tips: per value what the menu tells about it."""

    def __init__(self, names, groups, top=(0,), tips=None):
        super().__init__(names)
        self.groups, self.top, self.tips = groups, top, tips or {}
        self.current_entry = None                        # in the menu last made: the current value's entry

    def text(self, value):
        name = self.names[value] if 0 <= value < len(self.names) else None
        return str(value) if name is None else name

    def neighbour(self, value, direction, fine):
        return None

    def widest(self):
        return [self.text(v) for v in range(len(self.names))]

    def sizeHint(self):
        return QSize(max(map(self.fontMetrics().horizontalAdvance, self.widest())) + self.ARROW + 16, self.HEIGHT)

    def _action(self, menu, v):
        a = menu.addAction(self.text(v))
        if v == self.value:
            bold = a.font()
            bold.setBold(True)
            a.setFont(bold)
        if v in self.tips:
            a.setToolTip(self.tips[v])
            menu.setToolTipsVisible(True)
        a.triggered.connect(lambda _=False, v=v: v != self.value and self.chosen.emit(v))
        return a

    def menu(self):
        m = QMenu(self)
        m.setMinimumWidth(self.width())
        self.current_entry = None
        for v in self.top:
            a = self._action(m, v)
            if v == self.value:
                self.current_entry = a
        m.addSeparator()
        for title, values in self.groups:
            sub = m.addMenu(title)
            for v in values:
                if v is None:
                    sub.addSeparator()
                else:
                    self._action(sub, v)
            if self.value in values:
                bold = sub.menuAction().font()
                bold.setBold(True)
                sub.menuAction().setFont(bold)
                self.current_entry = sub.menuAction()
        return m

    def show_menu(self):
        m = self.menu()
        m.exec(self.mapToGlobal(QPoint(0, 0)), self.current_entry)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled() and self.value is not None:
            self.setFocus()
            self.show_menu()

    def wheelEvent(self, e):
        e.ignore()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_F4):
            if self.isEnabled() and self.value is not None:
                self.show_menu()
        else:
            QWidget.keyPressEvent(self, e)

    def mouseMoveEvent(self, e):
        pass

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), theme.CELL)
        cx, cy, s = w - self.ARROW / 2, h / 2, 3.5
        p.setPen(Qt.NoPen)
        p.setBrush(theme.SPIN if self.isEnabled() else theme.SPIN_OFF)
        p.drawPolygon([QPointF(cx - s, cy - s / 2), QPointF(cx + s, cy - s / 2), QPointF(cx, cy + s / 2)])
        if self.value is not None:
            color = (theme.DISABLED if not self.isEnabled() else theme.faded(theme.TEXT) if self.faded
                     else theme.TEXT)
            p.setPen(color)
            p.drawText(QRectF(self.ARROW / 2, 0, w - 1.5 * self.ARROW, h), Qt.AlignCenter, self.text(self.value))
        if self.bad or self.hasFocus():
            p.setPen(QPen(theme.BAD, 2) if self.bad else QPen(theme.LABEL, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(1, 1, w - 2, h - 2) if self.bad else QRectF(0.5, 0.5, w - 1, h - 1))


def pulse(beat):
    """The brightness (0.45 .. 1) of a pulsing dot at this beat; one pulse takes 20 beats."""
    return 0.45 + 0.55 * abs(beat % 20 - 10) / 10


def dropped_file(mime):
    """The one local file being dragged, or None: one file at a time, as with Load."""
    urls = mime.urls() if mime.hasUrls() else []
    if len(urls) == 1 and urls[0].isLocalFile() and os.path.isfile(urls[0].toLocalFile()):
        return urls[0].toLocalFile()
    return None


FRAME = QSize(16, 39)                            # what Windows adds around a window: its borders and title bar


def placement(size, room):
    """Where a window of this size opens in room, the part of a screen without the taskbar: in the middle, its frame
    included; None when it does not fit, and it opens maximized: on a small screen none of it is out of sight."""
    outer = size + FRAME
    if outer.width() > room.width() or outer.height() > room.height():
        return None
    return QPoint(room.x() + (room.width() - outer.width()) // 2, room.y() + (room.height() - outer.height()) // 2)


def show_on_screen(window, size, screen):
    """Show a window at size in the middle of the screen, or maximized when it does not fit (placement)."""
    at = placement(size, screen.availableGeometry())
    if at is None:
        window.showMaximized()
        return
    window.resize(size)
    window.move(at)
    window.show()


def head(*widgets):
    """A row of widgets, left aligned; an int is a spacing."""
    row = QWidget()
    row.setFixedHeight(26)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        else:
            lay.addWidget(w)
    lay.addStretch()
    return row
