"""The state of a device as a setup file of ADI-2 Remote: per model, as the session reads the simulated device."""

import os
import unittest

from commander.conversion import setupfile
from commander.device import models
from commander.device.simulator import DEMO_DUMP, DEMO_PRESETS, SimPort, SimulatedAdi2
from commander.session import Session
from tests.support import DATA


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def read(make):
    """The session after reading the device that make(clock) simulates: its state and its twenty slots."""
    clock = Clock()
    sim = make(clock)
    session = Session(lambda: SimPort(sim), clock=clock)
    for _ in range(400):
        clock.t += 0.05
        session.tick()
    assert session.ready() and len(session.slots) == 20
    session.close()
    return session


DEVICES = {
    "dac": lambda c: SimulatedAdi2.from_dump(DEMO_DUMP, presets=DEMO_PRESETS, clock=c),
    "pro": lambda c: SimulatedAdi2.factory(models.PRO, None, presets=DEMO_PRESETS, clock=c),
    "24ex": lambda c: SimulatedAdi2.factory(models.PRO_24, 1, presets=DEMO_PRESETS, clock=c),
}


class SetupFile(unittest.TestCase):
    def test_as_written_for_each_model(self):
        for label, make in DEVICES.items():
            s = read(make)
            with open(os.path.join(DATA, "setup-%s.adistp" % label), encoding="ascii", newline="") as f:
                self.assertEqual(setupfile.write(s.state, s.slots, s.model, s.revision()), f.read(), label)

    def test_without_the_revision(self):
        s = read(DEVICES["dac"])
        text = setupfile.write(s.state, s.slots, s.model)
        self.assertTrue(text.startswith('\t<ADI-2DAC>\n\t\t<General>\n\t\t\t<val e="Version" v="2"/>\n\t\t</General>\n'))

    def test_not_read_yet(self):
        s = read(DEVICES["pro"])
        slots = dict(s.slots)
        del slots[20]
        with self.assertRaises(ValueError):
            setupfile.write(s.state, slots, s.model)
        state = {k: v for k, v in s.state.items() if k[0] != 1}                # no EQ of the input
        with self.assertRaises(ValueError):
            setupfile.write(state, s.slots, s.model)

    def test_phones_1_2_of_the_pro_with_the_settings_of_line_out(self):
        s = read(DEVICES["pro"])
        state = {k: v for k, v in s.state.items() if k not in ((6, 5), (6, 15))}   # Width, Mute: Line Out's only
        state.update({(3, 5): 50, (3, 15): 1, (6, 12): -300})                    # and Volume of its own
        text = setupfile.write(state, s.slots, s.model)
        phones = text[text.index("<Output2>"):text.index("</Output2>")]
        for line in ('"Width" v="0.50,"', '"Mute" v="1.00,"', '"Volume" v="-30.00,"'):
            self.assertIn(line, phones)


if __name__ == "__main__":
    unittest.main()
