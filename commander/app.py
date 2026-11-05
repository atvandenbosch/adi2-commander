"""Start ADI-2 Commander.

    pythonw Commander.pyw                 the real device
    pythonw Commander.pyw --simulate      a simulated device, started from the demo
    pythonw Commander.pyw --simulate DUMP a simulated device, started from DUMP
    --model pro|24se|24ex                 with --simulate: an ADI-2 Pro, ADI-2/4 Pro SE or EX instead of the
                                          ADI-2 DAC FS,
                                          without DUMP as it leaves the factory
"""

import argparse
import ctypes
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .device import models
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
# --model: the model and the device revision it reports
SIMULATED_MODELS = {"dac": (models.DAC, None), "pro": (models.PRO, None), "24se": (models.PRO_24, 0),
                    "24ex": (models.PRO_24, 1)}


def simulator(dump, model):
    """The simulated device of --simulate [DUMP] --model MODEL."""
    model, revision = SIMULATED_MODELS[model]
    if dump is None and model is models.DAC:
        dump = DEMO_DUMP
    if dump is None:
        return SimulatedAdi2.factory(model, revision, presets=DEMO_PRESETS)
    return SimulatedAdi2.from_dump(dump, presets=DEMO_PRESETS, model=model, revision=revision)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="Commander")
    ap.add_argument("--simulate", nargs="?", const="", metavar="DUMP",
                    help="use a simulated device, started from a dump file")
    ap.add_argument("--model", choices=SIMULATED_MODELS, help="the simulated model (default: dac)")
    args = ap.parse_args(argv)
    if args.model and args.simulate is None:
        ap.error("--model needs --simulate")

    if args.simulate is not None:
        sim = simulator(args.simulate or None, args.model or "dac")
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
