"""The volume section in the top bar against the simulator: Volume with its slider, Lock Volume, Mute, Dim, the
switches of the EQ, Bass/Treble and Loudness, and Balance."""

import math
import unittest
from unittest import mock

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from commander.device import codec
from commander.device import params as P
from commander.ui import theme
from commander.ui.graph import side_color
from commander.ui.volume import GROUP_GAP, ICONS, NAME_GAP, NARROW_GAP, NARROW_PAD
from commander.ui.widgets import Action
from tests.gui import WindowTest, tab

PRESS, MOVE, RELEASE = QMouseEvent.Type.MouseButtonPress, QMouseEvent.Type.MouseMove, QMouseEvent.Type.MouseButtonRelease


class VolumeSection(WindowTest):
    def setUp(self):
        super().setUp()
        self.section = self.win.volume_section
        self.volume, self.balance = self.section.volume, self.section.balance
        self.lock, self.mute, self.dim = self.section.level.items
        self.eq, self.bt, self.loudness = self.section.sound.items
        short = self.section.sizeHint().width() - self.section.width()        # on one line, not narrowed
        if short > 0:
            self.win.resize(self.win.width() + short, self.win.height())
        for _ in range(30):                                                     # which output is active: Dim
            if self.session.device_status is not None:
                break
            self.spin(100)
        self.spin(50)

    # -- helpers --------------------------------------------------------------------------------------------------

    def arrow_at(self, direction):
        v = self.volume
        return QPoint(4 if direction < 0 else v._right() + v.ARROW // 2, v.height() // 2)

    def volume_arrow(self, direction, modifier=Qt.NoModifier):
        QTest.mouseClick(self.volume, Qt.LeftButton, modifier, self.arrow_at(direction))

    def mouse(self, kind, value, button=Qt.LeftButton):
        """A mouse event on the volume slider where value is."""
        v = self.volume
        p = QPointF(v.x_of(value), v.height() / 2)
        buttons = Qt.NoButton if kind == RELEASE else button
        QApplication.sendEvent(v, QMouseEvent(kind, p, v.mapToGlobal(p), button, buttons, Qt.NoModifier))

    def wheel(self, widget, delta, modifier=Qt.NoModifier):
        centre = QPointF(widget.rect().center())
        QApplication.sendEvent(widget, QWheelEvent(centre, QPointF(widget.mapToGlobal(centre.toPoint())), QPoint(0, 0),
                                                   QPoint(0, delta), Qt.NoButton, modifier, Qt.NoScrollPhase, False))

    def volume_writes(self, since):
        """The Volume values written to Line Out since that many messages, in order."""
        return [v for m in self.sim.received[since:] if m[5] == 0x02
                for a, i, v, _ in (codec.decode_triplet(*t) for t in codec.parameter_triplets([m]))
                if (a, i) == (3, P.VOLUME)]

    def recorder(self, steps):
        """Each step Volume takes: (time, Volume before, the offset of the device's scale then, Volume after). The
        control takes a step first, so the Volume before is the one after the step before."""
        last = [self.volume.value]

        def record(v):
            steps.append((self.clock.t, last[0], P.volume_offset(self.session.state, 3), v))
            last[0] = v
        return record

    def assert_held_steps(self, steps, direction):
        """Each step after the first as fast as the remote control at its level (params.volume_held)."""
        for _, before, offset, after in steps[1:]:
            self.assertEqual(after, P.volume_held(before, direction, offset, self.volume.floor))

    def hold(self, direction, ms, key=False):
        """The arrow (or the arrow key) held for ms of simulated time; the steps it took, as recorder."""
        s, times = self.volume, []
        record = self.recorder(times)
        s.chosen.connect(record)
        at = self.arrow_at(direction)
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
        s, slack = self.volume, 0.15                                            # a slot being read holds a write up
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

    # -- Volume ---------------------------------------------------------------------------------------------------

    def test_volume_steps_by_half_a_db(self):
        s, vol = self.volume, lambda: self.session.state[(3, P.VOLUME)]         # noqa: E731
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

    def test_the_slider_from_the_bottom_of_the_devices_scale(self):
        s = self.volume
        self.assertEqual(s.floor, -1145)                                        # Line, Auto Ref Level on: dBr
        self.assertEqual((s.fraction(s.floor), s.fraction(s.KNEE), s.fraction(P.OUTPUT_RANGES[P.VOLUME][1])),
                         (0, s.KNEE_AT, 1))                                     # a quarter below -60 dB
        self.assertEqual(s.ticks(), [s.KNEE, 0])
        self.assertEqual(s.value_at(s.x_of(-203)), -205)                       # by the mouse onto the half dBs
        self.assertIn("-114.5 … +6.0", s.toolTip())
        self.session.set((3, P.AUTO_REF_LEVEL), 0)
        self.settle()
        self.assertEqual(s.floor, -965)                                         # off: -96.5 dB, the dash
        self.assertIn("-96.5 … +6.0", s.toolTip())
        self.session.set((3, P.VOLUME), -965)
        self.settle()
        self.assertFalse(s.can_step(-1))
        self.volume_arrow(-1)
        self.mouse(PRESS, -1145)                                                # left of the bottom
        self.mouse(RELEASE, -1145)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], -965)                   # no lower than the dash

    def test_every_step_above_the_knee_under_a_pixel(self):
        s, hi = self.volume, P.OUTPUT_RANGES[P.VOLUME][1]
        pixels = range(math.floor(s.x_of(s.KNEE)), math.ceil(s.x_of(hi)) + 1)
        self.assertLessEqual(set(range(s.KNEE, hi + 1, P.VOLUME_STEP)), {s.value_at(x) for x in pixels})

    def test_the_name_of_volume_abbreviated_is_in_full_in_the_tooltips(self):
        name, s = self.section.volume_name, self.volume
        name.set_stage(1)
        self.assertEqual((name.text(), name.toolTip()), ("Vol", s.toolTip()))
        self.assertTrue(s.toolTip().startswith("Volume\n"))
        narrow, full = reversed(name.widths())
        self.assertLess(narrow, full)
        name.set_stage(0)
        self.assertEqual((name.text(), name.toolTip()), ("Volume", ""))
        self.assertFalse(s.toolTip().startswith("Volume\n"))

    def test_lower_on_the_slider_is_written_at_once(self):
        v, since = self.sim.state[(3, P.VOLUME)], len(self.sim.received)
        self.mouse(PRESS, v - 200)
        self.settle()
        self.mouse(MOVE, v - 300)
        self.settle()
        self.mouse(RELEASE, v - 300)
        self.assertEqual(self.volume_writes(since), [v - 200, v - 300])

    def test_higher_on_the_slider_rises_step_by_step_while_held(self):
        s, v, since = self.volume, self.sim.state[(3, P.VOLUME)], len(self.sim.received)
        ref, steps = self.sim.state[(3, P.REF_LEVEL)], []
        record = self.recorder(steps)
        s.chosen.connect(record)
        self.mouse(PRESS, v + 60)                                               # past where Auto Ref Level changes
        self.spin(500)
        self.assertEqual(s._rise[0], v + 60)                                    # the ring ahead of the knob
        self.assertLess(s.value, v + 60)
        self.spin(2500)
        self.mouse(RELEASE, v + 60)
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
        self.assertEqual((self.sim.state[(3, P.VOLUME)], s.value, s._rise), (v + 60, v + 60, None))

    def test_moving_the_mouse_while_it_rises_keeps_the_pace(self):
        s, v, times = self.volume, self.sim.state[(3, P.VOLUME)], []
        s.chosen.connect(lambda _: times.append(self.clock.t))
        self.mouse(PRESS, v + 250)
        for n in range(100):
            self.mouse(MOVE, v + 250 - 5 * (n % 2))
            self.spin(20)
        self.assertLess(s.value, v + 245)                                       # still on its way
        self.mouse(RELEASE, v + 250)
        self.settle()
        self.assertGreaterEqual(len(times), 5)
        self.assertTrue(all(b - a >= s.REPEAT_INTERVAL - 1e-6 for a, b in zip(times, times[1:])))

    def test_letting_go_stops_the_rise(self):
        v = self.sim.state[(3, P.VOLUME)]
        self.mouse(PRESS, v + 100)
        self.spin(450)
        self.mouse(RELEASE, v + 100)
        n = self.session.state[(3, P.VOLUME)]
        self.assertGreater(n, v)
        self.spin(1000)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], n)                      # where it had got to
        self.assertFalse(self.session._held)

    def test_no_step_before_the_previous_one_has_gone_out(self):
        s, v, since, gone = self.volume, self.sim.state[(3, P.VOLUME)], len(self.sim.received), [False]
        s.sent = lambda: gone[0]                                                # as if still queued
        steps = []
        s.chosen.connect(self.recorder(steps))
        self.mouse(PRESS, v + 50)
        self.spin(1000)
        self.assertEqual(self.volume_writes(since), [])                         # it waits
        gone[0] = True
        self.spin(500)                                                          # at once, 0.2 and 0.4 s later
        self.assertEqual(len(steps), 3)
        self.assertEqual(self.volume_writes(since), [a for _, _, _, a in steps])
        self.mouse(RELEASE, v + 50)
        self.settle()

    def test_a_step_or_the_device_stops_the_rise(self):
        s, v = self.volume, self.sim.state[(3, P.VOLUME)]
        self.mouse(PRESS, v + 60)
        self.spin(300)
        QTest.keyClick(s, Qt.Key_Down)                                          # a step of one's own
        n = self.session.state[(3, P.VOLUME)]
        self.spin(1000)
        self.assertEqual(self.session.state[(3, P.VOLUME)], n)
        self.mouse(RELEASE, v + 60)
        self.settle()
        self.mouse(PRESS, n + 60)
        self.spin(300)
        self.sim.front_panel([(3, P.VOLUME, -400)])                             # the device's own knob
        self.spin(1000)
        self.mouse(RELEASE, n + 60)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], -400)

    def test_the_right_button_follows_the_mouse_from_its_first_move(self):
        s, v, since = self.volume, self.sim.state[(3, P.VOLUME)], len(self.sim.received)
        self.mouse(PRESS, v + 200, Qt.RightButton)
        self.spin(500)
        self.assertEqual((self.session.state[(3, P.VOLUME)], self.volume_writes(since)), (v, []))   # the press: none
        self.assertTrue(self.session._held)
        self.mouse(MOVE, v + 200, Qt.RightButton)
        self.assertEqual(self.session.state[(3, P.VOLUME)], v + 200)           # up at once, past a held step
        self.mouse(MOVE, v - 100, Qt.RightButton)
        self.assertEqual(s.value, v - 100)
        self.mouse(RELEASE, v - 100, Qt.RightButton)
        self.assertFalse(self.session._held)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], v - 100)

    def test_the_right_button_shows_only_what_is_written(self):
        s, v = self.volume, self.sim.state[(3, P.VOLUME)]
        self.mouse(PRESS, v, Qt.RightButton)
        with mock.patch.object(self.session, "writable", return_value=False):
            self.mouse(MOVE, v + 100, Qt.RightButton)
        self.assertEqual((s.value, self.session.state[(3, P.VOLUME)]), (v, v))
        self.mouse(RELEASE, v + 100, Qt.RightButton)

    def test_a_held_arrow_repeats_after_a_pause_up_half_a_db_per_write(self):
        self.assert_held(+1, key=False)

    def test_a_held_key_repeats_at_the_same_pace_down_in_larger_steps(self):
        self.assert_held(-1, key=True)

    def test_letting_go_of_ctrl_leaves_a_held_key_held(self):
        s = self.volume
        s.setFocus()
        QApplication.sendEvent(s, QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.ControlModifier))
        QApplication.sendEvent(s, QKeyEvent(QEvent.KeyRelease, Qt.Key_Control, Qt.NoModifier))
        self.assertEqual(s._hold, -1)
        QApplication.sendEvent(s, QKeyEvent(QEvent.KeyRelease, Qt.Key_Down, Qt.NoModifier))
        self.assertIsNone(s._hold)
        self.settle()

    def test_held_out_of_dim_from_the_level_reported(self):
        v = self.sim.state[(3, P.VOLUME)]
        QTest.mouseClick(self.dim, Qt.LeftButton)
        self.settle()
        steps = self.hold(+1, 1500)
        self.settle()
        self.assertEqual((steps[0][3], self.sim.state[(3, P.DIM)]), (v - 200 + 5, 0))   # Dim off, 0.5 dB up
        self.assertGreaterEqual(steps[1][0] - steps[0][0], self.volume.REPEAT_DELAY - 1e-6)
        self.assert_held_steps(steps, +1)
        self.assertEqual(self.sim.state[(3, P.VOLUME)], steps[-1][3])

    def test_out_of_dim_a_step_goes_from_the_level_reported(self):
        vol, dim = (lambda: self.sim.state[(3, P.VOLUME)]), (lambda: self.sim.state[(3, P.DIM)])  # noqa: E731
        v = vol()
        QTest.mouseClick(self.dim, Qt.LeftButton)                               # Line Out is active
        self.settle()
        self.assertEqual(vol(), v - 200)                                        # the device moved it down
        self.volume_arrow(+1)                                                   # no jump back: 0.5 dB
        self.settle()
        self.assertEqual((vol(), dim()), (v - 195, 0))
        QTest.mouseClick(self.dim, Qt.LeftButton)
        self.settle()
        self.volume_arrow(-1)
        self.settle()
        self.assertEqual((vol(), dim()), (v - 195 - 200 - 5, 0))
        QTest.mouseClick(self.dim, Qt.LeftButton)                               # Dim on, and off again: back up
        self.settle()
        QTest.mouseClick(self.dim, Qt.LeftButton)
        self.settle()
        self.assertEqual((vol(), dim()), (v - 400, 0))

    def test_the_wheel_by_the_notch_without_the_focus(self):
        s, vol = self.volume, lambda: self.session.state[(3, P.VOLUME)]         # noqa: E731
        v = vol()
        self.assertFalse(s.hasFocus())
        for delta in (40, 40, 40, 120):                                         # a touchpad, then a notch
            self.wheel(s, delta)
        self.assertEqual(vol(), v + 10)
        self.settle()

    def test_volume_in_dbr_with_auto_ref_level(self):
        s = self.volume
        self.assertEqual((self.session.state[(3, P.AUTO_REF_LEVEL)], s.unit), (1, "dBr"))
        self.session.set((3, P.AUTO_REF_LEVEL), 0)
        self.assertEqual(s.unit, "dB")
        self.settle()
        self.win.tabs.setCurrentIndex(tab(9))                                   # IEM: no Auto Ref Level
        self.assertEqual(s.unit, "dB")

    def test_lock_volume_holds_volume(self):
        s = self.volume
        QTest.mouseClick(self.lock, Qt.LeftButton)
        self.settle()
        self.assertTrue(s.toolTip().startswith("Lock Volume is on: set it in the device's menu.\n"))
        self.assertTrue(s.held and not s.isEnabled())                           # the arrows grey, the value not
        self.assertEqual(s.text(s.value), "%.1f" % (self.sim.state[(3, P.VOLUME)] / 10))   # still readable
        self.assertEqual(s.cursor().shape(), Qt.ArrowCursor)
        v = self.sim.state[(3, P.VOLUME)]
        self.wheel(s, 120)
        self.volume_arrow(+1)
        for button in (Qt.LeftButton, Qt.RightButton):
            self.mouse(PRESS, v - 100, button)
            self.mouse(MOVE, v - 100, button)
            self.mouse(RELEASE, v - 100, button)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.VOLUME)], v)                      # the wheel, arrows, slider: nothing
        QTest.mouseClick(self.lock, Qt.LeftButton)
        self.settle()
        self.assertTrue(s.toolTip().startswith("Adjust with the arrows, the slider or the mouse wheel.\n"))
        self.assertIn("-114.5 … +6.0, step 0.5 dB", s.toolTip())

    # -- Lock, Mute, Dim ------------------------------------------------------------------------------------------

    def test_lock_mute_and_dim_switch_on_and_off(self):
        for i, seg in ((P.LOCK_VOLUME, self.lock), (P.MUTE, self.mute), (P.DIM, self.dim)):
            QTest.mouseClick(seg, Qt.LeftButton)
            self.settle()
            self.assertEqual((self.sim.state[(3, i)], seg.on), (1, True))
        self.assertTrue(self.mute.toolTip().startswith("Mute: on\nOn: mutes this output."))
        for i, seg in ((P.LOCK_VOLUME, self.lock), (P.MUTE, self.mute), (P.DIM, self.dim)):
            QTest.mouseClick(seg, Qt.LeftButton)
            self.settle()
            self.assertEqual((self.sim.state[(3, i)], seg.on), (0, False))

    def test_ctrl_shift_m_switches_mute(self):
        for on in (1, 0):
            QTest.keyClick(self.win, Qt.Key_M, Qt.ControlModifier | Qt.ShiftModifier)
            self.settle()
            self.assertEqual((self.sim.state[(3, P.MUTE)], self.mute.on), (on, bool(on)))

    def test_mute_and_dim_turn_the_volume_amber(self):
        s = self.volume
        self.assertFalse(s.warned)
        steps = "A step turns Dim off and goes on from this level."
        how = "Adjust with the arrows, the slider or the mouse wheel."
        for seg, first, second in ((self.dim, "Dim is on.", steps), (self.mute, "Mute and Dim are on.", steps),
                                   (self.dim, "Mute is on.", how)):
            QTest.mouseClick(seg, Qt.LeftButton)
            self.settle()
            self.assertTrue(s.warned)
            self.assertEqual(s.toolTip().split("\n")[:2], [first, second])
        QTest.mouseClick(self.mute, Qt.LeftButton)
        self.settle()
        self.assertFalse(s.warned)
        self.assertTrue(s.toolTip().startswith("Adjust with"))

    def test_dim_only_on_the_active_output(self):
        dim = self.dim
        self.assertTrue(dim.isEnabled())                                        # Line Out, active
        self.assertEqual(dim.cursor().shape(), Qt.PointingHandCursor)
        self.win.tabs.setCurrentIndex(tab(6))                                   # Phones, not active
        self.assertFalse(dim.isEnabled())
        self.assertEqual(dim.cursor().shape(), Qt.ArrowCursor)
        self.assertIn("Dim works on the active output only.", dim.toolTip())
        self.sim.plug(6)
        self.spin(1100)
        self.assertTrue(dim.isEnabled())
        self.assertNotIn("active output only", dim.toolTip())

    def test_lock_mute_and_dim_as_icons_of_one_width(self):
        level = self.section.level
        hints, tips = [], [s.toolTip() for s in level.items]
        for stage in (0, 1):
            level.set_stage(stage)
            hints.append(level.sizeHint().width())
        self.assertEqual(level.widths(), hints)
        self.assertLess(hints[1], hints[0])
        self.assertEqual(len({s.sizeHint().width() for s in level.items}), 1)
        self.assertEqual(self.mute.runs, [(ICONS[P.MUTE], theme.OFF)])
        self.assertEqual([s.toolTip() for s in level.items], tips)              # the names are there
        QTest.mouseClick(self.mute, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.mute.runs, [(ICONS[P.MUTE], theme.WARN)])
        level.set_stage(0)
        self.assertEqual([self.runs(s) for s in level.items], [["Lock"], ["Mute"], ["Dim"]])

    # -- EQ, B/T, LD ----------------------------------------------------------------------------------------------

    def runs(self, seg):
        return [t for t, _ in seg.runs]

    def test_eq_off_while_either_channel_has_it_on_else_on_for_both(self):
        eq = lambda: (self.sim.state[(4, P.EQ_ENABLE)], self.sim.state[(5, P.EQ_ENABLE)])   # noqa: E731
        self.assertEqual((eq(), self.runs(self.eq), self.eq.on), ((1, 1), ["EQ", "L", "R"], True))
        self.session.set((5, P.EQ_ENABLE), 0)
        self.settle()
        self.assertIn("EQ: left on, right off", self.eq.toolTip())
        QTest.mouseClick(self.eq, Qt.LeftButton)
        self.settle()
        self.assertEqual((eq(), self.eq.on), ((0, 0), False))
        QTest.mouseClick(self.eq, Qt.LeftButton)
        self.settle()
        self.assertEqual(eq(), (1, 1))

    def test_eq_with_dual_eq_off_one_for_both_channels(self):
        width = self.eq.sizeHint().width()
        self.sim.front_panel([(*P.dual_eq_key(3), 0)])                         # Dual EQ off on the device
        self.spin(100)
        self.session.set((4, P.EQ_ENABLE), 0)
        self.settle()
        self.assertEqual((self.runs(self.eq), self.eq.on), (["EQ", "L=R"], False))
        self.assertEqual(self.eq.sizeHint().width(), width)                     # the bar stays as it is
        QTest.mouseClick(self.eq, Qt.LeftButton)                                # on the left address only
        self.settle()
        self.assertEqual((self.sim.state[(4, P.EQ_ENABLE)], self.eq.on), (1, True))

    def test_eq_with_dual_eq_off_while_the_device_is_read(self):
        self.sim.front_panel([(*P.dual_eq_key(3), 0)])
        self.spin(100)
        self.session.status = "loading"
        self.addCleanup(setattr, self.session, "status", "ready")
        self.section.refresh()
        self.assertEqual((self.runs(self.eq), self.eq.on, self.eq.isEnabled()), (["EQ", "L=R"], False, False))

    def test_bass_treble_and_loudness_switch_on_and_off(self):
        for seg, key in ((self.bt, (4, P.BT_ENABLE)), (self.loudness, (3, P.LOUDNESS_ENABLE))):
            self.assertFalse(seg.on)
            QTest.mouseClick(seg, Qt.LeftButton)
            self.settle()
            self.assertEqual((self.sim.state[key], seg.on), (1, True))
            QTest.mouseClick(seg, Qt.LeftButton)
            self.settle()
            self.assertEqual((self.sim.state[key], seg.on), (0, False))

    def test_narrower_the_eq_in_two_letters_one_for_each_channel(self):
        left, right = (side_color(side, True) for side in (0, 1))
        sound, hints = self.section.sound, []
        for stage in (0, 1):
            sound.set_stage(stage)
            hints.append(sound.sizeHint().width())
        self.assertEqual(sound.widths(), hints)
        self.assertLess(hints[1], hints[0])
        self.assertEqual([self.runs(s) for s in sound.items], [["E", "Q"], ["BT"], ["LD"]])
        self.assertEqual(self.eq.runs, [("E", left), ("Q", right)])             # the left channel, the right
        self.session.set((5, P.EQ_ENABLE), 0)
        self.settle()
        self.assertEqual(self.eq.runs, [("E", left), ("Q", theme.OFF)])
        self.assertIn("EQ: left on, right off", self.eq.toolTip())
        self.sim.front_panel([(*P.dual_eq_key(3), 0)])                          # Dual EQ off: one for both
        self.spin(100)
        self.settle()
        self.assertEqual(self.eq.runs, [("E", theme.SHARED), ("Q", theme.SHARED)])
        self.assertEqual(sound.sizeHint().width(), hints[1])
        sound.set_stage(0)
        self.assertEqual([self.runs(s) for s in sound.items], [["EQ", "L=R"], ["B/T"], ["LD"]])

    def test_narrower_the_six_segments_of_one_width_each_name_with_room(self):
        segments = self.section.level.items + self.section.sound.items
        for group in (self.section.level, self.section.sound):
            group.set_stage(1)
        self.settle()
        self.assertEqual({s.width() for s in segments}, {max(s.name_width(1) for s in segments) + 2 * NARROW_PAD})

    # -- Balance --------------------------------------------------------------------------------------------------

    def balance_arrow(self, direction):
        s = self.balance
        QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(4 if direction < 0 else s.width() - 4, s.height() // 2))

    def test_balance_as_the_device_shows_it(self):
        s = self.balance
        self.assertEqual((s.value, s.text(s.value), s.off), (0, "C", 0))       # C: grey, as off
        self.balance_arrow(-1)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -5)
        self.assertEqual(s.text(s.value), "L 5")
        QTest.keyClick(s, Qt.Key_Right, Qt.ControlModifier)                     # with Ctrl: by 1
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -4)
        self.assertEqual((s.neighbour(-4, -1, False), s.neighbour(-4, +1, False)), (-5, 0))   # onto the 5s
        self.assertIsNone(s.neighbour(100, +1, False))
        self.wheel(s, 120)
        self.wheel(s, -120, Qt.ControlModifier)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -1)                    # the wheel: onto the 5s, by 1

    def test_balance_minus_1_is_a_value_like_any_other(self):
        self.session.set((3, P.BALANCE), -1)                                    # L 1: not absent as on IEM
        self.settle()
        self.assertTrue(self.balance.isEnabled())
        self.assertEqual(self.balance.value, -1)
        self.session.set((3, P.BALANCE), -2)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -2)

    def test_a_held_balance_arrow_repeats_after_a_pause(self):
        s, bal = self.balance, lambda: self.session.state[(3, P.BALANCE)]       # noqa: E731
        at = QPoint(4, s.height() // 2)
        QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, at)
        self.assertEqual(bal(), -5)
        self.spin(400)
        self.assertEqual(bal(), -5)                                             # the pause
        self.spin(400)
        self.assertLess(bal(), -10)
        QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, at)
        n = bal()
        self.spin(500)
        self.assertEqual(bal(), n)
        self.settle()

    def test_balance_opens_a_slider_by_1(self):
        s = self.balance
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
        send(PRESS, 0, Qt.LeftButton)
        for v in (-1, -2, -12):                                                 # one pixel, one step
            send(MOVE, v, Qt.LeftButton)
            self.spin(20)
            self.assertEqual((slider.value, s.value), (v, v))                   # the stepper follows
        send(RELEASE, -12, Qt.NoButton)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -12)
        QTest.keyClick(pop, Qt.Key_Right)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -11)
        QTest.keyClick(pop, Qt.Key_PageUp)                                      # as the stepper's arrow
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], -10)
        self.sim.front_panel([(3, P.BALANCE, 30)])                              # the device moves the knob
        self.settle()
        self.assertEqual(slider.value, 30)
        buttons = {b.text(): b for b in pop.findChildren(Action)}
        self.assertEqual(sorted(buttons), ["C", "L", "R"])
        QTest.mouseClick(buttons["R"], Qt.LeftButton)                           # a named point: chosen, and done
        self.spin(50)
        self.assertIsNone(s.popup)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.BALANCE)], 100)

    def test_esc_brings_balance_back(self):
        s = self.balance
        s.setFocus()
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

    def test_the_name_of_balance_abbreviated_is_in_full_in_the_tooltips(self):
        name, s, hints = self.section.balance_name, self.balance, []
        for stage, text in enumerate(("Balance", "Bal")):
            name.set_stage(stage)
            hints.append(name.sizeHint().width())
            self.assertEqual(name.text(), text)
            self.assertEqual(s.toolTip().startswith("Balance\n"), stage == 1)
            self.assertEqual(name.toolTip(), s.toolTip() if stage else "")
        self.assertEqual(name.widths(), hints)
        self.assertLess(hints[1], hints[0])
        name.set_stage(0)
        self.assertEqual((name.text(), name.toolTip()), ("Balance", ""))

    # -- the bar --------------------------------------------------------------------------------------------------

    def test_narrowed_step_by_step_before_it_takes_a_second_line(self):
        s, tabs = self.section, self.win.tabs
        widgets = lambda: [[line.itemAt(i).widget() for i in range(line.count())   # noqa: E731
                            if line.itemAt(i).widget()] for line in s.lines]
        gaps = lambda: [[line.itemAt(i).spacerItem().sizeHint().width() for i in range(line.count())   # noqa: E731
                         if line.itemAt(i).spacerItem() and line.itemAt(i).spacerItem().sizeHint().width()]
                        for line in s.lines]
        one = [[s.volume_name, s.volume, s.level, s.sound, s.balance_name, s.balance], []]
        two = [[s.volume_name, s.volume], [s.level, s.sound, s.balance_name, s.balance]]
        staged = [s.volume_name, s.balance_name, s.sound, s.level]
        name, wide, narrow = NAME_GAP, GROUP_GAP, NARROW_GAP
        ways = [  # lines, steps, narrowed, the room between the parts
            (1, 0, [], [[name, wide, wide, wide, name], []]),
            (1, 1, [s.volume_name, s.balance_name], [[name, wide, wide, wide, name], []]),
            (1, 2, [s.volume_name, s.balance_name, s.sound], [[name, wide, wide, narrow, name], []]),
            (1, 3, staged, [[name, narrow, narrow, narrow, name], []]),
            (2, 0, [], [[name], [wide, wide, name]]),
            (2, 1, [s.volume_name, s.balance_name], [[name], [wide, wide, name]]),
            (2, 2, [s.volume_name, s.balance_name, s.sound], [[name], [wide, narrow, name]]),
            (2, 3, staged, [[name], [narrow, narrow, name]])]
        needs = [s._needs(n, k) for n, k, _, _ in ways]
        self.assertEqual(needs, sorted(needs, reverse=True))
        self.assertEqual(len(set(needs)), len(needs))                           # each step narrower
        self.assertEqual((needs[0], needs[-1]), (s.sizeHint().width(), s.minimumSizeHint().width()))
        heights = {}
        for (n, k, narrowed, room), need, after in zip(ways, needs, ways[1:] + ways[-1:]):
            s.resize(need - 1, s.height())
            self.assertEqual((s.n_lines, s.narrowed), after[:2])                # a pixel less: the next way
            s.resize(need, s.height())
            self.assertEqual((s.n_lines, s.narrowed), (n, k))
            s.layout().activate()
            self.assertEqual((widgets(), gaps()), (one if n == 1 else two, room))
            self.assertEqual([p for p in staged if p.stage], narrowed)
            for line in filter(None, widgets()):                                # it fits as reckoned
                self.assertLessEqual(max(w.geometry().right() + 1 for w in line), need)
            self.assertEqual(s.bar_height(), s.bar_height(n))
            heights.setdefault(n, tabs.sizeHint().height())
        self.assertLess(heights[1], heights[2])                                 # the tabs as high
        s.resize(needs[-1] - 50, s.height())
        self.assertEqual((s.n_lines, s.narrowed), (2, 3))                       # narrower than all: as narrow
        s.resize(needs[0], s.height())
        self.assertEqual((s.n_lines, s.narrowed, [p.stage for p in staged]), (1, 0, [0, 0, 0, 0]))
        self.assertEqual(tabs.sizeHint().height(), heights[1])


if __name__ == "__main__":
    unittest.main()
