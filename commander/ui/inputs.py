"""The inputs of the device: Source, what each input receives, and the clock. One panel for all outputs.

ADI-2 DAC FS: Source is one setting of the device, the same on Line Out, Phones and IEM.

    SOURCE          Source, a stepper, written to all three outputs at once; under it per input what the device's
                    status message says it receives, a dot at the input that plays
    CLOCK           the rate the device runs at, and the clock it follows

An input matters when it plays, or, with USB (Rec …), when it is recorded and clocks the device. What it receives is
white; nothing on an input that does not matter is grey; nothing, or a signal not in sync, on an input that matters
is amber. USB shows the rate set on the computer: whether audio comes with it, the device does not say.

ADI-2 Pro and ADI-2/4 Pro: the Basic Mode in use, then one Source for Line Out and Phones 1/2 and one for Phones
3/4; in Basic Mode DAC one for all outputs (Session.source_rows). Outside AD/DA and DAC the Basic Mode in use sets
the input of Line Out and Phones 1/2, and their row shows that input. Under CLOCK the rate the device runs at and
Clock Source, which cannot be set in Basic Mode DAC. Under it the settings of the analog input, in the groups LEVEL,
PROCESSING, ADC and RIAA, each row as far as the device has the setting.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..device import params as P
from . import theme
from .output import LABEL_WIDTH, NAME_INDENT, ROW_HEIGHT, VALUE_WIDTH, _label, _row
from .presets import restyle
from .widgets import ATTACHED_GAP, DOT_GAP, GROUP_STYLE, INNER_GAP, TITLE_STYLE, Dot, Option, Stepper, head

INPUTS = [("coax", "SPDIF coax"), ("optical", "Optical"), ("usb", "USB")]
SOURCE_TIP = ("The input of the whole device: Line Out, Phones and IEM alike\n"
              "Auto prefers SPDIF to USB; the USB (Rec …) choices select USB and record the SPDIF input over USB.")
MODE_TIP = "The Basic Mode in use\nSet in DEVICE › DEVICE MODE"
CLOCK_SOURCE_TIP = "The clock the device runs on\nAuto: the digital input with a signal; INT: its own"
NOT_IN_DAC_MODE = "In Basic Mode DAC Source sets it."
OUTPUTS_TIP = "The input of %s"                      # with the names of the outputs
SHORT = {"Phones 1/2": "Ph 1/2"}                     # in the name of a row of two outputs, as the device writes it
ALL_TIP = "The input of all outputs, and the clock of the device"
SET_BY_MODE_TIP = "Set by Basic Mode %s"
# what Line Out takes in a Basic Mode that sets it: USB, Preamp, Dig Thru
MODE_TAKES = {2: "USB 1/2", 3: "Analog", 4: "Digital input"}
PLAYS_TIP = "The input the device has selected"
RECORDED_TIP = "Recorded over USB; the device follows its clock."
NOT_IN_SYNC_TIP = "Not at the rate of the device's clock"
# the analog input of an ADI-2 Pro and ADI-2/4 Pro: (group, [(index, row name)]); Auto Ref Level is an option
ANALOG = [("LEVEL", [(P.IN_AUTO_REF_LEVEL, "Auto Ref Level"), (P.IN_REF_LEVEL, "Ref Level"),
                     (P.TRIM_LEFT, "Trim Gain L (dB)"), (P.TRIM_RIGHT, "Trim Gain R (dB)")]),
          ("PROCESSING", [(P.IN_POLARITY, "Polarity"), (P.IN_MS_PROC, "M/S-Proc")]),
          ("ADC", [(P.AD_FILTER, "AD Filter"), (P.AD_CONVERSION, "AD Conversion"), (P.DC_FILTER, "DC Filter")]),
          ("RIAA", [(P.RIAA_MODE, "RIAA Mode"), (P.RIAA_MONO_BASS, "RIAA Mono Bass"),
                    (P.BAL_IMPEDANCE, "Bal. Impedance")])]
ANALOG_TIPS = {P.IN_AUTO_REF_LEVEL: "On: the device raises Ref Level a step when the input overloads, up to +24 dBu;\n"
                                    "Trim goes to 0 dB first.",
               P.IN_REF_LEVEL: "The input level at full scale",
               P.TRIM_LEFT: "Digital gain of the left channel", P.TRIM_RIGHT: "Digital gain of the right channel",
               P.IN_POLARITY: "Inverts the polarity of both channels, or of one",
               P.IN_MS_PROC: "Mid/side: mono content to the left channel, stereo content to the right",
               P.AD_FILTER: "The filter of the AD conversion",
               P.AD_CONVERSION: "PCM, or DSD from 176.4 kHz on",
               P.DC_FILTER: "Removes DC from the input",
               P.RIAA_MODE: "Equalization and gain for a turntable with a moving magnet cartridge",
               P.RIAA_MONO_BASS: "Mono below 150 Hz",
               P.BAL_IMPEDANCE: "The impedance of the balanced input; 47 kΩ suits a moving magnet cartridge."}
RAISED_BY_AUTO = "Auto Ref Level raises it when the input overloads."
SET_BY_RIAA = {P.IN_REF_LEVEL: "RIAA Mode sets it to +1 dBu.", P.IN_AUTO_REF_LEVEL: "Off while RIAA Mode is on"}
RIAA_UP_TO = 192000                              # RIAA Mode works up to this rate, and with PCM only
OFF_AT_FIRST = {P.TRIM_LEFT, P.TRIM_RIGHT, P.IN_POLARITY, P.IN_MS_PROC, P.RIAA_MODE, P.RIAA_MONO_BASS}  # grey: off


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
    edited = Signal(object, int, bool)               # key, value, rounded or clamped: as the output panel's

    def __init__(self, session, marks):
        super().__init__()
        self.session, self.marks = session, marks
        self.dots, self.values = {}, {}
        self.rows = []                                   # per Source setting: (row, name, stepper)
        title = QLabel("INPUT")
        title.setStyleSheet(TITLE_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(head(title))
        lay.addSpacing(INNER_GAP)
        lay.addWidget(self._group("SOURCE"))
        lay.addSpacing(ATTACHED_GAP)
        self.mode_row = self._shown("mode", "Basic Mode")
        self.mode_row.setToolTip(MODE_TIP)
        lay.addWidget(self.mode_row)
        for n in range(2):
            stepper = Stepper(P.INPUTS)
            stepper.setFixedWidth(VALUE_WIDTH)
            stepper.chosen.connect(lambda value, n=n: self.choose(n, value))
            name = _label("Source")
            self.rows.append((_row(name, stepper), name, stepper))
            lay.addWidget(self.rows[n][0])
        self.source = self.rows[0][2]
        self.dac_fs = []                                 # what only the ADI-2 DAC FS shows
        for name, text in INPUTS:
            self.dac_fs.append(self._shown(name, text, dot=True))
            lay.addWidget(self.dac_fs[-1])
        lay.addSpacing(INNER_GAP)
        lay.addWidget(self._group("CLOCK"))
        lay.addSpacing(ATTACHED_GAP)
        lay.addWidget(self._shown("rate", "Sample Rate"))
        self.dac_fs.append(self._shown("clock", "Clock"))
        lay.addWidget(self.dac_fs[-1])
        self.clock_source = Stepper([""])
        self.clock_source.setFixedWidth(VALUE_WIDTH)
        self.clock_source.chosen.connect(
            lambda value: self.edited.emit((P.DEVICE_ADDRESS, P.CLOCK_SOURCE), value, False))
        self.clock_source_row = _row(_label("Clock Source"), self.clock_source)
        lay.addWidget(self.clock_source_row)
        self.analog, self.analog_rows, self.analog_groups = {}, {}, []   # steppers, rows, (widgets, indices)
        self.auto_ref = Option("Auto Ref Level")
        self.auto_ref.clicked.connect(self.toggle_auto_ref)
        for group, items in ANALOG:
            space, gap = QWidget(), QWidget()
            space.setFixedHeight(INNER_GAP)
            gap.setFixedHeight(ATTACHED_GAP)
            widgets = (space, self._group(group), gap)
            self.analog_groups.append((widgets, [i for i, _ in items]))
            for w in widgets:
                lay.addWidget(w)
            for i, text in items:
                if i == P.IN_AUTO_REF_LEVEL:
                    row = _row(self.auto_ref, indent=NAME_INDENT - Option.RING - 1)   # the track where names start
                else:
                    stepper = Stepper([""], off=0 if i in OFF_AT_FIRST else None)
                    stepper.setFixedWidth(VALUE_WIDTH)
                    stepper.chosen.connect(lambda value, i=i: self.choose_analog(i, value))
                    self.analog[i] = stepper
                    row = _row(_label(text), stepper)
                self.analog_rows[i] = row
                lay.addWidget(row)
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

    def choose(self, n, value):
        rows = self.session.source_rows()
        if n < len(rows) and self.session.writable(rows[n].key):
            self.session.set_source(value, rows[n].key)

    def choose_analog(self, i, n):
        """The n-th name of setting i of the analog input chosen."""
        key, c = (P.INPUT_ADDRESS, i), self.session.input_choices(i)
        if c is not None and self.session.writable(key):
            self.edited.emit(key, c.first + n, False)

    def toggle_auto_ref(self):
        key = (P.INPUT_ADDRESS, P.IN_AUTO_REF_LEVEL)
        if self.session.writable(key):
            self.edited.emit(key, 1 - self.session.state[key], False)

    def refresh(self):
        model = self.session.model
        own = model is not None and model.sources is not None          # an ADI-2 Pro or ADI-2/4 Pro
        self.mode_row.setVisible(own)
        for w in self.dac_fs:
            w.setVisible(not own)
        self.clock_source_row.setVisible(own)
        self.refresh_analog(own)
        if own:
            self.refresh_rows(model)
            self.refresh_clock()
            return
        self.rows[1][0].hide()
        self.rows[0][1].setText("Source")
        self.source.names = P.INPUTS
        s, st, ready = self.session.state, self.session.device_status, self.session.ready()
        keys = [(out, P.SOURCE) for out in P.OUTPUT_ADDRESSES]
        source = s.get(keys[0]) if ready else None
        bad = [k for k in keys if k in self.marks.mismatch]
        tip = SOURCE_TIP
        if bad:
            sent, actual = self.marks.mismatch[bad[0]]
            tip += "\nSent %s, device has %s." % (self.source.text(sent), self.source.text(actual))
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
        self.values["clock"].setToolTip("The device follows this SPDIF input's clock." if known and st.clock else
                                        "The device runs on its own clock." if known else "")

    def refresh_rows(self, model):
        """ADI-2 Pro and ADI-2/4 Pro: the Basic Mode in use, and a row per Source setting."""
        s, ready = self.session.state, self.session.ready()
        mode = self.session.basic_mode() if ready else None
        text = ""
        if mode is not None and mode < len(P.BASIC_MODES):
            text = P.BASIC_MODES[mode]
            if s.get(P.BASIC_MODE) == P.BASIC_MODES.index("Auto"):
                text = "Auto: " + text
        self.values["mode"].setText(text)
        rows = self.session.source_rows() if ready else []
        for n, (row, name, stepper) in enumerate(self.rows):
            row.setVisible(n < max(len(rows), 1))
            if n >= len(rows):
                name.setText("Source")
                stepper.show_state(None, False, "")
                continue
            r = rows[n]
            outputs = [model.outputs[P.OUTPUT_ADDRESSES.index(o)] for o in r.outputs]
            every = len(r.outputs) == len(P.OUTPUT_ADDRESSES)
            name.setText("Source" if every else outputs[0] if len(outputs) == 1 else
                         " · ".join(SHORT.get(o, o) for o in outputs))
            tip = ALL_TIP if every else OUTPUTS_TIP % " and ".join(outputs)
            takes = MODE_TAKES.get(mode) if r.key == rows[0].key else None
            if takes is not None:                        # set by the Basic Mode in use
                stepper.names, value = [takes], 0
                tip += "\n" + SET_BY_MODE_TIP % P.BASIC_MODES[mode]
            else:
                stepper.names, value = r.names, s.get(r.key)
            bad = r.key in self.marks.mismatch
            if bad:
                sent, actual = self.marks.mismatch[r.key]
                tip += "\nSent %s, device has %s." % (stepper.text(sent), stepper.text(actual))
            stepper.show_state(value, self.session.writable(r.key), tip, bad=bad, held=takes is not None)

    def refresh_clock(self):
        """ADI-2 Pro and ADI-2/4 Pro: the rate the device runs at (Sample Rate), and Clock Source."""
        session, s, ready = self.session, self.session.state, self.session.ready()
        index = s.get(P.SAMPLE_RATE) if ready else None
        self.values["rate"].setText(_khz(P.SAMPLE_RATES[index]) if index in range(len(P.SAMPLE_RATES)) else "")
        key = (P.DEVICE_ADDRESS, P.CLOCK_SOURCE)
        setting = session.device_setting(P.CLOCK_SOURCE) if ready else None
        if setting is not None:
            self.clock_source.names = setting.names
        tip = [CLOCK_SOURCE_TIP, NOT_IN_DAC_MODE if ready and session.basic_mode() == P.MODE_DAC else None]
        bad = key in self.marks.mismatch
        if bad:
            tip.append("Sent %s, device has %s." % tuple(self.clock_source.text(v) for v in self.marks.mismatch[key]))
        self.clock_source.show_state(s.get(key) if ready else None, session.writable(key),
                                     "\n".join(filter(None, tip)), bad=bad)

    def refresh_analog(self, shown):
        """ADI-2 Pro and ADI-2/4 Pro: the settings of the analog input, a row for each the device has, a group as far
        as it has a row. With RIAA Mode on Ref Level is held at +1 dBu. Faded where the device does not use the value
        now: AD Filter from the rate on where it uses Slow only, RIAA Mode above 192 kHz or with DSD, AD Conversion
        DSD while the device converts to PCM."""
        session, s, ready = self.session, self.session.state, self.session.ready()
        have = {i: session.input_choices(i) for i in self.analog_rows} if shown else {}
        have = {i: c for i, c in have.items() if c is not None and (not ready or (P.INPUT_ADDRESS, i) in s)}
        for widgets, indices in self.analog_groups:
            for w in widgets:
                w.setVisible(any(i in have for i in indices))
        for i, row in self.analog_rows.items():
            row.setVisible(i in have)
        if not have:
            return
        model, riaa = session.model, ready and session.riaa()
        index = s.get(P.SAMPLE_RATE) if ready else None
        rate = P.SAMPLE_RATES[index] if index in range(len(P.SAMPLE_RATES)) else None
        value = lambda i: s.get((P.INPUT_ADDRESS, i)) if ready else None          # noqa: E731
        on = value(P.IN_AUTO_REF_LEVEL) == 1
        tip = ["Auto Ref Level: %s" % ("on" if on else "off"), ANALOG_TIPS[P.IN_AUTO_REF_LEVEL],
               SET_BY_RIAA[P.IN_AUTO_REF_LEVEL] if riaa else None]
        self.auto_ref.show_state(on, session.writable((P.INPUT_ADDRESS, P.IN_AUTO_REF_LEVEL)),
                                 "\n".join(filter(None, tip)))
        for i, stepper in self.analog.items():
            if i not in have:
                continue
            key, c, v = (P.INPUT_ADDRESS, i), have[i], value(i)
            stepper.names = c.names
            tip, why = [ANALOG_TIPS[i]], None
            if i == P.IN_REF_LEVEL:
                tip.append(SET_BY_RIAA[i] if riaa else RAISED_BY_AUTO if on else None)
            elif i == P.AD_FILTER and rate is not None and rate >= model.ad_filter_fixed_from:
                why = "Not in use: from %g kHz the device uses Slow only." % (model.ad_filter_fixed_from / 1000)
            elif i == P.RIAA_MODE and (rate is not None and rate > RIAA_UP_TO or value(P.AD_CONVERSION) == 1):
                why = "Not in use: RIAA Mode works up to %g kHz, with PCM only." % (RIAA_UP_TO / 1000)
            elif i == P.AD_CONVERSION and v == 1 and not session.bypassed():
                why = "PCM now: DSD from %g kHz on" % (P.DSD_RECORD_FROM / 1000)
            faded = why is not None and v is not None and v - c.first != stepper.off
            tip.append(why if faded else None)
            bad = key in self.marks.mismatch
            if bad:
                sent, actual = (stepper.text(n - c.first) for n in self.marks.mismatch[key])
                tip.append("Sent %s, device has %s." % (sent, actual))
            stepper.show_state(None if v is None else v - c.first, session.writable(key), "\n".join(filter(None, tip)),
                               faded, bad, held=i == P.IN_REF_LEVEL and riaa)
