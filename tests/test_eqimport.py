r"""From a file to the device: the lines that can be used and why not, what a file is, the channels, Map (the Q
converted, the grid, limits, where the filters go, why a selection does not map, the proposal), what a fit sets,
and what OK writes, with what the input does not set at its factory default. The expected device Qs are not
computed by this code."""

import unittest

from commander.conversion import eqfile as E
from commander.conversion import eqfit as X
from commander.conversion import eqimport as I
from commander.device import params as P
from tests.support import TEN_FILTERS, dump_state

OUT, LEFT, RIGHT = 3, 4, 5
FS = 48000.0


def apo(*filters):
    return E.read("\n".join("Filter: ON " + f for f in filters) + "\n")


def group(eq, origin=I.EXTERNAL):
    usable, _ = I.items(eq, origin, FS)
    return list(usable.values())


def mapped(eq, origin=I.EXTERNAL):
    return I.mapping(group(eq, origin), origin, FS)


def bands(m):
    """{band: (kind, freq, gain, q)} of a mapping."""
    return {t: (p.kind, p.freq, p.gain, p.q) for t, p in m.placed.items()}


class Conversion(unittest.TestCase):
    def test_cookbook_q_to_device_q(self):
        """48 kHz: Cookbook 1 kHz Q 5 -> 5.0; 8 kHz Q 2 -> 2.4; 12 kHz Q 1 -> 1.5; 16 kHz Q 0.7 -> 1.6."""
        for f, q_cb, q_dev in ((1000, 5, 5.0), (8000, 2, 2.4), (12000, 1, 1.5), (16000, 0.7, 1.6)):
            m = mapped(apo("PK Fc %d Hz Gain -6 dB Q %s" % (f, q_cb)))
            self.assertEqual([p.q for p in m.placed.values()], [q_dev], f)

    def test_origin_adi2_takes_the_numbers_as_they_are(self):
        m = mapped(apo("PK Fc 8000 Hz Gain -6 dB Q 2"), I.ADI2)
        self.assertEqual(bands(m), {1: ("PK", 8000, -6.0, 2.0)})

    def test_grid_and_limits(self):
        m = mapped(apo("PK Fc 1000.4 Hz Gain 3.26 dB Q 1.04"), I.ADI2)
        self.assertEqual(bands(m), {1: ("PK", 1000, 3.5, 1.0)})
        m = mapped(apo("PK Fc 22000 Hz Gain 15 dB Q 12"), I.ADI2)
        self.assertEqual(bands(m), {1: ("PK", 20000, 12.0, 9.9)})
        self.assertEqual(m.placed[1].notes, ["frequency limited (20–20000 Hz)", "gain limited (±12 dB)",
                                             "Q limited (0.5–9.9)"])

    def test_broader_than_the_device_makes(self):
        m = mapped(apo("PK Fc 18000 Hz Gain 3 dB Q 0.3"))
        self.assertEqual(m.placed[1].notes, ["Q limited (too broad at 18000 Hz)"])


class Placement(unittest.TestCase):
    def test_in_order_of_frequency(self):
        m = mapped(apo("PK Fc 3000 Hz Gain 1 dB Q 1", "PK Fc 100 Hz Gain 1 dB Q 1", "PK Fc 500 Hz Gain 1 dB Q 1"))
        self.assertEqual([bands(m)[b][1] for b in (1, 2, 3)], [100, 500, 3000])

    def test_low_filters_where_they_fit(self):
        m = mapped(apo(*["PK Fc %d Hz Gain 1 dB Q 1" % f for f in (50, 100, 150, 1000, 4000)]))
        self.assertEqual({b: v[1] for b, v in bands(m).items()}, {1: 50, 2: 100, 3: 150, 4: 1000, 5: 4000})

    def test_shelves_high_pass_and_high_cut(self):
        m = mapped(apo("LSC Fc 100 Hz Gain 3 dB Q 0.7", "HSC Fc 8000 Hz Gain -2 dB Q 0.7", "PK Fc 1000 Hz Gain 1 dB Q 1"))
        self.assertEqual((bands(m)[1][0], bands(m)[5][0]), ("LS", "HS"))
        m = mapped(apo("HP Fc 30 Hz", "LP Fc 15000 Hz"))
        self.assertEqual((bands(m)[1][0], bands(m)[5][0]), ("HP", "LP"))

    def test_why_a_selection_does_not_map(self):
        peaks = ["PK Fc %d Hz Gain 1 dB Q 1" % f for f in (300, 600, 1200, 2400, 4800, 9600)]
        for filters, reason in (
                (peaks, "6 filters for 5 bands"),
                (["LSC Fc 100 Hz Gain 3 dB Q 0.7", "LSC Fc 300 Hz Gain 3 dB Q 0.7"],
                 "Only band 1 takes a low shelf or a High Pass"),
                (["HSC Fc 5000 Hz Gain 3 dB Q 0.7", "HSC Fc 9000 Hz Gain 3 dB Q 0.7"], "Only band 5 takes a high shelf"),
                (["LSC Fc 100 Hz Gain 3 dB Q 0.7", "HSC Fc 9000 Hz Gain 3 dB Q 0.7", "LP Fc 12000 Hz"],
                 "Only bands 1 and 5 take shelves, High Pass and High Cut"),
                (["PK Fc %d Hz Gain 1 dB Q 1" % f for f in (40, 80, 120, 160)], "Bands 4 and 5 start at 200 Hz"),
                (["PK Fc %d Hz Gain 1 dB Q 7" % f for f in (300, 600, 1200, 2400)], "Bands 4 and 5 go up to Q 5.0")):
            m = mapped(apo(*filters), I.ADI2)
            self.assertEqual((m.reason, m.placed), (reason, {}), filters)

    def test_the_proposal_keeps_the_largest_effect_that_maps(self):
        g = group(E.read(TEN_FILTERS))
        chosen = I.preselect(g, I.EXTERNAL, FS)
        self.assertEqual(len(chosen), 5)
        self.assertEqual(I.mapping(chosen, I.EXTERNAL, FS).reason, "")
        self.assertIn(2, [i.line for i in chosen])                 # the low shelf of +6.4 dB


class Lines(unittest.TestCase):
    def test_what_cannot_be_used_says_why(self):
        eq = E.read("Preamp: -3 dB\nFilter: OFF PK Fc 100 Hz Gain 1 dB Q 1\nFilter: ON PK Fc 30000 Hz Gain 1 dB Q 1\n"
                    "Filter: ON BP Fc 1000 Hz Q 1\nChannel: C\nFilter: ON PK Fc 200 Hz Gain 1 dB Q 1\n"
                    "Channel: all\nFilter: ON PK Fc 300 Hz Gain 1 dB Q 1\n")
        usable, why = I.items(eq, I.EXTERNAL, FS)
        self.assertEqual(list(usable), [8])
        self.assertEqual(why, {1: "Preamp: not needed on the device", 2: "Off in the file",
                               3: "No filter at this frequency", 4: "BP: not on the device",
                               5: "Only L and R are used", 6: "Not for L or R"})

    def test_a_commander_file_its_table_or_its_filter_lines(self):
        eq = E.read(E.write(dump_state(), OUT, FS))
        rows = {r.line for r in E.table(eq)}
        usable, why = I.items(eq, I.ADI2, FS)
        self.assertEqual(set(usable), rows)
        self.assertEqual(set(why), {e.line for e in eq.entries})
        self.assertEqual(set(why.values()), {"With Origin ADI-2 the table above is imported"})
        usable, why = I.items(eq, I.EXTERNAL, FS)
        self.assertEqual(set(usable), {e.line for e in eq.entries if e.on})
        self.assertTrue(rows <= set(why))
        self.assertEqual({why[n] for n in rows}, {"With Origin External the Filter lines are imported"})


class Category(unittest.TestCase):
    def test_what_a_file_is(self):
        self.assertEqual(I.category(E.read(E.write(dump_state(), OUT, FS))), "commander")
        self.assertEqual(I.category(apo("PK Fc 100 Hz Gain 1.5 dB Q 1.4", "LSC Fc 80 Hz Gain -3 dB Q 0.7")), "fits")
        self.assertEqual(I.category(apo("HP Fc 30 Hz Q 0.707")), "other")             # Q off the grid
        self.assertEqual(I.category(apo("PK Fc 100.5 Hz Gain 1 dB Q 1")), "other")
        self.assertEqual(I.category(E.read(TEN_FILTERS)), "other")
        self.assertEqual(I.category(apo(*["PK Fc %d Hz Gain 1 dB Q 1" % f for f in (300, 600, 1200, 2400, 4800)],
                                         "LSC Fc 80 Hz Gain 1 dB Q 0.7")), "other")   # shelves to Bass: not yet


class Channels(unittest.TestCase):
    def sets(self, text, dual):
        return {k: [i.line for i in v] for k, v in I.channel_sets(group(E.read(text)), dual).items()}

    def test_one_set_both_channels(self):
        text = "Filter: ON PK Fc 100 Hz Gain 1 dB Q 1\n"
        self.assertEqual(self.sets(text, True), {"L": [1], "R": [1]})
        self.assertEqual(self.sets(text, False), {"all": [1]})

    def test_left_and_right_of_their_own(self):
        text = ("Filter: ON PK Fc 100 Hz Gain 1 dB Q 1\nChannel: L\nFilter: ON PK Fc 200 Hz Gain 1 dB Q 1\n"
                "Channel: R\nFilter: ON PK Fc 300 Hz Gain 1 dB Q 1\n")
        self.assertEqual(self.sets(text, True), {"L": [1, 3], "R": [1, 5]})
        with self.assertRaises(ValueError):
            self.sets(text, False)

    def test_one_channel_only_leaves_the_other_out(self):
        text = "Channel: L\nFilter: ON PK Fc 100 Hz Gain 1 dB Q 1\n"
        self.assertEqual(self.sets(text, True), {"L": [2]})
        self.assertEqual(self.sets(text, False), {"all": [2]})


class Fit(unittest.TestCase):
    def test_a_band_left_at_0_db_is_not_set(self):
        S = X.Setting
        r = X.Result([S("1", "HP", 30, 0.0, 0.7), S("2", "PK", 82, 0.0, 6.5), S("3", "PK", 1002, -3.5, 1.9),
                      S("5", "HS", 9000, 0.0, 0.8), S("B", "LS", 100, 0.0, 0.9), S("T", "HS", 5000, 2.0, 0.7)],
                     0.0, 0.0, 0.0)
        self.assertEqual({t: (p.kind, p.gain) for t, p in I.from_fit(r).items()},
                         {1: ("HP", 0.0), 3: ("PK", -3.5), "Treble": ("HS", 2.0)})   # a High Pass has no gain


class Writing(unittest.TestCase):
    def test_undefined_bands_at_their_factory_default(self):
        m = mapped(apo("PK Fc 100 Hz Gain 2 dB Q 1"))
        outcome = {"all": m.placed}
        self.assertEqual(I.shown(outcome, OUT, False), {(LEFT, 3): 0, (LEFT, 4): 4, (LEFT, 5): 100, (LEFT, 6): 10})
        values = I.writes(outcome, OUT, False, {"all"})
        for i in range(7, 20):
            self.assertEqual(values[(LEFT, i)], P.FACTORY_BANDS[i])
        self.assertEqual(values[(LEFT, 5)], 100)
        self.assertNotIn((LEFT, P.BASS[0]), values)                  # Bass/Treble not taken
        values = I.writes(outcome, OUT, False, {"all", "BT"})
        self.assertEqual({k: v for k, v in values.items() if k[1] in P.BASS + P.TREBLE},
                         {(LEFT, i): P.FACTORY_BT[i] for i in P.BASS + P.TREBLE})

    def test_never_a_switch(self):
        values = I.writes({"L": mapped(apo("PK Fc 100 Hz Gain 2 dB Q 1")).placed}, OUT, True, {"L", "R", "BT"})
        switches = {(LEFT, P.EQ_ENABLE), (RIGHT, P.EQ_ENABLE), (LEFT, P.BT_ENABLE), (OUT, P.DUAL_EQ)}
        self.assertFalse(switches & set(values))

    def test_a_commander_file_back_exactly_through_its_table(self):
        state = dump_state()
        eq = E.read(E.write(state, OUT, FS))
        usable, _ = I.items(eq, I.ADI2, FS)
        chosen = list(usable.values())
        dual = state[(OUT, P.DUAL_EQ)] == 1
        outcome = {b: I.mapping(g, I.ADI2, FS).placed for b, g in I.channel_sets(chosen, dual).items()}
        outcome["BT"] = {i.target: I.on_row(i) for i in I.tone_items(chosen)}
        values = I.writes(outcome, OUT, dual, set(outcome))
        self.assertEqual(I.changes(state, values), {})

    def test_changes_are_what_differs(self):
        self.assertEqual(I.changes({(LEFT, 4): 0, (LEFT, 5): 100}, {(LEFT, 4): 0, (LEFT, 5): 200}), {(LEFT, 5): 200})


if __name__ == "__main__":
    unittest.main()
