"""From a file to the device: what Import proposes, and what OK writes.

A file is read by eqfile. Its lines that can be used become Items, in the convention of their Origin: 'External'
(a Cookbook biquad, as filter files usually mean it) or 'ADI-2' (the numbers as the device has them). In a
Commander file with Origin ADI-2 the rows of its table are the items, each with the band it belongs to.

Two ways to the device:
- Map: filter by filter onto the bands. A filter takes a band that accepts its kind, frequency and Q; the Q of an
  External filter is converted to the device Q with the same curve (filters.device_qs). What the device cannot do
  on any band is limited, with a note; when no band is left that can take a filter, the selection does not map
  (unmappable, with the reason).
- Fit: eqfit on the curve of the selected items; the mapped filters are one of its starts. A band it leaves at
  0 dB is flat, and as with Map not set.

The outcome is per block: the EQ of each channel ('L', 'R', or 'all' with Dual EQ off) and Bass/Treble ('BT').
What it does not set is undefined; written, an undefined band gets its factory default (params.FACTORY_BANDS,
FACTORY_BT, gain 0). EQ Enable, B/T Enable and Dual EQ are never written here.
"""

import itertools
import math
from collections import namedtuple

import numpy as np

from . import eqfile as E
from . import eqfit as X
from ..device import filters as F
from ..device import params as P

ADI2, EXTERNAL = "ADI-2", "External"
BANDS = (1, 2, 3, 4, 5)
TONE = ("Bass", "Treble")
TONE_KIND = {"Bass": "LS", "Treble": "HS"}
NO_GAIN = ("HP", "LP")
GAIN = P.EQ_RANGES[P.BANDS[1][1]][1] / 2         # dB either way, on every band and on Bass/Treble
FREQ_ANY = P.BANDS[1][2]                         # a frequency index with the device's whole range
Q_LO = min(P.EQ_RANGES[P.BANDS[b][3]][0] for b in BANDS) / 10
Q_HI = max(P.EQ_RANGES[P.BANDS[b][3]][1] for b in BANDS) / 10

# A line of the file that the conversion can use. freq, gain and q in the convention of its Origin; target: the band
# (1..5, 'Bass' or 'Treble') of a row of Commander's table, else None.
Item = namedtuple("Item", "line channel kind freq gain q target")
# One filter on its band, as the device will have it: kind, freq in Hz, gain in dB, Q; notes on what was limited.
Placed = namedtuple("Placed", "item target kind freq gain q notes")


def accepts(target):
    """The kinds a band (or Bass, Treble) takes."""
    if target in TONE:
        return (TONE_KIND[target],)
    ti = P.BANDS[target][0]
    return tuple(P.TYPE_ABBR[target]) if ti is not None else ("PK",)


def indices(target):
    """(gain, freq, Q) indices of a band or of Bass/Treble."""
    return P.BASS if target == "Bass" else P.TREBLE if target == "Treble" else P.BANDS[target][1:]


def freq_range(target):
    return P.EQ_RANGES[indices(target)[1]]


def q_range(target):
    lo, hi = P.EQ_RANGES[indices(target)[2]]
    return lo / 10, hi / 10


# -- the lines of a file ---------------------------------------------------------------------------

def items(eq, origin, fs):
    """({line: Item} that can be selected, {line: why not} for the lines of filters and Preamp that cannot)."""
    usable, why = {}, {}
    rows = E.table(eq)
    for _, _, no in eq.preamp:
        why[no] = "Preamp: not needed on the device"
    for s in eq.skipped:
        why[s.line] = _capital(s.reason)
    if rows is not None and origin == ADI2:
        for r in rows:
            usable[r.line] = Item(r.line, r.channel, _row_kind(r), r.freq, r.gain, r.q, r.target)
        for e in eq.entries:
            why[e.line] = "With Origin ADI-2 the table above is imported."
        return usable, why
    if rows is not None:
        for r in rows:
            why[r.line] = "With Origin External the Filter lines are imported."
    elif eq.table and eq.source == "commander":
        faults = E.table_faults(eq)
        for r in eq.table:
            why[r.line] = faults.get(r.line, "The table does not count; the Filter lines are imported.")
    for e in eq.entries:
        if not e.on:
            why[e.line] = "Off in the file"
        elif not 0 < e.freq < fs / 2:
            why[e.line] = "No filter at this frequency"
        elif origin == ADI2:
            usable[e.line] = Item(e.line, e.channel, e.kind, e.corner or e.freq, e.gain, e.q, None)
        else:
            usable[e.line] = Item(e.line, e.channel, e.kind, e.freq, e.gain, e.q, None)
    return usable, why


def _row_kind(r):
    if r.target in TONE:
        return TONE_KIND[r.target]
    return E.DEVICE_KIND.get(r.type, "PK")


def category(eq):
    """'commander': a Commander file with its table; 'fits': every filter that is on fits the device exactly as
    written, five bands per channel at most; 'other'. Bass and Treble count only when the file names them."""
    if E.table(eq) is not None:
        return "commander"
    usable, _ = items(eq, ADI2, F.FS)
    if not usable:
        return "other"
    for group in channel_sets(list(usable.values()), True).values():
        m = mapping(group, ADI2, F.FS)
        if not all(_on_grid(i) for i in group) or m.reason or any(p.notes for p in m.placed.values()):
            return "other"
    return "fits"


def _on_grid(i):
    if abs(i.freq - P.snap_freq(i.freq, FREQ_ANY)) > 1e-9 or abs(i.gain * 2 - round(i.gain * 2)) > 1e-9:
        return False
    return abs(i.q * 10 - round(i.q * 10)) < 1e-6


def channel_sets(chosen, dual):
    """The selected items per block of the EQ: {'L': [...], 'R': [...]} with Dual EQ, {'all': [...]} without. A
    file with one set gives both channels the same; items of only one channel leave the other out. Without Dual EQ,
    items of the left and of the right channel together are a conflict: ValueError. Bass and Treble rows apart."""
    eq_items = [i for i in chosen if i.target not in TONE]
    common = [i for i in eq_items if i.channel == "all"]
    own = {ch: [i for i in eq_items if i.channel == ch] for ch in ("L", "R")}
    if not dual:
        if own["L"] and own["R"]:
            raise ValueError("Dual EQ is off: one EQ for both channels. Choose left or right.")
        group = common + own["L"] + own["R"]
        return {"all": group} if group else {}
    out = {}
    for ch in ("L", "R"):
        group = common + own[ch]
        if group:
            out[ch] = group
    return out


def tone_items(chosen):
    return [i for i in chosen if i.target in TONE]


# -- Map -------------------------------------------------------------------------------------------

class Mapping:
    def __init__(self):
        self.placed = {}                  # {target: Placed}
        self.reason = ""                  # why the selection does not map, or ''


def mapping(group, origin, fs):
    """Filter by filter onto the bands: rows of the table on their own band, the rest where they fit."""
    m = Mapping()
    fixed = [i for i in group if i.target is not None]
    free = [i for i in group if i.target is None]
    for i in fixed:
        m.placed[i.target] = on_row(i)
    bands = [b for b in BANDS if b not in m.placed]
    converted = [(i, *_device_values(i, origin, fs)) for i in free]
    if len(free) > len(bands):
        m.reason = "%d filters for %d bands" % (len(free), len(bands))
        return m
    best, best_key = None, None
    for perm in itertools.permutations(bands, len(free)):
        chosen = []
        for (i, freq, gain, qs, notes), b in zip(converted, perm):
            q = _band_q(b, i.kind, freq, qs)
            if q is None:
                break
            chosen.append(Placed(i, b, i.kind, freq, gain, _half_up(q * 10) / 10, notes))
        else:
            error = sum(_error(p, origin, fs) for p in chosen)
            ordered = sorted((p.target, p.item.freq) for p in chosen)
            disorder = sum(1 for a, b in itertools.combinations(ordered, 2) if a[1] > b[1])
            key = (round(error, 6), disorder)
            if best_key is None or key < best_key:
                best, best_key = chosen, key
    if best is None:
        m.reason = _why_not(converted, bands)
        return m
    for p in best:
        m.placed[p.target] = p
    return m


def _device_values(i, origin, fs):
    """An item's frequency, gain and candidate device Qs (unrounded, the larger first), with what the device
    cannot do on any band limited (notes)."""
    notes = []
    lo, hi = P.EQ_RANGES[FREQ_ANY]
    freq = P.snap_freq(i.freq, FREQ_ANY)
    if not lo - 0.5 <= i.freq <= hi + 0.5:
        notes.append("frequency limited (%d–%d Hz)" % (lo, hi))
    gain = 0.0
    if i.kind not in NO_GAIN:
        gain = min(max(_half_up(i.gain * 2) / 2, -GAIN), GAIN)
        if abs(i.gain) > GAIN + 0.25:
            notes.append("gain limited (±%d dB)" % GAIN)
    qs = [i.q] if origin == ADI2 else F.device_qs(i.q, freq, fs)
    inside = [q for q in qs if Q_LO - 0.05 <= q <= Q_HI + 0.05]
    if inside:
        return freq, gain, inside, notes
    if qs:
        notes.append("Q limited (%.1f–%.1f)" % (Q_LO, Q_HI))
        return freq, gain, [min(max(qs[0], Q_LO), Q_HI)], notes
    notes.append("Q limited (too broad at %d Hz)" % freq)
    return freq, gain, [min(max(2 * freq / fs, Q_LO), Q_HI)], notes


def _band_q(target, kind, freq, qs):
    """The device Q a filter has on this band, or None when the band cannot take it."""
    if kind not in accepts(target):
        return None
    lo, hi = freq_range(target)
    if not lo <= freq <= hi:
        return None
    qlo, qhi = q_range(target)
    return next((q for q in qs if qlo <= _half_up(q * 10) / 10 <= qhi), None)


def on_row(i):
    """A row of Commander's table on its own band, on the grid; what the band cannot do limited (an edited table can
    say anything)."""
    notes = []
    gi, fi, qi = indices(i.target)
    lo, hi = P.EQ_RANGES[fi]
    freq = P.snap_freq(i.freq, fi)
    if not lo - 0.5 <= i.freq <= hi + 0.5:
        notes.append("frequency limited (%d–%d Hz)" % (lo, hi))
    gain = 0.0
    if i.kind not in NO_GAIN:
        gain = min(max(_half_up(i.gain * 2) / 2, -GAIN), GAIN)
        if abs(i.gain) > GAIN + 0.25:
            notes.append("gain limited (±%d dB)" % GAIN)
    qlo, qhi = q_range(i.target)
    q = min(max(_half_up(i.q * 10) / 10, qlo), qhi)
    if not qlo - 0.05 <= i.q <= qhi + 0.05:
        notes.append("Q limited (%.1f–%.1f)" % (qlo, qhi))
    return Placed(i, i.target, i.kind, freq, gain, q, notes)


def _why_not(converted, bands):
    """Why the filters do not fit the free bands together, in the words of the device."""
    def count(test):
        return sum(1 for i, freq, gain, qs, notes in converted if test(i, freq, qs))
    lows = count(lambda i, f, qs: i.kind in ("LS", "HP"))
    if lows > (1 if 1 in bands else 0):
        return "Only band 1 takes a low shelf or a High Pass"
    if count(lambda i, f, qs: i.kind == "HS") > (1 if 5 in bands else 0):
        return "Only band 5 takes a high shelf"
    if count(lambda i, f, qs: i.kind != "PK") > len({1, 5} & set(bands)):
        return "Only bands 1 and 5 take shelves, High Pass and High Cut"
    low_bands = len([b for b in bands if freq_range(b)[0] <= 20])
    if count(lambda i, f, qs: f < 200) > low_bands:
        return "Bands 4 and 5 start at 200 Hz"
    if count(lambda i, f, qs: min(qs) > 5.05) > low_bands:
        return "Bands 4 and 5 go up to Q 5.0"
    return "These filters do not fit the bands together"


def _error(p, origin, fs):
    return float(np.max(np.abs(item_db(p.item, origin, fs) - placed_db(p, fs))))


def preselect(group, origin, fs):
    """The items with the largest effect that map together (Map, when not all of them do)."""
    chosen = []
    for i in sorted(group, key=lambda i: -float(np.max(np.abs(item_db(i, origin, fs))))):
        if not mapping(chosen + [i], origin, fs).reason:
            chosen.append(i)
    return chosen


# -- curves ----------------------------------------------------------------------------------------

def item_db(i, origin, fs, freqs=F.FREQS):
    """The curve an item stands for: a Cookbook biquad (External), or as the device makes it (ADI-2, a table row).
    freqs: where; where curves are compared, by default."""
    cookbook = origin == EXTERNAL and i.target is None
    flt = F.Filter("", None, i.kind, i.freq, i.gain, i.q, True, None, None)
    return F.response_db(flt, freqs, fs, cookbook=cookbook)


def placed_db(p, fs, freqs=F.FREQS):
    return F.response_db(F.Filter("", None, p.kind, p.freq, p.gain, p.q, True, None, None), freqs, fs)


def target(group, origin, fs, freqs=F.FREQS):
    """The curve of a group of items: what Fit fits."""
    return sum((item_db(i, origin, fs, freqs) for i in group), np.zeros(len(freqs)))


def fit_start(m):
    """A mapping as a start for eqfit, or None when it does not map."""
    if m.reason:
        return None
    return [X.Setting(str(t) if t in BANDS else t[0], p.kind, p.freq, p.gain, p.q) for t, p in m.placed.items()]


def from_fit(result):
    """eqfit's Result as placed filters: {target: Placed}; without the bands left at 0 dB (a High Pass or High Cut
    has no gain and is never flat)."""
    out = {}
    for s in result.settings:
        if s.gain == 0 and s.kind not in NO_GAIN:
            continue
        t = int(s.name) if s.name.isdigit() else {"B": "Bass", "T": "Treble"}[s.name]
        out[t] = Placed(None, t, s.kind, s.freq, s.gain, s.q, [])
    return out


# -- the outcome -----------------------------------------------------------------------------------

def addresses(out, dual):
    """{block: address} of the EQ blocks of an output: 'L' and 'R' with Dual EQ, else 'all' (on the left)."""
    _, _, left, right = P.channel(out)
    return {"L": left, "R": right} if dual else {"all": left}


def shown(outcome, out, dual):
    """The values of what the outcome sets, {(address, index): increment}: the bands of each EQ block and Bass/Treble.
    outcome: {block: {target: Placed}}."""
    left = P.channel(out)[2]
    values = {}
    for block, addr in addresses(out, dual).items():
        for t, p in outcome.get(block, {}).items():
            values.update(_values(addr, t, p))
    for t, p in outcome.get("BT", {}).items():
        values.update(_values(left, t, p))
    return values


def _values(addr, target, p):
    gi, fi, qi = indices(target)
    v = {(addr, gi): round(p.gain * 2), (addr, fi): int(p.freq), (addr, qi): round(p.q * 10)}
    if target in BANDS and P.BANDS[target][0] is not None:
        v[(addr, P.BANDS[target][0])] = list(P.TYPE_ABBR[target]).index(p.kind)
    return v


def writes(outcome, out, dual, blocks):
    """What OK writes for the blocks taken to the device: every band of each, the undefined ones at their factory
    default; Bass and Treble likewise."""
    left = P.channel(out)[2]
    defined = shown(outcome, out, dual)
    values = {}
    for block, addr in addresses(out, dual).items():
        if block in blocks:
            for band in BANDS:
                for i in P.BANDS[band]:
                    if i is not None:
                        values[(addr, i)] = defined.get((addr, i), P.FACTORY_BANDS[i])
    if "BT" in blocks:
        for i in P.BASS + P.TREBLE:
            values[(left, i)] = defined.get((left, i), P.FACTORY_BT[i])
    return values


def changes(state, values):
    """The values that differ from the device."""
    return {k: v for k, v in values.items() if state.get(k) != v}


def apply(session, values):
    """Queue the values that differ from the device on a Session."""
    for key, v in sorted(changes(session.state, values).items()):
        session.set(key, v)


def _half_up(x):
    return int(math.floor(x + 0.5))


def _capital(text):
    return text[:1].upper() + text[1:]
