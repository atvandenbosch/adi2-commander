"""The settings of one output besides its EQ, Bass/Treble and Loudness, in three groups: Level, Processing and DAC.

A setting the output does not have (IEM: Ref Level and Auto Ref Level; Rear TRS Source, which only Phones 3/4 of the
ADI-2/4 Pro has) is left out. The input is in the Input panel.

    one of a few values     a stepper (‹ value ›)
    Width                   a stepper too: Swapped .. -0.50 .. Mono .. 0.50 .. Stereo; the value opens a slider
                            instead of a list
    on or off               an option: Auto Ref Level

Volume, Lock Volume, Mute, Dim and Balance are in the volume section (volume.VolumeSection).
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
OPTIONS = {P.AUTO_REF_LEVEL: "Auto Ref Level"}
OPTION_TIPS = {P.AUTO_REF_LEVEL: "On: the device chooses Ref Level from Volume and the positive EQ gain."}
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
        P.BALANCE: "L left only, C centre, R right only\nSteps of 5; with Ctrl of 1\n"
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


class RangeSlider(QWidget):
    """A value along a track from end to end (Width, Balance), filled in grey from the anchor (Width,
    Balance: the value that leaves the sound as it is) to the knob, with a tick at each point named between the ends.
    A drag, or a click on the track, puts the knob there. Which end is which, the buttons under it say. One pixel per
    hundredth."""

    moved = Signal(int)
    KNOB, TRACK = 12, 4                          # px

    def __init__(self, index, anchor, ticks):
        super().__init__()
        self.lo, self.hi = P.OUTPUT_RANGES[index]
        self.anchor, self.ticks = anchor, ticks
        self.value, self._dragging = anchor, False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.KNOB + self.hi - self.lo + 1, Stepper.HEIGHT)

    def x_of(self, value):
        """The middle of the value's column of pixels."""
        return self.KNOB // 2 + value - self.lo + 0.5

    def value_at(self, x):
        """The value of the column of pixels that holds x."""
        return max(self.lo, min(self.hi, self.lo + math.floor(x) - self.KNOB // 2))

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


class RangePopup(QFrame):
    """Under a RangeStepper: the slider, and a button for each named point. Every change goes to the stepper (aim),
    which shows it. The arrow keys and the wheel move by one, PgUp and PgDn as the stepper's arrows: it stays open, to
    adjust further. A named point is chosen at once and closes it, as Enter or a click elsewhere does; Esc brings back
    the value it opened with."""

    NOTCH = 120                                  # angleDelta of one wheel notch

    def __init__(self, stepper):
        super().__init__(stepper, Qt.Popup | Qt.FramelessWindowHint)
        self.stepper, self.opened, self._wheel = stepper, stepper.value, 0
        self.setAttribute(Qt.WA_NoMouseReplay)   # a click elsewhere only closes it
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet("RangePopup { background: %s; border: 1px solid %s; }"
                           % (theme.PANEL.name(), theme.BORDER.name()))
        self.slider = stepper.slider()
        self.slider.set_value(stepper.value)
        self.slider.moved.connect(self.choose)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        actions = []
        for n, (text, value) in enumerate(stepper.points):
            if n:
                buttons.addStretch()
            b = Action(compact=True)
            b.setText(text)
            b.setFocusPolicy(Qt.NoFocus)         # the keys stay with the slider
            b.clicked.connect(lambda _=False, value=value: self.pick(value))
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

    def pick(self, value):
        """A named point: chosen, and done."""
        self.choose(value)
        self.close()

    def follow(self):
        """The stepper's state: its value unless the knob is being dragged, and whether it can be changed."""
        if self.stepper.value is None:
            self.close()
            return
        self.slider.set_value(self.stepper.value)
        self.setEnabled(self.stepper.isEnabled())

    def _by_one(self, direction):
        s = self.slider
        self.choose(max(s.lo, min(s.hi, s.value + direction)))

    def keyPressEvent(self, e):
        k, v = e.key(), self.slider.value
        if k in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up):
            self._by_one(1 if k in (Qt.Key_Right, Qt.Key_Up) else -1)
        elif k in (Qt.Key_PageUp, Qt.Key_PageDown):
            n = self.stepper.neighbour(v, 1 if k == Qt.Key_PageUp else -1, False)
            if n is not None:
                self.choose(n)
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.close()
        elif k == Qt.Key_Escape:
            self.stepper.aim(self.opened)
            self.close()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        e.accept()
        self._wheel += e.angleDelta().y()
        while abs(self._wheel) >= self.NOTCH:
            direction = 1 if self._wheel > 0 else -1
            self._wheel -= direction * self.NOTCH
            self._by_one(direction)


class RangeStepper(Stepper):
    """Width or Balance, in hundredths, as the device shows them, but for the named points. The arrows step to the next
    multiple of 5, with Ctrl by 1; the value opens a slider by 1 (RangePopup) instead of a list.

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
        lo, hi = P.OUTPUT_RANGES[self.index]
        return [self.text(v) for v in range(lo, hi + 1)]

    def slider(self):
        return RangeSlider(self.index, self.anchor, [v for _, v in self.points[1:-1]])

    def aim(self, value):
        """A value chosen on the slider: written at once."""
        if value != self.value and self.isEnabled():
            self.chosen.emit(value)

    def show_menu(self):
        self.popup = RangePopup(self)
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
        groups = [("LEVEL", [(P.AUTO_REF_LEVEL, None), (P.REF_LEVEL, "Ref Level"),
                             (PHONES_REF, "Ref Level Ph 1/2")]),
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
        self.labels[i] = _label(text)
        if i == PHONES_REF:
            return _row(self.labels[i], self.phones_ref)
        names = P.CHOICES.get(i)
        if i == P.WIDTH:
            s = RangeStepper(i, [(n, v) for v, n in P.WIDTH_NAMES.items()], anchor=100)   # full stereo
        elif i == P.BALANCE:
            s = RangeStepper(i, [(n, v) for v, n in P.BALANCE_NAMES.items()], anchor=0)
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
            tip += "\nSent %s, the device has %s." % tuple(self.phones_ref.text(v) for v in self.marks.mismatch[key])
        self.phones_ref.show_state(s.get(key), self.session.writable(key), tip, bad=key in self.marks.mismatch,
                                   held=held, warned=warned)

    def crossfeed_crowded(self):
        """At EQ_OR_CROSSFEED_FROM and up, with the EQ on (either channel), Crossfeed does nothing."""
        st, s, (_, out, left, right) = self.session.device_status, self.session.state, self.out
        eq_on = s.get((left, P.EQ_ENABLE)) == 1 or self.session.dual(out) and s.get((right, P.EQ_ENABLE)) == 1
        return st is not None and st.rate is not None and st.rate >= EQ_OR_CROSSFEED_FROM and eq_on

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
                tip += "\nSent %s, the device has %s." % (stepper.text(sent), stepper.text(actual))
            stepper.show_state(v, self.session.writable(key), tip, faded, key in self.marks.mismatch, held, warned)
        self.refresh_phones_ref(ready)
        for i, option in self.options.items():
            key = self.key(i)
            v = s.get(key) if ready else None
            self.rows[i].setVisible(not P.absent(i, v))
            on = v == 1
            tip = "%s: %s\n%s" % (OPTIONS[i], "on" if on else "off", OPTION_TIPS[i])
            option.show_state(on, self.session.writable(key),
                              "\n".join(filter(None, (tip, shared_tip(self.session, key)))))
