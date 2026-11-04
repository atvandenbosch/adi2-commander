"""The filter model: the device's filter shapes, the sum, Loudness, and the mapping from a state to filters."""

import unittest

import numpy as np

from commander.device import filters as F
from tests.support import dump_state

FREQS = np.logspace(np.log10(10), np.log10(22000), 4000)


def flt(kind, f0, gain, q, active=True):
    return F.Filter("1", 1, kind, f0, gain, q, active, 4, (None, 4, 5, 6))


class Shapes(unittest.TestCase):
    def test_high_pass_resonance(self):
        # High Pass 100 Hz: (Q, at 100 Hz, maximum or None, at 50 Hz, at 25 Hz)
        for q, at100, peak, at50, at25 in ((0.5, -6.0, None, -14.0, -24.6), (0.7, -3.1, None, -12.3, -24.1),
                                           (1, 0.0, 1.3, -11.1, -23.8), (2, 6.0, 6.3, -10.0, -23.6)):
            f = flt("HP", 100, 6, q)                               # the gain does nothing on a High Pass
            np.testing.assert_allclose(F.response_db(f, [100, 50, 25]), [at100, at50, at25], atol=0.051)
            top = F.response_db(f, FREQS).max()
            if peak is None:
                self.assertLess(top, 0.01)
            else:
                self.assertAlmostEqual(top, peak, delta=0.06)
            np.testing.assert_allclose(F.response_db(f, FREQS), F.response_db(flt("HP", 100, -12, q), FREQS))

    def test_shelf_overshoot(self):
        # Low shelf 200 Hz, +6 dB: (Q, overshoot, counter-dip)
        for q, over, dip in ((1, 6.4, -0.4), (1.5, 7.6, -1.6), (3, 11.1, -5.1)):
            r = F.response_db(flt("LS", 200, 6, q), FREQS)
            self.assertAlmostEqual(r.max(), over, delta=0.051)
            self.assertAlmostEqual(r.min(), dip, delta=0.051)

    def test_peak_reaches_its_gain_at_f0(self):
        for fs in (44100.0, 48000.0):
            for f0 in (20, 1000, 19990):
                self.assertAlmostEqual(F.response_db(flt("PK", f0, -7.5, 9.9), [f0], fs)[0], -7.5, places=6)

    def test_sum_leaves_out_what_is_not_in_the_path(self):
        on, off = flt("PK", 1000, 6, 1), flt("PK", 100, -6, 1, active=False)
        np.testing.assert_allclose(F.total_db([on, off], FREQS), F.response_db(on, FREQS))
        np.testing.assert_allclose(F.total_db([on, on], FREQS), 2 * F.response_db(on, FREQS))


class CookbookQ(unittest.TestCase):
    def test_both_device_qs_give_the_cookbook_curve(self):
        for fs in (44100.0, 48000.0):
            for f0, q in ((100, 0.7), (8000, 2), (16000, 0.7)):
                qs = F.device_qs(q, f0, fs)
                self.assertEqual(len(qs), 2)
                for kind in ("PK", "LS", "HP"):
                    cookbook = F.response_db(flt(kind, f0, 6, q), FREQS, fs, cookbook=True)
                    for qd in qs:
                        self.assertAlmostEqual(F.cookbook_q(qd, f0, fs), q, places=9)
                        np.testing.assert_allclose(F.response_db(flt(kind, f0, 6, qd), FREQS, fs), cookbook,
                                                   atol=1e-6)

    def test_none_broader_than_the_device_makes(self):
        self.assertEqual(F.device_qs(0.46, 15000, 48000.0), [])          # 2 Q < sin(w0) = 0.924
        self.assertEqual(len(F.device_qs(0.47, 15000, 48000.0)), 2)


class FromState(unittest.TestCase):
    def setUp(self):
        self.state = dump_state()

    def test_bands_of_the_dump(self):
        left = F.band_filters(self.state, 4, 4)
        self.assertEqual([(f.name, f.kind, f.freq, f.gain, f.q, f.active) for f in left],
                         [("1", "LS", 60, -3.0, 0.7, True), ("2", "PK", 150, -8.0, 4.0, True),
                          ("3", "PK", 400, -3.0, 2.0, True), ("4", "PK", 200, -2.0, 5.0, True),
                          ("5", "PK", 3000, -1.5, 5.0, True)])
        right = F.band_filters(self.state, 5, 4)
        self.assertEqual([(f.freq, f.gain, f.q) for f in right][:2], [(40, -6.0, 6.0), (180, -7.0, 9.9)])
        self.assertEqual(left[0].indices, (3, 4, 5, 6))
        self.assertEqual(right[1].indices, (None, 7, 8, 9))

    def test_eq_enable_per_channel(self):
        active = lambda a: [f.active for f in F.band_filters(self.state, a, 4)]   # noqa: E731
        for l, r in ((0, 1), (1, 0), (0, 0), (1, 1)):     # the front panel's R, L, OFF, ON
            self.state[(4, 2)], self.state[(5, 2)] = l, r
            self.assertEqual((active(4), active(5)), ([bool(l)] * 5, [bool(r)] * 5))

    def test_types_of_band_1_and_5(self):
        self.state[(4, 3)], self.state[(4, 16)] = 2, 1
        bands = F.band_filters(self.state, 4, 4)
        self.assertEqual((bands[0].kind, bands[4].kind), ("HP", "HS"))
        self.state[(4, 3)], self.state[(4, 16)] = 1, 2
        bands = F.band_filters(self.state, 4, 4)
        self.assertEqual((bands[0].kind, bands[4].kind), ("LS", "LP"))

    def test_bass_treble_shared_and_switched(self):
        bt = F.bt_filters(self.state, 4)
        self.assertEqual([(f.name, f.kind, f.freq, f.gain, f.q, f.active) for f in bt],
                         [("B", "LS", 85, 0.0, 0.9, False), ("T", "HS", 6500, 0.0, 0.7, False)])
        self.state[(4, 20)] = 1
        self.assertTrue(all(f.active for f in F.bt_filters(self.state, 4)))

    def test_incomplete_state_gives_nothing(self):
        del self.state[(4, 14)]
        self.assertEqual(F.band_filters(self.state, 4, 4), [])
        self.assertEqual(F.bt_filters({}, 4), [])


class Loudness(unittest.TestCase):
    def test_full_at_and_below_low_vol_ref_none_20_db_above(self):
        np.testing.assert_allclose(F.loudness_gain(10, -20, [-40, -20, -15, -10, -5, 0, 6]),
                                   [10, 10, 7.5, 5, 2.5, 0, 0])             # the curves of manual 31.6

    def test_shelves_match_the_manual(self):
        """+10 dB (volume -20 dB, Low Vol Ref -20 dB), against the curve read off manual 31.6 (±1.2 dB)."""
        state = {(3, 20): 1, (3, 21): 20, (3, 22): 20, (3, 23): -40, (3, 12): -200}
        f = [20, 50, 100, 200, 500, 2000, 5000, 20000]
        np.testing.assert_allclose(F.total_db(F.loudness_filters(state, 3), f),
                                   [10, 6.6, 2.2, 0.3, 0, 1.0, 7.8, 10], atol=1.2)

    def test_at_many_volumes_in_one_go(self):
        state = {(3, 20): 1, (3, 21): 14, (3, 22): 20, (3, 23): -60, (3, 12): -200}
        f, volumes = np.geomspace(20, 20000, 50), [-45, -30, -24.5, -10, 0]
        for fs in (44100, 192000):
            each = [F.total_db([s._replace(active=True) for s in F.loudness_filters(state, 3, volume=v)], f, fs)
                    for v in volumes]
            np.testing.assert_allclose(F.loudness_db(state, 3, volumes, f, fs), each, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
