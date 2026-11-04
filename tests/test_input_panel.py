"""The input panel against the simulator: the source and what the inputs receive."""

import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from commander.device import params as P
from commander.device.status import Spdif
from commander.ui import theme
from commander.ui.inputs import _spdif_text
from tests.gui import WindowTest


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

    def test_source_is_written_to_every_output(self):
        s = self.panel.source
        self.assertEqual(s.text(s.value), "Auto")
        s.step(+1)
        self.settle()
        coax = P.INPUTS.index("SPDIF coax")
        self.assertEqual([self.sim.state[(out, P.SOURCE)] for out in P.OUTPUT_ADDRESSES], [coax] * 3)
        self.win.tabs.setCurrentIndex(2)
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


if __name__ == "__main__":
    unittest.main()
