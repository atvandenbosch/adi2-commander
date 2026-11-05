"""The simulator reproduces the device's behaviour, on a simulated clock."""

import unittest
from unittest import mock

from commander.device import codec, status
from commander.device.connection import DeviceNotFound, PortBusy
from commander.device.models import DAC, PRO, PRO_24
from commander.device.simulator import SimPort, SimulatedAdi2
from tests import client
from tests.client import Adi2, read_state
from tests.support import DUMP, PRESETS

F = codec.FREQ_INDICES
HEADER = codec.header(DAC.id)


def raw(*params, cmd=0x02):
    """One message with the given (address, index, value), bypassing the guards of build_messages."""
    return codec.sysex(DAC.id, [codec.encode(a, i, v, a in codec.EQ_ADDRESSES and i in F) for a, i, v in params], cmd)


class Clock:
    """The time of the simulator and of Adi2: sleeping moves it on at once."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    time = __call__

    def sleep(self, seconds):
        self.t += seconds


def simulated_clock(test):
    clock = Clock()
    patch = mock.patch.object(client, "time", clock)
    patch.start()
    test.addCleanup(patch.stop)
    return clock


class Simulator(unittest.TestCase):
    def setUp(self):
        self.clock = simulated_clock(self)
        self.sim = SimulatedAdi2.from_dump(DUMP, clock=self.clock)
        self.dev = Adi2(log=lambda *a: None, port=SimPort(self.sim))
        self.start = read_state(DUMP)

    def tearDown(self):
        self.dev.close()
        self.assertEqual(self.sim.unsimulated, [])

    def test_dump_is_byte_identical_to_the_real_one(self):
        self.dev.dump()
        real = [m for m in codec.read_dump(DUMP) if m[5] in (0x01, 0x05)]
        sent = [m for m in self.sim.received]
        self.assertEqual(sent, [HEADER + [0x03, 0x09, 0xF7]])
        self.dev.send(HEADER + [0x03, 0x09, 0xF7], pause=0.6)
        self.assertEqual([m for m in self.sim.poll() if m[5] != 0x07], real)

    def test_it_answers_only_under_its_own_device_id(self):
        pro = SimulatedAdi2.factory(PRO, clock=self.clock)
        pro.receive_from_remote(HEADER + [0x03, 0x09, 0xF7])
        self.clock.sleep(2.0)
        self.assertEqual(pro.poll(), [])                            # not even the status stream starts
        pro.receive_from_remote(codec.header(PRO.id) + [0x03, 0x09, 0xF7])
        self.clock.sleep(2.0)
        msgs = pro.poll()
        self.assertTrue(msgs)
        self.assertEqual({m[4] for m in msgs}, {PRO.id})
        self.assertIn(0x07, [m[5] for m in msgs])

    def test_write_is_not_confirmed_and_0x01_does_not_write(self):
        self.dev.dump()
        self.dev.send(raw((4, 4, -12)), pause=0)
        self.assertEqual(self.dev.collect(), [])                    # no echo
        self.dev.send(raw((4, 7, 6), cmd=0x01), pause=0)
        st = self.dev.dump()
        self.assertEqual((st[(4, 4)], st[(4, 7)]), (-12, self.start[(4, 7)]))

    def test_clamps_at_the_limits(self):
        self.dev.send(raw((4, 3, -1), (4, 16, 3), (4, 4, -25), (4, 13, 25), (4, 5, 19), (4, 14, 199),
                          (4, 18, 44), (5, 14, 150), (4, 6, 4), (4, 15, 51), (4, 19, 99), (4, 22, 151),
                          (4, 23, 16), (4, 25, 2990), (4, 26, 4)), pause=0)
        st = self.dev.dump()
        self.assertEqual([st[k] for k in [(4, 3), (4, 16), (4, 4), (4, 13), (4, 5), (4, 14), (4, 18), (5, 14),
                                          (4, 6), (4, 15), (4, 19), (4, 22), (4, 23), (4, 25), (4, 26)]],
                         [0, 2, -24, 24, 20, 200, 200, 200, 5, 50, 50, 150, 15, 3000, 5])

    def test_frequency_grid(self):
        self.dev.send(raw((4, 5, 2045), (4, 8, 12340), (4, 11, 2037)), pause=0)
        st = self.dev.dump()
        self.assertEqual((st[(4, 5)], st[(4, 8)], st[(4, 11)]), (2040, 12340, 2037))

    def test_reload_parameter_does_not_swallow_the_next_message(self):
        self.dev.send(raw((4, 2, 0)), pause=0)
        self.dev.send(raw((4, 22, 86)), pause=0)
        st = self.dev.dump()
        self.assertEqual((st[(4, 2)], st[(4, 22)]), (0, 86))

    def test_bass_treble_through_the_right_address_hits_the_shared_shelf(self):
        self.dev.send(raw((5, 21, 8)), pause=0)
        st = self.dev.dump()
        self.assertEqual(st[(4, 21)], 8)
        self.assertNotIn((5, 21), st)

    def test_dual_eq_off_aliases_right_to_left_and_on_copies_left_to_right(self):
        self.dev.write([(3, 11, 0, False)])
        st = self.dev.dump()
        self.assertTrue(all(st[(5, i)] == st[(4, i)] for i in range(2, 20)))
        self.dev.send(raw((5, 7, 6), (5, 11, 777)), pause=0)
        st = self.dev.dump()
        self.assertEqual((st[(4, 7)], st[(4, 11)]), (6, 777))       # writing "right" moved left
        self.dev.write([(3, 11, 1, False)])
        st = self.dev.dump()
        self.assertTrue(all(st[(5, i)] == st[(4, i)] for i in range(3, 20)))
        self.assertNotEqual(st[(5, 5)], self.start[(5, 5)])         # the old right setting is gone

    def test_preset_select_clear_manual_and_temp(self):
        self.dev.write([(4, 28, 22, False)], reload=True)
        st = self.dev.dump()
        self.assertEqual((st[(4, 5)], st[(4, 3)], st[(4, 16)], st[(3, 11)]), (100, 1, 1, 0))  # factory, Dual EQ off
        self.dev.write([(4, 4, 6, False)])
        self.assertEqual(self.dev.dump()[(4, 28)], 1)               # edited -> Temp
        self.dev.write([(4, 28, 0, False)], reload=True)
        st = self.dev.dump()
        self.assertEqual(st[(3, 11)], 1)                            # Manual brings its Dual EQ back
        self.assertEqual({k: st[k] for k in self.start if k[0] in (4, 5) and 3 <= k[1] <= 19},
                         {k: v for k, v in self.start.items() if k[0] in (4, 5) and 3 <= k[1] <= 19})

    def test_unknown_preset_content_is_reported_not_guessed(self):
        self.dev.send(raw((4, 28, 5)), pause=0)
        self.assertEqual(len(self.sim.unsimulated), 1)
        self.sim.unsimulated.clear()

    def test_auto_ref_level_follows_positive_gain(self):
        self.assertEqual((self.start[(3, 3)], self.start[(3, 2)], self.start[(3, 12)]), (1, 0, -205))
        self.assertEqual(self.start[(4, 5)], 60)
        self.dev.send(raw((4, 4, 24)), pause=0)                     # +12 dB at 60 Hz, -20.5 dB: Ref Level 2
        self.assertEqual(self.dev.dump()[(3, 2)], 2)

    def test_auto_ref_level_ignores_gain_between_400_and_5000_hz(self):
        self.dev.send(raw((4, 4, 0), (4, 5, 1000), (3, 12, -200)), pause=0)
        self.dev.send(raw((4, 4, 12)), pause=0)                     # +6 dB at 1000 Hz leaves Ref Level 0
        self.assertEqual(self.dev.dump()[(3, 2)], 0)
        self.dev.send(raw((4, 5, 390)), pause=0)                    # at 390 Hz it counts
        self.assertEqual(self.dev.dump()[(3, 2)], 1)

    def ref_level(self, *params):
        self.dev.send(raw(*params), pause=0)
        return self.dev.dump()[(3, 2)]

    def test_auto_ref_level_counts_a_band_only_with_the_eq_on(self):
        self.dev.send(raw((3, 11, 0)), pause=0)                                 # Dual EQ off: one EQ Enable
        self.dev.send(raw((3, 12, -160), (4, 5, 100)), pause=0)                 # Line Out is active
        self.assertEqual(self.ref_level((4, 2, 0), (4, 4, 12)), 1)              # +6 dB at 100 Hz, EQ off: -16 dB
        self.assertEqual(self.ref_level((4, 2, 1)), 2)                          # EQ on: -10 dB
        self.assertEqual(self.ref_level((4, 2, 0)), 1)

    def test_auto_ref_level_counts_bass_and_treble_while_bt_is_on(self):
        self.dev.send(raw((3, 12, -160), (4, 2, 0), (4, 20, 1)), pause=0)       # the EQ off: not needed
        self.assertEqual(self.ref_level((4, 21, 12)), 2)                        # Bass +6 dB at 85 Hz
        self.assertEqual(self.ref_level((4, 20, 0)), 1)                         # B/T Enable off
        self.assertEqual(self.ref_level((4, 20, 1), (4, 21, 0), (4, 24, 12)), 2)   # Treble +6 dB at 6500 Hz

    def test_auto_ref_level_adds_a_band_and_bass_at_the_low_end(self):
        self.dev.send(raw((3, 12, -160), (4, 2, 1), (4, 20, 1), (4, 5, 100)), pause=0)
        self.dev.send(raw(*[(a, g, 0) for a in (4, 5) for g in (4, 7, 10, 13, 17)]), pause=0)
        self.assertEqual(self.ref_level((4, 4, 12), (4, 21, 12)), 3)            # 6 + 6 dB: -4 dB
        self.assertEqual(self.ref_level((4, 21, 8)), 2)                         # 6 + 4 dB: -6 dB

    def test_lock_volume_refuses_a_volume_write(self):
        self.dev.write([(3, 13, 1, False)])
        self.dev.collect()
        self.dev.send(raw((3, 12, -300)), pause=0)
        msgs = self.dev.collect()                                   # the volume it keeps, unsolicited
        self.assertEqual([codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(msgs)],
                         [(3, 12, self.start[(3, 12)])])
        self.assertEqual(self.dev.dump()[(3, 12)], self.start[(3, 12)])

    def test_dim_lowers_the_reported_volume_and_a_volume_write_turns_it_off(self):
        v = self.start[(3, 12)]
        self.dev.write([(3, 16, 1, False)])
        self.assertEqual(self.dev.dump()[(3, 12)], v - 200)
        self.dev.write([(3, 16, 0, False)])
        self.assertEqual(self.dev.dump()[(3, 12)], v)
        self.dev.write([(3, 16, 1, False)])
        self.dev.collect()
        self.dev.send(raw((3, 12, v - 195)), pause=0)
        msgs = self.dev.collect()                                   # Dim off, unsolicited
        self.assertEqual([codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(msgs)], [(3, 16, 0)])
        st = self.dev.dump()
        self.assertEqual((st[(3, 12)], st[(3, 16)]), (v - 195, 0))

    def test_dim_moves_volume_only_on_the_active_output(self):
        v = self.start[(6, 12)]                                     # Phones, Line Out active
        self.dev.write([(6, 16, 1, False)])
        self.assertEqual(self.dev.dump()[(6, 12)], v)               # only the flag
        self.sim.plug(6)
        self.assertEqual(self.dev.dump()[(6, 12)], v)               # becoming active changes nothing
        self.dev.write([(6, 16, 0, False)])
        self.assertEqual(self.dev.dump()[(6, 12)], v)               # nor does off: Dim moved nothing
        self.dev.write([(6, 16, 1, False)])
        self.assertEqual(self.dev.dump()[(6, 12)], v - 200)         # active: Volume itself 20 dB down
        self.dev.write([(6, 16, 0, False)])
        self.assertEqual(self.dev.dump()[(6, 12)], v)               # and back up
        self.dev.write([(6, 16, 1, False)])
        self.sim.plug()
        self.dev.write([(6, 16, 0, False)])
        st = self.dev.dump()
        self.assertEqual((st[(6, 12)], st[(6, 16)]), (v - 200, 0))  # off once no longer active: it stays down

    def test_volume_clamps_at_minus_120_db(self):
        self.dev.send(raw((3, 12, -1300)), pause=0)
        self.assertEqual(self.dev.dump()[(3, 12)], -1200)

    def test_source_is_one_setting_for_all_outputs(self):
        self.dev.dump()
        self.dev.collect()
        self.dev.send(raw((6, 1, 1)), pause=0)                      # Phones only: SPDIF coax
        self.assertEqual([codec.to_hex(m) for m in self.dev.collect()],
                         ["f0 00 20 0d 71 01 48 20 01 18 20 01 61 70 02 f7"])    # 9/1, 3/1, 12/15
        self.dev.send(raw((6, 1, 1)), pause=0)
        self.assertEqual(self.dev.collect(), [])                    # nothing changed: nothing said
        self.dev.send(raw((3, 1, 2), (6, 1, 2), (9, 1, 2)), pause=0)    # all three: Optical
        msgs = self.dev.collect()
        self.assertEqual([codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(msgs)], [(12, 15, 3)])
        self.dev.send(raw((3, 1, 3)), pause=0)                      # USB
        st = self.dev.dump()
        self.assertEqual([st[k] for k in [(3, 1), (6, 1), (9, 1), (12, 15)]], [3, 3, 3, 1])

    def reports(self, *params):
        """Send one message; what the device reports unsolicited."""
        self.dev.collect()
        self.dev.send(raw(*params), pause=0)
        return [codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(self.dev.collect())]

    def test_switching_auto_ref_level_keeps_the_level(self):
        self.dev.dump()
        self.assertEqual(self.reports((3, 3, 0)), [(3, 12, -25)])     # -20.5 dBr at -5 dBu: -2.5 dB
        self.assertEqual(self.reports((3, 3, 1)), [(3, 12, -205)])
        self.assertEqual(self.reports((3, 12, -150)), [(3, 2, 1)])    # Auto: +1 dBu
        self.assertEqual(self.reports((3, 3, 0)), [(3, 12, -30)])
        self.assertEqual(self.reports((3, 3, 1)), [(3, 12, -150)])
        st = self.dev.dump()
        self.assertEqual((st[(3, 2)], st[(3, 12)]), (1, -150))

    def test_phones_have_auto_ref_level(self):
        self.dev.dump()
        self.assertEqual(self.reports((6, 3, 1)), [(6, 12, -250)])    # -10 dB at Lo-Power: 15 dB below Hi
        self.assertEqual(self.reports((6, 12, -150)), [])
        self.assertEqual(self.reports((6, 12, -140)), [(6, 2, 1)])    # Hi-Power above -15 dBr
        self.assertEqual(self.reports((6, 12, -150)), [(6, 2, 0)])
        self.reports((6, 2, 1))                                       # written: Volume moves 15 dB
        self.assertEqual(self.dev.dump()[(6, 12)], 0)
        self.reports((6, 2, 0))
        self.assertEqual(self.reports((6, 3, 0)), [(6, 12, 0)])

    def test_auto_ref_level_follows_band_gain_on_the_active_output(self):
        self.dev.write([(7, 2, 1, False), (6, 3, 1, False), (6, 12, -170, False)])     # Phones, not active
        self.assertEqual(self.reports((7, 4, 12), (7, 5, 60)), [])     # +6 dB at 60 Hz: not counted yet
        self.assertEqual(self.reports((6, 12, -165)), [(6, 2, 1)])    # a Volume write counts it: -10.5 dB
        self.reports((6, 12, -170), (7, 4, 0))
        self.reports((6, 12, -175))
        self.reports((7, 4, 12))
        self.dev.collect()
        self.sim.plug(6)                                              # Phones becomes active
        self.assertEqual([codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(self.dev.collect())],
                         [(6, 2, 1), (6, 12, -175)])
        self.assertEqual(self.reports((7, 5, 1000)), [(6, 2, 0), (6, 12, -175)])
        self.reports((7, 5, 60))
        self.sim.plug()                                               # inactive again: keeps Hi-Power
        self.assertEqual(self.dev.dump()[(6, 2)], 1)

    def test_auto_ref_level_is_in_the_report_of_a_source_choice(self):
        self.sim.plug(6)
        self.dev.write([(7, 2, 1, False), (6, 3, 1, False), (6, 12, -170, False), (7, 4, 12, False),
                        (7, 5, 60, False)])
        self.dev.collect()
        self.dev.send(raw((7, 28, 22)), pause=0)                      # clear: no gain, Lo-Power
        msgs = self.dev.collect()
        self.assertEqual(len(msgs), 1)
        self.assertEqual([codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(msgs)][:2],
                         [(6, 2, 0), (6, 12, -170)])                  # first, by index, as after clear

    def test_iem_ignores_ref_level_and_auto_ref_level(self):
        self.assertEqual(self.reports((9, 2, 1), (9, 3, 1)), [])
        st = self.dev.dump()
        self.assertEqual((st[(9, 2)], st[(9, 3)]), (-1, -1))

    def test_status_stream_starts_after_the_first_valid_message(self):
        self.assertEqual(self.sim.poll(), [])
        self.dev.send(raw((12, 2, 1)), pause=0)
        self.clock.sleep(1.8)
        self.assertEqual(self.dev.collect(), [])
        self.assertGreaterEqual(self.dev.n_status, 2)

    def test_front_panel_change_arrives_unsolicited(self):
        self.dev.dump()
        self.sim.front_panel([(4, 4, -10)])
        msgs = self.dev.collect()
        self.assertEqual([codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(msgs)], [(4, 4, -10)])
        # turning a knob sends every step as its own message
        self.sim.front_panel([(3, 12, -200), (3, 12, -195), (3, 12, -200), (3, 12, -205)])
        msgs = self.dev.collect()
        self.assertEqual([codec.to_hex(m) for m in msgs],
                         ["f0 00 20 0d 71 01 1b 1e 38 f7", "f0 00 20 0d 71 01 1b 1e 3d f7",
                          "f0 00 20 0d 71 01 1b 1e 38 f7", "f0 00 20 0d 71 01 1b 1e 33 f7"])

    def status(self):
        """The data bytes of the last status message, and the parameter messages beside it."""
        self.clock.sleep(1.1)
        msgs = self.sim.poll()
        return ([m[6:-1] for m in msgs if m[5] == 0x07][-1],
                [codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(msgs)])

    def test_status_message_as_the_device_sends_it(self):
        def body(text):
            return [int(x, 16) for x in text.split()]
        self.dev.dump()
        self.assertEqual(self.status()[0], body("08 30 7e 08 00 00 00 42 00 00 02 02 00 00"))   # USB, 48 kHz
        self.sim.signal(usb=192000)
        self.assertEqual(self.status(), (body("08 30 7e 28 00 00 00 42 00 00 02 0a 00 00"), [(12, 16, 5)]))
        self.sim.plug(9)
        self.assertEqual(self.status()[0][:5], body("0a 30 7e 28 40"))                         # IEM active
        self.sim.plug()
        self.dev.write([(3, 1, 2, False)])                                                     # source Optical
        self.sim.signal(coax=44100, usb=48000)
        self.sim.signal(optical=48000, usb=768000)
        self.assertEqual(self.status()[0], body("08 1a 43 08 00 00 00 42 00 00 02 12 00 00"))
        self.dev.write([(3, 1, 1, False)])                                                     # source Coax
        self.sim.signal(coax=44100, optical=48000, usb=48000)
        self.assertEqual(self.status(), (body("08 57 42 04 00 00 00 41 00 00 02 02 00 00"), [(12, 16, 0)]))
        self.dev.write([(3, 1, 3, False)])                                                     # source USB
        self.sim.signal(optical=48000, usb=176400, dsd=True)                                   # DSD over USB
        self.assertEqual(self.status()[0], body("08 12 42 24 00 0c 00 41 00 70 02 09 00 00"))

    def test_a_chosen_input_without_signal_leaves_the_device_on_usb(self):
        self.dev.dump()
        self.dev.write([(3, 1, 1, False)])                                                     # source Coax
        self.sim.signal(usb=96000)
        body, params = self.status()
        self.assertEqual((body[1] & 0x40, body[3] >> 3, params), (0, 3, [(12, 16, 3)]))       # own clock, 96 kHz
        self.sim.signal(optical=44100)
        self.dev.write([(3, 1, 2, False)])                                                     # source Optical
        self.assertEqual((self.status()[0][3] >> 3, self.sim.state[(12, 16)]), (0, 0))              # 44.1 kHz

    def test_auto_takes_the_first_signal_on_spdif_and_keeps_it(self):
        def clock():
            body = self.status()[0]
            return "coax" if body[1] & 0x40 else "optical" if body[2] & 0x01 else None
        self.dev.dump()                                                                        # source Auto
        self.sim.signal(optical=48000)
        self.assertEqual(clock(), "optical")
        self.sim.signal(coax=44100, optical=48000)
        self.assertEqual(clock(), "optical")                                                   # kept
        self.sim.signal(coax=44100)
        self.assertEqual(clock(), "coax")                                                      # optical gone
        self.sim.signal()
        self.assertEqual(clock(), None)                                                        # USB
        self.sim.signal(coax=44100, optical=48000)                                             # both at once
        self.status()
        self.assertEqual(self.sim.unsimulated, ["source Auto: a signal on coax and optical at once"])
        self.sim.unsimulated.clear()

    def test_port_found_absent_or_busy(self):
        self.assertEqual(self.dev.ports[0][:9], "ADI-2 DAC")
        with self.assertRaises(DeviceNotFound):
            SimPort(self.sim, present=False)
        with self.assertRaises(PortBusy):
            SimPort(self.sim, busy=True)


LEFT_KEYS = list(range(3, 20)) + list(range(21, 27))


class Presets(unittest.TestCase):
    """EQ presets, Manual, Temp and the source, on the slots of the demo."""

    def setUp(self):
        self.clock = simulated_clock(self)
        self.sim = SimulatedAdi2.from_dump(DUMP, presets=PRESETS, clock=self.clock)
        self.dev = Adi2(log=lambda *a: None, port=SimPort(self.sim))
        self.dev.dump()                                             # opens the session

    def tearDown(self):
        self.dev.close()
        self.assertEqual(self.sim.unsimulated, [])

    def read(self, slot):
        self.dev.collect()
        self.dev.send(HEADER + [0x03, 0x09 + slot, 0xF7], pause=0.2)
        return self.dev.collect()

    def slot(self, slot):
        msgs = self.read(slot)
        vals = {codec.decode_triplet(*t)[:2]: codec.decode_triplet(*t)[2] for t in codec.parameter_triplets(msgs)}
        names = [bytes(m[7:-1]) for m in msgs if m[5] == 0x05]
        return vals, names[0]

    def transfer(self, slot, left, right, dual=0, name=None):
        """Name, left, right, then the flag word on 13/2."""
        if name is not None:
            self.dev.send(HEADER + [0x06, slot] + list(name.rjust(14).encode()) + [0, 0] + [0xF7], pause=0)
        self.dev.send(raw(*[(13, i, left[i]) for i in LEFT_KEYS]), pause=0)
        self.dev.send(raw(*[(14, i, right[i]) for i in range(3, 20)]), pause=0)
        self.dev.send(raw((13, 2, (slot - 1) << 4 | dual)), pause=0)

    def contents(self, slot):
        vals, _ = self.slot(slot)
        return ({i: vals[(13, i)] for i in LEFT_KEYS}, {i: vals[(14, i)] for i in range(3, 20)})

    def live(self, left):
        st = self.dev.dump()
        return {i: st[(left, i)] for i in range(3, 20)}

    def test_answers_are_byte_identical_to_the_real_ones(self):
        real, n = {}, None
        with open(PRESETS, encoding="utf-8") as f:
            for line in f:
                if line.startswith("=== slot"):
                    n = int(line.split()[-1])
                    real[n] = []
                elif n and line.strip():
                    real[n].append([int(x, 16) for x in line.split()])
        for slot in range(1, 21):
            self.assertEqual(self.read(slot), real[slot], "slot %d" % slot)

    def test_transfer_writes_a_slot_with_its_name(self):
        left, right = self.contents(1)
        left[4], right[7] = -6, 5
        self.transfer(19, left, right, dual=1, name="Test")
        self.assertEqual(self.contents(19), (left, right))
        vals, name = self.slot(19)
        self.assertEqual((vals[(13, 1)], name), (18 << 4 | 1, b"          Test\x00\x00"))

    def test_without_a_name_the_name_is_empty_and_a_name_alone_does_nothing(self):
        left, right = self.contents(1)
        self.transfer(19, left, right)
        self.assertEqual(self.slot(19)[1], bytes(16))
        self.dev.send(HEADER + [0x06, 19] + list(b"     Alone    ") + [0, 0, 0xF7], pause=0)
        self.assertEqual(self.slot(19)[1], bytes(16))

    def test_the_flag_word_on_index_1_does_nothing(self):
        before = self.contents(19)
        left, right = self.contents(1)
        self.dev.send(raw(*[(13, i, left[i]) for i in LEFT_KEYS]), pause=0)
        self.dev.send(raw(*[(14, i, right[i]) for i in range(3, 20)]), pause=0)
        self.dev.send(raw((13, 1, 18 << 4)), pause=0)
        self.assertEqual(self.contents(19), before)
        self.sim.pending.clear()

    def test_select_loads_the_slot_and_its_dual_eq(self):
        left, right = self.contents(1)
        left[4], right[4] = -6, 3
        self.transfer(20, left, right, dual=1)
        st = self.dev.write([(7, 28, 21, False)], reload=True)
        self.assertEqual(({i: st[(7, i)] for i in range(3, 20)}, st[(6, 11)]), ({i: left[i] for i in range(3, 20)}, 1))
        self.assertEqual({i: st[(8, i)] for i in range(3, 20)}, right)

    def test_an_unused_slot_loads_the_factory_bands_and_stays_unused(self):
        self.dev.write([(7, 4, -6, False)])
        self.dev.collect()
        self.dev.send(raw((7, 28, 6)), pause=0.1)                   # Preset 5: unused in the reading
        said = [codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(self.dev.collect())]
        st = self.dev.dump()
        self.assertEqual((st[(7, 28)], st[(7, 4)], st[(7, 5)], st[(6, 11)]), (6, 0, 100, 0))
        self.assertIn((7, 4, 0), said)                              # what changed, said unasked
        self.assertNotIn(28, [i for a, i, v in said])
        self.assertEqual(self.read(5)[0], raw((13, 1, 4 << 4 | 0x0F), cmd=0x01))
        st = self.dev.write([(7, 28, 0, False)], reload=True)
        self.assertEqual(st[(7, 4)], -6)

    def test_the_jump_to_temp_with_dual_eq_on_says_only_the_source(self):
        left, right = self.contents(1)
        self.transfer(19, left, right, dual=1)
        self.dev.write([(7, 28, 20, False)], reload=True)
        self.dev.collect()
        self.dev.send(raw((8, 8, 650)), pause=0.1)
        self.assertEqual([codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(self.dev.collect())],
                         [(7, 28, 1)])

    def test_a_source_choice_says_what_changed_and_nothing_when_nothing_did(self):
        self.dev.write([(7, 4, -6, False)])                         # a mark in Manual
        self.dev.write([(6, 11, 0, False)])
        self.dev.write([(7, 28, 22, False)], reload=True)           # clear
        self.dev.collect()
        self.dev.send(raw((7, 28, 22)), pause=0.1)                  # clear again: nothing changes
        self.assertEqual(self.dev.collect(), [])
        self.dev.send(raw((7, 28, 0)), pause=0.1)                   # Manual: the mark comes back, said unasked
        msgs = self.dev.collect()
        self.assertEqual(len(msgs), 1)
        self.assertIn((7, 4, -6), [codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(msgs)])

    def test_what_makes_temp(self):
        self.dev.write([(7, 28, 2, False)], reload=True)            # Preset 1 on Phones
        st = self.dev.dump()
        for params, source in [([(7, 2, 1 - st[(7, 2)])], 2),       # EQ Enable: stays
                               ([(7, 20, 1 - st[(7, 20)])], 2),     # B/T Enable: stays
                               ([(7, 21, 4)], 2),                   # Bass with Load B/T off: stays
                               ([(7, 4, st[(7, 4)])], 2),           # the value that was there: stays
                               ([(7, 4, st[(7, 4)] + 2)], 1)]:      # a band: Temp
            self.dev.send(raw(*params), pause=0)
            self.assertEqual(self.dev.dump()[(7, 28)], source, params)

    def test_the_device_reports_the_jump_to_temp(self):
        self.dev.write([(7, 28, 2, False)], reload=True)
        self.dev.write([(6, 11, 0, False)])                         # Dual EQ off: that already makes Temp
        self.dev.write([(7, 28, 2, False)], reload=True)
        self.dev.collect()
        self.dev.send(raw((8, 8, 640)), pause=0.1)                  # right address, shared L/R
        got = [[codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets([m])] for m in self.dev.collect()]
        self.assertEqual(got, [[(7, 8, 640)], [(7, 28, 1)]])        # the other side, then the source

    def test_clear_with_load_bt_on_loads_the_factory_shelves_and_switches_them_on(self):
        self.dev.write([(7, 27, 1, False)])
        self.dev.write([(7, 20, 0, False), (7, 21, 6, False), (7, 22, 60, True)])
        self.dev.collect()
        self.dev.send(raw((7, 28, 22)), pause=0.1)
        said = [codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(self.dev.collect())]
        self.assertIn((7, 20, 1), said)                             # B/T Enable, said unasked
        st = self.dev.dump()
        self.assertEqual([st[(7, i)] for i in range(20, 27)], [1, 0, 85, 9, 0, 6500, 7])
        st = self.dev.write([(7, 28, 0, False)], reload=True)       # Manual brings its own back
        self.assertEqual((st[(7, 21)], st[(7, 22)]), (6, 60))

    def test_manual_keeps_its_bass_treble_while_load_bt_is_off(self):
        self.dev.write([(7, 27, 1, False)])
        self.dev.write([(7, 21, 6, False)])                         # Y: Manual's own
        self.dev.write([(7, 27, 0, False)])
        self.dev.write([(7, 21, -2, False)])                        # Z: the output's, not Manual's
        self.dev.write([(7, 27, 1, False)])
        self.dev.write([(7, 28, 5, False)], reload=True)
        st = self.dev.write([(7, 28, 0, False)], reload=True)
        self.assertEqual(st[(7, 21)], 6)

    def test_slot_values_outside_the_range_are_reported(self):
        left, right = self.contents(1)
        left[4] = -30
        self.transfer(19, left, right)
        self.assertEqual(len(self.sim.unsimulated), 1)
        self.sim.unsimulated.clear()

    def test_load_bt_makes_bass_treble_part_of_the_source(self):
        self.dev.write([(7, 27, 1, False)])
        self.dev.write([(7, 28, 2, False)], reload=True)
        self.dev.send(raw((7, 21, 4)), pause=0)
        self.assertEqual(self.dev.dump()[(7, 28)], 1)

    def test_load_bt_switches_bt_enable_off_except_on_line_out(self):
        self.dev.write([(4, 20, 1, False), (7, 20, 1, False), (10, 20, 1, False)])
        self.dev.collect()
        self.dev.send(raw((7, 27, 1)), pause=0.1)
        self.assertEqual([codec.decode_triplet(*t)[:3] for t in codec.parameter_triplets(self.dev.collect())],
                         [(7, 20, 0)])                              # said unasked
        st = self.dev.write([(4, 27, 1, False), (10, 27, 1, False)])
        self.assertEqual((st[(4, 20)], st[(7, 20)], st[(10, 20)]), (1, 0, 0))

    def test_rewriting_a_source_slot_reaches_only_the_active_output(self):
        self.dev.write([(4, 28, 5, False)], reload=True)            # Line and Phones on Preset 4
        self.dev.write([(7, 28, 5, False)], reload=True)
        old = self.live(7)
        left, right = self.contents(4)
        left[7], left[10], right[7], right[10] = -2, -6, -2, -6
        self.dev.collect()
        self.transfer(4, left, right, dual=0)
        self.clock.sleep(0.1)
        reported = [codec.decode_triplet(*t)[:2] for t in codec.parameter_triplets(self.dev.collect())]
        self.assertIn((4, 10), reported)                            # the device says so itself
        self.assertEqual(self.live(4)[10], -6)                      # Line, active, follows
        self.assertEqual(self.live(7), old)                         # Phones keeps its copy
        self.assertEqual(self.dev.dump()[(7, 28)], 5)               # ... and still says Preset 4
        self.sim.plug(6)                                            # Phones becomes active: no reload
        self.assertEqual(self.live(7), old)
        self.transfer(4, *self.contents(1))                         # now Phones follows, Line does not
        self.assertEqual(self.live(7), {i: self.contents(1)[0][i] for i in range(3, 20)})
        self.assertEqual(self.live(4)[10], -6)

    def test_standby_keeps_what_sounds(self):
        self.dev.write([(4, 4, -9, False)])                         # a mark in Manual of Line
        self.dev.write([(7, 28, 2, False)], reload=True)            # Phones: Preset 1
        self.dev.write([(10, 28, 4, False)], reload=True)           # IEM: Preset 3, then edited: Temp
        self.dev.write([(10, 4, 3, False)])
        line, phones, iem = self.live(4), self.live(7), self.live(10)
        self.dev.close()
        self.sim.power(False)
        self.sim.power(True)
        self.dev = Adi2(log=lambda *a: None, port=SimPort(self.sim))
        st = self.dev.dump()
        self.assertEqual((st[(4, 28)], st[(7, 28)], st[(10, 28)]), (0, 2, 0))   # Temp became Manual
        self.assertEqual((self.live(4), self.live(7), self.live(10)), (line, phones, iem))
        st = self.dev.write([(7, 28, 0, False)], reload=True)       # Manual of Phones is now Preset 1
        self.assertEqual({i: st[(7, i)] for i in range(3, 20)}, phones)
        st = self.dev.write([(10, 28, 1, False)], reload=True)      # Temp is empty: flat
        self.assertEqual((st[(10, 4)], st[(10, 5)]), (0, 100))

    def test_there_is_always_a_temp(self):
        st = self.dev.write([(4, 28, 1, False)], reload=True)       # Line: Temp, before any preset was edited
        self.assertEqual(st[(4, 28)], 1)
        self.assertEqual((st[(4, 4)], st[(4, 5)], st[(3, 11)]), (0, 100, 0))   # as after power on: flat, no Dual EQ

    def test_standby_with_load_bt_on(self):
        left, right = self.contents(1)
        left.update({21: 4, 22: 70, 23: 11, 24: -2, 25: 7000, 26: 9})                  # X
        self.transfer(19, left, right, dual=1)
        self.dev.write([(10, 27, 1, False)])
        self.dev.write([(10, 21, -4, False), (10, 22, 100, True)])  # Y: Manual's own
        self.dev.write([(10, 28, 20, False)], reload=True)          # IEM sounds Preset 19: Dual on, B/T X
        self.dev.close()
        self.sim.power(False)
        self.sim.power(True)
        self.dev = Adi2(log=lambda *a: None, port=SimPort(self.sim))
        st = self.dev.write([(10, 28, 0, False)], reload=True)      # Manual is what sounded
        self.assertEqual((st[(9, 11)], st[(10, 21)], st[(10, 22)]), (1, 4, 70))
        st = self.dev.write([(10, 28, 1, False)], reload=True)      # Temp is the factory state
        self.assertEqual((st[(9, 11)], [st[(10, i)] for i in range(21, 27)]), (0, [0, 85, 9, 0, 6500, 7]))

    def test_asking_again_before_the_answer_is_complete_is_reported(self):
        self.dev.send(HEADER + [0x03, 0x0A, 0xF7], pause=0)
        self.dev.send(HEADER + [0x03, 0x0B, 0xF7], pause=0)
        self.assertEqual(len(self.sim.unsimulated), 1)
        self.sim.unsimulated.clear()


class OtherModels(unittest.TestCase):
    """The ADI-2 Pro and ADI-2/4 Pro SE and EX, from their factory values."""

    MODELS = {"Pro": (PRO, None), "2/4 SE": (PRO_24, 0), "2/4 EX": (PRO_24, 1)}

    def setUp(self):
        self.clock = simulated_clock(self)

    def use(self, name):
        model, revision = self.MODELS[name]
        self.sim = SimulatedAdi2.factory(model, revision, presets=PRESETS, clock=self.clock)
        self.addCleanup(lambda sim=self.sim: self.assertEqual(sim.unsimulated, []))
        return self.sim

    def send(self, *params):
        self.sim.receive_from_remote(codec.sysex(self.sim.model.id, [
            codec.encode(a, i, v, a in codec.EQ_ADDRESSES and i in F) for a, i, v in params]))

    def dump(self):
        self.sim.receive_from_remote(codec.header(self.sim.model.id) + [0x03, 0x09, 0xF7])
        self.clock.sleep(2.0)
        return self.sim.poll()

    def test_a_dump_holds_every_parameter_the_table_names(self):
        for name, (model, revision) in self.MODELS.items():
            with self.subTest(name):
                sim = self.use(name)
                msgs = self.dump()
                params = [m for m in msgs if m[5] == 0x01]
                self.assertTrue(all(len(m) <= 256 for m in params))
                self.assertEqual(client.parse(params), sim.reported())
                for a, ranges in [(0, sim.tables.input), (12, sim.tables.device)] + list(sim.tables.outputs.items()):
                    for i, (lo, hi, value) in ranges.items():
                        self.assertTrue(lo <= sim.state[(a, i)] == value <= hi, (a, i))
                self.assertEqual([m[6] for m in msgs if m[5] == 0x05], list(range(0x21, 0x2A)))
                body = [m for m in msgs if m[5] == 0x07][0][6:-1]
                st = status.decode(body)
                self.assertEqual((len(body), st.revision, st.rate, st.usb_rate, st.output),
                                 (14, revision or 0, 48000, 48000, 1))                 # Line Out active

    def test_the_ranges_of_each_model(self):
        writes = [(9, 2, 9), (3, 2, 9), (3, 9, 9), (6, 17, 12), (0, 1, -9), (0, 10, 9)]
        expect = {"Pro": [1, 3, 5, 9, 0, 3], "2/4 SE": [2, 4, 6, 9, 0, 1], "2/4 EX": [2, 4, 6, 9, -6, 2]}
        for name, values in expect.items():
            with self.subTest(name):
                sim = self.use(name)
                self.send(*writes)
                self.assertEqual([sim.state[(a, i)] for a, i, _ in writes], values)

    def test_rear_trs_source_and_dsd_direct(self):
        sim = self.use("2/4 SE")
        self.send((9, 19, 1))
        self.assertEqual(sim.state[(9, 19)], 1)
        self.send((3, 19, 1), (12, 5, 1))
        self.assertEqual(sim.unsimulated, ["output address 3 index 19", "device index 5"])
        sim.unsimulated.clear()
        sim = self.use("Pro")
        self.send((12, 5, 1))
        self.assertEqual(sim.state[(12, 5)], 1)

    def test_source_has_one_choice_more_in_basic_mode_dac(self):
        for name, before, after in (("Pro", 5, 6), ("2/4 SE", 5, 6), ("2/4 EX", 6, 6)):
            with self.subTest(name):
                sim = self.use(name)
                self.send((3, 1, 9))
                self.send((12, 6, 5), (6, 1, 9))
                self.assertEqual((sim.state[(3, 1)], sim.state[(6, 1)]), (before, after))

    def test_what_only_the_dac_fs_is_known_to_do_it_does_not(self):
        sim = self.use("2/4 SE")
        self.dump()
        clock_source = sim.state[(12, 15)]
        self.send((3, 1, 4))                                        # Source on one output, nothing else
        self.send((3, 12, 60), (6, 2, 0), (6, 12, 0))               # Auto Ref Level is on: Ref Level stays
        self.send((7, 27, 1))                                       # Load B/T: B/T Enable stays on
        self.clock.sleep(0.1)
        self.assertEqual([m for m in sim.poll() if m[5] != 0x07], [])
        self.assertEqual([sim.state[k] for k in [(6, 1), (9, 1), (12, 15), (3, 2), (6, 2), (7, 20)]],
                         [0, 0, clock_source, 1, 0, 1])

    def test_the_input_eq_is_not_simulated_yet(self):
        sim = self.use("Pro")
        self.send((1, 4, 6))
        self.assertEqual(sim.unsimulated, ["input EQ address 1 index 4"])
        sim.unsimulated.clear()

    def test_the_eq_and_presets_follow_the_rules_of_the_dac_fs(self):
        sim = self.use("Pro")
        self.dump()
        self.send((4, 28, 2))                                       # Preset 1
        self.assertEqual(sim.state[(4, 4)], sim.slots[1]["vals"][(13, 4)])
        self.clock.sleep(0.1)
        sim.poll()
        self.send((4, 7, 3))                                        # edited: Temp, and the device says so
        self.clock.sleep(0.1)
        self.assertEqual(client.parse([m for m in sim.poll() if m[5] == 0x01]).get((4, 28)), 1)

    def test_the_dac_fs_has_no_factory_values_here(self):
        with self.assertRaises(ValueError):
            SimulatedAdi2.factory(DAC)


if __name__ == "__main__":
    unittest.main()
