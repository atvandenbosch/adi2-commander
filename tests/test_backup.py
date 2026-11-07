"""Copies of the device's state, per model: a new one only when it differs from the newest, the last five kept."""

import datetime
import os
import tempfile
import unittest

from commander import backup
from commander.device import models


def at(minute):
    return datetime.datetime(2026, 11, 7, 15, minute, 0)


class Keep(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.where = os.path.join(self.dir.name, "Backups")

    def files(self):
        return sorted(os.listdir(self.where))

    def test_a_copy_named_by_the_model_and_the_time(self):
        path = backup.keep(self.where, models.PRO_24, "a\n", at(30))
        self.assertEqual(os.path.basename(path), "ADI-2-4 Pro 2026-11-07 153000.adistp")
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"a\n")

    def test_only_what_differs_from_the_newest(self):
        backup.keep(self.where, models.DAC, "a\n", at(1))
        self.assertIsNone(backup.keep(self.where, models.DAC, "a\n", at(2)))
        backup.keep(self.where, models.DAC, "b\n", at(3))
        backup.keep(self.where, models.DAC, "a\n", at(4))                       # the newest holds b
        self.assertEqual(len(self.files()), 3)

    def test_the_last_five_per_model(self):
        backup.keep(self.where, models.PRO, "pro\n", at(0))
        for m in range(1, 8):
            backup.keep(self.where, models.DAC, "%d\n" % m, at(m))
        dac = [f for f in self.files() if f.startswith("ADI-2 DAC FS")]
        self.assertEqual(dac, ["ADI-2 DAC FS 2026-11-07 15%02d00.adistp" % m for m in range(3, 8)])
        self.assertIn("ADI-2 Pro 2026-11-07 150000.adistp", self.files())      # another model's copy stays

    def test_the_folder(self):
        self.assertTrue(backup.folder().endswith(os.path.join("ADI-2 Commander", "Backups")))


if __name__ == "__main__":
    unittest.main()
