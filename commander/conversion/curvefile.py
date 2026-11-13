"""A correction curve as a table: the frequency in the first column, curves in dB beside it.

A table is read for what it holds: a column can serve as EQ when its data can, whatever it is called. A curve is
a correction, carried out as it stands; its level does not matter (a fit has a free level).

What makes a table: after comment lines and at most one header, at least MIN_ROWS rows of numbers, split by a
semicolon, a tab, a comma or spaces; the first column a rising frequency within FREQ_RANGE. A decimal comma only with
a semicolon or a tab. Rows below FREQ_RANGE are left out (a linear export starts at 0 Hz).
"""

import math

import numpy as np

from . import eqfile as E
from ..device import filters as F

COMMENT = ("#", "*", ";", "//")
SEPARATORS = (";", "\t", ",", None)              # None: spaces
DECIMAL_COMMA = (";", "\t")
MIN_ROWS = 10
FREQ_RANGE = (1.0, 100000.0)
RANGE_DB = 15.0                                  # the fixed scale of the graphs: a curve lies within it


class CurveFile:
    def __init__(self):
        self.lines = []                   # the text, line by line
        self.comments = []                # the comment lines, as written
        self.names = []                   # per column after the frequency: from the header, else "Column n"
        self.freqs = None                 # Hz, rising
        self.columns = []                 # per column after the frequency: dB, NaN where a cell is not a number
        self.usable = []                  # the columns that can serve as EQ, as indices
        self.chosen = None                # the one proposed, or None when none can


def load(path):
    return read(E.text(path))


def read(text):
    """The table in a text as a CurveFile, or None when the text is not a table."""
    lines = text.splitlines()
    body = [s for s in (l.strip() for l in lines) if s and not s.startswith(COMMENT)]
    found = next((r for r in (_rows(body, sep) for sep in SEPARATORS) if r is not None), None)
    if found is None:
        return None
    header, data = found
    data = [r for r in data if r[0] >= FREQ_RANGE[0]]
    if len(data) < MIN_ROWS:
        return None
    freqs = np.array([r[0] for r in data])
    if np.any(np.diff(freqs) <= 0) or freqs[-1] > FREQ_RANGE[1]:
        return None
    cf = CurveFile()
    cf.lines = lines
    cf.comments = [s for s in (l.strip() for l in lines) if s.startswith(COMMENT)]
    cf.freqs = freqs
    given = header[1:] if header else []
    for i in range(1, len(data[0])):
        cf.names.append(given[i - 1] if i - 1 < len(given) and given[i - 1] else "Column %d" % (i + 1))
        cf.columns.append(np.array([np.nan if r[i] is None else r[i] for r in data]))
    cf.usable = [i for i in range(len(cf.columns)) if unusable(cf, i) is None]
    eq = [i for i in cf.usable if cf.names[i].lower().startswith("eq")]
    cf.chosen = (eq or cf.usable or [None])[0]
    return cf


def unusable(cf, column):
    """Why a column cannot serve as EQ, or None when it can."""
    v = cf.columns[column]
    if not np.all(np.isfinite(v)):
        return "A cell is not a number."
    if np.any(np.abs(v) > RANGE_DB):
        return "Beyond ±%g dB" % RANGE_DB
    return None


def curve(cf, column, freqs=F.FREQS):
    """A column at freqs: straight in dB over log f between the points, the first and last value beyond them."""
    return np.interp(np.log(freqs), np.log(cf.freqs), cf.columns[column])


def _rows(body, sep):
    """(header or None, rows of numbers or None per cell) when the lines split by sep make a table, else None."""
    cells = [[c.strip().strip('"') for c in (s.split(sep) if sep else s.split())] for s in body]
    header = cells[0] if cells and _number(cells[0][0], sep) is None else None
    data = cells[1:] if header else cells
    if len(data) < MIN_ROWS or len({len(r) for r in data}) != 1 or len(data[0]) < 2:
        return None
    rows = [[_number(c, sep) for c in r] for r in data]
    if any(r[0] is None or all(x is None for x in r[1:]) for r in rows):
        return None
    return header, rows


def _number(cell, sep):
    if sep in DECIMAL_COMMA:
        cell = cell.replace(",", ".")
    try:
        x = float(cell)
    except ValueError:
        return None
    return x if math.isfinite(x) else None
