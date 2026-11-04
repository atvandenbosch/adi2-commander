"""The input of the whole device: Source, what each input receives, and the clock. One panel for all outputs: Source
is one setting of the device, the same on Line Out, Phones and IEM.

    SOURCE          Source, a stepper, written to all three outputs at once; under it per input what the device's
                    status message says it receives, a dot at the input that plays
    CLOCK           the rate the device runs at, and the clock it follows

An input matters when it plays, or, with USB (Rec …), when it is recorded and clocks the device. What it receives is
white; nothing on an input that does not matter is grey; nothing, or a signal not in sync, on an input that matters
is amber. USB shows the rate set on the computer: whether audio comes with it, the device does not say.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..device import params as P
from . import theme
from .output import LABEL_WIDTH, NAME_INDENT, ROW_HEIGHT, VALUE_WIDTH, _label, _row
from .presets import restyle
from .widgets import ATTACHED_GAP, DOT_GAP, GROUP_STYLE, INNER_GAP, TITLE_STYLE, Dot, Stepper, head

INPUTS = [("coax", "SPDIF coax"), ("optical", "Optical"), ("usb", "USB")]
SOURCE_TIP = ("The input of the whole device: Line Out, Phones and IEM alike.\n"
              "Auto prefers SPDIF to USB; the USB (Rec …) choices select USB and record the SPDIF input over USB.")
PLAYS_TIP = "The input the device has selected"
RECORDED_TIP = "Recorded over USB; the device follows its clock"
NOT_IN_SYNC_TIP = "Not at the rate of the device's clock"


def played(source, status):
    """The input the device takes, 'coax', 'optical' or 'usb'. With Auto the one it follows: SPDIF before USB."""
    if source == P.INPUTS.index("Auto"):
        return status.clock or "usb"
    return {P.INPUTS.index("SPDIF coax"): "coax", P.INPUTS.index("Optical"): "optical"}.get(source, "usb")


def recorded(source):
    """With USB (Rec …) the SPDIF input recorded over USB, which the device takes its clock from; else None."""
    return {P.INPUTS.index("USB (Rec coax)"): "coax", P.INPUTS.index("USB (Rec opt.)"): "optical"}.get(source)


def _khz(rate):
    return "%g kHz" % (rate / 1000)


def _dsd(rate):
    """DSD by the rate of the PCM that carries it: 16 DSD bits per sample, DSD64 at 176.4 kHz."""
    return "DSD%d" % (rate * 16 // 44100) if rate and rate % 44100 == 0 else "DSD"


def _spdif_text(spdif, matters):
    """What an SPDIF input receives, and its trouble: 'nothing' (no signal, non-audio data), 'sync' on an input that
    matters and is not at the rate of the device's clock (elsewhere sync means nothing), or None."""
    if not spdif.lock:
        return "no signal", "nothing"
    if spdif.non_audio:
        return "non-audio", "nothing"
    text = _dsd(spdif.rate) + " (DoP)" if spdif.dsd else _khz(spdif.rate) if spdif.rate else "signal"
    if matters and not spdif.sync:
        return text + ", not in sync", "sync"
    return text, None


def _usb_text(status, plays):
    """The rate set for USB, and its trouble: 'sync' when it plays while the device follows an SPDIF clock at
    another rate (USB (Rec …)), or None."""
    if status.usb_rate is None:
        return "", None
    text = _dsd(status.usb_rate) + " (DoP)" if status.usb_dsd else _khz(status.usb_rate)
    if plays and status.clock is not None and status.usb_rate != status.rate:
        return text + ", not in sync", "sync"
    return text, None


class InputPanel(QWidget):
    def __init__(self, session, marks):
        super().__init__()
        self.session, self.marks = session, marks
        self.source = Stepper(P.INPUTS)
        self.source.setFixedWidth(VALUE_WIDTH)
        self.source.chosen.connect(self.choose)
        self.dots, self.values = {}, {}
        title = QLabel("INPUT")
        title.setStyleSheet(TITLE_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(head(title))
        lay.addSpacing(INNER_GAP)
        lay.addWidget(self._group("SOURCE"))
        lay.addSpacing(ATTACHED_GAP)
        lay.addWidget(_row(_label("Source"), self.source))
        for name, text in INPUTS:
            lay.addWidget(self._shown(name, text, dot=True))
        lay.addSpacing(INNER_GAP)
        lay.addWidget(self._group("CLOCK"))
        lay.addSpacing(ATTACHED_GAP)
        lay.addWidget(self._shown("rate", "Sample Rate"))
        lay.addWidget(self._shown("clock", "Clock"))
        lay.addStretch()

    @staticmethod
    def _group(name):
        group = QLabel(name)
        group.setStyleSheet(GROUP_STYLE)
        return head(group)

    def _shown(self, key, text, dot=False):
        """A row of what is only shown: its name, after a dot where the dot can mark it, then the value."""
        value = QLabel()
        value.setFixedWidth(VALUE_WIDTH)
        value.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        value.setStyleSheet("color: %s;" % theme.TEXT.name())
        self.values[key] = value
        if not dot:
            return _row(_label(text), value)
        mark = Dot()
        self.dots[key] = mark
        name = QLabel(text)
        name.setStyleSheet("color: %s;" % theme.LABEL.name())
        name.setFixedWidth(LABEL_WIDTH - NAME_INDENT - mark.width() - DOT_GAP)
        row = QWidget()
        row.setFixedHeight(ROW_HEIGHT)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(NAME_INDENT, 0, 0, 0)
        lay.setSpacing(DOT_GAP)
        lay.addWidget(mark)
        lay.addWidget(name)
        lay.addWidget(value)
        lay.addStretch()
        return row

    def choose(self, value):
        if self.session.writable((P.OUTPUT_ADDRESSES[0], P.SOURCE)):
            self.session.set_source(value)

    def refresh(self):
        s, st, ready = self.session.state, self.session.device_status, self.session.ready()
        keys = [(out, P.SOURCE) for out in P.OUTPUT_ADDRESSES]
        source = s.get(keys[0]) if ready else None
        bad = [k for k in keys if k in self.marks.mismatch]
        tip = SOURCE_TIP
        if bad:
            sent, actual = self.marks.mismatch[bad[0]]
            tip += "\nSent %s, device has %s" % (self.source.text(sent), self.source.text(actual))
        self.source.show_state(source, ready and all(self.session.writable(k) for k in keys), tip, bad=bool(bad))
        known = ready and st is not None and source is not None
        plays = played(source, st) if known else None
        rec = recorded(source) if known else None
        for name, _ in INPUTS:
            matters = name in (plays, rec)
            if not known:
                text, trouble = "", None
            elif name == "usb":
                text, trouble = _usb_text(st, name == plays)
            else:
                text, trouble = _spdif_text(getattr(st, name), matters)
            if name == plays and trouble == "nothing":
                plays = None                         # the chosen SPDIF input has nothing to play
            color = theme.WARN if trouble and matters else theme.SECONDARY if trouble else theme.TEXT
            self.values[name].setText(text)
            restyle(self.values[name], "color: %s;" % color.name())
            tips = [RECORDED_TIP if name == rec else "", NOT_IN_SYNC_TIP if trouble == "sync" else ""]
            self.values[name].setToolTip("\n".join(filter(None, tips)))
            if name == plays:
                self.dots[name].set(theme.GOOD)
                self.dots[name].setToolTip(PLAYS_TIP)
            else:
                self.dots[name].clear()
                self.dots[name].setToolTip("")
        if known:
            rate = _dsd(st.rate) if st.dsd else _khz(st.rate) if st.rate else ""
            clock = dict(INPUTS).get(st.clock, "Internal")
        else:
            rate = clock = ""
        self.values["rate"].setText(rate)
        self.values["clock"].setText(clock)
        self.values["clock"].setToolTip("The device follows this SPDIF input's clock" if known and st.clock else
                                        "The device runs on its own clock" if known else "")
