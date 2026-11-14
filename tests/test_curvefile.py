"""A correction curve as a table: what makes a table, which columns can serve as EQ, and the curve between the
points."""

import os
import tempfile
import unittest

import numpy as np

from commander.conversion import curvefile as C
from commander.device import filters as F

FREQS = np.logspace(np.log10(20), np.log10(20000), 25)


def table(columns, header=None, sep=",", comma=False, freqs=FREQS, before=()):
    """A table as text: freqs and one value per column and frequency, from columns {name: f(freq)}."""
    def cell(x):
        s = "%.2f" % x
        return s.replace(".", ",") if comma else s
    lines = list(before)
    if header:
        lines.append(sep.join(["frequency"] + list(columns)))
    for f in freqs:
        lines.append(sep.join([cell(f)] + [cell(v(f)) for v in columns.values()]))
    return "\n".join(lines) + "\n"


def bump(f):
    return 4.0 * np.exp(-np.log(f / 1000.0) ** 2)


class Reading(unittest.TestCase):
    def test_comma_separated_with_a_header(self):
        cf = C.read(table({"measured": lambda f: 75.0 + bump(f), "off": bump, "eq": lambda f: -bump(f)}, header=True))
        self.assertEqual(cf.names, ["measured", "off", "eq"])
        self.assertEqual(len(cf.freqs), len(FREQS))
        np.testing.assert_allclose(cf.columns[2], [-round(bump(f), 2) for f in FREQS], atol=1e-9)

    def test_separators(self):
        for sep, comma in ((";", True), ("\t", True), (";", False), ("\t", False), (" ", False), ("  ", False)):
            with self.subTest(sep=repr(sep), comma=comma):
                cf = C.read(table({"a": bump}, sep=sep, comma=comma))
                np.testing.assert_allclose(cf.freqs, [round(f, 2) for f in FREQS])
                np.testing.assert_allclose(cf.columns[0], [round(bump(f), 2) for f in FREQS], atol=1e-9)

    def test_without_a_header_the_columns_are_numbered(self):
        cf = C.read(table({"a": bump, "b": bump}))
        self.assertEqual(cf.names, ["Column 2", "Column 3"])

    def test_comments_are_kept(self):
        before = ["* Measurement", "# made somewhere", "; another", "// and one more"]
        cf = C.read(table({"a": bump}, header=True, before=before))
        self.assertEqual(cf.comments, before)
        self.assertEqual(cf.names, ["a"])

    def test_a_quoted_header(self):
        cf = C.read('"Freq","dB"\n' + table({"a": bump}))
        self.assertEqual(cf.names, ["dB"])

    def test_rows_below_1_hz_are_left_out(self):
        cf = C.read(table({"a": bump}, freqs=np.r_[0.0, 0.5, FREQS]))
        np.testing.assert_allclose(cf.freqs, [round(f, 2) for f in FREQS])
        self.assertIsNone(C.read(table({"a": bump}, freqs=np.r_[0.0, FREQS[:C.MIN_ROWS - 1]])))

    def test_load_reads_the_file(self):
        for encoding in ("utf-8-sig", "utf-16"):
            with self.subTest(encoding), tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "curve.txt")
                with open(path, "w", encoding=encoding) as f:
                    f.write(table({"a": bump}, header=True, sep="\t", comma=True))
                self.assertEqual(C.load(path).names, ["a"])


class NotATable(unittest.TestCase):
    def test_not_a_table(self):
        cases = {
            "a filter file": "Preamp: -3 dB\nFilter 1: ON PK Fc 100 Hz Gain 3 dB Q 1\n" * 10,
            "too few rows": table({"a": bump}, freqs=FREQS[:C.MIN_ROWS - 1]),
            "frequency not rising": table({"a": bump}, freqs=FREQS[::-1]),
            "frequency above 100 kHz": table({"a": bump}, freqs=np.r_[FREQS, 200000.0]),
            "two headers": "x,y\n" + table({"a": bump}, header=True),
            "rows of different width": table({"a": bump}) + "30000,1,2\n",
            "only a frequency": table({}),
            "no number beside the frequency": "".join("%g,x\n" % f for f in FREQS),
            "empty": "",
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.assertIsNone(C.read(text))


class Columns(unittest.TestCase):
    def test_a_column_serves_when_its_data_can(self):
        cf = C.read(table({"spl": lambda f: 75.0 + bump(f), "phase": lambda f: 170 * np.sin(np.log(f)),
                           "deep": lambda f: -16.0 * bump(f) / 4.0, "edge": lambda f: 15.0 * bump(f) / 4.0,
                           "curve": bump}, header=True))
        self.assertEqual([cf.names[i] for i in cf.usable], ["edge", "curve"])

    def test_a_cell_that_is_not_a_number(self):
        text = table({"a": bump, "b": bump}, header=True)
        lines = text.splitlines()
        lines[5] = lines[5].rsplit(",", 1)[0] + ","
        cf = C.read("\n".join(lines))
        self.assertEqual(cf.usable, [0])

    def test_the_proposal(self):
        cases = (({"measured": bump, "off": bump, "equaliser": bump}, "equaliser"),
                 ({"a": bump, "EQ": bump}, "EQ"),
                 ({"a": bump, "b": bump}, "a"),
                 ({"eq": lambda f: 20.0 + bump(f), "b": bump}, "b"))
        for columns, chosen in cases:
            with self.subTest(chosen):
                cf = C.read(table(columns, header=True))
                self.assertEqual(cf.names[cf.chosen], chosen)

    def test_why_a_column_cannot_serve(self):
        text = table({"spl": lambda f: 75.0 + bump(f), "curve": bump, "gap": bump}, header=True)
        lines = text.splitlines()
        lines[5] = lines[5].rsplit(",", 1)[0] + ","
        cf = C.read("\n".join(lines))
        self.assertEqual([C.unusable(cf, i) for i in range(3)], ["Beyond ±15 dB", None, "A cell is not a number."])

    def test_no_column_can_serve(self):
        cf = C.read(table({"spl": lambda f: 75.0 + bump(f)}, header=True))
        self.assertEqual((cf.usable, cf.chosen), ([], None))


class Curve(unittest.TestCase):
    def test_between_the_points_straight_over_log_f(self):
        cf = C.read("\n".join("%g,%g" % (f, g) for f, g in
                              zip(np.logspace(1, 4, 13), np.arange(13.0) - 6)))
        np.testing.assert_allclose(C.curve(cf, 0, np.array([10 * 10 ** 0.125, 100.0])), [-5.5, -2.0])

    def test_beyond_the_points_the_first_and_last_value(self):
        cf = C.read(table({"a": lambda f: np.log10(f)}, freqs=np.logspace(2, 3, 11)))
        y = C.curve(cf, 0)
        self.assertTrue(np.all(y[F.FREQS <= 100] == 2.0))
        self.assertTrue(np.all(y[F.FREQS >= 1000] == 3.0))
        self.assertEqual(len(y), len(F.FREQS))

    def test_centred_on_0_db_where_the_table_spans(self):
        cf = C.read(table({"a": lambda f: 5.0 + np.log10(f)}, freqs=np.logspace(2, 3, 11)))
        inside = (F.FREQS >= 100) & (F.FREQS <= 1000)
        self.assertAlmostEqual(C.level(cf, 0), float(C.curve(cf, 0)[inside].mean()))
        y = C.centred(cf, 0)
        self.assertAlmostEqual(float(y[inside].mean()), 0.0)
        np.testing.assert_allclose(y, C.curve(cf, 0) - C.level(cf, 0))


if __name__ == "__main__":
    unittest.main()
