"""The status message (0x07) of an ADI-2 DAC FS: the active output, the plugs, what the inputs receive and the
rate the device runs at. No I/O.

The device sends it about once a second, from the first valid message of a remote on: 14 data bytes, d0..d13.
Only the bits a remote needs are read here.
"""

from collections import namedtuple

from .params import SAMPLE_RATES

# an SPDIF input: lock (a valid signal), sync (at the rate of the device's clock), its rate in Hz (None before
# any signal since power-on), and whether it carries DSD or non-audio data (a bitstream)
Spdif = namedtuple("Spdif", "lock sync rate dsd non_audio")
# output: the active output, the one the display and the volume knob control, as an index into params.OUTPUTS;
# phones, iem: a plug in that jack, on an ADI-2 Pro and ADI-2/4 Pro in Phones 1/2 and Phones 3/4; clock: "coax" or "optical" while the device follows that input, None on its
# own clock (internal, or USB); rate: the rate the device runs at; usb_rate: the rate set for USB on the
# computer; usb_dsd: DSD over USB (DoP); dsd: DSD is played, with the DSP bypassed; coax, optical: Spdif;
# revision: the device revision, which tells its D/A converter (params.da_filters); mode: on an ADI-2 Pro and
# ADI-2/4 Pro the Basic Mode in use, an index into params.BASIC_MODES (with Auto, the mode it took); balanced: on an
# ADI-2 Pro and ADI-2/4 Pro, Balanced Phones mode is active, with Phones 1/2 as the right channel of Phones 3/4
Status = namedtuple("Status", "output phones iem clock rate usb_rate usb_dsd dsd coax optical revision mode "
                              "balanced")

SPDIF_FAMILIES = (32000, 44100, 48000, None)    # the fourth: no signal seen since power-on
USB_FAMILIES = (None, 44100, 48000, None)
LENGTH = 14


def _spdif_rate(family, multiplier):
    base = SPDIF_FAMILIES[family]
    return None if base is None else base << multiplier


def decode(body):
    """The Status in the data bytes of a status message, the bytes after the command 0x07."""
    if len(body) < LENGTH:
        raise ValueError("status message of %d data bytes; the device sends %d" % (len(body), LENGTH))
    d = body
    index = (d[3] >> 3) & 0x0F
    usb = USB_FAMILIES[d[11] & 0x03]
    return Status(
        output=d[0] & 0x03,
        phones=bool(d[4] & 0x01),
        iem=bool(d[4] & 0x40),
        clock="coax" if d[1] & 0x40 else "optical" if d[2] & 0x01 else None,
        rate=SAMPLE_RATES[index] if index < len(SAMPLE_RATES) else None,
        usb_rate=None if usb is None else usb << (d[11] >> 2),
        usb_dsd=(d[5] & 0x0C) == 0x0C,
        dsd=(d[9] & 0x70) == 0x70,
        coax=Spdif(lock=bool(d[1] & 0x01), sync=bool(d[1] & 0x04),
                   rate=_spdif_rate((d[2] >> 1) & 0x03, (d[2] >> 3) & 0x03),
                   dsd=bool(d[5] & 0x40), non_audio=bool(d[7] & 0x04)),
        optical=Spdif(lock=bool(d[1] & 0x02), sync=bool(d[1] & 0x08),
                      rate=_spdif_rate((d[2] >> 5) & 0x03, d[3] & 0x03),
                      dsd=bool(d[6] & 0x01), non_audio=bool(d[7] & 0x08)),
        revision=(d[0] >> 2) & 0x03,
        mode=d[9] & 0x07,
        balanced=bool(d[9] & 0x08))
