"""Start ADI-2 Commander.

    pythonw Commander.pyw                 the real device
    pythonw Commander.pyw --simulate      a simulated device, of the model chosen in a dialog: the ADI-2 DAC FS
                                          started from the demo, another model as it leaves the factory
    pythonw Commander.pyw --simulate DUMP a simulated device, started from DUMP: an ADI-2 DAC FS unless --model
    --model dac|pro|24se|24ex             with --simulate: the ADI-2 DAC FS, ADI-2 Pro, ADI-2/4 Pro SE or EX,
                                          without the dialog
"""

import argparse
import ctypes
import os
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import backup
from .device import models
from .device.connection import WinmmPort, warm_up
from .device.simulator import DEMO_DUMP, DEMO_PRESETS, SimPort, SimulatedAdi2
from .session import Session
from .ui import collector, simulated, theme, untested
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
SIMULATED_NAMES = (("dac", models.DAC.name), ("pro", models.PRO.name), ("24se", "ADI-2/4 Pro SE"),
                   ("24ex", "ADI-2/4 Pro EX"))


def simulator(dump, model):
    """The simulated device of --simulate [DUMP] --model MODEL."""
    model, revision = SIMULATED_MODELS[model]
    if dump is None and model is models.DAC:
        dump = DEMO_DUMP
    if dump is None:
        return SimulatedAdi2.factory(model, revision, presets=DEMO_PRESETS)
    return SimulatedAdi2.from_dump(dump, presets=DEMO_PRESETS, model=model, revision=revision)


def simulated_model(dump, model, choose):
    """The model --simulate [DUMP] simulates: --model; without it the ADI-2 DAC FS for a DUMP, else choose(), None
    when cancelled."""
    if model is not None:
        return model
    return "dac" if dump else choose()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="Commander")
    ap.add_argument("--simulate", nargs="?", const="", metavar="DUMP",
                    help="use a simulated device, started from a dump file")
    ap.add_argument("--model", choices=SIMULATED_MODELS, help="the simulated model, without the dialog")
    args = ap.parse_args(argv)
    if args.model and args.simulate is None:
        ap.error("--model needs --simulate")

    simulate = args.simulate is not None
    if not simulate:
        warm_up()                                              # while the window is built

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(SIMULATED_APP_ID if simulate else APP_ID)
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(QIcon(SIMULATED_ICON if simulate else ICON))
    theme.apply(app)
    collector.start(app)
    if simulate:
        model = simulated_model(args.simulate, args.model, lambda: simulated.choose(
            QSettings(untested.ORGANIZATION, untested.APPLICATION), SIMULATED_NAMES))
        if model is None:
            return 0                                           # cancelled
        sim = simulator(args.simulate or None, model)
        open_port = lambda: SimPort(sim)                       # noqa: E731
    else:
        sim = None
        open_port = WinmmPort
    session = Session(open_port)
    win = MainWindow(session, simulated=sim is not None, backups=backup.folder())
    if sim is not None:
        win.setWindowTitle(win.windowTitle() + "  —  SIMULATED " + dict(SIMULATED_NAMES)[model])
        win.simulator = sim
    show_on_screen(win, win.sizeHint(), app.primaryScreen())
    code = app.exec()
    session.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
