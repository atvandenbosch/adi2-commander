"""The EQ parameters of an ADI-2 DAC FS: addresses, ranges, grid and steps, in device increments and in
units. No I/O.

Increments: gain x2 (0.5 dB), Q x10 (0.1), frequency in Hz. The device clamps silently to exactly the limits
below.
"""

import math
import re

# (name, output address, left EQ address, right EQ address)
OUTPUTS = [("Line Out", 3, 4, 5), ("Phones 1/2", 6, 7, 8), ("Phones 3/4 · IEM", 9, 10, 11)]

# per band: (type index or None, gain index, freq index, Q index)
BANDS = {1: (3, 4, 5, 6), 2: (None, 7, 8, 9), 3: (None, 10, 11, 12), 4: (None, 13, 14, 15), 5: (16, 17, 18, 19)}
BAND_TYPES = {1: ["Peak", "Shelf", "High Pass", "High Cut"], 5: ["Peak", "Shelf", "High Cut"]}   # device names
# the usual abbreviations (REW, Equalizer APO); the shelf of band 1 is a low shelf, of band 5 a high shelf
TYPE_ABBR = {1: ["PK", "LS", "HP", "LP"], 5: ["PK", "HS", "LP"]}
TYPE_LONG = {1: ["Peak", "Low Shelf", "High Pass", "High Cut (low pass)"],
             5: ["Peak", "High Shelf", "High Cut (low pass)"]}
NO_GAIN_TYPES = {1: (2, 3), 5: (2,)}            # High Pass / High Cut: gain does nothing

# Bass/Treble: shared, on the left EQ address only
BT_ENABLE = 20
BASS = (21, 22, 23)                              # gain, freq, Q
TREBLE = (24, 25, 26)

EQ_ENABLE, EQ_PRESET_SELECT = 2, 28
LOAD_BT = 27                                     # Load B/T with Preset: a preset brings its Bass/Treble too
DUAL_EQ = 11                                     # on the output address
INPUT_EQ = (1, 2)                                # ADI-2 Pro and ADI-2/4 Pro: the EQ of the input, left and right
INPUT_DUAL_EQ = (0, 8)                           # and its Dual EQ
AUTO_REF_LEVEL = 3                               # on the output address; Line Out and Phones
VOLUME = 12                                      # on the output address, in 0.1 dB
SOURCE = 1                                       # on the output address: the input, in the device's own names
INPUTS = ["Auto", "SPDIF coax", "Optical", "USB", "USB (Rec coax)", "USB (Rec opt.)"]

# the other settings of an output, on its address. IEM has no Ref Level and no Auto Ref Level: both report -1
REF_LEVEL, MONO, WIDTH, MS_PROC, POLARITY, CROSSFEED, DA_FILTER, DE_EMPHASIS = 2, 4, 5, 6, 7, 8, 9, 10
LOCK_VOLUME, BALANCE, MUTE, DIM, LOOPBACK, DC_PROTECTION = 13, 14, 15, 16, 17, 18
NOT_APPLICABLE = -1
REF_LEVELS = {3: ["-5 dBu", "+1 dBu", "+7 dBu", "+13 dBu"], 6: ["Lo-Power", "Hi-Power"]}
CHOICES = {MONO: ["Off", "On", "to Left"], POLARITY: ["Off", "Both", "Left", "Right"],
           CROSSFEED: ["Off", "1", "2", "3", "4", "5"],
           DE_EMPHASIS: ["Auto", "On", "Off"], DC_PROTECTION: ["Off", "On", "Filter"], MS_PROC: ["Off", "On"],
           LOOPBACK: ["Off", "pre FX", "post FX", "post -6 dB"]}
# DA Filter: which filters there are depends on the D/A converter, which the device reports as its revision
# (status.revision): the AK4490 (0) has five, the AK4493 (1) adds SD LD, the ES9028Q2M (2) Brickwall
DA_FILTERS = {0: ["SD Sharp", "SD Slow", "Sharp", "Slow", "NOS"]}
DA_FILTERS.update({1: DA_FILTERS[0] + ["SD LD"], 2: DA_FILTERS[0] + ["Brickwall"]})


def da_filters(revision, model=None):
    """The DA Filter names of a device of this revision; None when they are not known: before the first status
    message, or for another revision. model: a models.Model, else the ADI-2 DAC FS."""
    return (DA_FILTERS if model is None else model.da_filters).get(revision)


def ref_levels(out, model=None):
    """The Ref Level names of output address out; none where it has no Ref Level."""
    return (REF_LEVELS if model is None else model.ref_levels).get(out, [])


def choices(index, model=None):
    """The names of a setting on an output address that has a fixed list (CHOICES), as model names them."""
    return CHOICES[index] if model is None else model.choices.get(index, CHOICES[index])


# Width and Balance -100 .. 100, in hundredths; shown -1.00 .. 1.00 with its three points by name, and
# L 100 .. C .. R 100
WIDTH_NAMES = {-100: "Swapped", 0: "Mono", 100: "Stereo"}
OUTPUT_ADDRESSES = tuple(out for _, out, _, _ in OUTPUTS)
# the rates the device runs at, in the order of their index (Sample Rate, 12/16, and the status message)
SAMPLE_RATES = [44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000, 705600, 768000]
SAMPLE_RATE = (12, 16)                           # Sample Rate: the rate the device runs at, display only

# Loudness, on the output address (manual 12.4): Bass and Treble Gain +1..+10 dB, Low Vol Ref -90..-20 dB,
# all in 0.5 dB steps. Their indices 20..23 are Bass/Treble on an EQ address, so they are told apart by spec():
# ("out", index)
LOUDNESS_ENABLE = 20
LD_BASS, LD_TREBLE, LD_LOW_VOL_REF = 21, 22, 23
OUTPUT_RANGES = {LOUDNESS_ENABLE: (0, 1), LD_BASS: (2, 20), LD_TREBLE: (2, 20), LD_LOW_VOL_REF: (-180, -40)}
# what Commander writes besides Loudness. Ref Level: Line Out 0 .. 3, Phones 0 .. 1 (limits())
OUTPUT_RANGES.update({i: (0, len(names) - 1) for i, names in CHOICES.items()})
OUTPUT_RANGES[DA_FILTER] = (0, max(map(len, DA_FILTERS.values())) - 1)   # the widest; limits() takes the revision's
OUTPUT_RANGES.update({WIDTH: (-100, 100), BALANCE: (-100, 100), LOCK_VOLUME: (0, 1), VOLUME: (-1145, 60),
                      REF_LEVEL: (0, 3), AUTO_REF_LEVEL: (0, 1), MUTE: (0, 1), DIM: (0, 1),
                      SOURCE: (0, len(INPUTS) - 1)})
VOLUME_STEP = 5                                  # 0.5 dB: one click on an arrow, and the grid of Volume
# Volume held, up or down: the remote control's rise per second at each level of the device's own scale
# (volume_level), in steps of five a second (0.5 dB down to -5 dB, half a dB more about every 10 dB, coarse below
# -65 dB); (from this level, this step), else VOLUME_HELD_LOWEST, in 0.1 dB
VOLUME_HELD_STEPS = [(-50, 10), (-145, 20), (-245, 25), (-345, 35), (-440, 45), (-550, 55), (-645, 65)]
VOLUME_HELD_LOWEST = 80
VOLUME_FLOOR = -965                              # the bottom of the device's own scale: its display shows a dash

EQ_RANGES = {
    2: (0, 1),
    3: (0, 3), 4: (-24, 24), 5: (20, 20000), 6: (5, 99),
    7: (-24, 24), 8: (20, 20000), 9: (5, 99),
    10: (-24, 24), 11: (20, 20000), 12: (5, 99),
    13: (-24, 24), 14: (200, 20000), 15: (5, 50),
    16: (0, 2), 17: (-24, 24), 18: (200, 20000), 19: (5, 50),
    20: (0, 1),
    21: (-24, 24), 22: (20, 150), 23: (5, 15),
    24: (-24, 24), 25: (3000, 10000), 26: (5, 15),
    27: (0, 1),
    28: (0, 22),
}

FREQ_INDICES = {5, 8, 11, 14, 18, 22, 25}
GAIN_INDICES = {4, 7, 10, 13, 17, 21, 24}
Q_INDICES = {6, 9, 12, 15, 19, 23, 26}
TYPE_INDICES = {3, 16}

RANGES = {**EQ_RANGES, **{("out", i): r for i, r in OUTPUT_RANGES.items()}}


def spec(key):
    """What the helpers below take for a parameter key: the index on an EQ address, ("out", index) on an
    output address."""
    a, i = key
    return ("out", i) if a in OUTPUT_ADDRESSES else i


def limits(key, revision=None, model=None):
    """The lowest and highest value of a parameter key; Ref Level as far as its output goes, DA Filter as far as the
    device's revision goes (ValueError when its filters are not known), the other lists as model names them.
    model: a models.Model, else the ADI-2 DAC FS."""
    a, i = key
    if a in OUTPUT_ADDRESSES and i == REF_LEVEL:
        return 0, len(ref_levels(a, model)) - 1
    if a in OUTPUT_ADDRESSES and i == DA_FILTER:
        names = da_filters(revision, model)
        if names is None:
            raise ValueError("the DA filters of revision %s are not known" % revision)
        return 0, len(names) - 1
    if a in OUTPUT_ADDRESSES and i in CHOICES:
        return 0, len(choices(i, model)) - 1
    return RANGES[spec(key)]


def absent(index, value):
    """True for a setting this output does not have: Ref Level or Auto Ref Level reporting -1. Elsewhere -1 is a
    value like any other (Balance L 1, Width -0.01)."""
    return index in (REF_LEVEL, AUTO_REF_LEVEL) and value == NOT_APPLICABLE

SOURCES = ["Manual", "Temp"] + ["Preset %d" % n for n in range(1, 21)] + ["Clear"]

# what Clear and an unused preset slot load: gains 0, the default frequencies and Q 1.0, Band 1 and 5 type
# Shelf, and Dual EQ off; with Load B/T on also this Bass/Treble: 0 dB at 85 Hz Q 0.9, 0 dB at 6500 Hz Q 0.7
FACTORY_BANDS = {3: 1, 4: 0, 5: 100, 6: 10, 7: 0, 8: 500, 9: 10, 10: 0, 11: 1000, 12: 10,
                 13: 0, 14: 5000, 15: 10, 16: 1, 17: 0, 18: 10000, 19: 10}
FACTORY_BT = {21: 0, 22: 85, 23: 9, 24: 0, 25: 6500, 26: 7}

# a preset name: the signs the front panel offers, up to 14 (ADI-2 DAC FS manual, p. 27)
NAME_MARKS = "+-/()*;:.,!#$&<>='|@"                # besides letters, digits and space
NAME_SIGNS = frozenset(" ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" + NAME_MARKS)
NAME_LENGTH = 14


def valid_name(name):
    return len(name) <= NAME_LENGTH and set(name) <= NAME_SIGNS


def kind(index):
    if isinstance(index, tuple):
        if index[1] in (WIDTH, BALANCE):
            return "width" if index[1] == WIDTH else "balance"
        if index[1] in CHOICES or index[1] in (REF_LEVEL, SOURCE, DA_FILTER):
            return "choice"
        if index[1] == VOLUME:
            return "volume"
        return ("switch" if index[1] in (LOUDNESS_ENABLE, LOCK_VOLUME, AUTO_REF_LEVEL, MUTE, DIM)
                else "gain")                                                     # Loudness: all in 0.5 dB
    if index in FREQ_INDICES:
        return "freq"
    if index in GAIN_INDICES:
        return "gain"
    if index in Q_INDICES:
        return "q"
    if index in TYPE_INDICES:
        return "type"
    return "switch"


# -- the frequency grid -------------------------------------------------------------------------
# 1 Hz up to and including 2040 Hz, 10 Hz above; the filter uses this grid too.

def grid_step(hz):
    return 1 if hz <= 2040 else 10


def snap_freq(hz, index):
    """Nearest frequency the device can hold on this parameter."""
    lo, hi = RANGES[index]
    hz = min(max(hz, lo), hi)
    if hz <= 2040.5:
        return int(math.floor(hz + 0.5))                         # half up, not Python's half to even
    return int(math.floor(hz / 10.0 + 0.5)) * 10


def next_on_grid(hz, direction):
    """The neighbouring grid frequency: 2039 <-> 2040 <-> 2050."""
    if direction > 0:
        return hz + 1 if hz < 2040 else (hz // 10 + 1) * 10
    return hz - 1 if hz <= 2040 else (hz - 1) // 10 * 10


def step_freq(hz, octaves, index):
    """Move by a fraction of an octave, onto the grid; always at least one grid step."""
    target = snap_freq(hz * 2 ** octaves, index)
    if target == hz:
        target = fine_step_freq(hz, 1 if octaves > 0 else -1, index)
    return target


def fine_step_freq(hz, direction, index):
    lo, hi = RANGES[index]
    return min(max(next_on_grid(hz, direction), lo), hi)


# -- steps per kind, in increments ----------------------------------------------------------------
# (small, large, finest); frequency steps are in octaves except the finest, which is one grid step
STEPS = {"freq": (1 / 24, 1 / 3, None), "gain": (1, 6, 1), "q": (1, 10, 1)}


def step(index, value, direction, size="small"):
    """The value one step up (direction +1) or down (-1). size: 'small', 'large' or 'finest'."""
    k = kind(index)
    lo, hi = RANGES[index]
    if k == "freq":
        if size == "finest":
            return fine_step_freq(value, direction, index)
        octaves = STEPS["freq"][0 if size == "small" else 1]
        return step_freq(value, direction * octaves, index)
    if k == "volume":                                            # every size: one step onto the half dBs
        v = (value // VOLUME_STEP + 1) * VOLUME_STEP if direction > 0 else (value - 1) // VOLUME_STEP * VOLUME_STEP
        return min(max(v, lo), hi)
    if k in ("gain", "q"):
        small, large, finest = STEPS[k]
        n = {"small": small, "large": large, "finest": finest}[size]
        return min(max(value + direction * n, lo), hi)
    return min(max(value + direction, lo), hi)


def volume_offset(state, out):
    """How far the device's own scale lies above the Volume an output reports, in 0.1 dB. With Auto Ref Level on,
    Volume is relative to the highest Ref Level (dBr) and the device's scale to the Ref Level in use: Line 6 dB a step
    lower, Phones 15 dB at Lo-Power. Otherwise 0."""
    if state.get((out, AUTO_REF_LEVEL)) != 1:
        return 0
    ref = state.get((out, REF_LEVEL), 0)
    return {3: (3 - ref) * 60, 6: 150 if ref == 0 else 0}.get(out, 0)


def volume_floor(state, out):
    """The lowest Volume on the device's own scale, as the output reports it: -96.5 dB, with Auto Ref Level on at
    the lowest Ref Level, which it then uses."""
    lowest = dict(state)
    lowest[(out, REF_LEVEL)] = 0
    return VOLUME_FLOOR - volume_offset(lowest, out)


def volume_held_step(level):
    """The step of a held Volume at this level of the device's own scale, in 0.1 dB."""
    return next((s for lowest, s in VOLUME_HELD_STEPS if level >= lowest), VOLUME_HELD_LOWEST)


def volume_held(value, direction, offset=0, floor=None):
    """One held step of Volume up or down from value (volume_held_step at value + offset), onto the half dBs, between
    floor (else the range) and the top. value itself when it cannot move."""
    lo, hi = RANGES[("out", VOLUME)]
    lo = lo if floor is None else floor
    v = (value + direction * volume_held_step(value + offset)) // VOLUME_STEP * VOLUME_STEP
    return max(value, min(hi, v)) if direction > 0 else min(value, max(lo, v))


# -- units ----------------------------------------------------------------------------------------

def to_text(index, value, band=None):
    k = kind(index)
    if k == "freq":
        return "%d" % value
    if k == "gain":
        return "%.1f" % (value / 2)
    if k == "q":
        return "%.1f" % (value / 10)
    if k == "volume":
        return "%.1f" % (value / 10)
    if k == "width":
        return WIDTH_NAMES.get(value, "%.2f" % (value / 100))
    if k == "balance":
        return "C" if value == 0 else "%s %d" % ("L" if value < 0 else "R", abs(value))
    if k == "type":
        return TYPE_ABBR[band][value]
    return "on" if value else "off"


def parse(index, text):
    """Text typed by the user -> (increment value the device will hold, clamped or rounded: bool).
    Accepts a comma as decimal separator and 'k' for kHz. Raises ValueError for text that is no number."""
    t = text.strip().lower().replace(",", ".").replace(" ", "")
    k = kind(index)
    lo, hi = RANGES[index]
    if k == "freq":
        t = t.removesuffix("hz")
        m = re.fullmatch(r"([0-9]*\.?[0-9]+)(k?)", t)
        if not m:
            raise ValueError(text)
        hz = float(m.group(1)) * (1000 if m.group(2) else 1)
        v = snap_freq(hz, index)
        return v, v != hz
    x = float(t.removesuffix("db"))
    raw = x * (2 if k == "gain" else 10)
    v = min(max(int(math.floor(raw + 0.5)), lo), hi)
    return v, abs(v - raw) > 1e-9


def at_limit(index, value):
    """-1 at the lower limit, +1 at the upper limit, 0 otherwise."""
    lo, hi = RANGES[index]
    return -1 if value <= lo else 1 if value >= hi else 0
