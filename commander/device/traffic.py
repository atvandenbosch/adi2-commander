"""What goes between Commander and the device, as it goes: every message sent, every buffer received as the port
delivers it, and what happens to the port itself, in order, with the time. The last ENTRIES entries are kept, shown
or not.

What happens to the port, as entries of kind 'port':
    opened  in "<name>"  out "<name>"     Commander opened the ports with these names
    not opened: <why>                   opening failed, as the port says why; once until that reads otherwise
    send failed: <why>                  a message did not go out, as the port says why
    receive failed: <why>
    no longer listed                    the port names are gone from the list of ports
    closed                              Commander closed the ports

split() and irregular() read a buffer from its bytes alone, by the framing of MIDI SysEx: a message runs from F0
to F7, with data bytes below 0x80 in between.

Listeners are plain callables:
    on_entry(entry)     an Entry, the moment it is added
"""

import time
from collections import deque, namedtuple

ENTRIES = 100000               # an idle connection: ~1500 a minute, so about an hour

# t: when Commander sent it, collected it from the port, or the port changed, as time.time(); kind: 'out' (sent),
# 'in' (received) or 'port'; data: the bytes, as they went, or for 'port' the text
Entry = namedtuple("Entry", "t kind data")


class Traffic:
    def __init__(self, clock=time.time, size=ENTRIES):
        self.clock = clock
        self.entries = deque(maxlen=size)
        self.on_entry = []
        self._not_opened = None

    def clear(self):
        self.entries.clear()

    def add(self, kind, data):
        e = Entry(self.clock(), kind, data if kind == "port" else bytes(data))
        self.entries.append(e)
        for f in self.on_entry:
            f(e)

    def open(self, open_port):
        """open_port() as a RecordedPort, its opening recorded; what it raises, recorded and raised."""
        try:
            port = open_port()
        except Exception as e:
            text = "not opened: %s" % e
            if text != self._not_opened:
                self._not_opened = text
                self.add("port", text)
            raise
        self._not_opened = None
        self.add("port", 'opened  in "%s"  out "%s"' % tuple(port.names))
        return RecordedPort(port, self)


class RecordedPort:
    """A port whose traffic also goes into a Traffic; otherwise the port itself. A message is recorded before it
    goes out, so one that fails to go is in it too."""

    def __init__(self, port, traffic):
        self._port, self.traffic = port, traffic
        self._listed, self._open = True, True

    def __getattr__(self, name):
        return getattr(self._port, name)

    def send(self, msg):
        self.traffic.add("out", msg)
        try:
            self._port.send(msg)
        except Exception as e:
            self.traffic.add("port", "send failed: %s" % e)
            raise

    def receive(self):
        try:
            out = self._port.receive()
        except Exception as e:
            self.traffic.add("port", "receive failed: %s" % e)
            raise
        for m in out:
            self.traffic.add("in", m)
        return out

    def present(self):
        listed = self._port.present()
        if self._listed and not listed:
            self.traffic.add("port", "no longer listed")
        self._listed = listed
        return listed

    def close(self):
        self._port.close()
        if self._open:
            self._open = False
            self.traffic.add("port", "closed")


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
    out, at, starts = [], 0, 0
    for m in split(data):
        if m[0] != 0xF0:
            out.append("%d bytes without f0 at %d" % (len(m), at))
        else:
            starts += 1
            if m[-1] != 0xF7:
                out.append("f0 at %d without f7" % at)
        at += len(m)
    out += ["byte %02x at %d" % (b, i) for i, b in enumerate(data) if b >= 0x80 and b not in (0xF0, 0xF7)]
    if starts > 1:
        out.append("%d × f0" % starts)
    if not data:
        out.append("empty")
    return out
