"""The main window against the simulator, off-screen."""

import math
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QPoint, QPointF, QRect, QSettings, QTimer   # noqa: E402
from PySide6.QtWidgets import QApplication, QToolTip         # noqa: E402

from commander.device import params as P                     # noqa: E402
from commander.device.simulator import SimPort, SimulatedAdi2  # noqa: E402
from commander.session import Session                        # noqa: E402
from commander.ui import collector, theme                    # noqa: E402
from commander.ui import graph as G                          # noqa: E402
from commander.ui.window import MainWindow                   # noqa: E402
from tests.support import DUMP, PRESETS                      # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)
collector.start(app)


def spin(ms):
    """Real time, for scripts that show the window."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()



def tab(out):
    """The index of the tab of the output, or the input, at address out."""
    return P.CHANNELS.index(P.channel(out))


OUTPUT_TABS = [tab(out) for out in P.OUTPUT_ADDRESSES]


def assert_ratio_corner(test, graph, db_title, choose=False):
    """graph.ratio (a RatioCorner): the aspect ratio as the view is, in the tooltip to one decimal, with the hint to
    click when it chooses; the icon near where the lines of the axis titles cross (db_title: the dB axis's), under the
    dB values, left of the frequency values, its ink within the graph."""
    icon, view = graph.ratio.icon, graph.getPlotItem().getViewBox()
    (x0, x1), (y0, y1) = view.viewRange()
    ratio = (y1 - y0) / (x1 - x0) * view.width() / view.height()                # dB as long as one decade
    test.assertAlmostEqual(icon.ratio, ratio, places=9)
    test.assertEqual(icon.toolTip().splitlines(), ["Aspect ratio: %.1f dB/dec" % ratio] + [G.RATIO_HINT] * choose)
    plot = graph.mapFromScene(view.sceneBoundingRect()).boundingRect()
    cross = QPointF(graph.mapFromScene(db_title.sceneBoundingRect().center()).x(),
                    graph.mapFromScene(graph.getPlotItem().getAxis("bottom").label.sceneBoundingRect().center()).y())
    cross += QPointF(G.TITLE_INK, G.TITLE_INK)                                  # where the axis titles cross
    box = icon.geometry()
    mid = QPointF(box.center()) + QPointF(0.5, 0.5)
    corner = QPointF(plot.bottomLeft())
    test.assertLess(math.hypot(*(mid - cross).toTuple()), math.hypot(*(mid - corner).toTuple()) / 2)   # near
    test.assertLess(box.right(), plot.left())                                   # under the dB values
    test.assertGreater(box.top(), plot.bottom())                                # left of the frequency values
    test.assertTrue(graph.rect().contains(box.adjusted(icon.PAD, icon.PAD, -icon.PAD, -icon.PAD)))   # within it


def tooltip_color(widget):
    """The colour of the text of widget's tooltip, as Qt shows it: a widget's style sheet reaches its tooltip."""
    QToolTip.showText(widget.mapToGlobal(QPoint(2, 2)), widget.toolTip(), widget)
    QApplication.processEvents()
    tip = [t for t in QApplication.allWidgets() if t.metaObject().className() == "QTipLabel"][-1]
    tip.ensurePolished()
    color = tip.palette().color(tip.foregroundRole()).name()
    QToolTip.hideText()
    return color


def hover(win, row):
    """The mouse on a row of the presets panel, and kept there: a slot's row, Clear or Rumble opens its preview."""
    win.pointer = lambda: row.mapToGlobal(QPoint(row.width() // 2, row.height() // 2))
    row.enterEvent(None)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class WindowTest(unittest.TestCase):
    """The window on the dump, connected and loaded, on a simulated clock: the test turns it."""

    size = None
    model = None                                 # a models.Model to start from its factory values instead of the dump
    revision = None                              # and its device revision
    room = QRect(0, 0, 1920, 1032)               # MainWindow.room: full HD; offscreen has 800 px
    TICK = 20                                    # ms, as the window's timer

    def setUp(self):
        self.clock = Clock()
        if self.model is None:
            self.sim = SimulatedAdi2.from_dump(DUMP, presets=PRESETS, clock=self.clock)
        else:
            self.sim = SimulatedAdi2.factory(self.model, self.revision, presets=PRESETS, clock=self.clock)
        self.session = Session(lambda: SimPort(self.sim), clock=self.clock)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.settings = QSettings(os.path.join(folder.name, "settings.ini"), QSettings.IniFormat)
        self.win = MainWindow(self.session, settings=self.settings)
        self.dialogs = []                            # what the window asked while it connected: answered OK
        self.win.ask = lambda dialog: self.dialogs.append(dialog) or True
        self.win.room = lambda: self.room
        self.win.timer.setInterval(24 * 3600 * 1000)   # still running while the window talks, but spin ticks
        if self.size:
            self.win.resize(*self.size)
        self.win.show()
        for _ in range(60):
            self.spin(50)
            if self.session.ready():
                break
        self.assertTrue(self.session.ready())

    def tearDown(self):
        self.win.close()
        self.session.close()
        self.assertEqual(self.sim.unsimulated, [])

    def spin(self, ms):
        """Let ms of simulated time pass, ticking as the window's timer would."""
        for _ in range(max(1, round(ms / self.TICK))):
            self.clock.t += self.TICK / 1000
            if self.win.timer.isActive():
                self.win.tick()
            app.processEvents()

    def settle(self, limit=8000):
        """Until everything is written, read back and verified."""
        for _ in range(limit // 100):
            self.spin(100)
            if not (self.session.pending or self.session.sent):
                break
        self.assertFalse(self.session.pending or self.session.sent)
