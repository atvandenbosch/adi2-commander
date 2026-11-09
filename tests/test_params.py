"""Ranges, grid, steps and text input of the EQ parameters."""

import unittest

from commander.device import params as p
from commander.device.models import DAC, PRO, PRO_24


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


class Channels(unittest.TestCase):
    def test_the_input_and_the_outputs_with_their_eq_and_dual_eq(self):
        self.assertEqual([c[1:] for c in p.CHANNELS], [(0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11)])
        self.assertEqual(p.channel(9), p.OUTPUTS[2])
        self.assertEqual([p.dual_eq_key(out) for out in (0, 3, 6, 9)], [(0, 8), (3, 11), (6, 11), (9, 11)])
        self.assertNotEqual(p.dual_eq_key(0), (0, p.RIAA_MODE))                  # 0/11 is the input's RIAA Mode
        self.assertEqual([p.has_bt(out) for out in (0, 3, 6, 9)], [False, True, True, True])


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
                                    p.MUTE, p.DIM, p.SOURCE, p.DA_FILTER]:
            self.assertIn(i, p.OUTPUT_RANGES)
        self.assertEqual(p.OUTPUT_RANGES[p.SOURCE], (0, len(p.INPUTS) - 1))
        self.assertEqual(p.kind(p.spec((3, p.DA_FILTER))), "choice")

    def test_ref_level_as_far_as_its_output_goes(self):
        self.assertEqual((p.limits((3, p.REF_LEVEL)), p.limits((6, p.REF_LEVEL))), ((0, 3), (0, 1)))
        self.assertEqual(p.limits((3, p.VOLUME)), (-1145, 60))
        self.assertEqual(p.limits((4, 4)), (-24, 24))                          # an EQ address as before

    def test_the_da_filters_follow_the_d_a_converter(self):
        self.assertEqual([p.da_filters(r)[5:] for r in (0, 1, 2)], [[], ["SD LD"], ["Brickwall"]])
        self.assertEqual([p.da_filters(r) for r in (3, None)], [None, None])          # not known
        self.assertEqual([p.limits((9, p.DA_FILTER), r) for r in (0, 1, 2)], [(0, 4), (0, 5), (0, 5)])
        with self.assertRaises(ValueError):
            p.limits((9, p.DA_FILTER), 3)
        self.assertEqual(p.OUTPUT_RANGES[p.DA_FILTER], (0, 5))

    def test_the_names_and_limits_of_each_model(self):
        loopback = (3, p.LOOPBACK)
        self.assertEqual([p.limits(loopback, model=m) for m in (None, DAC, PRO, PRO_24)],
                         [(0, 3), (0, 3), (0, 9), (0, 9)])
        self.assertEqual(p.choices(p.LOOPBACK, PRO)[1:4], ["pre FX to 1/2", "post FX to 1/2", "post 1/2 -6 dB"])
        self.assertEqual(p.choices(p.MONO, PRO), p.CHOICES[p.MONO])                          # the same on each
        ref = {m.name: [p.limits((a, p.REF_LEVEL), model=m)[1] for a in (3, 6, 9)] for m in (DAC, PRO, PRO_24)}
        self.assertEqual(ref, {DAC.name: [3, 1, -1], PRO.name: [3, 1, 1], PRO_24.name: [4, 2, 2]})  # IEM: none
        self.assertEqual((p.ref_levels(9, PRO)[1], p.ref_levels(9, PRO_24)[0]), ("Hi-Power", "IEM"))
        filters = {m.name: [len(p.da_filters(r, m)) for r in range(4)] for m in (PRO, PRO_24)}
        self.assertEqual(filters, {PRO.name: [5, 6, 6, 6], PRO_24.name: [7, 7, 7, 7]})
        self.assertEqual((p.da_filters(1, PRO)[5], p.da_filters(1, PRO_24)[6]), ("SD LD", "NOS"))
        self.assertEqual([p.da_filters(None, m) for m in (PRO, PRO_24)], [None, None])     # before the first status
        self.assertEqual(p.limits((9, p.DA_FILTER), 0, PRO_24), (0, 6))
        self.assertEqual(p.da_filters(1, DAC), p.da_filters(1))
        select = [(a, p.EQ_PRESET_SELECT) for a in (1, 4, 10)]
        self.assertEqual({m.name: {p.limits(k, model=m) for k in select} for m in (DAC, PRO, PRO_24)},   # Rumble
                         {DAC.name: {(0, 22)}, PRO.name: {(0, 22)}, PRO_24.name: {(0, 23)}})

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

    def test_volume_on_the_scale_of_each_model(self):
        state = {(a, i): v for a in (3, 6, 9) for i, v in ((p.AUTO_REF_LEVEL, 1), (p.REF_LEVEL, 0))}
        offsets = lambda model: [p.volume_offset(state, o, model) for o in (3, 6, 9)]          # noqa: E731
        self.assertEqual(offsets(PRO), [200, 150, 150])          # +4 dBu, Lo-Power
        self.assertEqual(offsets(PRO_24), [230, 180, 180])       # +1 dBu, IEM
        self.assertEqual(p.volume_floor(state, 3, PRO_24), -1145)   # no lower than Volume goes
        state[(9, p.REF_LEVEL)] = 1
        self.assertEqual(p.volume_offset(state, 9, PRO_24), 120)  # Lo-Power, +7 dBu


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
