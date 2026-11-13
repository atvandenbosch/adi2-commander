"""Start ADI-2 Commander.

    pythonw Commander.pyw                 the real device
    pythonw Commander.pyw --simulate      a simulated device, of the model chosen in a dialog, or the one chosen
                                          last with Don't ask again: the ADI-2 DAC FS started from the demo,
                                          another model as it leaves the factory
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


def simulator(dump, model, **kw):
    """The simulated device of --simulate [DUMP] --model MODEL; kw: for SimulatedAdi2, as its clock."""
    model, revision = SIMULATED_MODELS[model]
    if dump is None and model is models.DAC:
        dump = DEMO_DUMP
    if dump is None:
        return SimulatedAdi2.factory(model, revision, presets=DEMO_PRESETS, **kw)
    return SimulatedAdi2.from_dump(dump, presets=DEMO_PRESETS, model=model, revision=revision, **kw)


class Simulation:
    """The simulated device of --simulate [DUMP], of the model with key in SIMULATED_MODELS; switch replaces it with
    another, started anew. kw: for SimulatedAdi2, as its clock."""

    choices = SIMULATED_NAMES

    def __init__(self, dump, key, **kw):
        self.dump, self.kw = dump, kw
        self.switch(key)

    def switch(self, key):
        self.key, self.device = key, simulator(self.dump, key, **self.kw)

    def name(self):
        return dict(SIMULATED_NAMES)[self.key]

    def open_port(self):
        return SimPort(self.device)


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
    simulation = None
    if simulate:
        settings = QSettings(untested.ORGANIZATION, untested.APPLICATION)
        model = simulated_model(args.simulate, args.model, lambda: simulated.remembered(settings, SIMULATED_NAMES)
                                or simulated.choose(settings, SIMULATED_NAMES))
        if model is None:
            return 0                                           # cancelled
        simulation = Simulation(args.simulate or None, model)
    session = Session(WinmmPort if simulation is None else simulation.open_port)
    win = MainWindow(session, simulation=simulation, backups=backup.folder())
    show_on_screen(win, win.sizeHint(), app.primaryScreen())
    code = app.exec()
    session.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
