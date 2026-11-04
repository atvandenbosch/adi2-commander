"""Garbage collection in the GUI thread: on a timer, the young objects and now and then everything."""

import gc
import time
import unittest
import weakref
from unittest import mock

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from commander.ui import collector
from tests.gui import app  # noqa: F401  (the application, with the collector started)


class Node:
    pass


def cycle():
    """Two objects that only refer to each other, and a weak reference to see them go."""
    a, b = Node(), Node()
    a.other, b.other = b, a
    return a, weakref.ref(a)


def until(condition, seconds=2.0):
    t0 = time.monotonic()
    while not condition() and time.monotonic() - t0 < seconds:
        QApplication.processEvents()
        time.sleep(0.005)
    return condition()


class Collector(unittest.TestCase):
    def setUp(self):
        self.parent = QObject()

    def tearDown(self):
        self.parent.deleteLater()
        QApplication.processEvents()

    def test_the_automatic_collector_is_off(self):
        self.assertFalse(gc.isenabled())

    def test_young_garbage_goes_on_the_next_tick(self):
        with mock.patch.object(collector, "INTERVAL_MS", 20):
            collector.start(self.parent)
        gone = cycle()[1]
        young = [[] for _ in range(gc.get_threshold()[0] + 100)]  # enough new objects for a collection
        self.assertTrue(until(lambda: gone() is None))
        del young

    def test_old_garbage_goes_with_the_full_collection(self):
        held, gone = cycle()
        gc.collect(0)
        gc.collect(0)                                             # still in use: it survives, and is old
        del held
        gc.collect(0)
        self.assertIsNotNone(gone())                              # garbage, but not young
        with mock.patch.object(collector, "INTERVAL_MS", 20), mock.patch.object(collector, "FULL_EVERY", 3):
            collector.start(self.parent)
            self.assertTrue(until(lambda: gone() is None))


if __name__ == "__main__":
    unittest.main()
