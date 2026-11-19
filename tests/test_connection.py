"""The serial number of the device behind a MIDI port."""

import ctypes as C
import unittest
from unittest import mock

from commander.device import connection


class SerialNumber(unittest.TestCase):
    NONE = connection._mm.midiInGetNumDevs() + 10                   # no port has this number

    def test_from_the_port_name(self):
        self.assertEqual(connection.serial_number(self.NONE, "ADI-2 DAC (12345678)"), "12345678")
        self.assertEqual(connection.serial_number(self.NONE, "2- ADI-2 DAC (12345678)"), "12345678")

    def test_none_without_a_device(self):
        self.assertIsNone(connection.serial_number(self.NONE, "ADI-2 DAC Midi Port 1"))
        self.assertIsNone(connection.serial_number(self.NONE, "Other (12345678)"))



class Receive(unittest.TestCase):
    """winmm fills the buffers in the order they were handed to it; the pool goes round."""

    def setUp(self):
        self.port = connection.WinmmPort.__new__(connection.WinmmPort)
        self.port.h_in, self.port.bufs, self.port.hdrs, self.port.queued = None, [], [], 0
        for _ in range(3):
            b = C.create_string_buffer(8)
            h = connection.MIDIHDR()
            h.lpData = C.cast(b, C.c_void_p)
            h.dwBufferLength = 8
            h.dwUser, self.port.queued = self.port.queued, self.port.queued + 1
            self.port.bufs.append(b)
            self.port.hdrs.append(h)
        self.queue = list(self.port.hdrs)                           # as winmm has them, the next one first
        mm = mock.patch.object(connection, "_mm")
        mm.start().midiInAddBuffer.side_effect = lambda h_in, ref, size: self.queue.append(ref._obj)
        self.addCleanup(mm.stop)

    def fill(self, *data):
        """winmm fills the next buffers, one message each."""
        for d in data:
            h = self.queue.pop(0)
            C.memmove(h.lpData, bytes(d), len(d))
            h.dwBytesRecorded, h.dwFlags = len(d), connection.MHDR_DONE | connection.MHDR_PREPARED

    def test_in_the_order_they_came_also_when_the_pool_goes_round(self):
        self.fill([1], [2])
        self.assertEqual(self.port.receive(), [[1], [2]])
        self.fill([3], [4], [5])                                    # the third buffer, then the first two again
        self.assertEqual(self.port.receive(), [[3], [4], [5]])

if __name__ == "__main__":
    unittest.main()
