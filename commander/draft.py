"""A preset slot being edited: its content in memory, shown and changed as the EQ of an output is, while nothing of
it goes to the device until it is written as a whole (Session.write_slot).

It answers what the tables, the graphs and Load ask of a Session: state, ready(), bypassed(), dual(), writable(),
set(), set_dual(), hold(), and the listeners on_changed and on_connection. Its state is the session's at the start,
with the output's EQ replaced by the slot: the bands on the output's left and right EQ address, Bass/Treble on the
left, Dual EQ on the output address. EQ Enable and B/T Enable are on: they are no part of a slot, and its content is
shown as selecting it loads it. With Dual EQ off the right side is the left's, as the device uses it.

No Qt here; on_changed(keys, origin) as the session's, origin always 'write'; the name is the key 'name'.
"""

from .device import params as P
from .session import SLOT_LEFT, SLOT_RIGHT, loaded


class Draft:
    def __init__(self, slot, stored, state, output):
        """slot: its number; stored: the slot as the session read it (None: not read yet); state: the session's;
        output: (name, address, left, right) of the output it is shown on."""
        self.slot, self.output = slot, output
        self.stored = stored
        _, out, left, right = output
        start = loaded(stored) if stored else loaded({"used": False})
        if not start["dual"]:                    # the device uses the left side for both; a slot may hold another
            start["vals"].update({(14, i): start["vals"][(13, i)] for i in SLOT_RIGHT})
        self.base = dict(start, name=(stored or {}).get("name", ""))
        self.name = self.base["name"].strip()
        self.state = dict(state)
        self.state[(out, P.DUAL_EQ)] = start["dual"]
        for (a, i), v in start["vals"].items():
            self.state[((left, right)[a - 13], i)] = v
        self.state[(left, P.EQ_ENABLE)] = self.state[(right, P.EQ_ENABLE)] = 1
        self.state[(left, P.BT_ENABLE)] = 1
        self.locked = False                      # while it is being written: nothing changes
        self.on_changed = []
        self.on_connection = []

    # -- as a Session ---------------------------------------------------------------------------
    def ready(self):
        return True

    def bypassed(self):
        return False

    def dual(self, out):
        return self.state.get((out, P.DUAL_EQ), 1) == 1

    def hold(self, on):
        pass

    def writable(self, key):
        _, out, left, right = self.output
        a, i = key
        if self.locked:
            return False
        if a == left:
            return i in SLOT_LEFT
        return a == right and i in SLOT_RIGHT and self.dual(out)

    def set(self, key, value):
        if not self.writable(key):
            raise ValueError("parameter %d/%d is not in a preset" % key)
        lo, hi = P.limits(key)
        if not lo <= value <= hi:
            raise ValueError("%d/%d: %d outside %d..%d" % (key + (value, lo, hi)))
        _, out, left, right = self.output
        keys = [key] + ([(right, key[1])] if key[0] == left and key[1] in SLOT_RIGHT and not self.dual(out) else [])
        changed = [k for k in keys if self.state.get(k) != value]
        for k in keys:
            self.state[k] = value
        if changed:
            self._emit(changed)

    def set_dual(self, out, on, keep="left"):
        """As Session.set_dual: off, the channel kept gives the one EQ of both; on, both start from it."""
        if self.locked:
            raise ValueError("the preset is being written")
        _, out, left, right = self.output
        if not on and keep == "right":
            for i in SLOT_RIGHT:
                self.state[(left, i)] = self.state[(right, i)]
        for i in SLOT_RIGHT:
            self.state[(right, i)] = self.state[(left, i)]
        self.state[(out, P.DUAL_EQ)] = 1 if on else 0
        self._emit([(out, P.DUAL_EQ)] + [(a, i) for a in (left, right) for i in SLOT_RIGHT])

    # -- the preset -----------------------------------------------------------------------------
    def set_name(self, name):
        if self.locked:
            raise ValueError("the preset is being written")
        if not P.valid_name(name):
            raise ValueError("preset name %r: up to %d of the signs the front panel offers" % (name, P.NAME_LENGTH))
        if name != self.name:
            self.name = name
            self._emit(["name"])

    def content(self):
        """What the slot gets: {'name', 'dual', 'vals'}, as Session.write_slot takes it. An unchanged name is the
        stored one, as the device has it."""
        _, out, left, right = self.output
        vals = {(13, i): self.state[(left, i)] for i in SLOT_LEFT}
        vals.update({(14, i): self.state[(right, i)] for i in SLOT_RIGHT})
        name = self.base["name"] if self.name == self.base["name"].strip() else self.name
        return {"name": name, "dual": self.state[(out, P.DUAL_EQ)], "vals": vals}

    def changed(self):
        """Whether it differs from the slot as it was opened. An unused slot opens as the factory state with the name
        the device shows; it becomes used only when something of that changes."""
        return self.content() != self.base

    def _emit(self, keys):
        for f in self.on_changed:
            f(keys, "write")
