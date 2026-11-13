"""The response graph: what it draws per Dual EQ, EQ Enable, B/T Enable and sample rate; its axes; the points, their
labels and tooltips; the legend; and that dragging and wheeling a point write to the device on its grid."""

import math
import unittest

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QHelpEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolTip
from pyqtgraph.graphicsItems.ScatterPlotItem import renderSymbol

from commander.device import filters as F
from commander.device import params as P
from commander.ui import graph as G
from commander.ui import theme
from commander.ui.legend import ITEM_PAD
from tests.gui import WindowTest, app, tab


class Graph(WindowTest):
    size = (1200, 900)

    def setUp(self):
        super().setUp()
        self.graph = self.win.graph

    def point(self, name, side):
        return next(p for p in self.graph.points if p.flt.name == name and p.side == side)

    def sum_curve(self, side):
        return self.graph.sum_items[side].getData()[1]

    def test_points_and_curves_per_dual_eq(self):
        self.assertEqual(sorted((p.side if p.side is not None else 9, p.flt.name) for p in self.graph.points),
                         [(0, n) for n in "12345"] + [(1, n) for n in "12345"] + [(9, "B"), (9, "T")])
        self.assertTrue(self.graph.sum_items[1].isVisible())
        right = F.band_filters(self.session.state, 5, 4)
        np.testing.assert_allclose(self.sum_curve(1), F.total_db(right, self.graph.freqs))   # B/T off: bands only
        self.session.set_dual(3, False, keep="right")
        self.spin(100)
        self.assertEqual(len(self.graph.points), 7)
        self.assertFalse(self.graph.sum_items[1].isVisible())
        np.testing.assert_allclose(self.sum_curve(0), F.total_db(right, self.graph.freqs))   # the right set, for both
        self.assertEqual(self.graph.sum_items[0].opts["pen"].color().rgb(), theme.SHARED.rgb())
        self.assertEqual(self.win.legend.items["L"].name.text(), "EQ (shared)")
        self.assertEqual(self.win.legend.items["L"].color.rgb(), theme.SHARED.rgb())
        self.assertFalse(self.win.legend.items["R"].isVisible())
        self.settle()

    def test_sum_follows_eq_enable_and_bass_treble(self):
        self.sim.front_panel([(4, 2, 0)])                    # EQ off: only the left PEQ leaves the path
        self.spin(300)
        np.testing.assert_allclose(self.sum_curve(0), 0, atol=1e-9)
        self.assertLess(self.sum_curve(1).min(), -6)
        self.sim.front_panel([(4, 21, 12)])                  # Bass +6 dB, still off: not in the sum
        self.spin(300)
        np.testing.assert_allclose(self.sum_curve(0), 0, atol=1e-9)
        self.sim.front_panel([(4, 20, 1)])                   # B/T on: in both channels
        self.spin(300)
        bass = F.response_db(F.bt_filters(self.session.state, 4)[0], self.graph.freqs)
        np.testing.assert_allclose(self.sum_curve(0), bass + F.response_db(F.bt_filters(self.session.state, 4)[1],
                                                                           self.graph.freqs))
        self.assertGreater(self.sum_curve(1)[0], 5)

    def test_sum_follows_eq_enable_per_channel(self):
        self.sim.front_panel([(5, 2, 0)])                    # front panel L: only the right PEQ leaves the path
        self.spin(300)                                            # (B/T is off in this dump: the right sum goes flat)
        self.assertLess(self.sum_curve(0).min(), -6)
        np.testing.assert_allclose(self.sum_curve(1), 0, atol=1e-9)
        self.assertFalse(any(p.flt.active for p in self.graph.points if p.side == 1))
        self.assertIn("EQ off: not in the signal path", self.hover_text(self.point("2", 1)))

    def test_bass_treble_switch_writes_bt_enable(self):
        switch = self.win.bt_switch
        self.assertEqual(self.sim.state[(4, 20)], 0)
        self.assertEqual((switch.on, switch.text()), (False, "BASS/TREBLE"))
        QTest.mouseClick(switch, Qt.LeftButton)
        self.assertTrue(switch.on)                                       # at once, before the device has it
        self.settle()
        self.assertEqual(self.sim.state[(4, 20)], 1)
        self.assertNotIn((4, 20), self.win.marks.mismatch)
        self.win.tabs.setCurrentIndex(tab(6))                     # every output has its own
        phones = self.sim.state[(7, 20)]
        self.assertEqual(switch.on, bool(phones))
        QTest.mouseClick(switch, Qt.LeftButton)
        self.settle()
        self.assertEqual((self.sim.state[(4, 20)], self.sim.state[(7, 20)]), (1, 1 - phones))

    def test_curves_stay_fine_when_zoomed_in(self):
        view = self.graph.view
        x0, x1 = math.log10(140), math.log10(140) + 0.3          # as far in as it goes, around band 2
        view.setRange(xRange=(x0, x1), padding=0)
        self.spin(50)
        x = self.graph.sum_items[0].getData()[0]
        self.assertAlmostEqual(x[0], x0, places=6)
        self.assertAlmostEqual(x[-1], x1, places=6)
        self.assertLessEqual(view.width() / (len(x) - 1), 1 / G.POINTS_PER_PIXEL + 0.01)   # px per point
        left = F.band_filters(self.session.state, 4, 4)
        np.testing.assert_allclose(self.sum_curve(0), F.total_db(left, self.graph.freqs))
        self.assertAlmostEqual(self.sum_curve(0).min(), F.total_db(left, np.linspace(140, 160, 20001)).min(),
                               delta=0.01)                       # the bottom of the dip is in the curve
        self.graph.reset_view()
        self.spin(50)
        x = self.graph.sum_items[0].getData()[0]
        self.assertAlmostEqual((x[0], x[-1]), (G.X_LO, G.X_HI))  # never beyond 20 Hz .. 20 kHz

    def test_drag_writes_frequency_and_gain_on_the_grid(self):
        pt = self.point("2", 0)                              # left band 2: 150 Hz, -8 dB
        self.graph.drag_to(pt, math.log10(2045.3), -3.3)
        self.settle()
        self.assertEqual((self.sim.state[(4, 8)], self.sim.state[(4, 7)]), (2050, -7))   # 10 Hz grid, 0.5 dB
        self.graph.drag_to(self.point("4", 1), math.log10(50), 20)
        self.settle()
        self.assertEqual((self.sim.state[(5, 14)], self.sim.state[(5, 13)]), (200, 24))  # band 4 from 200 Hz
        self.assertEqual(self.win.marks.mismatch, {})

    def test_drag_leaves_the_gain_of_a_high_pass_alone(self):
        self.sim.front_panel([(4, 3, 2)])                    # band 1 left: High Pass
        self.spin(300)
        pt = self.point("1", 0)
        self.assertEqual(pt.y, 0.0)                          # on the 0 dB line: it has no gain
        self.graph.drag_to(pt, math.log10(30), 8)
        self.settle()
        self.assertEqual((self.sim.state[(4, 5)], self.sim.state[(4, 4)]), (30, -6))
        self.graph.step_q(self.point("1", 0), +1, "large")   # Q moves the curve at f0, not the point
        self.settle()
        self.assertEqual(self.sim.state[(4, 6)], 17)
        self.assertEqual(self.point("1", 0).y, 0.0)

    def hover_text(self, pt):
        """Rest the mouse on a point: the tooltip Qt then shows."""
        view, vp = self.graph.view, self.graph.viewport()
        p = self.graph.mapFromScene(view.mapToScene(view.mapFromView(QPointF(pt.x, pt.y))))
        self.graph.hover(pt)
        app.sendEvent(vp, QHelpEvent(QEvent.ToolTip, p, vp.mapToGlobal(p)))
        return QToolTip.text() if QToolTip.isVisible() else ""

    def test_tooltips_of_the_points(self):
        self.assertEqual(self.hover_text(self.point("2", 0)).split("\n"),
                         ["Band 2 · LEFT", "Peak  150 Hz  -8.0 dB  Q 4.0", "20 … 20000 Hz · ±12 dB · Q 0.5 … 9.9",
                          "Wheel: Q"])
        self.assertEqual(self.hover_text(self.point("4", 1)).split("\n")[:3],
                         ["Band 4 · RIGHT", "Peak  200 Hz  -2.0 dB  Q 5.0", "200 … 20000 Hz · ±12 dB · Q 0.5 … 5.0"])
        self.assertEqual(self.hover_text(self.point("T", None)).split("\n"),
                         ["Treble · shared L/R", "High Shelf  6500 Hz  +0.0 dB  Q 0.7",
                          "3000 … 10000 Hz · ±12 dB · Q 0.5 … 1.5", "Bass/Treble off: not in the signal path",
                          "Wheel: Q"])
        self.sim.front_panel([(4, 16, 2), (4, 2, 0)])        # band 5 left: High Cut; and EQ off
        self.spin(300)
        self.assertEqual(self.hover_text(self.point("5", 0)).split("\n"),
                         ["Band 5 · LEFT", "High Cut  3000 Hz  Q 5.0", "200 … 20000 Hz · Q 0.5 … 5.0",
                          "No gain; Q sets the resonance", "EQ off: not in the signal path", "Wheel: Q"])
        self.graph.step_q(self.point("5", 0), -1, "small")   # an open tooltip shows the new value
        self.spin(100)
        self.assertIn("Q 4.9", QToolTip.text())
        self.session.set_dual(3, False)
        self.spin(100)
        self.assertTrue(self.hover_text(self.point("1", 0)).startswith("Band 1 · shared L/R"))
        self.graph.hover(None)
        self.assertEqual(self.graph.view.toolTip(), "")
        self.settle()

    def test_wheel_on_a_point_steps_q(self):
        self.graph.step_q(self.point("1", 1), +1, "small")   # right band 1: Q 6.0
        self.graph.step_q(self.point("T", None), -1, "large")
        self.settle()
        self.assertEqual((self.sim.state[(5, 6)], self.sim.state[(4, 26)]), (61, 5))   # Treble Q 0.7 -> 0.5

    def test_coinciding_points_go_to_the_channel_last_worked_on(self):
        view = self.graph.view
        left3 = self.point("3", 0)                           # band 3 is the same left and right
        pos = view.mapFromView(QPointF(left3.x, left3.y))
        self.assertEqual(self.graph.point_at(view, pos).side, 0)
        right = self.win.band_views[1]
        right.setCurrentIndex(right.model().index(0, 1))
        self.assertEqual(self.graph.point_at(view, pos).side, 1)
        self.graph.pick(self.graph.point_at(view, pos))      # and taking it selects its row in the table
        self.assertTrue(right.hasFocus())
        self.assertEqual((right.currentIndex().row(), right.currentIndex().column()), (2, 1))

    def test_with_dual_eq_off_a_point_belongs_to_both_tables(self):
        self.session.set_dual(3, False)
        self.spin(100)
        filled = lambda: sorted(k for k, i in self.graph.band_items.items()               # noqa: E731
                                if i.isVisible() and i.opts["fillLevel"] is not None)
        left, right = self.win.band_views
        right.setFocus()
        right.setCurrentIndex(right.model().index(1, 1))            # band 2 in the right table: its curve
        self.spin(50)
        self.assertEqual(filled(), [(0, "2")])
        self.graph.pick(self.point("4", 0))                  # taken in the graph: in the table last worked on
        self.assertEqual((right.hasFocus(), right.currentIndex().row()), (True, 3))
        left.setFocus()
        left.setCurrentIndex(left.model().index(0, 1))
        self.graph.pick(self.point("4", 0))
        self.assertEqual((left.hasFocus(), left.currentIndex().row()), (True, 3))
        self.settle()

    def click(self, pt):
        """A real left click on a point."""
        view, vp = self.graph.view, self.graph.viewport()
        p = self.graph.mapFromScene(view.mapToScene(view.mapFromView(QPointF(pt.x, pt.y))))
        for kind, buttons in ((QMouseEvent.Type.MouseButtonPress, Qt.LeftButton),
                              (QMouseEvent.Type.MouseButtonRelease, Qt.NoButton)):
            app.sendEvent(vp, QMouseEvent(kind, QPointF(p), QPointF(vp.mapToGlobal(p)), Qt.LeftButton, buttons,
                                          Qt.KeyboardModifier.NoModifier))
        self.spin(50)

    def test_a_click_on_a_point_chooses_its_band(self):
        filled = lambda: sorted(k for k, i in self.graph.band_items.items()               # noqa: E731
                                if i.isVisible() and i.opts["fillLevel"] is not None)
        self.click(self.point("1", 1))                      # right band 1, 40 Hz: no left point on it
        self.assertEqual(filled(), [(1, "1")])
        right = self.win.band_views[1]
        self.assertEqual((right.hasFocus(), right.currentIndex().row()), (True, 0))
        self.click(self.point("T", None))
        self.assertEqual(filled(), [(None, "T")])

    def test_a_label_is_a_handle_on_its_point(self):
        g, vp = self.graph, self.graph.viewport()
        i = next(i for i, p in enumerate(g.points) if p.flt.name == "1" and p.side == 1)   # right band 1, 40 Hz
        pt, label = g.points[i], g.labels[i]
        at = g.mapFromScene(label.sceneBoundingRect().center())
        self.assertIs(g.point_at(g.view, g.view.mapFromScene(label.sceneBoundingRect().center())), pt)
        self.assertFalse(label.textItem.font().bold())

        def send(kind, p, buttons):
            app.sendEvent(vp, QMouseEvent(kind, QPointF(p), QPointF(vp.mapToGlobal(p)), Qt.LeftButton, buttons,
                                          Qt.KeyboardModifier.NoModifier))
        send(QMouseEvent.Type.MouseButtonPress, at, Qt.LeftButton)              # click: chosen
        send(QMouseEvent.Type.MouseButtonRelease, at, Qt.NoButton)
        self.spin(50)
        self.assertEqual(g.current, pt.key)
        label = g.labels[next(i for i, p in enumerate(g.points) if p.key == pt.key)]
        self.assertTrue(label.textItem.font().bold())
        self.assertEqual(label.color.name(), G.CHANNEL[1].name())                # its own colour, not white
        f0, q0 = self.sim.state[(5, 5)], self.sim.state[(5, 6)]
        move = QPointF(60, -80)                                                 # diagonal: frequency only
        send(QMouseEvent.Type.MouseButtonPress, at, Qt.LeftButton)
        for k in range(1, 11):
            send(QMouseEvent.Type.MouseMove, at + (move * (k / 10)).toPoint(), Qt.LeftButton)
            self.assertEqual(g.view.cursor().shape(), Qt.SizeHorCursor)         # up into the graph as well
        send(QMouseEvent.Type.MouseButtonRelease, at + move.toPoint(), Qt.NoButton)
        self.settle()
        self.assertGreater(self.sim.state[(5, 5)], f0)
        self.assertEqual(self.sim.state[(5, 4)], -12)                          # its gain stays
        label = g.labels[next(i for i, p in enumerate(g.points) if p.key == pt.key)]
        on_label = g.view.mapFromScene(label.sceneBoundingRect().center())
        g.hover(g.point_at(g.view, on_label), by_label=True)
        self.assertTrue(g.view.toolTip().endswith("Drag: frequency · Wheel: Q"))
        g.view.wheelEvent(type("Wheel", (), {"pos": lambda s: on_label, "accept": lambda s: None,     # wheel: Q
                                             "modifiers": lambda s: Qt.KeyboardModifier.NoModifier,
                                             "delta": lambda s: 120})())
        self.settle()
        self.assertEqual(self.sim.state[(5, 6)], q0 + 1)

    def test_open_rings_and_labels_in_the_lane(self):
        self.assertTrue(all(s["brush"].color().alpha() == 0 for s in self.graph.scatter.data))
        view = self.graph.view

        def lane():
            (_, _), (y0, y1) = view.viewRange()
            return [(t.pos().x(), (t.pos().y() - y0) / (y1 - y0) * view.height())
                    for t in self.graph.labels if t.isVisible()]
        before = lane()
        self.assertEqual(len(before), 12)
        self.assertTrue(all(abs(px - G.LANE_PX) < 0.01 for _, px in before))      # just above the bottom
        self.assertEqual([x for x, _ in before], [p.x for p in self.graph.points])  # at f0
        view.setRange(yRange=(-13, 1), padding=0)
        self.spin(50)
        self.assertTrue(all(abs(px - G.LANE_PX) < 0.01 for _, px in lane()))

    def test_a_chosen_shelf_off_its_curve_has_a_dot_in_its_ring(self):
        self.sim.front_panel([(4, 21, 12)])                  # Bass +6 dB: at f0 its curve is halfway
        self.spin(300)
        g = self.graph
        g.current = (4, "B")
        g.update_from(self.win.output)
        dots = g.dots.points()
        ring = next(s for s, p in zip(g.scatter.points(), g.points) if p.key == (4, "B"))
        self.assertEqual(len(dots), 1)
        self.assertEqual(dots[0].pos(), ring.pos())

        def side(spot):
            return renderSymbol(spot.symbol(), spot.size(), spot.pen(), spot.brush()).width()
        self.assertEqual((side(ring) % 2, side(dots[0]) % 2), (1, 1))         # odd: both centred on a pixel

    def test_fill_follows_the_last_choice(self):
        left, bt = self.win.band_views[0], self.win.bt_view
        filled = lambda: sorted(k for k, i in self.graph.band_items.items()               # noqa: E731
                                if i.isVisible() and i.opts["fillLevel"] is not None)
        self.graph.pick(self.point("2", 0))
        self.assertEqual(filled(), [(0, "2")])
        self.graph.pick(self.point("B", None))
        self.assertEqual(filled(), [(None, "B")])
        self.graph.pick(self.point("2", 0))                  # the left table's current cell did not change
        self.assertEqual(filled(), [(0, "2")])
        bt.setFocus()                                        # into a table by keyboard or mouse
        self.spin(50)
        self.assertEqual(filled(), [(None, "B")])
        left.setFocus()
        self.spin(50)
        self.assertEqual(filled(), [(0, "2")])

    # -- what is shown: the legend --------------------------------------------------------------
    def shown(self):
        """(sums visible per side, band curves visible, sides and names of the points)"""
        g = self.graph
        return ([i.isVisible() for i in g.sum_items], sorted(k for k, i in g.band_items.items() if i.isVisible()
                                                             for k in [(9 if k[0] is None else k[0], k[1])]),
                sorted((9 if p.side is None else p.side, p.flt.name) for p in g.points))

    def test_legend_click_shows_and_hides(self):
        item = self.win.legend.items["L"]
        size = item.sizeHint()
        sums_before = self.sum_curve(0).copy()
        QTest.mouseClick(item, Qt.LeftButton)
        sums, bands, points = self.shown()
        self.assertEqual(sums, [False, True])
        self.assertFalse(any(side == 0 for side, _ in bands + points))
        self.assertEqual((item.color.rgb(), item.sizeHint()), (theme.OFF.rgb(), size))   # hidden: grey, as wide
        QTest.mouseClick(item, Qt.LeftButton)
        self.assertEqual(self.shown()[0], [True, True])
        QTest.mouseClick(self.win.legend.items["bands"], Qt.LeftButton)
        sums, bands, points = self.shown()
        self.assertEqual((sums, bands, len(points)), ([True, True], [], 12))      # the points stay
        np.testing.assert_allclose(self.sum_curve(0), sums_before)               # the sum is what the device runs

    def test_legend_double_click_shows_only_that_item_of_its_group(self):
        legend = self.win.legend
        QTest.mouseDClick(legend.items["R"], Qt.LeftButton)
        v = self.graph.visible
        self.assertEqual((v["L"], v["R"], v["BT"], v["sum"], v["bands"]), (False, True, False, True, True))
        self.assertEqual({side for side, _ in self.shown()[2]}, {1})
        QTest.mouseDClick(legend.items["R"], Qt.LeftButton)                      # again: the whole group
        self.assertEqual((v["L"], v["R"], v["BT"]), (True, True, True))
        QTest.mouseDClick(legend.items["sum"], Qt.LeftButton)
        self.assertEqual((v["sum"], v["bands"]), (True, False))
        self.assertEqual((v["L"], v["R"], v["BT"]), (True, True, True))          # the other group stays

    def test_legend_handles_off_keeps_the_labels_but_not_the_mouse(self):
        g = self.graph
        pt = self.point("2", 0)
        label = g.labels[g.points.index(pt)]
        on_point = g.view.mapFromView(QPointF(pt.x, pt.y))
        on_label = g.view.mapRectFromScene(label.sceneBoundingRect()).center()
        self.assertIs(g.point_at(g.view, on_point), pt)
        QTest.mouseClick(self.win.legend.items["handles"], Qt.LeftButton)
        sums, bands, _ = self.shown()
        self.assertTrue(all(sums) and bands)                                     # the curves stay
        self.assertEqual(len(g.scatter.points()), 0)                             # no rings
        self.assertEqual(sum(t.isVisible() for t in g.labels), 12)               # the labels stay, to inform
        self.assertIsNone(g.point_at(g.view, on_point))                          # ... but take no mouse
        self.assertIsNone(g.point_at(g.view, on_label))
        QTest.mouseClick(self.win.legend.items["handles"], Qt.LeftButton)
        self.assertEqual(len(g.scatter.points()), 12)
        self.assertEqual(g.point_at(g.view, on_label).key, pt.key)        # a new Point per redraw
        QTest.mouseDClick(self.win.legend.items["handles"], Qt.LeftButton)      # only the handles
        v = self.graph.visible
        self.assertEqual((v["sum"], v["bands"], v["handles"]), (False, False, True))

    def test_legend_tooltips(self):
        items = self.win.legend.items
        self.assertEqual(items["L"].toolTip(),
                         "Click: show or hide · Double-click: only this channel; again: all channels")
        self.assertEqual(items["bands"].toolTip().split("\n"),
                         ["Includes Bass and Treble",
                          "Click: show or hide · Double-click: only this layer; again: all layers"])

    def test_the_head_gives_way_in_three_steps(self):
        head, legend, controls = self.win.graph_head, self.win.legend, self.win.graph_head.controls
        c = controls.sizeHint().width()
        line = legend.size_for(False).width() + head.GAP + c
        rows = legend.size_for(True).width() + head.GAP + c
        y = lambda wd: wd.geometry().y()                                         # noqa: E731
        for width, how in ((line, "line"), (rows, "rows"), (rows - 1, "above")):
            head.resize(width, head.heightForWidth(width))
            self.assertEqual(head._fit(width, legend)[0], how)
            flat_fits = legend.size_for(False).width() <= width                  # over the rates: one line if it fits
            self.assertEqual(legend.stacked, how == "rows" or how == "above" and not flat_fits)
            right = controls.geometry().right() == width - 1
            if how == "above":
                self.assertTrue(right and y(controls) == 0 and y(legend) > y(controls))   # the rates on top
                self.assertEqual(legend.geometry().right() - ITEM_PAD, width - 1)       # the names end where kHz ends
            else:
                self.assertTrue(right and y(controls) < y(legend) + legend.first_row_height())   # beside the first

    def test_a_longer_name_in_the_legend_fits_at_once(self):
        item = self.win.legend.items["L"]
        self.win.resize(1600, 900)                                              # room for the whole legend
        self.spin(50)
        QTest.mouseClick(self.win.dual_actions[0], Qt.LeftButton)               # EQ Left -> EQ (shared)
        self.assertEqual(item.name.text(), "EQ (shared)")
        self.assertEqual(item.width(), item.sizeHint().width())                 # not cut off until a next refresh
        self.settle()

    def test_legend_with_dual_eq_off(self):
        self.session.set_dual(3, False)
        self.spin(100)
        QTest.mouseDClick(self.win.legend.items["L"], Qt.LeftButton)            # RIGHT is not there to count
        v = self.graph.visible
        self.assertEqual((v["L"], v["BT"]), (True, False))
        QTest.mouseDClick(self.win.legend.items["L"], Qt.LeftButton)
        self.assertEqual((v["L"], v["BT"]), (True, True))
        self.settle()

    def test_pointing_at_a_legend_item_sets_the_rest_back(self):
        alphas = lambda items: [round(i.opts["pen"].color().alphaF(), 2) for i in items]   # noqa: E731
        sums, widths = self.graph.sum_items, [i.opts["pen"].widthF() for i in self.graph.sum_items]
        self.win.legend.point("R", True)
        self.assertEqual(alphas(sums), [G.DIMMED, 1.0])                       # the rest steps back ...
        self.assertEqual([i.opts["pen"].widthF() for i in sums], widths)      # ... nothing grows
        self.win.legend.point("R", False)
        self.assertEqual(alphas(sums), [1.0, 1.0])
        rings = lambda: [round(s.pen().color().alphaF(), 2) for s in self.graph.scatter.points()]   # noqa: E731
        self.win.legend.point("sum", True)
        self.assertTrue(all(a == G.DIMMED for a in rings()))
        self.win.legend.point("sum", False)
        self.win.legend.point("handles", True)
        self.assertTrue(all(a == 1 for a in rings()))
        self.assertEqual(alphas(sums), [G.DIMMED, G.DIMMED])
        self.win.legend.point("handles", False)

    def test_chosen_and_attention_are_two_marks(self):
        g, vp = self.graph, self.graph.viewport()
        pt, other = self.point("2", 0), self.point("3", 0)
        at = g.mapFromScene(g.view.mapToScene(g.view.mapFromView(QPointF(pt.x, pt.y))))

        def alpha(key):
            pen = (g.sum_items[key] if isinstance(key, int) else g.band_items[key]).opts["pen"]
            stops = pen.brush().gradient().stops() if pen.brush().gradient() else [(0, pen.color())]
            return round(max(c.alphaF() for _, c in stops), 2)

        def fill(key):
            opts = g.band_items[key].opts
            return None if opts["fillLevel"] is None else round(opts["fillBrush"].color().alphaF(), 3)

        def send(kind, p, buttons):
            app.sendEvent(vp, QMouseEvent(kind, QPointF(p), QPointF(vp.mapToGlobal(p)), Qt.LeftButton, buttons,
                                          Qt.KeyboardModifier.NoModifier))
        g.hover(other)                                                          # pointing at band 3: attention
        self.assertEqual((alpha(0), alpha(1), alpha((0, "3"))), (G.DIMMED, G.DIMMED, 1.0))
        self.assertEqual((fill((0, "3")), g.current == other.key), (None, False))   # ... it does not colour
        g.hover(None)
        self.assertEqual((alpha(0), alpha(1)), (1.0, 1.0))
        send(QMouseEvent.Type.MouseButtonPress, at, Qt.LeftButton)
        self.assertEqual((g.current, g.held), (pt.key, pt.key))                 # pressing: chosen and held at once
        self.assertEqual(fill((0, "2")), 0.14)
        send(QMouseEvent.Type.MouseMove, at + QPoint(4, 4), Qt.LeftButton)
        self.assertEqual((alpha(0), alpha((1, "2"))), (G.DIMMED, G.DIMMED))     # the own sum too
        send(QMouseEvent.Type.MouseButtonRelease, at + QPoint(4, 4), Qt.NoButton)
        g.hover(None)                                                           # the mouse off: all comes back
        self.assertIsNone(g.held)
        self.assertEqual((alpha(0), alpha((0, "2")), fill((0, "2"))), (1.0, 1.0, 0.14))   # chosen stays
        g.hover(other)                                                          # another band: the chosen steps back
        self.assertEqual((alpha((0, "2")), fill((0, "2"))), (G.DIMMED, round(0.14 * G.DIMMED, 3)))
        wheel = type("Wheel", (), {"pos": lambda s: g.view.mapFromView(QPointF(other.x, other.y)),
                                   "accept": lambda s: None, "modifiers": lambda s: Qt.NoModifier,
                                   "delta": lambda s: 120})()
        g.view.wheelEvent(wheel)                                                # who edits, has chosen
        self.assertEqual(g.current, other.key)
        g.hover(None)
        self.settle()

    def test_a_band_out_of_the_path_is_grey(self):
        self.sim.front_panel([(4, P.EQ_ENABLE, 0)])                              # EQ Left off
        self.spin(300)
        band = self.graph.band_items[(0, "2")]
        peak = int(np.argmax(np.abs(band.getData()[1])))
        self.assertEqual(band.opts["pen"].brush().gradient().stops()[0][1].rgb(), theme.OFF.rgb())
        self.assertEqual(self.graph.sum_items[0].opts["pen"].color().rgb(), theme.LEFT.rgb())   # what the device does
        ring = next(s for s, p in zip(self.graph.scatter.points(), self.graph.points) if p.key == (4, "2"))
        self.assertEqual(ring.pen().color().rgb(), theme.OFF.rgb())
        self.assertGreater(abs(band.getData()[1][peak]), G.BAND_FULL)

    def test_a_band_fades_in_where_it_does_something(self):
        band = self.graph.band_items[(0, "2")]                                  # a Peak at 150 Hz
        x, y = band.getData()
        stops = band.opts["pen"].brush().gradient().stops()
        alpha_at = lambda f: min(stops, key=lambda s: abs(s[0] - (math.log10(f) - x[0]) / (x[-1] - x[0])))[1].alphaF()   # noqa: E731
        self.assertEqual(alpha_at(15000), 0.0)                                  # far away: nothing to see
        self.assertAlmostEqual(alpha_at(150), G.BAND_ALPHA, places=2)           # at the band: as a band
        self.assertEqual(band.opts["pen"].widthF(), G.BAND_W)
        self.assertEqual(self.graph.sum_items[0].opts["pen"].widthF(), G.SUM_W)

    # -- the axes --------------------------------------------------------------------------------
    def test_values_and_band_labels_in_the_app_font(self):
        left = self.graph.getPlotItem().getAxis("left")
        self.assertEqual(left.style["tickFont"].family(), app.font().family())   # labels, not values one sets
        self.assertEqual(self.graph.labels[0].textItem.font().family(), app.font().family())

    def test_the_axes_are_titled_and_the_plot_area_closed(self):
        pi = self.graph.getPlotItem()
        self.assertEqual([pi.getAxis(n).labelText for n in ("bottom", "left")], ["Frequency (Hz)", "Gain (dB)"])
        right = pi.getAxis("right")
        self.assertTrue(right.isVisible())                                      # a line on the right, as the left
        self.assertEqual((right.style["showValues"], right.grid), (False, False))   # no values, no grid of its own

    def test_on_an_axis_the_wheel_zooms_that_axis_only(self):
        pi, view, vp = self.graph.getPlotItem(), self.graph.view, self.graph.viewport()
        for name, zoomed in (("bottom", 0), ("left", 1)):
            self.graph.reset_view()
            before = view.viewRange()
            axis = pi.getAxis(name)
            p = self.graph.mapFromScene(axis.mapToScene(axis.shape()).boundingRect().center())   # without the grid
            app.sendEvent(vp, QHelpEvent(QEvent.ToolTip, p, vp.mapToGlobal(p)))
            self.assertEqual(QToolTip.text() if QToolTip.isVisible() else "", G.AXIS_TIPS[name])
            app.sendEvent(vp, QWheelEvent(QPointF(p), QPointF(vp.mapToGlobal(p)), QPoint(0, 0), QPoint(0, 120),
                                          Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
            after = view.viewRange()
            self.assertLess(after[zoomed][1] - after[zoomed][0], before[zoomed][1] - before[zoomed][0])
            self.assertEqual(after[1 - zoomed], before[1 - zoomed])
        QToolTip.hideText()
        inside = self.graph.mapFromScene(view.sceneBoundingRect().center())
        app.sendEvent(vp, QHelpEvent(QEvent.ToolTip, inside, vp.mapToGlobal(inside)))
        self.assertFalse(QToolTip.isVisible() and QToolTip.text() in G.AXIS_TIPS.values())  # the grid takes none
        self.graph.reset_view()

    def test_a_faint_line_per_db(self):
        left = self.graph.getPlotItem().getAxis("left")
        self.assertEqual(left.tickSpacing(G.Y_LO, G.Y_HI, 600), [(6, 0), (3, 0), (1, 0)])
        self.assertEqual(left.style["maxTextLevel"], 1)                         # without a value

    # -- the sample rate -------------------------------------------------------------------------
    def test_curves_at_the_chosen_sample_rate_compared_with_the_device_rate(self):
        self.sim.front_panel([(4, 18, 12000)])               # band 5 left in the high, where fs matters
        self.spin(300)
        left = F.band_filters(self.session.state, 4, 4)
        cmp, item = self.graph.compare_items[0], self.win.legend.items["compare"]     # the dashed sums, their item
        self.assertFalse(cmp.isVisible() or item.isVisible())                 # the device runs at the chosen 48
        self.win.fs_box.setCurrentIndex(G.SAMPLE_RATES.index(44100))
        np.testing.assert_allclose(self.sum_curve(0), F.total_db(left, self.graph.freqs, 44100))
        self.assertEqual((item.isVisible(), item.name.text()), (True, "<i>f</i><sub>s</sub> 48 kHz"))
        self.assertFalse(cmp.isVisible())                                     # off at first
        QTest.mouseClick(item, Qt.LeftButton)
        self.assertTrue(cmp.isVisible())
        self.assertEqual(cmp.opts["pen"].style(), Qt.DashLine)
        np.testing.assert_allclose(cmp.getData()[1], F.total_db(left, self.graph.freqs, 48000))
        self.assertGreater(np.abs(cmp.getData()[1] - self.sum_curve(0)).max(), 0.01)
        QTest.mouseClick(self.win.legend.items["sum"], Qt.LeftButton)        # a layer of its own
        self.assertTrue(cmp.isVisible())
        self.sim.signal(usb=96000)                                            # the device follows: so does the curve
        self.spin(1100)
        np.testing.assert_allclose(cmp.getData()[1], F.total_db(left, self.graph.freqs, 96000))
        self.assertEqual(item.name.text(), "<i>f</i><sub>s</sub> 96 kHz")
        self.win.fs_box.setCurrentIndex(G.SAMPLE_RATES.index(96000))          # the chosen rate: nothing to compare
        self.assertFalse(cmp.isVisible() or item.isVisible())
        self.win.fs_box.setCurrentIndex(G.SAMPLE_RATES.index(44100))
        self.assertTrue(cmp.isVisible())                                      # still on in the legend
        self.sim.signal(usb=176400, dsd=True)                                 # DSD: no DSP, no rate
        self.spin(1100)
        self.assertFalse(cmp.isVisible() or item.isVisible())

    def test_no_bass_treble_from_705_6_khz(self):
        self.sim.front_panel([(4, 20, 1), (4, 21, -12)])                         # B/T on, Bass -6 dB
        self.spin(300)
        s = self.session.state
        left, bt = F.band_filters(s, 4, 4), F.bt_filters(s, 4)
        np.testing.assert_allclose(self.sum_curve(0), F.total_db(left + bt, self.graph.freqs))
        self.win.fs_box.setCurrentIndex(G.SAMPLE_RATES.index(705600))
        np.testing.assert_allclose(self.sum_curve(0), F.total_db(left, self.graph.freqs, 705600))
        self.assertEqual(self.win.graph_note.text(), "No Bass/Treble at 705.6 kHz")
        self.assertIn("Not available at 705.6 kHz", self.hover_text(self.point("B", None)))

    def test_a_real_mouse_drag(self):
        pt = self.point("5", 0)                              # left band 5: 3000 Hz, -1.5 dB
        view, vp = self.graph.view, self.graph.viewport()

        def at(x, y):
            return self.graph.mapFromScene(view.mapToScene(view.mapFromView(QPointF(x, y))))

        start, end = at(pt.x, pt.y), at(math.log10(8000), -6)       # negative gain all the way
        mods = Qt.KeyboardModifier.NoModifier

        def send(kind, p, buttons):
            ev = QMouseEvent(kind, QPointF(p), QPointF(vp.mapToGlobal(p)), Qt.LeftButton, buttons, mods)
            app.sendEvent(vp, ev)

        send(QMouseEvent.Type.MouseButtonPress, start, Qt.LeftButton)
        for k in range(1, 11):
            send(QMouseEvent.Type.MouseMove, start + (end - start) * (k / 10), Qt.LeftButton)
        send(QMouseEvent.Type.MouseButtonRelease, end, Qt.NoButton)
        self.settle()
        self.assertAlmostEqual(math.log10(self.sim.state[(4, 18)]), math.log10(8000), delta=0.02)
        self.assertAlmostEqual(self.sim.state[(4, 17)] / 2, -6, delta=0.6)
        self.assertEqual(self.sim.state[(5, 18)], 2800)      # the right channel stays


if __name__ == "__main__":
    unittest.main()
