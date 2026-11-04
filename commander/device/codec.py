r"""Encodes and decodes ADI-2 SysEx parameters.

Encoding, 3 bytes per parameter (MIDITable_ADI-2_230930 v0.2):

  byte1  bit 6..3  address
         bit 2..0  upper 3 bits of the index
  byte2  bit 6..5  lower 2 bits of the index   (channel)
         bit 6..4  lower 3 bits of the index   (device, address 12)
         bit 4     highest value bit, or the x10 flag for frequencies
         bit 3..0  upper 4 bits of the value
  byte3  bit 6..0  lower 7 bits of the value

Commands: 0x01 is the direction device -> remote, 0x02 is remote -> device. Only 0x02 writes; a
parameter message with 0x01 is ignored without any sign.
"""

import re

FREQ_INDICES = {5, 8, 11, 14, 18, 22, 25}       # Band 1..5 Freq, Bass Freq, Treble Freq
EQ_ADDRESSES = (1, 2, 4, 5, 7, 8, 10, 11, 13, 14)

# The value field of a frequency is 11 bits, with bit 4 of byte 2 as x10 flag.
# Hence the grid: 1 Hz up to and including 2040 Hz, 10 Hz above.
FREQ_FINE_MAX = 2040

HEADER = [0xF0, 0x00, 0x20, 0x0D, 0x71]


def encode(address, index, value, is_freq=False):
    """Return the three bytes for a parameter. value is the increment value from the MIDITable,
    not the unit: gain in steps of 0.5 dB, Q in steps of 0.1."""
    if address == 12:
        if not 0 <= index <= 63:
            raise ValueError("device index %d out of range" % index)
        if not 0 <= value <= 2047:
            raise ValueError("device value %d out of range" % value)
        return [(12 << 3) | ((index >> 3) & 0x07),
                ((index & 0x07) << 4) | ((value >> 7) & 0x0F),
                value & 0x7F]

    if not 0 <= index <= 31:
        raise ValueError("channel index %d out of range" % index)
    b1 = (address << 3) | ((index >> 2) & 0x07)

    if is_freq:
        if value <= 2047:
            v, flag = value, 0
        elif value % 10 == 0 and value // 10 <= 2047:
            v, flag = value // 10, 1
        else:
            raise ValueError(
                "frequency %d Hz cannot be encoded: above %d Hz only a multiple of 10 is possible"
                % (value, FREQ_FINE_MAX))
        return [b1, ((index & 0x03) << 5) | (flag << 4) | ((v >> 7) & 0x0F), v & 0x7F]

    w = value & 0x0FFF                           # 12 bits, signed
    return [b1, ((index & 0x03) << 5) | (((w >> 11) & 0x01) << 4) | ((w >> 7) & 0x0F), w & 0x7F]


def decode_triplet(b1, b2, b3):
    """Return (address, index, value, is_freq) for three bytes."""
    address = (b1 >> 3) & 0x0F
    upper = b1 & 0x07
    if address == 12:
        return address, (upper << 3) | ((b2 >> 4) & 0x07), ((b2 & 0x0F) << 7) | (b3 & 0x7F), False
    index = (upper << 2) | ((b2 >> 5) & 0x03)
    if address in EQ_ADDRESSES and index in FREQ_INDICES:
        v = ((b2 & 0x0F) << 7) | (b3 & 0x7F)
        return address, index, v * 10 if ((b2 >> 4) & 1) else v, True
    raw = (((b2 >> 4) & 0x01) << 11) | ((b2 & 0x0F) << 7) | (b3 & 0x7F)
    return address, index, raw - 4096 if raw > 2047 else raw, False


def sysex(triplets, cmd=0x02):
    """Build a SysEx message. cmd 0x02 writes; 0x01 is the read direction and does nothing."""
    body = []
    for t in triplets:
        body += t
    msg = HEADER + [cmd] + body + [0xF7]
    if len(msg) > 256:
        raise ValueError("message is %d bytes; the protocol allows 256" % len(msg))
    return msg


def to_hex(msg):
    return " ".join("%02x" % b for b in msg)


def read_dump(path):
    """Return all SysEx messages from a dump file as lists of bytes."""
    msgs = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("---"):
                continue
            if re.fullmatch(r"(?:[0-9a-fA-F]{2}\s+)*[0-9a-fA-F]{2}", line):
                msgs.append([int(x, 16) for x in line.split()])
    return msgs


def parameter_triplets(msgs):
    """Yield the raw triplets of all parameter messages (0x01 or 0x02) from the device."""
    for m in msgs:
        if len(m) < 7 or list(m[:5]) != HEADER or m[5] not in (0x01, 0x02):
            continue
        body = m[6:-1] if m[-1] == 0xF7 else m[6:]
        for i in range(0, len(body) - 2, 3):
            yield body[i:i + 3]
