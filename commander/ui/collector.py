"""Python's cyclic garbage collection in the GUI thread only.

Left automatic, it runs in whichever thread happens to allocate, a fit's too, and destroys Qt objects there that
belong to the GUI thread; Qt then crashes. So the automatic collector is off, and a timer collects instead: the young
objects each second once there are enough of them, everything once a minute (some 20 ms with the main window open).
"""

import gc

from PySide6.QtCore import QTimer

INTERVAL_MS = 1000
FULL_EVERY = 60                                     # ticks


def start(parent):
    """From now on collect in the thread of parent, on a timer that lives as long as parent."""
    gc.disable()
    young = gc.get_threshold()[0]
    ticks = 0

    def tick():
        nonlocal ticks
        ticks += 1
        if ticks >= FULL_EVERY:
            ticks = 0
            gc.collect()
        elif gc.get_count()[0] > young:
            gc.collect(0)

    timer = QTimer(parent, interval=INTERVAL_MS, timeout=tick)
    timer.start()
    return timer
