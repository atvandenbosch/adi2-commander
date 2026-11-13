r"""EQ settings as a file: Commander's own files back to exactly the same device setting, and the meaning of
REW exports and APO configurations.

The REW exports in data\ are from REW V5.40 Beta 134 (File > Export > Export filter settings as text).
The expected values for REW and APO come from REW itself and from APO's source, not from this module.
"""

import codecs
import datetime
import itertools
import math
import os
import tempfile
import unittest

from commander import __version__
from commander.conversion import eqfile as E
from commander.device import filters as F
from commander.device import models
from commander.device import params as P
from tests.support import DATA, TEN_FILTERS, dump_state

OUT, LEFT, RIGHT = 3, 4, 5                       # Line Out
FS = (44100.0, 48000.0, 96000.0, 192000.0)


def eq_keys(state, out):
    """The keys of one output that a file carries."""
    _, _, left, right = next(o for o in P.OUTPUTS if o[1] == out)
    keys = {(out, P.DUAL_EQ), (left, P.BT_ENABLE)}
    for addr in (left, right) if state[(out, P.DUAL_EQ)] == 1 else (left,):
        keys |= {(addr, i) for i in range(2, 20)}
    keys |= {(left, i) for i in P.BASS + P.TREBLE}
    return keys


def table_state(eq, out):
    """What the table of a Commander file says, as the setting of one output."""
    _, _, left, right = next(o for o in P.OUTPUTS if o[1] == out)
    rows = E.table(eq)
    addr = {"L": left, "R": right, "all": left}
    state = {(out, P.DUAL_EQ): 1 if any(r.channel in ("L", "R") for r in rows) else 0}
    for r in rows:
        if r.target in ("Bass", "Treble"):
            a, (gi, fi, qi) = left, (P.BASS if r.target == "Bass" else P.TREBLE)
            state[(left, P.BT_ENABLE)] = 1 if r.on else 0
        else:
            a, (ti, gi, fi, qi) = addr[r.channel], P.BANDS[r.target]
            if ti is not None:
                state[(a, ti)] = P.TYPE_ABBR[r.target].index(E.DEVICE_KIND[r.type])
            state[(a, P.EQ_ENABLE)] = 1 if r.on else 0
        state[(a, gi)], state[(a, fi)], state[(a, qi)] = round(r.gain * 2), int(r.freq), round(r.q * 10)
    return state


class RoundTrip(unittest.TestCase):
    """Write and read back: exactly the same device setting, at every sample rate."""

    def round_trip(self, state, out=OUT, fs=48000.0):
        eq = E.read(E.write(state, out, fs), 44100.0 if fs != 44100.0 else 48000.0)   # the file's own fs counts
        self.assertEqual(eq.source, "commander")
        self.assertEqual(eq.fs, fs)
        self.assertIsNotNone(E.table(eq))
        expected = {k: state[k] for k in eq_keys(state, out)}
        self.assertEqual(table_state(eq, out), expected)
        self.assertEqual(E.disagreeing(eq), set())               # the Filter lines say the same
        return eq

    def test_the_dump_of_every_output(self):
        state = dump_state()
        for _, out, _, _ in P.OUTPUTS:
            for fs in FS:
                self.round_trip(state, out, fs)

    def test_every_value_on_the_grid(self):
        """Every gain, Q and type of every band, every third frequency step (every seventh with Dual), B/T
        and switches, Shared and Dual, at four sample rates: one file per frequency, the rest cycling along.
        Every single frequency would add nothing: the precision is in the '%.4f' of the Q."""
        base = dump_state()
        for fs in FS:
            n = 0
            for dual in (0, 1):
                state = dict(base)
                state[(OUT, P.DUAL_EQ)] = dual
                for addr in (LEFT, RIGHT):
                    for band, (ti, gi, fi, qi) in P.BANDS.items():
                        freqs = [f for f in range(P.EQ_RANGES[fi][0], P.EQ_RANGES[fi][1] + 1) if P.snap_freq(f, fi) == f]
                        gains = itertools.cycle(range(P.EQ_RANGES[gi][0], P.EQ_RANGES[gi][1] + 1))
                        qs = itertools.cycle(range(P.EQ_RANGES[qi][0], P.EQ_RANGES[qi][1] + 1))
                        types = itertools.cycle(range(len(P.BAND_TYPES.get(band, [0]))))
                        for step, f in enumerate(freqs):
                            if step % (7 if dual else 3):        # all of them in Shared, a sample in Dual
                                continue
                            s = dict(state)
                            s[(addr, fi)], s[(addr, gi)], s[(addr, qi)] = f, next(gains), next(qs)
                            if ti is not None:
                                s[(addr, ti)] = next(types)
                            s[(addr, P.EQ_ENABLE)] = step % 2
                            s[(LEFT, P.BT_ENABLE)] = (step // 2) % 2
                            for gi2, fi2, qi2 in (P.BASS, P.TREBLE):
                                lo, hi = P.EQ_RANGES[fi2]
                                s[(LEFT, fi2)] = lo + step % (hi - lo + 1)
                                s[(LEFT, gi2)] = -24 + step % 49
                                s[(LEFT, qi2)] = 5 + step % 11
                            if addr == RIGHT and not dual:
                                continue                         # the right set is an alias then
                            self.round_trip(s, OUT, fs)
                            n += 1
            self.assertGreater(n, 3000)

    def test_two_device_qs_with_one_curve(self):
        """Q 0.5 at 15 kHz and some higher Q have the same Cookbook Q at 48 kHz: the comment decides."""
        fs, f = 48000.0, 15000
        w0 = 2 * math.pi * f / fs
        q_other = w0 / (2 * (math.pi - math.asin(math.sin(w0 / (2 * 0.5)))))
        self.assertAlmostEqual(F.cookbook_q(0.5, f, fs), F.cookbook_q(q_other, f, fs), places=9)
        state = dump_state()
        state[(LEFT, 14)], state[(LEFT, 15)] = f, 5
        self.round_trip(state, OUT, fs)

    def test_file_is_english_ascii_and_valid_apo(self):
        text = E.write(dump_state(), 9, 48000.0, datetime.datetime(2026, 10, 6, 14, 32))
        text.encode("ascii")
        self.assertTrue(text.startswith("# ADI-2 Commander %s\n# Date: 2026-10-06 14:32\n# Device: RME ADI-2 DAC FS\n"
                                        "# Output: Phones 3/4 - IEM\n# Settings: EQ, Bass/Treble\n#\n" % __version__))
        self.assertIn("\n#\n# %s\n# Converted to RBJ Cookbook biquads at 48 kHz, Equalizer APO format:\n" % ("-" * 66),
                      text)
        self.assertEqual(E.read(text).output, "Phones 3/4 - IEM")
        eq = E.read("# as APO sees it\n" + text)                         # not Commander's: the table is a comment
        self.assertEqual(eq.source, "apo")
        self.assertEqual(eq.skipped, [])
        self.assertGreaterEqual(len(eq.entries), 7)

    def test_the_input_without_bass_treble(self):
        dump = dump_state()
        state = {(a - 3, i): v for (a, i), v in dump.items() if a in (LEFT, RIGHT) and i < P.BT_ENABLE}
        state[P.INPUT_DUAL_EQ] = dump[(OUT, P.DUAL_EQ)]                # Line Out's EQ, on the input
        text = E.write(state, P.INPUT_ADDRESS, 48000.0, model=models.PRO_24)
        self.assertIn("\n# Device: RME ADI-2/4 Pro\n# Input: Analog In\n# Settings: EQ\n#\n", text)
        self.assertNotIn("Bass/Treble", text)
        eq = E.read(text)
        self.assertEqual((eq.output, len(eq.entries)), ("Analog In", 10 if state[P.INPUT_DUAL_EQ] else 5))
        self.assertIsNotNone(E.table(eq))
        with self.assertRaises(ValueError):
            E.write(state, OUT, 48000.0)                                 # an output without Bass/Treble

    def test_a_preset_names_itself_instead_of_the_output(self):
        text = E.write(dump_state(), OUT, 48000.0, preset=(3, "Studio"))
        self.assertIn("\n# Preset: 3 (Studio)\n", text)
        self.assertNotIn("# Output:", text)
        self.assertIsNone(E.read(text).output)                           # no "Exported from" in Import
        self.assertIn("\n# Preset: 3\n", E.write(dump_state(), OUT, 48000.0, preset=(3, "")))

    def test_readable_table_first_one_row_per_band(self):
        lines = E.write(dump_state(), OUT, 48000.0).splitlines()
        rows = [l for l in lines if E.ROW.match(l)]
        self.assertEqual(len(rows), 12)                                  # Dual EQ: 2 x 5 bands, Bass, Treble
        heads = [l for l in lines if E.GROUP_HEAD.match(l)]
        self.assertEqual(heads, ["# EQ Left", "# EQ Right", "# Bass/Treble (off)"])   # the groups of the app
        self.assertEqual(lines.index(heads[0]) + 1, lines.index(rows[0]))           # a row starts with its band
        self.assertEqual(rows[0].split()[1:5], ["Band", "1", "Low", "Shelf"])       # a shelf with its side
        self.assertLess(lines.index(rows[-1]), next(i for i, l in enumerate(lines) if l.startswith("Filter")))
        self.assertFalse([l for l in lines if l.startswith("# commander")])

    def test_the_type_column_is_as_wide_as_its_longest_type(self):
        state = dump_state()                                             # Low Shelf the longest
        before = E.write(state, OUT, 48000.0).splitlines()
        state[(LEFT, P.BANDS[5][0])] = 1                                 # then High Shelf, one longer
        after = E.write(state, OUT, 48000.0).splitlines()
        width = {len(l) for l in before if E.ROW.match(l)}
        self.assertEqual(len(width), 1)                                  # the columns line up
        self.assertEqual({len(l) for l in after if E.ROW.match(l)}, {width.pop() + 1})

    def test_the_table_counts_when_a_filter_line_is_edited(self):
        text = E.write(dump_state(), OUT, 48000.0)
        lines = text.splitlines()
        i = next(n for n, l in enumerate(lines) if l.startswith("Filter 2:"))
        lines[i] = lines[i].replace(" Gain ", " Gain 1").replace("Gain 1-", "Gain -1")
        eq = E.read("\n".join(lines))
        self.assertEqual(table_state(eq, OUT), {k: dump_state()[k] for k in eq_keys(dump_state(), OUT)})
        self.assertEqual(E.disagreeing(eq), {i + 1})

    def test_a_comma_in_the_table_is_a_decimal_point(self):
        lines = E.write(dump_state(), OUT, 48000.0).splitlines()
        rows = [n for n, l in enumerate(lines) if E.ROW.match(l)]
        lines[rows[0]] = lines[rows[0]].replace(".", ",")                # gain and Q
        eq = E.read("\n".join(lines))
        self.assertEqual(table_state(eq, OUT), {k: dump_state()[k] for k in eq_keys(dump_state(), OUT)})
        self.assertEqual(E.disagreeing(eq), set())

    def test_a_table_that_is_not_whole_does_not_count(self):
        lines = E.write(dump_state(), OUT, 48000.0).splitlines()
        rows = [n for n, l in enumerate(lines) if E.ROW.match(l)]
        self.assertIsNone(E.table(E.read("\n".join(l for n, l in enumerate(lines) if n != rows[1]))))
        self.assertIsNone(E.table(E.read("\n".join(lines).replace("Peak", "Peak  x", 1))))
        self.assertEqual([r.on for r in E.table(E.read("\n".join(lines)))][-2:], [False, False])   # B/T off
        self.assertIsNone(E.table(E.read("\n".join(lines).replace("Low Shelf", "High Shelf", 1))))  # not on band 1
        self.assertIsNone(E.table(E.read("\n".join(l for l in lines if l != "# EQ Left"))))       # under no group

    def test_the_rows_that_keep_a_table_from_counting(self):
        lines = E.write(dump_state(), OUT, 48000.0).splitlines()
        rows = [n for n, l in enumerate(lines) if E.ROW.match(l)]
        self.assertEqual(E.table_faults(E.read("\n".join(lines))), {})
        cases = [(rows[1], " dB", "x dB", "Gain is not a number"),
                 (rows[0], "Low Shelf", "High Shelf", "Band 1 has no High Shelf"),
                 (rows[2], "Peak", "    ", "No type"),
                 (rows[2], "Band 3", "Band 2", "Band 2 twice in its group")]
        for n, old, new, why in cases:
            edited = list(lines)
            edited[n] = edited[n].replace(old, new, 1)
            eq = E.read("\n".join(edited))
            self.assertEqual(E.table_faults(eq), {n + 1: why}, why)
            self.assertIsNone(E.table(eq))
        eq = E.read("\n".join(l for l in lines if l != "# EQ Left"))
        self.assertEqual(set(E.table_faults(eq).values()), {"Under no group"})
        eq = E.read("\n".join(l for n, l in enumerate(lines) if n != rows[1]))   # a row missing: no line to point at
        self.assertEqual(E.table_faults(eq), {})
        self.assertIsNone(E.table(eq))

    def test_incomplete_state(self):
        with self.assertRaises(ValueError):
            E.write({(OUT, P.DUAL_EQ): 0}, OUT)


class Rew(unittest.TestCase):
    def load(self, name):
        return E.load(os.path.join(DATA, name), 48000.0)

    def test_generic(self):
        eq = self.load("rew-generic.txt")
        self.assertEqual((eq.source, eq.equaliser, eq.warnings), ("rew", "Generic", []))
        got = [(e.kind, round(e.freq, 2), e.gain, round(e.q, 4), e.on) for e in eq.entries]
        r = round(math.sqrt(0.5), 4)
        self.assertEqual(got[:4], [("PK", 1000.0, -3.5, 2.0, True), ("PK", 63.4, 4.3, 7.123, False),
                                   ("LS", 100.0, 6.0, r, True), ("HS", 8000.0, -4.0, r, True)])
        self.assertEqual(got[6:], [("HP", 30.0, 0.0, r, True), ("LP", 18000.0, 0.0, r, True),
                                   ("PK", 45.0, -6.0, 4.347, True), ("PK", 12346.0, 11.5, 0.5, True)])
        self.assertEqual([(s.line, s.reason) for s in eq.skipped], [(18, "HP1: not on the device")])

    def test_fixed_slope_shelves(self):
        """Centre and Q of REW's own curves (48 kHz): S 0.5 and 1 at the corner, prewarped."""
        head = "Filter Settings file\n\nEqualiser: Generic\nflat\n"
        expected = [("LS 6dB", 200, 6, 282.50, 0.4926), ("LS 12dB", 200, 6, 237.71, 0.7070),
                    ("HS 6dB", 5000, -6, 3603.84, 0.4926), ("HS 12dB", 5000, 6, 4250.79, 0.7070),
                    ("HS 6dB", 2000, -6, 1420.05, 0.4926), ("LS 6dB", 5000, 6, 6832.06, 0.4926)]
        for typ, fc, g, centre, q in expected:
            e = E.read(head + "Filter  1: ON  %s Fc %.2f Hz  Gain %.1f dB\n" % (typ, fc, g), 48000.0).entries[0]
            self.assertAlmostEqual(e.freq / centre, 1, delta=2e-4, msg=typ)
            self.assertAlmostEqual(e.q, q, delta=1e-3, msg=typ)

    def test_extended(self):
        eq = self.load("rew-extended.txt")
        self.assertEqual(eq.equaliser, "Extended")
        got = [(e.kind, e.freq, e.gain, e.q, e.on) for e in eq.entries]
        self.assertEqual(got, [("PK", 1000.0, -3.5, 2.0, True), ("LS", 100.0, 6.0, 1.5, False),
                               ("HS", 8000.0, -4.0, 0.9, True), ("HP", 30.0, 0.0, 0.5, True),
                               ("LP", 18000.0, 0.0, 2.0, True), ("PK", 63.4, 4.3, 7.123, True)])
        self.assertEqual([s.reason.split(":")[0] for s in eq.skipped], ["Notch", "All pass"])

    def test_fbq2496_is_read_with_a_warning(self):
        eq = self.load("rew-fbq2496.txt")
        self.assertEqual(len(eq.warnings), 1)
        self.assertEqual([(e.freq, round(e.q, 3)) for e in eq.entries], [(1002.3, 1.902), (63.2, 7.208)])


class Apo(unittest.TestCase):
    """APO's meaning, from its parser (BiQuadFilterFactory.cpp, BiQuadFilter.cpp)."""

    def one(self, line, fs=48000.0):
        eq = E.read(line, fs)
        self.assertEqual(eq.skipped, [], line)
        return eq.entries[0]

    def test_types_and_defaults(self):
        e = self.one("Filter: ON PK Fc 50.0 Hz Gain -10.0 dB Q 2.50")
        self.assertEqual((e.kind, e.freq, e.gain, e.q), ("PK", 50.0, -10.0, 2.5))
        self.assertAlmostEqual(self.one("Filter: ON HP Fc 30.0 Hz").q, math.sqrt(0.5))
        self.assertEqual(self.one("Filter: ON LPQ Fc 10000 Hz Q 0.400").q, 0.4)
        self.assertEqual(self.one("Filter: ON Modal Fc 100 Hz Gain 3.0 dB Q 5.41 T60 target 100 ms").q, 5.41)
        e = self.one("Filter 1: ON LSC Fc 105 Hz Gain 6.4 dB Q 0.70")              # numbered, LSC with a Q
        self.assertEqual((e.kind, e.freq, e.q), ("LS", 105.0, 0.7))

    def test_shelf_without_q_is_s_09_at_the_centre(self):
        e = self.one("Filter: ON LS Fc 300 Hz Gain 6.0 dB")
        a = 10 ** (6 / 40)
        self.assertAlmostEqual(e.q, 1 / math.sqrt((a + 1 / a) * (1 / 0.9 - 1) + 2))
        self.assertEqual(e.freq, 300.0)

    def test_shelf_with_slope_or_q_but_no_c_is_at_the_corner(self):
        for line, s in (("Filter: ON LS 12dB Fc 200 Hz Gain 6.0 dB", 1.0), ("Filter: ON LS 6dB Fc 200 Hz Gain 6.0 dB", 0.5)):
            e = self.one(line)
            self.assertAlmostEqual(e.freq, 200 * 10 ** (6 / 80 / s), places=6)
        e = self.one("Filter: ON HS Fc 5000 Hz Gain 6.0 dB Q 0.7071")
        self.assertLess(e.freq, 5000)
        e = self.one("Filter: ON LSC 12 dB Fc 300 Hz Gain 5.0 dB")              # LSC with slope: the centre
        self.assertEqual(e.freq, 300.0)

    def test_bandwidth_in_octaves(self):
        e = self.one("Filter: ON PEQ Fc 1000 Hz Gain 1.0 dB BW Oct 1.0")
        w0 = 2 * math.pi * 1000 / 48000
        self.assertAlmostEqual(e.q, 1 / (2 * math.sinh(math.log(2) / 2 * w0 / math.sin(w0))))

    def test_numbers(self):
        self.assertEqual(self.one("Filter: ON PK Fc 1,5 Hz Gain -3,5 dB Q 2,0").gain, -3.5)
        self.assertEqual(self.one("Filter: ON PK Fc 1.000 Hz Gain 1 dB Q 1").freq, 1000.0)      # a thousand
        self.assertEqual(self.one("Filter: ON PK Fc 1 000 Hz Gain 1 dB Q 1").freq, 1000.0)
        self.assertEqual(self.one("Filter: ON PK Fc 63.40 Hz Gain 1 dB Q 1").freq, 63.4)

    def test_off_none_and_what_does_not_fit(self):
        eq = E.read("Preamp: -6.1 dB\nInclude: other.txt\nFilter: OFF PK Fc 100 Hz Gain 1 dB Q 1\n"
                    "Filter: ON None\nFilter: ON NO Fc 50 Hz\nFilter: ON PK Fc 100 Hz Gain 1 dB\n"
                    "GraphicEQ: 20 0; 40 1\n")
        self.assertEqual([e.on for e in eq.entries], [False])
        self.assertEqual(eq.preamp, [("all", -6.1, 1)])
        self.assertEqual([(s.line, s.reason) for s in eq.skipped],
                         [(2, "Include: not an EQ filter"), (5, "NO: not on the device"),
                          (6, "no Q or bandwidth"), (7, "GraphicEQ: not an EQ filter")])

    def test_a_filter_file_at_all(self):
        """Lines with a colon are no filter file; one line of APO or REW syntax is."""
        self.assertFalse(E.read("Date: 6 October\nFilters loaded: 12:30\nhttp://example.com\n").recognised)
        self.assertFalse(E.read("").recognised)
        self.assertFalse(E.read("# ADI-2 Commander — features\n\nSee: manual\n").recognised)
        for text in ("Include: other.txt\n", "GraphicEQ: 20 0; 40 1\n", "Preamp: -3 dB\n",
                     "Filter 1: OFF PK Fc 100 Hz Gain 1 dB Q 1\n", "Filter Settings file\n"):
            self.assertTrue(E.read(text).recognised, text)

    def test_malformed_numbers_are_skipped_not_fatal(self):
        eq = E.read("# ADI-2 Commander 0.1.0\n# Converted to RBJ Cookbook biquads at x kHz\n# EQ Left and Right\n#   Band 1  Peak   100 Hz   a dB   Q 1.0\n"
                    "Preamp: - dB\nFilter: ON PK Fc - Hz Gain 1 dB Q 1\nFilter 1: ON PK Fc 100 Hz Gain 1 dB Q 1\n")
        self.assertIsNone(eq.fs)
        self.assertEqual([s.line for s in eq.skipped], [5, 6])
        self.assertEqual([(e.freq, e.device) for e in eq.entries], [(100.0, None)])
        self.assertIsNone(E.table(eq))

    def test_channels(self):
        eq = E.read("Channel: L\nFilter: ON PK Fc 100 Hz Gain 1 dB Q 1\nChannel: 2\n"
                    "Filter: ON PK Fc 200 Hz Gain 1 dB Q 1\nChannel: C LFE\nFilter: ON PK Fc 300 Hz Gain 1 dB Q 1\n"
                    "Channel: L R\nFilter: ON PK Fc 400 Hz Gain 1 dB Q 1\n")
        self.assertEqual([(e.channel, e.freq) for e in eq.entries], [("L", 100.0), ("R", 200.0), ("all", 400.0)])
        self.assertEqual([s.line for s in eq.skipped], [5, 6])           # the channels, and a filter for them

    def test_ten_filters_and_a_preamp(self):
        eq = E.read(TEN_FILTERS)
        self.assertEqual((len(eq.entries), eq.skipped, eq.preamp), (10, [], [("all", -6.1, 1)]))
        self.assertIsNone(E.table(eq))


class Text(unittest.TestCase):
    def test_encodings(self):
        text = "Preamp: -3 dB\r\n# ±3 dB für links\r\n"
        cases = {"UTF-8": text.encode("utf-8"), "UTF-8 with BOM": text.encode("utf-8-sig"),
                 "UTF-16 LE": codecs.BOM_UTF16_LE + text.encode("utf-16-le"),
                 "UTF-16 BE": codecs.BOM_UTF16_BE + text.encode("utf-16-be"), "Windows-1252": text.encode("cp1252")}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "file.txt")
            for name, raw in cases.items():
                with self.subTest(name):
                    with open(path, "wb") as f:
                        f.write(raw)
                    self.assertEqual(E.text(path), text)


if __name__ == "__main__":
    unittest.main()
