"""What goes between Commander and the device, as it goes: every message sent, every buffer received as the port
delivers it, in order, with the time. The last ENTRIES entries are kept, shown or not.

split() and irregular() read a buffer from its bytes alone, by the framing of MIDI SysEx: a message runs from F0
to F7, with data bytes below 0x80 in between.

Listeners are plain callables:
    on_entry(entry)     an Entry, the moment it is added
"""

import time
from collections import deque, namedtuple

ENTRIES = 100000               # an idle connection: ~1500 a minute, so about an hour

# t: when Commander sent it, or collected it from the port, as time.time(); kind: 'out' (sent) or 'in'
# (received); data: the bytes, as they went
Entry = namedtuple("Entry", "t kind data")


class Traffic:
    def __init__(self, clock=time.time, size=ENTRIES):
        self.clock = clock
        self.entries = deque(maxlen=size)
        self.on_entry = []

    def add(self, kind, data):
        e = Entry(self.clock(), kind, bytes(data))
        self.entries.append(e)
        for f in self.on_entry:
            f(e)


class RecordedPort:
    """A port whose traffic also goes into a Traffic; otherwise the port itself. A message is recorded before it
    goes out, so one that fails to go is in it too."""

    def __init__(self, port, traffic):
        self._port, self.traffic = port, traffic

    def __getattr__(self, name):
        return getattr(self._port, name)

    def send(self, msg):
        self.traffic.add("out", msg)
        self._port.send(msg)

    def receive(self):
        out = self._port.receive()
        for m in out:
            self.traffic.add("in", m)
        return out


def split(data):
    """The messages in a buffer: each from an F0 up to and including its F7; bytes before the first F0, or after
    the last F7, on their own."""
    out, start = [], 0
    for i, b in enumerate(data):
        if b == 0xF0 and i > start:
            out.append(bytes(data[start:i]))
            start = i
        elif b == 0xF7:
            out.append(bytes(data[start:i + 1]))
            start = i + 1
    if start < len(data):
        out.append(bytes(data[start:]))
    return out


def irregular(data):
    """Where a buffer departs from one message framed as SysEx, each as a short text with the place (counted from
    0); [] for one such message."""
    out, at, messages = [], 0, 0
    for m in split(data):
        if m[0] != 0xF0:
            out.append("%d bytes without F0 at %d" % (len(m), at))
        else:
            messages += 1
            if m[-1] != 0xF7:
                out.append("F0 at %d without F7" % at)
        at += len(m)
    out += ["byte %02x at %d" % (b, i) for i, b in enumerate(data) if b >= 0x80 and b not in (0xF0, 0xF7)]
    if messages > 1:
        out.append("%d messages" % messages)
    if not data:
        out.append("empty")
    return out
