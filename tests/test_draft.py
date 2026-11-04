"""A preset slot being edited, in memory: as the EQ of an output, what it lets change, and what it would write."""

import unittest

from commander.device import params as P
from commander.device.simulator import SimPort, SimulatedAdi2
from commander.draft import Draft
from commander.session import SLOT_KEYS, Session
from tests.support import DUMP, PRESETS

PHONES = P.OUTPUTS[1]                                    # ("Phones 1/2", 6, 7, 8)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class DraftTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clock = Clock()
        session = Session(lambda: SimPort(SimulatedAdi2.from_dump(DUMP, presets=PRESETS, clock=clock)), clock=clock)
        while len(session.slots) < 20:
            clock.t += 0.02
            session.tick()
        cls.state, cls.slots = session.state, dict(session.slots)
        session.close()
        two = cls.slots[2]                               # Dual EQ on, the right side its own
        cls.slots[2] = dict(two, dual=1, vals=two["vals"] | {(14, 7): two["vals"][(14, 7)] + 4})

    def draft(self, slot=2, output=PHONES):
        d = Draft(slot, self.slots.get(slot), self.state, output)
        self.events = []
        d.on_changed.append(lambda keys, origin: self.events.append((tuple(keys), origin)))
        return d

    def dual_slot(self):
        return 2

    def test_the_slot_on_the_outputs_addresses_switches_on(self):
        n = self.dual_slot()
        d = self.draft(n)
        vals = self.slots[n]["vals"]
        self.assertEqual(d.state[(6, P.DUAL_EQ)], 1)
        self.assertEqual({(a, i): d.state[((7, 8)[a - 13], i)] for a, i in SLOT_KEYS}, vals)
        self.assertEqual([d.state[k] for k in ((7, 2), (8, 2), (7, 20))], [1, 1, 1])
        self.assertEqual(d.state[(3, P.VOLUME)], self.state[(3, P.VOLUME)])    # the rest as the session has it
        self.assertFalse(d.changed())
        self.assertEqual(d.name, self.slots[n]["name"].strip())

    def test_an_unused_slot_starts_as_the_factory_state_and_changes_as_any(self):
        n = next(n for n, s in self.slots.items() if not s["used"])
        d = self.draft(n)
        self.assertEqual(d.state[(7, 5)], P.FACTORY_BANDS[5])
        self.assertEqual(d.state[(6, P.DUAL_EQ)], 0)
        self.assertFalse(d.changed())
        d.set_name("Spare")
        self.assertTrue(d.changed())

    def test_only_what_a_slot_holds_is_writable(self):
        d = self.draft(self.dual_slot())
        for key in [(7, 4), (8, 4), (7, 21), (7, 26)]:
            self.assertTrue(d.writable(key), key)
        for key in [(7, 2), (7, 20), (7, 27), (7, 28), (8, 21), (4, 4), (6, P.VOLUME)]:
            self.assertFalse(d.writable(key), key)
        with self.assertRaises(ValueError):
            d.set((7, 5), 19)
        with self.assertRaises(ValueError):
            d.set((6, P.VOLUME), -100)

    def test_a_change_is_in_memory_and_told(self):
        d = self.draft(self.dual_slot())
        before = dict(self.state)
        d.set((8, 7), d.state[(8, 7)] + 2)
        self.assertEqual(self.events, [(((8, 7),), "write")])
        self.assertTrue(d.changed())
        self.assertEqual(self.state, before)
        self.assertEqual(d.content()["vals"][(14, 7)], d.state[(8, 7)])
        d.set((8, 7), d.state[(8, 7)] - 2)
        self.assertFalse(d.changed())                     # back as it was: nothing to write

    def test_with_dual_eq_off_the_right_side_is_the_left(self):
        n = next(n for n, s in self.slots.items() if s["used"] and s["dual"] == 0)
        d = self.draft(n)
        self.assertFalse(d.writable((8, 7)))
        d.set((7, 7), 5)
        c = d.content()
        self.assertEqual((c["dual"], c["vals"][(13, 7)], c["vals"][(14, 7)]), (0, 5, 5))

    def test_share_and_split(self):
        d = self.draft(self.dual_slot())
        d.set((8, 7), 9)
        d.set_dual(6, False, keep="right")
        c = d.content()
        self.assertEqual((c["dual"], c["vals"][(13, 7)], c["vals"][(14, 7)]), (0, 9, 9))
        d.set_dual(6, True)
        self.assertTrue(d.dual(6))
        self.assertTrue(d.writable((8, 7)))

    def test_the_name(self):
        d = self.draft(self.dual_slot())
        stored = self.slots[self.dual_slot()]["name"]
        self.assertEqual(d.content()["name"], stored)            # unchanged: as the device has it, spaces and all
        d.set_name("Room")
        self.assertEqual((d.content()["name"], self.events[-1]), ("Room", (("name",), "write")))
        self.assertTrue(d.changed())
        with self.assertRaises(ValueError):
            d.set_name("Café")
        d.set_name(stored.strip())
        self.assertFalse(d.changed())


if __name__ == "__main__":
    unittest.main()
