"""The window apart from the graph, Import/Export and the side panels: the layout (the graph beside the sound column),
layout by Dual EQ, the EQ and Loudness switches, Share, Loudness and its graph in the graph's place, the active output,
the status bar, the keyboard in and across the tables, spinners at the band limits."""

import math
import os
import tempfile
import time
import unittest
from unittest import mock

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QSettings, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from commander import __version__
from commander.device import models
from commander.device import params as P
from commander.device.models import PRO, PRO_24
from commander.device.simulator import SimPort, SimulatedAdi2
from commander.session import Session
from commander import app as commander_app
from commander.ui import about
from commander.ui import loudness as L
from commander.conversion import setupfile
from commander.ui import simulated, theme
from commander.ui.tables import FLASH_TIME, KEY_ROLE
from commander.ui.output import PHONES_REF
from commander.ui.untested import UntestedBox
from commander.ui.window import PHONES_1_2, MainWindow
from commander.ui.widgets import FRAME, SIDE, label_color, placement
from tests.gui import OUTPUT_TABS, Clock, WindowTest, hover, tab, tooltip_color
from tests.support import DUMP, PRESETS


class Window(WindowTest):
    def test_about_from_the_menu_and_f1(self):
        opened = []
        self.win.ask = lambda dialog: opened.append(dialog) or True
        self.assertEqual(self.win.more.toolTip(), "More options")
        menu = self.win.more_menu()
        self.assertEqual([a.text() for a in menu.actions()], ["View backups", "", "About ADI-2 Commander"])
        self.assertFalse(menu.actions()[0].isEnabled())                       # no folder given
        menu.actions()[2].trigger()
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
            self.assertEqual([edges(w)[1] for w in (self.win.band_views[0], self.win.export_action, self.win.more)],
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

    def test_import_and_export_on_the_title_line_share_above_the_tables(self):
        top = lambda w: w.mapTo(self.win, w.rect().topLeft()).y()          # noqa: E731
        line = self.win.eq_title.parentWidget()
        self.assertIs(self.win.export_action.parentWidget(), line)
        self.assertIs(self.win.import_action.parentWidget(), line)
        share = {top(w) for w in self.win.dual_actions}
        self.assertEqual(len(share), 1)
        self.assertLess(top(self.win.export_action), share.pop())
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
        self.win.tabs.setCurrentIndex(tab(6))                                    # every output has its own
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
        self.win.tabs.setCurrentIndex(tab(6))                                    # every output has its own
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
        win.tabs.setCurrentIndex(tab(6))                                         # another output: the stage stays
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

    def test_no_notice_for_the_dac_fs(self):
        self.assertEqual(self.dialogs, [])

    def test_connection_in_the_status_bar(self):
        self.assertIs(self.win.lamp.parent(), self.win.statusBar())
        self.assertEqual(self.win.lamp_text.text(), "Connected")
        self.assertEqual(self.win.source.name.text(), "Manual")               # what the EQ was loaded from

    def test_the_connected_model_in_the_title(self):
        self.assertEqual(self.win.windowTitle(), "ADI-2 Commander – ADI-2 DAC FS")
        self.sim.power(False)
        self.spin(1000)
        self.assertEqual(self.win.windowTitle(), "ADI-2 Commander")

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
            return [bool(self.win.tabs.tabToolTip(i)) for i in OUTPUT_TABS]
        self.spin(1100)                                                          # the first status message
        widths = [self.win.tabs.tabRect(i).width() for i in OUTPUT_TABS]
        self.assertEqual(marked(), [True, False, False])                         # Line Out, no plug
        self.sim.plug(6)
        self.spin(1100)
        self.assertEqual(marked(), [False, True, False])                         # a plug in Phones
        self.assertEqual(self.win.tabs.currentIndex(), tab(3))                   # the tab shown stays
        self.assertEqual([self.win.tabs.tabRect(i).width() for i in OUTPUT_TABS], widths)
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

    def test_as_many_panels_as_the_screen_has_room_for(self):
        win = self.win
        win.resize(1200, 700)
        win.move(0, 0)
        tabs = (win.input_tab, win.output_tab, win.presets_tab, win.device_tab)
        opened = lambda: [t.text for t in tabs if t.open]                       # noqa: E731
        for t in tabs:                                                          # full HD: three of them
            QTest.mouseClick(t, Qt.LeftButton)
            self.spin(50)
        self.assertEqual(opened(), ["OUTPUT", "PRESETS", "DEVICE"])          # the one open longest closed
        self.assertFalse(win.input_area.isVisible())
        self.assertLessEqual(win.frameGeometry().right(), self.room.right())
        QTest.mouseClick(win.input_tab, Qt.LeftButton)
        self.spin(50)
        self.assertEqual(opened(), ["INPUT", "PRESETS", "DEVICE"])
        win.room = lambda: QRect(0, 0, 1280, 680)                             # 1920 x 1080 at 150 %
        QTest.mouseClick(win.output_tab, Qt.LeftButton)
        self.spin(50)
        self.assertEqual(opened(), ["OUTPUT"])
        self.assertLessEqual(win.frameGeometry().width(), 1280)

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

    def notices(self, dialogs):
        return [d for d in dialogs if isinstance(d, UntestedBox)]

    def start_again(self, simulated=False, answer=None):
        """Commander started once more, with the same settings: the notices it showed."""
        sim = SimulatedAdi2.factory(PRO, presets=PRESETS, clock=self.clock)
        session = Session(lambda: SimPort(sim), clock=self.clock)
        win = MainWindow(session, simulated=simulated, settings=self.settings)
        win.timer.setInterval(24 * 3600 * 1000)
        shown = []
        win.ask = lambda dialog: shown.append(dialog) or (answer(dialog) if answer else True)
        win.show()
        for _ in range(60):
            self.clock.t += 0.05
            win.tick()
            QApplication.processEvents()
        self.assertTrue(session.ready())
        win.close()
        session.close()
        return self.notices(shown)

    def test_a_notice_that_it_is_not_tested(self):
        [box] = self.notices(self.dialogs)
        self.assertEqual(box.windowTitle(), "ADI-2 Commander")
        self.assertEqual(box.title, "Not tested with the ADI-2 Pro")              # over the text, larger
        self.assertIn("font-size: 12pt", box.heading.text())
        self.assertIn(box.title, box.heading.text().replace("\u00a0", " "))
        self.assertEqual(box.body.text().replace("\u00a0", " "),                   # names kept whole
                         "Commander has not been tested with an actual ADI-2 Pro.\n\n"
                         "Commander keeps a copy of the device's state as it was when connected, in the backups "
                         "folder. Restore it with ADI-2 Remote: File → Open Setup File…\n\n"
                         "To explore the app first, or to convert filter sets and curves for your ADI-2 Pro, no "
                         "device is needed: start ADI-2 Commander (simulated) from the Start menu.")
        self.assertEqual([box.go.text(), box.quit.text()], ["Continue", "Quit"])
        self.assertTrue(box.go.isDefault())
        QTest.keyClick(box, Qt.Key_Escape)                                     # Escape: Continue
        self.assertFalse(box.quitting)
        self.assertEqual(box.keep.text(), "Don't show this again")
        self.assertIsNone(box.folder)                                          # no backups folder given
        self.assertTrue(self.win.isVisible())                                  # Continue
        self.sim.power(False)
        self.spin(1000)
        self.sim.power(True)
        self.spin(3000)
        self.assertTrue(self.session.ready())
        self.assertEqual(len(self.notices(self.dialogs)), 1)                   # once per run
        self.assertEqual(len(self.start_again()), 1)                           # and at every start

    def test_dont_show_this_again_in_this_version(self):
        self.assertEqual(len(self.start_again(answer=lambda box: box.keep.setChecked(True) or True)), 1)
        self.assertEqual(self.settings.value("untested/72"), __version__)
        self.assertEqual(self.start_again(), [])
        self.settings.setValue("untested/72", "0.0.1")                         # another version: again
        self.assertEqual(len(self.start_again()), 1)

    def test_quit_closes_commander(self):
        self.win.ask = lambda box: box.quit.click() or False
        self.win.warned.clear()
        self.win.warn_untested()
        self.assertFalse(self.win.isVisible())

    def test_no_notice_in_simulated_mode(self):
        self.assertEqual(self.start_again(simulated=True), [])

    def test_the_outputs_it_controls(self):
        tabs = self.win.tabs
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],
                         ["Analog In", "Line Out", "Phones 1/2", "Phones 3/4"])
        self.assertEqual([tabs.isTabVisible(i) and tabs.isTabEnabled(i) for i in range(tabs.count())],
                         [True, True, False, True])
        self.assertEqual(tabs.currentIndex(), tab(3))
        self.win.next_tab(1)
        self.assertEqual(tabs.currentIndex(), tab(9))
        self.win.next_tab(1)
        self.assertEqual(tabs.currentIndex(), tab(0))
        self.win.next_tab(-1)
        self.assertEqual(tabs.currentIndex(), tab(9))
        self.assertEqual(self.win.presets.output_title.text(), "PHONES 3/4")

    def test_phones_1_2_with_settings_of_its_own(self):
        """Dual Phones (12/8) and Mute v. TRS 1/2 (12/11) on: Phones 1/2 has settings of its own, and Commander
        controls its EQ; Dual Phones off again: its tab grey, and the window on another output."""
        tabs = self.win.tabs
        self.assertEqual(tabs.tabToolTip(tab(6)), PHONES_1_2["off"])
        self.sim.state[(12, 8)] = 1                                   # read back by the idle refresh
        self.spin(4000)
        self.assertEqual([tabs.isTabEnabled(i) for i in OUTPUT_TABS], [True, True, True])
        self.assertEqual(tabs.tabToolTip(tab(6)), "")
        tabs.setCurrentIndex(tab(6))
        self.assertTrue(self.session.writable((7, 4)) and self.session.writable((6, 12)))       # a gain, Volume
        self.win.eq_switches[0].click()
        self.spin(1500)
        self.assertEqual(self.sim.state[(7, 2)], 1)
        self.sim.state[(12, 8)] = 0
        self.spin(4000)
        self.assertEqual((tabs.isTabEnabled(tab(6)), tabs.currentIndex() == tab(6)), (False, False))
        self.assertFalse(self.session.writable((7, 4)))

    def test_phones_1_2_with_some_settings_of_line_out(self):
        """With settings of its own, Phones 1/2 shows and writes Mute and the other settings of the D/A converter at
        Line Out's address, and says so, as Line Out does; Volume is its own. Dim where Line Out or Phones 1/2 is
        active."""
        panel, sim = self.win.output_panel, self.sim
        sim.state[(12, 8)] = 1
        self.spin(4000)
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)
        self.win.tabs.setCurrentIndex(tab(6))
        volume = sim.state[(6, P.VOLUME)], sim.state[(3, P.VOLUME)]
        QTest.mouseClick(panel.options[P.MUTE], Qt.LeftButton)
        s = panel.volume
        QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(4, s.height() // 2))
        self.spin(1500)
        self.assertEqual((sim.state[(3, P.MUTE)], (6, P.MUTE) in sim.state), (1, False))
        self.assertEqual((sim.state[(6, P.VOLUME)], sim.state[(3, P.VOLUME)]), (volume[0] - 5, volume[1]))
        shared = "One setting for Line Out and Phones 1/2"
        self.assertIn(shared, panel.options[P.MUTE].toolTip())
        self.assertIn(shared, panel.steppers[P.DA_FILTER].toolTip())
        self.assertNotIn(shared, panel.steppers[P.CROSSFEED].toolTip())
        self.assertTrue(panel.options[P.DIM].isEnabled())                      # Line Out is active
        self.session.device_status = self.session.device_status._replace(output=0)
        self.win.refresh()
        self.assertFalse(panel.options[P.DIM].isEnabled())
        self.win.tabs.setCurrentIndex(tab(3))
        self.assertIn(shared, panel.options[P.MUTE].toolTip())
        self.win.tabs.setCurrentIndex(tab(9))
        self.assertNotIn(shared, panel.options[P.MUTE].toolTip())

    def test_ref_level_of_phones_1_2_beside_line_out(self):
        """Phones 1/2 with the settings of Line Out: on their tab its Ref Level beside Line Out's, which sets it, shown
        only; with settings of its own, on its own tab."""
        panel = self.win.output_panel
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)
        self.sim.state.update({(12, 8): 1, (12, 11): 0, (3, P.AUTO_REF_LEVEL): 0, (3, P.REF_LEVEL): 1})
        self.spin(4000)
        phones = panel.phones_ref
        self.assertTrue(panel.rows[PHONES_REF].isVisible())
        self.assertEqual([panel.labels[P.REF_LEVEL].text(), panel.labels[PHONES_REF].text()],
                         ["Ref Level Ln. Out", "Ref Level Ph. 1/2"])
        self.assertEqual((phones.text(phones.value), phones.isEnabled(), phones.held), ("+16 dBu", False, True))
        self.assertEqual(phones.toolTip(), "Set by the Ref Level of Line Out: 3 dB higher, +22 dBu at most")
        self.sim.state[(12, 11)] = 1
        self.spin(4000)
        self.assertFalse(panel.rows[PHONES_REF].isVisible())
        self.assertEqual(panel.labels[P.REF_LEVEL].text(), "Ref Level")

    def test_load_bt_of_phones_1_2_is_that_of_line_out(self):
        """With settings of its own, Phones 1/2 shows and switches Load B/T of Line Out, and says so; so does Line
        Out."""
        load_bt = self.win.load_bt
        self.assertNotIn("One setting", load_bt.toolTip())                    # Phones 1/2 off
        self.sim.state.update({(12, 8): 1, (4, P.LOAD_BT): 1, (7, P.LOAD_BT): 0})
        self.spin(4000)
        self.assertIn("One setting for Line Out and Phones 1/2", load_bt.toolTip())
        self.win.tabs.setCurrentIndex(tab(6))
        self.assertTrue(load_bt.on)
        self.assertIn("One setting for Line Out and Phones 1/2", load_bt.toolTip())
        QTest.mouseClick(load_bt, Qt.LeftButton)
        self.spin(1500)
        self.assertEqual((self.sim.state[(4, P.LOAD_BT)], self.sim.state[(7, P.LOAD_BT)]), (0, 0))

    def shown_tabs(self):
        tabs = self.win.tabs
        return [tabs.tabText(i) for i in OUTPUT_TABS if tabs.isTabVisible(i)]

    def test_phones_1_2_with_the_settings_of_line_out(self):
        """Dual Phones on, Mute v. TRS 1/2 off: Phones 1/2 uses the settings of Line Out, and shares its tab, named
        after both; the window on Phones 1/2 moves there. Its own EQ is left alone. Mute v. TRS 1/2 on again: two
        tabs again."""
        tabs = self.win.tabs
        self.sim.state[(12, 8)] = 1
        self.spin(4000)
        tabs.setCurrentIndex(tab(6))
        self.sim.state[(12, 11)] = 0
        self.spin(4000)
        self.assertEqual(self.shown_tabs(), ["Line Out · Phones 1/2", "Phones 3/4"])
        self.assertEqual((tabs.currentIndex(), self.win.output[1]), (tab(3), 3))
        self.assertEqual(tabs.tabToolTip(tab(3)), PHONES_1_2["shared"] + "\nActive on the device")
        self.win.eq_switches[0].click()
        self.spin(1500)
        self.assertEqual((self.sim.state[(4, 2)], self.sim.state[(7, 2)]), (1, 0))
        self.win.next_tab(1)
        self.assertEqual(tabs.currentIndex(), tab(9))
        self.win.next_tab(1)
        self.assertEqual(tabs.currentIndex(), tab(0))                         # Analog In
        self.sim.state[(12, 11)] = 1
        self.spin(4000)
        self.assertEqual(self.shown_tabs(), ["Line Out", "Phones 1/2", "Phones 3/4"])
        self.assertEqual(tabs.tabToolTip(tab(3)), "Active on the device")

    def test_phones_1_2_in_balanced_phones_mode(self):
        """Bal Phones on: Phones 1/2 is the right channel of Phones 3/4, whose settings it uses, and shares its tab;
        also with Dual Phones off."""
        tabs = self.win.tabs
        tabs.setCurrentIndex(tab(9))
        self.sim.state[(12, 9)] = 1
        self.spin(4000)
        self.assertEqual(self.shown_tabs(), ["Line Out", "Phones 3/4 · Phones 1/2"])
        self.assertEqual((tabs.currentIndex(), self.win.output[1]), (tab(9), 9))
        self.assertEqual(tabs.tabToolTip(tab(9)), PHONES_1_2["balanced"] + "\nAlways active on the device")

    def test_the_outputs_the_device_has_active(self):
        """Line Out or Phones 1/2, which share a signal, or neither; Phones 3/4 always. A dot also on Phones 1/2,
        which Commander does not control."""
        tabs, why = self.win.tabs, PHONES_1_2["off"]

        def dots():
            return [tabs.tabIcon(i).cacheKey() == self.win.dot.cacheKey() for i in OUTPUT_TABS]
        self.spin(1100)                                                         # the first status message
        self.assertEqual(dots(), [True, False, True])                           # the simulator: Line Out
        self.assertEqual([tabs.tabToolTip(i) for i in OUTPUT_TABS],
                         ["Active on the device", why, "Always active on the device"])
        for code, expected in ((2, [False, True, True]), (3, [False, True, True]), (0, [False, False, True])):
            self.win.on_device_status(self.session.device_status._replace(output=code))
            self.assertEqual(dots(), expected)
        self.assertEqual(tabs.tabToolTip(tab(6)), why)                               # code 0: Phones 1/2 not active
        self.win.on_device_status(self.session.device_status._replace(output=2))
        self.assertEqual(tabs.tabToolTip(tab(6)), why + "\nActive on the device")
        self.win.on_device_status(None)
        self.assertEqual(dots(), [False, False, False])

    def test_the_output_panel(self):
        """Open, on the settings of the output shown, with the names of the model."""
        side, area, panel = self.win.output_tab, self.win.output_area, self.win.output_panel
        QTest.mouseClick(side, Qt.LeftButton)
        self.assertFalse(area.isHidden())
        self.assertEqual(panel.steppers[P.REF_LEVEL].text(panel.steppers[P.REF_LEVEL].value), "+19 dBu")
        self.assertEqual(panel.volume_label.text(), "Volume (dBr)")                  # Auto Ref Level on
        QTest.mouseClick(panel.options[P.MUTE], Qt.LeftButton)
        self.spin(1500)
        self.assertEqual(self.sim.state[(3, P.MUTE)], 1)
        self.win.tabs.setCurrentIndex(tab(9))
        QTest.mouseClick(panel.options[P.AUTO_REF_LEVEL], Qt.LeftButton)
        self.spin(1500)
        self.assertEqual((self.sim.state[(9, P.AUTO_REF_LEVEL)], panel.volume_label.text()), (0, "Volume (dB)"))
        self.assertTrue(panel.steppers[P.REF_LEVEL].isEnabled())
        QTest.mouseClick(self.win.input_tab, Qt.LeftButton)
        self.assertFalse(self.win.input_area.isHidden())
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.assertFalse(self.win.presets_area.isHidden())

    def test_the_status_bar_and_the_rate(self):
        self.assertEqual(self.win.lamp_text.text(), "Connected")
        self.assertTrue(self.win.input_text.isHidden())
        self.assertEqual(self.win.rate_text.text(), "48 kHz")
        self.sim.state[(12, 16)] = 6                                  # 352.8 kHz, read back by the idle refresh
        self.spin(4000)
        self.assertEqual(self.win.rate_text.text(), "352.8 kHz")
        self.win.fs_box.setCurrentIndex(P.SAMPLE_RATES.index(352800))
        self.assertEqual(self.win.graph_note.text(), "No Bass/Treble at 352.8 kHz")
        self.assertNotIn("Phones and IEM", self.win.load_bt.toolTip())

    def bypassed_by_the_input(self):
        """Line Out, read back by the idle refresh: its left EQ switch dashed, and says why; Band 1 inactive in the
        table; a band active in the graph."""
        self.spin(4000)
        left = self.win.eq_switches[0]
        model = self.win.band_models[0]
        return ("dashed" in left.styleSheet(), "the EQ of the input is on" in left.toolTip(),
                model.inactive(model.cell(model.index(0, 2))),
                any(p.flt.active for p in self.win.graph.points if p.flt.band is not None))

    def test_the_eq_of_the_input_bypasses_that_of_the_outputs_from_352_8_khz(self):
        self.sim.state.update({(4, 2): 1, (1, 2): 1})                 # EQ on: Line Out and the input
        self.assertEqual(self.bypassed_by_the_input(), (False, False, False, True))      # 48 kHz
        self.sim.state[(12, 16)] = 6                                  # 352.8 kHz
        self.assertEqual(self.bypassed_by_the_input(), (True, True, True, False))
        self.assertIn("Bypassed at 352.8 kHz while the EQ of the input is on: the ADI-2 Pro then runs that EQ only.",
                      self.win.eq_switches[0].toolTip())
        band = next(p for p in self.win.graph.points if p.flt.band is not None)
        self.assertIn("EQ of the input on at 352.8 kHz: not in the signal path", self.win.graph._describe(band))
        self.sim.state.update({(1, 2): 0, (2, 2): 1})                 # the right channel's, with Dual EQ off
        self.assertEqual(self.bypassed_by_the_input(), (False, False, False, True))
        self.sim.state[(0, 8)] = 1                                    # and on
        self.assertEqual(self.bypassed_by_the_input(), (True, True, True, False))
        self.sim.state[(4, 2)] = 0                                    # Line Out's EQ off: off, as always
        self.assertEqual(self.bypassed_by_the_input()[:3], (False, False, True))

    def test_a_preset_shows_where_it_is_selected(self):
        self.sim.front_panel([(7, 28, 3), (10, 28, 3)])               # Preset 2 on Phones 1/2 and Phones 3/4
        self.spin(1500)
        self.assertEqual(self.win.presets.rows[3].tags.text(), "P34")

    def test_export_names_the_device_and_the_output(self):
        self.win.tabs.setCurrentIndex(tab(9))
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "eq.txt")
            self.win.export_file(path)
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
        self.assertEqual([tabs.tabText(i) for i in OUTPUT_TABS], ["Line Out", "Phones 1/2", "Phones 3/4 · IEM"])
        self.assertFalse(tabs.isTabVisible(tab(0)))                            # no analog input
        self.assertTrue(all(tabs.isTabEnabled(i) for i in OUTPUT_TABS) and self.win.input_tab.isEnabled())
        self.assertEqual(self.win.input_text.isHidden(), False)


class Pro24Window(WindowTest):
    model = PRO_24

    bypassed_by_the_input = ProWindow.bypassed_by_the_input

    def test_se_in_the_title(self):
        self.spin(1000)                                               # the revision: in the status message
        self.assertEqual(self.win.windowTitle(), "ADI-2 Commander – ADI-2/4 Pro SE")

    def test_the_eq_of_the_input_bypasses_that_of_the_outputs_from_705_6_khz(self):
        self.assertEqual(self.win.tabs.tabToolTip(tab(6)), PHONES_1_2["off"])
        self.sim.state.update({(4, 2): 1, (1, 2): 1, (12, 16): 7})   # 384 kHz: no Bass/Treble, the EQ as before
        self.assertEqual(self.bypassed_by_the_input(), (False, False, False, True))
        self.sim.state[(12, 16)] = 8                                  # 705.6 kHz
        self.assertEqual(self.bypassed_by_the_input(), (True, True, True, False))
        self.assertIn("the ADI-2/4 Pro then runs that EQ only.", self.win.eq_switches[0].toolTip())

    def test_rear_trs_source_on_phones_3_4(self):
        panel = self.win.output_panel
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)
        row, trs = panel.rows[P.REAR_TRS_SOURCE], panel.steppers[P.REAR_TRS_SOURCE]
        self.assertFalse(row.isVisible())                             # Line Out
        self.win.tabs.setCurrentIndex(tab(9))
        self.assertTrue(row.isVisible())
        self.assertEqual(trs.text(trs.value), "Line 1/2")
        QTest.mouseClick(trs, Qt.LeftButton, pos=QPoint(trs.width() - 4, trs.height() // 2))
        self.spin(1500)
        self.assertEqual(self.sim.state[(9, P.REAR_TRS_SOURCE)], 1)

    def test_ref_level_of_phones_1_2_beside_line_out(self):
        """Phones 1/2 with the settings of Line Out keeps a Ref Level of its own: on their tab, beside Line Out's."""
        panel = self.win.output_panel
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)
        self.sim.state.update({(12, 8): 1, (12, 11): 0, (6, P.AUTO_REF_LEVEL): 0, (6, P.REF_LEVEL): 1})
        self.spin(4000)
        phones, line = panel.phones_ref, self.sim.state[(3, P.REF_LEVEL)]
        self.assertTrue(panel.rows[PHONES_REF].isVisible())
        self.assertEqual((phones.names, phones.text(phones.value), phones.isEnabled()),
                         (["IEM", "Lo-Power", "Hi-Power"], "Lo-Power", True))
        self.assertFalse(phones.warned)
        QTest.mouseClick(phones, Qt.LeftButton, pos=QPoint(phones.width() - 4, phones.height() // 2))
        self.spin(1500)
        self.assertEqual((self.sim.state[(6, P.REF_LEVEL)], self.sim.state[(3, P.REF_LEVEL)]), (2, line))
        self.assertTrue(phones.warned)                                # Hi-Power, Volume -10 dB, no plug in
        self.assertIn("Plugging in headphones", phones.toolTip())


class AnalogIn(WindowTest):
    """The EQ of the analog input on its own tab, first: its bands and presets; no Bass/Treble, no Loudness, no
    output settings, except Bass/Treble in a preset opened in the edit stand."""

    model = PRO_24

    def setUp(self):
        super().setUp()
        for _ in range(120):
            if len(self.session.slots) == 20:
                break
            self.spin(100)
        self.win.presets_tab.set_open(True)
        QTest.mouseClick(self.win.output_tab, Qt.LeftButton)          # on Line Out
        self.win.tabs.setCurrentIndex(tab(0))
        self.spin(50)

    def test_its_tab_has_its_eq_only(self):
        win = self.win
        self.assertEqual((win.tabs.tabText(tab(0)), win.output[1], win.presets.output_title.text()),
                         ("Analog In", 0, "ANALOG IN"))
        self.assertTrue(win.band_views[0].isVisible())
        self.assertFalse(win.bt_view.isVisible() or win.loudness_view.isVisible() or win.load_bt.isVisible())
        self.assertFalse(win.legend.items["BT"].isVisible())
        self.assertFalse(win.output_tab.isEnabled() or win.output_area.isVisible())
        self.assertEqual(win.output_tab.toolTip(), "The settings of Analog In are in the input panel")
        win.tabs.setCurrentIndex(tab(3))
        self.assertTrue(win.bt_view.isVisible() and win.output_area.isVisible() and win.load_bt.isVisible())

    def test_its_eq_and_presets_on_the_device(self):
        win = self.win
        win.eq_switches[0].click()
        win.dual_action(0)                                            # Split: Dual EQ on, at 0/8
        self.spin(1500)
        self.assertEqual((self.sim.state[(1, 2)], self.sim.state[(0, 8)], self.sim.state[(0, 11)]), (1, 1, 0))
        win.select_preset(3)                                          # Preset 2
        self.spin(1500)
        self.assertEqual(self.sim.state[(1, 28)], 3)
        self.assertTrue(win.presets.rows[3].dot.on)
        win.tabs.setCurrentIndex(tab(3))
        self.assertEqual(win.presets.rows[3].tags.text(), "In")       # selected on Analog In

    def test_select_and_store_say_what_they_do_without_its_bass_treble(self):
        hover(self.win, self.win.presets.rows[3])
        self.spin(20)
        preview = self.win.preview
        self.assertEqual(preview.select.toolTip(), "Select it on Analog In: its EQ is loaded there")
        self.assertTrue(preview.store.toolTip().startswith(
            "Store the current EQ of Analog In in Preset 2, with Bass/Treble at 0 dB\n"))
        clear = self.win.presets.rows[22]
        self.assertTrue(clear.toolTip().endswith("Store sets the Bass/Treble of the preset to 0 dB."))
        self.win.tabs.setCurrentIndex(tab(3))
        self.assertTrue(clear.toolTip().endswith("Store takes this output's Bass/Treble into the preset too."))

    def test_export_names_the_input(self):
        self.assertTrue(self.win.export_action.isEnabled())
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "eq.txt")
            self.win.export_file(path)
            with open(path, encoding="utf-8") as f:
                head = f.read(300)
        self.assertIn("# Device: RME ADI-2/4 Pro\n# Input: Analog In\n# Settings: EQ\n", head)

    def test_a_preset_opened_here_shows_its_bass_treble(self):
        self.win.edit_preset(2)
        self.spin(50)
        self.assertTrue(self.win.bt_view.isVisible())
        self.assertFalse(self.win.loudness_view.isVisible())
        self.win.leave_edit()
        self.assertFalse(self.win.bt_view.isVisible())


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


class SimulatedModel(unittest.TestCase):
    """The model Simulated mode simulates, chosen in a dialog; the choice made last chosen again."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = QSettings(os.path.join(self.folder.name, "settings.ini"), QSettings.IniFormat)
        self.shown = []

    def choose(self, answer):
        """What the dialog gives, answer(dialog) choosing in it and telling whether it was accepted."""
        return simulated.choose(self.settings, commander_app.SIMULATED_NAMES,
                                lambda dialog: self.shown.append(dialog) or answer(dialog))

    def test_the_dialog(self):
        self.assertEqual(self.choose(lambda d: True), "dac")                  # the first time: the DAC FS
        [d] = self.shown
        self.assertEqual(d.windowTitle(), "ADI-2 Commander (simulated)")
        self.assertIn("Choose the ADI-2 to simulate", d.heading.text())
        self.assertEqual([b.text() for b in d.group.buttons()],
                         ["ADI-2 DAC FS", "ADI-2 Pro", "ADI-2/4 Pro SE", "ADI-2/4 Pro EX"])
        self.assertTrue(d.start.isDefault())

    def test_the_choice_made_last(self):
        self.assertEqual(self.choose(lambda d: d.group.button(2).click() or True), "24se")
        self.assertEqual(self.settings.value(simulated.KEY), "24se")
        self.assertEqual(self.choose(lambda d: True), "24se")                 # chosen again
        self.assertTrue(self.shown[-1].group.button(2).isChecked())
        self.settings.setValue(simulated.KEY, "other")                          # not a model: the first
        self.assertEqual(self.choose(lambda d: True), "dac")

    def test_cancel(self):
        self.settings.setValue(simulated.KEY, "pro")

        def escape(d):
            d.group.button(3).click()
            QTest.keyClick(d, Qt.Key_Escape)
            return d.result() == d.DialogCode.Accepted
        self.assertIsNone(self.choose(escape))
        self.assertEqual(self.settings.value(simulated.KEY), "pro")             # not remembered


class Backup(unittest.TestCase):
    """A copy of the device's state at each connection: taken before anything can be written, saved once the preset
    slots are read."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = os.path.join(self.dir.name, "Backups")
        self.clock = Clock()
        self.sim = SimulatedAdi2.from_dump(DUMP, presets=PRESETS, clock=self.clock)
        self.settings = QSettings(os.path.join(self.dir.name, "settings.ini"), QSettings.IniFormat)

    def window(self, **kw):
        session = Session(lambda: SimPort(self.sim), clock=self.clock)
        win = MainWindow(session, settings=self.settings, **kw)
        win.timer.setInterval(24 * 3600 * 1000)
        win.ask = lambda dialog: True
        self.addCleanup(session.close)
        self.addCleanup(win.close)
        return win, session

    def run_for(self, win, seconds, until=lambda: False):
        end = self.clock.t + seconds
        while self.clock.t < end and not until():
            self.clock.t += 0.05
            win.tick()
            QApplication.processEvents()

    def copies(self):
        return sorted(os.listdir(self.folder)) if os.path.isdir(self.folder) else []

    def test_the_state_as_connected(self):
        win, session = self.window(backups=self.folder)
        self.run_for(win, 5, session.ready)
        taken = dict(session.state)
        self.assertNotIn(20, session.slots)                                 # the slots still to read
        session.set((4, 7), taken[(4, 7)] + 4)                              # written before the copy is saved
        self.run_for(win, 6)
        [name] = self.copies()
        self.assertTrue(name.startswith("ADI-2 DAC FS "))
        with open(os.path.join(self.folder, name), encoding="ascii", newline="") as f:
            self.assertEqual(f.read(), setupfile.write(taken, session.slots, session.model, session.revision()))
        self.assertEqual(self.sim.state[(4, 7)], taken[(4, 7)] + 4)

    def test_a_new_copy_only_when_the_state_differs(self):
        win, session = self.window(backups=self.folder)
        self.run_for(win, 8)
        self.sim.power(False)
        self.run_for(win, 1)
        self.sim.power(True)
        self.run_for(win, 8)
        self.assertEqual(len(self.copies()), 1)

    def test_gone_before_the_slots_are_read(self):
        win, session = self.window(backups=self.folder)
        self.run_for(win, 5, session.ready)
        self.sim.power(False)
        self.run_for(win, 4)
        self.assertEqual(self.copies(), [])

    def test_the_folder_from_the_notice(self):
        self.sim = SimulatedAdi2.factory(PRO, presets=PRESETS, clock=self.clock)
        win, session = self.window(backups=self.folder)
        shown = []
        win.ask = lambda dialog: shown.append(dialog) or True
        self.run_for(win, 5, session.ready)
        self.run_for(win, 0.5)
        [box] = [d for d in shown if isinstance(d, UntestedBox)]
        self.assertEqual(box.folder.text(), "View backups")
        with mock.patch("commander.ui.window.QDesktopServices.openUrl") as opened:
            box.folder.click()
        self.assertEqual(opened.call_args[0][0].toLocalFile(), self.folder.replace("\\", "/"))
        self.assertEqual(box.result(), 0)                                      # the notice stays

    def test_none_in_simulated_mode(self):
        win, session = self.window(backups=self.folder, simulated=True)
        self.run_for(win, 8)
        self.assertEqual(self.copies(), [])

    def test_the_folder_from_the_menu(self):
        for simulated in (False, True):
            win, session = self.window(backups=self.folder, simulated=simulated)
            menu = win.more_menu()
            self.assertTrue(menu.actions()[0].isEnabled())
            with mock.patch("commander.ui.window.QDesktopServices.openUrl") as opened:
                menu.actions()[0].trigger()
            self.assertTrue(os.path.isdir(self.folder))                       # made when missing
            self.assertEqual(opened.call_args[0][0].toLocalFile(), self.folder.replace("\\", "/"))

    def test_none_without_a_folder(self):
        win, session = self.window()
        self.run_for(win, 8)
        self.assertEqual(self.copies(), [])
        self.assertIsNone(win.backups)


if __name__ == "__main__":
    unittest.main()
