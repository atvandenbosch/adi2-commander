"""A buffer from the device, read by the framing of MIDI SysEx alone: split into its messages, and where it departs
from one message."""

import unittest

from commander.device.traffic import irregular, split

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



if __name__ == "__main__":
    unittest.main()
