"""The level of the output shown, in the window's top bar: always in view and within reach, also while a preset is
being edited. Volume with Lock Volume, Mute and Dim; what of the sound is on: the EQ, Bass/Treble and Loudness; and
Balance. Each acts on the output itself. On one line where the bar is wide enough, else Volume above the rest;
narrower still, Volume, the switches and Balance each on a line of its own.

    Volume      ‹ slider › value unit, the value larger. The knob is the Volume the device has, filled from the
                bottom. A click or a drag on the slider lower writes at once; higher, Volume rises to it step by
                step, as fast as the remote control, while the button is held, a ring marking where it is going. A
                drag with the right button follows the mouse up as well as down, from its first move. The arrows step 0.5 dB; held, they
                repeat as the remote control. The wheel over it steps 0.5 dB a notch.
    Balance     ‹ value ›, as in the output panel: L 100 .. C .. R 100; the arrows and the wheel step 5, with
                Ctrl 1, a held arrow again and again; the value opens a slider.
    Lock | Mute | Dim, EQ | B/T | LD (Bass/Treble, Loudness)
                segments, each on or off. EQ shows the switch of each channel, L and R in their colour when on;
                with Dual EQ off one, L=R. A click switches the EQ off while either channel has it on, and on for
                both when neither has.

Volume and Balance take the focus, for the keys, with Tab only: the mouse has the slider, the arrows and the wheel.
"""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QVBoxLayout, QWidget

from ..device import params as P
from . import theme
from .graph import side_color
from .legend import segment_path
from .output import TIPS, RangeStepper, shared_tip
from .tables import band_address
from .widgets import DSD_BYPASS, switch_tip

NOTCH = 120                                      # angleDelta of one wheel notch
ARROW_KEYS = (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up)
GROUP_GAP = 24                                   # px between the parts of the section
NAME_GAP = 8                                     # ... between a name and its control
ROW_GAP = 6                                      # ... between its rows, when it has two
SEGMENT_H, SEGMENT_PAD, RUN_GAP = 24, 10, 4      # px: a segment's height, the room beside its name, between its runs
VALUE_PT = 14                                    # pt: Volume's value, larger than the rest
UNIT_GAP = 4                                     # px between the value and its unit
LINES_MARGIN = {1: 15, 2: 8, 3: 8}               # px above and below its lines: on one, as two lines without margin
LEVEL = {P.LOCK_VOLUME: ("Lock", "Lock Volume", "On: disables the device's VOLUME knob for this output;\n"
                                                "Volume in the device's menu sets a fixed level."),
         P.MUTE: ("Mute", "Mute", "On: mutes this output."),
         P.DIM: ("Dim", "Dim", "On: turns this output down by 20 dB; off turns it back up.\n"
                               "Volume shows the lowered level.")}       # the segment's name, the setting's, its tip
DIM_ACTIVE_ONLY = "Dim works on the active output only."
LOWERED = {(P.MUTE,): "Mute is on.",                                       # Volume, its value in amber
           (P.DIM,): "Dim is on.",
           (P.MUTE, P.DIM): "Mute and Dim are on."}
OUT_OF_DIM = "A step turns Dim off and goes on from this level."


class Notches:
    """Wheel notches from wheel events; a touchpad's small steps add up to a notch first."""

    def __init__(self):
        self.rest = 0

    def __call__(self, e):
        self.rest += e.angleDelta().y()
        out = []
        while abs(self.rest) >= NOTCH:
            d = 1 if self.rest > 0 else -1
            self.rest -= d * NOTCH
            out.append(d)
        return out


class VolumeControl(RangeStepper):
    """Volume, as the device has it, by 0.5 dB: ‹ slider › value unit, on a stepper's ground. With Dim on, a step goes
    from the Volume reported, as any other, and turns Dim off: Dim on does not say whether the device moved Volume
    down (it does only on the active output), so going back up by the 20 dB of Dim is left to Dim itself.

    Up is held to the pace of the device's remote control, so that Volume never jumps up by itself; down is not:
    - An arrow, a key or a wheel notch steps 0.5 dB. A held arrow or key repeats after a pause, as the remote
      control, up or down as fast as it: steps that grow lower down the device's own scale (params.volume_held, with
      the output's offset).
    - A click or a drag on the slider aims: lower, it is written at once; higher, Volume rises to it in the same
      steps at the same pace while the button is held, a ring marking the aim. Letting go, a step of the user's own,
      or the device moving Volume elsewhere stops it.
    - A drag with the right button is the exception: once the mouse moves, Volume follows it, up as well as down
      (jumped). The press itself writes nothing.
    Nothing goes below the bottom of the device's own scale (floor), where its display shows a dash. A step up never
    goes out before the previous one has: each write rises one held step at most. While held, rising or dragged, the
    session leaves reading back until it is over (Session.hold). The window's tick drives it (tick), on the session's
    clock.

    The slider is in two straight parts: above KNEE three quarters of it, a pixel a little less than a step of 0.5 dB;
    below, down to the floor, the last quarter. A tick at the knee and at 0."""

    jumped = Signal(int)                         # a drag with the right button: Volume itself
    REPEAT_DELAY = 0.5                           # s from the press to the first repeat, as the remote control
    REPEAT_INTERVAL = 0.2                        # s between steps: 2.5 dB/s up, below the session's six writes a second
    HEIGHT = SEGMENT_H                           # in line with the segments beside it
    TRACK_PX, PAD, KNOB, TRACK, GAP = 200, 4, 12, 4, 8
    KNEE, KNEE_AT = -600, 0.25                   # -60 dB, a quarter up the slider

    def __init__(self, sent, holding, offset):
        super().__init__(P.VOLUME, [], anchor=None)
        self.off = None                          # no value of Volume means off
        self.sent = sent                         # () -> bool: no Volume write of the output shown is still queued
        self.holding = holding                   # (bool) -> None: Session.hold
        self.offset = offset                     # () -> int: params.volume_offset for the output shown
        self.unit = "dB"                         # dBr while Auto Ref Level is on: the section says
        self.floor = P.VOLUME_FLOOR
        self.notch = Notches()
        self.drag = None                         # "aim" or "free" while a button is held on the slider
        self._hold = None                        # the direction while an arrow or key is held
        self._rise = None                        # (Volume aimed at, the value last written) while rising
        self._due = 0.0                          # when the next step of either is due
        self._told = False                       # held, rising or dragged, as told to the session
        self._now = 0.0                          # the session's clock at the last tick
        self.big = QFont(self.font())
        self.big.setPointSizeF(VALUE_PT)
        self.value_w = max(QFontMetricsF(self.big).horizontalAdvance(t) for t in ("-114.5", "+6.0")) + 2
        self.unit_w = UNIT_GAP + self.fontMetrics().horizontalAdvance("dBr") + 2
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedSize(self.sizeHint())

    def set_floor(self, floor):
        """The bottom of the device's own scale, as this output reports it (params.volume_floor)."""
        self.floor = floor

    def neighbour(self, value, direction, fine):
        v = P.step(("out", P.VOLUME), value, direction)
        return v if v != value and (direction > 0 or v >= self.floor) else None

    # -- the slider -----------------------------------------------------------------------------------------------

    def sizeHint(self):
        return QSize(self._right() + self.ARROW + self.GAP + self.value_w + self.unit_w, self.HEIGHT)

    def _right(self):
        """Where the right arrow starts."""
        return self.ARROW + 2 * self.PAD + self.KNOB + self.TRACK_PX

    def _zone(self, x):
        return -1 if x < self.ARROW else 1 if self._right() <= x < self._right() + self.ARROW else 0

    def _on_track(self, x):
        return self.ARROW <= x < self._right()

    def _knee(self):
        """The knee, or None where the floor is above it: then one straight part."""
        return self.KNEE if self.floor < self.KNEE else None

    def fraction(self, v):
        """Where Volume v is along the slider, from 0 at the floor to 1 at the top."""
        lo, hi, k = self.floor, P.OUTPUT_RANGES[P.VOLUME][1], self._knee()
        if k is None:
            return (v - lo) / (hi - lo)
        if v < k:
            return (v - lo) / (k - lo) * self.KNEE_AT
        return self.KNEE_AT + (v - k) / (hi - k) * (1 - self.KNEE_AT)

    def value_of(self, f):
        """The Volume at fraction f along the slider, off the grid."""
        lo, hi, k = self.floor, P.OUTPUT_RANGES[P.VOLUME][1], self._knee()
        if k is None:
            return lo + f * (hi - lo)
        if f < self.KNEE_AT:
            return lo + f / self.KNEE_AT * (k - lo)
        return k + (f - self.KNEE_AT) / (1 - self.KNEE_AT) * (hi - k)

    def x_of(self, v):
        return self.ARROW + self.PAD + self.KNOB / 2 + self.fraction(v) * self.TRACK_PX

    def value_at(self, x):
        """The Volume on the half dBs nearest to x."""
        lo, hi = self.floor, P.OUTPUT_RANGES[P.VOLUME][1]
        v = self.value_of((x - self.ARROW - self.PAD - self.KNOB / 2) / self.TRACK_PX)
        return max(lo, min(hi, lo + round((v - lo) / P.VOLUME_STEP) * P.VOLUME_STEP))

    def ticks(self):
        return [0] if self._knee() is None else [self.KNEE, 0]

    # -- stepping, holding and rising -----------------------------------------------------------------------------

    def show_menu(self):
        pass                                     # the slider is in view

    def show_state(self, *args, **kwargs):
        """Held (Lock Volume): the value, its unit and the fill readable; the knob grey as the arrows, and no hand
        over it, as nothing can be moved."""
        super().show_state(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor if self.isEnabled() else Qt.ArrowCursor)

    def aim(self, value):
        """Lower: at once. Higher: rising to it, step by step, while the button is held on the slider."""
        if not self.isEnabled() or self.value is None:
            return
        rising = value > self.value and self.drag == "aim"
        if not rising or self._rise is None:                     # already rising, it keeps its pace
            self._due = self._now
        self._hold, self._rise = None, (value, self.value) if rising else None
        if value < self.value:
            self.chosen.emit(value)
        self._tell()

    def jump_to(self, value):
        if value != self.value:
            self.jumped.emit(value)                              # written, the value comes back by show_state
        self._tell()

    def stop(self):
        self._rise = None
        self._tell()

    def step(self, direction, fine=False):
        """A step of the user's own: it ends rising to a Volume aimed at."""
        self.stop()
        super().step(direction, fine)

    def _tell(self):
        on = self._hold is not None or self._rise is not None or self.drag == "free"
        if on != self._told:
            self._told = on
            self.holding(on)
        self.update()

    def _set_hold(self, direction):
        self._hold, self._due = direction, self._now + self.REPEAT_DELAY
        self._tell()

    def tick(self, now):
        self._now = now
        if self._hold is None and self._rise is None:
            return
        if not self.isEnabled() or self.value is None:
            self._hold = self._rise = None
        elif self._rise is not None and (self.drag != "aim"
                                         or self.value != self._rise[1] or self.value >= self._rise[0]):
            self._rise = None                                    # let go, moved elsewhere, or there
        elif now >= self._due and self.sent():
            self._due = now + self.REPEAT_INTERVAL
            if self._rise is not None:
                v = min(self._rise[0], P.volume_held(self.value, +1, self.offset()))
                self._rise = (self._rise[0], v)
            else:
                v = P.volume_held(self.value, self._hold, self.offset(), self.floor)
            if v is not None and v != self.value:
                self.chosen.emit(v)
        self._tell()

    # -- the mouse, the keys and the wheel ------------------------------------------------------------------------

    def mousePressEvent(self, e):
        x = e.position().x()
        if not self._on_track(x) or self._zone(x):
            super().mousePressEvent(e)                           # an arrow: a step, then held
            if e.button() == Qt.LeftButton and self._zone(x) and self.isEnabled():
                self._set_hold(self._zone(x))
            return
        if not self.isEnabled() or self.value is None:
            return
        if e.button() == Qt.LeftButton:
            self.drag = "aim"
            self.aim(self.value_at(x))
        elif e.button() == Qt.RightButton:
            self.drag = "free"                                   # it follows from the first move
            self._tell()

    def mouseMoveEvent(self, e):
        if self.drag == "aim":
            self.aim(self.value_at(e.position().x()))
        elif self.drag == "free":
            self.jump_to(self.value_at(e.position().x()))
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self.drag = None
        self._set_hold(None)

    def contextMenuEvent(self, e):
        e.accept()                               # the right button drags

    def keyPressEvent(self, e):
        k = e.key()
        if k in ARROW_KEYS:
            if not e.isAutoRepeat():                 # the system's own repeat gives way to the pace of tick
                super().keyPressEvent(e)
                self._set_hold(1 if k in (Qt.Key_Right, Qt.Key_Up) else -1)
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if not e.isAutoRepeat() and e.key() in ARROW_KEYS:      # letting go of Ctrl or Shift: still held
            self._set_hold(None)
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        self._set_hold(None)
        super().focusOutEvent(e)

    def wheelEvent(self, e):
        e.accept()
        for d in self.notch(e):
            self.step(d)

    # -- drawn ----------------------------------------------------------------------------------------------------

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h, cy = self.height(), self.height() / 2
        live = self.isEnabled() or self.held
        p.fillRect(QRectF(0, 0, self._right() + self.ARROW, h), theme.CELL)
        for d in (-1, 1):                                        # the arrows, as a Stepper's
            box = QRectF(0 if d < 0 else self._right(), 0, self.ARROW, h)
            lit = self._hover == d and self.can_step(d)
            if lit:
                p.fillRect(box, theme.GRID)
            cx, s = box.center().x(), 3.5
            back, tip = cx - d * s / 2, cx + d * s / 2
            p.setPen(Qt.NoPen)
            p.setBrush(theme.TEXT if lit else theme.SPIN if self.can_step(d) else theme.SPIN_OFF)
            p.drawPolygon([QPointF(back, cy - s), QPointF(back, cy + s), QPointF(tip, cy)])
        x0, x1 = self.x_of(self.floor), self.x_of(P.OUTPUT_RANGES[P.VOLUME][1])
        p.setBrush(theme.BORDER)
        p.drawRoundedRect(QRectF(x0, cy - self.TRACK / 2, x1 - x0, self.TRACK), self.TRACK / 2, self.TRACK / 2)
        if self.value is not None:
            p.setBrush(theme.SECONDARY if live else theme.DISABLED)
            p.drawRect(QRectF(x0, cy - self.TRACK / 2, self.x_of(self.value) - x0, self.TRACK))
        p.setPen(QPen(theme.SECONDARY if live else theme.DISABLED, 1))
        for t in self.ticks():
            p.drawLine(QPointF(self.x_of(t), cy - 6), QPointF(self.x_of(t), cy + 6))
        if self._rise is not None:                               # where it is rising to
            p.setPen(QPen(theme.TEXT, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(self.x_of(self._rise[0]), cy), self.KNOB / 2 - 1, self.KNOB / 2 - 1)
        if self.value is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(theme.TEXT if self.isEnabled() else theme.OFF if self.held else theme.DISABLED)
            p.drawEllipse(QPointF(self.x_of(self.value), cy), self.KNOB / 2, self.KNOB / 2)
            field = QRectF(self._right() + self.ARROW + self.GAP, 0, self.value_w, h)
            text, fm = self.text(self.value), QFontMetricsF(self.big)
            base = cy + fm.capHeight() / 2 - 1   # the capitals centred, a pixel up for the low minus and round figures
            p.setPen(theme.DISABLED if not live else theme.WARN if self.warned else theme.TEXT)
            p.setFont(self.big)                  # right-aligned: the point stays put
            p.drawText(QPointF(field.right() - fm.horizontalAdvance(text), base), text)
            p.setFont(self.font())               # the unit on the figures' baseline
            p.setPen(theme.SECONDARY if live else theme.DISABLED)
            p.drawText(QPointF(field.right() + UNIT_GAP, base), self.unit)
            if self.bad:
                p.setPen(QPen(theme.BAD, 2))
                p.setBrush(Qt.NoBrush)
                p.drawRect(field.adjusted(-4, 3, 2, -3))
        if self.hasFocus():
            p.setPen(QPen(theme.LABEL, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(0.5, 0.5, self._right() + self.ARROW - 1, h - 1))


class BalanceControl(RangeStepper):
    """Balance as in the output panel: ‹ value ›, the value opening a slider. A held arrow repeats its step, on the
    session's clock (tick). The wheel steps without the focus."""

    WIDTH, HEIGHT = 92, SEGMENT_H                # in line with the segments beside it
    REPEAT_DELAY, REPEAT_INTERVAL = 0.5, 0.1     # s from the press to the first repeat, and between repeats

    def __init__(self):
        super().__init__(P.BALANCE, [("L 100", -100), ("C", 0), ("R 100", 100)], anchor=0)
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedWidth(self.WIDTH)
        self.notch = Notches()
        self._hold, self._fine = None, False     # the arrow held, and with Ctrl
        self._due = self._now = 0.0

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        zone = self._zone(e.position().x())
        if e.button() == Qt.LeftButton and zone and self.isEnabled():
            self._hold, self._fine = zone, bool(e.modifiers() & Qt.ControlModifier)
            self._due = self._now + self.REPEAT_DELAY

    def tick(self, now):
        self._now = now
        if self._hold is None or now < self._due:
            return
        if not self.can_step(self._hold):
            self._hold = None
            return
        self._due = now + self.REPEAT_INTERVAL
        self.step(self._hold, self._fine)

    def mouseReleaseEvent(self, e):
        self._hold = None
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._hold = None
        super().leaveEvent(e)

    def wheelEvent(self, e):
        e.accept()
        for d in self.notch(e):
            self.step(d, bool(e.modifiers() & Qt.ControlModifier))


class Segment(QWidget):
    """One segment of a Segments: its name in runs of text, each in a colour of its own, centred. A click emits
    clicked. widest: the texts of each set of runs it can show; it is as wide as the widest, so that it keeps its
    width as its runs change."""

    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.runs, self.on, self.under = [("", theme.OFF)], False, False
        self.widest = []
        self.setFixedHeight(SEGMENT_H)

    def show_state(self, runs, on, enabled, tip):
        if runs != self.runs:
            self.runs = runs
            self.updateGeometry()
        self.on = on
        self.setEnabled(enabled)
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self.setToolTip(tip)
        self.update()
        if self.parentWidget():
            self.parentWidget().update()

    def _width(self, texts):
        fm = self.fontMetrics()
        return sum(fm.horizontalAdvance(t) for t in texts) + RUN_GAP * (len(texts) - 1)

    def sizeHint(self):
        w = max(self._width(texts) for texts in [[t for t, _ in self.runs]] + self.widest)
        return QSize(w + 2 * SEGMENT_PAD, SEGMENT_H)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QPainter(self)
        fm = self.fontMetrics()
        x = (self.width() - self._width([t for t, _ in self.runs])) / 2
        for text, color in self.runs:
            p.setPen(color if self.isEnabled() else theme.DISABLED)
            w = fm.horizontalAdvance(text)
            p.drawText(QRectF(x, 0, w + 1, self.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
            x += w + RUN_GAP

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled() and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def enterEvent(self, e):
        self.under = True
        self.parentWidget().update()

    def leaveEvent(self, e):
        self.under = False
        self.parentWidget().update()


class Segments(QWidget):
    """Segments side by side as one control, each on or off: on with a face and a lighter outline, off only
    outlined; under the mouse with a face."""

    def __init__(self, n):
        super().__init__()
        self.items = [Segment() for _ in range(n)]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        for s in self.items:
            lay.addWidget(s)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        last = len(self.items) - 1
        for chosen in (False, True):             # neighbours share their outline; an on one's is drawn last
            for i, s in enumerate(self.items):
                if s.on != chosen:
                    continue
                r = QRectF(s.geometry()).adjusted(0.5, 0.5, 0.5 if i < last else -0.5, -0.5)
                path = segment_path(r, 3, i == 0, i == last)
                if (s.on or s.under) and s.isEnabled():
                    p.fillPath(path, theme.RAISED if s.on else theme.PANEL)
                p.setPen(QPen(theme.SECONDARY if s.on and s.isEnabled() else theme.GRID, 1))
                p.drawPath(path)
        p.end()


def _name(text):
    label = QLabel(text)
    label.setStyleSheet("color: %s;" % theme.LABEL.name())
    return label


class VolumeSection(QWidget):
    rearranged = Signal(int)                     # over to another number of lines: the bar's height changed

    def __init__(self, session, marks):
        super().__init__()
        self.session, self.marks, self.out = session, marks, None
        self.volume = VolumeControl(lambda: (self.out[1], P.VOLUME) not in self.session.pending, self.session.hold,
                                    lambda: P.volume_offset(self.session.state, self.out[1], self.session.model))
        self.volume.chosen.connect(lambda v: self.write((self.out[1], P.VOLUME), v))
        self.volume.jumped.connect(self.jump)
        self.balance = BalanceControl()
        self.balance.chosen.connect(lambda v: self.write(self.key(P.BALANCE), v))
        self.level = Segments(3)
        for seg, i in zip(self.level.items, LEVEL):
            seg.clicked.connect(lambda i=i: self.toggle(self.key(i)))
        self.sound = Segments(3)
        eq, bt, loudness = self.sound.items
        eq.widest = [["EQ", "L", "R"], ["EQ", "L=R"]]           # Dual EQ on, off
        eq.clicked.connect(self.toggle_eq)
        bt.clicked.connect(lambda: self.toggle((self.out[2], P.BT_ENABLE)))
        loudness.clicked.connect(lambda: self.toggle((self.out[1], P.LOUDNESS_ENABLE)))
        self.volume_name, self.balance_name = _name("Volume"), _name("Balance")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSizeConstraint(QLayout.SetNoConstraint)   # its narrowest is that of three lines (minimumSizeHint)
        self.lines = QHBoxLayout(), QHBoxLayout(), QHBoxLayout()
        for line in self.lines:
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(0)
            lay.addLayout(line)
        self.n_lines, self._widths = None, None
        self.arrange(1)

    def _parts(self, n):
        """What goes on each line: widgets, room in px between them, and None for the room left."""
        volume = [self.volume_name, NAME_GAP, self.volume]
        rest = [self.level, GROUP_GAP, self.sound, GROUP_GAP, self.balance_name, NAME_GAP, self.balance, None]
        if n == 1:
            return [volume + [GROUP_GAP] + rest, [], []]
        if n == 2:
            return [volume + [None], rest, []]           # Volume alone above the switches and Balance
        return [volume + [None], [self.level, GROUP_GAP, self.sound, None],
                [self.balance_name, NAME_GAP, self.balance, None]]

    def _width(self, parts):
        return sum(p if isinstance(p, int) else max(p.sizeHint().width(), p.minimumWidth())
                   for p in parts if p is not None)

    def arrange(self, n):
        """On n lines: one, two or three."""
        if n == self.n_lines:
            return
        self.n_lines = n
        for line in self.lines:
            while line.count():
                line.takeAt(0)
        for line, parts in zip(self.lines, self._parts(n)):
            for p in parts:
                if p is None:
                    line.addStretch()
                elif isinstance(p, int):
                    line.addSpacing(p)
                else:
                    line.addWidget(p, 0, Qt.AlignVCenter)
        m = LINES_MARGIN[n]
        self.layout().setSpacing(ROW_GAP if n > 1 else 0)
        self.layout().setContentsMargins(0, m, 0, m)
        self.updateGeometry()
        self.rearranged.emit(n)

    def bar_height(self, n=None):
        """Its height on n lines, else as it is now."""
        n = n or self.n_lines
        return n * SEGMENT_H + (n - 1) * ROW_GAP + 2 * LINES_MARGIN[n]

    def lines_for(self, width):
        """On how many lines it goes at this width."""
        return next((n for n in (1, 2) if width >= max(map(self._width, self._parts(n)))), 3)

    def minimumSizeHint(self):
        """As narrow as three lines."""
        return QSize(max(self._width(line) for line in self._parts(3)), self.bar_height())

    def sizeHint(self):
        return QSize(self._width(self._parts(1)[0]), self.bar_height())

    def resizeEvent(self, e):
        self.arrange(self.lines_for(self.width()))
        super().resizeEvent(e)

    def set_output(self, output):
        self.out = output

    def key(self, i):
        return self.session.at((self.out[1], i))

    def write(self, key, value):
        if self.session.writable(key):
            self.session.set(key, value)

    def jump(self, value):
        """A drag with the right button: Volume where the mouse is, up as well as down."""
        key = (self.out[1], P.VOLUME)
        if self.session.writable(key):
            self.session.set(key, value, jump=True)

    def toggle(self, key):
        if self.session.writable(key):
            self.session.set(key, 1 - self.session.state[key])

    def eq_keys(self):
        """The EQ switch of each channel; with Dual EQ off one, on the left address."""
        keys = [(band_address(self.out, side, self.session), P.EQ_ENABLE) for side in (0, 1)]
        return keys if self.session.dual(self.out[1]) else keys[:1]

    def toggle_eq(self):
        """Off while either channel has the EQ on, else on for both."""
        keys = self.eq_keys()
        value = 0 if any(self.session.state.get(k) == 1 for k in keys) else 1
        for k in keys:
            if self.session.writable(k):
                self.session.set(k, value)

    def active(self, i):
        """Setting i is that of an output the device has active, as its status message says: of this one, or of one
        that shares it (Session.sharing)."""
        st, model = self.session.device_status, self.session.model
        active = () if model is None else model.active
        return (st is not None and st.output < len(active)
                and bool(set(self.session.sharing((self.out[1], i))) & set(active[st.output])))

    def tick(self, now):
        self.volume.tick(now)
        self.balance.tick(now)

    def refresh(self):
        if self.out is None or not P.has_bt(self.out[1]):
            return
        s, ready = self.session.state, self.session.ready()
        on = lambda i: ready and s.get(self.key(i)) == 1                      # noqa: E731
        self.refresh_volume(s, ready, on)
        key = self.key(P.BALANCE)
        tip = "\n".join(filter(None, (TIPS[P.BALANCE], shared_tip(self.session, key) if ready else None)))
        self.balance.show_state(s.get(key) if ready else None, self.session.writable(key), tip,
                                bad=key in self.marks.mismatch)
        for seg, (i, (name, setting, what)), lit in zip(self.level.items, LEVEL.items(),
                                                        (theme.TEXT, theme.WARN, theme.WARN)):
            enabled = self.session.writable(self.key(i))
            tip = "%s: %s\n%s" % (setting, "on" if on(i) else "off", what)
            if i == P.DIM and ready and not self.active(i):                # as on the device: the active output only
                enabled, tip = False, tip + "\n" + DIM_ACTIVE_ONLY
            tip = "\n".join(filter(None, (tip, shared_tip(self.session, self.key(i)) if ready else None)))
            seg.show_state([(name, lit if on(i) else theme.OFF)], on(i), enabled, tip)
        self.refresh_sound(s, ready)
        widths = self.sizeHint().width(), self.minimumSizeHint().width()
        if widths != self._widths:               # the names of the segments set its widths
            self._widths = widths
            self.updateGeometry()

    def refresh_volume(self, s, ready, on):
        """Its unit: dBr while Auto Ref Level is on, else dB. With Lock Volume on it is held; with Mute or Dim on its
        value is amber."""
        out = self.out[1]
        key = (out, P.VOLUME)
        self.volume.unit = "dBr" if on(P.AUTO_REF_LEVEL) else "dB"
        lowering = tuple(i for i in (P.MUTE, P.DIM) if on(i))
        if ready:
            self.volume.set_floor(P.volume_floor(s, out, self.session.model))
        lo, hi = self.volume.floor, P.OUTPUT_RANGES[P.VOLUME][1]
        tip = [LOWERED.get(lowering), OUT_OF_DIM if P.DIM in lowering and not on(P.LOCK_VOLUME) else None,
               "Lock Volume is on: set it in the device's menu." if on(P.LOCK_VOLUME) else
               "Adjust with the arrows, the slider or the mouse wheel.\n"
               "On the slider, up rises step by step while the button is held;\n"
               "with the right button it follows the mouse.",
               "%s … +%s, step 0.5 dB" % (self.volume.text(lo), self.volume.text(hi))]
        if key in self.marks.mismatch:
            tip.append("Sent %s, the device has %s." % tuple(self.volume.text(v) for v in self.marks.mismatch[key]))
        self.volume.show_state(s.get(key) if ready else None, self.session.writable(key),
                               "\n".join(filter(None, tip)), bad=key in self.marks.mismatch,
                               held=on(P.LOCK_VOLUME), warned=bool(lowering))

    def refresh_sound(self, s, ready):
        out, left = self.out[1], self.out[2]
        bypassed = ready and self.session.bypassed()
        color = lambda c, lit: (theme.faded(c) if bypassed else c) if lit else theme.OFF       # noqa: E731
        eq, bt, loudness = self.sound.items
        keys = self.eq_keys()
        eq_on = [ready and s.get(k) == 1 for k in keys]
        if len(keys) == 2:                                       # Dual EQ on
            runs = [("EQ", color(theme.LABEL, any(eq_on))), ("L", color(side_color(0, True), eq_on[0])),
                    ("R", color(side_color(1, True), eq_on[1]))]
            tip = "EQ: left %s, right %s" % tuple("on" if o else "off" for o in eq_on)
        else:
            runs = [("EQ", color(theme.LABEL, eq_on[0])), ("L=R", color(side_color(0, False), eq_on[0]))]
            tip = "EQ, one for both channels (Dual EQ off): %s" % ("on" if eq_on[0] else "off")
        tip += ("\nClick to switch it off." if any(eq_on) else "\nClick to switch it on for both channels.")
        enabled = ready and all(self.session.writable(k) for k in keys)
        eq.show_state(runs, any(eq_on), enabled, tip + ("\n" + DSD_BYPASS if bypassed else ""))
        bt_on = ready and s.get((left, P.BT_ENABLE)) == 1
        bt.show_state([("B/T", color(theme.BT, bt_on))], bt_on,
                      ready and self.session.writable((left, P.BT_ENABLE)),
                      switch_tip("Bass/Treble, both channels", bt_on))
        ld_on = ready and s.get((out, P.LOUDNESS_ENABLE)) == 1
        loudness.show_state([("LD", color(theme.LOUDNESS, ld_on))], ld_on,
                            ready and self.session.writable((out, P.LOUDNESS_ENABLE)),
                            switch_tip("Loudness, both channels", ld_on))
