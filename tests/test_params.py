"""Ranges, grid, steps and text input of the EQ parameters."""

import unittest

from commander.device import params as p


class Grid(unittest.TestCase):
    def test_snap(self):
        self.assertEqual(p.snap_freq(1234.4, 5), 1234)
        self.assertEqual(p.snap_freq(2044, 5), 2040)
        self.assertEqual(p.snap_freq(2046, 5), 2050)
        self.assertEqual(p.snap_freq(12345, 5), 12350)          # half up
        self.assertEqual(p.snap_freq(12346, 5), 12350)
        self.assertEqual(p.snap_freq(10, 5), 20)
        self.assertEqual(p.snap_freq(150, 14), 200)             # band 4 starts at 200 Hz
        self.assertEqual(p.snap_freq(30000, 5), 20000)

    def test_neighbours_across_2040(self):
        self.assertEqual([p.next_on_grid(f, +1) for f in (2039, 2040, 2050)], [2040, 2050, 2060])
        self.assertEqual([p.next_on_grid(f, -1) for f in (2060, 2050, 2040)], [2050, 2040, 2039])


class Loudness(unittest.TestCase):
    def test_apart_from_bass_treble(self):
        self.assertEqual(p.spec((3, 22)), ("out", 22))           # Treble Gain, not the Bass frequency
        self.assertEqual(p.spec((4, 22)), 22)
        self.assertEqual(p.to_text(p.spec((3, 22)), 14), "7.0")
        self.assertEqual(p.parse(p.spec((3, 23)), "-35"), (-70, False))
        self.assertEqual(p.parse(p.spec((3, 21)), "12"), (20, True))         # +10 dB is the limit
        self.assertEqual(p.step(p.spec((3, 23)), -40, +1), -40)              # -20 dB is the limit


class Output(unittest.TestCase):
    def test_width_as_the_device_shows_it_with_its_names(self):
        w = p.spec((3, p.WIDTH))
        self.assertEqual([p.to_text(w, v) for v in (100, 75, 0, -5, -100)],
                         ["Stereo", "0.75", "Mono", "-0.05", "Swapped"])
        self.assertEqual(p.spec((4, p.WIDTH)), p.WIDTH)                         # band 1 Freq on an EQ address

    def test_balance_as_the_device_shows_it(self):
        b = p.spec((3, p.BALANCE))
        self.assertEqual([p.to_text(b, v) for v in (-100, -7, 0, 30)], ["L 100", "L 7", "C", "R 30"])

    def test_what_is_written_on_an_output_address(self):
        for i in list(p.CHOICES) + [p.WIDTH, p.BALANCE, p.LOCK_VOLUME, p.VOLUME, p.REF_LEVEL, p.AUTO_REF_LEVEL,
                                    p.MUTE, p.DIM, p.SOURCE]:
            self.assertIn(i, p.OUTPUT_RANGES)
        self.assertEqual(p.OUTPUT_RANGES[p.SOURCE], (0, len(p.INPUTS) - 1))

    def test_ref_level_as_far_as_its_output_goes(self):
        self.assertEqual((p.limits((3, p.REF_LEVEL)), p.limits((6, p.REF_LEVEL))), ((0, 3), (0, 1)))
        self.assertEqual(p.limits((3, p.VOLUME)), (-1145, 60))
        self.assertEqual(p.limits((4, 4)), (-24, 24))                          # an EQ address as before

    def test_volume_steps_onto_the_half_dbs_whatever_the_size(self):
        v = p.spec((3, p.VOLUME))
        self.assertEqual([p.step(v, -215, +1, size) for size in ("small", "large", "finest")], [-210] * 3)
        self.assertEqual((p.step(v, -213, +1), p.step(v, -213, -1)), (-210, -215))    # off the grid: onto it
        self.assertEqual((p.step(v, 60, +1), p.step(v, -1145, -1)), (60, -1145))
        self.assertEqual(p.to_text(v, -215), "-21.5")
        self.assertEqual([p.kind(p.spec((3, i))) for i in (p.MUTE, p.DIM, p.AUTO_REF_LEVEL, p.REF_LEVEL)],
                         ["switch", "switch", "switch", "choice"])

    def test_volume_held_steps_grow_lower_down_the_devices_scale(self):
        levels = (0, -50, -55, -145, -150, -245, -250, -345, -350, -440, -445, -550, -555, -645, -650, -900)
        self.assertEqual([p.volume_held_step(v) for v in levels],
                         [10, 10, 20, 20, 25, 25, 35, 35, 45, 45, 55, 55, 65, 65, 80, 80])
        self.assertEqual((p.volume_held(-215, -1, 180), p.volume_held(-215, +1, 180)), (-225, -205))   # -3.5 dB
        self.assertEqual((p.volume_held(-215, -1), p.volume_held(-215, +1)), (-240, -190))             # -21.5 dB
        self.assertEqual((p.volume_held(-213, +1), p.volume_held(55, +1)), (-190, 60))     # onto the grid, the top
        self.assertEqual((p.volume_held(-960, -1, 0, -965), p.volume_held(-1000, -1, 0, -965)), (-965, -1000))

    def test_volume_on_the_devices_own_scale(self):
        state = {(3, p.AUTO_REF_LEVEL): 1, (3, p.REF_LEVEL): 0, (6, p.AUTO_REF_LEVEL): 1, (6, p.REF_LEVEL): 1,
                 (9, p.AUTO_REF_LEVEL): -1}
        self.assertEqual([p.volume_offset(state, o) for o in (3, 6, 9)], [180, 0, 0])   # -5 dBu, Hi-Power, IEM
        self.assertEqual([p.volume_floor(state, o) for o in (3, 6, 9)], [-1145, -1115, -965])
        state[(3, p.REF_LEVEL)] = 3
        self.assertEqual((p.volume_offset(state, 3), p.volume_floor(state, 3)), (0, -1145))   # +13 dBu
        state[(3, p.AUTO_REF_LEVEL)] = 0
        self.assertEqual((p.volume_offset(state, 3), p.volume_floor(state, 3)), (0, -965))


class Steps(unittest.TestCase):
    def test_frequency(self):
        self.assertEqual(p.step(5, 1000, +1, "large"), 1260)     # 1/3 octave
        self.assertEqual(p.step(5, 1000, +1), 1029)              # 1/24 octave
        self.assertEqual(p.step(5, 20, +1), 21)                  # at least one grid step
        self.assertEqual(p.step(5, 20, -1), 20)                  # the band limit holds
        self.assertEqual(p.step(5, 2040, +1, "finest"), 2050)
        self.assertEqual(p.step(5, 2050, -1, "finest"), 2040)
        self.assertEqual(p.step(14, 200, -1, "large"), 200)

    def test_gain_and_q(self):
        self.assertEqual(p.step(4, 0, +1), 1)                    # +0.5 dB
        self.assertEqual(p.step(4, 0, -1, "large"), -6)          # -3 dB
        self.assertEqual(p.step(4, 23, +1, "large"), 24)         # +12 dB is the limit
        self.assertEqual(p.step(15, 49, +1, "large"), 50)        # band 4 Q stops at 5.0
        self.assertEqual(p.step(6, 7, -1), 6)


class Text(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(p.parse(5, "1.2k"), (1200, False))
        self.assertEqual(p.parse(5, "1,2 kHz"), (1200, False))
        self.assertEqual(p.parse(5, "12344"), (12340, True))
        self.assertEqual(p.parse(18, "44"), (200, True))
        self.assertEqual(p.parse(4, "-3,5"), (-7, False))
        self.assertEqual(p.parse(4, "-3.7 dB"), (-7, True))
        self.assertEqual(p.parse(4, "15"), (24, True))
        self.assertEqual(p.parse(15, "9.9"), (50, True))
        with self.assertRaises(ValueError):
            p.parse(5, "abc")

    def test_to_text(self):
        self.assertEqual(p.to_text(5, 12340), "12340")
        self.assertEqual(p.to_text(4, -7), "-3.5")
        self.assertEqual(p.to_text(6, 7), "0.7")
        self.assertEqual(p.to_text(3, 2, band=1), "HP")
        self.assertEqual(p.to_text(3, 1, band=1), "LS")
        self.assertEqual(p.to_text(16, 1, band=5), "HS")
        self.assertEqual(p.to_text(16, 2, band=5), "LP")

    def test_limits(self):
        self.assertEqual((p.at_limit(4, -24), p.at_limit(4, 0), p.at_limit(15, 50)), (-1, 0, 1))


if __name__ == "__main__":
    unittest.main()
