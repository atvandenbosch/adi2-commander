"""A preset's preview against the simulator: opened by the mouse on a slot's row, Clear or Rumble, not by a click;
beside the panel, joined to its row; following the mouse; its graph; Select, and what it says it does; an unused slot,
Clear, Rumble, a slot not read yet; and when there is none. Select, Store and Edit as actions on the device: test_preset_panel."""

import unittest

import numpy as np
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from commander.device import params as P
from commander.device.models import PRO_24
from commander.ui import theme
from commander.ui.graph import side_color
from commander.ui.presets import CLEAR, MANUAL, RUMBLE, TEMP
from commander.ui.preview import EDIT_FREE_TIP, EDIT_TIP, NOT_READ, PAD
from commander.ui.scrim import RISE
from commander.ui.window import PREVIEW_GAP
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

    def test_a_slot_shows_itself_under_the_mouse_and_a_click_on_it_selects_nothing(self):
        row, preview = self.row(3), self.open(3)                              # Preset 2
        self.assertTrue(preview.isVisible())
        self.assertTrue(row.peeked)
        self.assertIn(theme.BACKGROUND.name(), row.styleSheet())              # the preview's tab
        self.assertTrue(self.win.peek.isVisible() and not self.win.peek.veil)
        self.assertTrue(self.win.tabs.isEnabled())                            # nothing out of reach
        self.assertEqual(self.row(3).cursor().shape(), Qt.ArrowCursor)
        QTest.mouseClick(row, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], 0)                          # Manual still

    def test_manual_and_temp_are_selected_by_a_click(self):
        for value in (TEMP, MANUAL):
            row = self.row(value)
            hover(self.win, row)
            self.spin(20)
            self.assertIsNone(self.win.preview_row)
            self.assertEqual(row.cursor().shape(), Qt.PointingHandCursor)
            QTest.mouseClick(row, Qt.LeftButton)
            self.settle()
            self.assertEqual(self.sim.state[(4, 28)], value)

    def test_just_past_the_names_its_actions_level_with_the_row(self):
        row, preview = self.row(4), self.open(4)                              # Preset 3
        left = self.at(preview, 0, 0).x()
        names = max(self.at(r, r.text_end(False), 0).x() for r in self.win.presets.rows.values() if r.isVisible())
        self.assertEqual(left, names + PREVIEW_GAP)
        self.assertLess(left, self.at(self.win.presets_area, self.win.presets_area.width(), 0).x())   # over the panel
        middle = self.at(row, 0, row.height() // 2).y()
        actions = preview.actions.mapTo(self.win.centralWidget(), preview.actions.rect().center()).y()
        self.assertLessEqual(abs(actions - middle), 1)
        bottom = self.at(row, 0, row.height()).y() + RISE                     # the tab's lower edge runs on
        self.assertEqual(self.at(preview, 0, preview.height()).y(), bottom)   # as the preview's
        self.assertEqual([b.text() for b in (preview.select, preview.edit, preview.store)],
                         ["Select", "Edit", "Store"])
        self.assertLess(preview.select.x(), preview.edit.x())
        self.assertLess(preview.edit.x(), preview.store.x())
        self.assertEqual(preview.select.mapTo(preview, QPoint(0, 0)).x(), preview.graph.x())   # under its left edge
        self.assertEqual((preview.graph.x(), preview.graph.y()), (PAD, PAD))

    def test_an_edge_of_the_tab_runs_on_as_the_preview_s_in_a_low_window_too(self):
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
                top, bottom = self.at(row, 0, 0).y() - RISE, self.at(row, 0, row.height()).y() + RISE
                edge = ("lower" if self.at(preview, 0, preview.height()).y() == bottom else
                        "upper" if self.at(preview, 0, 0).y() == top else None)
                self.assertIsNotNone(edge, row.value)
                edges.add(edge)
        self.assertEqual(edges, {"lower", "upper"})                           # high up: its upper edge

    def test_the_tags_of_its_own_row_stay_in_sight(self):
        self.session.set((7, 28), 4)                                          # Phones: Preset 3
        self.settle()
        row = self.row(4)
        self.assertEqual(row.tags.text(), "P")
        preview = self.open(4)
        self.assertGreaterEqual(self.at(preview, 0, 0).x(), self.at(row.tags, row.tags.width(), 0).x())
        names = max(self.at(r, r.text_end(False), 0).x() for r in self.win.presets.rows.values() if r.isVisible())
        self.assertEqual(self.at(self.open(3), 0, 0).x(), names + PREVIEW_GAP)   # another row's tags: not counted

    def test_it_follows_the_mouse(self):
        preview = self.open(3)
        row = self.row(3)
        self.point(row, row.text_end(True) + 4, 10)                           # on the row, up to the preview
        self.assertIs(self.win.preview_row, row)
        self.point(preview, 20, 20)                                           # on it, over other rows
        self.assertIs(self.win.preview_row, row)
        self.point(self.row(5), 40, 10)                                       # on another slot's row
        self.assertIs(self.win.preview_row, self.row(5))
        self.assertFalse(self.row(3).peeked)
        self.point(self.row(MANUAL), 40, 10)
        self.assertIsNone(self.win.preview_row)
        self.assertFalse(preview.isVisible() or self.win.peek.isVisible())
        self.open(3)
        self.point(self.win.centralWidget(), self.win.centralWidget().width() - 10, 10)   # elsewhere
        self.assertIsNone(self.win.preview_row)

    def test_an_action_closes_it(self):
        preview = self.open(3)
        QTest.mouseClick(preview.select, Qt.LeftButton)
        self.assertIsNone(self.win.preview_row)
        self.assertFalse(self.row(3).peeked)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], 3)

    def test_the_graph_draws_what_the_slot_holds(self):
        preview = self.open(3)
        graph = preview.graph
        self.assertEqual([c.name() for c, _ in graph.eq], [side_color(0, False).name()])   # Dual EQ off: one EQ
        self.assertIsNotNone(graph.bt)
        slot = dict(self.session.slots[2], dual=1)
        slot["vals"] = slot["vals"] | {(14, 4): 12, (13, 21): 8}             # right band 1 +6 dB, Bass +4 dB
        preview.show_preset(3, slot, "Line Out", True, False, 48000)
        self.assertEqual([c.name() for c, _ in graph.eq], [theme.LEFT.name(), theme.RIGHT.name()])
        self.assertGreater(graph.eq[1][1].max(), graph.eq[0][1].max() + 3)
        self.assertGreater(graph.bt[0], 3)                                    # Bass, at 20 Hz
        self.assertFalse(graph.bt_off)

    def test_select_says_what_it_does_and_greys_bass_treble_that_stays(self):
        preview = self.open(3)
        select, graph = preview.select, preview.graph
        self.assertEqual(select.toolTip(), "Select it on Line Out: its EQ is loaded there\n"
                                           "Bass/Treble stays as it is: Load Bass/Treble with preset is off")
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
        self.assertEqual(self.open(3).store.toolTip(),
                         "Store the current EQ of Line Out in Preset 2, Bass/Treble included\n"
                         "It replaces what the graph shows; the name stays\n"
                         "Afterwards Preset 2 is selected on Line Out")
        self.session.set((7, 28), 3)                                          # Phones: Preset 2
        self.settle()
        self.assertTrue(self.open(3).store.toolTip().endswith(
            "Afterwards Preset 2 is selected on Line Out and loaded again on Phones 1/2"))
        self.assertIn("Preset 5 is unused: it becomes used, with the name it shows", self.open(6).store.toolTip())

    def test_select_again(self):
        self.session.set((4, 28), 3)
        self.settle()
        self.assertTrue(self.open(3).select.toolTip().startswith("Select it again: Line Out loads it as it is now"))

    def test_an_unused_slot_shows_nothing_until_the_mouse_is_on_select(self):
        preview = self.open(6)                                                # Preset 5, (free)
        graph, select = preview.graph, preview.select
        self.assertEqual((graph.eq, graph.bt), ([], None))
        QApplication.sendEvent(select, QEvent(QEvent.Enter))                  # what Select loads: the factory state
        self.assertEqual(len(graph.eq), 1)
        self.assertTrue(np.allclose(graph.eq[0][1], 0, atol=0.01))
        self.assertTrue(graph.bt is not None and graph.bt_off)               # Bass/Treble stays as it is
        QApplication.sendEvent(select, QEvent(QEvent.Leave))
        self.assertEqual((graph.eq, graph.bt), ([], None))
        self.assertTrue(select.toolTip().startswith(
            "This preset is unused\nSelect loads the factory state on Line Out: all bands 0 dB, Dual EQ off\n"))
        self.assertEqual(preview.edit.toolTip(), EDIT_TIP + "\n" + EDIT_FREE_TIP)
        self.assertFalse(self.amber(select))                                  # the graph shows all it does
        self.session.set((4, P.LOAD_BT), 1)
        self.settle()
        self.assertTrue(self.amber(select))                                   # but Bass/Treble switched on
        self.assertEqual(tooltip_color(select), theme.TEXT.name())            # amber only the name
        self.open(3)
        self.assertFalse(self.amber(select))

    def test_rumble_only_where_the_model_has_it(self):
        self.assertFalse(self.row(RUMBLE).isVisible())

    def test_clear_has_select_only_amber_where_it_switches_bass_treble_on(self):
        preview = self.open(CLEAR)
        self.assertTrue(preview.select.isVisible())
        self.assertFalse(preview.edit.isVisible() or preview.store.isVisible())
        self.assertEqual(len(preview.graph.eq), 1)                            # the factory state: Dual EQ off,
        self.assertTrue(np.allclose(preview.graph.eq[0][1], 0, atol=0.01))    # flat
        self.assertFalse(self.amber(preview.select))
        self.session.set((4, P.LOAD_BT), 1)
        self.settle()
        self.assertTrue(self.amber(preview.select))
        self.assertIn("Bass/Treble 0 dB and switched on", preview.select.toolTip())
        QTest.mouseClick(preview.select, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], CLEAR)

    def test_a_slot_not_read_yet(self):
        del self.session.slots[2]
        preview = self.open(3)
        self.assertEqual((preview.graph.eq, preview.graph.bt), ([], None))
        self.assertFalse(preview.select.isEnabled() or preview.edit.isEnabled())
        self.assertEqual((preview.select.toolTip(), preview.edit.toolTip()), (NOT_READ, NOT_READ))
        self.assertTrue(preview.store.isEnabled())

    def test_none_while_a_preset_is_written_or_edited(self):
        QTest.mouseClick(self.open(8).store, Qt.LeftButton)                   # Preset 7
        self.assertTrue(self.session.operating())
        self.open(3)
        self.assertIsNone(self.win.preview_row)
        for _ in range(150):
            if not self.session.operating():
                break
            self.spin(100)
        self.win.edit_preset(2)
        self.spin(20)
        self.open(4)
        self.assertIsNone(self.win.preview_row)
        self.win.finish_edit(False)

    def test_the_device_going_away_closes_it(self):
        self.open(3)
        self.sim.power(False)
        self.spin(1500)
        self.assertIsNone(self.win.preview_row)


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
        hover(self.win, rows[RUMBLE])
        self.spin(20)
        preview = self.win.preview
        self.assertTrue(preview.isVisible() and preview.select.isVisible())
        self.assertFalse(preview.edit.isVisible() or preview.store.isVisible())
        self.assertTrue(preview.select.toolTip().startswith("Select loads Rumble on Line Out"))
        self.assertEqual(len(preview.graph.eq), 1)                            # Dual EQ off
        db = preview.graph.eq[0][1]
        self.assertLess(db[0], -12)                                           # 20 Hz: the high pass and -12 dB
        self.assertAlmostEqual(db[-1], 0, places=2)
        QTest.mouseClick(preview.select, Qt.LeftButton)
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], RUMBLE)
        self.assertEqual(self.sim.state[(4, 5)], 35)
        self.assertTrue(rows[RUMBLE].dot.on)


if __name__ == "__main__":
    unittest.main()
