"""Starting the app: with a simulated device, and Windows' MIDI service started off the GUI thread."""

import os
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from commander import app
from commander.device import connection, models
from commander.device.simulator import SimulatedAdi2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Start(unittest.TestCase):
    def test_simulate_starts_from_the_demo(self):
        sim = SimulatedAdi2.from_dump(app.DEMO_DUMP, presets=app.DEMO_PRESETS)
        self.assertTrue(sim.state and sim.slots)

    def test_simulate_a_model(self):
        self.assertEqual(app.simulator(None, "dac").state, SimulatedAdi2.from_dump(app.DEMO_DUMP).state)
        for name, (model, revision) in app.SIMULATED_MODELS.items():
            sim = app.simulator(None, name)
            self.assertEqual((sim.model, sim.revision), (model, sim.revision if revision is None else revision))
            self.assertTrue(sim.slots)
        self.assertIn((0, 1), app.simulator(None, "24ex").state)                 # the input, from the factory
        sim = app.simulator(app.DEMO_DUMP, "pro")
        self.assertEqual((sim.model, sim.state), (models.PRO, SimulatedAdi2.from_dump(app.DEMO_DUMP).state))

    def test_model_only_with_simulate(self):
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            app.main(["--model", "pro"])

    def test_an_icon_for_each_way_of_starting(self):
        for path in (app.ICON, app.SIMULATED_ICON):
            with open(path, "rb") as f:
                reserved, kind, count = struct.unpack("<HHH", f.read(6))
            self.assertEqual((reserved, kind, count), (0, 1, 9), path)          # an icon, 16 to 256 px

    def test_simulate_runs_without_errors(self):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        proc = subprocess.Popen([sys.executable, "-m", "commander.app", "--simulate"], cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(3)
        running = proc.poll() is None
        proc.kill()
        _, err = proc.communicate()
        self.assertTrue(running, err)
        self.assertEqual(err, "")


class MidiWarmUp(unittest.TestCase):
    """Windows' MIDI service started off the GUI thread: until then no device, not a window that hangs."""

    def test_no_device_while_the_first_winmm_call_waits(self):
        release, calls = threading.Event(), []

        def slow_list_ports():
            calls.append(threading.current_thread())
            release.wait(5)
            return [], []
        with mock.patch.object(connection, "list_ports", slow_list_ports):
            connection.warm_up()
            with self.assertRaisesRegex(connection.DeviceNotFound, "MIDI service"):
                connection.WinmmPort()
            release.set()
            self.assertTrue(connection._started.wait(5))
            with self.assertRaisesRegex(connection.DeviceNotFound, "no ADI-2 MIDI port"):
                connection.WinmmPort()                   # now it looks for the device
        self.assertIsNot(calls[0], threading.current_thread())


if __name__ == "__main__":
    unittest.main()
