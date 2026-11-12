"""The input panel against the simulator: the source and what the inputs receive."""

import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from commander.device import params as P
from commander.device.models import PRO, PRO_24
from commander.device.status import Spdif
from commander.ui import theme
from commander.ui.inputs import _spdif_text
from tests.gui import WindowTest, tab


class InputSettings(WindowTest):
    def setUp(self):
        super().setUp()
        self.panel = self.win.input_panel
        QTest.mouseClick(self.win.input_tab, Qt.LeftButton)
        self.spin(50)

    def row(self, name):
        return self.panel.values[name].text(), self.panel.dots[name].on if name in self.panel.dots else None

    def color(self, name):
        return QColor(self.panel.values[name].styleSheet().split(":")[1].strip(" ;"))

    def test_its_tab_comes_first(self):
        y = lambda w: w.mapTo(self.win, w.rect().topLeft()).y()                  # noqa: E731
        self.assertTrue(self.win.input_area.isVisible())
        self.assertLess(y(self.win.input_tab), y(self.win.output_tab))

    def test_no_analog_input(self):
        self.assertFalse(any(row.isVisible() for row in self.panel.analog_rows.values()))
        self.assertFalse(any(widgets[1].isVisible() for widgets, _ in self.panel.analog_groups))

    def test_source_is_written_to_every_output(self):
        s = self.panel.source
        self.assertEqual(s.text(s.value), "Auto")
        s.step(+1)
        self.settle()
        coax = P.INPUTS.index("SPDIF coax")
        self.assertEqual([self.sim.state[(out, P.SOURCE)] for out in P.OUTPUT_ADDRESSES], [coax] * 3)
        self.win.tabs.setCurrentIndex(tab(9))
        self.assertEqual(s.text(s.value), "SPDIF coax")                         # one setting, on every tab
        self.assertIn("Line Out, Phones and IEM alike", s.toolTip())

    def test_auto_marks_the_input_it_follows(self):
        self.spin(1100)                                                         # the first status message
        self.assertEqual([self.row(n)[1] for n in ("coax", "optical", "usb")], [False, False, True])
        self.assertEqual(self.row("clock")[0], "Internal")
        self.sim.signal(optical=48000)
        self.spin(1100)
        self.assertEqual(self.row("optical"), ("48 kHz", True))
        self.assertEqual(self.row("usb")[1], False)
        self.assertEqual((self.row("rate")[0], self.row("clock")[0]), ("48 kHz", "Optical"))
        self.assertEqual(self.row("coax"), ("no signal", False))
        self.assertEqual(self.color("coax"), theme.SECONDARY)                  # nothing, where it does not matter

    def test_a_chosen_input_without_a_signal_is_amber(self):
        self.session.set_source(P.INPUTS.index("SPDIF coax"))
        self.settle()
        self.spin(1100)
        self.assertEqual(self.row("coax"), ("no signal", False))                # nothing plays: no dot
        self.assertEqual(self.color("coax"), theme.WARN)
        self.assertFalse(any(self.panel.dots[n].on for n in ("coax", "optical", "usb")))

    def test_rec_marks_the_input_it_records(self):
        self.session.set_source(P.INPUTS.index("USB (Rec coax)"))
        self.settle()
        self.sim.signal(usb=48000)
        self.spin(1100)
        self.assertEqual((self.row("usb"), self.color("usb")), (("48 kHz", True), theme.TEXT))   # USB plays
        self.assertEqual((self.row("coax"), self.color("coax")), (("no signal", False), theme.WARN))
        self.assertEqual(self.panel.values["coax"].toolTip(), "Recorded over USB; the device follows its clock")
        self.sim.signal(coax=44100, usb=48000)                                  # the clock: coax, at 44.1 kHz
        self.spin(1100)
        self.assertEqual((self.row("coax"), self.color("coax")), (("44.1 kHz", False), theme.TEXT))
        self.assertEqual(self.row("clock")[0], "SPDIF coax")
        self.assertEqual((self.row("usb"), self.color("usb")), (("48 kHz, not in sync", True), theme.WARN))
        self.assertEqual(self.panel.values["usb"].toolTip(), "Not at the rate of the device's clock")

    def test_sync_only_where_it_matters(self):
        self.session.set_source(P.INPUTS.index("USB"))
        self.settle()
        self.sim.signal(optical=44100, usb=48000)                               # optical: not at the clock's rate
        self.spin(1100)
        self.assertEqual((self.row("optical"), self.color("optical")), (("44.1 kHz", False), theme.TEXT))

    def test_dsd_by_its_rate_on_every_input(self):
        self.assertEqual(_spdif_text(Spdif(True, True, 176400, True, False), True), ("DSD64 (DoP)", None))
        self.assertEqual(_spdif_text(Spdif(True, True, None, True, False), True), ("DSD (DoP)", None))
        self.sim.signal(usb=352800, dsd=True)
        self.spin(1100)
        self.assertEqual((self.row("usb")[0], self.row("rate")[0]), ("DSD128 (DoP)", "DSD128"))


class ProSource(WindowTest):
    """An ADI-2 Pro: the Basic Mode in use, and a Source row per setting."""

    model = PRO

    def setUp(self):
        super().setUp()
        self.panel = self.win.input_panel
        QTest.mouseClick(self.win.input_tab, Qt.LeftButton)
        for _ in range(30):
            if self.session.device_status is not None:
                break
            self.spin(100)
        self.spin(50)

    def shown(self):
        """Per visible Source row its name, value as shown, and whether its arrows work."""
        return [(name.text(), s.text(s.value), s.isEnabled()) for row, name, s in self.panel.rows if row.isVisible()]

    def mode(self, mode):
        self.sim.front_panel([(12, 6, mode)])
        self.spin(1500)

    def test_the_rows_in_each_basic_mode(self):
        self.assertEqual(self.panel.values["mode"].text(), "Auto: USB")
        self.assertEqual(self.panel.mode_row.toolTip(), "The Basic Mode in use\nSet in DEVICE › DEVICE MODE")
        self.assertEqual(self.shown(), [("Ln. Out · Ph. 1/2", "USB 1/2", False), ("Phones 3/4", "Auto", True)])
        self.assertEqual(self.panel.rows[0][2].toolTip(), "The input of Line Out and Phones 1/2\nSet by Basic Mode USB")
        self.assertFalse(self.panel.dac_fs[0].isVisible())                     # what the DAC FS inputs receive
        self.mode(1)
        self.assertEqual(self.panel.values["mode"].text(), "AD/DA")
        self.assertEqual(self.shown()[0], ("Ln. Out · Ph. 1/2", "Auto", True))
        self.mode(5)
        self.assertEqual(self.shown(), [("Source", "Auto", True)])
        self.assertEqual(self.panel.rows[0][2].toolTip(), "The input of all outputs, and the clock of the device")
        self.assertEqual(len(self.panel.rows[0][2].names), 7)

    def test_each_row_writes_its_own(self):
        self.mode(1)
        self.panel.rows[0][2].step(+1)                                          # Line Out: AES
        self.panel.rows[1][2].step(+1)                                          # Phones 3/4: AES
        self.settle()
        self.assertEqual([self.sim.state.get((out, P.SOURCE)) for out in (3, 6, 9)], [1, None, 1])  # 6: Line Out's

    def test_the_clock(self):
        """Sample Rate as the device reports it; Clock Source, which cannot be set in Basic Mode DAC."""
        c = self.panel.clock_source
        self.assertEqual((self.panel.values["rate"].text(), c.text(c.value), c.isEnabled()), ("48 kHz", "Auto", True))
        self.assertFalse(self.panel.dac_fs[-1].isVisible())                    # the clock the DAC FS follows
        c.step(+1)
        self.settle()
        self.assertEqual(self.sim.state[(P.DEVICE_ADDRESS, P.CLOCK_SOURCE)], 1)
        self.assertEqual(c.text(c.value), "INT")
        self.mode(5)
        self.assertFalse(c.isEnabled())
        self.assertTrue(c.toolTip().endswith("In Basic Mode DAC Source sets it"))


class AnalogInput(WindowTest):
    """The settings of the analog input: rows and lists by model, written as chosen."""

    def setUp(self):
        super().setUp()
        self.panel = self.win.input_panel
        QTest.mouseClick(self.win.input_tab, Qt.LeftButton)
        self.spin(1100)                                                         # the first status message

    def shown(self):
        return [i for i, row in self.panel.analog_rows.items() if row.isVisible()]

    def groups(self):
        return [widgets[1].isVisible() for widgets, _ in self.panel.analog_groups]

    def text(self, i):
        s = self.panel.analog[i]
        return s.text(s.value)

    def rate(self, index):
        self.sim.state[(12, 16)] = index                                        # read back by the idle refresh
        self.spin(4000)


class AnalogInputPro(AnalogInput):
    model = PRO

    def test_its_rows(self):
        self.assertEqual(self.shown(), [P.IN_AUTO_REF_LEVEL, P.IN_REF_LEVEL, P.TRIM_LEFT, P.TRIM_RIGHT, P.IN_POLARITY,
                                        P.IN_MS_PROC, P.AD_FILTER, P.AD_CONVERSION, P.DC_FILTER])
        self.assertEqual(self.groups(), [True, True, True, False])              # no RIAA
        self.assertEqual((self.text(P.IN_REF_LEVEL), self.text(P.DC_FILTER)), ("+19 dBu", "Auto"))

    def test_written_as_chosen(self):
        """Also Ref Level with Auto Ref Level on: Auto Ref Level only raises it."""
        self.panel.analog[P.IN_REF_LEVEL].step(-1)
        self.panel.analog[P.TRIM_LEFT].step(+1)
        QTest.mouseClick(self.panel.auto_ref, Qt.LeftButton)
        self.settle()
        written = [self.sim.state[(0, i)] for i in (P.IN_REF_LEVEL, P.TRIM_LEFT, P.IN_AUTO_REF_LEVEL)]
        self.assertEqual(written, [1, 1, 1])
        self.assertTrue(self.panel.analog[P.IN_REF_LEVEL].isEnabled())
        self.assertIn("Auto Ref Level raises it", self.panel.analog[P.IN_REF_LEVEL].toolTip())

    def test_ad_filter_above_192_khz(self):
        ad = self.panel.analog[P.AD_FILTER]
        self.assertFalse(ad.faded)
        self.rate(6)                                                            # 352.8 kHz
        self.assertTrue(ad.faded and ad.isEnabled())
        self.assertIn("Not in use: from 352.8 kHz the device uses Slow only", ad.toolTip())


class AnalogInputEx(AnalogInput):
    """An ADI-2/4 Pro EX: Ref Level down to -35 dBu, and RIAA Mode."""

    model, revision = PRO_24, 1

    def test_its_rows(self):
        self.assertEqual(self.shown()[-3:], [P.RIAA_MODE, P.RIAA_MONO_BASS, P.BAL_IMPEDANCE])
        self.assertEqual(self.groups(), [True, True, True, True])

    def test_ref_level_down_to_minus_35_dbu(self):
        ref = self.panel.analog[P.IN_REF_LEVEL]
        for _ in range(8):
            ref.step(-1)
            self.settle()
        self.assertEqual((self.sim.state[(0, P.IN_REF_LEVEL)], self.text(P.IN_REF_LEVEL)), (-6, "-35 dBu (dig.)"))

    def test_riaa_mode_holds_ref_level(self):
        self.panel.analog[P.RIAA_MODE].step(+1)                                # 0 dB
        self.settle()
        self.spin(500)
        ref = self.panel.analog[P.IN_REF_LEVEL]
        self.assertEqual((self.text(P.IN_REF_LEVEL), ref.held), ("+1 dBu", True))
        self.assertFalse(self.panel.auto_ref.isEnabled())
        self.assertIn("RIAA Mode sets it to +1 dBu", ref.toolTip())

    def test_ad_filter_up_to_705_6_khz(self):
        self.rate(7)                                                            # 384 kHz: chosen
        self.assertFalse(self.panel.analog[P.AD_FILTER].faded)
        self.rate(8)                                                            # 705.6 kHz: Slow
        self.assertTrue(self.panel.analog[P.AD_FILTER].faded)

if __name__ == "__main__":
    unittest.main()
