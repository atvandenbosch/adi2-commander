"""The output panel against the simulator: the output's settings other than the sound."""

import unittest

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleFactory, QToolTip

from commander.device import params as P
from commander.device.models import PRO_24
from commander.ui.widgets import Action
from tests.gui import OUTPUT_TABS, WindowTest, tab


class OutputSettings(WindowTest):
    def setUp(self):
        super().setUp()
        self.panel = self.win.output_panel
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)
        for _ in range(30):                                                     # which output is active: Dim
            if self.session.device_status is not None:
                break
            self.spin(100)
        self.spin(50)

    def arrow(self, i, direction):
        s = self.panel.steppers[i]
        QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(4 if direction < 0 else s.width() - 4, s.height() // 2))

    def test_opened_by_its_tab_before_the_presets(self):
        x = lambda w: w.mapTo(self.win, w.rect().topLeft())                  # noqa: E731
        self.assertTrue(self.win.output_area.isVisible())
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.spin(50)
        self.assertLess(x(self.win.output_tab).y(), x(self.win.presets_tab).y())
        self.assertLess(x(self.win.output_area).x(), x(self.win.presets_area).x())
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)
        self.assertFalse(self.win.output_area.isVisible())
        self.assertTrue(self.win.presets_area.isVisible())                      # each its own

    def test_the_name_of_a_setting_shows_its_tooltip(self):
        """The name shows what the control shows; the room beside the control shows nothing."""
        def tip(widget, pos):
            """The tooltip shown, None where none is."""
            QToolTip.hideText()
            e = QHelpEvent(QEvent.ToolTip, pos, widget.mapToGlobal(pos))
            QApplication.sendEvent(widget, e)
            return QToolTip.text() if e.isAccepted() else None

        label, stepper = self.panel.labels[P.POLARITY], self.panel.steppers[P.POLARITY]
        self.assertTrue(stepper.toolTip())
        row = self.panel.rows[P.POLARITY]
        self.assertEqual(tip(label, QPoint(4, 4)), stepper.toolTip())
        self.assertIsNone(tip(row, QPoint(row.width() - 2, 4)))
        QToolTip.hideText()

    def test_each_tooltip_waits_for_the_mouse_to_rest(self):
        """As long as in Fusion, also right after another tooltip."""
        style = self.panel.steppers[P.POLARITY].style()
        wake_up = QStyle.SH_ToolTip_WakeUpDelay
        self.assertEqual(style.styleHint(wake_up), QStyleFactory.create("Fusion").styleHint(wake_up))
        self.assertEqual(style.styleHint(QStyle.SH_ToolTip_FallAsleepDelay), 0)

    def test_a_line_between_two_open_panels(self):
        self.win.room = lambda: QRect(0, 0, 2560, 1400)                       # room for all five
        lines = self.win.panel_lines
        shown = lambda: [line.isVisible() for line in lines]                    # noqa: E731
        self.assertEqual(shown(), [False, False, False, False])                 # Output alone
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, False, True, False])
        QTest.mouseClick(self.win.input_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, True, True, False])
        QTest.mouseClick(self.win.device_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, True, True, True])
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, False, True, True])                   # Input, Presets, Device
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, False, False, True])                  # Input, Device
        QTest.mouseClick(self.win.input_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, False, False, False])                 # Device
        self.win.show_traffic()
        self.assertEqual(shown(), [False, False, False, True])                  # MIDI, Device
        QTest.mouseClick(self.win.input_tab, Qt.LeftButton)
        self.assertEqual(shown(), [True, False, False, True])                   # MIDI, Input, Device

    def test_ref_level_readable_while_auto_ref_level_chooses_it(self):
        ref = self.panel.steppers[P.REF_LEVEL]
        self.assertEqual(ref.text(ref.value), P.REF_LEVELS[3][self.sim.state[(3, P.REF_LEVEL)]])
        self.assertTrue(ref.held and not ref.isEnabled())                      # the arrows grey, the value not
        self.assertIn("Chosen by Auto Ref Level", ref.toolTip())
        QTest.mouseClick(self.panel.options[P.AUTO_REF_LEVEL], Qt.LeftButton)
        self.settle()
        self.assertTrue(not ref.held and ref.isEnabled())
        self.arrow(P.REF_LEVEL, +1)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.REF_LEVEL)], self.session.state[(3, P.REF_LEVEL)])

    def test_hi_power_in_amber_before_headphones_are_plugged_in(self):
        self.win.tabs.setCurrentIndex(tab(6))                                        # Phones: Lo-Power, -10.0, no plug
        ref = self.panel.steppers[P.REF_LEVEL]
        self.assertFalse(ref.warned)
        self.session.set((6, P.REF_LEVEL), 1)                                   # Hi-Power, above -15 dB
        self.settle()
        self.assertTrue(ref.warned)
        self.assertIn("Plugging in headphones will bring up a warning", ref.toolTip())
        self.session.set((6, P.VOLUME), -150)                                   # -15.0: no warning
        self.settle()
        self.assertFalse(ref.warned)
        self.session.set((6, P.VOLUME), -145)
        self.settle()
        self.assertTrue(ref.warned)
        self.sim.plug(6)                                                        # plugged in: one is at the device
        self.spin(1100)
        self.assertFalse(ref.warned)
        self.assertNotIn("Plugging in", ref.toolTip())
        self.sim.plug()
        self.spin(1100)
        self.win.tabs.setCurrentIndex(tab(3))                                        # only Phones
        self.assertFalse(self.panel.steppers[P.REF_LEVEL].warned)

    def test_no_rear_trs_source(self):
        for i in OUTPUT_TABS:
            self.win.tabs.setCurrentIndex(i)
            self.assertFalse(self.panel.rows[P.REAR_TRS_SOURCE].isVisible())

    def test_iem_has_no_ref_level(self):
        rows = self.panel.rows
        self.win.tabs.setCurrentIndex(tab(6))
        self.assertTrue(rows[P.REF_LEVEL].isVisible() and rows[P.AUTO_REF_LEVEL].isVisible())
        ref = self.panel.steppers[P.REF_LEVEL]
        self.assertEqual((ref.names, ref.text(ref.value) in P.REF_LEVELS[6]), (P.REF_LEVELS[6], True))
        self.win.tabs.setCurrentIndex(tab(9))
        self.assertFalse(rows[P.REF_LEVEL].isVisible() or rows[P.AUTO_REF_LEVEL].isVisible())

    def test_a_stepper_steps_and_stops_at_either_end(self):
        s = self.panel.steppers[P.CROSSFEED]
        self.assertEqual(s.value, 0)
        self.assertFalse(s.can_step(-1))
        self.arrow(P.CROSSFEED, +1)
        self.assertEqual(s.value, 1)                                            # at once
        self.settle()
        self.assertEqual(self.sim.state[(3, P.CROSSFEED)], 1)
        s.menu().actions()[5].trigger()                                         # all values: the strongest
        self.settle()
        self.assertEqual(self.sim.state[(3, P.CROSSFEED)], 5)
        self.assertFalse(s.can_step(+1))
        QTest.keyClick(s, Qt.Key_Left)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.CROSSFEED)], 4)

    def test_the_list_marks_the_value_in_bold_not_with_a_check(self):
        s = self.panel.steppers[P.DA_FILTER]
        actions = s.menu().actions()
        self.assertFalse(any(a.isCheckable() for a in actions))
        self.assertEqual([a.font().bold() for a in actions], [v == s.value for v in range(len(actions))])

    def test_minus_1_is_a_value_like_any_other(self):
        self.session.set((3, P.WIDTH), -1)                                      # -0.01: not absent as on IEM
        self.settle()
        self.assertTrue(self.panel.rows[P.WIDTH].isVisible())
        self.assertTrue(self.panel.steppers[P.WIDTH].isEnabled())
        self.session.set((3, P.WIDTH), -2)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.WIDTH)], -2)

    def test_the_order_of_the_level_group(self):
        y = lambda i: self.panel.rows[i].mapTo(self.panel, self.panel.rows[i].rect().topLeft()).y()   # noqa: E731
        order = [P.AUTO_REF_LEVEL, P.REF_LEVEL]
        self.assertEqual(sorted(order, key=y), order)

    def test_off_is_grey_on_is_bright(self):
        s = self.panel.steppers[P.MONO]
        self.assertEqual(s.off, 0)
        self.assertEqual(self.panel.steppers[P.DE_EMPHASIS].off, 2)            # Auto, On, Off: wherever it is
        self.assertIsNone(self.panel.steppers[P.DA_FILTER].off)                # no value means off

    def test_width_steps_of_five_hundredths_and_its_points(self):
        s = self.panel.steppers[P.WIDTH]
        self.assertEqual((s.text(s.value), s.off), ("Stereo", 100))              # full stereo: grey, as off
        self.assertFalse(s.can_step(+1))
        self.arrow(P.WIDTH, -1)
        self.settle()
        self.assertEqual((self.sim.state[(3, P.WIDTH)], s.text(s.value)), (95, "0.95"))
        QTest.keyClick(s, Qt.Key_Space)
        self.spin(50)
        slider = s.popup.slider
        self.assertEqual((slider.anchor, slider.ticks), (100, [0]))             # filled from Stereo; a tick at Mono
        buttons = {b.text(): b for b in s.popup.findChildren(Action)}
        self.assertEqual(sorted(buttons), ["Mono", "Stereo", "Swapped"])
        mono = buttons["Mono"]
        self.assertLessEqual(abs(mono.mapTo(s.popup, mono.rect().center()).x()
                                 - slider.mapTo(s.popup, QPoint(round(slider.x_of(0)), 0)).x()), 1)   # under it
        QTest.mouseClick(buttons["Swapped"], Qt.LeftButton)
        self.settle()
        self.assertEqual((self.sim.state[(3, P.WIDTH)], s.text(s.value)), (-100, "Swapped"))
        self.assertIn("left and right exchanged", s.toolTip())

    def test_every_output_has_its_own(self):
        line = self.sim.state[(3, P.DA_FILTER)]
        self.win.tabs.setCurrentIndex(tab(6))
        self.arrow(P.DA_FILTER, +1)
        self.settle()
        self.assertEqual((self.sim.state[(3, P.DA_FILTER)], self.sim.state[(6, P.DA_FILTER)]), (line, line + 1))

    def test_the_da_filters_follow_the_d_a_converter(self):
        s = self.panel.steppers[P.DA_FILTER]
        self.assertEqual(s.names[5], "Brickwall")                               # revision 2: the ES9028Q2M
        self.sim.revision = 1                                                   # the AK4493
        self.spin(1100)
        self.assertEqual(s.names[5:], ["SD LD"])
        self.sim.revision = 0                                                   # the AK4490: five
        self.sim.front_panel([(3, P.DA_FILTER, 4)])
        self.spin(1100)
        self.assertEqual((len(s.names), s.text(s.value)), (5, "NOS"))
        self.assertFalse(s.can_step(+1))

    def test_no_da_filter_of_an_unknown_revision(self):
        s = self.panel.steppers[P.DA_FILTER]
        self.sim.revision = 3
        self.spin(1100)
        self.assertEqual((s.value, s.isEnabled()), (None, False))
        self.assertIn("Not known for this device", s.toolTip())
        self.assertFalse(self.session.writable((3, P.DA_FILTER)))
        self.sim.revision = 2
        self.spin(1100)
        self.assertEqual((s.value, s.isEnabled()), (self.sim.state[(3, P.DA_FILTER)], True))

    def test_processing_that_is_on_is_bypassed_while_dsd_plays(self):
        self.arrow(P.MONO, +1)
        self.settle()
        self.sim.front_panel([(out, 1, 3) for out in (3, 6, 9)])                # USB
        self.sim.signal(usb=176400, dsd=True)
        self.spin(1100)
        mono, crossfeed, da = (self.panel.steppers[i] for i in (P.MONO, P.CROSSFEED, P.DA_FILTER))
        self.assertTrue(mono.faded and "DSD" in mono.toolTip())
        self.assertFalse(crossfeed.faded)                                       # off stays off
        self.assertFalse(da.faded)                                              # the DAC, not the DSP
        self.sim.signal(usb=176400)
        self.spin(1100)
        self.assertFalse(mono.faded)

    def test_crossfeed_gives_way_to_the_eq_from_705_6_khz(self):
        crossfeed = self.panel.steppers[P.CROSSFEED]
        self.arrow(P.CROSSFEED, +1)
        self.session.set((4, P.EQ_ENABLE), 1)
        self.settle()
        self.sim.signal(usb=705600)
        self.spin(1100)
        self.assertTrue(crossfeed.faded)
        self.assertIn("Bypassed at 705.6 kHz while the EQ is on", crossfeed.toolTip())
        for left, right in ((0, 1), (0, 0)):                                    # the EQ of either channel
            self.session.set((4, P.EQ_ENABLE), left)
            self.session.set((5, P.EQ_ENABLE), right)
            self.settle()
            self.assertEqual(crossfeed.faded, bool(right))
        self.session.set((4, P.EQ_ENABLE), 1)
        self.settle()
        self.sim.signal(usb=384000)
        self.spin(1100)
        self.assertFalse(crossfeed.faded)


class ProNames(WindowTest):
    """The lists of an ADI-2/4 Pro carry its own names."""

    model = PRO_24

    def test_ref_level_da_filter_and_loopback(self):
        panel = self.win.output_panel
        for _ in range(30):
            if self.session.device_status is not None:
                break
            self.spin(100)
        panel.set_output(P.OUTPUTS[2])                                          # Phones 3/4
        names = lambda i: panel.steppers[i].names                               # noqa: E731
        self.assertEqual((names(P.REF_LEVEL), len(names(P.DA_FILTER)), len(names(P.LOOPBACK))),
                         (["IEM", "Lo-Power", "Hi-Power"], 7, 10))
        panel.set_output(P.OUTPUTS[0])
        self.assertEqual(names(P.REF_LEVEL)[-1], "+24 dBu")

    def test_hi_power_on_either_phones(self):
        panel, s = self.win.output_panel, self.session.state
        for _ in range(30):
            if self.session.device_status is not None:
                break
            self.spin(100)
        for out, plug in ((9, "iem"), (6, "phones")):                          # Phones 3/4, Phones 1/2
            panel.set_output(next(o for o in P.OUTPUTS if o[1] == out))
            s[(out, P.VOLUME)] = -100
            s[(out, P.REF_LEVEL)] = 1                                           # Lo-Power
            self.assertFalse(panel.plug_warning())
            s[(out, P.REF_LEVEL)] = 2                                           # Hi-Power
            self.assertTrue(panel.plug_warning())
            self.session.device_status = self.session.device_status._replace(**{plug: True})
            self.assertFalse(panel.plug_warning())


if __name__ == "__main__":
    unittest.main()
