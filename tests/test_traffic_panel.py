"""The MIDI traffic panel in the window: how it opens and closes, which rows it shows, and what Copy, Save and
Clear take."""

import os
import tempfile
from unittest import mock

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from commander.ui import traffic as T
from commander.ui.window import TRAFFIC_WIDTH, MainWindow
from tests.gui import WindowTest

A = bytes([0xF0, 0x00, 0x20, 0x0D, 0x71, 0x05, 0x01, 0x41, 0x00, 0xF7])
MERGED = A + A[:6]                                           # one message and the start of the next


def left(widget):
    return widget.mapToGlobal(QPoint(0, 0)).x()


def right(widget):
    """Where the widget ends: the first pixel after it."""
    return left(widget) + widget.width()


class Panel(WindowTest):
    def setUp(self):
        super().setUp()
        self.panel = self.win.traffic_panel

    def open(self):
        QTest.mouseClick(self.win.lamp, Qt.LeftButton, Qt.ControlModifier)
        self.spin(20)

    def type_filter(self, text):
        """Type text into the filter and let it apply, a moment after the last key."""
        self.panel.filter.setText(text)
        while self.panel.typed.isActive():
            QTest.qWait(20)

    def rows(self):
        self.panel.model.flush()
        return list(self.panel.model.rows)

    def test_ctrl_click_on_the_light_opens_it_first_of_the_panels(self):
        self.win.presets_tab.set_open(True)
        QTest.mouseClick(self.win.lamp, Qt.LeftButton)
        self.spin(20)
        self.assertTrue(self.win.traffic_tab.isHidden() and self.win.traffic_area.isHidden())
        self.open()
        self.assertFalse(self.win.traffic_tab.isHidden() or self.win.traffic_area.isHidden())
        self.assertLess(left(self.panel), left(self.win.presets_area))

    def test_the_first_open_panel_as_far_from_the_tabs_with_it_or_without(self):
        gap = self.win.side_row.spacing()
        tabs = self.win.input_tab
        self.win.input_tab.set_open(True)
        self.spin(20)
        self.assertEqual(left(self.win.input_area) - right(tabs), gap)
        self.open()
        self.assertEqual(left(self.panel) - right(tabs), gap)
        self.assertEqual(left(self.win.traffic_grip), right(self.panel))           # the grip against its edge
        QTest.mouseClick(self.win.traffic_tab, Qt.LeftButton)
        self.spin(20)
        self.assertEqual(left(self.win.input_area) - right(tabs), gap)

    def test_closing_hides_its_tab(self):
        self.open()
        QTest.mouseClick(self.win.traffic_tab, Qt.LeftButton)
        self.assertTrue(self.win.traffic_tab.isHidden() and self.win.traffic_area.isHidden())

    def test_ctrl_shift_t_opens_and_closes(self):
        QTest.keyClick(self.win, Qt.Key_T, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertFalse(self.win.traffic_area.isHidden())
        QTest.keyClick(self.win, Qt.Key_T, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertTrue(self.win.traffic_tab.isHidden() and self.win.traffic_area.isHidden())

    def test_everything_recorded_also_before_it_opened(self):
        self.open()
        self.assertEqual(self.rows(), list(self.session.traffic.entries))
        self.assertEqual(self.rows()[0].kind, "port")                       # opened
        before = len(self.rows())
        self.spin(1000)
        self.assertGreater(len(self.rows()), before)

    def test_which_rows(self):
        self.session.traffic.add("in", MERGED)
        self.open()
        for i, kinds in ((1, {"out"}), (2, {"in"}), (3, {"port"}), (0, {"out", "in", "port"})):
            self.panel.shown._clicked(i)
            self.assertEqual({e.kind for e in self.rows()}, kinds)
        self.panel.shown._clicked(4)
        self.assertEqual([e.data for e in self.rows()], [MERGED])

    def test_filter_shows_or_hides_rows_with_any_of_its_terms(self):
        self.open()
        self.type_filter("71 07, opened")
        self.assertTrue(self.rows())
        self.assertTrue(all(b"\x71\x07" in e.data if e.kind != "port" else "opened" in e.data for e in self.rows()))
        self.panel.way._clicked(1)
        self.assertTrue(self.rows())
        self.assertFalse(any(b"\x71\x07" in e.data if e.kind != "port" else "opened" in e.data
                             for e in self.rows()))

    def test_filter_finds_the_time_and_the_bytes_as_ascii(self):
        self.session.traffic.add("in", A)
        self.open()
        self.type_filter("·q··A")                             # 05 01 41: · is a byte without a character
        self.assertEqual([e.data for e in self.rows()], [A])
        self.type_filter(T.clock(self.rows()[0].t))
        self.assertIn(A, [e.data for e in self.rows()])

    def test_pause_holds_the_list_and_resume_follows_again(self):
        self.open()
        QTest.mouseClick(self.panel.pause, Qt.LeftButton)
        held = len(self.rows())
        self.spin(1000)
        self.assertEqual((len(self.rows()), self.panel.pause.text()), (held, "Resume"))
        QTest.mouseClick(self.panel.pause, Qt.LeftButton)
        self.assertEqual(self.rows(), list(self.session.traffic.entries))
        self.assertEqual(self.panel.pause.text(), "Pause")

    def test_clear_deletes_the_recording(self):
        self.open()
        QTest.mouseClick(self.panel.clear, Qt.LeftButton)
        self.assertEqual((self.rows(), list(self.session.traffic.entries)), ([], []))

    def test_copy_takes_the_selection_or_all_rows_shown(self):
        self.session.traffic.add("in", MERGED)
        self.open()
        self.panel.shown._clicked(4)
        QTest.mouseClick(self.panel.copy, Qt.LeftButton)
        clock = T.clock(self.rows()[0].t)
        self.assertEqual(QApplication.clipboard().text(),
                         "%s  ←  %s  [f0 at 10 without f7; 2 × f0]\n" % (clock, T.hex_bytes(MERGED)))
        self.panel.shown._clicked(0)
        self.panel.view.selectRow(0)
        QTest.mouseClick(self.panel.copy, Qt.LeftButton)
        self.assertEqual(QApplication.clipboard().text(), self.panel.model.line(self.rows()[0]) + "\n")

    def test_save_writes_a_head_and_a_line_per_row(self):
        self.open()
        self.type_filter("opened")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = os.path.join(folder.name, "midi.txt")
        with mock.patch.object(T.QFileDialog, "getSaveFileName", return_value=(path, "")):
            QTest.mouseClick(self.panel.save, Qt.LeftButton)
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertTrue(lines[0].startswith("ADI-2 Commander "))
        self.assertEqual(lines[-1], self.panel.model.line(self.rows()[0]))
        self.assertEqual(lines[-2], "")

    def test_the_selected_row_in_full(self):
        self.session.traffic.add("in", MERGED)
        e = self.session.traffic.entries[-1]
        self.assertEqual(self.panel.model.detail(e, 8).splitlines(),
                         ["%s  received, 16 bytes" % T.clock(e.t), "",
                          "0000  f0 00 20 0d 71 05 01 41  ·· ·q··A",
                          "0008  00 f7 f0 00 20 0d 71 05  ···· ·q·", "",
                          "f0 at 10 without f7", "2 × f0"])

    def test_serial_numbers_in_port_names(self):
        serials = T.Serials()
        self.assertEqual(serials('opened  in "ADI-2 DAC (12345678)"  out "ADI-2 DAC (12345678)"'),
                         'opened  in "ADI-2 DAC (#1)"  out "ADI-2 DAC (#1)"')
        self.assertEqual(serials("not opened: no ADI-2 MIDI port found (in: ['Fireface (23456789)']; out: [])"),
                         "not opened: no ADI-2 MIDI port found (in: ['Fireface (#2)']; out: [])")
        self.assertEqual(serials('opened  in "ADI-2 DAC (12345678)"'), 'opened  in "ADI-2 DAC (#1)"')
        self.assertEqual(serials("midiInOpen failed (winmm 4, simulated); (simulated)"),
                         "midiInOpen failed (winmm 4, simulated); (simulated)")

    def test_wider_by_its_grip_and_as_wide_the_next_time(self):
        self.open()
        narrow = self.win.PRESETS_WIDTH
        grip = self.win.traffic_grip
        start = grip.rect().center()
        QTest.mousePress(grip, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(grip, start + QPoint(150, 0))
        QTest.mouseRelease(grip, Qt.LeftButton, Qt.NoModifier, start + QPoint(150, 0))
        self.assertEqual(self.panel.width(), narrow + 150)
        self.assertEqual(int(self.settings.value(TRAFFIC_WIDTH)), narrow + 150)
        self.win.widen_traffic(10)
        self.assertEqual(self.panel.width(), narrow)                # no narrower than the other panels
        self.win.widen_traffic(narrow + 150)
        again = MainWindow(self.session, settings=self.settings)
        self.addCleanup(again.close)
        self.assertEqual(again.traffic_panel.width(), narrow + 150)

    def test_as_wide_as_the_screen_allows_and_wider_on_a_larger_one(self):
        self.settings.setValue(TRAFFIC_WIDTH, 5000)                     # made on a larger screen
        self.open()
        self.spin(20)
        self.assertLess(self.panel.width(), 5000)
        self.assertLessEqual(self.win.least_width(), self.room.width())
        self.assertEqual(int(self.settings.value(TRAFFIC_WIDTH)), 5000)
