"""The device panel against the simulator: the settings of the device, per model, written as chosen."""

import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from commander.device import params as P
from commander.device.models import PRO, PRO_24
from tests.gui import WindowTest, tab


class DevicePanel(WindowTest):
    """An ADI-2 DAC FS with an ESS D/A converter: no DSD Direct."""

    def setUp(self):
        super().setUp()
        self.panel = self.win.device_panel
        QTest.mouseClick(self.win.device_tab, Qt.LeftButton)
        self.spin(1100)                                                         # the first status message

    def rows(self):
        """The groups and the names of their settings, as shown."""
        return [(g, [x.name for x in xs]) for g, xs in self.panel.built]

    def text(self, i):
        s = self.panel.steppers[i][1]
        return s.text(s.value)

    def option(self, i):
        return self.panel.options[i][1]

    def test_opened_by_its_tab_after_the_presets(self):
        x = lambda w: w.mapTo(self.win, w.rect().topLeft())                  # noqa: E731
        self.assertTrue(self.win.device_area.isVisible())
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.spin(50)
        self.assertLess(x(self.win.presets_tab).y(), x(self.win.device_tab).y())
        self.assertLess(x(self.win.presets_area).x(), x(self.win.device_area).x())

    def test_its_rows(self):
        self.assertEqual(self.rows(), [
            ("PHONES", ["Mute Line"]), ("DSD", ["DSD Filter", "DSD Detection"]), ("POWER", ["Auto Standby"]),
            ("KEYS", ["Remap Keys", "VOL (1)", "I/O (2)", "EQ (3)", "SETUP (4)"]),
            ("DISPLAY", ["Display Mode", "Meter Color", "Hor. Meter", "AutoDark Mode", "Show Vol. Screen", "Lock UI"])])
        self.assertEqual((self.text(P.METER_COLOR), self.text(P.DSD_FILTER)), ("Monochrome", "50 kHz"))
        self.assertFalse(self.panel.steppers[P.DSD_FILTER][1].faded)          # it has no DSD Direct to wait for
        self.assertIn("70 kHz DSD128", self.panel.steppers[P.DSD_FILTER][1].toolTip())

    def test_written_as_chosen(self):
        self.panel.steppers[P.METER_COLOR][1].step(+1)                          # Red
        QTest.mouseClick(self.option(P.DSD_DETECTION), Qt.LeftButton)
        self.settle()
        self.assertEqual((self.sim.state[(12, P.METER_COLOR)], self.sim.state[(12, P.DSD_DETECTION)]), (4, 1))
        self.assertEqual(self.text(P.METER_COLOR), "Red")
        self.assertTrue(self.option(P.DSD_DETECTION).on)

    def test_two_pages_the_one_chosen_kept(self):
        meter, remap = self.panel.steppers[P.METER_COLOR][1], self.panel.steppers[P.REMAP_KEYS][1]
        self.assertEqual((meter.isVisibleTo(self.panel), remap.isVisibleTo(self.panel)), (False, False))
        QTest.mouseClick(self.panel.choice.buttons[1], Qt.LeftButton)          # Controls
        self.assertEqual((meter.isVisibleTo(self.panel), remap.isVisibleTo(self.panel)), (True, True))
        self.assertFalse(self.panel.steppers[P.AUTO_STANDBY][1].isVisibleTo(self.panel))
        QTest.mouseClick(self.win.device_tab, Qt.LeftButton)                     # closed and opened again
        QTest.mouseClick(self.win.device_tab, Qt.LeftButton)
        self.spin(50)
        self.assertTrue(meter.isVisible())
        self.assertEqual(self.panel.choice.current, 1)

    def test_a_key_chosen_from_its_menu(self):
        key = self.panel.steppers[26][1]                                        # VOL (1)
        menu = key.menu()
        entry = key.current_entry                                               # the group of its function, bold
        self.assertTrue(entry.font().bold())
        self.assertIn(key.value, next(xs for g, xs in key.groups if g == entry.text()))
        crossfeed = next(a.menu() for a in menu.actions() if a.text() == "Crossfeed")
        crossfeed.actions()[0].trigger()
        self.settle()
        self.assertEqual(self.sim.state[(12, 26)], self.session.key_names().index("Crossfeed 1"))
        self.assertEqual(self.text(26), "Crossfeed 1")
        self.assertFalse(key.faded)
        self.session.set((12, P.REMAP_KEYS), 0)
        self.settle()
        self.assertTrue(key.faded)
        self.assertTrue(key.toolTip().endswith("Not in use: Remap Keys is off"))

    def test_a_change_on_the_device_is_shown(self):
        self.sim.front_panel([(12, P.LOCK_UI, 3)])
        self.spin(1500)
        self.assertEqual(self.text(P.LOCK_UI), "Keys+Remote")


class DevicePanelPro(DevicePanel):
    model = PRO

    def test_its_rows(self):
        self.assertEqual([g for g, _ in self.rows()], ["DEVICE MODE", "PHONES", "DSD", "SPDIF", "KEYS", "DISPLAY"])
        self.assertEqual(self.rows()[2][1], ["DSD Direct 1/2", "DSD Filter", "DSD Detection"])
        filter_ = self.panel.steppers[P.DSD_FILTER][1]
        self.assertTrue(filter_.faded)                                          # DSD Direct is off
        self.assertTrue(filter_.toolTip().endswith("Not in use: DSD Direct is off"))
        self.assertIn("Phones 1/2 is off", self.option(P.DSD_DIRECT).toolTip())

    def test_written_as_chosen(self):
        self.panel.steppers[P.SRC][1].step(-1)                                  # AES In
        self.settle()
        self.assertEqual(self.sim.state[(12, P.SRC)], 1)

    def test_mute_v_trs_1_2_with_dual_phones_on(self):
        mute = self.option(P.MUTE_V_PH_1_2)
        self.assertFalse(mute.isEnabled())
        self.assertTrue(mute.toolTip().endswith("Can be set with Dual Phones on"))
        QTest.mouseClick(self.option(P.DUAL_PHONES), Qt.LeftButton)
        self.settle()
        self.spin(1100)
        self.assertTrue(mute.isEnabled())
        self.assertTrue(self.win.tabs.isTabEnabled(tab(6)))                     # Phones 1/2, with settings of its own

    def test_basic_mode_changes_the_sources(self):
        self.panel.steppers[P.BASIC_MODE[1]][1].step(+1)                        # AD/DA
        self.settle()
        self.spin(1100)
        self.assertEqual(self.session.basic_mode(), P.MODE_AD_DA)
        self.assertEqual(self.win.input_panel.values["mode"].text(), "AD/DA")
        spdif_in = self.panel.steppers[P.SPDIF_IN][1]
        self.assertTrue(spdif_in.isEnabled())
        self.session.set(P.BASIC_MODE, P.MODE_DAC)
        self.settle()
        self.spin(1100)
        self.assertEqual(self.session.basic_mode(), P.MODE_DAC)
        self.assertFalse(spdif_in.isEnabled())
        self.assertTrue(spdif_in.toolTip().endswith("In Basic Mode DAC Source sets it"))


class DevicePanel24(DevicePanel):
    model = PRO_24

    def test_its_rows(self):
        self.assertEqual(self.rows()[0][1], ["Basic Mode", "Dig. Out Source", "Auto Standby"])
        self.assertEqual(self.rows()[1][1], ["Dual Phones", "Bal TRS Mode", "Toggle Ph/Line", "Mute v. Ph 1/2",
                                             "Mute v. Ph 3/4"])
        self.assertIn("Pentaconn", self.panel.steppers[P.BAL_PHONES][1].toolTip())
        self.assertEqual(self.rows()[4][1][-3:], ["IR 5", "IR 6", "IR 7"])
        self.assertEqual((self.text(22), self.text(24)), ("Source SPDIF coax", "Source USB 1/2"))     # IR 5, IR 7

    def test_a_source_on_a_key_in_basic_mode_dac(self):
        key = self.panel.steppers[26][1]                                        # VOL (1): Source Analog
        self.assertTrue(key.faded)
        self.assertTrue(key.toolTip().endswith("Takes effect in Basic Mode DAC"))
        source = next(a.menu() for a in key.menu().actions() if a.text() == "Source")
        self.assertTrue(source.toolTipsVisible())
        self.assertEqual(source.actions()[0].toolTip(), "Takes effect in Basic Mode DAC")
        self.session.set(P.BASIC_MODE, P.MODE_DAC)
        self.settle()
        self.spin(1100)
        self.assertFalse(key.faded)

    def test_written_as_chosen(self):
        self.panel.steppers[P.HOR_METER][1].step(+1)                            # Pre FX
        self.settle()
        self.assertEqual(self.sim.state[(12, P.HOR_METER)], 1)


if __name__ == "__main__":
    unittest.main()
