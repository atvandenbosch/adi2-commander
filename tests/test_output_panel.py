"""The output panel against the simulator: the output's settings other than the sound."""

import unittest

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from commander.device import codec
from commander.device import params as P
from commander.device.models import PRO_24
from commander.ui.output import VolumeStepper
from commander.ui.widgets import Action
from tests.gui import WindowTest


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

    def test_a_line_between_two_open_panels(self):
        lines = self.win.panel_lines
        shown = lambda: [line.isVisible() for line in lines]                    # noqa: E731
        self.assertEqual(shown(), [False, False])                               # Output alone
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, True])
        QTest.mouseClick(self.win.input_tab, Qt.LeftButton)
        self.assertEqual(shown(), [True, True])
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, True])                                # Input, then Presets
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.assertEqual(shown(), [False, False])

    def volume_arrow(self, direction, modifier=Qt.NoModifier):
        v = self.panel.volume
        QTest.mouseClick(v, Qt.LeftButton, modifier, QPoint(4 if direction < 0 else v.width() - 4, v.height() // 2))

    def wheel(self, widget, delta):
        centre = QPointF(widget.rect().center())
        QApplication.sendEvent(widget, QWheelEvent(centre, QPointF(widget.mapToGlobal(centre.toPoint())), QPoint(0, 0),
                                                   QPoint(0, delta), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase,
                                                   False))

    def test_out_of_dim_a_step_goes_from_the_level_reported(self):
        vol, dim = (lambda: self.sim.state[(3, P.VOLUME)]), (lambda: self.sim.state[(3, P.DIM)])  # noqa: E731
        v = vol()
        QTest.mouseClick(self.panel.options[P.DIM], Qt.LeftButton)              # Line Out is active
        self.settle()
        self.assertEqual(vol(), v - 200)                                        # the device moved it down
        self.volume_arrow(+1)                                                   # no jump back: 0.5 dB
        self.settle()
        self.assertEqual((vol(), dim()), (v - 195, 0))
        QTest.mouseClick(self.panel.options[P.DIM], Qt.LeftButton)
        self.settle()
        self.volume_arrow(-1)
        self.settle()
        self.assertEqual((vol(), dim()), (v - 195 - 200 - 5, 0))
        QTest.mouseClick(self.panel.options[P.DIM], Qt.LeftButton)              # Dim on, and off again: back up
        self.settle()
        QTest.mouseClick(self.panel.options[P.DIM], Qt.LeftButton)
        self.settle()
        self.assertEqual((vol(), dim()), (v - 400, 0))

    def test_dim_only_on_the_active_output(self):
        dim = self.panel.options[P.DIM]
        self.assertTrue(dim.isEnabled())                                        # Line Out, active
        self.win.tabs.setCurrentIndex(1)                                        # Phones, not active
        self.assertFalse(dim.isEnabled())
        self.assertIn("Dim works on the active output only.", dim.toolTip())
        self.sim.plug(6)
        self.spin(1100)
        self.assertTrue(dim.isEnabled())
        self.assertNotIn("active output only", dim.toolTip())

    def test_volume_is_a_stepper_by_half_a_db(self):
        s, vol = self.panel.volume, lambda: self.session.state[(3, P.VOLUME)]   # noqa: E731
        v = vol()
        self.assertEqual(s.text(s.value), "%.1f" % (v / 10))
        self.volume_arrow(+1, Qt.ControlModifier)
        self.assertEqual(vol(), v + 5)                                          # Ctrl: still 0.5 dB
        QTest.keyClick(s, Qt.Key_Up)
        self.assertEqual(vol(), v + 10)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], v + 10)
        self.sim.front_panel([(3, P.VOLUME, -300)])
        self.spin(100)
        self.assertEqual(s.text(s.value), "-30.0")                              # follows the device
        self.assertEqual((s.neighbour(-298, +1, False), s.neighbour(-298, -1, False)), (-295, -300))   # half dBs
        self.assertIsNone(s.neighbour(P.OUTPUT_RANGES[P.VOLUME][1], +1, False))

    def open_volume_slider(self):
        s = self.panel.volume
        QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(s.width() // 2, s.height() // 2))
        self.spin(50)
        return s.popup

    def test_the_volume_value_opens_a_slider_with_min_and_0_db(self):
        s, pop = self.panel.volume, self.open_volume_slider()
        self.assertTrue(pop.isVisible())
        self.assertEqual((pop.slider.actual, pop.slider.value), (s.value, s.value))
        self.assertLessEqual(pop.width(), self.panel.width())                   # within the panel
        buttons = {b.text(): b for b in pop.findChildren(Action)}
        self.assertEqual(sorted(buttons), ["0.0", "Min", "Stop"])
        self.assertFalse(buttons["Stop"].isVisible())                          # only while rising
        self.assertEqual(buttons["Min"].toolTip(), "The lowest Volume on the device's scale (-114.5)")
        self.assertEqual(buttons["0.0"].toolTip(), "0 dBr: no attenuation")    # Auto Ref Level is on
        self.assertEqual(pop.slider.value_at(pop.slider.x_of(-203)), -205)     # by the mouse onto the half dBs

    def test_min_and_the_bottom_follow_the_devices_scale(self):
        s = self.panel.volume
        self.assertEqual(s.points[0], ("Min", -1145))                           # Line, Auto Ref Level on: dBr
        QTest.mouseClick(self.panel.options[P.AUTO_REF_LEVEL], Qt.LeftButton)
        self.settle()
        self.assertEqual(s.points[0], ("Min", -965))                            # off: -96.5 dB, the dash
        self.assertIn("-96.5 … +6.0", s.toolTip())
        self.session.set((3, P.VOLUME), -965)
        self.settle()
        self.assertFalse(s.can_step(-1))
        self.volume_arrow(-1)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], -965)                   # no lower than the dash
        pop = self.open_volume_slider()
        self.assertEqual((pop.slider.lo, pop.slider.value), (-965, -965))
        QTest.keyClick(pop, Qt.Key_Escape)

    def test_aimed_lower_volume_is_written_at_once(self):
        v, since = self.sim.state[(3, P.VOLUME)], len(self.sim.received)
        self.open_volume_slider().choose(v - 200)
        self.settle()
        self.assertEqual(self.volume_writes(since), [v - 200])
        buttons = {b.text(): b for b in self.panel.volume.popup.findChildren(Action)}
        QTest.mouseClick(buttons["Min"], Qt.LeftButton)
        self.settle()
        self.assertEqual(self.volume_writes(since), [v - 200, -1145])

    def test_aimed_higher_volume_rises_step_by_step(self):
        s, v, since = self.panel.volume, self.sim.state[(3, P.VOLUME)], len(self.sim.received)
        ref, steps = self.sim.state[(3, P.REF_LEVEL)], []
        record = self.recorder(steps)
        s.chosen.connect(record)
        pop = self.open_volume_slider()
        pop.choose(v + 60)                                                      # past where Auto Ref Level changes
        self.spin(500)
        self.assertEqual((pop.slider.value, pop.slider.actual), (v + 60, s.value))   # the ring ahead of the knob
        self.assertLess(s.value, v + 60)
        self.spin(2500)
        s.chosen.disconnect(record)
        for _, before, offset, after in steps:                                  # as fast as the remote control
            self.assertEqual(after, min(v + 60, P.volume_held(before, +1, offset)))
        self.assertEqual(self.volume_writes(since), [a for _, _, _, a in steps])   # one step a write
        self.assertNotEqual(self.sim.state[(3, P.REF_LEVEL)], ref)
        times = [t for t, _, _, _ in steps]
        self.assertTrue(all(b - a >= s.REPEAT_INTERVAL - 1e-6 for a, b in zip(times, times[1:])))
        sent = [m for m in self.sim.received[since:]]
        last = max(n for n, m in enumerate(sent) if m[5] == 0x02)
        self.assertNotIn([0x03, 0x09], [m[5:7] for m in sent[:last]])          # read back once there
        self.settle()
        self.assertEqual((self.sim.state[(3, P.VOLUME)], pop.slider.value, pop.slider.actual), (v + 60,) * 3)

    def test_no_step_before_the_previous_one_has_gone_out(self):
        s, v, since, gone = self.panel.volume, self.sim.state[(3, P.VOLUME)], len(self.sim.received), [False]
        s.sent = lambda: gone[0]                                                # as if still queued
        steps = []
        s.chosen.connect(self.recorder(steps))
        self.open_volume_slider().choose(v + 50)
        self.spin(1000)
        self.assertEqual(self.volume_writes(since), [])                         # it waits
        gone[0] = True
        self.spin(500)                                                          # at once, 0.2 and 0.4 s later
        self.assertEqual(len(steps), 3)
        self.assertEqual(self.volume_writes(since), [a for _, _, _, a in steps])
        QTest.keyClick(s.popup, Qt.Key_Escape)
        self.settle()

    def test_stop_while_it_rises(self):
        v = self.sim.state[(3, P.VOLUME)]
        pop = self.open_volume_slider()
        stop = pop.stop
        pop.choose(v + 100)
        self.spin(450)
        self.assertTrue(stop.isVisible())
        x = lambda w: w.mapTo(pop, w.rect().center()).x()                      # noqa: E731
        buttons = {b.text(): b for b in pop.findChildren(Action)}
        self.assertLess(x(buttons["Min"]), x(stop))
        self.assertLess(x(stop), x(buttons["0.0"]))                             # between the two
        QTest.mouseClick(stop, Qt.LeftButton)
        n = self.session.state[(3, P.VOLUME)]
        self.assertGreater(n, v)
        self.assertFalse(stop.isVisible())
        self.assertTrue(pop.isVisible())                                        # the slider stays
        self.assertEqual((pop.slider.value, pop.slider.actual), (n, n))         # the ring back on the knob
        self.spin(1000)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], n)
        pop.choose(n + 10)                                                      # and there: gone too
        self.spin(1000)
        self.assertFalse(stop.isVisible())
        self.assertEqual(self.session.state[(3, P.VOLUME)], n + 10)
        QTest.keyClick(pop, Qt.Key_Return)
        self.settle()

    def test_it_rises_only_while_the_slider_is_open(self):
        v = self.sim.state[(3, P.VOLUME)]
        for close in (lambda pop: QTest.keyClick(pop, Qt.Key_Return), lambda pop: QTest.keyClick(pop, Qt.Key_Escape),
                      lambda pop: pop.close()):                                 # Enter, Esc, a click elsewhere
            pop = self.open_volume_slider()
            pop.choose(v + 100)
            self.spin(450)
            close(pop)
            n = self.session.state[(3, P.VOLUME)]
            self.assertGreater(n, v)
            self.spin(1000)
            self.settle()
            self.assertEqual(self.sim.state[(3, P.VOLUME)], n)                  # stopped where it had got to
            v = n

    def test_a_step_or_the_device_stops_the_rise(self):
        s, v = self.panel.volume, self.sim.state[(3, P.VOLUME)]
        pop = self.open_volume_slider()
        pop.choose(v + 60)
        self.spin(300)
        QTest.keyClick(s, Qt.Key_Down)                                          # a step of one's own
        n = self.session.state[(3, P.VOLUME)]
        self.spin(1000)
        self.assertEqual(self.session.state[(3, P.VOLUME)], n)
        self.settle()
        pop.choose(n + 60)
        self.spin(300)
        self.sim.front_panel([(3, P.VOLUME, -400)])                             # the device's own knob
        self.spin(1000)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], -400)
        self.assertTrue(pop.isVisible())

    def volume_writes(self, since):
        """The Volume values written to Line Out since that many messages, in order."""
        return [v for m in self.sim.received[since:] if m[5] == 0x02
                for a, i, v, _ in (codec.decode_triplet(*t) for t in codec.parameter_triplets([m]))
                if (a, i) == (3, P.VOLUME)]

    def recorder(self, steps):
        """Each step Volume takes: (time, Volume before, the offset of the device's scale then, Volume after). The
        panel takes a step first, so the Volume before is the one after the step before."""
        last = [self.panel.volume.value]

        def record(v):
            steps.append((self.clock.t, last[0], P.volume_offset(self.session.state, 3), v))
            last[0] = v
        return record

    def assert_held_steps(self, steps, direction):
        """Each step after the first as fast as the remote control at its level (params.volume_held)."""
        for _, before, offset, after in steps[1:]:
            self.assertEqual(after, P.volume_held(before, direction, offset, self.panel.volume.floor))

    def hold(self, direction, ms, key=False):
        """The arrow (or the arrow key) held for ms of simulated time; the steps it took, as recorder."""
        s, times = self.panel.volume, []
        record = self.recorder(times)
        s.chosen.connect(record)
        at = QPoint(4 if direction < 0 else s.width() - 4, s.height() // 2)
        k = Qt.Key_Up if direction > 0 else Qt.Key_Down
        if key:
            s.setFocus()
            QApplication.sendEvent(s, QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier))
        else:
            QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, at)
        for _ in range(ms // 20):
            if key:                                                             # the system's repeat, every 20 ms
                QApplication.sendEvent(s, QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier, "", True))
            self.spin(20)
        if key:
            QApplication.sendEvent(s, QKeyEvent(QEvent.KeyRelease, k, Qt.NoModifier))
        else:
            QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, at)
        s.chosen.disconnect(record)
        return times

    def assert_held(self, direction, key):
        v, since = self.sim.state[(3, P.VOLUME)], len(self.sim.received)
        self.assertEqual(len(self.hold(direction, 300, key)), 1)                # the press, then a pause
        self.settle()
        since_hold = len(self.sim.received)
        steps = self.hold(direction, 2000, key)
        times = [t for t, _, _, _ in steps]
        s, slack = self.panel.volume, 0.15                                      # a slot being read holds a write up
        self.assertTrue(s.REPEAT_DELAY - 1e-6 <= times[1] - times[0] <= s.REPEAT_DELAY + slack)   # the pause
        for a, b in zip(times[1:], times[2:]):                                  # then a steady pace
            self.assertTrue(s.REPEAT_INTERVAL - 1e-6 <= b - a <= s.REPEAT_INTERVAL + slack)
        self.assertGreaterEqual(len(times), 8)
        self.assertNotIn([0x03, 0x09], [m[5:7] for m in self.sim.received[since_hold:]])   # no dump while held
        n = self.session.state[(3, P.VOLUME)]
        self.spin(1000)
        self.assertEqual(self.session.state[(3, P.VOLUME)], n)                  # released: it stops
        self.settle()
        self.assertEqual(steps[0][3], v + direction * 10)                       # the second press: 0.5 dB
        self.assert_held_steps(steps, direction)                                # then as fast as the remote
        self.assertEqual(self.volume_writes(since), [v + direction * 5] + [a for _, _, _, a in steps])   # one a write
        self.assertEqual(self.sim.state[(3, P.VOLUME)], n)

    def test_a_held_arrow_repeats_after_a_pause_up_half_a_db_per_write(self):
        self.assert_held(+1, key=False)

    def test_a_held_key_repeats_at_the_same_pace_down_in_larger_steps(self):
        self.assert_held(-1, key=True)

    def test_held_out_of_dim_from_the_level_reported(self):
        v = self.sim.state[(3, P.VOLUME)]
        QTest.mouseClick(self.panel.options[P.DIM], Qt.LeftButton)
        self.settle()
        steps = self.hold(+1, 1500)
        self.settle()
        self.assertEqual((steps[0][3], self.sim.state[(3, P.DIM)]), (v - 200 + 5, 0))   # Dim off, 0.5 dB up
        self.assertGreaterEqual(steps[1][0] - steps[0][0], self.panel.volume.REPEAT_DELAY - 1e-6)
        self.assert_held_steps(steps, +1)
        self.assertEqual(self.sim.state[(3, P.VOLUME)], steps[-1][3])

    def test_the_wheel_by_the_notch(self):
        s, vol = self.panel.volume, lambda: self.session.state[(3, P.VOLUME)]   # noqa: E731
        v = vol()
        s.setFocus()
        for delta in (40, 40, 40, 120):                                         # a touchpad, then a notch
            self.wheel(s, delta)
        self.assertEqual(vol(), v + 10)
        self.settle()

    def test_volume_in_dbr_with_auto_ref_level(self):
        name = self.panel.volume_label.text
        self.assertEqual((self.session.state[(3, P.AUTO_REF_LEVEL)], name()), (1, "Volume (dBr)"))
        QTest.mouseClick(self.panel.options[P.AUTO_REF_LEVEL], Qt.LeftButton)
        self.assertEqual(name(), "Volume (dB)")
        self.settle()
        self.win.tabs.setCurrentIndex(2)                                        # IEM: no Auto Ref Level
        self.assertEqual(name(), "Volume (dB)")

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

    def test_lock_volume_holds_volume(self):
        s = self.panel.volume
        QTest.mouseClick(self.panel.options[P.LOCK_VOLUME], Qt.LeftButton)
        self.settle()
        self.assertTrue(s.toolTip().startswith("Lock Volume is on: set it in the device's menu\n"))
        self.assertTrue(s.held and not s.isEnabled())                           # the arrows grey, the value not
        self.assertEqual(s.text(s.value), "%.1f" % (self.sim.state[(3, P.VOLUME)] / 10))   # still readable
        v = self.sim.state[(3, P.VOLUME)]
        self.wheel(s, 120)
        self.volume_arrow(+1)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], v)                      # the wheel and the arrows: nothing
        QTest.mouseClick(self.panel.options[P.LOCK_VOLUME], Qt.LeftButton)
        self.settle()
        self.assertTrue(s.toolTip().startswith("Adjust with the arrows or the mouse wheel\n"))
        self.assertIn("-114.5 … +6.0, step 0.5 dB", s.toolTip())

    def test_mute_and_dim_are_options(self):
        for i in (P.MUTE, P.DIM):
            QTest.mouseClick(self.panel.options[i], Qt.LeftButton)
            self.settle()
            self.assertEqual(self.sim.state[(3, i)], 1)
            self.assertTrue(self.panel.options[i].on)

    def test_mute_and_dim_turn_the_volume_amber(self):
        s = self.panel.volume
        self.assertFalse(s.warned)
        steps = "A step turns Dim off and goes on from this level"
        how = "Adjust with the arrows or the mouse wheel"
        for i, first, second in (
                (P.DIM, "Dim is on", steps),
                (P.MUTE, "Mute and Dim are on: this output is silent", steps),
                (P.DIM, "Mute is on: this output is silent", how)):
            QTest.mouseClick(self.panel.options[i], Qt.LeftButton)
            self.settle()
            self.assertTrue(s.warned)
            self.assertEqual(s.toolTip().split("\n")[:2], [first, second])
        QTest.mouseClick(self.panel.options[P.MUTE], Qt.LeftButton)
        self.settle()
        self.assertFalse(s.warned)
        self.assertTrue(s.toolTip().startswith("Adjust with"))

    def test_hi_power_in_amber_before_headphones_are_plugged_in(self):
        self.win.tabs.setCurrentIndex(1)                                        # Phones: Lo-Power, -10.0, no plug
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
        self.win.tabs.setCurrentIndex(0)                                        # only Phones
        self.assertFalse(self.panel.steppers[P.REF_LEVEL].warned)

    def test_no_rear_trs_source(self):
        for tab in range(3):
            self.win.tabs.setCurrentIndex(tab)
            self.assertFalse(self.panel.rows[P.REAR_TRS_SOURCE].isVisible())

    def test_iem_has_no_ref_level(self):
        rows = self.panel.rows
        self.win.tabs.setCurrentIndex(1)
        self.assertTrue(rows[P.REF_LEVEL].isVisible() and rows[P.AUTO_REF_LEVEL].isVisible())
        ref = self.panel.steppers[P.REF_LEVEL]
        self.assertEqual((ref.names, ref.text(ref.value) in P.REF_LEVELS[6]), (P.REF_LEVELS[6], True))
        self.win.tabs.setCurrentIndex(2)
        self.assertFalse(rows[P.REF_LEVEL].isVisible() or rows[P.AUTO_REF_LEVEL].isVisible())
        self.assertTrue(rows[P.VOLUME].isVisible())

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

    def test_balance_as_the_device_shows_it(self):
        s = self.panel.steppers[P.BALANCE]
        self.assertEqual((s.value, s.text(s.value)), (0, "C"))
        self.arrow(P.BALANCE, -1)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -5)
        self.assertEqual(s.text(s.value), "L 5")
        QTest.keyClick(s, Qt.Key_Right, Qt.ControlModifier)                     # with Ctrl: by 1
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -4)
        self.assertEqual((s.neighbour(-4, -1, False), s.neighbour(-4, +1, False)), (-5, 0))   # onto the 5s
        self.assertIsNone(s.neighbour(100, +1, False))

    def test_minus_1_is_a_value_like_any_other(self):
        for i in (P.BALANCE, P.WIDTH):                                          # L 1, -0.01: not absent as on IEM
            self.session.set((3, i), -1)
            self.settle()
            self.assertTrue(self.panel.rows[i].isVisible())
            self.assertTrue(self.panel.steppers[i].isEnabled())
            self.session.set((3, i), -2)
            self.settle()
            self.assertEqual(self.sim.state[(3, i)], -2)

    def test_balance_opens_a_slider_by_1(self):
        s = self.panel.steppers[P.BALANCE]
        QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(s.width() // 2, s.height() // 2))
        self.spin(50)
        pop = s.popup
        self.assertTrue(pop.isVisible())
        self.assertEqual(pop.geometry().right(), s.mapToGlobal(s.rect().bottomRight()).x())   # under the stepper
        slider = pop.slider

        def send(kind, v, buttons):
            p = QPointF(slider.x_of(v), slider.height() / 2)
            QApplication.sendEvent(slider, QMouseEvent(kind, p, slider.mapToGlobal(p), Qt.LeftButton, buttons,
                                                       Qt.NoModifier))
        send(QMouseEvent.Type.MouseButtonPress, 0, Qt.LeftButton)
        for v in (-1, -2, -12):                                                 # one pixel, one step
            send(QMouseEvent.Type.MouseMove, v, Qt.LeftButton)
            self.spin(20)
            self.assertEqual((slider.value, s.value), (v, v))                   # the stepper follows
        send(QMouseEvent.Type.MouseButtonRelease, -12, Qt.NoButton)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -12)
        QTest.keyClick(pop, Qt.Key_Right)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -11)
        QTest.keyClick(pop, Qt.Key_PageUp)                                      # as the stepper's arrow
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -10)
        buttons = {b.text(): b for b in pop.findChildren(Action)}
        self.assertEqual(sorted(buttons), ["C", "L 100", "R 100"])
        for text, value in (("R 100", 100), ("L 100", -100), ("C", 0)):
            QTest.mouseClick(buttons[text], Qt.LeftButton)
            self.settle()
            self.assertEqual((self.sim.state[(3, P.BALANCE)], slider.value), (value, value))
        self.assertTrue(pop.isVisible())                                        # open, to adjust further
        self.sim.front_panel([(3, P.BALANCE, 30)])                              # the device moves the knob
        self.settle()
        self.assertEqual(slider.value, 30)
        QTest.keyClick(pop, Qt.Key_Return)
        self.spin(50)
        self.assertIsNone(s.popup)
        self.assertEqual(self.sim.state[(3, P.BALANCE)], 30)

    def test_esc_brings_balance_back(self):
        s = self.panel.steppers[P.BALANCE]
        QTest.keyClick(s, Qt.Key_Space)
        self.spin(50)
        pop = s.popup
        for _ in range(3):
            QTest.keyClick(pop, Qt.Key_Left)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -3)
        QTest.keyClick(pop, Qt.Key_Escape)
        self.settle()
        self.assertIsNone(s.popup)
        self.assertEqual(self.sim.state[(3, P.BALANCE)], 0)

    def test_the_order_of_the_level_group(self):
        y = lambda i: self.panel.rows[i].mapTo(self.panel, self.panel.rows[i].rect().topLeft()).y()   # noqa: E731
        order = [P.LOCK_VOLUME, P.VOLUME, P.AUTO_REF_LEVEL, P.REF_LEVEL, P.MUTE, P.DIM, P.BALANCE]
        self.assertEqual(sorted(order, key=y), order)

    def test_off_is_grey_on_is_bright(self):
        s = self.panel.steppers[P.MONO]
        self.assertEqual(s.off, 0)
        self.assertEqual(self.panel.steppers[P.DE_EMPHASIS].off, 2)            # Auto, On, Off: wherever it is
        self.assertEqual(self.panel.steppers[P.BALANCE].off, 0)                # C: Balance does nothing
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

    def test_lock_volume_is_an_option(self):
        QTest.mouseClick(self.panel.options[P.LOCK_VOLUME], Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.LOCK_VOLUME)], 1)
        self.assertTrue(self.panel.options[P.LOCK_VOLUME].on)

    def test_every_output_has_its_own(self):
        line = self.sim.state[(3, P.DA_FILTER)]
        self.win.tabs.setCurrentIndex(1)
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
