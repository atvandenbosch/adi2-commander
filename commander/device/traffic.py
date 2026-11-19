"""What goes between Commander and the device, as it goes: every message sent, every buffer received as the port
delivers it, in order, with the time. The last ENTRIES entries are kept, shown or not.

Listeners are plain callables:
    on_entry(entry)     an Entry, the moment it is added
"""

import time
from collections import deque, namedtuple

ENTRIES = 100000               # an idle connection: ~1500 a minute, so about an hour

# t: the time, as time.time(); kind: 'out' (sent) or 'in' (received); data: the bytes, as they went
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
