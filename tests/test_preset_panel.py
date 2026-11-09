"""The presets panel against the simulator: closed until its tab opens it, its groups, the slots as the device has them,
(free) and (lin), Select, Store and Edit in a row's preview, Load B/T, and where else a slot is selected. The preview
itself: test_preview; the edit stand: test_edit."""

import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from commander.ui import theme
from commander.ui.presets import CLEAR, MANUAL, STALE_TIP, mark
from commander.ui.widgets import Dot
from commander.ui.preview import EDIT_FREE_TIP, EDIT_TIP
from tests.gui import WindowTest, hover, tab, tooltip_color


class PresetPanel(WindowTest):
    def setUp(self):
        super().setUp()
        self.wait(lambda: len(self.session.slots) == 20)
        self.win.presets_tab.set_open(True)
        self.spin(50)

    def wait(self, done, limit=12000):
        for _ in range(limit // 100):
            if done():
                return
            self.spin(100)
        self.fail("still waiting after %d ms" % limit)

    def row(self, value):
        return self.win.presets.rows[value]

    def name(self, slot):
        return bytes(self.sim.slots[slot]["name"]).split(b"\0")[0].decode()

    def preview(self, value):
        """The preview of this row, open."""
        hover(self.win, self.row(value))
        self.spin(20)
        self.assertIs(self.win.preview_row, self.row(value))
        return self.win.preview

    def test_closed_until_its_tab_opens_it(self):
        self.win.presets_tab.set_open(False)
        self.spin(50)
        self.assertFalse(self.win.presets_area.isVisible())
        QTest.mouseClick(self.win.presets_tab, Qt.LeftButton)
        self.assertTrue(self.win.presets_area.isVisible())

    def test_the_output_its_own_then_user_and_factory(self):
        y = lambda w: w.mapTo(self.win.presets, w.rect().topLeft()).y()          # noqa: E731
        panel = self.win.presets
        titles = {t.text(): t for t in panel.findChildren(type(panel.output_title)) if t.text().isupper()}
        self.assertEqual(panel.output_title.text(), "LINE OUT")                 # the name of the tab
        order = [titles["LINE OUT"], self.win.load_bt, self.row(MANUAL), titles["USER"], self.row(2),
                 titles["FACTORY"], self.row(CLEAR)]
        self.assertEqual(sorted(order, key=y), order)
        self.win.tabs.setCurrentIndex(tab(9))
        self.assertEqual(panel.output_title.text(), "PHONES 3/4 · IEM")

    def test_the_slots_as_the_device_has_them(self):
        self.assertEqual(self.row(2).name.text(), "EQ Preset 1")              # without the device's leading spaces
        self.assertEqual([self.row(n + 1).mark.text() for n in range(1, 21)],
                         ["(lin)", "", "(lin)", "(lin)"] + ["(free)"] * 14 + ["(lin)", "(lin)"])
        self.assertTrue(self.row(MANUAL).dot.on)                              # Line Out: Manual
        self.assertFalse(self.row(2).dot.on)

    def test_numbers_and_tags_in_the_app_font(self):
        family = QApplication.font().family()                                 # labels, not values one sets
        row = self.row(3)
        self.assertEqual([w.font().family() for w in (row.number, row.tags, self.win.source.number)], [family] * 3)

    def test_lin_is_all_gains_zero_and_no_pass_filter(self):
        flat = self.session.slots[1]

        def changed(key, value):
            return mark(dict(flat, vals=flat["vals"] | {key: value}))
        self.assertEqual(mark(flat), "(lin)")
        self.assertEqual(changed((13, 8), 1000), "(lin)")                     # another frequency, gain 0
        self.assertEqual(changed((13, 9), 20), "(lin)")                       # another Q
        self.assertEqual(changed((13, 21), 6), "(lin)")                       # Bass +3 dB
        self.assertEqual(changed((14, 7), -2), "")                            # a gain, right
        self.assertEqual(changed((14, 3), 2), "")                             # band 1 High Pass, right
        self.assertEqual(changed((13, 16), 2), "")                            # band 5 High Cut
        self.assertEqual(mark(None), "")                                      # not read yet

    def test_select_in_the_preview(self):
        QTest.mouseClick(self.preview(3).select, Qt.LeftButton)               # Preset 2
        self.settle()
        self.assertEqual(self.sim.state[(4, 28)], 3)
        self.assertEqual((self.row(3).dot.on, self.row(MANUAL).dot.on), (True, False))
        self.assertEqual((self.win.source.number.text(), self.win.source.name.text()), ("2", "EQ Preset 2"))

    def test_load_bt_is_an_option(self):
        option = self.win.load_bt
        self.assertEqual((option.name, option.on), ("Load Bass/Treble with preset", False))
        self.assertIn("Not loaded with a preset", self.win.bt_switch.toolTip())
        QTest.mouseClick(option, Qt.LeftButton)
        self.settle()
        self.assertEqual((self.sim.state[(4, 27)], option.on), (1, True))
        self.assertIn("Loaded with a preset", self.win.bt_switch.toolTip())   # where Bass/Treble is set
        option.setFocus()
        QTest.keyClick(option, Qt.Key_Space)                                  # the keyboard as well
        self.settle()
        self.assertEqual((self.sim.state[(4, 27)], option.on), (0, False))

    def test_store_from_the_preview(self):
        row = self.row(8)                                                     # Preset 7, unused
        QTest.mouseClick(self.preview(8).store, Qt.LeftButton)
        self.assertFalse(self.row(3).isEnabled())                             # nothing to select meanwhile
        self.wait(lambda: not self.session.operating())
        self.assertEqual(self.win.file_note.text(), "Stored in Preset 7")
        self.assertEqual((self.sim.slots[7]["used"], self.name(7)), (True, "  EQ Preset 7"))
        self.assertEqual(self.sim.state[(4, 28)], 8)                          # selected on Line Out now
        self.assertEqual((row.mark.text(), row.dot.on, self.row(3).isEnabled()), ("", True, True))

    def test_edit_from_the_preview(self):
        row = self.row(3)                                                     # Preset 2
        QTest.mouseClick(self.preview(3).edit, Qt.LeftButton)
        self.assertEqual(self.win.draft.slot, 2)
        self.assertEqual((row.name.text(), row.isEnabled(), row.ok.isVisible()), ("EQ Preset 2", True, True))
        self.assertFalse(self.row(4).isEnabled())                             # nothing else to select meanwhile
        hover(self.win, self.row(4))                                          # no preview meanwhile
        self.spin(20)
        self.assertIsNone(self.win.preview_row)
        self.assertEqual(self.sim.state[(4, 28)], 0)

    def test_edit_says_what_it_does_to_an_unused_slot(self):
        self.assertIn(EDIT_FREE_TIP, self.preview(6).edit.toolTip())         # Preset 5, (free)
        self.assertEqual(self.preview(3).edit.toolTip(), EDIT_TIP)

    def test_a_written_row_shows_its_new_name_at_once(self):
        row = self.row(3)
        self.win.edit_preset(2)
        self.win.preset_name.setText("Room")
        self.win.rename_draft("Room")
        QTest.mouseClick(row.ok, Qt.LeftButton)
        self.assertEqual((row.name.text(), row.mark.text()), ("Room", "storing…"))    # before the device has it
        self.assertIn(theme.WARN.name(), row.mark.styleSheet())              # in amber
        self.spin(60)
        self.assertTrue(self.win.lamp.busy)                                   # the lamp pulses meanwhile
        self.assertEqual([d for d in row.findChildren(Dot) if d.isVisible() and d.on], [])   # the row has no dot
        self.wait(lambda: not self.session.operating())
        self.assertEqual((row.name.text(), row.mark.text()), ("Room", ""))
        self.assertFalse(self.win.lamp.busy)

    def test_a_stored_row_says_storing(self):
        row = self.row(8)                                                     # Preset 7, (free)
        QTest.mouseClick(self.preview(8).store, Qt.LeftButton)
        self.assertEqual((row.name.text(), row.mark.text()), ("EQ Preset 7", "storing…"))
        self.assertEqual((row.dot.on, self.row(MANUAL).dot.on), (False, True))       # one selected row, still
        self.wait(lambda: not self.session.operating())
        self.assertEqual(row.mark.text(), "")                                 # Line Out's EQ is not flat

    def test_a_row_that_reads_back_otherwise_is_marked_until_the_next_action(self):
        commit = self.sim._commit

        def commit_wrong(flag):
            self.sim.pending[(13, 4)] += 2
            commit(flag)

        self.sim._commit = commit_wrong
        row = self.row(8)
        QTest.mouseClick(self.preview(8).store, Qt.LeftButton)
        self.wait(lambda: not self.session.operating(), 15000)
        gain = self.sim.state[(4, 4)]
        self.assertEqual(row.mark.text(), "not as sent")
        self.assertEqual(row.mark.toolTip(), "13/4: sent %d, the device has %d" % (gain, gain + 2))
        self.assertEqual(tooltip_color(row.mark), theme.TEXT.name())                  # red only the mark
        self.assertIn("reads back otherwise", self.win.file_note.text())
        self.sim._commit = commit
        QTest.mouseClick(self.preview(8).select, Qt.LeftButton)               # the next action on it: Select
        self.settle()
        self.assertEqual(row.mark.text(), "")

    def test_an_earlier_copy_shows_in_the_eq_head(self):
        self.win.tabs.setCurrentIndex(tab(9))                                      # IEM, not active
        self.session.set((10, 28), 3)                                         # Preset 2
        self.settle()
        self.sim.slots[2] = dict(self.sim.slots[2], vals=self.sim.slots[2]["vals"] | {(13, 7): 0})   # elsewhere
        self.wait(lambda: self.session.stale(9))
        source, row = self.win.source, self.row(3)
        self.assertIn(theme.WARN.name(), source.name.styleSheet())
        self.assertEqual(source.toolTip(), STALE_TIP)
        self.assertNotIn(theme.WARN.name(), row.name.styleSheet())            # the slot itself is as it should be
        QTest.mouseClick(self.preview(3).select, Qt.LeftButton)               # selected again
        self.settle()
        self.assertNotIn(theme.WARN.name(), source.name.styleSheet())
        self.assertEqual(source.toolTip(), "")

    def test_where_else_a_slot_is_chosen(self):
        self.session.set((7, 28), 3)                                          # Phones: Preset 2
        self.settle()
        self.assertEqual(self.row(3).tags.text(), "P")
        self.session.set((7, 28), 0)                                          # Phones: Manual
        self.settle()
        self.assertEqual(self.row(MANUAL).tags.text(), "")                    # Manual is each output's own


if __name__ == "__main__":
    unittest.main()
