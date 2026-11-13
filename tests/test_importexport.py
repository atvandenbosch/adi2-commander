"""Import and Export in the window: how the dialog starts for each kind of file, Map, what is checked and what stands
in the way of OK, what OK writes, the device changing or going while it is open, dropping a file, and a file that
is neither a filter file nor a curve. Fit at work and curves: test_importfit."""

import os
import tempfile
import time
from unittest import mock

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from commander.conversion import eqfile as E
from commander.conversion import presetfile as R
from commander.device import codec
from commander.device import params as P
from commander.device.models import PRO, PRO_24
from commander.ui import importdialog as D
from commander.ui import theme
from commander.ui import window as W
from commander.ui.widgets import INNER_GAP, SIDE
from tests.gui import WindowTest, tab
from tests.support import TEN_FILTERS

OUT, LEFT, RIGHT = 3, 4, 5
THREE = ("Filter: ON PK Fc 100 Hz Gain 2.0 dB Q 1.0\nFilter: ON PK Fc 1000 Hz Gain -3.0 dB Q 2.0\n"
         "Filter: ON PK Fc 5000 Hz Gain 1.5 dB Q 1.4\n")                     # fits the device exactly as written


class ImportTest(WindowTest):
    """The window with Import: files to import, and the dialog answered as the user would."""

    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.asked = []
        self.check = None                                # what to look at in the dialog before OK
        self.win.ask = self.answer

    def answer(self, dialog, ok=True):
        """As the user: look (self.check), then OK, which takes only when it can."""
        self.asked.append(dialog)
        wait_for_fit(dialog)
        if self.check:
            self.check(dialog)
        if ok:
            dialog.accept()
        if dialog.result() != QDialog.Accepted:
            dialog.reject()
        return dialog.result() == QDialog.Accepted

    def without_auto_ref_level(self):
        """For a fit that is written: it may put a positive gain anywhere, and what Auto Ref Level does with one
        between 4000 and 5000 Hz is outside the simulator."""
        self.session.set((OUT, P.AUTO_REF_LEVEL), 0)
        self.settle()

    def file(self, name, text):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def eq_of(self, addresses):
        return {k: v for k, v in self.sim.state.items() if k[0] in addresses and 2 <= k[1] <= 26}

    def open(self, path):
        """The dialog for a file, left open."""
        self.win.ask = lambda dialog: self.asked.append(dialog) or False
        self.win.import_file(path)
        dialog = self.asked[-1]
        wait_for_fit(dialog)
        self.addCleanup(dialog.done, 0)
        return dialog

    def drop_on(self, dialog, path):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        drop = QDropEvent(QPointF(dialog.rect().center()), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        dialog.dropEvent(drop)


class ImportExport(ImportTest):
    def test_maximized_on_a_screen_too_small_and_as_it_was_closed(self):
        dialog = self.open(self.file("three.txt", THREE))
        self.assertTrue(dialog.isMaximized())                    # the test screen is 800 x 600
        dialog.setWindowState(Qt.WindowNoState)
        dialog.done(0)
        self.assertFalse(D.ImportDialog.maximized)

    def test_low_its_tables_scroll_and_ok_stays_in_sight_below_them(self):
        dialog = self.open(self.file("ten.txt", TEN_FILTERS))
        dialog.setWindowState(Qt.WindowNoState)
        dialog.show()                                            # laid out as on the screen

        def at(w):
            p = w.mapTo(dialog, QPoint(0, 0))
            return p.y(), p.y() + w.height(), dialog.width() - p.x() - w.width()
        for height in (780, 500):
            dialog.resize(1500, height)
            self.spin(100)
            self.assertEqual(dialog.height(), height)
            self.assertEqual(dialog.tables.verticalScrollBar().isVisible(), height == 500)
            ok = at(dialog.ok)
            self.assertEqual(ok[0] - at(dialog.tables)[1], INNER_GAP)
            self.assertLess(ok[1], at(dialog.status)[0])                         # above the status line
            cancel = next(w for w in dialog.findChildren(QPushButton) if w.text() == "Cancel")
            self.assertEqual([at(cancel)[2], at(dialog.band_views[0])[2]], [SIDE, SIDE])     # on one line
            self.assertEqual(at(dialog.tables)[2], 0)                             # its scroll bar against the edge

    def test_export_and_import_back_exactly(self):
        before = self.eq_of((LEFT, RIGHT))
        path = os.path.join(self.dir.name, "line out.txt")
        self.win.export_file(path)
        self.assertTrue(self.win.file_note.text().startswith("Exported"))
        self.session.set((LEFT, 7), 10)                          # band 2 gain +5 dB
        self.session.set((RIGHT, 18), 9000)
        self.settle()
        self.win.import_file(path)
        self.settle()
        self.assertEqual(self.eq_of((LEFT, RIGHT)), before)
        self.assertEqual(self.win.file_note.text(), "Imported line out.txt")
        dialog = self.asked[0]
        self.assertEqual((dialog.mode, dialog.origin), (D.MAP, "ADI-2"))   # a Commander file maps its table

    def test_a_file_that_fits_maps_the_rest_is_factory_default(self):
        self.win.import_file(self.file("three.txt", THREE))
        self.settle()
        dialog = self.asked[0]
        self.assertEqual((dialog.mode, dialog.origin), (D.MAP, "External"))
        self.assertEqual([self.sim.state[(LEFT, i)] for i in (5, 4, 6)], [100, 4, 10])     # band 1
        for i in range(14, 20):                                  # bands 4 and 5: not set by the file
            self.assertEqual(self.sim.state[(LEFT, i)], P.FACTORY_BANDS[i])
        self.assertFalse(dialog.bt_corner.box.isChecked())       # Bass/Treble not set at all: left as they are

    def test_map_proposes_what_maps_and_says_why_more_does_not(self):
        dialog = self.open(self.file("ten.txt", TEN_FILTERS))
        dialog.way.buttons[D.MAP].click()
        checked = sorted(dialog.selection())
        self.assertEqual(len(checked), 5)                       # the largest effect that maps
        self.assertTrue(dialog.ok.isEnabled())
        extra = next(n for n in range(2, 12) if n not in checked)
        dialog.toggle_line(extra)
        self.assertTrue(dialog.problem.startswith("6 filters for 5 bands"))
        self.assertIn("or try Fit", dialog.problem)
        self.assertFalse(dialog.ok.isEnabled())
        self.assertTrue(all(dialog.input.item(n - 1).data(D.WARN_ROLE) for n in checked + [extra]))

    def test_the_users_selection_holds_for_map_and_fit(self):
        dialog = self.open(self.file("ten.txt", TEN_FILTERS))
        everything = set(dialog.selection())                     # Fit proposes all, Map what maps
        dialog.way.buttons[D.MAP].click()
        proposal = set(dialog.selection())
        self.assertLess(proposal, everything)
        extra = min(everything - proposal)
        dialog.toggle_line(extra)                                # one too many: "or try Fit"
        dialog.way.buttons[D.FIT].click()
        self.assertEqual(dialog.selection(), proposal | {extra})
        dialog.origin_box.setCurrentIndex(0)                     # other lines: the proposal again
        dialog.origin_box.setCurrentIndex(1)
        self.assertEqual(dialog.selection(), everything)

    def test_nothing_to_import_is_said_in_the_dialog(self):
        before = dict(self.sim.state)
        dialog = self.open(self.file("off.txt", "Preamp: -3 dB\nFilter: OFF PK Fc 100 Hz Gain 1 dB Q 1\n"
                                                "GraphicEQ: 20 0; 40 1\n"))
        self.assertEqual(dialog.problem, "Nothing to import")
        self.assertFalse(dialog.ok.isEnabled())
        self.assertEqual([dialog.input.item(n).toolTip() for n in range(3)],
                         ["Preamp: not needed on the device", "Off in the file", "GraphicEQ: not an EQ filter"])
        self.spin(300)
        self.assertEqual(self.sim.state, before)

    def test_nothing_selected_or_nothing_into_the_device(self):
        dialog = self.open(self.file("three.txt", THREE))
        for n in (1, 2, 3):
            dialog.toggle_line(n)
        self.assertEqual(dialog.problem, "Nothing selected")
        self.assertFalse(dialog.ok.isEnabled())
        for n in (1, 2, 3):
            dialog.toggle_line(n)
        self.assertTrue(dialog.ok.isEnabled())
        dialog.toggle_block(0)                                   # EQ Left, EQ Right; Bass/Treble is off already
        dialog.toggle_block(1)
        self.assertIn("Nothing to write to the device", dialog.status.text())
        self.assertFalse(dialog.ok.isEnabled())
        self.assertEqual(dialog.ok.toolTip(), "Write the checked tables to the device")
        self.assertEqual(dialog.bt_corner.box.toolTip(), "Checked: OK writes this table")

    def test_export_for_adi2_remote(self):
        path = os.path.join(self.dir.name, "HD 800 S (Harman).adieqpr")
        self.win.export_file(path)
        self.assertEqual(self.win.file_note.text(), "Exported HD 800 S (Harman).adieqpr")
        with open(path, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(raw.decode("ascii"), R.write(self.session.state, OUT, "HD 800 S (Harm", self.win.model,
                                                      self.session.revision()))      # named as the file
        self.assertTrue(raw.startswith(b"\t<ADI-2DAC>"))

    def test_the_kind_of_file_chosen_when_saving(self):
        for typed, kind, exported in (("a.txt", W.APO_FILES, "a.txt"), ("b.txt", W.REMOTE_FILES, "b.adieqpr"),
                                   ("c", W.REMOTE_FILES, "c.adieqpr"), ("d.adieqpr", W.REMOTE_FILES, "d.adieqpr")):
            answer = (os.path.join(self.dir.name, typed), kind)
            with mock.patch.object(W.QFileDialog, "getSaveFileName", return_value=answer) as dialog:
                self.win.export_dialog()
            self.assertTrue(os.path.exists(os.path.join(self.dir.name, exported)), exported)
            self.assertEqual(dialog.call_args[0][3], "Equalizer APO (*.txt);;ADI-2 Remote preset (*.adieqpr)")

    def test_already_on_the_device(self):
        path = os.path.join(self.dir.name, "same.txt")
        self.win.export_file(path)
        self.win.import_file(path)
        self.assertTrue(self.asked[0].unchanged)
        self.assertEqual(self.win.file_note.text(), "Already on the device: same.txt")

    def test_the_device_gone_and_back(self):
        dialog = self.open(self.file("three.txt", THREE))
        dialog.connection("searching", "")
        self.assertIn("The device is not connected", dialog.status.text())
        self.assertFalse(dialog.ok.isEnabled())
        dialog.connection("ready", "")
        self.assertNotIn("not connected", dialog.status.text())
        self.assertTrue(dialog.ok.isEnabled())
        dialog.done(0)
        self.assertNotIn(dialog.connection, self.session.on_connection)   # let go when closed
        self.assertNotIn(dialog.changed, self.session.on_changed)

    def test_follows_dual_eq_on_the_device(self):
        dialog = self.open(self.file("three.txt", THREE))
        self.assertTrue(dialog.dual)                             # Dual EQ on in the dump
        self.assertEqual(dialog.corners[0].name.text(), "EQ LEFT")
        self.session.set_dual(OUT, False)
        self.settle()
        self.assertFalse(dialog.dual)
        self.assertEqual([c.name.text() for c in dialog.corners], ["EQ L = R", "EQ R = L"])
        self.assertEqual(set(dialog.outcome), {"all"})

    def test_left_and_right_of_their_own_without_dual_eq(self):
        self.session.set_dual(OUT, False)
        self.settle()
        dialog = self.open(self.file("lr.txt", "Channel: L\nFilter: ON PK Fc 100 Hz Gain 1.0 dB Q 1.0\n"
                                               "Channel: R\nFilter: ON PK Fc 200 Hz Gain 1.0 dB Q 1.0\n"))
        self.assertEqual(dialog.selection(), {2})                # the left proposed, the right unchecked
        dialog.toggle_line(4)
        self.assertTrue(dialog.problem.startswith("Dual EQ is off"))
        self.assertFalse(dialog.ok.isEnabled())

    def test_a_commander_file_its_table_or_its_filter_lines(self):
        path = os.path.join(self.dir.name, "line out.txt")
        self.win.export_file(path)
        eq = E.load(path)
        rows = {r.line for r in E.table(eq)}
        dialog = self.open(path)
        self.assertTrue(all(dialog.input.item(n - 1).data(D.STATE_ROLE) == "on" for n in rows))
        self.assertTrue(all(dialog.input.item(e.line - 1).data(D.STATE_ROLE) is None for e in eq.entries))
        dialog.origin_box.setCurrentIndex(1)                     # External: the Filter lines
        self.assertTrue(all(dialog.input.item(n - 1).data(D.STATE_ROLE) is None for n in rows))
        self.assertTrue(all(dialog.input.item(e.line - 1).data(D.STATE_ROLE) == "on" for e in eq.entries if e.on))

    def test_exported_elsewhere_and_lines_that_differ_from_the_table(self):
        text = E.write(self.session.state, 6, 48000.0)
        lines = text.splitlines()
        i = next(n for n, l in enumerate(lines) if l.startswith("Filter 2:"))
        lines[i] = lines[i].replace(" Gain ", " Gain 1").replace("Gain 1-", "Gain -1")
        dialog = self.open(self.file("phones.txt", "\n".join(lines) + "\n"))
        self.assertIn("Exported from Phones 1/2", dialog.status.text())
        self.assertIn("The Filter lines differ from the table; the table is imported", dialog.status.text())
        self.assertTrue(dialog.input.item(i).data(D.MARK_ROLE))
        self.assertEqual(dialog.input.item(i).toolTip(), "Differs from the table")
        self.assertNotIn("The table is incomplete", dialog.status.text())

    def test_a_table_that_does_not_count_is_said(self):
        lines = E.write(self.session.state, 6, 48000.0).splitlines()
        i = next(n for n, l in enumerate(lines) if E.ROW.match(l))
        lines[i] = lines[i].replace(" dB", "x dB")
        dialog = self.open(self.file("phones.txt", "\n".join(lines) + "\n"))
        self.assertIn("The table is incomplete or unreadable; the Filter lines are imported", dialog.status.text())
        row = dialog.input.item(i)                               # the row that does it: amber, and why
        self.assertTrue(row.data(D.MARK_ROLE))
        self.assertEqual(row.toolTip(), "Gain is not a number")
        other = dialog.input.item(i + 1)
        self.assertFalse(other.data(D.MARK_ROLE))
        self.assertEqual(other.toolTip(), "The table does not count; the Filter lines are imported")

    def test_the_output_does_not_change_the_graph(self):
        dialog = self.open(self.file("three.txt", THREE))
        before = [(t.copy(), g.copy()) for t, g in dialog.deviation]
        dialog.toggle_block(1)                                   # EQ Right not to the device
        self.assertEqual(len(dialog.deviation), len(before))
        for (t, g), (t0, g0) in zip(dialog.deviation, before):
            self.assertTrue((t == t0).all() and (g == g0).all())

    def test_the_legend_shows_and_hides(self):
        dialog = self.open(self.file("three.txt", THREE))
        visible = dialog.graph.visible
        dialog.legend.items["bands"].clicked.emit()
        self.assertFalse(visible["bands"])
        dialog.legend.items["L"].double_clicked.emit()            # only the left
        self.assertEqual((visible["L"], visible["R"]), (True, False))
        dialog.legend.items["L"].double_clicked.emit()            # again: both
        self.assertEqual((visible["L"], visible["R"]), (True, True))
        self.assertFalse(dialog.legend.items["BT"].isVisibleTo(dialog))   # no Bass/Treble in the outcome

    def test_the_sample_rate_of_the_file_amber_when_changed(self):
        path = os.path.join(self.dir.name, "line out.txt")
        self.win.export_file(path)
        dialog = self.open(path)
        self.assertEqual(dialog.fs_box.currentData(), int(self.win.graph.fs))
        self.assertIsNone(dialog.fs_box.value_color)
        other = next(r for r in P.SAMPLE_RATES if r != int(self.win.graph.fs))
        dialog.fs_box.setCurrentIndex(dialog.fs_box.findData(other))
        self.assertEqual(dialog.fs_box.value_color, theme.WARN)
        self.assertIn("The file was exported at", dialog.fs_box.toolTip())

    def test_what_the_input_does_not_set(self):
        dialog = self.open(self.file("three.txt", THREE))
        m = dialog.band_models[0]
        band4 = m.index(3, 1)                                    # Band 4, Hz
        self.assertEqual((m.data(band4), m.data(band4, Qt.ToolTipRole)), ("—", "Not set: factory default"))
        self.assertFalse(dialog.bt_corner.box.isChecked())
        dialog.bt_corner.box.click()                             # Bass/Treble to the device: factory default
        self.assertTrue(dialog.bt_corner.box.isChecked())
        self.assertEqual({k: v for k, v in dialog.values.items() if k[1] in P.BASS + P.TREBLE},
                         {(LEFT, i): P.FACTORY_BT[i] for i in P.BASS + P.TREBLE})

    def test_another_file_dropped_on_the_dialog(self):
        self.without_auto_ref_level()
        ten = self.file("ten.txt", TEN_FILTERS)

        def answer(dialog):
            self.asked.append(dialog)
            self.drop_on(dialog, self.file("sound.wav", "RIFF"))  # no filter file: the input stays
            self.assertIn("Not imported: sound.wav is not a filter file or a curve", dialog.status.text())
            self.assertEqual(dialog.mode, D.MAP)
            self.drop_on(dialog, ten)                              # starts again, as that file decides
            self.assertEqual((os.path.normpath(dialog.path), dialog.mode, dialog.file_label.text()),
                             (ten, D.FIT, "ten.txt"))
            self.assertNotIn("not a filter file", dialog.status.text())
            wait_for_fit(dialog)
            dialog.accept()
            return dialog.result() == QDialog.Accepted

        self.win.ask = answer
        self.win.import_file(self.file("three.txt", THREE))
        self.settle()
        self.assertEqual(self.win.file_note.text(), "Imported ten.txt")

    def test_the_dialog_does_not_stay_with_the_window(self):
        for ok in (True, False):                                 # imported, and cancelled
            self.win.ask = lambda dialog, ok=ok: self.answer(dialog, ok)
            self.win.import_file(self.file("three.txt", THREE))
            self.settle()
            self.assertIsNone(self.asked[-1].parent())
            self.assertEqual(self.win.findChildren(D.ImportDialog), [])

    def test_the_dialog_can_be_maximised(self):
        dialog = self.open(self.file("three.txt", THREE))
        self.assertTrue(dialog.windowFlags() & Qt.WindowMaximizeButtonHint)

    def test_the_rate_the_device_runs_at_bold(self):
        path = self.file("three.txt", THREE)
        dialog = D.ImportDialog(E.load(path), path, self.session, OUT, 96000, 48000.0, self.win)
        self.addCleanup(dialog.done, 0)
        bold = {dialog.fs_box.itemData(i): bool(dialog.fs_box.itemData(i, Qt.FontRole))
                for i in range(dialog.fs_box.count())}
        self.assertEqual([r for r, b in bold.items() if b], [96000])
        self.assertEqual(dialog.fs_box.currentData(), 96000)    # no rate in the file: the one it runs at

    def drag(self, *paths):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        pos = QPointF(self.win.rect().center())
        enter = QDragEnterEvent(pos.toPoint(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self.win, enter)
        return enter, QDropEvent(pos, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier), mime

    def test_drop_a_file_to_import_it(self):
        enter, drop, _ = self.drag(self.file("one.txt", "Filter: ON PK Fc 1234 Hz Gain 2 dB Q 1\n"))
        self.assertTrue(enter.isAccepted())
        QApplication.sendEvent(self.win, drop)
        self.assertEqual(self.asked, [])                         # not while the drop is still going on
        self.spin(100)
        self.assertEqual(len(self.asked), 1)
        self.settle()
        self.assertEqual((self.sim.state[(LEFT, 5)], self.sim.state[(LEFT, 4)]), (1234, 4))       # band 1

    def test_drop_only_one_file(self):
        a, b = self.file("a.txt", ""), self.file("b.txt", "")
        enter, _, _ = self.drag(a, b)
        self.assertFalse(enter.isAccepted())
        enter, _, _ = self.drag(self.dir.name)                   # a folder is not a file
        self.assertFalse(enter.isAccepted())

    def test_no_filter_file_only_a_note(self):
        for name, data in (("empty.txt", b""), ("sound.wav", b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00"),
                           ("notes.md", b"# Notes\nDate: 6 October\nSee: http://example.com\n")):
            path = os.path.join(self.dir.name, name)
            with open(path, "wb") as f:
                f.write(data)
            self.win.import_file(path)
            self.assertEqual(self.win.file_note.text(), "Not imported: %s is not a filter file or a curve" % name)
        self.assertEqual(self.asked, [])


def wait_for_fit(dialog, limit=120):
    """A fit runs in a thread of its own, in real time."""
    t0 = time.monotonic()
    QApplication.processEvents()
    while dialog.fitting and time.monotonic() - t0 < limit:
        time.sleep(0.02)
        QApplication.processEvents()


class ProImport(ImportTest):
    """Import into Phones 3/4 of an ADI-2 Pro: its name, and only its EQ is written."""

    model = PRO

    def test_into_phones_3_4(self):
        self.win.tabs.setCurrentIndex(tab(9))
        since = len(self.sim.received)
        self.win.import_file(self.file("three.txt", THREE))
        self.settle()
        dialog = self.asked[0]
        self.assertEqual(dialog.name, "Phones 3/4")
        self.assertEqual([self.sim.state[(10, i)] for i in (5, 4, 6)], [100, 4, 10])      # band 1
        written = {a for m in self.sim.received[since:] if m[5] == 0x02
                   for a, *_ in [codec.decode_triplet(*t) for t in codec.parameter_triplets([m])]}
        self.assertLessEqual(written, {9, 10, 11})


class InputImport(ImportTest):
    """Import into the analog input of an ADI-2/4 Pro: its bands only, without Bass/Treble."""

    model = PRO_24

    def setUp(self):
        super().setUp()
        self.session.set((LEFT, P.BASS[0]), 6)                            # Line Out's Bass, in its file
        for i, v in ((4, 4), (5, 250), (7, -6), (8, 1200)):                # bands 1 and 2
            self.session.set((LEFT, i), v)
        self.settle()
        self.line_out = self.file("line.txt", E.write(self.session.state, OUT, 48000.0, model=PRO_24))
        self.win.tabs.setCurrentIndex(tab(0))

    def test_the_bands_of_a_file_without_its_bass_treble(self):
        def check(dialog):
            usable, why = dialog.usable()
            self.assertEqual((dialog.name, dialog.has_bt, dialog.mode), ("Analog In", False, D.MAP))
            self.assertEqual(list(why.values()).count("Analog In has no Bass/Treble"), 2)
            self.assertFalse(any(i.target in ("Bass", "Treble") for i in usable.values()))
            self.assertFalse(dialog.bt_view.isVisible())
            self.assertNotIn("BT", dialog.blocks())
            dialog.set_mode(D.FIT)
            self.assertFalse(dialog.tone_box.isVisible())
            dialog.set_mode(D.MAP)
        self.check = check
        since = len(self.sim.received)
        self.win.import_file(self.line_out)
        self.settle()
        self.assertEqual([self.sim.state[(1, i)] for i in range(3, 20)],
                         [self.sim.state[(LEFT, i)] for i in range(3, 20)])
        self.assertEqual([k for k in self.sim.state if k[0] == 1 and 20 <= k[1] <= 26], [])
        written = {a for m in self.sim.received[since:] if m[5] == 0x02
                   for a, *_ in [codec.decode_triplet(*t) for t in codec.parameter_triplets([m])]}
        self.assertLessEqual(written, {1, 2})


if __name__ == "__main__":
    import unittest
    unittest.main()
