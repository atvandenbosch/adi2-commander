"""Copies of the device's state, per device: a new one only when it differs from the newest, the last five kept."""

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

    def test_named_by_the_serial_number_too(self):
        path = backup.keep(self.where, models.DAC, "a\n", at(30), serial="12345678")
        self.assertEqual(os.path.basename(path), "ADI-2 DAC FS 12345678 2026-11-07 153000.adistp")

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

    def test_the_last_five_per_device(self):
        for m in range(1, 8):
            backup.keep(self.where, models.DAC, "a%d\n" % m, at(m), serial="11111111")
            backup.keep(self.where, models.DAC, "b%d\n" % m, at(m), serial="22222222")
        backup.keep(self.where, models.DAC, "c\n", at(9))                       # serial number unknown
        for serial in ("11111111", "22222222"):
            self.assertEqual([f for f in self.files() if serial in f],
                             ["ADI-2 DAC FS %s 2026-11-07 15%02d00.adistp" % (serial, m) for m in range(3, 8)])
        self.assertIn("ADI-2 DAC FS 2026-11-07 150900.adistp", self.files())
        self.assertIsNone(backup.keep(self.where, models.DAC, "b7\n", at(10), serial="22222222"))
        self.assertIsNotNone(backup.keep(self.where, models.DAC, "b7\n", at(10), serial="11111111"))

    def test_the_folder(self):
        self.assertTrue(backup.folder().endswith(os.path.join("ADI-2 Commander", "Backups")))


if __name__ == "__main__":
    unittest.main()
