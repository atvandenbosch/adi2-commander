"""Draw the app icons and write commander/ui/icon.ico and icon-simulated.ico (16-256 px).

A dark rounded tile with two well-known target curves on one dB scale: the Harman in-ear
target in the right channel's colour, over the Harman in-room loudspeaker target in the left channel's, each
lightly filled to 0 dB, on a grid of decades and 5 dB steps. Up to 32 px the tile fills the image and the
lines are set in pixels at 16 px rather than scaled down from 256. The simulator's icon is the same drawing in
greys and the other way round: a light tile, dark lines, the in-room curve a little lighter than the in-ear one
so that the two stay apart.

    python tools/make_icon.py
"""

import math
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from commander.ui.theme import LEFT, RIGHT                   # noqa: E402

OUT = os.path.join(ROOT, "commander", "ui")
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
SMALL = 32                                                   # up to here: the full tile, lines in px at 16
GRID_FROM = 24
DB_LARGE, DB_SMALL = (17.0, 13.5), (21.5, 18.5)              # dB above and below 0 on the scale

# (Hz, dB): the Harman targets, approximately
IN_EAR = [(20, 7.7), (30, 7.7), (40, 7.3), (60, 5.5), (100, 3), (150, 0.5), (200, -1), (300, -1.6), (500, -1.4),
          (800, -0.6), (1000, 0), (1500, 2.5), (2000, 6), (2500, 8.4), (3000, 9.4), (3500, 9.6), (4000, 9.3),
          (5000, 8.0), (6000, 6.3), (8000, 3), (10000, 0), (12000, -3), (15000, -8), (18000, -14), (20000, -18)]
IN_ROOM = [(20, 5.4), (30, 5.4), (40, 5.2), (50, 4.9), (60, 4.5), (80, 3.7), (100, 2.8), (150, 1.2), (200, 0.2),
           (300, -0.3), (500, -0.6), (1000, -1.0), (2000, -1.4), (5000, -2.0), (10000, -2.6), (20000, -3.5)]


def curve(points):
    """dB over 0..1 (20 Hz to 20 kHz, log): straight between the points, then lightly smoothed."""
    xs = [math.log10(f / 20) / 3 for f, _ in points]
    ys = [db for _, db in points]

    def linear(x):
        x = min(max(x, xs[0]), xs[-1])
        for i in range(len(xs) - 1):
            if x <= xs[i + 1]:
                return ys[i] + (x - xs[i]) / (xs[i + 1] - xs[i]) * (ys[i + 1] - ys[i])
        return ys[-1]
    kernel = [(j * 0.02 / 6, math.exp(-(j / 6) ** 2 * 2)) for j in range(-12, 13)]
    total = sum(w for _, w in kernel)
    return lambda x: sum(w * linear(x + d) for d, w in kernel) / total


# the colours of a tile: its gradient top and bottom, its outline, the grid and 0 dB line (white or black, its
# alpha set where drawn), the in-room curve, the in-ear curve
APP = dict(top="#24272b", bottom="#0d0e0f", outline="#7a8088", ink=(255, 255, 255), in_room=LEFT, in_ear=RIGHT)
SIMULATED = dict(top="#f1f2f3", bottom="#d8dadd", outline="#5f646b", ink=(0, 0, 0), in_room=QColor("#6c7075"),
                 in_ear=QColor("#45484c"))


def draw(size, colors=APP):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0
    if size <= SMALL:
        k = size / 16.0
        tile, radius = QRectF(0.5, 0.5, size - 1, size - 1), 1.5 * k
        margin_x, margin_y, width, zero_width, zero_alpha = 1.0 * k, 1.6 * k, 1.0 * k, 0.45 * k, 80
        db_top, db_bottom = DB_SMALL
    else:
        tile, radius = QRectF(8 * s, 8 * s, 240 * s, 240 * s), 25 * s
        margin_x, margin_y, width, zero_width, zero_alpha = 30 * s, 40 * s, 6.5 * s, 2.5 * s, 60
        db_top, db_bottom = DB_LARGE

    grad = QLinearGradient(0, tile.top(), 0, tile.bottom())
    grad.setColorAt(0, QColor(colors["top"]))
    grad.setColorAt(1, QColor(colors["bottom"]))
    p.setPen(QPen(QColor(colors["outline"]), max(1.0, 3 * s)))
    p.setBrush(grad)
    p.drawRoundedRect(tile, radius, radius)

    left, right = tile.left() + margin_x, tile.right() - margin_x
    top, bottom = tile.top() + margin_y, tile.bottom() - margin_y
    per_db = (bottom - top) / (db_top + db_bottom)
    mid = top + db_top * per_db                                  # 0 dB
    X = lambda x: left + x * (right - left)                      # noqa: E731

    if size >= GRID_FROM:
        clip = QPainterPath()
        clip.addRoundedRect(tile, radius, radius)
        p.setClipPath(clip)
        p.setPen(QPen(QColor(*colors["ink"], 40), max(1.0, 2 * s), Qt.SolidLine, Qt.FlatCap))
        for f in (100, 1000, 10000):
            x = X(math.log10(f / 20) / 3)
            p.drawLine(QPointF(x, top), QPointF(x, bottom))
        for db in [d for d in range(5, 30, 5) if d <= db_top] + [-d for d in range(5, 30, 5) if d <= db_bottom]:
            p.drawLine(QPointF(left, mid - db * per_db), QPointF(right, mid - db * per_db))
        p.setClipping(False)

    p.setPen(QPen(QColor(*colors["ink"], zero_alpha), zero_width, Qt.SolidLine, Qt.FlatCap))
    p.drawLine(QPointF(left, mid), QPointF(right, mid))

    n = 240
    for points, color in ((IN_ROOM, colors["in_room"]), (IN_EAR, colors["in_ear"])):
        f = curve(points)
        pts = [QPointF(X(i / n), mid - f(i / n) * per_db) for i in range(n + 1)]
        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        area = QPainterPath(line)                                # between the curve and 0 dB
        area.lineTo(QPointF(right, mid))
        area.lineTo(QPointF(left, mid))
        area.closeSubpath()
        fill = QColor(color)
        fill.setAlpha(25)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(area)
        p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(line)
    p.end()
    return img


def png_bytes(img):
    buf = QBuffer()
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path, images):
    """An .ico with PNG-compressed entries, one per size (supported since Windows Vista)."""
    entries = [(img.width(), png_bytes(img)) for img in images]
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory, data = b"", b""
    for size, png in entries:
        wh = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    with open(path, "wb") as f:
        f.write(header + directory + data)


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])   # noqa: F841
    os.makedirs(OUT, exist_ok=True)
    for name, colors in (("icon.ico", APP), ("icon-simulated.ico", SIMULATED)):
        images = [draw(s, colors) for s in SIZES]
        write_ico(os.path.join(OUT, name), images)
        print("written: commander/ui/%s; sizes" % name, SIZES)


if __name__ == "__main__":
    main()
