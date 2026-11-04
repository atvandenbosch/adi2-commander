"""Start ADI-2 Commander.

    pythonw Commander.pyw                 the real device
    pythonw Commander.pyw --simulate      a simulated device, started from the demo
    pythonw Commander.pyw --simulate DUMP a simulated device, started from DUMP
"""

import argparse
import ctypes
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .device.connection import WinmmPort, warm_up
from .device.simulator import DEMO_DUMP, DEMO_PRESETS, SimPort, SimulatedAdi2
from .session import Session
from .ui import collector, theme
from .ui.widgets import show_on_screen
from .ui.window import MainWindow

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "ui", "icon.ico")
SIMULATED_ICON = os.path.join(HERE, "ui", "icon-simulated.ico")    # the same in greys, light
# Its own taskbar identity, so Windows shows this icon, not Python's. The Start menu shortcuts carry the same
# identity (installer/Commander.iss): pinned, the running window then shares the pinned button.
APP_ID = "ADI2Commander"
SIMULATED_APP_ID = APP_ID + ".Simulated"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="Commander")
    ap.add_argument("--simulate", nargs="?", const=DEMO_DUMP, metavar="DUMP",
                    help="use a simulated device, started from a dump file")
    args = ap.parse_args(argv)

    if args.simulate:
        sim = SimulatedAdi2.from_dump(args.simulate, presets=DEMO_PRESETS)
        open_port = lambda: SimPort(sim)                       # noqa: E731
    else:
        sim = None
        open_port = WinmmPort
        warm_up()                                              # while the window is built

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID if sim is None else SIMULATED_APP_ID)
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(QIcon(ICON if sim is None else SIMULATED_ICON))
    theme.apply(app)
    collector.start(app)
    session = Session(open_port)
    win = MainWindow(session)
    if sim is not None:
        win.setWindowTitle(win.windowTitle() + "  —  SIMULATED DEVICE")
        win.simulator = sim
    show_on_screen(win, win.sizeHint(), app.primaryScreen())
    code = app.exec()
    session.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
