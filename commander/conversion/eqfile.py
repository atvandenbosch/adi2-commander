"""EQ settings as a file, in the format of Equalizer APO.

Commander writes a file for people and for APO: first, as comments, a table of the settings as the device
holds them, from which Commander loads back exactly; then the same as APO filters (PK, LSC, HSC, HPQ, LPQ)
with the Cookbook Q of the same response (the device computes alpha differently; filters.cookbook_q). The
table is needed: where w0/2Q > pi/2 two device Qs give the same Cookbook Q.

Reading understands three dialects, each with its own meaning of the same words:
- Commander's own files: the table is what counts (table), also when the Filter lines no longer say the same
  (disagreeing).
- REW's "Export filter settings as text" (header "Filter Settings file"): REW's meaning. LS/HS without Q are Q 0.707 at the centre frequency, LS Q/HS Q take the centre frequency too, and
  the fixed slope shelves take the corner frequency with a prewarped conversion.
- Any other APO configuration: APO's meaning, after its parser (filters/BiQuadFilterFactory.cpp and
  BiQuadFilter.cpp). LS/HS without Q or slope are S 0.9 at the centre frequency, LS/HS with a Q or slope
  take the corner frequency, a comma is a decimal point, and '1.000' in a frequency is a thousand.

Every filter comes out as a Cookbook biquad: kind PK, LS, HS, HP or LP, f0 (the centre of a shelf), gain and
Q.
"""

import codecs
import datetime
import math
import re
from collections import namedtuple

from .. import __version__
from ..device import models
from ..device import filters as F
from ..device import params as P

# A filter from a file, as a Cookbook biquad. channel: 'all', 'L' or 'R'. gain 0 for HP and LP. device: the
# setting Commander wrote with it, (target, type, freq, gain, q) with target 1..5, 'Bass' or 'Treble', or None.
# line: 1-based line number in the file. corner: a shelf's frequency as written, when the file gives its corner
# (freq is then the centre), else None.
Entry = namedtuple("Entry", "channel kind freq gain q on device line corner", defaults=(None,))
Skipped = namedtuple("Skipped", "line text reason")
# A row of Commander's table: channel 'L', 'R' or 'all'; target 1..5, 'Bass' or 'Treble'; type as the device names
# it, a shelf with its side ('Peak', 'Low Shelf', 'High Shelf', 'High Pass', 'High Cut'; the target for Bass and
# Treble); freq, gain and q as the device shows them, or None where the number is not a number; on: its group is not
# '(off)'.
Row = namedtuple("Row", "line channel target type freq gain q on")


class EqFile:
    def __init__(self):
        self.source = "apo"               # 'commander', 'rew' or 'apo'
        self.equaliser = None             # REW: the equaliser the filters were made for
        self.output = None                # Commander: the output it was saved from, as in its header
        self.fs = None                    # Commander: the sample rate the Cookbook Q was computed for
        self.entries = []
        self.preamp = []                  # (channel, dB, line)
        self.skipped = []                 # lines that do something in APO or REW, but not here
        self.recognised = False           # a line in APO or REW syntax: a filter file at all
        self.warnings = []                # about the file as a whole
        self.lines = []                   # the text, line by line (Entry.line counts from 1)
        self.table = []                   # Commander: the rows of its table, as Row


SQRT1_2 = math.sqrt(0.5)
APO_TYPE = {"PK": "PK", "LS": "LSC", "HS": "HSC", "HP": "HPQ", "LP": "LPQ"}
DEVICE_KIND = {"Peak": "PK", "Low Shelf": "LS", "High Shelf": "HS", "High Pass": "HP", "High Cut": "LP"}
TYPE_NAME = {kind: name for name, kind in DEVICE_KIND.items()}
REW_COOKBOOK = ("Generic", "Extended", "Configurable PEQ")                 # Cookbook with the Q set
NOT_HERE = "not on the device"
NUMBER = r"([-+0-9.eE]+)"
HEADER = "# ADI-2 Commander"
HEADER_LINE = re.compile(r"^# ADI-2 Commander( \d+\.\d+\.\d+\S*)?$")       # with the version that wrote it
# the commands of APO besides Filter, Channel and Preamp: a line with one of them makes a filter file
APO_COMMANDS = ("Device", "Stage", "Include", "Delay", "Copy", "Convolution", "GraphicEQ", "Eval", "If",
                "ElseIf", "Else", "EndIf", "VSTPlugin", "LoudnessCorrection")
# the groups of the table, as the app shows them, with the channel of their rows
GROUP = {"EQ Left": "L", "EQ Right": "R", "EQ Left and Right": "all", "Bass/Treble": "all"}
GROUP_HEAD = re.compile(r"^#\s*(EQ Left and Right|EQ Left|EQ Right|Bass/Treble)( \(off\))?$")
ROW = re.compile(r"^#\s+(Band [1-5]|Bass|Treble)\s+(?:(Peak|Low Shelf|High Shelf|High Pass|High Cut)\s+)?"
                 r"(\S+) Hz\s+(\S+) dB\s+Q (\S+)")
FS_NOTE = re.compile(r"^#\s*Converted to RBJ Cookbook biquads at (\S+) kHz")
OUTPUT_NOTE = re.compile(r"^#\s*(?:Output|Input):\s*(.+?)\s*$")


# -- writing ---------------------------------------------------------------------------------------

def write(state, out, fs=F.FS, now=None, preset=None, model=models.DAC):
    """The EQ of one output, or of the input, as a file: a header (tool, date, device, where the settings come from,
    which settings), the settings as a table for people (and for Commander to load back exactly), then the same
    converted to RBJ Cookbook biquads in the format of Equalizer APO. A channel with EQ Enable off, and Bass/Treble
    with B/T Enable off, are '(off)' on their group in the table and OFF for APO, which skips them. The column of
    types is as wide as the longest type in it. preset: (slot, name) when state holds a preset being edited rather
    than the output. model: the device, with its names of the outputs. The input has no Bass/Treble: its EQ comes
    without, a preset being edited on it with. Raises ValueError when the state of the output is incomplete."""
    _, _, left, right = P.channel(out)
    name = models.channel_name(model, out)
    dual = state.get(P.dual_eq_key(out))
    sets = [("L", left), ("R", right)] if dual == 1 else [("all", left)]
    bands = {ch: F.band_filters(state, addr, left) for ch, addr in sets}
    bt = F.bt_filters(state, left)
    if dual is None or not all(bands.values()) or not bt and P.has_bt(out):
        raise ValueError("EQ of %s not read yet" % name)
    when = (now or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M")
    group = {"L": "EQ Left", "R": "EQ Right", "all": "EQ Left and Right"}
    rows = []                                    # (channel, group, label, type, filter)
    for ch, _ in sets:
        rows += [(ch, group[ch], "Band %d" % flt.band, TYPE_NAME[flt.kind], flt) for flt in bands[ch]]
    rows += [("all", "Bass/Treble", {"B": "Bass", "T": "Treble"}[flt.name], "", flt) for flt in bt]
    width = max(len(typ) for *_, typ, _ in rows)
    if preset:
        slot, label = preset
        source = "# Preset: %d" % slot + (" (%s)" % label if label else "")
    else:
        source = "# %s: %s" % ("Output" if P.has_bt(out) else "Input", name.replace("·", "-"))
    lines = ["%s %s" % (HEADER, __version__), "# Date: " + when, "# Device: RME " + model.name, source,
             "# Settings: EQ, Bass/Treble" if bt else "# Settings: EQ", "#"]
    shown = None
    for _, head, label, typ, flt in rows:
        if head != shown:
            lines.append("# " + head + ("" if flt.active else " (off)"))
            shown = head
        lines.append(("#   %-6s  %-*s  %5d Hz  %5.1f dB  Q %.1f" % (
            label, width, typ, flt.freq, flt.gain, flt.q)).rstrip())
    filters = "Converted to RBJ Cookbook biquads at %g kHz, Equalizer APO format:" % (fs / 1000)
    lines += ["#", "# " + "-" * len(filters), "# " + filters]
    apo_channel = "all"
    for ch, _, label, _, flt in rows:
        if dual == 1 and ch != apo_channel:
            lines.append("Channel: %s" % ch)
            apo_channel = ch
        lines.append(_filter_line(label.replace("Band ", ""), flt, fs))
    return "\n".join(lines) + "\n"


def _filter_line(label, flt, fs):
    s = "Filter %s: %s %s Fc %d Hz" % (label, "ON" if flt.active else "OFF", APO_TYPE[flt.kind], flt.freq)
    if flt.kind in ("PK", "LS", "HS"):
        s += " Gain %.1f dB" % flt.gain
    return s + " Q %.4f" % F.cookbook_q(flt.q, flt.freq, fs)


def save(path, text):
    with open(path, "w", encoding="ascii", newline="\r\n") as f:
        f.write(text)


# -- reading ---------------------------------------------------------------------------------------

def load(path, fs=F.FS):
    return read(text(path), fs)


def text(path):
    """The text of a file: UTF-16 when it starts with its byte order mark, else UTF-8, else Windows-1252."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def read(text, fs=F.FS):
    """Parse a file into an EqFile. fs: the sample rate for what depends on it (a bandwidth in octaves, a
    prewarped corner frequency); a Commander file brings its own."""
    lines = text.splitlines()
    eq = EqFile()
    eq.lines = lines
    first = next((l.strip() for l in lines if l.strip()), "")
    if first == "Filter Settings file":
        eq.source = "rew"
    elif HEADER_LINE.match(first):
        eq.source = "commander"
    eq.recognised = eq.source != "apo"
    channel = "all"
    devices = {}                                 # Commander: {(channel, target label): device setting}
    shown, shown_on = None, True                 # the channel and the state of the group heading the rows
    for no, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("#"):
            if eq.source == "commander":
                m = FS_NOTE.match(s)
                if m:
                    khz = _number(m.group(1))
                    eq.fs = float(round(khz * 1000)) if khz else None
                    fs = eq.fs or fs
                m = OUTPUT_NOTE.match(s)
                if m:
                    eq.output = m.group(1)
                m = GROUP_HEAD.match(s)
                if m:
                    shown, shown_on = GROUP[m.group(1)], not m.group(2)
                m = ROW.match(s)
                if m:
                    devices[(shown, m.group(1))] = _device(m)
                    eq.table.append(_row(no, shown, shown_on, m))
            continue
        if not s or ":" not in s:
            continue
        command, params = s.split(":", 1)
        command = command.strip()
        if re.match(r"(Filter|Channel|Preamp)\b", command) or command in APO_COMMANDS:
            eq.recognised = True
        if command.startswith("Filter"):
            if channel is not None:
                label = command[len("Filter"):].strip()
                target = "Band " + label if label.isdigit() else label
                _filter(eq, channel, params, no, s, devices.get((channel, target)), fs)
            else:
                eq.skipped.append(Skipped(no, s, "not for L or R"))
        elif command == "Channel":
            channel = _channel(eq, params, no, s)
        elif command == "Preamp":
            m = re.match(r"^\s*" + NUMBER + r"\s*dB", params.replace(",", "."))
            db = _number(m.group(1)) if m else None
            if db is None:
                eq.skipped.append(Skipped(no, s, "no number of dB"))
            elif channel is not None:
                eq.preamp.append((channel, db, no))
        elif eq.source == "rew":
            if command == "Equaliser":
                eq.equaliser = params.strip()
                if eq.equaliser not in REW_COOKBOOK:
                    eq.warnings.append("REW equaliser %s: curves not exact. Export with Generic." % eq.equaliser)
        else:
            eq.skipped.append(Skipped(no, s, "%s: not an EQ filter" % command))
    return eq


def _number(text):
    try:
        return float(text)
    except ValueError:
        return None


def _device(m):
    """The setting in a row of Commander's table, or None when its numbers are not numbers. A comma is a decimal
    point, as in a Filter line."""
    label, typ, *numbers = m.groups()
    numbers = [_number(x.replace(",", ".")) for x in numbers]
    if None in numbers:
        return None
    target = int(label[5:]) if label.startswith("Band") else label
    return (target, typ or label, *numbers)


def _row(no, channel, on, m):
    label, typ, *numbers = m.groups()
    freq, gain, q = (_number(x.replace(",", ".")) for x in numbers)
    target = int(label[5:]) if label.startswith("Band") else label
    return Row(no, channel, target, typ or label, freq, gain, q, on)


def _channel(eq, params, no, text):
    """'all', 'L' or 'R' for the filters that follow, or None to skip them."""
    names = {"L": "L", "1": "L", "R": "R", "2": "R"}
    tokens = params.split()
    if any(t.lower() == "all" for t in tokens):
        return "all"
    found = {names[t] for t in tokens if t in names}
    if len(found) < len(tokens):
        eq.skipped.append(Skipped(no, text, "only L and R are used"))
    if not found:
        return None
    return "all" if len(found) == 2 else found.pop()


def _filter(eq, channel, params, no, text, device, fs):
    params = params.replace(",", ".")
    m = re.match(r"^\s*(ON|OFF)\s+(.*)$", params)
    if not m:
        eq.skipped.append(Skipped(no, text, "neither ON nor OFF"))
        return
    on, rest = m.group(1) == "ON", m.group(2)
    parse = _rew_filter if eq.source == "rew" else _apo_filter
    try:
        result = parse(rest, fs)
    except ValueError as e:
        eq.skipped.append(Skipped(no, text, str(e)))
        return
    if result is not None:
        kind, f0, gain, q, corner = result
        eq.entries.append(Entry(channel, kind, f0, gain, q, on, device, no, corner))


def _search(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    return float(m.group(1)) if m else None


def _apo_freq(text):
    """APO's getFreq: a frequency with exactly three digits after the point is a thousand."""
    m = re.search(r"\s+Fc\s*([-+0-9.eE\u00A0]+)\s*H\s*z", " " + text)
    if not m:
        return None
    s = m.group(1).replace("\u00A0", "")
    f = float(s)
    if len(s) >= 5 and "e" not in s.lower() and s[-4] == ".":
        f *= 1000.0
    return f


def _apo_filter(rest, fs):
    """One filter after ON/OFF, as APO reads it: (kind, f0, gain, Cookbook Q, corner as written or None), or
    None for 'None'."""
    m = re.match(r"^([A-Za-z]+)(.*)$", rest)
    if not m:
        raise ValueError("no filter type")
    word, rest = m.group(1), m.group(2)
    kind = {"PK": "PK", "PEQ": "PK", "Modal": "PK", "LP": "LP", "LPQ": "LP", "HP": "HP", "HPQ": "HP",
            "LS": "LS", "LSC": "LS", "HS": "HS", "HSC": "HS"}.get(word)
    if word == "None":
        return None
    if kind is None:
        raise ValueError("%s: %s" % (word, NOT_HERE if word in ("NO", "AP", "BP", "IIR") else "unknown filter type"))
    f0 = _apo_freq(rest)
    if f0 is None:
        raise ValueError("no frequency")
    gain = _search(r"\s+Gain\s*" + NUMBER + r"\s*dB", rest)
    shelf = kind in ("LS", "HS")
    if gain is None and kind != "HP" and kind != "LP":
        raise ValueError("no gain")
    gain = 0.0 if kind in ("HP", "LP") else gain
    value, how = 0.0, "q"
    q = _search(r"\s+Q\s*" + NUMBER, rest)
    if q is not None:
        value = q
    bw = _search(r"\s+BW\s+Oct\s*" + NUMBER, rest)
    if bw is not None and not shelf:
        value, how = bw, "bw"
    slope = _search(r"^\s*" + NUMBER + r"\s*dB", rest)
    if slope is not None and shelf:
        value, how = slope, "s"
    corner = False
    if value == 0:
        if kind == "PK":
            raise ValueError("no Q or bandwidth")
        if shelf:
            value, how = 0.9, "s"
        else:
            value = SQRT1_2
    elif shelf:
        if how == "s":
            value /= 12.0
        corner = not word.endswith("C")
    if how == "bw":
        w0 = 2 * math.pi * f0 / fs
        q = 1 / (2 * math.sinh(math.log(2) / 2 * value * w0 / math.sin(w0)))
    elif how == "s":
        q = _q_from_s(value, gain)
    else:
        q = value
    written = None
    if corner:
        written, f0 = f0, _centre(kind, f0, gain, q, fs, prewarp=False)
    return kind, f0, gain, q, written


# REW writes its type names in full, some with a space; longest first so that 'LS Q' wins over 'LS'
REW_TYPES = {"PK": "PK", "Modal": "PK", "PEQ": "PK", "LS": "LS", "HS": "HS", "LS Q": "LS", "HS Q": "HS",
             "LS 6dB": "LS", "LS 12dB": "LS", "HS 6dB": "HS", "HS 12dB": "HS", "HP": "HP", "LP": "LP",
             "HP Q": "HP", "LP Q": "LP"}
REW_NOT_HERE = ("Notch", "All pass", "HP1", "LP1", "BP", "PA")


def _rew_filter(rest, fs):
    """One filter after ON/OFF, as REW means it."""
    names = sorted(list(REW_TYPES) + list(REW_NOT_HERE) + ["None"], key=len, reverse=True)
    word = next((n for n in names if re.match(re.escape(n) + r"(\s|$)", rest)), None)
    if word is None:
        raise ValueError("unknown filter type")
    if word == "None":
        return None
    if word in REW_NOT_HERE:
        raise ValueError("%s: %s" % (word, NOT_HERE))
    kind, rest = REW_TYPES[word], rest[len(word):]
    written = None
    f0 = _search(r"\bFc\s*" + NUMBER + r"\s*Hz", rest, re.I)
    if f0 is None:
        raise ValueError("no frequency")
    gain = _search(r"\bGain\s*" + NUMBER + r"\s*dB", rest, re.I)
    if gain is None and kind not in ("HP", "LP"):
        raise ValueError("no gain")
    gain = 0.0 if kind in ("HP", "LP") else gain
    q = _search(r"\bQ\s+" + NUMBER, rest)
    bw = _search(r"\bBW\s+oct\s*" + NUMBER, rest, re.I)
    if word.endswith("dB"):                          # fixed slope: S 0.5 or 1, corner frequency (prewarped)
        q = _q_from_s(int(word.split()[1][:-2]) / 12.0, gain)
        written, f0 = f0, _centre(kind, f0, gain, q, fs, prewarp=True)
    elif q is None and bw is not None:               # an equaliser in octaves (FBQ2496): not Cookbook anyway
        q = 1 / (2 * math.sinh(math.log(2) / 2 * bw))
    elif q is None:
        if kind == "PK":
            raise ValueError("no Q")
        q = SQRT1_2                                  # Generic LS, HS, HP, LP: Q 0.707
    return kind, f0, gain, q, written


def _q_from_s(s, gain):
    """Cookbook shelf: Q from the slope S, 1/Q^2 = (A + 1/A)(1/S - 1) + 2."""
    a = 10 ** (gain / 40)
    v = (a + 1 / a) * (1 / s - 1) + 2
    if v <= 0:
        raise ValueError("slope too steep")
    return 1 / math.sqrt(v)


def _centre(kind, corner, gain, q, fs, prewarp):
    """The centre frequency of a shelf given by its corner: a factor 10^(|gain|/80/S), up for a low shelf and
    down for a high one. APO applies it to the frequency itself; REW to tan(pi f/fs), as a bilinear transform
    would."""
    a = 10 ** (gain / 40)
    s = 1 / ((1 / (q * q) - 2) / (a + 1 / a) + 1)
    factor = 10 ** (abs(gain) / 80 / s)
    if kind == "HS":
        factor = 1 / factor
    if not prewarp:
        return corner * factor
    return fs / math.pi * math.atan(math.tan(math.pi * corner / fs) * factor)


# -- Commander's own files ------------------------------------------------------------------------

def table(eq):
    """The rows of a Commander file's table when it is whole, else None: one set of five bands for both channels
    or one for each, Bass and Treble with them or not, and no row in table_faults. The table is what counts: it is
    the device's own setting, also when the Filter lines below it were edited (disagreeing)."""
    if eq.source != "commander" or not eq.table or table_faults(eq):
        return None
    rows = eq.table
    bands = {}
    for r in rows:
        if r.target not in ("Bass", "Treble"):
            bands.setdefault(r.channel, []).append(r.target)
    if sorted(bands) not in (["all"], ["L", "R"]) or any(sorted(t) != [1, 2, 3, 4, 5] for t in bands.values()):
        return None
    tone = sorted(r.target for r in rows if r.target in ("Bass", "Treble"))
    if tone not in ([], ["Bass", "Treble"]):
        return None
    return rows


def table_faults(eq):
    """{line: why} for the rows of a Commander file's table that keep it from counting: under no group, a number
    that is not a number, a type its band does not have, a band or Bass/Treble twice in its group. A row that is
    missing has no line; table() still tells."""
    if eq.source != "commander":
        return {}
    faults, seen = {}, set()
    for r in eq.table:
        band = r.target not in ("Bass", "Treble")
        name = "Band %d" % r.target if band else r.target
        if r.channel is None:
            faults[r.line] = "Under no group"
        elif None in (r.freq, r.gain, r.q):
            what = "Frequency" if r.freq is None else "Gain" if r.gain is None else "Q"
            faults[r.line] = "%s is not a number" % what
        elif band and r.type not in DEVICE_KIND:
            faults[r.line] = "No type"
        elif band and DEVICE_KIND[r.type] not in (P.TYPE_ABBR[r.target] if P.BANDS[r.target][0] is not None
                                                  else ["PK"]):
            faults[r.line] = "%s has no %s" % (name, r.type)
        elif (r.channel, r.target) in seen:
            faults[r.line] = "%s twice in its group" % name
        seen.add((r.channel, r.target))
    return faults


def disagreeing(eq):
    """The lines of the Filters that no longer say what the table does (within the precision Commander writes)."""
    if table(eq) is None:
        return set()
    return {e.line for e in eq.entries if e.device is None or not _agrees(e, eq.fs or F.FS)}


def _agrees(e, fs):
    """The Filter line says what its row in the table does, within the precision Commander writes."""
    target, typ, freq, gain, q = e.device
    if target == "Bass":
        kind = "LS"
    elif target == "Treble":
        kind = "HS"
    else:
        kind = DEVICE_KIND[typ]
    if kind in ("HP", "LP"):
        gain_ok = e.gain == 0
    else:
        gain_ok = abs(e.gain - gain) < 0.05
    return (e.kind == kind and abs(e.freq - freq) < 0.5 and gain_ok
            and abs(e.q - F.cookbook_q(q, freq, fs)) < 6e-5)
