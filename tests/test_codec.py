"""Codec and message building, against known bytes and the dump."""

import unittest

from commander.device import codec
from commander.device import connection as conn
from tests import client
from tests.support import DUMP


class Codec(unittest.TestCase):
    def test_known_messages(self):
        # Auto Standby (address 12, index 2) OFF
        self.assertEqual(codec.to_hex(codec.sysex([codec.encode(12, 2, 0)])), "f0 00 20 0d 71 02 60 20 00 f7")
        # Treble Freq 10000 Hz: above 2040 Hz the value goes x10 with the flag in bit 4 of byte 2
        self.assertEqual(codec.encode(4, 25, 10000, True), [0x26, 0x37, 0x68])
        self.assertEqual(codec.decode_triplet(0x26, 0x37, 0x68), (4, 25, 10000, True))
        # gain -6 dB = -12 increments, 12-bit two's complement
        self.assertEqual(codec.decode_triplet(*codec.encode(4, 4, -12)), (4, 4, -12, False))

    def test_frequency_grid(self):
        for f in (1, 44, 1234, 2040, 2047, 2050, 12340, 20000):
            self.assertEqual(codec.decode_triplet(*codec.encode(4, 5, f, True))[2], f)
        for f in (2048, 2055, 20471):
            with self.assertRaises(ValueError):
                codec.encode(4, 5, f, True)

    def test_only_whole_triplets_of_parameter_messages(self):
        t = codec.encode(4, 4, -12)
        msg = codec.sysex([t], 0x01)
        other_device = msg[:4] + [0x72] + msg[5:]
        name = msg[:5] + [0x05] + msg[6:]
        half = msg[:-1] + [0x10, 0x20, 0xF7]                        # a triplet and two bytes
        unterminated = msg[:-1]
        msgs = [other_device, name, msg[:6], half, unterminated]
        self.assertEqual([list(x) for x in codec.parameter_triplets(msgs)], [t, t])

    def test_dump(self):
        self.assertEqual(client.roundtrip_mismatches(DUMP), [])
        state = client.parse(codec.read_dump(DUMP))
        self.assertFalse(conn.REQUIRED - set(state))
        self.assertEqual(state[(4, 28)], 0)                 # EQ Preset Select: Manual
        self.assertEqual(client.read_state(DUMP), {k: v for k, v in state.items() if k[0] not in (13, 14)})

    def test_build_messages(self):
        params = [(4, 4, 0, False)] * 200
        msgs = conn.build_messages(params)
        self.assertEqual([len(m) for m in msgs], [247, 247, 127])   # at most 80 triplets per message
        self.assertTrue(all(m[5] == 0x02 for m in msgs))
        with self.assertRaises(ValueError):                         # address 5 index > 19 hits shared B/T
            conn.build_messages([(5, 21, 0, False)])


if __name__ == "__main__":
    unittest.main()
