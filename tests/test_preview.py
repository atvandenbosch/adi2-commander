"""A row's actions and a preset's preview against the simulator: under the mouse a row shows Select over its dot and
number, a slot's row Edit and Store at its end too; a click on the row itself selects nothing. A slot's row, Clear or
Rumble also shows its preview over the graph, level with the row; Manual and Temp have none. Both follow the mouse; the
graph; Select, and what it says it does; an unused slot, Clear, Rumble, a slot not read yet; and when there are none.
Select, Store and Edit as actions on the device: test_preset_panel."""

import unittest

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from commander.device import params as P
from commander.device.models import PRO_24
from commander.ui import theme
from commander.ui.graph import side_color
from commander.ui.presets import (ACTION_EDGE, CLEAR, DOUBLE_CLICK_TIP, EDIT_FREE_TIP, EDIT_TIP, MANUAL,
                                  NOT_READ, RUMBLE, TAGS_CLEAR, TAGS_GAP, TEMP)
from commander.ui.preview import PAD
from commander.ui.window import PREVIEW_INSET
from tests.gui import WindowTest, hover, tooltip_color


class Preview(WindowTest):
    def setUp(self):
        super().setUp()
        for _ in range(120):
            if len(self.session.slots) == 20:
                break
            self.spin(100)
        self.win.presets_tab.set_open(True)
        self.spin(50)

    def row(self, value):
        return self.win.presets.rows[value]

    def open(self, value):
        """This row under the mouse, in sight: its actions, and its preview if it has one."""
        self.win.presets_area.ensureWidgetVisible(self.row(value))
        self.spin(20)
        hover(self.win, self.row(value))
        self.spin(20)
        return self.win.preview

    def point(self, widget, x, y):
        """The mouse at x, y in widget; it stays there."""
        self.win.pointer = lambda: widget.mapToGlobal(QPoint(x, y))
        self.spin(20)

    def at(self, widget, x, y):
        return widget.mapTo(self.win.centralWidget(), QPoint(x, y))

    def amber(self, button):
        return theme.WARN.name() in button.styleSheet()

    def shown(self, row):
        return [w.text() for w in (row.select, row.edit, row.store) if w.isVisible()]

    def test_a_slot_shows_its_actions_and_itself_under_the_mouse_and_a_click_on_it_selects_nothing(self):
        row, preview = self.row(3), self.open(3)                              # Preset 2
        self.assertTrue(preview.isVisible())
        self.assertEqual(self.shown(row), ["Select", "Edit", "Store"])
        self.assertIn("transparent", row.styleSheet())                        # the row keeps its ground
        self.assertTrue(self.win.tabs.isEnabled())                            # nothing out of reach
        self.assertEqual(row.cursor().shape(), Qt.ArrowCursor)
        QTest.mouseClick(row, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], 0)                          # Manual still

    def test_manual_and_temp_have_select_only_and_no_preview(self):
        row = self.row(TEMP)
        self.open(TEMP)
        self.assertIs(self.win.hovered_row, row)
        self.assertFalse(self.win.preview.isVisible())
        self.assertEqual(self.shown(row), ["Select"])
        self.assertEqual(row.cursor().shape(), Qt.ArrowCursor)
        self.assertEqual(row.select.toolTip(), "Select Temp on Line Out.")
        QTest.mouseClick(row, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], MANUAL)                     # the row itself: nothing
        QTest.mouseClick(row.select, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], TEMP)
        self.open(MANUAL)
        self.assertEqual(self.shown(self.row(MANUAL)), ["Select"])
        QTest.mouseClick(self.row(MANUAL).select, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], MANUAL)

    def test_select_over_the_dot_and_number_edit_and_store_at_the_end(self):
        row = self.row(4)
        self.open(4)
        select = row.select.geometry()
        self.assertEqual(select.left(), ACTION_EDGE)
        self.assertEqual(select.top(), (row.height() - select.height()) // 2)
        for w in (row.dot, row.number):
            self.assertTrue(select.contains(QRect(w.mapTo(row, QPoint(0, 0)), w.size()).center()))
        self.assertLess(select.right(), row.name.mapTo(row, QPoint(0, 0)).x())   # the name stays clear
        self.assertLess(row.edit.x(), row.store.x())
        self.assertEqual(row.store.geometry().right(), row.width() - 1 - ACTION_EDGE)

    def test_over_the_graph_level_with_the_row(self):
        row, preview = self.row(4), self.open(4)                              # Preset 3
        zone = self.at(self.win.display, 0, 0)
        self.assertEqual(self.at(preview, 0, 0).x(), zone.x() + PREVIEW_INSET)
        self.assertGreater(self.at(preview, 0, 0).x(),
                           self.at(self.win.presets_area, self.win.presets_area.width(), 0).x())   # off the panel
        self.assertEqual(self.at(preview, 0, preview.height()).y(), self.at(row, 0, row.height()).y())
        self.assertEqual((preview.graph.x(), preview.graph.y()), (PAD, PAD))

    def test_level_with_the_row_in_a_low_window_too(self):
        self.win.resize(1200, 460)
        area = self.win.presets_area
        edges = set()
        for scroll in (0, area.verticalScrollBar().maximum()):                # the first rows, then the last
            area.verticalScrollBar().setValue(scroll)
            self.spin(50)
            shown = [r for r in self.win.presets.rows.values() if r.previewable
                     and r.visibleRegion().boundingRect().height() == r.height()]
            self.assertTrue(shown)
            for row in shown:
                preview = self.open(row.value)
                top, bottom = self.at(row, 0, 0).y(), self.at(row, 0, row.height()).y()
                edge = ("lower" if self.at(preview, 0, preview.height()).y() == bottom else
                        "upper" if self.at(preview, 0, 0).y() == top else None)
                self.assertIsNotNone(edge, row.value)
                edges.add(edge)
        self.assertEqual(edges, {"lower", "upper"})                           # high up: its upper edge

    def named(self, value, name):
        """The row of value with this name, laid out at once."""
        row = self.row(value)
        row.name.setText(name)
        row.line.refit()
        row.layout().invalidate()
        row.layout().activate()
        return row

    def test_the_tags_follow_the_name_and_stay_whole(self):
        self.session.set((7, 28), 4)                                          # Phones: Preset 3
        self.settle()
        row = self.named(4, "A")
        self.assertEqual(row.tags.text(), "P")
        end = max(w.mapTo(row, QPoint(w.width(), 0)).x() for w in (row.name, row.mark) if w.isVisible())
        tags = row.tags.mapTo(row, QPoint(0, 0)).x()
        self.assertEqual(tags - end, TAGS_GAP)                                # the name fits: nothing of it fades
        self.assertEqual(row.label.mapTo(row, QPoint(row.label.width(), 0)).x(), tags)
        self.open(4)
        self.assertLessEqual(row.tags.mapTo(row, QPoint(row.tags.width(), 0)).x(), row.edit.x())
        self.assertEqual(row.tags.width(), row.tags.sizeHint().width())

    def test_a_name_cut_off_fades_out_before_the_tags(self):
        self.session.set((7, 28), 4)                                          # Phones: Preset 3
        self.settle()
        row = self.named(4, "A name as long as it can be")
        tags = row.tags.mapTo(row, QPoint(0, 0)).x()
        self.assertEqual(row.tags.width(), row.tags.sizeHint().width())       # whole
        self.assertEqual(row.label.mapTo(row, QPoint(row.label.width(), 0)).x(), tags)   # cut off at the tags
        self.assertGreater(row.name.mapTo(row, QPoint(row.name.width(), 0)).x(), tags)
        mask = row.line.fade.opacityMask().gradient()
        width = row.label.width()
        self.assertEqual((mask.start().x(), mask.finalStop().x()), (width - TAGS_GAP, width - TAGS_CLEAR))

    def test_they_follow_the_mouse(self):
        preview = self.open(3)
        self.point(self.row(5), 40, 10)                                       # on another slot's row
        self.assertIs(self.win.hovered_row, self.row(5))
        self.assertEqual(self.shown(self.row(3)), [])
        self.assertTrue(preview.isVisible())
        self.point(self.row(MANUAL), 40, 10)                                  # Manual: its actions only
        self.assertIs(self.win.hovered_row, self.row(MANUAL))
        self.assertFalse(preview.isVisible())
        self.open(3)
        self.point(preview, 20, 20)                                           # on the preview: off the rows
        self.assertIsNone(self.win.hovered_row)
        self.assertFalse(preview.isVisible())
        self.assertEqual(self.shown(self.row(3)), [])

    def test_an_action_closes_them(self):
        row = self.row(3)
        self.open(3)
        QTest.mouseClick(row.select, Qt.LeftButton)
        self.assertIsNone(self.win.hovered_row)
        self.assertEqual(self.shown(row), [])
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], 3)

    def test_the_row_s_tooltip_says_where_a_double_click_selects(self):
        self.assertEqual(self.row(3).toolTip(), "Shared by all outputs")      # not under the mouse
        self.open(3)
        self.assertEqual(self.row(3).toolTip(), "Shared by all outputs\n" + DOUBLE_CLICK_TIP)
        self.open(TEMP)
        self.assertTrue(self.row(TEMP).toolTip().endswith("\n" + DOUBLE_CLICK_TIP))
        self.assertEqual(self.row(3).toolTip(), "Shared by all outputs")
        self.open(6)                                                          # Preset 5, (free)
        self.assertEqual(self.row(6).toolTip(), "Shared by all outputs")
        self.open(CLEAR)
        self.assertTrue(self.row(CLEAR).toolTip().endswith("\n" + DOUBLE_CLICK_TIP))
        self.session.set((4, P.LOAD_BT), 1)                                   # Select amber
        self.settle()
        self.assertFalse(self.row(CLEAR).toolTip().endswith(DOUBLE_CLICK_TIP))

    def test_no_double_click_where_select_is_amber(self):
        self.session.set((4, P.LOAD_BT), 1)
        self.settle()
        self.open(CLEAR)
        QTest.mouseDClick(self.row(CLEAR), Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], MANUAL)

    def test_a_double_click_selects_except_on_an_unused_slot(self):
        for value in (3, TEMP, CLEAR):                                        # Preset 2
            self.open(value)
            QTest.mouseDClick(self.row(value), Qt.LeftButton)
            self.assertIsNone(self.win.hovered_row)                           # as after Select
            self.settle()
            self.assertEqual(self.sim.state[(4, 28)], value)
        self.open(6)                                                          # Preset 5, (free)
        QTest.mouseDClick(self.row(6), Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], CLEAR)
        self.assertIs(self.win.hovered_row, self.row(6))

    def test_a_double_click_on_select_is_one_select(self):
        row = self.row(3)
        self.open(3)
        writes = []
        self.win.presets.selected.connect(writes.append)
        QTest.mouseDClick(row.select, Qt.LeftButton)
        QTest.mouseDClick(row, Qt.LeftButton, pos=row.select.geometry().center())
        self.assertEqual(writes, [3])

    def test_no_double_click_on_a_slot_not_read_yet(self):
        del self.session.slots[2]
        self.open(3)
        QTest.mouseDClick(self.row(3), Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], MANUAL)

    def test_leaving_another_row_s_select_leaves_the_graph_as_it_is(self):
        preview = self.open(4)
        QApplication.sendEvent(self.row(4).select, QEvent(QEvent.Enter))
        self.assertTrue(preview.on_select)
        QApplication.sendEvent(self.row(3).select, QEvent(QEvent.Leave))     # the row before, after the next
        self.assertTrue(preview.on_select)
        QApplication.sendEvent(self.row(4).select, QEvent(QEvent.Leave))

    def test_the_graph_draws_what_the_slot_holds(self):
        preview = self.open(3)
        graph = preview.graph
        self.assertEqual([c.name() for c, _ in graph.eq], [side_color(0, False).name()])   # Dual EQ off: one EQ
        self.assertIsNotNone(graph.bt)
        slot = dict(self.session.slots[2], dual=1)
        slot["vals"] = slot["vals"] | {(14, 4): 12, (13, 21): 8}             # right band 1 +6 dB, Bass +4 dB
        preview.show_preset(3, slot, True, 48000)
        self.assertEqual([c.name() for c, _ in graph.eq], [theme.LEFT.name(), theme.RIGHT.name()])
        self.assertGreater(graph.eq[1][1].max(), graph.eq[0][1].max() + 3)
        self.assertGreater(graph.bt[0], 3)                                    # Bass, at 20 Hz
        self.assertFalse(graph.bt_off)

    def test_select_says_what_it_does_and_greys_bass_treble_that_stays(self):
        preview = self.open(3)
        select, graph = self.row(3).select, preview.graph
        self.assertEqual(select.toolTip(), "Select it on Line Out: its EQ is loaded there.\n"
                                           "Bass/Treble stays as it is: Load Bass/Treble with preset is off.")
        self.assertFalse(self.amber(select))
        QApplication.sendEvent(select, QEvent(QEvent.Enter))
        self.assertTrue(graph.bt_off)                                         # it does not come along
        QApplication.sendEvent(select, QEvent(QEvent.Leave))
        self.assertFalse(graph.bt_off)
        self.session.set((4, P.LOAD_BT), 1)
        self.settle()
        self.assertIn("Its Bass/Treble comes along", select.toolTip())
        QApplication.sendEvent(select, QEvent(QEvent.Enter))
        self.assertFalse(graph.bt_off)
        QApplication.sendEvent(select, QEvent(QEvent.Leave))

    def test_store_says_what_it_does(self):
        self.open(3)
        self.assertEqual(self.row(3).store.toolTip(),
                         "Store the current EQ of Line Out in Preset 2, Bass/Treble included.\n"
                         "It replaces what the graph shows; the name stays.\n"
                         "Afterwards Preset 2 is selected on Line Out.")
        self.session.set((7, 28), 3)                                          # Phones: Preset 2
        self.settle()
        self.open(3)
        self.assertTrue(self.row(3).store.toolTip().endswith(
            "Afterwards Preset 2 is selected on Line Out and loaded again on Phones 1/2."))
        self.open(6)
        self.assertIn("Preset 5 is unused: it becomes used, with the name it shows", self.row(6).store.toolTip())

    def test_select_again(self):
        self.session.set((4, 28), 3)
        self.settle()
        self.open(3)
        self.assertTrue(self.row(3).select.toolTip().startswith("Select it again: Line Out loads it as it is now"))

    def test_an_unused_slot_shows_nothing_until_the_mouse_is_on_select(self):
        preview = self.open(6)                                                # Preset 5, (free)
        graph, select = preview.graph, self.row(6).select
        self.assertEqual((graph.eq, graph.bt), ([], None))
        QApplication.sendEvent(select, QEvent(QEvent.Enter))                  # what Select loads: the factory state
        self.assertEqual(len(graph.eq), 1)
        self.assertTrue(np.allclose(graph.eq[0][1], 0, atol=0.01))
        self.assertTrue(graph.bt is not None and graph.bt_off)               # Bass/Treble stays as it is
        QApplication.sendEvent(select, QEvent(QEvent.Leave))
        self.assertEqual((graph.eq, graph.bt), ([], None))
        self.assertTrue(select.toolTip().startswith(
            "This preset is unused.\nSelect loads the factory state on Line Out: all bands 0 dB, Dual EQ off.\n"))
        self.assertEqual(self.row(6).edit.toolTip(), EDIT_TIP + "\n" + EDIT_FREE_TIP)
        self.assertFalse(self.amber(select))                                  # the graph shows all it does
        self.session.set((4, P.LOAD_BT), 1)
        self.settle()
        self.assertTrue(self.amber(select))                                   # but Bass/Treble switched on
        self.assertEqual(tooltip_color(select), theme.TEXT.name())            # amber only the name
        self.open(3)
        self.assertFalse(self.amber(self.row(3).select))

    def test_rumble_only_where_the_model_has_it(self):
        self.assertFalse(self.row(RUMBLE).isVisible())

    def test_clear_has_select_only_amber_where_it_switches_bass_treble_on(self):
        preview, row = self.open(CLEAR), self.row(CLEAR)
        self.assertEqual(self.shown(row), ["Select"])
        self.assertEqual(len(preview.graph.eq), 1)                            # the factory state: Dual EQ off,
        self.assertTrue(np.allclose(preview.graph.eq[0][1], 0, atol=0.01))    # flat
        self.assertFalse(self.amber(row.select))
        self.session.set((4, P.LOAD_BT), 1)
        self.settle()
        self.assertTrue(self.amber(row.select))
        self.assertIn("Bass/Treble 0 dB and switched on", row.select.toolTip())
        QTest.mouseClick(row.select, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], CLEAR)

    def test_a_slot_not_read_yet(self):
        del self.session.slots[2]
        preview, row = self.open(3), self.row(3)
        self.assertEqual((preview.graph.eq, preview.graph.bt), ([], None))
        self.assertFalse(row.select.isEnabled() or row.edit.isEnabled())
        self.assertEqual((row.select.toolTip(), row.edit.toolTip()), (NOT_READ, NOT_READ))
        self.assertTrue(row.store.isEnabled())

    def test_none_while_a_preset_is_written_or_edited(self):
        self.open(8)
        QTest.mouseClick(self.row(8).store, Qt.LeftButton)                    # Preset 7
        self.assertTrue(self.session.operating())
        self.open(3)
        self.assertIsNone(self.win.hovered_row)
        for _ in range(150):
            if not self.session.operating():
                break
            self.spin(100)
        self.win.edit_preset(2)
        self.spin(20)
        self.open(4)
        self.assertIsNone(self.win.hovered_row)
        self.win.finish_edit(False)

    def test_the_device_going_away_closes_it(self):
        self.open(3)
        self.sim.power(False)
        self.spin(1500)
        self.assertIsNone(self.win.hovered_row)


class Rumble(WindowTest):
    model = PRO_24

    def setUp(self):
        super().setUp()
        for _ in range(120):
            if len(self.session.slots) == 20:
                break
            self.spin(100)
        self.win.presets_tab.set_open(True)
        self.spin(50)

    def test_behind_clear_with_select_only(self):
        rows = self.win.presets.rows
        y = lambda w: w.mapTo(self.win.presets, QPoint(0, 0)).y()            # noqa: E731
        self.assertTrue(rows[RUMBLE].isVisible())
        self.assertEqual((rows[RUMBLE].number.text(), rows[RUMBLE].name.text()), ("22", "Rumble"))
        self.assertGreater(y(rows[RUMBLE]), y(rows[CLEAR]))
        self.win.presets_area.ensureWidgetVisible(rows[RUMBLE])
        self.spin(20)
        hover(self.win, rows[RUMBLE])
        self.spin(20)
        preview = self.win.preview
        row = rows[RUMBLE]
        self.assertTrue(preview.isVisible())
        self.assertEqual([w.isVisible() for w in (row.select, row.edit, row.store)], [True, False, False])
        self.assertTrue(row.select.toolTip().startswith("Select loads Rumble on Line Out"))
        self.assertEqual(len(preview.graph.eq), 1)                            # Dual EQ off
        db = preview.graph.eq[0][1]
        self.assertLess(db[0], -12)                                           # 20 Hz: the high pass and -12 dB
        self.assertAlmostEqual(db[-1], 0, places=2)
        QTest.mouseClick(row.select, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], RUMBLE)
        self.assertEqual(self.sim.state[(4, 5)], 35)
        self.assertTrue(rows[RUMBLE].dot.on)


if __name__ == "__main__":
    unittest.main()
