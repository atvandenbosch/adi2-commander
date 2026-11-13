"""The settings of one output besides its EQ, Bass/Treble and Loudness, in three groups: Level, Processing and DAC.

A setting the output does not have (IEM: Ref Level and Auto Ref Level; Rear TRS Source, which only Phones 3/4 of the
ADI-2/4 Pro has) is left out. The input is in the Input panel.

    one of a few values     a stepper (‹ value ›)
    Width, Balance          a stepper too: Swapped .. -0.50 .. Mono .. 0.50 .. Stereo, L 100 .. C .. R 100;
                            the value opens a slider instead of a list
    Volume                  a stepper too, by 0.5 dB up; the value opens a slider to aim at, rising step by step
    on or off               an option: Lock Volume, Auto Ref Level, Mute, Dim
"""

import math

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolTip, QVBoxLayout, QWidget

from ..device import params as P
from . import theme
from .widgets import ATTACHED_GAP, GROUP_STYLE, INNER_GAP, TITLE_STYLE, Action, Option, Stepper, head

LABEL_WIDTH, VALUE_WIDTH, ROW_HEIGHT = 112, 124, 30
NAME_INDENT = 6                                  # px: where the row names of the tables start, in Segoe UI
OPTIONS = {P.LOCK_VOLUME: "Lock Volume", P.AUTO_REF_LEVEL: "Auto Ref Level", P.MUTE: "Mute", P.DIM: "Dim"}
OPTION_TIPS = {P.LOCK_VOLUME: "On: disables the device's VOLUME knob for this output;\n"
                              "Volume in the device's menu sets a fixed level.",
               P.AUTO_REF_LEVEL: "On: the device chooses Ref Level from Volume and the positive EQ gain.",
               P.MUTE: "On: this output is silent.",
               P.DIM: "On: turns this output down by 20 dB; off brings them back.\n"
                      "Volume shows the lowered level."}
DIM_ACTIVE_ONLY = "Dim works on the active output only."
LOWERED = {(P.MUTE,): "Mute is on: this output is silent.",                # Volume, its value in amber
           (P.DIM,): "Dim is on.",
           (P.MUTE, P.DIM): "Mute and Dim are on: this output is silent."}
OUT_OF_DIM = "A step turns Dim off and goes on from this level."
TIPS = {P.REF_LEVEL: "The output level at full scale",
        P.MONO: "On: both channels summed\nto Left: the sum on the left output only",
        P.MS_PROC: "Mid/side: mono content to the left channel, stereo content to the right",
        P.POLARITY: "Inverts the polarity of both channels, or of one",
        P.CROSSFEED: "Bauer binaural crossfeed: less stereo width in the treble, as from speakers;\n"
                     "1 just a touch, 5 the strongest",
        P.DA_FILTER: "The reconstruction filter of the DAC",
        P.DE_EMPHASIS: "The de-emphasis filter of the DAC",
        P.DC_PROTECTION: "Digital DC protection",
        P.REAR_TRS_SOURCE: "What the rear TRS outputs carry: Line Out 1/2,\n"
                           "or Phones 3/4 with all its settings, Ref Level included",
        P.LOOPBACK: "This output's signal back to the computer over USB:\n"
                    "before the processing (FX), after it, or after it 6 dB lower",
        P.BALANCE: "L 100 left only, C centre, R 100 right only\nSteps of 5; with Ctrl of 1\n"
                   "Click the value for a slider by 1.",
        P.WIDTH: "Stereo 1.00, Mono 0.00, Swapped -1.00: left and right exchanged\n"
                 "Steps of 0.05; with Ctrl of 0.01\nClick the value for a slider by 0.01."}
NOT_KNOWN = "Not known for this device"           # DA Filter: the device's filters (params.da_filters)
PLUG_WARNING = ("Plugging in headphones will bring up a warning on the device:\n"
                "it will hold the output low until Volume is -15 dB or lower, or the warning is confirmed there.")
PLUG_WARNING_ABOVE = -150                       # Phones on Hi-Power: the warning comes above -15 dB, not at -15.0
PLUGS = {6: "phones", 9: "iem"}                # per Phones address its plug in the status message (status.Status)
PROCESSING = (P.MONO, P.WIDTH, P.MS_PROC, P.POLARITY, P.CROSSFEED)      # the DSP: bypassed while DSD plays
EQ_OR_CROSSFEED_FROM = 705600                    # from this rate the device runs the EQ or Crossfeed, the EQ first
PHONES_REF = "phones_ref"                         # the row of the Ref Level of Phones 1/2 beside Line Out's
SHARED_REF_TIP = "Set by the Ref Level of Line Out: 3 dB higher, %s at most"
VOLUME_UNIT = 6                                  # 0.1 dB per pixel of Volume's slider: ~200 px, as Balance's


class RangeSlider(QWidget):
    """A value along a track from end to end (Width, Balance, Volume), filled in grey from the anchor (Width,
    Balance: the value that leaves the sound as it is) to the knob, with a tick at each point named between the ends.
    A drag, or a click on the track, puts the knob there. Which end is which, the buttons under it say.

    unit: values per pixel; grid: the values it takes; lo: where it starts, if not at the bottom of the range. Width
    and Balance: one pixel per hundredth."""

    moved = Signal(int)
    KNOB, TRACK = 12, 4                          # px

    def __init__(self, index, anchor, ticks, unit=1, grid=1, lo=None):
        super().__init__()
        self.lo, self.hi = P.OUTPUT_RANGES[index]
        self.lo = self.lo if lo is None else lo
        self.anchor, self.ticks, self.unit, self.grid = anchor, ticks, unit, grid
        self.value, self._dragging = anchor, False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.KNOB + math.ceil((self.hi - self.lo) / unit) + 1, Stepper.HEIGHT)

    def x_of(self, value):
        """The middle of the value's column of pixels."""
        return self.KNOB // 2 + (value - self.lo) / self.unit + 0.5

    def value_at(self, x):
        """The value on the grid nearest to the column of pixels that holds x."""
        v = self.lo + (math.floor(x) - self.KNOB // 2) * self.unit
        return max(self.lo, min(self.hi, self.lo + round((v - self.lo) / self.grid) * self.grid))

    def set_value(self, value):
        if not self._dragging and value != self.value:
            self.value = value
            self.update()

    def _move(self, e):
        v = self.value_at(e.position().x())
        if v != self.value:
            self.value = v
            self.update()
            self.moved.emit(v)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self._dragging = True
            self._move(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._move(e)

    def mouseReleaseEvent(self, e):
        self._dragging = False

    def _track(self, p, fill_from, fill_to):
        """The track, its fill between two values, and the ticks."""
        on, cy = self.isEnabled(), self.height() / 2
        x0, x1, xa, xb = self.x_of(self.lo), self.x_of(self.hi), self.x_of(fill_from), self.x_of(fill_to)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.GRID)
        p.drawRoundedRect(QRectF(x0, cy - self.TRACK / 2, x1 - x0, self.TRACK), self.TRACK / 2, self.TRACK / 2)
        p.setBrush(theme.SECONDARY if on else theme.DISABLED)
        p.drawRect(QRectF(min(xa, xb), cy - self.TRACK / 2, abs(xb - xa), self.TRACK))
        p.setPen(QPen(theme.SECONDARY if on else theme.DISABLED, 1))
        for t in self.ticks:
            p.drawLine(QPointF(self.x_of(t), cy - 6), QPointF(self.x_of(t), cy + 6))

    def _knob(self, p, value):
        p.setPen(Qt.NoPen)
        p.setBrush(theme.TEXT if self.isEnabled() else theme.DISABLED)
        p.drawEllipse(QPointF(self.x_of(value), self.height() / 2), self.KNOB / 2, self.KNOB / 2)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._track(p, self.anchor, self.value)
        self._knob(p, self.value)


class VolumeSlider(RangeSlider):
    """Volume's slider, from the bottom of the device's own scale (floor) to the top: the knob is the Volume the device
    has, filled from the bottom; while Volume rises step by step to a value aimed at, a ring marks that value. A drag
    moves the ring."""

    def __init__(self, floor):
        super().__init__(P.VOLUME, floor, [0], unit=VOLUME_UNIT, grid=P.VOLUME_STEP, lo=floor)
        self.actual = floor

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._track(p, self.lo, self.actual)
        if self.value != self.actual:
            p.setPen(QPen(theme.TEXT if self.isEnabled() else theme.DISABLED, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(self.x_of(self.value), self.height() / 2), self.KNOB / 2 - 1, self.KNOB / 2 - 1)
        self._knob(p, self.actual)


class RangePopup(QFrame):
    """Under a RangeStepper: the slider, and a button for each named point to go there at once. Every change goes to
    the stepper (aim), which shows it. The arrow keys and the wheel move by the slider's grid, PgUp and PgDn as the
    stepper's arrows. Enter or a click elsewhere closes it as it is; Esc as the stepper says (give_up)."""

    NOTCH = 120                                  # angleDelta of one wheel notch
    closed = Signal()                            # however it closes

    def __init__(self, stepper):
        super().__init__(stepper, Qt.Popup | Qt.FramelessWindowHint)
        self.stepper, self.opened, self._wheel = stepper, stepper.value, 0
        self.setAttribute(Qt.WA_NoMouseReplay)   # a click elsewhere only closes it
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet("RangePopup { background: %s; border: 1px solid %s; }"
                           % (theme.PANEL.name(), theme.BORDER.name()))
        self.slider = stepper.slider()
        stepper.show_on(self.slider)
        self.slider.moved.connect(self.choose)
        self.buttons = buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        actions = []
        for n, (text, value) in enumerate(stepper.points):
            if n:
                buttons.addStretch()
            b = Action(compact=True)
            b.setText(text)
            b.setToolTip(stepper.point_tip(text))
            b.setFocusPolicy(Qt.NoFocus)         # the keys stay with the slider
            b.clicked.connect(lambda _=False, value=value: self.choose(value))
            buttons.addWidget(b)
            actions.append(b)
        ends = max(actions[0].sizeHint().width(), actions[-1].sizeHint().width())
        for b in (actions[0], actions[-1]):
            b.setFixedWidth(ends)                # the ends as wide: the middle one under its tick
        lay = QVBoxLayout(self)
        lay.setContentsMargins(ATTACHED_GAP, ATTACHED_GAP // 2, ATTACHED_GAP, ATTACHED_GAP)
        lay.setSpacing(ATTACHED_GAP // 2)
        lay.addWidget(self.slider, 0, Qt.AlignHCenter)  # its middle above the middle button, however wide they are
        lay.addLayout(buttons)

    def choose(self, value):
        self.slider.set_value(value)
        self.stepper.aim(value)

    def follow(self):
        """The stepper's state: its value unless the knob is being dragged, and whether it can be changed."""
        if self.stepper.value is None:
            self.close()
            return
        self.stepper.show_on(self.slider)
        self.setEnabled(self.stepper.isEnabled())

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)

    def _by_grid(self, direction):
        s = self.slider
        self.choose(max(s.lo, min(s.hi, s.value + direction * s.grid)))

    def keyPressEvent(self, e):
        k, v = e.key(), self.slider.value
        if k in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up):
            self._by_grid(1 if k in (Qt.Key_Right, Qt.Key_Up) else -1)
        elif k in (Qt.Key_PageUp, Qt.Key_PageDown):
            n = self.stepper.neighbour(v, 1 if k == Qt.Key_PageUp else -1, False)
            if n is not None:
                self.choose(n)
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.close()
        elif k == Qt.Key_Escape:
            self.stepper.give_up(self.opened)
            self.close()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        e.accept()
        self._wheel += e.angleDelta().y()
        while abs(self._wheel) >= self.NOTCH:
            direction = 1 if self._wheel > 0 else -1
            self._wheel -= direction * self.NOTCH
            self._by_grid(direction)


class RangeStepper(Stepper):
    """Width or Balance, in hundredths, as the device shows them. The arrows step to the next multiple of 5, with
    Ctrl by 1; the value opens a slider by 1 (RangePopup) instead of a list.

    points: the named points, left to right, as (name, value): the buttons under the slider. anchor: the value that
    leaves the sound as it is (Stereo, C): grey, as off, and where the slider's fill starts."""

    STEP = 5

    def __init__(self, index, points, anchor):
        super().__init__([], off=anchor)
        self.index, self.points, self.anchor = index, points, anchor
        self.popup = None

    def text(self, value):
        return P.to_text(("out", self.index), value)

    def neighbour(self, value, direction, fine):
        lo, hi = P.OUTPUT_RANGES[self.index]
        if fine:
            v = value + direction
        elif direction > 0:
            v = (value // self.STEP + 1) * self.STEP
        else:
            v = (value - 1) // self.STEP * self.STEP
        return v if lo <= v <= hi else None

    def widest(self):
        return [self.text(v) for _, v in self.points]

    def slider(self):
        return RangeSlider(self.index, self.anchor, [v for _, v in self.points[1:-1]])

    def show_on(self, slider):
        """Its state on the popup's slider."""
        slider.set_value(self.value)

    def point_tip(self, name):
        return ""

    def aim(self, value):
        """A value chosen on the slider: written at once."""
        if value != self.value and self.isEnabled():
            self.chosen.emit(value)

    def give_up(self, opened):
        """Esc on the slider: back to the value it opened with."""
        self.aim(opened)

    def dress(self, popup):
        """Anything of its own on the popup, before it is shown."""

    def show_menu(self):
        popup = RangePopup(self)
        self.dress(popup)
        self.popup = popup
        self.popup.destroyed.connect(lambda: setattr(self, "popup", None))
        self.popup.ensurePolished()                  # its border from the style sheet counts in its size
        self.popup.adjustSize()
        corner = self.mapToGlobal(QPoint(self.width(), self.height()))        # its right edge under the stepper's
        self.popup.move(corner.x() - self.popup.width(), corner.y())
        self.popup.show()
        self.popup.slider.setFocus()

    def show_state(self, *args, **kwargs):
        super().show_state(*args, **kwargs)
        if self.popup is not None:
            self.popup.follow()


class VolumeStepper(RangeStepper):
    """Volume, as the device has it, by 0.5 dB: one step per click on an arrow, per key press and per wheel notch,
    with or without Ctrl; a touchpad's small wheel steps add up to a notch first. With Dim on, a step goes from the
    Volume reported, as any other, and turns Dim off: Dim on does not say whether the device moved Volume down (it
    does only on the active output), so going back up by the 20 dB of Dim is left to Dim itself.

    Up is held to the pace of the device's remote control, so that Volume never jumps up; down is not:
    - A held arrow or key repeats after a pause, as the remote control, up or down as fast as it: steps that grow
      lower down the device's own scale (params.volume_held, with the output's offset).
    - The value opens a slider (RangePopup) to aim at a Volume: lower, it is written at once; higher, Volume rises to
      it in the same steps at the same pace, and only while the slider is open: closing it in any way (Enter, Esc, a
      click elsewhere), a step of the user's own, or the device moving Volume elsewhere stops it. Min and 0.0 under
      the slider.
    Neither goes below the bottom of the device's own scale (floor), where its display shows a dash. A step up never
    goes out before the previous one has: each write rises one held step at most. While held or rising, the session
    leaves reading back until it is over (Session.hold). The window's tick drives it (tick), on the session's clock."""

    NOTCH = 120                                  # angleDelta of one wheel notch
    REPEAT_DELAY = 0.5                           # s from the press to the first repeat, as the remote control
    REPEAT_INTERVAL = 0.2                        # s between steps: 2.5 dB/s up, below the session's six writes a second

    def __init__(self, sent, holding, offset):
        super().__init__(P.VOLUME, [], anchor=None)
        self.off = None                          # no value of Volume means off
        self.sent = sent                         # () -> bool: no Volume write of the output shown is still queued
        self.holding = holding                   # (bool) -> None: Session.hold
        self.offset = offset                     # () -> int: params.volume_offset for the output shown
        self.unit = "dB"                         # dBr while Auto Ref Level is on: the panel says
        self.set_floor(P.VOLUME_FLOOR)
        self._wheel = 0
        self._hold = None                        # the direction while held
        self._rise = None                        # (Volume aimed at, the value last written) while rising
        self._due = 0.0                          # when the next step of either is due
        self._told = False                       # held or rising, as told to the session
        self._now = 0.0                          # the session's clock at the last tick

    def set_floor(self, floor):
        """The bottom of the device's own scale, as this output reports it (params.volume_floor): Min."""
        self.floor, self.anchor = floor, floor
        self.points = [("Min", floor), ("0.0", 0)]

    def neighbour(self, value, direction, fine):
        v = P.step(("out", P.VOLUME), value, direction)
        return v if v != value and (direction > 0 or v >= self.floor) else None

    def slider(self):
        return VolumeSlider(self.floor)

    def show_on(self, slider):
        slider.actual = self.value
        slider.set_value(self.value if self._rise is None else self._rise[0])
        slider.update()

    def point_tip(self, name):
        if name == "Min":
            return "The lowest Volume on the device's scale (%s)" % self.text(self.points[0][1])
        return "0 %s: no attenuation" % self.unit

    def dress(self, popup):
        popup.closed.connect(self.stop)              # it rises only in view
        popup.stop = stop = Action(compact=True)     # between Min and 0.0, while rising
        stop.setText("Stop")
        stop.setToolTip("Stop rising: Volume stays where it has got to.")
        stop.setFocusPolicy(Qt.NoFocus)
        stop.clicked.connect(self.stop)
        stop.setVisible(self._rise is not None)
        popup.buttons.insertStretch(1)
        popup.buttons.insertWidget(2, stop)

    def aim(self, value):
        """Lower: at once. Higher: rising to it, step by step, while the slider is open."""
        if not self.isEnabled() or self.value is None:
            return
        self._hold, self._due = None, self._now
        self._rise = (value, self.value) if value > self.value and self.popup is not None else None
        if value < self.value:
            self.chosen.emit(value)
        self._tell()

    def give_up(self, opened):
        """Esc on the slider: Volume stays where it has got to, as on closing it."""
        self.stop()

    def stop(self):
        self._rise = None
        self._tell()

    def step(self, direction, fine=False):
        """A step of the user's own: it ends rising to a Volume aimed at."""
        self.stop()
        super().step(direction, fine)

    def _tell(self):
        if self.popup is not None:                   # the slider and its Stop as they now are
            self.popup.stop.setVisible(self._rise is not None)
            self.show_on(self.popup.slider)
        on = self._hold is not None or self._rise is not None
        if on != self._told:
            self._told = on
            self.holding(on)

    def _set_hold(self, direction):
        self._hold, self._due = direction, self._now + self.REPEAT_DELAY
        self._tell()

    def tick(self, now):
        self._now = now
        if self._hold is None and self._rise is None:
            return
        if not self.isEnabled() or self.value is None:
            self._hold = self._rise = None
        elif self._rise is not None and (self.popup is None or not self.popup.isVisible()
                                         or self.value != self._rise[1] or self.value >= self._rise[0]):
            self._rise = None                                    # out of view, moved elsewhere, or there
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

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        zone = self._zone(e.position().x())
        if e.button() == Qt.LeftButton and zone and self.isEnabled():
            self._set_hold(zone)

    def mouseReleaseEvent(self, e):
        self._set_hold(None)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up):
            if not e.isAutoRepeat():                 # the system's own repeat gives way to the pace of tick
                super().keyPressEvent(e)
                self._set_hold(1 if k in (Qt.Key_Right, Qt.Key_Up) else -1)
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if not e.isAutoRepeat():
            self._set_hold(None)
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        self._wheel = 0
        self._set_hold(None)
        super().focusOutEvent(e)

    def wheelEvent(self, e):
        if not self.hasFocus():
            self._wheel = 0
            e.ignore()                               # leave the value alone, let the panel scroll
            return
        e.accept()
        self._wheel += e.angleDelta().y()
        while abs(self._wheel) >= self.NOTCH:
            direction = 1 if self._wheel > 0 else -1
            self._wheel -= direction * self.NOTCH
            self.step(direction)


def shared_tip(session, key):
    """Where the setting at key is that of more than one output, each with settings of its own now: which."""
    outs = session.sharing(key)
    if len(outs) < 2 or not all(session.controls(o) for o in outs):
        return None
    return "One setting for %s" % " and ".join(session.model.outputs[P.OUTPUT_ADDRESSES.index(o)] for o in outs)


def _label(text):
    label = QLabel(text)
    label.setFixedWidth(LABEL_WIDTH)
    label.setStyleSheet("color: %s; padding-left: %dpx;" % (theme.LABEL.name(), NAME_INDENT))
    return label


class Row(QWidget):
    """A setting's row: its name, then what sets it, the last widget. Its tooltip is the row's own, else on the name
    that of what sets it."""

    def __init__(self, control):
        super().__init__()
        self.control = control

    def event(self, e):
        if e.type() == QEvent.ToolTip and not self.toolTip():
            child = self.childAt(e.pos())
            name = child is not None and child is not self.control and not self.control.isAncestorOf(child)
            if name and self.control.toolTip():
                QToolTip.showText(e.globalPos(), self.control.toolTip(), self)
                e.accept()
            else:
                QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)


def _row(*widgets, indent=0):
    row = Row(widgets[-1])
    row.setFixedHeight(ROW_HEIGHT)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(indent, 0, 0, 0)
    lay.setSpacing(0)
    for w in widgets:
        lay.addWidget(w)
    lay.addStretch()
    return row


class OutputPanel(QWidget):
    edited = Signal(object, int, bool)               # key, value, rounded or clamped: as a table's

    def __init__(self, session, marks):
        super().__init__()
        self.session, self.marks = session, marks
        self.out = None
        self.steppers, self.options, self.rows = {}, {}, {}
        self.volume = VolumeStepper(lambda: (self.out[1], P.VOLUME) not in self.session.pending, self.session.hold,
                                    lambda: P.volume_offset(self.session.state, self.out[1], self.session.model))
        self.volume.setFixedWidth(VALUE_WIDTH)
        self.volume.chosen.connect(lambda value: self.edited.emit((self.out[1], P.VOLUME), value, False))
        self.volume_label = _label("Volume (dB)")
        title = QLabel("OUTPUT")
        title.setStyleSheet(TITLE_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(head(title))
        self.phones_ref = Stepper(P.REF_LEVELS[P.OUTPUTS[1][1]])                # its names follow the model
        self.phones_ref.setFixedWidth(VALUE_WIDTH)
        self.phones_ref.chosen.connect(lambda value: self.edited.emit(self.session.kept_ref_level(), value, False))
        self.labels = {}
        groups = [("LEVEL", [(P.LOCK_VOLUME, None), (P.VOLUME, "Volume"), (P.AUTO_REF_LEVEL, None),
                             (P.REF_LEVEL, "Ref Level"), (PHONES_REF, "Ref Level Ph 1/2"), (P.MUTE, None),
                             (P.DIM, None), (P.BALANCE, "Balance")]),
                  ("PROCESSING", [(P.MONO, "Mono"), (P.WIDTH, "Width"), (P.MS_PROC, "M/S-Proc"),
                                  (P.POLARITY, "Polarity"), (P.CROSSFEED, "Crossfeed")]),
                  ("DAC", [(P.DA_FILTER, "DA Filter"), (P.DE_EMPHASIS, "De-Emphasis"),
                           (P.DC_PROTECTION, "DC Protection"), (P.LOOPBACK, "Loopback to USB"),
                           (P.REAR_TRS_SOURCE, "Rear TRS Source")])]
        for name, items in groups:
            lay.addSpacing(INNER_GAP)
            group = QLabel(name)
            group.setStyleSheet(GROUP_STYLE)
            lay.addWidget(head(group))
            lay.addSpacing(ATTACHED_GAP)
            for i, text in items:
                self.rows[i] = self._control(i, text)
                lay.addWidget(self.rows[i])
        lay.addStretch()

    def _control(self, i, text):
        """The row of one setting: its name, then what sets it; an option carries its own name."""
        if i in OPTIONS:
            option = Option(OPTIONS[i])
            option.clicked.connect(lambda i=i: self.toggle(i))
            self.options[i] = option
            return _row(option, indent=NAME_INDENT - Option.RING - 1)        # the track where the names start
        if i == P.VOLUME:
            return _row(self.volume_label, self.volume)
        self.labels[i] = _label(text)
        if i == PHONES_REF:
            return _row(self.labels[i], self.phones_ref)
        names = P.CHOICES.get(i)
        if i == P.WIDTH:
            s = RangeStepper(i, [(n, v) for v, n in P.WIDTH_NAMES.items()], anchor=100)   # full stereo
        elif i == P.BALANCE:
            s = RangeStepper(i, [("L 100", -100), ("C", 0), ("R 100", 100)], anchor=0)
        elif i == P.REF_LEVEL:
            s = Stepper(P.REF_LEVELS[P.OUTPUTS[0][1]])                       # its names follow the output
        elif i == P.DA_FILTER:
            s = Stepper(P.DA_FILTERS[0])                                     # its names follow the device
        else:
            s = Stepper(names, off=names.index("Off") if "Off" in names else None)
        s.setFixedWidth(VALUE_WIDTH)
        s.chosen.connect(lambda value, i=i: self.edited.emit(self.key(i), value, False))
        self.steppers[i] = s
        return _row(self.labels[i], s)

    def set_output(self, output):
        self.out = output
        self.refresh_names()

    def refresh_names(self):
        """The names of the lists as the device connected has them: Ref Level per output, DA Filter per revision."""
        model = self.session.model
        self.steppers[P.REF_LEVEL].names = P.ref_levels(self.out[1], model)
        for i in P.CHOICES.keys() & self.steppers.keys():
            self.steppers[i].names = P.choices(i, model)
        da_filters = P.da_filters(self.session.revision(), model)
        if da_filters is not None:
            self.steppers[P.DA_FILTER].names = da_filters
        return da_filters

    def key(self, i):
        """The key of setting i of this output, where the device holds it (Session.at)."""
        return self.session.at((self.out[1], i))

    def active(self, i):
        """Setting i is that of an output the device has active, as its status message says: of this one, or of one
        that shares it (Session.sharing)."""
        st, model = self.session.device_status, self.session.model
        active = () if model is None else model.active
        return (st is not None and st.output < len(active)
                and bool(set(self.session.sharing((self.out[1], i))) & set(active[st.output])))

    def plug_warning(self, out=None):
        """Plugging headphones into output out (else this one) now brings up the device's Hi-Power warning: Hi-Power
        (by hand or by Auto Ref Level), Volume as shown above -15 dB, and no plug in yet. Once the plug is in, whoever
        put it in is at the device."""
        s, st, out = self.session.state, self.session.device_status, out or self.out[1]
        names = P.ref_levels(out, self.session.model)
        return ("Hi-Power" in names and s.get((out, P.REF_LEVEL)) == names.index("Hi-Power")
                and s.get((self.out[1], P.VOLUME), PLUG_WARNING_ABOVE) > PLUG_WARNING_ABOVE
                and st is not None and not getattr(st, PLUGS[out]))

    def shared_phones(self):
        """Phones 1/2 where it uses the settings of this output (Session.phones_1_2 'shared'); else None."""
        model = self.session.model
        return None if model is None else next((o for o, _ in model.separate if self.session.phones_1_2(o) == "shared"
                                                and self.session.follows(o) == self.out[1]), None)

    def refresh_phones_ref(self, ready):
        """Beside Line Out's Ref Level, where Phones 1/2 uses the settings of Line Out: that of Phones 1/2. On an
        ADI-2/4 Pro its own; on an ADI-2 Pro set by Line Out's, shown only."""
        s, model, line = self.session.state, self.session.model, self.key(P.REF_LEVEL)
        phones = self.shared_phones() if ready else None
        shown = phones is not None and not P.absent(P.REF_LEVEL, s.get(line))
        self.rows[PHONES_REF].setVisible(shown)
        self.labels[P.REF_LEVEL].setText("Ref Level Line Out" if shown else "Ref Level")
        if not shown:
            return
        key = self.session.kept_ref_level()
        if key is None:
            names = model.shared_ref_level
            self.phones_ref.names = names
            self.phones_ref.show_state(s.get(line), False, SHARED_REF_TIP % names[-1], held=True)
            return
        self.phones_ref.names = P.ref_levels(phones, model)
        held = s.get((phones, P.AUTO_REF_LEVEL)) == 1
        tip = "Chosen by Auto Ref Level, from Volume and the positive EQ gain" if held else TIPS[P.REF_LEVEL]
        warned = self.plug_warning(phones)
        if warned:
            tip += "\n" + PLUG_WARNING
        if key in self.marks.mismatch:
            tip += "\nSent %s, device has %s." % tuple(self.phones_ref.text(v) for v in self.marks.mismatch[key])
        self.phones_ref.show_state(s.get(key), self.session.writable(key), tip, bad=key in self.marks.mismatch,
                                   held=held, warned=warned)

    def crossfeed_crowded(self):
        """At EQ_OR_CROSSFEED_FROM and up, with the EQ on (either channel), Crossfeed does nothing."""
        st, s, (_, out, left, right) = self.session.device_status, self.session.state, self.out
        eq_on = s.get((left, P.EQ_ENABLE)) == 1 or self.session.dual(out) and s.get((right, P.EQ_ENABLE)) == 1
        return st is not None and st.rate is not None and st.rate >= EQ_OR_CROSSFEED_FROM and eq_on

    def refresh_volume(self):
        """Its unit in the row name: dBr while Auto Ref Level is on, else dB. Never faded (it works whatever else is
        on or off). With Lock Volume on it is the fixed volume: held, as the device refuses a write and takes it from
        its own menu only. With Mute or Dim on its value is amber: the output is silent, or Dim is on."""
        s, out, ready = self.session.state, self.out[1], self.session.ready()
        key = (out, P.VOLUME)
        on = lambda i: ready and s.get(self.key(i)) == 1                      # noqa: E731
        self.volume.unit = "dBr" if on(P.AUTO_REF_LEVEL) else "dB"
        self.volume_label.setText("Volume (%s)" % self.volume.unit)
        lowering = tuple(i for i in (P.MUTE, P.DIM) if on(i))
        if ready:
            self.volume.set_floor(P.volume_floor(s, out, self.session.model))
        lo, hi = self.volume.floor, P.OUTPUT_RANGES[P.VOLUME][1]
        tip = [LOWERED.get(lowering), OUT_OF_DIM if P.DIM in lowering and not on(P.LOCK_VOLUME) else None,
               "Lock Volume is on: set it in the device's menu." if on(P.LOCK_VOLUME) else
               "Adjust with the arrows or the mouse wheel.\nClick the value for a slider: up rises step by step.",
               "%s … +%s, step 0.5 dB" % (self.volume.text(lo), self.volume.text(hi))]
        if key in self.marks.mismatch:
            tip.append("Sent %s, device has %s." % tuple(self.volume.text(v) for v in self.marks.mismatch[key]))
        self.volume.show_state(s.get(key) if ready else None, self.session.writable(key), "\n".join(filter(None, tip)),
                               bad=key in self.marks.mismatch, held=on(P.LOCK_VOLUME), warned=bool(lowering))

    def toggle(self, i):
        key = self.key(i)
        if self.session.writable(key):
            self.edited.emit(key, 1 - self.session.state[key], False)

    def refresh(self):
        s, out, ready = self.session.state, self.out[1], self.session.ready()
        bypassed = ready and self.session.bypassed()
        da_filters = self.refresh_names()
        for i, stepper in self.steppers.items():
            key = self.key(i)
            unknown = i == P.DA_FILTER and da_filters is None
            v = s.get(key) if ready and not unknown else None
            self.rows[i].setVisible(not P.absent(i, v))
            if P.absent(i, v):
                continue
            tip = TIPS[i]
            if unknown:
                tip += "\n" + NOT_KNOWN
            held = i == P.REF_LEVEL and s.get((out, P.AUTO_REF_LEVEL)) == 1
            if held:
                tip = "Chosen by Auto Ref Level, from Volume and the positive EQ gain"
            crowded = ready and i == P.CROSSFEED and self.crossfeed_crowded()
            faded = (bypassed and i in PROCESSING or crowded) and v not in (None, stepper.off)
            if faded and bypassed:
                tip += "\nBypassed while the input is DSD: the device has no DSP for DSD."
            elif faded:
                tip += ("\nBypassed at %g kHz while the EQ is on: from %g kHz the device runs one of the two, the EQ"
                        " first." % (self.session.device_status.rate / 1000, EQ_OR_CROSSFEED_FROM / 1000))
            warned = ready and i == P.REF_LEVEL and self.plug_warning()
            if warned:
                tip += "\n" + PLUG_WARNING
            tip = "\n".join(filter(None, (tip, shared_tip(self.session, key))))
            if key in self.marks.mismatch:
                sent, actual = self.marks.mismatch[key]
                tip += "\nSent %s, device has %s." % (stepper.text(sent), stepper.text(actual))
            stepper.show_state(v, self.session.writable(key), tip, faded, key in self.marks.mismatch, held, warned)
        self.refresh_phones_ref(ready)
        self.refresh_volume()
        for i, option in self.options.items():
            key = self.key(i)
            v = s.get(key) if ready else None
            self.rows[i].setVisible(not P.absent(i, v))
            on = v == 1
            tip = "%s: %s\n%s" % (OPTIONS[i], "on" if on else "off", OPTION_TIPS[i])
            enabled = self.session.writable(key)
            if i == P.DIM and not self.active(i):               # as on the device: the current output only
                enabled, tip = False, tip + "\n" + DIM_ACTIVE_ONLY
            option.show_state(on, enabled, "\n".join(filter(None, (tip, shared_tip(self.session, key)))))
