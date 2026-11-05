"""The window apart from the graph, Load/Save and the side panels: the layout (the graph beside the sound column),
layout by Dual EQ, the EQ and Loudness switches, Share, Loudness and its graph in the graph's place, the active output,
the status bar, the keyboard in and across the tables, spinners at the band limits."""

import math
import os
import tempfile
import time
import unittest
from unittest import mock

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from commander import __version__
from commander.device import models
from commander.device import params as P
from commander.device.models import PRO, PRO_24
from commander.device.simulator import SimulatedAdi2
from commander.ui import about
from commander.ui import loudness as L
from commander.ui import theme
from commander.ui.tables import FLASH_TIME, KEY_ROLE
from commander.ui.widgets import FRAME, SIDE, label_color, placement
from tests.gui import WindowTest, tooltip_color
from tests.support import DUMP, PRESETS


class Window(WindowTest):
    def test_about_from_the_ring_and_f1(self):
        opened = []
        self.win.ask = lambda dialog: opened.append(dialog) or True
        self.assertEqual(self.win.info.toolTip(), "About ADI-2 Commander (F1)")
        QTest.mouseClick(self.win.info, Qt.LeftButton)
        QTest.keyClick(self.win, Qt.Key_F1)
        self.assertEqual([d.windowTitle() for d in opened], ["About ADI-2 Commander"] * 2)
        text = " ".join(label.text() for label in opened[0].findChildren(QLabel))
        self.assertIn("Version %s" % __version__, text)
        self.assertIn("Tested with the ADI-2 DAC FS, firmware DSP 62 and USB 81, on Windows 11.", text)
        self.assertIn("GNU General Public License, version 3 or later", text)
        self.assertIn("Not affiliated with or endorsed by RME", text)
        self.assertIn("Qt for Python, Copyright (C) The Qt Company Ltd. and other contributors, under the GNU LGPL", text)

    def test_about_names_the_repository(self):
        shown = []
        dialog = about.AboutDialog(self.win)
        self.assertEqual(dialog.repository.text(), "GitHub")
        self.assertEqual(dialog.repository.toolTip(), "https://github.com/atvandenbosch/adi2-commander")
        with mock.patch.object(about, "show_url", shown.append):
            dialog.repository.click()
        self.assertEqual(shown, ["https://github.com/atvandenbosch/adi2-commander"])

    def test_as_far_from_the_right_edge_as_from_the_left(self):
        def edges(w):
            p = w.mapTo(self.win, QPoint(0, 0))
            return p.x(), self.win.width() - p.x() - w.width()
        for height in (900, 500):                                     # low: the column scrolls
            self.win.resize(1400, height)
            self.spin(100)
            self.assertEqual(self.win.sound.verticalScrollBar().isVisible(), height == 500)
            self.assertEqual(edges(self.win.input_tab)[0], SIDE)
            self.assertEqual([edges(w)[1] for w in (self.win.band_views[0], self.win.load_action, self.win.info)],
                             [SIDE] * 3)
            self.assertEqual(edges(self.win.sound)[1], 0)              # its scroll bar against the edge

    def test_about_opens_the_license(self):
        shown = []
        dialog = about.AboutDialog(self.win)
        self.assertTrue(dialog.license.isEnabled())
        with mock.patch.object(about, "show_file", shown.append):
            dialog.license.click()
        self.assertEqual(shown, [about.LICENSE])
        with open(about.LICENSE, encoding="utf-8") as f:
            self.assertIn("GNU GENERAL PUBLIC LICENSE", f.read(200))

    def test_two_tables_with_dual_eq_on_and_off(self):
        left, right = self.win.eq_switches
        self.assertTrue(self.win.band_views[1].isVisible())
        self.assertEqual([(s.on, s.text()) for s in (left, right)], [(True, "EQ LEFT"), (True, "EQ RIGHT")])
        self.assertEqual([s.color.name() for s in (left, right)], [theme.LEFT.name(), theme.RIGHT.name()])
        self.assertFalse(left.icon().isNull())                       # the dot, drawn
        share = self.win.dual_actions[0]
        where = share.mapTo(self.win, share.rect().topLeft())
        self.session.set_dual(3, False, keep="left")
        self.spin(100)
        self.assertTrue(self.win.band_views[1].isVisible())          # nothing moves
        self.assertEqual(share.mapTo(self.win, share.rect().topLeft()), where)    # Split where Share L was
        self.assertEqual([(s.on, s.text()) for s in (left, right)], [(True, "EQ L = R"), (True, "EQ R = L")])
        self.assertTrue(right.toolTip().startswith("Dual EQ off: one EQ for both channels\nEQ: on"))
        self.assertEqual({s.color.name() for s in (left, right)}, {theme.SHARED.name()})
        self.assertEqual({d.color.name() for d in self.win.band_delegates}, {theme.SHARED.name()})
        m = self.win.band_models
        self.assertEqual([[m[side].index(r, c).data() for r in range(5) for c in range(4)] for side in (0, 1)],
                         [[m[0].index(r, c).data() for r in range(5) for c in range(4)]] * 2)    # L = R
        self.settle()

    def test_both_tables_edit_the_one_eq_with_dual_eq_off(self):
        self.session.set_dual(3, False, keep="left")
        self.settle()
        left, right = self.win.band_views
        right.setFocus()
        right.setCurrentIndex(right.model().index(1, 2))            # band 2 gain, in the right table
        QTest.keyClick(right, Qt.Key_Up)
        gain = self.session.state[(4, 7)]
        self.assertEqual(right.model().index(1, 2).data(), left.model().index(1, 2).data())   # at once, in both
        self.settle()
        self.assertEqual(self.sim.state[(4, 7)], gain)
        QTest.mouseClick(self.win.eq_switches[1], Qt.LeftButton)     # either switch: the EQ of both
        self.assertEqual([s.on for s in self.win.eq_switches], [False, False])
        self.settle()
        self.assertEqual(self.sim.state[(4, 2)], 0)

    def test_a_switch_under_the_mouse_keeps_its_colour(self):
        for switch in self.win.eq_switches + [self.win.bt_switch, self.win.loudness_switch]:
            hover = switch.styleSheet().split("QPushButton:hover")[1].split("}")[0]
            self.assertEqual(hover.strip(" {;"), "background: %s" % theme.RAISED.name())   # only the background lights up

    def test_eq_switch_per_channel(self):
        left, right = self.win.eq_switches
        QTest.mouseClick(right, Qt.LeftButton)               # the front panel's L: only the right EQ off
        self.assertEqual((right.on, right.text()), (False, "EQ RIGHT"))
        self.settle()
        self.assertEqual((self.sim.state[(4, 2)], self.sim.state[(5, 2)]), (1, 0))
        m = self.win.band_models
        self.assertTrue(m[1].inactive(m[1].index(1, 2).data(KEY_ROLE)))       # right band 2 gain: dimmed
        self.assertFalse(m[0].inactive(m[0].index(1, 2).data(KEY_ROLE)))
        QTest.mouseClick(left, Qt.LeftButton)
        QTest.mouseClick(right, Qt.LeftButton)
        self.settle()
        self.assertEqual((self.sim.state[(4, 2)], self.sim.state[(5, 2)]), (0, 1))   # the front panel's R

    def test_use_for_both_in_one_click_and_split_again(self):
        right = {i: self.sim.state[(5, i)] for i in range(3, 20)}
        actions = self.win.dual_actions
        shown = lambda: [(a.text(), a.isVisible()) for a in actions]     # noqa: E731
        self.assertEqual(shown(), [("Share L > R", True), ("Share R > L", True)])
        self.assertEqual(actions[1].toolTip().split("\n"),
                         ["Apply the right channel's EQ to both channels (Dual EQ off).",
                          "This replaces the left channel's EQ."])
        QTest.mouseClick(actions[1], Qt.LeftButton)                          # RIGHT for both
        self.settle()
        self.assertEqual(self.sim.state[(3, 11)], 0)
        self.assertEqual({i: self.sim.state[(4, i)] for i in range(3, 20)}, right)
        self.assertEqual(shown(), [("Split L <> R", True), ("Split L <> R", False)])
        self.assertEqual(actions[0].toolTip(),
                         "Make each channel's EQ independent (Dual EQ on).\nBoth start from this EQ.")
        QTest.mouseClick(actions[0], Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(3, 11)], 1)
        self.assertEqual({i: self.sim.state[(5, i)] for i in range(3, 20)}, right)   # both start from it
        self.assertEqual(shown(), [("Share L > R", True), ("Share R > L", True)])

    def test_save_and_load_on_the_title_line_share_above_the_tables(self):
        top = lambda w: w.mapTo(self.win, w.rect().topLeft()).y()          # noqa: E731
        line = self.win.eq_title.parentWidget()
        self.assertIs(self.win.save_action.parentWidget(), line)
        self.assertIs(self.win.load_action.parentWidget(), line)
        share = {top(w) for w in self.win.dual_actions}
        self.assertEqual(len(share), 1)
        self.assertLess(top(self.win.save_action), share.pop())
        self.assertLess(top(self.win.dual_actions[0]), top(self.win.band_views[0]))

    def test_each_switch_heads_its_table_in_the_corner(self):
        views = self.win.band_views + [self.win.bt_view, self.win.loudness_view]
        switches = self.win.eq_switches + [self.win.bt_switch, self.win.loudness_switch]
        for view, switch in zip(views, switches):
            head = view.horizontalHeader()
            self.assertIs(switch.parent(), view)
            self.assertTrue(switch.isVisible())
            self.assertEqual(switch.geometry().center().y(), head.geometry().center().y())   # on the column names
            self.assertEqual(switch.x(), 0)                                                  # above the row names

    def test_loudness_switch_writes_loudness_enable(self):
        switch = self.win.loudness_switch
        line = self.sim.state[(3, 20)]
        self.assertEqual((switch.on, switch.text()), (bool(line), "LOUDNESS"))
        QTest.mouseClick(switch, Qt.LeftButton)
        self.assertEqual(switch.on, not line)                               # at once, before the device has it
        self.settle()
        self.assertEqual(self.sim.state[(3, 20)], 1 - line)
        self.assertNotIn((3, 20), self.win.marks.mismatch)
        self.win.tabs.setCurrentIndex(1)                                    # every output has its own
        phones = self.sim.state[(6, 20)]
        QTest.mouseClick(switch, Qt.LeftButton)
        self.settle()
        self.assertEqual((self.sim.state[(3, 20)], self.sim.state[(6, 20)]), (1 - line, 1 - phones))

    def test_loudness_parameters(self):
        m = self.win.loudness_model
        self.assertEqual([m.index(r, 1).data() for r in range(3)], ["7.0", "7.0", "-30.0"])   # the dump
        self.assertEqual([[m.index(r, c).data() for c in (0, 2)] for r in range(3)],
                         [["70", "0.7"], ["3500", "0.7"], ["", ""]])         # fixed in the device
        self.assertFalse(m.flags(m.index(0, 0)) & Qt.ItemIsEditable)
        self.assertTrue(m.inactive(m.index(0, 1).data(KEY_ROLE)))           # Loudness off: dimmed
        self.assertIn("1.0 … 10.0, step 0.5 dB", m.index(0, 1).data(Qt.ToolTipRole))
        view = self.win.loudness_view
        view.setFocus()
        view.setCurrentIndex(m.index(0, 1))
        QTest.keyClick(view, Qt.Key_Up)                                     # Bass Gain +0.5 dB
        view.setCurrentIndex(m.index(2, 1))
        QTest.keyClick(view, Qt.Key_PageDown)                               # Low Vol Ref -3 dB
        self.settle()
        self.assertEqual([self.sim.state[(3, i)] for i in (21, 22, 23)], [15, 14, -66])
        self.assertEqual(m.index(2, 1).data(), "-33.0")
        QTest.mouseClick(self.win.loudness_switch, Qt.LeftButton)
        self.assertFalse(m.inactive(m.index(0, 1).data(KEY_ROLE)))

    def test_loudness_graph_follows_volume_and_settings(self):
        g, view = self.win.loudness_graph, self.win.loudness_view
        view.setFocus()
        view.setCurrentIndex(view.model().index(0, 1))                     # on the stage: drawn
        self.assertEqual(g.getPlotItem().viewRange()[1], [-35, -5])         # 30 dB around Low Vol Ref -30 dB
        full = g.full_boost.getData()[1]
        self.assertAlmostEqual(full[0], -30 + 7, delta=0.3)                 # full boost at 20 Hz
        self.assertAlmostEqual(full.min(), -30, delta=0.05)                 # none in the middle
        np.testing.assert_allclose(g.no_boost.getData()[1], -10)            # No boost
        self.assertEqual(g.no_boost.opts["pen"], g.full_boost.opts["pen"])  # drawn as the Loudness curve
        self.assertEqual(g.legend.names(), ["Loudness", "No boost", "Handles", "At current volume"])
        self.assertEqual(len(g.family_levels), 78)                         # -45 ... -5 dB but three:
        self.assertFalse({-30, -10, -20.5} & set(g.family_levels))         # Loudness, No boost, the current volume
        family, now = g.family.opts["pen"], g.now.opts["pen"]
        self.assertEqual((family.dashPattern(), round(family.color().alphaF(), 2)), ([1.0, 3.0], L.FAMILY_ALPHA))
        self.assertEqual((now.dashPattern(), now.color().alphaF()), ([1.0, 3.0], 1.0))   # its own line, lit
        self.assertEqual(self.sim.state[(3, 12)], -205)                     # -20.5 dB
        self.assertAlmostEqual(g.boost[0], 7 * (20 - 9.5) / 20)             # 9.5 dB above it
        self.sim.front_panel([(3, 12, -350)])                               # turned down to -35 dB
        self.spin(300)
        self.assertEqual(g.boost, (7.0, 7.0))                               # at and below Low Vol Ref: full
        self.assertTrue(g.now.isVisible())                                  # in part: its ends reach -28 dB
        self.sim.front_panel([(3, 12, -450)])                               # -45 dB: its ends reach -38 dB
        self.spin(300)
        self.assertFalse(g.now.isVisible())                                 # below the view (-35 dB)
        self.assertNotIn("At current volume", g.legend.names())
        self.sim.front_panel([(3, 23, -40), (3, 12, -205)])                 # Low Vol Ref -20, volume -20.5
        self.spin(300)
        self.assertTrue(g.now.isVisible())                                  # below Low Vol Ref, but in view
        self.assertIn("At current volume", g.legend.names())
        self.sim.front_panel([(3, 23, -60)])
        self.sim.front_panel([(3, 12, -90)])                                # -9 dB: 21 dB above it
        self.spin(300)
        self.assertEqual(g.boost, (0.0, 0.0))
        self.win.tabs.setCurrentIndex(1)                                    # every output has its own
        self.assertAlmostEqual(g.boost[0], 7 * 0 / 20)                      # Phones at -10 dB: none

    def test_the_loudness_graph_takes_the_stage_while_one_works_in_its_table(self):
        win, stage, head = self.win, self.win.stage, self.win.graph_head
        g = win.loudness_graph
        self.assertFalse(win.sound.isAncestorOf(g))                         # not in the sound column
        self.assertIs(stage.currentWidget(), win.graph)
        self.assertEqual((g.points, len(g.legend.names())), ([], 4))        # not drawn off the stage; its legend is
        view = win.loudness_view
        view.setFocus()
        plot = win.graph.getPlotItem().getViewBox().sceneBoundingRect()
        view.setCurrentIndex(view.model().index(0, 1))
        self.assertIs(stage.currentWidget(), g)                             # at once
        self.spin(50)
        self.assertEqual(g.getPlotItem().getViewBox().sceneBoundingRect(), plot)   # in the same place
        self.assertEqual(g.getPlotItem().getAxis("left").labelText, "Volume (dB)")
        self.assertIs(head.legend, g.legend)
        self.assertTrue(g.legend.isVisible() and not win.legend.isVisible())
        self.assertTrue(win.fs_box.isVisible())                             # the sample rate stays
        QTest.mouseClick(win.loudness_switch, Qt.LeftButton)
        self.assertEqual(g.now.opts["pen"].color().rgb(), theme.LOUDNESS.rgb())
        win.fs_box.setCurrentIndex(P.SAMPLE_RATES.index(44100))
        self.spin(1100)
        self.assertIn("runs at 48 kHz.", win.fs_box.toolTip())
        self.assertNotIn("Sum curves", win.fs_box.toolTip())                # no comparison here
        win.fs_box.setCurrentIndex(P.SAMPLE_RATES.index(705600))
        self.assertEqual(win.graph_note.text(), "No Loudness at 705.6 kHz")
        self.assertEqual(g.now.opts["pen"].color().rgb(), theme.OFF.rgb())
        win.tabs.setCurrentIndex(1)                                         # another output: the stage stays
        self.assertIs(stage.currentWidget(), g)
        band = win.band_views[0]
        band.setFocus()
        band.setCurrentIndex(band.model().index(1, 1))
        self.assertIs(stage.currentWidget(), win.graph)
        self.assertIs(head.legend, win.legend)
        self.assertEqual(win.graph_note.text(), "No Bass/Treble at 705.6 kHz")
        self.settle()

    def test_the_chosen_cell_keeps_its_colour_without_focus(self):
        win, view = self.win, self.win.loudness_view
        view.setFocus()
        view.setCurrentIndex(view.model().index(1, 1))                     # Treble gain: the Loudness stage
        self.spin(50)
        rect = view.visualRect(view.currentIndex())
        fill = lambda: view.viewport().grab(rect).toImage().pixelColor(3, 3).name()   # noqa: E731
        focused = fill()
        win.fs_box.setFocus()                                               # away from the tables
        self.spin(50)
        self.assertTrue(view.chosen and not view.hasFocus())
        self.assertIs(win.stage.currentWidget(), win.loudness_graph)       # and why it is on the stage
        chosen = fill()
        band = win.band_views[0]
        band.setFocus()
        band.setCurrentIndex(band.model().index(1, 1))
        self.spin(50)
        self.assertEqual([v.chosen for v in win.band_views + [win.bt_view, view]], [True, False, False, False])
        self.assertEqual(len({focused, chosen, fill()}), 3)                # focus, fainter, none

    def test_a_switch_turned_on_takes_its_table_and_stage_turned_off_nothing(self):
        win, stage = self.win, self.win.stage
        left, right = win.band_views
        right.setFocus()
        right.setCurrentIndex(right.model().index(3, 1))
        left.setFocus()
        left.setCurrentIndex(left.model().index(2, 2))
        self.spin(50)
        QTest.mouseClick(win.loudness_switch, Qt.LeftButton)                # on: its table, where Tab enters it
        view = win.loudness_view
        self.assertEqual((view.hasFocus(), view.currentIndex().row(), view.currentIndex().column()), (True, 0, 1))
        self.assertIs(stage.currentWidget(), win.loudness_graph)
        QTest.mouseClick(win.eq_switches[1], Qt.LeftButton)                 # off: the focus stays
        self.assertTrue(view.hasFocus() and view.chosen)
        self.assertIs(stage.currentWidget(), win.loudness_graph)
        left.setFocus()
        QTest.keyClick(left, Qt.Key_Return)                                 # in an editor
        QTest.mouseClick(win.loudness_switch, Qt.LeftButton)                # off: back to its table
        self.assertTrue(left.hasFocus())
        self.assertIs(stage.currentWidget(), win.graph)
        QTest.mouseClick(win.eq_switches[1], Qt.LeftButton)                 # on: its current cell
        self.assertEqual((right.hasFocus(), right.currentIndex().row()), (True, 3))
        self.settle()
        self.assertEqual([self.sim.state[(3, P.LOUDNESS_ENABLE)], self.sim.state[(4, P.EQ_ENABLE)]], [0, 1])
        win.tabs.setFocus()
        QTest.keyClick(win.tabs, Qt.Key_Backtab)                            # no switch in the Tab order
        self.assertIn(QApplication.focusWidget(), win.band_views + [win.bt_view, view])

    def test_the_loudness_shelves_have_points_to_choose_and_drag(self):
        g, view = self.win.loudness_graph, self.win.loudness_view
        view.setFocus()
        view.setCurrentIndex(view.model().index(2, 1))                     # Low Vol Ref: the Loudness stage
        self.spin(50)
        spots = [s.pos() for s in g.handles.points()][:2]
        self.assertEqual([(round(10 ** p.x()), p.y()) for p in spots], [(70, -23.0), (3500, -23.0)])   # full boost
        self.assertEqual([t.textItem.toPlainText() for t in g.handle_labels], ["B", "T"])
        self.assertIn("Drag: gain", g._describe((3, P.LD_TREBLE)))
        vb = g.view
        at = lambda y: g.mapFromScene(vb.mapToScene(vb.mapFromView(QPointF(math.log10(3500), y))))   # noqa: E731
        p, q = at(-23.0), at(-25.0)
        QTest.mousePress(g.viewport(), Qt.LeftButton, Qt.NoModifier, p)
        self.assertEqual((view.currentIndex().row(), g.current), (1, (3, P.LD_TREBLE)))   # Treble, on the press
        for i in range(1, 11):
            QTest.mouseMove(g.viewport(), QPoint(p.x(), p.y() + (q.y() - p.y()) * i // 10))
            self.spin(20)
        QTest.mouseRelease(g.viewport(), Qt.LeftButton, Qt.NoModifier, q)
        self.settle()
        self.assertEqual(self.sim.state[(3, P.LD_TREBLE)], 10)            # +5 dB, on the device
        self.assertIs(self.win.stage.currentWidget(), g)

    def test_low_vol_ref_has_a_point_that_steers_the_scale(self):
        g, view = self.win.loudness_graph, self.win.loudness_view
        view.setFocus()
        view.setCurrentIndex(view.model().index(0, 1))
        self.spin(50)
        key, x, y, label = g.points[-1]
        self.assertEqual((key, label), ((3, P.LD_LOW_VOL_REF), None))       # no label: it has no frequency
        self.assertAlmostEqual(y, -30, delta=0.05)                          # at the lowest of the curve
        self.assertTrue(70 < 10 ** x < 3500)                                # between the shelves
        vb = g.view
        at = lambda: g.mapFromScene(vb.mapToScene(vb.mapFromView(QPointF(*g.points[-1][1:3]))))   # noqa: E731
        p = at()
        QTest.mouseClick(g.viewport(), Qt.LeftButton, Qt.NoModifier, p)
        self.assertEqual((view.currentIndex().row(), g.current), (2, key))  # Low Vol Ref, on the press
        g.stick_start(key)
        g.stick(-60)                                                        # 60 px up: 10 dB/s
        k, ref, dy, t = g._stick
        g._stick = (k, ref, dy, t - 0.5)                                    # half a second on
        g._stick_tick()
        g.stick_stop()
        self.settle()
        self.assertEqual(self.sim.state[key], -50)                          # -25 dB, on the device
        self.assertEqual(g.getPlotItem().viewRange()[1], [-30, 0])          # the scale moved ...
        self.assertLessEqual((at() - p).manhattanLength(), 1)               # ... the point stayed

    def test_focus_and_flash_in_the_colour_of_the_channel(self):
        delegates = self.win.band_delegates + [self.win.bt_delegate]
        self.assertEqual([d.color.name() for d in delegates],
                         [theme.LEFT.name(), theme.RIGHT.name(), theme.BT.name()])   # as in the graph

    def test_tables_drawn_again_only_while_a_flash_fades(self):
        views = self.win.band_views + [self.win.bt_view, self.win.loudness_view]

        def drawing():
            return [v._flash_timer.isActive() for v in views]

        self.assertEqual(drawing(), [False] * 4)                 # nothing lights up: still
        self.win.marks.start_flash((4, 5))
        self.assertEqual(drawing(), [True] * 4)
        t0 = time.monotonic()
        while any(drawing()) and time.monotonic() - t0 < 2:      # in real time, as the flash
            time.sleep(0.02)
            QApplication.processEvents()
        self.assertEqual(drawing(), [False] * 4)
        self.assertGreaterEqual(time.monotonic() - t0, FLASH_TIME * 0.9)

    def test_a_closed_window_no_longer_talks_to_the_device(self):
        self.win.close()
        self.session.close()
        sent = len(self.sim.received)
        self.spin(1000)
        self.assertEqual(len(self.sim.received), sent)

    def test_connection_in_the_status_bar(self):
        self.assertIs(self.win.lamp.parent(), self.win.statusBar())
        self.assertEqual(self.win.lamp_text.text(), "Connected")
        self.assertEqual(self.win.source.name.text(), "Manual")               # what the EQ was loaded from

    def test_a_model_that_is_not_supported(self):
        self.sim.power(False)
        self.spin(1000)
        self.sim = SimulatedAdi2.factory(PRO, presets=PRESETS, clock=self.clock)
        with mock.patch.dict(models.BY_ID, {PRO.id: PRO._replace(supported=False)}):
            self.spin(3000)
        self.assertEqual(self.win.lamp_text.text(), "ADI-2 Pro not currently supported")
        self.assertIn("ADI-2 DAC FS", self.win.lamp_text.toolTip())

    def test_what_comes_in_beside_the_connection(self):
        def bar():
            self.spin(1100)
            return self.win.input_text.text(), self.win.rate_text.text(), self.win.rate_text.styleSheet()
        quiet, warn = label_color(theme.LABEL), label_color(theme.WARN)
        self.assertEqual(bar(), ("USB (Auto)", "48 kHz PCM", quiet))
        self.sim.signal(optical=44100)
        self.assertEqual(bar(), ("Optical (Auto)", "44.1 kHz PCM", quiet))                # SPDIF before USB
        self.sim.signal()
        self.sim.front_panel([(out, 1, 1) for out in (3, 6, 9)])                # source SPDIF coax
        self.assertEqual(bar(), ("SPDIF coax", "no signal", warn))
        self.assertEqual(tooltip_color(self.win.rate_text), theme.TEXT.name())     # amber only the text
        self.sim.signal(coax=44100)
        self.assertEqual(bar(), ("SPDIF coax", "44.1 kHz PCM", quiet))
        self.sim.front_panel([(out, 1, 3) for out in (3, 6, 9)])                # source USB
        self.sim.signal(usb=176400, dsd=True)
        self.assertEqual(bar(), ("USB", "DSD64", quiet))
        self.sim.power(False)
        self.spin(1000)
        self.assertTrue(self.win.signal_info.isHidden())                         # only the lamp: no device

    def test_a_rate_the_device_does_not_run_at_is_amber(self):
        def value():
            self.spin(1100)
            return self.win.fs_box.value_color and self.win.fs_box.value_color.name()
        def bold():
            font = [self.win.fs_box.itemData(i, Qt.FontRole) for i in range(3)]
            return [f is not None and f.bold() for f in font]
        self.assertEqual((self.win.graph.fs, value(), bold()), (48000, None, [False, True, False]))
        self.win.fs_box.setCurrentIndex(0)
        self.assertEqual(value(), theme.WARN.name())                                    # 44.1 kHz, it runs at 48
        self.assertIn("runs at 48 kHz.\nSum curves at that rate are available for comparison through the legend.",
                      self.win.fs_box.toolTip())
        self.sim.front_panel([(out, 1, 1) for out in (3, 6, 9)])                       # SPDIF coax, no signal
        self.assertEqual(value(), None)
        self.sim.front_panel([(out, 1, 3) for out in (3, 6, 9)])                       # USB
        self.sim.signal(usb=176400, dsd=True)
        self.assertEqual((value(), bold()), (None, [False, False, False]))             # DSD: no DSP, no rate

    def test_dsd_bypasses_what_is_on(self):
        def state():
            self.spin(1100)
            left = self.win.eq_switches[0]
            cell = self.win.band_models[0].index(0, 2)                           # Band 1 Hz, left
            return ("dashed" in left.styleSheet(), "DSD" in left.toolTip(),
                    self.win.band_models[0].inactive(self.win.band_models[0].cell(cell)),
                    any(p.flt.active for p in self.win.graph.points))
        self.assertEqual(state(), (False, False, False, True))
        self.sim.front_panel([(out, 1, 3) for out in (3, 6, 9)])                # USB
        self.sim.signal(usb=176400, dsd=True)
        self.assertEqual(state(), (True, True, True, False))                    # on, but bypassed
        self.assertNotIn("dashed", self.win.bt_switch.styleSheet())             # off stays off
        self.sim.signal(usb=176400)
        self.assertEqual(state(), (False, False, False, True))

    def test_the_active_output_has_a_dot_on_its_tab(self):
        def marked():
            return [bool(self.win.tabs.tabToolTip(i)) for i in range(self.win.tabs.count())]
        self.spin(1100)                                                          # the first status message
        widths = [self.win.tabs.tabRect(i).width() for i in range(self.win.tabs.count())]
        self.assertEqual(marked(), [True, False, False])                         # Line Out, no plug
        self.sim.plug(6)
        self.spin(1100)
        self.assertEqual(marked(), [False, True, False])                         # a plug in Phones
        self.assertEqual(self.win.tabs.currentIndex(), 0)                        # the tab shown stays
        self.assertEqual([self.win.tabs.tabRect(i).width() for i in range(self.win.tabs.count())], widths)
        self.sim.power(False)
        self.spin(1000)
        self.assertEqual(marked(), [False, False, False])                        # no device, no dot

    def test_extra_width_goes_to_the_graph(self):
        def sizes():
            table = self.win.band_views[0]
            return (self.win.width() - table.mapTo(self.win, table.rect().topLeft()).x(), self.win.sound.width(),
                    self.win.graph.width())
        self.win.resize(1300, 1000)
        self.spin(50)
        narrow = sizes()
        self.win.resize(2560, 1000)
        self.spin(50)
        wide = sizes()
        self.assertEqual(wide[:2], narrow[:2])                              # the column stays at the right
        self.assertEqual(wide[2] - narrow[2], 2560 - 1300)

    def test_the_sound_column_does_not_hold_the_window_up(self):
        self.assertLess(self.win.minimumSizeHint().height(), 600)          # it scrolls when the window is low
        self.win.resize(1300, 500)
        self.spin(50)
        self.assertTrue(self.win.sound.verticalScrollBar().isVisible())

    def test_the_side_tabs_keep_their_width_in_a_narrow_window(self):
        self.win.resize(self.win.minimumSizeHint())
        self.spin(50)
        for tab in (self.win.input_tab, self.win.output_tab, self.win.presets_tab):
            self.assertEqual(tab.width(), tab.sizeHint().width())

    def test_legend_in_the_middle_above_the_graph(self):
        self.win.resize(2560, 1000)
        self.spin(50)
        legend, graph = self.win.legend, self.win.graph
        middle = legend.mapTo(self.win, legend.rect().center()).x()
        self.assertAlmostEqual(middle, graph.mapTo(self.win, graph.rect().center()).x(), delta=2)
        self.assertLess(legend.mapTo(self.win, legend.rect().bottomLeft()).y(),
                        graph.mapTo(self.win, graph.rect().topLeft()).y())

    def key(self, k, mods=Qt.NoModifier):
        v = next(v for v in self.win.band_views + [self.win.bt_view, self.win.loudness_view] if v.hasFocus())
        QTest.keyClick(v, k, mods)
        return self.where()

    def test_left_and_right_stop_at_the_edge_of_the_row(self):
        left = self.win.band_views[0]
        left.setFocus()
        left.setCurrentIndex(left.model().index(2, 3))              # band 3, left Q
        self.assertEqual(self.key(Qt.Key_Right), (0, 2, 3))
        left.setCurrentIndex(left.model().index(2, 0))
        self.assertEqual(self.key(Qt.Key_Left), (0, 2, 0))

    def test_alt_up_and_down_walk_the_column_through_the_stack(self):
        left = self.win.band_views[0]
        left.setFocus()
        left.setCurrentIndex(left.model().index(4, 2))              # band 5 left, Gain
        down = [self.key(Qt.Key_Down, Qt.AltModifier) for _ in range(11)]
        self.assertEqual(down[:2], [(1, 0, 2), (1, 1, 2)])           # the right table, straight below
        self.assertEqual(down[5:], [(2, 0, 1), (2, 1, 1), (3, 0, 1), (3, 1, 1), (3, 2, 1), (3, 2, 1)])
        self.assertEqual([self.key(Qt.Key_Up, Qt.AltModifier) for _ in range(6)][3:],
                         [(2, 0, 1), (1, 4, 2), (1, 3, 2)])          # back into the bands, still Gain
        left.setFocus()
        left.setCurrentIndex(left.model().index(0, 0))
        self.assertEqual(self.key(Qt.Key_Up, Qt.AltModifier), (0, 0, 0))         # the top stops
        right = self.win.band_views[1]
        right.setFocus()
        right.setCurrentIndex(right.model().index(4, 0))            # band 5 right, Type
        self.assertEqual(self.key(Qt.Key_Down, Qt.AltModifier), (2, 0, 0))       # Bass/Treble has no Type: Hz

    def where(self):
        views = self.win.band_views + [self.win.bt_view, self.win.loudness_view]
        v = next(v for v in views if v.hasFocus())
        return views.index(v), v.currentIndex().row(), v.currentIndex().column()

    def tab(self, shift=False):
        return self.key(Qt.Key_Backtab if shift else Qt.Key_Tab, Qt.ShiftModifier if shift else Qt.NoModifier)

    def test_tab_walks_left_table_then_right_then_bass_treble_then_loudness(self):
        left, right = self.win.band_views
        left.setFocus()
        left.setCurrentIndex(left.model().index(0, 0))              # band 1 left, Type
        self.assertEqual([self.tab() for _ in range(4)], [(0, 0, 1), (0, 0, 2), (0, 0, 3), (0, 1, 1)])
        left.setCurrentIndex(left.model().index(4, 3))              # band 5 left, Q
        self.assertEqual(self.tab(), (1, 0, 0))                      # right table, band 1 Type
        right.setCurrentIndex(right.model().index(4, 3))
        self.assertEqual(self.tab(), (2, 0, 0))                      # Bass Freq
        self.win.bt_view.setCurrentIndex(self.win.bt_view.model().index(1, 2))
        self.assertEqual(self.tab(), (3, 0, 1))                      # Loudness Bass Gain: Freq is fixed
        self.assertEqual([self.tab() for _ in range(3)], [(3, 1, 1), (3, 2, 1), (0, 0, 0)])   # around again
        self.assertEqual(self.tab(shift=True), (3, 2, 1))            # and back

    def test_tab_walks_both_tables_with_dual_eq_off_too(self):
        self.session.set_dual(3, False, keep="left")
        self.spin(100)
        left = self.win.band_views[0]
        left.setFocus()
        left.setCurrentIndex(left.model().index(4, 3))
        self.assertEqual(self.tab(), (1, 0, 0))
        self.settle()

    def test_tab_while_typing_commits_and_moves_on(self):
        left = self.win.band_views[0]
        left.setFocus()
        left.setCurrentIndex(left.model().index(1, 1))              # band 2 left, Freq
        QTest.keyClick(left, "9")                                    # the first key opens the editor ...
        editor = self.win.band_delegates[0].editor
        QTest.keyClick(editor, "5")                                  # ... which then has the focus
        self.assertEqual(editor.text(), "95")                        # the first key was not lost
        QTest.keyClick(editor, Qt.Key_Tab)
        self.spin(50)
        self.assertEqual(self.session.state[(4, 8)], 95)
        self.assertEqual(self.where(), (0, 1, 2))                    # on to Gain

    def test_spinner_greyed_at_the_limit(self):
        m = self.win.band_models[0]
        q4 = m.index(3, 3).data(KEY_ROLE)                          # band 4 Q = 5.0: the upper limit
        f4 = m.index(3, 1).data(KEY_ROLE)                          # band 4 Freq = 200 Hz: the lower limit
        self.assertEqual((m.can_step(q4, +1), m.can_step(q4, -1)), (False, True))
        self.assertEqual((m.can_step(f4, +1), m.can_step(f4, -1)), (True, False))
        pk = m.index(1, 0).data(KEY_ROLE)                          # band 2 type: fixed Peak
        self.assertEqual((m.can_step(pk, +1), m.can_step(pk, -1)), (False, False))


class ProWindow(WindowTest):
    """An ADI-2 Pro: the EQ of Line Out and Phones 3/4; Phones 1/2 and the panels of the input and the output's other
    settings grey, not to be opened."""

    model = PRO

    def test_the_outputs_it_controls(self):
        tabs, why = self.win.tabs, "Not yet available for the ADI-2 Pro"
        self.assertEqual([tabs.tabText(i) for i in range(3)], ["Line Out", "Phones 1/2", "Phones 3/4"])
        self.assertEqual([tabs.isTabEnabled(i) for i in range(3)], [True, False, True])
        self.assertEqual([tabs.tabToolTip(i) for i in range(3)], ["", why, ""])
        self.win.next_tab(1)
        self.assertEqual(tabs.currentIndex(), 2)
        self.win.next_tab(1)
        self.assertEqual(tabs.currentIndex(), 0)
        self.win.next_tab(-1)
        self.assertEqual(tabs.currentIndex(), 2)
        self.assertEqual(self.win.presets.output_title.text(), "PHONES 3/4")

    def test_input_and_output_panels_grey(self):
        for tab, area in ((self.win.input_tab, self.win.input_area), (self.win.output_tab, self.win.output_area)):
            self.assertFalse(tab.isEnabled())
            self.assertEqual(tab.toolTip(), "Not yet available for the ADI-2 Pro")
            QTest.mouseClick(tab, Qt.LeftButton)
            self.assertTrue(area.isHidden())
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.assertFalse(self.win.presets_area.isHidden())

    def test_the_status_bar_and_the_rate(self):
        self.assertEqual(self.win.lamp_text.text(), "Connected")
        self.assertTrue(self.win.input_text.isHidden())
        self.assertEqual((self.win.rate_text.text(), self.win.one_eq.isHidden()), ("48 kHz", True))
        self.sim.state[(12, 16)] = 6                                  # 352.8 kHz, read back by the idle refresh
        self.spin(4000)
        self.assertEqual((self.win.rate_text.text(), self.win.one_eq.isHidden()), ("352.8 kHz", False))
        self.assertIn("From 352.8 kHz the ADI-2 Pro runs the EQ on one stereo channel only", self.win.one_eq.toolTip())
        self.win.fs_box.setCurrentIndex(P.SAMPLE_RATES.index(352800))
        self.assertEqual(self.win.graph_note.text(), "No Bass/Treble at 352.8 kHz")
        self.assertNotIn("Phones and IEM", self.win.load_bt.toolTip())

    def test_a_preset_shows_where_it_is_selected(self):
        self.sim.front_panel([(7, 28, 3), (10, 28, 3)])               # Preset 2 on Phones 1/2 and Phones 3/4
        self.spin(1500)
        self.assertEqual(self.win.presets.rows[3].tags.text(), "P34")

    def test_save_names_the_device_and_the_output(self):
        self.win.tabs.setCurrentIndex(2)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "eq.txt")
            self.win.save_file(path)
            with open(path, encoding="utf-8") as f:
                head = f.read(300)
        self.assertIn("# Device: RME ADI-2 Pro\n# Output: Phones 3/4\n", head)

    def test_back_to_the_dac_fs(self):
        self.sim.power(False)
        self.spin(1000)
        self.sim = SimulatedAdi2.from_dump(DUMP, presets=PRESETS, clock=self.clock)
        self.spin(3000)
        self.assertTrue(self.session.ready())
        tabs = self.win.tabs
        self.assertEqual([tabs.tabText(i) for i in range(3)], ["Line Out", "Phones 1/2", "Phones 3/4 · IEM"])
        self.assertTrue(all(tabs.isTabEnabled(i) for i in range(3)) and self.win.input_tab.isEnabled())
        self.assertEqual(self.win.input_text.isHidden(), False)


class Pro24Window(WindowTest):
    model = PRO_24

    def test_the_eq_on_one_channel_from_705_6_khz(self):
        self.assertEqual(self.win.tabs.tabToolTip(1), "Not yet available for the ADI-2/4 Pro")
        self.sim.state[(12, 16)] = 7                                  # 384 kHz: no Bass/Treble, the EQ as before
        self.spin(4000)
        self.assertTrue(self.win.one_eq.isHidden())
        self.sim.state[(12, 16)] = 8                                  # 705.6 kHz
        self.spin(4000)
        self.assertFalse(self.win.one_eq.isHidden())


class Placement(unittest.TestCase):
    """Where a window opens: in the middle of the screen, or maximized when it does not fit."""

    def test_in_the_middle_of_the_room_with_its_frame(self):
        size, room = QSize(1000, 600), QRect(0, 40, 1280, 680)
        outer = size + FRAME
        self.assertEqual(placement(size, room),
                         QPoint((1280 - outer.width()) // 2, 40 + (680 - outer.height()) // 2))

    def test_maximized_where_it_does_not_fit(self):
        self.assertIsNone(placement(QSize(1199, 594), QRect(0, 0, 1024, 720)))          # too wide
        self.assertIsNone(placement(QSize(1000, 700), QRect(0, 0, 1280, 720)))          # too high with its frame


if __name__ == "__main__":
    unittest.main()
