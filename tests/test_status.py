"""The status message of the device, decoded."""

import unittest

from commander.device import status as S


def body(text):
    return [int(x, 16) for x in text.split()]


class Status(unittest.TestCase):
    def test_usb_without_spdif(self):
        s = S.decode(body("08 30 7e 28 00 00 00 42 00 00 02 0a 00 00"))
        self.assertEqual((s.output, s.phones, s.iem, s.clock), (0, False, False, None))
        self.assertEqual((s.rate, s.usb_rate, s.usb_dsd, s.dsd), (192000, 192000, False, False))
        self.assertEqual(s.coax, S.Spdif(False, False, None, False, False))      # no signal since power-on
        self.assertEqual(s.optical, S.Spdif(False, False, None, False, False))

    def test_every_rate(self):
        seen = [(0x04, 0x01), (0x08, 0x02), (0x14, 0x05), (0x18, 0x06), (0x24, 0x09),
                (0x28, 0x0a), (0x34, 0x0d), (0x38, 0x0e), (0x44, 0x11), (0x48, 0x12)]    # d3, d11 on USB
        for (d3, d11), rate in zip(seen, S.SAMPLE_RATES):
            s = S.decode(body("08 30 7e %02x 00 00 00 41 00 00 02 %02x 00 00" % (d3, d11)))
            self.assertEqual((s.rate, s.usb_rate), (rate, rate))

    def test_the_active_output_follows_a_plug(self):
        phones = S.decode(body("09 12 42 34 01 00 00 41 00 00 02 0d 00 00"))
        iem = S.decode(body("0a 12 42 34 40 00 00 41 00 00 02 0d 00 00"))
        self.assertEqual((phones.output, phones.phones, phones.iem), (1, True, False))
        self.assertEqual((iem.output, iem.phones, iem.iem), (2, False, True))

    def test_optical_as_clock(self):
        s = S.decode(body("08 1a 43 08 08 00 04 42 00 00 02 12 00 00"))
        self.assertEqual((s.clock, s.rate, s.usb_rate), ("optical", 48000, 768000))
        self.assertEqual(s.optical, S.Spdif(True, True, 48000, False, False))
        self.assertEqual(s.coax, S.Spdif(False, False, 44100, False, False))      # the rate it had stays

    def test_coax_as_clock_with_optical_beside(self):
        s = S.decode(body("08 57 42 04 00 00 00 41 00 00 02 02 00 00"))
        self.assertEqual((s.clock, s.rate), ("coax", 44100))
        self.assertEqual(s.coax, S.Spdif(True, True, 44100, False, False))
        self.assertEqual(s.optical, S.Spdif(True, False, 48000, False, False))    # a signal, at another rate

    def test_dsd_over_usb(self):
        s = S.decode(body("08 12 42 34 08 0c 00 41 00 70 02 0d 00 00"))
        self.assertEqual((s.usb_dsd, s.dsd, s.rate), (True, True, 352800))

    def test_non_audio_on_optical(self):
        s = S.decode(body("08 12 43 08 00 00 00 4a 00 00 02 12 00 00"))
        self.assertTrue(s.optical.non_audio)
        self.assertFalse(s.coax.non_audio)

    def test_the_revision_beside_the_active_output(self):
        revisions = [S.decode(body("%02x 30 7e 08 00 00 00 42 00 00 02 02 00 00" % d0)) for d0 in (0x08, 0x05, 0x02)]
        self.assertEqual([(s.revision, s.output) for s in revisions], [(2, 0), (1, 1), (0, 2)])

    def test_too_short(self):
        with self.assertRaises(ValueError):
            S.decode(body("08 30 7e 28 00 00 00 42 00 00 02 0a"))


if __name__ == "__main__":
    unittest.main()
