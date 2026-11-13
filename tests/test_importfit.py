"""Import by Fit: OK waits for the fit, Cancel and Close enough while it runs, converting again, the sum as the device
makes it with the input moved onto it, garbage collection while it runs, and a curve."""

import gc
import time

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from commander.conversion import eqfile as E
from commander.conversion import eqfit as X
from commander.conversion import eqimport as I
from commander.device import filters as F
from commander.device import params as P
from commander.ui import importdialog as D
from commander.ui import theme
from tests.support import TEN_FILTERS
from tests.test_importexport import OUT, THREE, ImportTest, wait_for_fit

FREQS = F.FREQS
PEAK = X.response([X.Setting("3", "PK", 1000, 4.0, 0.7)], 48000.0)    # one the device makes: a quick fit


def table(columns, freqs=FREQS):
    """A curve as a table: the frequency, then per column {name: dB per frequency}."""
    lines = [",".join(["frequency"] + list(columns))]
    for k, f in enumerate(freqs):
        lines.append(",".join(["%.2f" % f] + ["%.2f" % c[k] for c in columns.values()]))
    return "\n".join(lines) + "\n"


class ImportFit(ImportTest):
    def setUp(self):
        super().setUp()
        self.without_auto_ref_level()

    def test_any_other_file_fits_and_ok_waits_for_it(self):
        def check(dialog):
            self.assertEqual(dialog.mode, D.FIT)
            self.assertFalse(dialog.fitting)
            self.assertIn("Fitted", dialog.status.text())
            self.assertTrue(dialog.ok.isEnabled())

        self.win.ask = self.answer
        self.check = check
        path = self.file("ten.txt", TEN_FILTERS)
        eq = E.load(path)
        dialog = D.ImportDialog(eq, path, self.session, OUT, None, 48000.0, self.win)
        self.assertTrue(dialog.fitting)
        self.assertFalse(dialog.ok.isEnabled())                  # not while the fit runs
        dialog.done(0)
        self.win.import_file(path)
        self.settle()
        values = self.asked[0].values
        self.assertTrue(values)
        self.assertEqual({k: self.sim.state[k] for k in values}, values)

    def test_cancel_during_a_fit_writes_nothing(self):
        before = dict(self.sim.state)
        path = self.file("ten.txt", TEN_FILTERS)
        dialog = D.ImportDialog(E.load(path), path, self.session, OUT, None, 48000.0, self.win)
        QApplication.processEvents()
        dialog.reject()
        self.assertEqual(dialog.threads, [])
        self.spin(300)
        self.assertEqual(self.sim.state, before)

    def test_good_enough_takes_the_best_so_far_on_the_grid(self):
        path = self.file("ten.txt", TEN_FILTERS)
        dialog = D.ImportDialog(E.load(path), path, self.session, OUT, None, 48000.0, self.win)
        self.addCleanup(dialog.done, 0)
        t0 = time.monotonic()
        while not dialog.enough.isEnabled() and time.monotonic() - t0 < 60:
            time.sleep(0.02)
            QApplication.processEvents()
        self.assertTrue(dialog.fitting)
        self.assertTrue(dialog.legend.items["candidate"].isVisibleTo(dialog))   # what it tries: while it fits
        bar = dialog.progress.parentWidget()
        self.assertEqual(bar.minimumHeight(), bar.maximumHeight())             # as high while fitting as not
        self.assertIs(dialog.enough.parentWidget(), dialog.again.parentWidget())    # beside convert again
        dialog.enough.click()
        self.assertFalse(dialog.fitting)
        self.assertTrue(dialog.ok.isEnabled())
        self.assertTrue(dialog.enough.isVisibleTo(dialog))                      # stays, so the row stays put
        self.assertFalse(dialog.enough.isEnabled())
        self.assertFalse(dialog.legend.items["candidate"].isVisibleTo(dialog))
        freqs = {k: v for k, v in dialog.values.items() if k[1] in (5, 8, 11, 14, 18)}
        self.assertEqual({k: P.snap_freq(v, k[1]) for k, v in freqs.items()}, freqs)

    def test_convert_again(self):
        dialog = self.open(self.file("three.txt", THREE))
        before = dict(dialog.values)
        dialog.again.click()                                     # Map: the same plan again
        self.assertEqual(dialog.values, before)
        dialog.way.buttons[D.FIT].click()
        wait_for_fit(dialog)
        dialog.again.click()                                     # Fit: it fits again, to the same end
        self.assertTrue(dialog.fitting)
        wait_for_fit(dialog)
        self.assertTrue(dialog.ok.isEnabled())

    def test_a_curve_fits_and_ok_writes(self):
        def check(dialog):
            self.assertEqual(dialog.mode, D.FIT)
            self.assertIn("Fitted", dialog.status.text())

        self.check = check
        self.win.import_file(self.file("curve.csv", table({"eq": PEAK})))
        self.settle()
        self.assertEqual(self.win.file_note.text(), "Imported curve.csv")
        values = self.asked[0].values
        self.assertTrue(values)
        self.assertEqual({k: self.sim.state[k] for k in values}, values)

    def test_a_curve_its_summary_and_its_column(self):
        dialog = self.open(self.file("curve.csv", table({"spl": 75.0 + PEAK, "a": PEAK, "eq": -PEAK})))
        s = dialog.summary
        self.assertIs(dialog.input_stack.currentWidget(), s)
        self.assertFalse(dialog.way.buttons[D.MAP].isEnabled())  # no filters to map
        self.assertTrue(dialog.origin_group.isHidden())
        self.assertEqual([s.values[r].text() for r in ("Points", "Frequency", "Gain", "Comments")],
                         ["241", "20 Hz – 20 kHz", "-4.0 … +0.0 dB", "None"])
        self.assertEqual((s.choice.currentText(), dialog.column), ("eq", 2))     # the name starting with "eq"
        spl = s.choice.model().item(0)
        self.assertEqual((spl.isEnabled(), s.choice.itemData(0, Qt.ToolTipRole)), (False, "Beyond ±15 dB"))
        self.assertIn("Fitted", dialog.status.text())
        s.choice.setCurrentIndex(1)                              # another column: fitted again
        self.assertEqual(dialog.column, 1)
        self.assertTrue(dialog.fitting)
        self.assertEqual(s.values["Gain"].text(), "+0.0 … +4.0 dB")
        wait_for_fit(dialog)
        self.assertIn("Fitted", dialog.status.text())
        self.assertTrue(dialog.ok.isEnabled())

    def test_a_curve_without_a_column_that_can_serve(self):
        inner = (FREQS >= 100) & (FREQS <= 10000)
        dialog = self.open(self.file("measured.txt", "# measured\n" + table(
            {"spl": 75.0 + PEAK[inner], "phase": 170 * np.sin(np.log(FREQS[inner]))}, FREQS[inner])))
        s = dialog.summary
        self.assertEqual((s.choice.currentIndex(), s.choice.placeholderText(), s.choice.value_color),
                         (-1, "None", theme.WARN))
        self.assertIn("within ±15 dB", s.choice.toolTip())
        self.assertIn(theme.WARN.name(), s.values["Frequency"].styleSheet())   # not all of 20 Hz - 20 kHz
        self.assertEqual(s.values["Comments"].text(), "# measured")
        self.assertIn("Nothing to import", dialog.status.text())
        self.assertFalse(dialog.ok.isEnabled())

    def test_a_curve_dropped_on_the_dialog_and_a_filter_file_back(self):
        three, curve = self.file("three.txt", THREE), self.file("curve.csv", table({"eq": PEAK}))
        dialog = self.open(three)
        self.drop_on(dialog, curve)
        self.assertEqual((dialog.mode, dialog.file_label.text()), (D.FIT, "curve.csv"))
        self.assertIs(dialog.input_stack.currentWidget(), dialog.summary)
        self.assertTrue(dialog.origin_group.isHidden())
        self.drop_on(dialog, three)                              # during the fit
        self.assertEqual((dialog.mode, dialog.fitting), (D.MAP, False))
        self.assertIs(dialog.input_stack.currentWidget(), dialog.input)
        self.assertFalse(dialog.origin_group.isHidden())
        self.assertTrue(dialog.way.buttons[D.MAP].isEnabled())
        self.assertIn("Mapped", dialog.status.text())

    def test_no_garbage_collection_in_a_fits_thread(self):
        path = self.file("ten.txt", TEN_FILTERS)
        dialog = D.ImportDialog(E.load(path), path, self.session, OUT, None, 48000.0, self.win)
        QApplication.processEvents()                             # the fit starts
        self.assertTrue(dialog.fitting)
        self.assertFalse(gc.isenabled())                         # the GUI thread collects, on a timer
        wait_for_fit(dialog)
        dialog.done(0)

    def test_the_sum_as_the_device_makes_it_the_input_moved_onto_it(self):
        dialog = self.open(self.file("ten.txt", TEN_FILTERS))
        key, _, shown, total, bands, _ = dialog.graph.channels[0]
        block = dialog.eq_blocks()[0]
        level = dialog.levels[block]
        given = dialog.summed(dialog.groups[block] + I.tone_items(dialog.chosen), dialog.graph.freqs())
        np.testing.assert_allclose(total, sum(b[0] for b in bands))
        np.testing.assert_allclose(shown, given + level)
        self.assertEqual(dialog.legend.items["input"].name.text(), D._adjusted({key: level})[0])

    def test_the_input_named_when_a_fit_moved_it(self):
        self.assertEqual(D._adjusted({"L": 0.04, "R": -0.04}), ("Input", ""))
        self.assertEqual(D._adjusted({"L": -1.02}),
                         ("Input (adj.)", "Moved -1.0 dB onto the sum: the fit leaves the level free.\n"))
        self.assertEqual(D._adjusted({"L": -1.02, "R": 0.43})[1],
                         "Moved left -1.0 dB, right +0.4 dB onto the sum: the fit leaves the level free.\n")


if __name__ == "__main__":
    import unittest
    unittest.main()
