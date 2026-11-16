"""The serial number of the device behind a MIDI port."""

import unittest

from commander.device import connection


class SerialNumber(unittest.TestCase):
    NONE = connection._mm.midiInGetNumDevs() + 10                   # no port has this number

    def test_from_the_port_name(self):
        self.assertEqual(connection.serial_number(self.NONE, "ADI-2 DAC (12345678)"), "12345678")
        self.assertEqual(connection.serial_number(self.NONE, "2- ADI-2 DAC (12345678)"), "12345678")

    def test_none_without_a_device(self):
        self.assertIsNone(connection.serial_number(self.NONE, "ADI-2 DAC Midi Port 1"))
        self.assertIsNone(connection.serial_number(self.NONE, "Other (12345678)"))


if __name__ == "__main__":
    unittest.main()
