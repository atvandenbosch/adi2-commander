"""The main window against the simulator, off-screen."""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QPoint, QRect, QSettings, QTimer   # noqa: E402
from PySide6.QtWidgets import QApplication, QToolTip         # noqa: E402

from commander.device import params as P                     # noqa: E402
from commander.device.simulator import SimPort, SimulatedAdi2  # noqa: E402
from commander.session import Session                        # noqa: E402
from commander.ui import collector, theme                    # noqa: E402
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
