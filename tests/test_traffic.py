"""The traffic with the device: what is recorded of the port, and a buffer read by the framing of MIDI SysEx alone,
split into its messages, and where it departs from one message."""

import unittest

from commander.device.traffic import Traffic, irregular, split

A = bytes([0xF0, 0x00, 0x20, 0x0D, 0x71, 0x03, 0x09, 0xF7])
B = bytes([0xF0, 0x00, 0x20, 0x0D, 0x71, 0x05, 0x01, 0x41, 0x00, 0xF7])


class Split(unittest.TestCase):
    def test_one_message(self):
        self.assertEqual(split(A), [A])

    def test_two_messages_in_one_buffer(self):
        self.assertEqual(split(A + B), [A, B])

    def test_the_end_of_a_message_and_the_start_of_the_next(self):
        self.assertEqual(split(B[3:] + A[:5]), [B[3:], A[:5]])

    def test_a_start_before_the_end(self):
        self.assertEqual(split(B[:-1] + A), [B[:-1], A])


class Irregular(unittest.TestCase):
    def test_one_message(self):
        self.assertEqual(irregular(A), [])
        self.assertEqual(irregular(bytes([0xF0, 0xF7])), [])

    def test_more_than_one(self):
        self.assertEqual(irregular(A + B), ["2 messages"])

    def test_pieces(self):
        self.assertEqual(irregular(B[3:]), ["7 bytes without F0 at 0"])
        self.assertEqual(irregular(A[:5]), ["F0 at 0 without F7"])
        self.assertEqual(irregular(B[:-1] + A), ["F0 at 0 without F7", "2 messages"])
        self.assertEqual(irregular(A + B[:4]), ["F0 at 8 without F7", "2 messages"])

    def test_a_byte_that_is_no_data_byte(self):
        self.assertEqual(irregular(A[:6] + bytes([0xF8]) + A[6:]), ["byte f8 at 6"])

    def test_empty(self):
        self.assertEqual(irregular(b""), ["empty"])



class Port:
    names = ("ADI-2 DAC (12345678)", "ADI-2 DAC (12345678)")

    def __init__(self):
        self.listed, self.fail, self.sent = True, None, []

    def send(self, msg):
        if self.fail:
            raise OSError(self.fail)
        self.sent.append(msg)

    def receive(self):
        if self.fail:
            raise OSError(self.fail)
        return [list(A)]

    def present(self):
        return self.listed

    def close(self):
        pass


class Recorded(unittest.TestCase):
    def setUp(self):
        self.traffic, self.raw = Traffic(), Port()

    def entries(self):
        return [(e.kind, e.data) for e in self.traffic.entries]

    def test_what_goes_out_and_comes_in(self):
        port = self.traffic.open(lambda: self.raw)
        port.send(list(B))
        self.assertEqual(port.receive(), [list(A)])
        self.assertEqual(self.raw.sent, [list(B)])
        self.assertEqual(self.entries(), [("port", 'opened  in "ADI-2 DAC (12345678)"  out "ADI-2 DAC (12345678)"'),
                                          ("out", B), ("in", A)])

    def test_not_opened_once_until_it_reads_otherwise(self):
        def fail(why):
            def open_port():
                raise OSError(why)
            return open_port
        for why in ("no port", "no port", "busy", "busy"):
            with self.assertRaises(OSError):
                self.traffic.open(fail(why))
        self.traffic.open(lambda: self.raw)
        with self.assertRaises(OSError):
            self.traffic.open(fail("busy"))
        self.assertEqual([d for _, d in self.entries()],
                         ["not opened: no port", "not opened: busy", self.entries()[2][1], "not opened: busy"])

    def test_failures_and_what_was_attempted(self):
        port = self.traffic.open(lambda: self.raw)
        self.raw.fail = "midiOutLongMsg failed (winmm 11)"
        with self.assertRaises(OSError):
            port.send(list(B))
        with self.assertRaises(OSError):
            port.receive()
        self.assertEqual(self.entries()[1:], [("out", B), ("port", "send failed: midiOutLongMsg failed (winmm 11)"),
                                              ("port", "receive failed: midiOutLongMsg failed (winmm 11)")])

    def test_no_longer_listed_and_closed_once(self):
        port = self.traffic.open(lambda: self.raw)
        self.assertTrue(port.present())
        self.raw.listed = False
        self.assertFalse(port.present())
        self.assertFalse(port.present())
        port.close()
        port.close()
        self.assertEqual(self.entries()[1:], [("port", "no longer listed"), ("port", "closed")])


if __name__ == "__main__":
    unittest.main()
