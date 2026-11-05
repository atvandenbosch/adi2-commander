"""A simulated ADI-2 at the level of raw SysEx: bytes in, bytes out.

SimPort takes the place of WinmmPort, so everything above it (the session, the app) runs unchanged.

The ADI-2 DAC FS is simulated as it behaves. The ADI-2 Pro and ADI-2/4 Pro are simulated as RME's MIDI table
(MIDITable_ADI-2 v1.2) and their manuals describe them: their parameters, ranges and factory values. Where they
share the protocol of the ADI-2 DAC FS (EQ, presets, Volume, Dim, Lock Volume) they follow its rules; what only the
ADI-2 DAC FS is known to do (Source and the clock, Auto Ref Level, the status message from its inputs) they do not.

Anything the model does not cover is not silently accepted: it is recorded in SimulatedAdi2.unsimulated,
and tests assert that list stays empty.
"""

import os
import threading
import time
from collections import namedtuple

from . import codec, models
from .connection import DeviceNotFound, PortBusy
from .params import EQ_RANGES, FACTORY_BANDS, FACTORY_BT, SAMPLE_RATES

# The device's answers for an invented setup: what --simulate starts from, and the tests too
DEMO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo")
DEMO_DUMP = os.path.join(DEMO, "dump.txt")
DEMO_PRESETS = os.path.join(DEMO, "presets.txt")

# ---------------------------------------------------------------------------------------------
# Parameter ranges in increments (gain x2, Q x10, volume x10, frequency in Hz)

OUTPUT_ADDRESSES = (3, 6, 9)                     # Line Out, Phones 1/2, Phones 3/4 / IEM
EQ_PAIRS = {3: (4, 5), 6: (7, 8), 9: (10, 11)}   # output address -> (left EQ, right EQ)
LEFT_EQ = {l: o for o, (l, r) in EQ_PAIRS.items()}
RIGHT_EQ = {r: l for o, (l, r) in EQ_PAIRS.items()}
INPUT_EQ = (1, 2)                                # ADI-2 Pro and ADI-2/4 Pro: the EQ of the input, left and right

# output channel settings, ADI-2 DAC; index 2 differs between line and phones
OUTPUT_RANGES = {
    1: (0, 5), 3: (0, 1), 4: (0, 2), 5: (-100, 100), 6: (0, 1), 7: (0, 3), 8: (0, 5),
    9: (0, 5),                                   # DA Filter
    10: (0, 2), 11: (0, 1), 12: (-1200, 60), 13: (0, 1), 14: (-100, 100), 15: (0, 1), 16: (0, 1),
    17: (0, 3), 18: (0, 2), 20: (0, 1), 21: (2, 20), 22: (2, 20),
    23: (-180, -40),                             # Low Vol Ref in 0.5 dB steps
}
REF_LEVEL_RANGE = {3: (0, 3), 6: (0, 1), 9: (0, 1)}
# Auto Ref Level, on Line Out and Phones: the Volume of one Ref Level step (Line 6 dB, Phones 15 dB)
REF_STEP = {3: 60, 6: 150}

# device settings (address 12), ADI-2 DAC
DEVICE_RANGES = {
    1: (0, 3), 2: (0, 4), 3: (0, 1), 4: (0, 1), 5: (0, 1), 15: (0, 3),
    25: (0, 2), 26: (0, 41), 27: (0, 41), 28: (0, 41), 29: (0, 41),
    32: (0, 1), 33: (0, 5), 34: (0, 3), 35: (0, 1), 36: (0, 1), 37: (0, 3),
}
DEVICE_READ_ONLY = {16}                          # Sample Rate, display only

# ---------------------------------------------------------------------------------------------
# ADI-2 Pro and ADI-2/4 Pro: {index: (min, max, factory value)}. Where the table's maximum and its list of names
# disagree, the names count: Input Ref Level and DA Filter of the Pro, SRC Gain.

PRO_OUTPUT = {
    1: (0, 5, 0),                                # Source; one more in Basic Mode DAC (SOURCE_IN_DAC_MODE)
    3: (0, 1, 1), 4: (0, 2, 0), 5: (-100, 100, 100), 6: (0, 1, 0), 7: (0, 3, 0), 8: (0, 5, 0),
    9: (0, 5, 0),                                # DA Filter: SD Sharp .. NOS, SD LD
    10: (0, 2, 0), 11: (0, 1, 0), 12: (-1145, 60, -100), 13: (0, 1, 0), 14: (-100, 100, 0), 15: (0, 1, 0),
    16: (0, 1, 0), 17: (0, 9, 0), 18: (0, 2, 2), 20: (0, 1, 0), 21: (2, 20, 14), 22: (2, 20, 14),
    23: (-180, -40, -60),
}
PRO_REF_LEVEL = {"line": (0, 3, 2), "phones": (0, 1, 0)}    # +4 .. +24 dBu; Lo-Power, Hi-Power
PRO_24_OUTPUT = {**PRO_OUTPUT, 9: (0, 6, 2)}     # DA Filter: SD Sharp .. SD LD, Brickwall, NOS
PRO_24_REF_LEVEL = {"line": (0, 4, 1), "phones": (0, 2, 1)}  # +1 .. +24 dBu; IEM, Lo-Power, Hi-Power
REAR_TRS_SOURCE = {19: (0, 1, 0)}                # ADI-2/4 Pro, Phones 3/4 only: Line 1/2, Ph. 3/4
EX_SOURCE = (0, 6, 0)                            # ADI-2/4 Pro EX: ADAT 3/4 besides
SOURCE_IN_DAC_MODE = (0, 6, 0)                   # Auto, AES, SPDIF coax, Optical, Analog, USB 1/2, USB 3/4
BASIC_MODE, BASIC_MODE_DAC = 6, 5                # on address 12

INPUT = {                                        # address 0, the ADI-2 Pro
    1: (0, 3, 2), 2: (0, 1, 0), 3: (0, 12, 0), 4: (0, 12, 0), 5: (0, 3, 0), 6: (0, 1, 0), 7: (0, 3, 2),
    8: (0, 1, 0), 9: (0, 1, 0), 10: (0, 3, 0),
}
INPUT_24_SE = {**INPUT, 1: (0, 4, 2), 10: (0, 1, 0), 11: (0, 5, 0), 12: (0, 1, 0)}
INPUT_24_EX = {**INPUT_24_SE, 1: (-6, 4, 2), 10: (0, 2, 0), 11: (0, 6, 0), 13: (0, 1, 0)}

# address 12; the Remap Keys 1 .. 7 are indices 26, 27, 28, 29, 22, 23, 24
PRO_DEVICE = {
    2: (0, 4, 0), 3: (0, 1, 1), 4: (0, 1, 0), 5: (0, 1, 0), 6: (0, 5, 0), 7: (0, 1, 0), 8: (0, 1, 0),
    9: (0, 2, 0), 10: (0, 5, 0), 11: (0, 1, 1), 12: (0, 1, 1), 15: (0, 3, 0),
    22: (0, 61, 48), 23: (0, 61, 49), 24: (0, 61, 51), 25: (0, 2, 2),
    26: (0, 61, 50), 27: (0, 61, 47), 28: (0, 61, 52), 29: (0, 61, 41),
    32: (0, 1, 0), 33: (0, 5, 0), 34: (0, 3, 0), 35: (0, 1, 0), 36: (0, 1, 1), 37: (0, 3, 0),
    40: (0, 2, 0), 41: (0, 2, 2), 42: (0, 1, 0), 43: (0, 2, 0),
}
PRO_24_DEVICE = {i: r for i, r in PRO_DEVICE.items() if i != 5}             # no DSD Direct
PRO_24_DEVICE.update({22: (0, 65, 49), 23: (0, 65, 50), 24: (0, 65, 52),
                      26: (0, 65, 51), 27: (0, 65, 48), 28: (0, 65, 53), 29: (0, 65, 42)})
# in a dump, not set by the simulator: Sample Rate (48 kHz) and Load Volume
DEVICE_REPORTED = {16: 1, 62: 0}
SETUP_NAMES = ["Setup %d" % n for n in range(1, 10)]

# what the simulator holds for one model: per output address and for the input (address 0) and the device
# (address 12) {index: (min, max, factory value)}; the ADI-2 DAC FS has no factory values here, it starts from a
# real dump
Tables = namedtuple("Tables", "outputs input device")


def tables(model, revision):
    """The Tables of a model; revision tells the ADI-2/4 Pro SE (0) from the EX (1 and up)."""
    if model.id not in (models.PRO.id, models.PRO_24.id):
        outputs = {a: {i: r + (None,) for i, r in {**OUTPUT_RANGES, 2: REF_LEVEL_RANGE[a]}.items()}
                   for a in OUTPUT_ADDRESSES}
        return Tables(outputs, {}, {i: r + (None,) for i, r in DEVICE_RANGES.items()})
    pro = model.id == models.PRO.id
    ex = not pro and revision >= 1
    output, ref = (PRO_OUTPUT, PRO_REF_LEVEL) if pro else (PRO_24_OUTPUT, PRO_24_REF_LEVEL)
    if ex:
        output = {**output, 1: EX_SOURCE}
    outputs = {a: {**output, 2: ref["line" if a == 3 else "phones"]} for a in OUTPUT_ADDRESSES}
    if not pro:
        outputs[9].update(REAR_TRS_SOURCE)
    inputs = INPUT if pro else INPUT_24_EX if ex else INPUT_24_SE
    return Tables(outputs, inputs, PRO_DEVICE if pro else PRO_24_DEVICE)


def factory_layout(t):
    """The parameter messages of a dump, [[(address, index), ...] per message], for a model with factory values:
    in the order of a real dump of the ADI-2 DAC FS, 40 parameters a message. Per channel its settings, the bands
    left and right, Bass/Treble, Loudness; then the device; then Load B/T and EQ Preset Select of every channel."""
    keys = []
    channels = [(0, INPUT_EQ)] + [(o, EQ_PAIRS[o]) for o in OUTPUT_ADDRESSES]
    for o, (left, right) in channels:
        own = t.input if o == 0 else t.outputs[o]
        keys += [(o, i) for i in sorted(own) if i < 20]
        keys += [(x, i) for x in (left, right) for i in range(2, 20)]
        keys += [(left, i) for i in range(20, 27)]
        keys += [(o, i) for i in sorted(own) if i >= 20]
    keys += [(12, i) for i in sorted(set(t.device) | set(DEVICE_REPORTED))]
    keys += [(left, i) for _, (left, _) in channels for i in (27, 28)]
    return [keys[k:k + 40] for k in range(0, len(keys), 40)]


def factory_state(t):
    """What a dump of a factory-new device holds: the factory values of MIDITable_ADI-2 v1.2."""
    state = {}
    for o, (left, right) in [(0, INPUT_EQ)] + [(o, EQ_PAIRS[o]) for o in OUTPUT_ADDRESSES]:
        state.update({(o, i): r[2] for i, r in (t.input if o == 0 else t.outputs[o]).items()})
        for x in (left, right):
            state.update({(x, i): v for i, v in FACTORY_BANDS.items()})
            state[(x, 2)] = 0                    # EQ Enable
        state.update({(left, i): v for i, v in FACTORY_BT.items()})
        state.update({(left, 20): 1, (left, 27): 0, (left, 28): MANUAL})
    state.update({(12, i): r[2] for i, r in t.device.items()})
    state.update({(12, i): v for i, v in DEVICE_REPORTED.items()})
    return state

# EQ Preset Select values
MANUAL, TEMP, CLEAR = 0, 1, 22                   # 2..21 = Preset 1..20

BAND_INDICES = range(3, 20)                      # band types, gains, frequencies, Qs
BT_INDICES = range(21, 27)                       # Bass and Treble gain, frequency, Q
GAIN_INDICES = (4, 7, 10, 13, 17)

# EQ presets: a slot holds the left side on address 13 (index 3..19 and the
# Bass/Treble 21..26) and the right side on address 14 (3..19). The flag word is written on 13/2 and read
# back on 13/1: (slot - 1) << 4 | Dual EQ; an unused slot reads back with the four low bits set.
SLOT_KEYS = [(13, i) for i in list(BAND_INDICES) + list(BT_INDICES)] + [(14, i) for i in BAND_INDICES]
# answer to 03 0A+n: a used slot sends its name, then two parameter messages; an unused one its flag word,
# then its name
PRESET_FIRST, PRESET_SPACING = 0.045, 0.035
# switching Load B/T with Preset on switches B/T Enable off on Phones and IEM, not on Line Out
BT_OFF_WITH_LOAD_BT = (6, 9)

# status stream: first message 0.7 s after the first valid message, then every 1.02 s, 14 data bytes
# (status.py reads them)
STATUS_FIRST, STATUS_INTERVAL = 0.7, 1.02
ACTIVE_CODE = {3: 0, 6: 1, 9: 2}                 # output address -> the active output in the status message
SPDIF_FAMILY = {32000: 0, 44100: 1, 48000: 2}
SOURCE_AUTO, SOURCE_COAX, SOURCE_OPTICAL = 0, 1, 2   # out/1; 3..5 play USB
REC_INPUT = {4: "coax", 5: "optical"}            # USB (Rec coax), USB (Rec opt.): the SPDIF input recorded over USB
SOURCE_KEYS = [(3, 1), (6, 1), (9, 1), (12, 15)]
# Clock Source (12/15) for each source: coax and USB (Rec coax) 2, optical and USB (Rec opt.) 3, USB 1; Auto 1
# without a signal on SPDIF
CLOCK_SOURCE = {SOURCE_AUTO: 1, SOURCE_COAX: 2, SOURCE_OPTICAL: 3, 3: 1, 4: 2, 5: 3}
# a dump arrives over about 0.4 s: first message after 0.08 s, 15 messages up to 0.48 s
DUMP_FIRST, DUMP_SPACING = 0.08, 0.028


class SimulatedAdi2:
    """The device: parameter state, the rules that change it, and the messages it sends back."""

    def __init__(self, state, layout, names, clock=time.monotonic, slots=None, slot_layout=None, model=models.DAC,
                 revision=None):
        self.model = model                       # it answers only under its own device ID
        # the rules only the ADI-2 DAC FS is known to follow
        self.dac_fs = model.id not in (models.PRO.id, models.PRO_24.id)
        # the device revision in the status message: the D/A converter of the ADI-2 DAC FS (default the ES9028Q2M),
        # the ADI-2/4 Pro SE (0) or EX (1)
        self.revision = (2 if self.dac_fs else 0) if revision is None else revision
        self.tables = tables(model, self.revision)
        self.header = codec.header(model.id)
        self.state = dict(state)
        self.layout = layout                     # [[(address, index), ...] per 0x01 message] as in a real dump
        self.names = [self.header + list(m[5:]) for m in names]   # the 0x05 name messages of a real dump
        self.clock = clock
        self.outbox = []                         # messages waiting to be received by the remote
        self.unsimulated = []                    # anything outside the model
        self.received = []                       # every message the device got, for tests
        self.source_report = []                  # what a source choice in the message being written reports
        self.session = False                     # status and changes flow after the first valid message
        self.next_status = None
        # banks for EQ Preset Select, per left EQ address: {source: {(address, index): value}}. There is always a
        # Temp; what it holds is not in a dump: the simulator starts it as the live EQ when it is the source, else
        # as the state after power on
        self.banks = {l: {MANUAL: self._bands(l),
                          TEMP: self._bands(l) if self.state.get((l, 28)) == TEMP else self._factory(l)}
                      for l in LEFT_EQ}
        # the twenty preset slots, {1..20: {"used", "dual", "vals" {(13|14, index): value}, "name" 16 bytes}};
        # None when the simulator was started without them: then anything about presets is unsimulated
        self.slots = slots
        self.slot_layout = slot_layout           # [[(address, index), ...] per 0x01 message] of a used slot
        self.pending = {}                        # a transfer is held until the flag word commits it
        self.pending_names = {}                  # {slot: 16 bytes} from 0x06
        self.preset_answer_until = 0.0           # when the last 03 0A+n answer is complete
        # one signal path: the output with a plug is active, else Line Out (manual 12)
        self.active = 3
        self.lowered = set()                     # outputs whose Volume Dim moved down, active ever since
        # what the inputs receive (signal()): a rate in Hz or None per SPDIF input, the rate of USB set on the
        # computer, DSD over USB. The status message keeps the last rate seen on an SPDIF input.
        self.coax = self.optical = None
        self.seen = {"coax": None, "optical": None}
        self.arrived = {"coax": None, "optical": None}   # when a signal came, in calls of signal(): for Auto
        self.signals = 0
        self.usb_rate = SAMPLE_RATES[self.state.get((12, 16), 0)]
        self.usb_dsd = False
        self.lock = threading.Lock()
        self.powered = True

    @classmethod
    def from_dump(cls, path, presets=None, **kw):
        """Start from a real dump: its values, its message layout and its name messages. presets: a file with
        the real answers to 03 0A+n, one '=== slot n' block per slot."""
        msgs = codec.read_dump(path)
        state, layout, names = {}, [], []
        for m in msgs:
            if len(m) < 7 or list(m[:4]) != codec.PREFIX:
                continue
            if m[5] == 0x01:
                keys = []
                for t in codec.parameter_triplets([m]):
                    a, i, v, _ = codec.decode_triplet(*t)
                    state[(a, i)] = v
                    keys.append((a, i))
                layout.append(keys)
            elif m[5] == 0x05:
                names.append(list(m))
        if presets is not None:
            kw["slots"], kw["slot_layout"] = read_presets(presets)
        return cls(state, layout, names, **kw)

    @classmethod
    def factory(cls, model, revision=None, presets=None, **kw):
        """An ADI-2 Pro or ADI-2/4 Pro as it leaves the factory, its setups unnamed. presets: as for from_dump."""
        if model.id not in (models.PRO.id, models.PRO_24.id):
            raise ValueError("%s: no factory values; start from a dump" % model.name)
        t = tables(model, 0 if revision is None else revision)
        names = [codec.header(model.id) + [0x05, 0x21 + n] + list(name.rjust(14).encode("ascii")) + [0, 0, 0xF7]
                 for n, name in enumerate(SETUP_NAMES)]
        if presets is not None:
            kw["slots"], kw["slot_layout"] = read_presets(presets)
        return cls(factory_state(t), factory_layout(t), names, model=model, revision=revision, **kw)

    # -- helpers ------------------------------------------------------------------------------
    def _bands(self, left):
        """The bands of one output, left and right, with its Dual EQ state (a source carries it),
        and Bass/Treble, which a source carries only with Load B/T on."""
        out = LEFT_EQ[left]
        right = EQ_PAIRS[out][1]
        bank = {(a, i): self.state[(a, i)] for a in (left, right) for i in BAND_INDICES if (a, i) in self.state}
        bank.update({(left, i): self.state[(left, i)] for i in BT_INDICES if (left, i) in self.state})
        bank[(out, 11)] = self.state.get((out, 11), 1)
        return bank

    def _factory(self, left):
        """Temp after power on: flat, Dual EQ off, factory Bass/Treble."""
        out = LEFT_EQ[left]
        right = EQ_PAIRS[out][1]
        bank = {(x, i): w for x in (left, right) for i, w in FACTORY_BANDS.items() if (x, i) in self.state}
        bank[(out, 11)] = 0
        bank.update({(left, i): w for i, w in FACTORY_BT.items()})
        return bank

    def _capture(self, left, source, bt=False):
        """Store the live EQ in the bank of a source. A source keeps its own Bass/Treble: it changes
        only when Bass/Treble is edited with Load B/T on (bt=True). Leaving Manual with other Bass/Treble live,
        set while Load B/T was off, brings Manual's own back."""
        bank = self._bands(left)
        if not bt:
            old = self.banks[left].get(source, {})
            for i in BT_INDICES:
                bank.pop((left, i), None)
                if (left, i) in old:
                    bank[(left, i)] = old[(left, i)]
        self.banks[left][source] = bank

    def _apply(self, left, bank):
        """Load a source into the live EQ; Bass/Treble only with Load B/T on."""
        load_bt = self.state.get((left, 27)) == 1
        self.state.update({k: v for k, v in bank.items() if not (k[0] == left and k[1] in BT_INDICES) or load_bt})

    def _ref_step(self):
        """Auto Ref Level is modelled on the ADI-2 DAC FS only."""
        return REF_STEP if self.dac_fs else {}

    def _dac_mode(self):
        """ADI-2 Pro and ADI-2/4 Pro in Basic Mode DAC: Source has its seven choices."""
        return not self.dac_fs and self.state.get((12, BASIC_MODE)) == BASIC_MODE_DAC

    def _dual(self, left):
        return self.state.get((LEFT_EQ[left], 11), 1) == 1

    def _note(self, what):
        self.unsimulated.append(what)

    def _emit(self, msg, due=None):
        self.outbox.append((self.clock() if due is None else due, list(msg)))

    def _said(self, triplets):
        """A parameter message from the device (0x01)."""
        return codec.sysex(self.model.id, triplets, 0x01)

    # -- incoming -----------------------------------------------------------------------------
    def receive_from_remote(self, msg):
        """One SysEx message from the remote."""
        with self.lock:
            if not self.powered:
                return                                              # the simulator drops it
            now = self.clock()
            self.received.append(list(msg))
            if len(msg) < 7 or list(msg[:5]) != self.header or msg[-1] != 0xF7:
                return                                              # not for us: ignored
            if not self.session:
                self.session = True
                self.next_status = now + STATUS_FIRST
            if len(msg) > 256:
                self._note("message of %d bytes (limit 256)" % len(msg))
                return
            cmd = msg[5]
            if cmd == 0x01:
                return                                              # ignored without a sign
            if cmd == 0x02:
                self._write(msg)
                return
            if cmd == 0x03 and msg[6:] == [0x09, 0xF7]:
                self._dump()
                return
            if cmd == 0x03 and len(msg) == 8 and 0x0A <= msg[6] <= 0x1D:
                self._answer_preset(msg[6] - 0x09)
                return
            if cmd == 0x06 and 1 <= msg[6] <= 20 and self.slots is not None:
                name = list(msg[7:-1])
                if len(name) != 16:
                    self._note("preset name of %d bytes (the device sends 16)" % len(name))
                    return
                self.pending_names[msg[6]] = name[:15] + [0]       # up to 15 signs, the 16th is the null
                return
            self._note("command %02x %s" % (cmd, codec.to_hex(msg[6:])))

    def _write(self, msg):
        """Apply a 0x02 message. No reply; what a source choice set besides what was written, the device reports
        unsolicited, in one message, nothing when nothing changed."""
        self.source_report = []
        before = {k: self.state.get(k) for k in SOURCE_KEYS}
        written = set()
        for t in codec.parameter_triplets([msg]):
            a, i, v, is_freq = codec.decode_triplet(*t)
            written.add((a, i))
            self._set(a, i, v, is_freq)
        changed = [k for k in self.source_report if k not in written and self.state.get(k) != before[k]]
        if self.session and changed:
            self._emit(self._said([codec.encode(a, i, self.state[(a, i)]) for a, i in changed]))

    def front_panel(self, changes):
        """Changes made on the device itself, one knob step each: [(address, index, value)]. Applied by the
        same rules. Every step arrives at once as an unsolicited 0x01 message holding that one
        parameter; nothing else comes along."""
        with self.lock:
            for a, i, v in changes:
                is_freq = a in codec.EQ_ADDRESSES and i in codec.FREQ_INDICES
                before = self.state.get((a, i))
                self._set(a, i, v, is_freq)
                if self.session and self.state.get((a, i)) != before:
                    self._emit(self._said([codec.encode(a, i, self.state[(a, i)], is_freq)]))

    # -- the rules ----------------------------------------------------------------------------
    def _set(self, a, i, v, is_freq):
        """Set one parameter as the device would."""
        if a in LEFT_EQ or a in RIGHT_EQ:
            self._set_eq(a, i, v, is_freq)
        elif a in OUTPUT_ADDRESSES:
            self._set_output(a, i, v)
        elif a == 12:
            if i in DEVICE_READ_ONLY:
                return
            if i not in self.tables.device:
                self._note("device index %d" % i)
                return
            self.state[(12, i)] = _clamp(v, self.tables.device[i])
        elif a in (13, 14):
            self._set_slot(a, i, v, is_freq)
        elif a == 0 and i in self.tables.input:
            self.state[(0, i)] = _clamp(v, self.tables.input[i])
        elif a in INPUT_EQ and self.tables.input:
            self._note("input EQ address %d index %d" % (a, i))
        else:
            self._note("address %d index %d" % (a, i))

    # -- presets ------------------------------------------------------------------------------
    def _set_slot(self, a, i, v, is_freq):
        """Part of a preset transfer."""
        if self.slots is None:
            self._note("preset address %d index %d: started without preset slots" % (a, i))
            return
        if (a, i) == (13, 1):
            return                                                  # the read-back index: nothing happens
        if (a, i) == (13, 2):
            self._commit(v)
            return
        if (a, i) not in SLOT_KEYS:
            self._note("preset address %d index %d" % (a, i))
            return
        if is_freq and 2040 < v <= 2047:
            v = 2040
        if v != _clamp(v, EQ_RANGES[i]):
            # a slot keeps most values outside the range as they are and mangles some; not modelled
            self._note("preset address %d index %d: %d outside the range" % (a, i, v))
        self.pending[(a, i)] = v

    def _commit(self, flag):
        """The flag word commits the transfer to slot (flag >> 4) + 1, Dual EQ from bit 0. The name
        comes from a 0x06 for that slot in the same transfer; without one the name is empty."""
        slot, pending = (flag >> 4) + 1, self.pending
        self.pending = {}
        if not 1 <= slot <= 20:
            self._note("preset flag word %d: slot %d" % (flag, slot))
            return
        if set(pending) != set(SLOT_KEYS):
            # a partial transfer is not modelled
            self._note("preset flag word for slot %d without a complete transfer" % slot)
            return
        self.slots[slot] = {"used": True, "dual": flag & 1, "vals": pending,
                            "name": self.pending_names.pop(slot, [0] * 16)}
        # the active output follows a slot it has as source; the others keep their copy, also when
        # they become active later. A source of Temp stays Temp.
        left = EQ_PAIRS[self.active][0]
        if self.state.get((left, 28)) == slot + 1:
            before = self.reported()
            self._apply(left, self._slot_bank(left, slot))
            changed = self._auto_ref_level(self.active)
            self._report_changes(before, also=[(self.active, 12)] if changed else [])

    def _slot_bank(self, left, slot):
        """A slot as a bank for one output."""
        out = LEFT_EQ[left]
        right = EQ_PAIRS[out][1]
        s = self.slots[slot]
        bank = {(left if a == 13 else right, i): v for (a, i), v in s["vals"].items()}
        bank[(out, 11)] = s["dual"]
        return bank

    def _answer_preset(self, slot):
        """The answer to 03 0A+n."""
        if self.slots is None:
            self._note("03 0A+n: started without preset slots")
            return
        now = self.clock()
        if now < self.preset_answer_until:
            # asked again before the answer is complete: parameter messages get lost or mixed up
            self._note("03 0A+n for slot %d while the previous answer is still coming" % slot)
        s = self.slots[slot]
        name = self.header + [0x05, slot] + list(s["name"]) + [0xF7]
        if s["used"]:
            vals = dict(s["vals"])
            vals[(13, 1)] = (slot - 1) << 4 | s["dual"]
            params = [self._said([codec.encode(a, i, vals[(a, i)], i in codec.FREQ_INDICES) for a, i in keys])
                      for keys in self.slot_layout]
            msgs = [name] + params
        else:
            flag = self._said([codec.encode(13, 1, (slot - 1) << 4 | 0x0F)])
            msgs = [flag, name]
        t = now + PRESET_FIRST
        for j, m in enumerate(msgs):
            self._emit(m, due=t + j * PRESET_SPACING)
        self.preset_answer_until = t + (len(msgs) - 1) * PRESET_SPACING

    def _report_changes(self, before, skip=(), also=()):
        """The device reports what it changed on its own as one unsolicited 0x01 message, nothing when nothing
        changed: after a source choice (not EQ Preset Select itself; the right EQ as reported), and when the
        active output followed a rewritten slot. Dual EQ first, then by index and address (beyond Dual EQ, bands
        and Bass/Treble the simulator's order). also: reported even unchanged (Volume beside a Ref Level that Auto
        Ref Level moved; after Manual the device puts both last)."""
        after = self.reported()
        changed = sorted((k for k in after if (after[k] != before.get(k) or k in also) and k not in skip),
                         key=lambda k: (k[0] not in OUTPUT_ADDRESSES, k[1], k[0]))
        if self.session and changed:
            self._emit(self._said([codec.encode(a, i, after[(a, i)], a in codec.EQ_ADDRESSES and i in codec.FREQ_INDICES)
                                    for a, i in changed]))

    def _set_eq(self, a, i, v, is_freq):
        written = a
        if i not in EQ_RANGES:
            self._note("EQ address %d index %d" % (a, i))
            return
        if a in RIGHT_EQ:
            left = RIGHT_EQ[a]
            if i > 19:
                a = left                                            # address 5 index > 19 hits the shared B/T
            elif not self._dual(left):
                a = left                                            # with Dual EQ off, right is an alias of left
        left = a if a in LEFT_EQ else RIGHT_EQ[a]
        if (a, i) not in self.state:
            self._note("EQ address %d index %d not in the dump" % (a, i))
            return
        if is_freq and 2040 < v <= 2047:
            v = 2040                                                # 2041..2047 without the x10 flag
        v = _clamp(v, EQ_RANGES[i])
        # EQ Enable on a right address can be written and is read back (Dual EQ on); it takes the
        # right PEQ out of the path, the left address the left one: the front panel's ON/OFF/L/R
        if i == 28:
            self._select_source(left, v)
            return
        if i == 27:
            self._set_load_bt(left, v)
            return
        before = self.state[(a, i)]
        self.state[(a, i)] = v
        # the source changes with a band, and with Bass/Treble only when Load B/T is on; EQ Enable,
        # B/T Enable and a value that was already there leave it
        if v != before and (i in BAND_INDICES or (i in BT_INDICES and self.state.get((left, 27)) == 1)):
            self._source_edited(left, (written, i))
        if (i in BAND_INDICES or i in (2, 20, 21, 22, 24, 25)) and LEFT_EQ[left] == self.active:
            # also when a band frequency moves, and EQ Enable and B/T Enable, which decide what counts; a band of an
            # output that is not active does not start it
            self._follow_ref_level(LEFT_EQ[left], volume=True)

    def _source_edited(self, left, key=None):
        """Editing a loaded preset or 'clear' makes the source Temp, and the device says so itself.
        With Dual EQ off: first the value on the other address than the one written (written right, reported
        left; written left, reported right), then EQ Preset Select = Temp, as two 0x01 messages. With Dual EQ
        on only the second. Manual and Temp keep their own bank."""
        source = self.state.get((left, 28), MANUAL)
        new_temp = source not in (MANUAL, TEMP)
        if new_temp:
            self.state[(left, 28)] = TEMP
            if self.session:
                if key is not None and key[1] in BAND_INDICES and not self._dual(left):
                    a, i = key
                    other = EQ_PAIRS[LEFT_EQ[left]][1] if a == left else left
                    self._emit(self._said([codec.encode(other, i, self.state[(left, i)], i in codec.FREQ_INDICES)]))
                self._emit(self._said([codec.encode(left, 28, TEMP)]))
        # a new Temp takes the Bass/Treble of the preset it came from
        self._capture(left, self.state[(left, 28)], bt=new_temp or (key is not None and key[1] in BT_INDICES))

    def _set_load_bt(self, left, v):
        """Switching Load B/T with Preset on switches B/T Enable off, on Phones and IEM only."""
        was = self.state.get((left, 27), 0)
        self.state[(left, 27)] = v
        if (was == 0 and v == 1 and self.dac_fs and LEFT_EQ[left] in BT_OFF_WITH_LOAD_BT
                and self.state.get((left, 20)) != 0):
            self.state[(left, 20)] = 0
            if self.session:
                self._emit(self._said([codec.encode(left, 20, 0)]))   # said unasked

    def _select_source(self, left, v):
        """EQ Preset Select: which bank drives the live bands."""
        if self.state.get((left, 28), MANUAL) == MANUAL:
            self._capture(left, MANUAL)
        if v == MANUAL or v == TEMP:
            bands = self.banks[left][v]                              # Manual survives switching
        elif v == CLEAR:
            right = EQ_PAIRS[LEFT_EQ[left]][1]
            bands = {(x, i): w for x in (left, right) for i, w in FACTORY_BANDS.items() if (x, i) in self.state}
            bands[(LEFT_EQ[left], 11)] = 0
            if self.state.get((left, 27)) == 1:
                # with Load B/T on, clear loads the factory Bass/Treble and switches B/T Enable on;
                # with Load B/T off it leaves both
                bands.update({(left, i): w for i, w in FACTORY_BT.items()})
                bands[(left, 20)] = 1
        else:
            slot = v - 1
            if self.slots is None:
                self._note("EQ Preset Select %d: started without preset slots" % v)
                return
            if self.slots[slot]["used"]:
                bands = self._slot_bank(left, slot)                  # the same slot again reloads it
            else:
                # an unused slot loads like 'clear' (with Load B/T on too) and stays unused
                right = EQ_PAIRS[LEFT_EQ[left]][1]
                bands = {(x, i): w for x in (left, right) for i, w in FACTORY_BANDS.items() if (x, i) in self.state}
                bands[(LEFT_EQ[left], 11)] = 0
                if self.state.get((left, 27)) == 1:
                    bands.update({(left, i): w for i, w in FACTORY_BT.items()})
                    bands[(left, 20)] = 1
        before = self.reported()
        self._apply(left, bands)                                    # Dual EQ comes with the source
        self.state[(left, 28)] = v
        out = LEFT_EQ[left]
        changed = out == self.active and self._auto_ref_level(out)
        self._report_changes(before, skip={(left, 28)}, also=[(out, 12)] if changed else [])   # every source choice

    def _set_output(self, a, i, v):
        if i in (2, 3) and self.state.get((a, i)) == -1:
            return                                   # IEM: no Ref Level, no Auto Ref Level; a write does nothing
        ranges = self.tables.outputs[a]
        if i == 2:
            self._set_ref_level(a, _clamp(v, ranges[2]))
            return
        if i not in ranges:
            self._note("output address %d index %d" % (a, i))
            return
        if i == 12 and self.state.get((a, 13)) == 1:
            # Lock Volume on: refused, and the device reports the volume it keeps
            if self.session:
                self._emit(self._said([codec.encode(a, 12, self.state[(a, 12)])]))
            return
        v = _clamp(v, SOURCE_IN_DAC_MODE if i == 1 and self._dac_mode() else ranges[i])
        if i == 16:
            # Dim: on the active output, on moves Volume itself 20 dB down, unclamped, and says so; off moves it back
            # up only if Dim moved it down and the output stayed active since. Otherwise only the flag. Ref Level stays.
            if v != self.state.get((a, 16)):
                self.state[(a, 16)] = v
                move = -200 if v and a == self.active else 200 if not v and a in self.lowered else 0
                (self.lowered.add if v and move else self.lowered.discard)(a)
                if move:
                    self.state[(a, 12)] += move
                    if self.session:
                        self._emit(self._said([codec.encode(a, 12, self.state[(a, 12)])]))
            return
        if i == 12 and self.state.get((a, 16)) == 1:
            self.state[(a, 16)] = 0                  # a Volume write turns Dim off and sets the value written
            self.lowered.discard(a)
            if self.session:
                self._emit(self._said([codec.encode(a, 16, 0)]))
        if i == 11:
            self._set_dual(a, v)
            return
        if i == 1 and self.dac_fs:
            self._set_source(a, v)
            return
        if i == 3:
            self._set_auto_ref_level(a, v)
            return
        self.state[(a, i)] = v
        if i == 12:
            self._follow_ref_level(a)

    def _set_auto_ref_level(self, a, v):
        """Switching Auto Ref Level keeps the level: on, Volume is relative to the highest Ref Level (dBr); off, to
        the Ref Level that is set, which stays. The device reports the new Volume."""
        if v != self.state.get((a, 3)) and a in self._ref_step():
            shift = (self.tables.outputs[a][2][1] - self.state[(a, 2)]) * REF_STEP[a]
            self._report_volume(a, self.state[(a, 12)] + (-shift if v else shift))
        self.state[(a, 3)] = v
        self._follow_ref_level(a)

    def _report_volume(self, a, vol):
        vol = _clamp(vol, self.tables.outputs[a][12])
        if vol != self.state[(a, 12)]:
            self.state[(a, 12)] = vol
            if self.session:
                self._emit(self._said([codec.encode(a, 12, vol)]))

    def _set_source(self, a, v):
        """Source is one setting of the whole device: written on one output it is set on all three, and Clock Source
        (12/15) follows it. The device reports the other outputs, from the one written on, and Clock Source."""
        k = OUTPUT_ADDRESSES.index(a)
        self.source_report = [(o, 1) for o in OUTPUT_ADDRESSES[k + 1:] + OUTPUT_ADDRESSES[:k]] + [(12, 15)]
        for o in OUTPUT_ADDRESSES:
            self.state[(o, 1)] = v
        if v == SOURCE_AUTO and (self.coax or self.optical):
            self._note("Clock Source with source Auto and a signal on SPDIF")
        else:
            self.state[(12, 15)] = CLOCK_SOURCE[v]
        self._follow_rate()                      # another source can bring another clock

    def _set_dual(self, a, v):
        left, right = EQ_PAIRS[a]
        was = self.state.get((a, 11), 1)
        self.state[(a, 11)] = v
        if was == 0 and v == 1:
            for i in range(2, 20):                                  # switching on copies left to right
                if (right, i) in self.state:
                    self.state[(right, i)] = self.state[(left, i)]
        if v != was:
            self._source_edited(left)                               # on a preset: Temp

    def _set_ref_level(self, a, v):
        old = self.state.get((a, 2), v)
        if a in self._ref_step() and self.state.get((a, 3)) == 1 and v != old:
            # with Auto Ref Level on, writing Ref Level moves Volume a step's worth, both directions, unreported
            vol = self.state[(a, 12)] + REF_STEP[a] * (v - old)
            self.state[(a, 12)] = _clamp(vol, self.tables.outputs[a][12])
        self.state[(a, 2)] = v

    def _auto_ref_level(self, a):
        """With Auto Ref Level on, the device picks Ref Level from Volume plus the positive gain at the low or the
        high end, whichever is more, per channel; True when it moved. Line Out: 0 up to -18 dB, 1 up to -12 dB, 2 up
        to -6 dB, else 3. Phones: Lo-Power up to -15 dB, else Hi-Power. Counted: a band below 400 Hz (390 counts,
        400 not) or from 5000 Hz (4000 not), peak and shelf alike, while the EQ of its channel is on; Bass and
        Treble by the same rule on their frequency, while B/T Enable is on, the EQ on or off. At either end the
        positive gains add up: a band and Bass together, measured; two bands together, assumed. Between 4000 and
        5000 Hz it is not modelled. A Volume write and switching Auto Ref Level on start it on any output; a band,
        Bass/Treble, EQ Enable or B/T Enable change and a source choice only on the active output, and an output
        becoming active starts it there; one becoming inactive keeps its Ref Level."""
        if a not in self._ref_step() or self.state.get((a, 3)) != 1:
            return False
        left, right = EQ_PAIRS[a]

        def ends(pairs):
            low = high = 0
            for gain, freq in pairs:
                if gain <= 0:
                    continue
                if 4000 < freq < 5000:
                    self._note("Auto Ref Level with +gain at %d Hz, between 4000 and 5000 Hz" % freq)
                if freq < 400:
                    low += gain
                elif freq >= 5000:
                    high += gain
            return low, high

        tone = [(self.state.get((left, g), 0), self.state.get((left, g + 1), 0)) for g in (21, 24)
                if self.state.get((left, 20)) == 1]
        gain = 0
        for x in [left] + ([right] if self._dual(left) else []):    # Dual EQ off: right is the left
            bands = [(self.state.get((x, g), 0), self.state.get((x, g + 1), 0)) for g in GAIN_INDICES
                     if self.state.get((x, 2)) == 1]
            gain = max([gain, *ends(bands + tone)])
        level = self.state[(a, 12)] / 10 + gain / 2
        if a == 3:
            ref = 0 if level <= -18 else 1 if level <= -12 else 2 if level <= -6 else 3
        else:
            ref = 0 if level <= -15 else 1
        if ref == self.state.get((a, 2)):
            return False
        self.state[(a, 2)] = ref
        return True

    def _follow_ref_level(self, a, volume=False):
        """Auto Ref Level, reported: Ref Level on its own after a Volume write, with Volume after a band change or
        when the output becomes active."""
        if self._auto_ref_level(a) and self.session:
            self._emit(self._said([codec.encode(a, i, self.state[(a, i)]) for i in ((2, 12) if volume else (2,))]))

    # -- outgoing -----------------------------------------------------------------------------
    def reported(self):
        """The state as a dump reports it: with Dual EQ off, the right EQ shows the left values."""
        out = dict(self.state)
        for o, (left, right) in EQ_PAIRS.items():
            if self.state.get((o, 11), 1) == 0:
                for i in range(2, 20):
                    if (right, i) in out:
                        out[(right, i)] = self.state[(left, i)]
        return out

    def _dump(self):
        """The answer to 03 09: parameter messages in the layout of a real dump, then the
        setup names; the last one (05 29) marks the end."""
        rep = self.reported()
        msgs = []
        for keys in self.layout:
            triplets = [codec.encode(a, i, rep[(a, i)], a in codec.EQ_ADDRESSES and i in codec.FREQ_INDICES)
                        for a, i in keys]
            msgs.append(self._said(triplets))
        t = self.clock() + DUMP_FIRST
        for j, m in enumerate(msgs + self.names):
            self._emit(m, due=t + j * DUMP_SPACING)

    def poll(self):
        """Messages for the remote, the status stream included."""
        with self.lock:
            if not self.powered:
                return []
            now = self.clock()
            while self.session and self.next_status is not None and now >= self.next_status:
                # collected or not
                self._emit(self.header + [0x07] + self._status_body() + [0xF7], due=self.next_status)
                self.next_status += STATUS_INTERVAL
            self.outbox.sort(key=lambda e: e[0])
            out = [m for due, m in self.outbox if due <= now]
            self.outbox = [(due, m) for due, m in self.outbox if due > now]
            return out


    def power(self, on):
        """In standby the MIDI port disappears; a new session starts when it is back.
        Standby and power loss keep per output only what sounds: it becomes Manual (Dual EQ and,
        with Load B/T on, Bass/Treble included), a source of Temp becomes Manual, a preset or 'clear' stays the
        source, and Temp is the factory state: flat, Dual EQ off, factory Bass/Treble."""
        with self.lock:
            if self.powered and not on:
                for left in LEFT_EQ:
                    # with Load B/T off, the simulator lets Manual keep its own Bass/Treble
                    self._capture(left, MANUAL, bt=self.state.get((left, 27)) == 1)
                    self.banks[left][TEMP] = self._factory(left)
                    if self.state.get((left, 28)) == TEMP:
                        self.state[(left, 28)] = MANUAL
                self.pending, self.pending_names = {}, {}           # the simulator drops an unfinished transfer
            self.powered = on
            if on:
                self.session = False
                self.next_status = None
                self.outbox = []

    def plug(self, output=None):
        """A plug in Phones (6) or IEM (9), or none: Line Out (3) is active. Becoming active does not
        reload anything; Auto Ref Level of the output that became active follows its band gain then."""
        with self.lock:
            if not self.dac_fs:
                self._note("plug: the outputs of the %s" % self.model.name)
                return
            was, self.active = self.active, 3 if output is None else output
            if self.active != was:
                self.lowered.discard(was)            # what Dim moved down there, stays down
                self._follow_ref_level(self.active, volume=True)

    def signal(self, coax=None, optical=None, usb=None, dsd=False):
        """What the inputs receive: coax and optical a rate in Hz or None for no signal; usb the rate set on the
        computer (None: as it was); dsd: DSD over USB. A chosen SPDIF input with a signal clocks the device, and
        in the simulator so does the one USB (Rec …) records; otherwise it runs on its own clock at the rate of USB.
        A new rate is reported as 12/16."""
        with self.lock:
            if not self.dac_fs:
                self._note("signal: the inputs of the %s" % self.model.name)
                return
            self.signals += 1
            for name, rate in (("coax", coax), ("optical", optical)):
                if rate is None:
                    self.arrived[name] = None
                elif getattr(self, name) is None:
                    self.arrived[name] = self.signals
            self.coax, self.optical, self.usb_dsd = coax, optical, dsd
            self.usb_rate = self.usb_rate if usb is None else usb
            for name, rate in (("coax", coax), ("optical", optical)):
                if rate is not None:
                    self.seen[name] = rate
            self._follow_rate()

    # -- the status message ------------------------------------------------------------------
    def _clock(self):
        """The SPDIF input the device follows, "coax" or "optical", or None: its own clock. The ADI-2 Pro and
        ADI-2/4 Pro run on their own clock, at the rate of USB."""
        if not self.dac_fs:
            return None
        source = self.state.get((3, 1), SOURCE_AUTO)
        if source == SOURCE_COAX and self.coax:
            return "coax"
        if source == SOURCE_OPTICAL and self.optical:
            return "optical"
        if source in REC_INPUT and getattr(self, REC_INPUT[source]):
            return REC_INPUT[source]             # the simulator lets the recorded input clock the device (manual 12.1)
        if source == SOURCE_AUTO:
            # SPDIF has priority over USB (manual 12.1, 18). Of the two, the simulator takes the first signal after
            # silence and keeps it as long as it lasts
            present = sorted((self.arrived[n], n) for n in ("coax", "optical") if getattr(self, n))
            if len(present) == 2 and present[0][0] == present[1][0]:
                what = "source Auto: a signal on coax and optical at once"
                if what not in self.unsimulated:
                    self._note(what)
            return present[0][1] if present else None
        return None

    def _rate(self):
        clock = self._clock()
        return self.usb_rate if clock is None else getattr(self, clock)

    def _follow_rate(self):
        """Sample Rate (12/16) follows the rate the device runs at, and says so unsolicited."""
        index = SAMPLE_RATES.index(self._rate())
        if self.state.get((12, 16)) != index:
            self.state[(12, 16)] = index
            if self.session:
                self._emit(self._said([codec.encode(12, 16, index)]))

    def _status_body(self):
        """The 14 data bytes of a status message, from the model. Bits that carry nothing a remote needs
        (bit depth, channel status, the bit test, overload) stay 0."""
        if not self.dac_fs:
            return self._own_status_body()
        clock, rate = self._clock(), self._rate()
        base = _family(rate)[0]
        coax, optical = self.seen["coax"], self.seen["optical"]
        coax_code = 0x0F if coax is None else SPDIF_FAMILY[_family(coax)[0]] | _family(coax)[1] << 2
        optical_family, optical_n = (3, 0) if optical is None else (SPDIF_FAMILY[_family(optical)[0]],
                                                                    _family(optical)[1])
        d1 = (0x10 | (self.coax is not None) | (self.optical is not None) << 1 | (self.coax == rate) << 2
              | (self.optical == rate) << 3 | (coax is None and optical is None) << 5 | (clock == "coax") << 6)
        d2 = (clock == "optical") | coax_code << 1 | optical_family << 5
        d3 = SAMPLE_RATES.index(rate) << 3 | (base == 44100) << 2 | optical_n
        d4 = (self.active == 6) | (self.active == 9) << 6
        # USB and USB (Rec …) play USB, and Auto without a signal on SPDIF
        source = self.state.get((3, 1), SOURCE_AUTO)
        usb_played = source not in (SOURCE_COAX, SOURCE_OPTICAL) and not (source == SOURCE_AUTO and clock)
        usb_base, usb_n = _family(self.usb_rate)
        return [self.revision << 2 | ACTIVE_CODE[self.active], d1, d2, d3, d4, 0x0C if self.usb_dsd else 0, 0,
                0x40 | SPDIF_FAMILY[base], 0, 0x70 if self.usb_dsd and usb_played else 0, 0x02,
                SPDIF_FAMILY[usb_base] | usb_n << 2, 0, 0]

    def _own_status_body(self):
        """ADI-2 Pro and ADI-2/4 Pro: the status message as the table describes it, in the layout of the ADI-2 DAC FS:
        14 data bytes. No signal on any input, no plug, the internal clock at the rate of USB."""
        rate = self._rate()
        d2 = 0x0F << 1 | 0x03 << 5                    # AES and SPDIF: no rate
        d3 = SAMPLE_RATES.index(rate) << 3 | (_family(rate)[0] == 44100) << 2 | 0x03
        return [self.revision << 2, 0, d2, d3, 0, 0, 0, 0, 0, 0, 0x02, 0, 0, 0]


def _clamp(v, rng):
    return min(max(v, rng[0]), rng[1])


def _family(rate):
    """(base, n): a rate is its base rate (32, 44.1 or 48 kHz) doubled n times."""
    for base in SPDIF_FAMILY:
        n = 0
        while base << n < rate:
            n += 1
        if base << n == rate:
            return base, n
    raise ValueError("rate %s" % rate)


def read_presets(path):
    """The twenty slots from a file of real 03 0A+n answers ('=== slot n', then the messages in hex).
    Returns (slots, the parameter message layout of a used slot)."""
    blocks, n = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("=== slot"):
                n = int(line.split()[-1])
                blocks[n] = []
            elif n is not None and line and not line.startswith("#"):
                blocks[n].append([int(x, 16) for x in line.split()])
    slots, layout = {}, None
    for n in range(1, 21):
        msgs = blocks[n]
        vals, keys = {}, []
        for m in msgs:
            if m[5] == 0x01:
                keys.append([codec.decode_triplet(*t)[:2] for t in codec.parameter_triplets([m])])
                for t in codec.parameter_triplets([m]):
                    a, i, v, _ = codec.decode_triplet(*t)
                    vals[(a, i)] = v
        name = [m for m in msgs if m[5] == 0x05][0][7:-1]
        flag = vals.pop((13, 1))
        used = flag & 0x0F != 0x0F
        if used and layout is None:
            layout = keys
        slots[n] = {"used": used, "dual": flag & 1 if used else 0, "vals": vals if used else {}, "name": name}
    return slots, layout


class SimPort:
    """Stands in for WinmmPort. present=False behaves like a device that is off; busy=True like a port
    held by another program."""

    def __init__(self, device, present=True, busy=False):
        if not present or not device.powered:
            raise DeviceNotFound("no ADI-2 MIDI port found (simulated: device off)")
        if busy:
            raise PortBusy("midiInOpen: the ADI-2 MIDI port is in use by another program (simulated)")
        self.device = device
        self.names = ("%s Midi Port 1 (simulated)" % device.model.port,) * 2
        self.open = True

    def send(self, msg):
        if not self.open:
            raise OSError("port closed")
        self.device.receive_from_remote(list(msg))

    def receive(self):
        return self.device.poll() if self.open else []

    def present(self):
        return self.device.powered                   # the port leaves the list at once in standby

    def close(self):
        self.open = False
