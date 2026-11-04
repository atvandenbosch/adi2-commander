"""From a curve to a device setting: the bands, a setting found back from its own curve, the level, the same setting
at any level, the best on the grid, random starts, Bass and Treble, a start that is not lost, the grid, progress, what
is tried and cancelling."""

import unittest

from commander.conversion import eqfit as X
from commander.device import filters as F
from commander.device import params as P

S = X.Setting
FIVE = [S("1", "LS", 80, 4.0, 0.7), S("2", "PK", 250, -3.0, 1.4), S("3", "PK", 1200, 2.5, 2.0),
        S("4", "PK", 3500, -4.0, 3.0), S("5", "HS", 9000, -2.0, 0.8)]
TONE = FIVE + [S("B", "LS", 100, 3.0, 0.9), S("T", "HS", 5000, -2.0, 0.7)]
# a resonant High Cut, with a shelf and peaks near and above it
STEEP = [S("1", "LP", 2860, 0.0, 9.2), S("2", "PK", 16680, -7.5, 2.0), S("3", "PK", 87, 6.0, 7.0),
         S("4", "PK", 10100, 8.5, 4.1), S("5", "HS", 4170, 11.0, 4.3)]


def on_device(test, settings, tone):
    """Every band once, in order, with a kind it takes and values on its grid."""
    sl = X.slots(tone)
    test.assertEqual([x.name for x in settings], [s.name for s in sl])
    for x, s in zip(settings, sl):
        test.assertIn(x.kind, s.kinds)
        test.assertEqual(x.freq, P.snap_freq(x.freq, s.fi))
        test.assertTrue(s.flo <= x.freq <= s.fhi)
        test.assertEqual(x.gain * 2, round(x.gain * 2))
        test.assertTrue(-12 <= x.gain <= 12)
        if x.kind in X.NO_GAIN:
            test.assertEqual(x.gain, 0)
        test.assertAlmostEqual(x.q * 10, round(x.q * 10))
        test.assertTrue(s.qlo <= x.q <= s.qhi)


class Bands(unittest.TestCase):
    def test_as_the_device(self):
        sl = {s.name: s for s in X.slots(True)}
        self.assertEqual(sl["1"].kinds, ("PK", "LS", "HP", "LP"))
        self.assertEqual(sl["5"].kinds, ("PK", "HS", "LP"))
        self.assertEqual((sl["4"].flo, sl["4"].qhi), (200, 5.0))
        self.assertEqual((sl["B"].kinds, sl["B"].fhi, sl["T"].flo), (("LS",), 150, 3000))
        self.assertEqual([s.name for s in X.slots(False)], ["1", "2", "3", "4", "5"])


class FoundBack(unittest.TestCase):
    """The curve of five bands, 3 dB up: the same filters back, 3 dB quieter than the curve."""

    @classmethod
    def setUpClass(cls):
        cls.calls, cls.tried = [], []
        cls.target = X.response(FIVE) + 3.0
        cls.r = X.fit(cls.target, progress=lambda done, r: cls.calls.append((done, r)), candidate=cls.tried.append)

    def test_a_best_so_far_onto_the_grid(self):
        first = self.calls[0][1]
        on_device(self, X.to_grid(first.settings, self.target).settings, False)

    def test_found_back(self):
        self.assertLess(self.r.rms, 0.01)
        self.assertEqual(sorted(tuple(x)[1:] for x in self.r.settings), sorted(tuple(x)[1:] for x in FIVE))

    def test_level(self):
        self.assertAlmostEqual(self.r.level, -3.0, places=3)

    def test_on_device(self):
        on_device(self, self.r.settings, False)

    def test_progress(self):
        done = [d for d, _ in self.calls]
        self.assertEqual(done, sorted(done))
        self.assertEqual(done[-1], 1.0)
        self.assertTrue(all(isinstance(r, X.Result) for _, r in self.calls))

    def test_what_is_tried(self):
        self.assertTrue(self.tried)
        self.assertTrue(all(isinstance(r, X.Result) for r in self.tried))
        self.assertGreater(max(r.rms for r in self.tried), self.r.rms)     # better or not


class Level(unittest.TestCase):
    def test_the_same_setting_at_any_level(self):
        # six filters: a curve the five bands cannot make, so the search decides where it ends
        target = X.response(FIVE) + X.response([S("2", "PK", 600, 5.0, 4.0)])
        r, up = X.fit(target), X.fit(target + 8.0)
        self.assertEqual(up.settings, r.settings)
        self.assertAlmostEqual(up.level, r.level - 8.0, places=6)
        self.assertGreater(r.rms, 0.01)


class Grid(unittest.TestCase):
    def test_the_best_on_the_grid(self):
        # seven filters from a file: the best before the grid is not the best on it
        fs = 384000.0
        file = [("LS", 105, -5.54, 0.7), ("HS", 10000, 0.7, 0.7), ("PK", 56.08, -2.98, 4.97), ("PK", 21.1, 1.75, 2.47),
                ("PK", 5490.5, -0.55, 5.25), ("PK", 31.22, -0.55, 2.46), ("PK", 149.73, 4.33, 2.56)]
        target = sum(F.response_db(F.Filter("", None, k, f, g, q, True, None, None), F.FREQS, fs, cookbook=True)
                     for k, f, g, q in file)
        calls = []
        r = X.fit(target, fs, progress=lambda done, best: calls.append(best))
        self.assertLess(r.rms, X.to_grid(calls[-1].settings, target, fs).rms - 0.005)
        on_device(self, r.settings, False)


class RandomStarts(unittest.TestCase):
    def test_found_where_the_fixed_starts_end_beside_it(self):
        # a resonant High Pass under peaks and a shelf
        given = [S("1", "HP", 403, 0.0, 3.6), S("2", "PK", 152, 5.5, 1.7), S("3", "PK", 71, 4.5, 2.1),
                 S("4", "PK", 5370, 11.0, 1.5), S("5", "HS", 5720, 2.5, 4.5)]
        r = X.fit(X.response(given))
        self.assertLess(r.rms, 0.01)
        on_device(self, r.settings, False)


class Tone(unittest.TestCase):
    def test_bass_and_treble_take_part(self):
        r = X.fit(X.response(TONE), tone=True)
        on_device(self, r.settings, True)
        self.assertLess(r.rms, 0.05)


class Starts(unittest.TestCase):
    def test_a_start_is_not_lost(self):
        r = X.fit(X.response(STEEP, 44100.0), 44100.0, starts=[STEEP])
        self.assertLess(r.rms, 1e-6)
        on_device(self, r.settings, False)

    def test_a_start_fills_the_bands_it_leaves(self):
        kinds, vals = X._start(X.slots(True), [S("2", "PK", 1000.4, 3.26, 1.04)])
        self.assertEqual(kinds, ["PK"] * 5 + ["LS", "HS"])
        self.assertEqual(vals[1], (1000, 3.5, 1.0))
        self.assertEqual([g for _, g, _ in vals[:1] + vals[2:]], [0.0] * 6)

    def test_a_start_must_fit_the_bands(self):
        with self.assertRaises(ValueError):
            X.fit(X.response(FIVE), starts=[[S("B", "LS", 100, 3.0, 0.9)]])
        with self.assertRaises(ValueError):
            X.fit(X.response(FIVE), starts=[[S("2", "LS", 100, 3.0, 0.9)]])


class Cancel(unittest.TestCase):
    def test_at_once(self):
        with self.assertRaises(X.Cancelled):
            X.fit(X.response(FIVE), cancel=lambda: True)

    def test_while_searching(self):
        calls = []
        with self.assertRaises(X.Cancelled):
            X.fit(X.response(FIVE), progress=lambda done, r: calls.append(done), cancel=lambda: bool(calls))
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
