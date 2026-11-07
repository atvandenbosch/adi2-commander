"""The edit stand against the simulator: a preset opened from its row, changed without the device hearing it, and
left by OK or Cancel only; what lies under the veil, the name, the switches as titles, Save and Load on the preset,
what OK changes beyond it, the device going away, and closing the window."""

import os
import tempfile
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolTip

from commander.conversion import eqfile as E
from commander.conversion import presetfile as R
from commander.device import params as P
from commander.ui import theme
from commander.ui.presets import NAME_RULE
from tests.gui import WindowTest, tooltip_color


class EditStand(WindowTest):
    def setUp(self):
        super().setUp()
        self.wait(lambda: len(self.session.slots) == 20)
        self.win.presets_tab.set_open(True)
        self.win.discard_ok = lambda: True                                    # no question when the test ends
        self.spin(50)

    def wait(self, done, limit=15000):
        for _ in range(limit // 100):
            if done():
                return
            self.spin(100)
        self.fail("still waiting after %d ms" % limit)

    def edit(self, slot=2):
        self.win.edit_preset(slot)
        self.spin(50)
        return self.win.draft

    def name(self, slot):
        return bytes(self.sim.slots[slot]["name"]).split(b"\0")[0].decode()

    def ok(self, slot=2):
        return self.win.presets.rows[slot + 1].ok

    def cancel(self, slot=2):
        return self.win.presets.rows[slot + 1].cancel

    def names_sent(self):
        return [m for m in self.sim.received if m[5] == 0x06]

    def test_all_else_is_out_of_reach(self):
        self.edit()
        win = self.win
        self.assertTrue(win.scrim.isVisible())
        for w in (win.tabs, win.input_tab, win.output_tab, win.presets_tab, win.input_area, win.output_area):
            self.assertFalse(w.isEnabled())
        self.assertFalse(win.load_bt.isEnabled())
        self.assertFalse(win.presets.rows[4].isEnabled())
        QTest.keyClick(win, Qt.Key_Tab, Qt.ControlModifier)                   # no other output meanwhile
        self.assertEqual(win.tabs.currentIndex(), 0)
        for w in (win.band_views[0], win.bt_view, self.cancel(), win.preset_name, win.save_action):
            self.assertTrue(w.isEnabled() and w.isVisible())
        self.assertTrue(self.ok().isVisible())                                # disabled until something changes
        self.assertFalse(win.loudness_view.isVisible())                       # no part of a preset

    def test_nothing_is_chosen_at_the_start_and_the_work_before_comes_back(self):
        right = self.win.band_views[1]
        right.setFocus()
        right.setCurrentIndex(right.model().index(3, 2))                      # Band 4, dB of the output's EQ
        self.spin(50)
        self.edit()
        views = self.win.band_views + [self.win.bt_view]
        self.assertEqual([v.currentIndex().isValid() for v in views], [False] * 3)
        self.assertFalse(any(v.hasFocus() or v.chosen for v in views))
        self.assertIsNone(self.win.graph.current)
        QTest.mouseClick(self.cancel(), Qt.LeftButton)
        self.assertEqual((right.currentIndex().row(), right.currentIndex().column(), right.chosen), (3, 2, True))
        self.assertEqual(self.win.graph.current, (5, "4"))                    # Line Out, right: Band 4

    def test_ok_and_cancel_in_the_tab(self):
        row = self.win.presets.rows[3]
        self.edit()
        self.assertTrue(row.ok.isVisible() and row.cancel.isVisible())
        self.assertEqual(row.mark.text(), "")
        self.assertIn(theme.BACKGROUND.name(), row.styleSheet())              # the ground of the sound column
        self.assertFalse(self.win.presets.rows[4].ok.isVisible())
        self.win.write((4, 7), 6, False)
        QTest.mouseClick(row.ok, Qt.LeftButton)
        self.assertFalse(row.ok.isVisible() or row.cancel.isVisible())        # storing… in their place
        self.assertEqual(row.mark.text(), "storing…")
        self.wait(lambda: self.win.draft is None)
        self.assertFalse(row.ok.isVisible())
        self.assertNotIn(theme.BACKGROUND.name(), row.styleSheet())

    def test_the_head_and_the_switches(self):
        self.edit()
        self.assertEqual((self.win.eq_title.text(), self.win.preset_number.text()), ("PRESET", "2"))
        self.assertEqual(self.win.preset_name.text(), "EQ Preset 2")
        self.assertFalse(self.win.source.isVisible())
        switch = self.win.eq_switches[0]
        self.assertEqual(switch.icon().isNull(), True)                        # a title: no dot
        enable = self.sim.state[(4, P.EQ_ENABLE)]
        QTest.mouseClick(switch, Qt.LeftButton)
        QTest.mouseClick(self.win.bt_switch, Qt.LeftButton)
        self.spin(300)
        self.assertEqual(self.sim.state[(4, P.EQ_ENABLE)], enable)
        self.assertEqual(self.session.pending, {})

    def test_changes_stay_in_memory_until_ok(self):
        d = self.edit()
        live = self.sim.reported()
        self.win.write((4, 7), 6, False)                                      # band 2 of the preset +3 dB
        self.win.write((4, 21), -4, False)                                    # Bass -2 dB
        self.spin(1000)
        self.assertEqual(self.sim.reported(), live)
        self.assertEqual(self.session.pending, {})
        self.assertEqual(self.win.band_models[0].value(self.win.band_models[0].cell(
            self.win.band_models[0].index(1, 2))), 6)                         # the table shows the preset
        self.assertTrue(d.changed())
        QTest.mouseClick(self.ok(), Qt.LeftButton)
        self.assertTrue(d.locked)
        self.assertFalse(self.win.band_models[0].editable(self.win.band_models[0].cell(
            self.win.band_models[0].index(1, 2))))                            # nothing changes while it is written
        self.wait(lambda: self.win.draft is None)
        s = self.sim.slots[2]
        self.assertEqual((s["vals"][(13, 7)], s["vals"][(14, 7)], s["vals"][(13, 21)]), (6, 6, -4))   # Dual EQ off
        self.assertEqual(self.win.file_note.text(), "Stored Preset 2")
        self.assertFalse(self.win.scrim.isVisible())
        self.assertTrue(self.win.tabs.isEnabled())
        self.assertEqual(self.win.eq_title.text(), "EQ")
        self.assertTrue(self.win.loudness_view.isVisible())
        self.assertEqual(self.win.band_models[0].session, self.session)

    def test_cancel_writes_nothing(self):
        self.edit()
        self.win.write((4, 7), 6, False)
        self.win.preset_name.setText("Room")
        self.win.rename_draft("Room")
        QTest.mouseClick(self.cancel(), Qt.LeftButton)
        self.spin(1500)
        self.assertIsNone(self.win.draft)
        self.assertEqual(self.names_sent(), [])
        self.assertEqual(self.name(2), "   EQ Preset 2")
        self.assertEqual(self.win.file_note.text(), "Edit of Preset 2 cancelled")
        self.assertEqual(self.win.presets.rows[3].name.text(), "EQ Preset 2")

    def test_ok_is_off_while_the_preset_is_unchanged(self):
        d = self.edit()
        ok = self.ok()
        self.assertFalse(ok.isEnabled())
        self.assertEqual(ok.toolTip(), "Nothing to write: the preset is unchanged")
        self.win.write((4, 7), 6, False)
        self.assertTrue(ok.isEnabled())
        self.assertEqual(ok.toolTip(), "Write this preset to the device as it is now")
        self.win.write((4, 7), d.base["vals"][(13, 7)], False)                # and back
        self.assertFalse(ok.isEnabled())
        self.win.finish_edit(True)                                            # as if it were clicked
        self.spin(1500)
        self.assertIs(self.win.draft, d)
        self.assertEqual(self.names_sent(), [])

    def test_the_name_is_typed_in_the_column_and_shows_in_the_row(self):
        self.edit()
        field, row = self.win.preset_name, self.win.presets.rows[3]
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "Room~ 50%")
        self.assertEqual(field.text(), "Room 50")                             # ~ and % are not on the front panel
        self.assertEqual(QToolTip.text(), NAME_RULE)
        self.assertEqual((row.name.text(), row.mark.text()), ("Room 50", ""))
        QTest.keyClick(field, Qt.Key_Escape)                                  # back to the name it has
        self.assertEqual((field.text(), row.name.text()), ("EQ Preset 2", "EQ Preset 2"))
        field.selectAll()
        QTest.keyClicks(field, "Room 50")
        QTest.mouseClick(self.ok(), Qt.LeftButton)
        self.wait(lambda: self.win.draft is None)
        self.assertEqual(self.name(2), "       Room 50")                      # aligned right on 14

    def test_an_unused_slot_starts_as_the_factory_state(self):
        d = self.edit(5)                                                      # (free), with the device's name
        ok = self.ok(5)
        self.assertEqual((d.name, self.win.preset_name.text()), ("EQ Preset 5", "EQ Preset 5"))
        self.assertEqual({k: d.state[(4, k)] for k in P.FACTORY_BANDS}, P.FACTORY_BANDS)
        self.assertFalse(ok.isEnabled())                                      # as it is: nothing to write
        self.win.preset_name.setText("Spare")
        self.win.rename_draft("Spare")
        QTest.mouseClick(ok, Qt.LeftButton)
        self.wait(lambda: self.win.draft is None)
        self.assertEqual((self.sim.slots[5]["used"], self.name(5)), (True, "         Spare"))

    def test_share_and_split_on_the_preset(self):
        d = self.edit()
        dual = self.sim.state[(3, P.DUAL_EQ)]
        QTest.mouseClick(self.win.dual_actions[0], Qt.LeftButton)            # Split
        self.spin(300)
        self.assertEqual((d.dual(3), self.sim.state[(3, P.DUAL_EQ)]), (True, dual))
        self.assertTrue(self.win.band_views[1].isEnabled())
        self.win.write((5, 7), 4, False)                                      # the right channel of the preset
        self.assertEqual(d.content()["vals"][(14, 7)], 4)

    def test_save_and_load_work_on_the_preset(self):
        d = self.edit()
        self.win.write((4, 7), 6, False)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "preset.txt")
            self.win.save_file(path)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("\n# Preset: %d" % d.slot, text)
            self.assertNotIn("# Output:", text)
            band2 = next(r for r in E.table(E.read(text)) if r.target == 2)
            self.assertEqual((band2.freq, band2.gain), (1000, 3.0))
            self.win.write((4, 7), 0, False)
            self.win.ask = lambda dialog: dialog.accept() or True
            self.win.load_file(path)
        self.assertEqual(d.state[(4, 7)], 6)
        self.assertEqual(self.sim.state[(4, 7)], self.session.state[(4, 7)])  # the device heard nothing
        self.assertEqual(self.session.pending, {})

    def test_saved_for_adi2_remote_under_the_presets_name(self):
        d = self.edit()
        self.win.write((4, 7), 6, False)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "file.adieqpr")
            self.win.save_file(path)
            with open(path, encoding="ascii") as f:
                text = f.read()
        self.assertEqual(text, R.write(d.state, 3, d.name, self.win.model, self.session.revision()))
        self.assertIn('v="%s"' % d.name, text)
        self.assertIn('<val e="EQBand2Gain" v="3.00,"/>', text)                # the preset, not the output

    def test_what_ok_changes_beyond_the_preset(self):
        self.session.set((4, 28), 3)                                          # Line Out, active: Preset 2
        self.session.set((10, 28), 3)                                         # IEM too
        self.settle()
        self.edit()
        row = self.win.presets.rows[3]                                        # the tab
        self.assertEqual(row.label.toolTip(), "")                             # unchanged: OK does nothing
        self.assertNotIn(theme.WARN.name(), row.name.styleSheet())
        self.win.write((4, 7), 6, False)
        self.assertIn(theme.WARN.name(), row.name.styleSheet())
        self.assertEqual(row.label.toolTip(), "Selected on Line Out and Phones 3/4 · IEM: OK loads it there")
        self.assertEqual(tooltip_color(row.label), theme.TEXT.name())         # amber only the name, as everywhere
        QTest.mouseClick(self.ok(), Qt.LeftButton)
        self.wait(lambda: self.win.draft is None)
        self.settle()
        self.assertEqual((self.sim.state[(4, 7)], self.sim.state[(10, 7)]), (6, 6))   # both load it again

    def test_a_preset_written_elsewhere_meanwhile(self):
        self.edit()
        row = self.win.presets.rows[3]
        self.win.write((4, 7), 6, False)
        self.assertEqual(row.label.toolTip(), "")
        self.assertNotIn(theme.WARN.name(), row.name.styleSheet())
        self.sim.slots[2] = dict(self.sim.slots[2], vals=self.sim.slots[2]["vals"] | {(13, 7): 2})   # front panel
        self.wait(lambda: "meanwhile" in row.label.toolTip(), 20000)
        self.assertIn(theme.WARN.name(), row.name.styleSheet())
        self.win.write((4, 7), self.win.draft.base["vals"][(13, 7)], False)  # unchanged again: OK writes nothing
        self.assertEqual(row.label.toolTip(), "")

    def test_the_device_going_away_keeps_the_preset(self):
        d = self.edit()
        self.win.write((4, 7), 6, False)
        self.sim.power(False)
        self.spin(1500)
        self.assertIs(self.win.draft, d)
        self.assertEqual(d.state[(4, 7)], 6)
        self.assertFalse(self.ok().isEnabled())
        self.assertEqual(self.ok().toolTip(), "OK waits for the device: it is not connected")
        self.sim.power(True)
        self.wait(lambda: self.session.ready() and len(self.session.slots) == 20)
        self.assertTrue(self.ok().isEnabled())
        self.assertEqual(self.ok().toolTip(), "Write this preset to the device as it is now")
        QTest.mouseClick(self.ok(), Qt.LeftButton)
        self.wait(lambda: self.win.draft is None)
        self.assertEqual(self.sim.slots[2]["vals"][(13, 7)], 6)

    def test_gone_while_it_is_written_the_stand_stays(self):
        d = self.edit()
        self.win.write((4, 7), 6, False)
        QTest.mouseClick(self.ok(), Qt.LeftButton)
        self.spin(400)
        self.sim.power(False)
        self.spin(1500)
        self.assertIs(self.win.draft, d)
        self.assertFalse(d.locked)
        self.assertIn("the device was disconnected", self.win.file_note.text())

    def test_closing_with_changes_asks(self):
        self.edit()
        self.win.write((4, 7), 6, False)
        asked = []
        self.win.discard_ok = lambda: asked.append(1) or False
        self.win.close()
        self.assertTrue(self.win.isVisible())
        self.win.discard_ok = lambda: asked.append(2) or True
        self.win.close()
        self.assertFalse(self.win.isVisible())
        self.assertEqual(asked, [1, 2])
        self.assertEqual(self.names_sent(), [])

    def test_closing_without_changes_does_not_ask(self):
        self.edit(5)                                                          # (free): as it opened, too
        self.win.discard_ok = lambda: self.fail("asked")
        self.win.close()
        self.assertFalse(self.win.isVisible())


if __name__ == "__main__":
    unittest.main()
