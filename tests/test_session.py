"""The session against the simulator, on a simulated clock: connect, load, follow, write, verify, read the
preset slots, recover."""

import unittest

from unittest import mock

from commander.device import codec, models, simulator
from commander.device import params as P
from commander.device.connection import PortBusy
from commander.device.models import DAC, PRO, PRO_24
from commander.session import Session, loaded
from commander.device.simulator import SimPort, SimulatedAdi2
from tests.support import DUMP, PRESETS


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Harness(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sim = SimulatedAdi2.from_dump(DUMP, presets=PRESETS, clock=self.clock)
        self.busy = False
        self.session = Session(self.open_port, clock=self.clock)
        self.events = []
        self.session.on_connection.append(lambda s, d: self.events.append(("connection", s)))
        self.session.on_changed.append(lambda keys, origin: self.events.append(("changed", origin, tuple(keys))))
        self.session.on_verified.append(lambda r: self.events.append(("verified", r)))
        self.slot_events = []
        self.session.on_slots.append(self.slot_events.append)

    def tearDown(self):
        self.session.close()
        self.assertEqual(self.sim.unsimulated, [])

    def open_port(self):
        if self.busy:
            raise PortBusy("busy (simulated)")
        return SimPort(self.sim)

    def run_for(self, seconds, step=0.02):
        end = self.clock.t + seconds
        while self.clock.t < end:
            self.clock.t += step
            self.session.tick()

    def connect(self):
        self.run_for(1.0)
        self.assertEqual(self.session.status, "ready")
        self.events.clear()

    def statuses(self):
        return [e[1] for e in self.events if e[0] == "connection"]

    def verified(self):
        return [e[1] for e in self.events if e[0] == "verified"]


class Connect(Harness):
    def test_loads_the_device_state(self):
        self.run_for(1.0)
        self.assertEqual(self.statuses(), ["loading", "ready"])
        rep = self.sim.reported()
        self.assertEqual({k: v for k, v in self.session.state.items()},
                         {k: v for k, v in rep.items() if k[0] not in (13, 14)})

    def test_searching_while_off_then_connects(self):
        self.sim.power(False)
        self.run_for(5.0)
        self.assertEqual(self.statuses(), ["searching"])
        self.sim.power(True)
        self.run_for(3.0)
        self.assertEqual(self.statuses(), ["searching", "loading", "ready"])

    def test_busy_port_is_retried(self):
        self.busy = True
        self.run_for(3.0)
        self.assertEqual(self.statuses(), ["busy"])
        self.busy = False
        self.run_for(3.0)
        self.assertEqual(self.statuses(), ["busy", "loading", "ready"])

    def test_device_gone_drops_the_queue_and_comes_back(self):
        self.connect()
        self.sim.power(False)
        self.session.set((4, 4), 0)
        self.run_for(5.0)
        self.assertIn("searching", self.statuses())
        self.assertEqual((self.session.pending, self.session.sent, self.session.state), ({}, {}, {}))
        self.sim.power(True)
        self.run_for(3.0)
        self.assertEqual(self.session.status, "ready")

    def test_device_gone_before_the_read_back(self):
        self.connect()
        self.session.set((4, 4), -12)
        self.run_for(0.1)
        self.assertEqual(self.session.sent, {(4, 4): -12})       # sent, not yet verified
        self.sim.power(False)
        self.run_for(1.0)
        self.assertEqual((self.session.pending, self.session.sent, self.verified()), ({}, {}, []))
        self.sim.power(True)
        self.run_for(3.0)
        self.assertEqual(self.session.status, "ready")
        self.assertEqual(self.session.state[(4, 4)], self.sim.state[(4, 4)])
        self.assertEqual(self.verified(), [])

    def test_standby_is_noticed_within_half_a_second(self):
        self.connect()
        self.sim.power(False)
        self.run_for(0.6)
        self.assertEqual(self.statuses(), ["searching"])


class Recognition(Harness):
    """The model is the device ID that answers; the port name only says which to ask first."""

    def use(self, model, port=None):
        if model in (PRO, PRO_24):
            self.sim = SimulatedAdi2.factory(model, presets=PRESETS, clock=self.clock)
        else:
            self.sim = SimulatedAdi2.from_dump(DUMP, presets=PRESETS, clock=self.clock, model=model)
        self.port_name = port

    def open_port(self):
        port = SimPort(self.sim)
        if getattr(self, "port_name", None):
            port.names = (self.port_name, self.port_name)
        return port

    def asked(self):
        """The device IDs dump requests went to, in order."""
        return [m[4] for m in self.sim.received if m[5:] == [0x03, 0x09, 0xF7]]

    def test_the_port_name_is_a_hint(self):
        self.assertEqual(models.probe_order("ADI-2 DAC Midi Port 1"), [DAC, PRO, PRO_24])
        self.assertEqual(models.probe_order("ADI-2 Pro Midi Port 1"), [PRO, DAC, PRO_24])
        self.assertEqual(models.probe_order("ADI-24 Pro Midi Port 1"), [PRO_24, DAC, PRO])
        self.assertEqual(models.probe_order("ADI-2"), [DAC, PRO, PRO_24])

    def test_the_dac_is_asked_once(self):
        self.connect()
        self.assertEqual((self.session.model, self.asked()), (DAC, [DAC.id]))

    def recognised(self, model):
        self.use(model)
        self.run_for(3.0)
        self.assertEqual(self.statuses(), ["loading", "ready"])
        self.assertEqual((self.session.model, self.asked()), (model, [model.id]))

    def test_a_pro_is_recognised(self):
        self.recognised(PRO)

    def test_a_2_4_is_recognised(self):
        self.recognised(PRO_24)

    def test_a_model_that_is_not_supported_is_named_and_let_go(self):
        with mock.patch.dict(models.BY_ID, {PRO.id: PRO._replace(supported=False)}):
            self.use(PRO)
            self.run_for(3.0)
        self.assertEqual(self.statuses(), ["loading", "unsupported"])
        self.assertEqual((self.session.model.name, self.asked()), (PRO.name, [PRO.id]))
        self.assertIsNone(self.session.port)                             # free for other programs

    def test_past_a_port_name_that_does_not_fit(self):
        self.use(PRO, port="ADI-2 DAC Midi Port 1")
        self.run_for(3.0)
        self.assertEqual((self.session.status, self.asked()), ("ready", [DAC.id, PRO.id]))

    def test_a_dac_behind_another_port_name(self):
        self.use(DAC, port="ADI-24 Pro Midi Port 1")
        self.run_for(3.0)
        self.assertEqual((self.session.status, self.asked()), ("ready", [PRO_24.id, DAC.id]))

    def test_a_late_answer_still_counts(self):
        with mock.patch.object(simulator, "DUMP_FIRST", 1.2), mock.patch.object(simulator, "STATUS_FIRST", 1.2):
            self.run_for(3.0)
        self.assertEqual(self.session.status, "ready")
        self.assertEqual((self.session.model, self.asked()), (DAC, [DAC.id, PRO.id, DAC.id]))
        self.assertEqual(self.session.state, {k: v for k, v in self.sim.reported().items() if k[0] not in (13, 14)})

    def test_unsupported_until_it_is_gone(self):
        with mock.patch.dict(models.BY_ID, {PRO.id: PRO._replace(supported=False)}):
            self.use(PRO)
            self.run_for(3.0)
            self.run_for(10.0)
        self.assertEqual((self.statuses(), self.asked()), (["loading", "unsupported"], [PRO.id]))   # not asked again
        self.sim.power(False)
        self.run_for(0.6)
        self.assertEqual(self.statuses()[-1], "searching")
        self.use(DAC)
        self.run_for(3.0)
        self.assertEqual((self.session.status, self.session.model), ("ready", DAC))

    def test_no_answer_under_any_id(self):
        self.use(DAC._replace(id=0x7F, name="Other"))
        self.run_for(3.5)
        self.assertEqual(self.statuses(), ["loading", "searching"])
        self.assertEqual(self.asked(), [DAC.id, PRO.id, PRO_24.id])
        self.assertIsNone(self.session.model)
        self.run_for(2.0)
        self.assertEqual(self.statuses(), ["loading", "searching", "loading"])        # and on looking


class DeviceStatus(Harness):
    def setUp(self):
        super().setUp()
        self.reports = []
        self.session.on_device_status.append(self.reports.append)

    def test_the_status_message_is_followed(self):
        self.connect()
        self.assertEqual((self.session.device_status.output, self.session.device_status.rate), (0, 48000))
        self.reports.clear()
        self.sim.plug(6)
        self.run_for(1.1)
        self.run_for(1.1)
        self.assertEqual([(s.output, s.phones) for s in self.reports], [(1, True)])     # once, when it changed

    def test_a_new_rate_comes_with_its_parameter(self):
        self.connect()
        self.sim.signal(usb=96000)
        self.run_for(1.1)
        self.assertEqual((self.session.device_status.rate, self.session.state[(12, 16)]), (96000, 3))

    def test_gone_with_the_device(self):
        self.connect()
        self.sim.power(False)
        self.run_for(1.0)
        self.assertEqual((self.session.device_status, self.reports[-1]), (None, None))


class Write(Harness):
    def test_write_is_verified(self):
        self.connect()
        self.session.set((4, 4), -12)
        self.assertEqual(self.events[0], ("changed", "write", ((4, 4),)))
        self.run_for(2.0)
        self.assertEqual(self.sim.state[(4, 4)], -12)
        self.assertEqual(self.verified(), [{(4, 4): (-12, -12)}])

    def test_bundled_and_rate_limited(self):
        self.connect()
        for v in range(-10, 0):
            self.session.set((4, 4), v)
            self.session.set((4, 7), v)
            self.run_for(0.03)
        self.run_for(2.0)
        writes = [m for m in self.sim.received if m[5] == 0x02]
        self.assertLessEqual(len(writes), 3)                     # 0.3 s of edits, at most ~6 per second
        self.assertEqual((self.sim.state[(4, 4)], self.sim.state[(4, 7)]), (-1, -1))
        self.assertEqual(self.verified(), [{(4, 4): (-1, -1), (4, 7): (-1, -1)}])

    def test_mismatch_is_reported(self):
        self.connect()
        original = self.sim._set_eq
        self.sim._set_eq = lambda a, i, v, f: original(a, i, v - 2 if (a, i) == (4, 7) else v, f)
        self.session.set((4, 7), -6)
        self.run_for(2.0)
        self.assertEqual(self.verified(), [{(4, 7): (-6, -8)}])
        self.assertEqual(self.session.state[(4, 7)], -8)        # the device is the truth

    def test_dual_eq_off_keeping_left(self):
        self.connect()
        left = {i: self.sim.state[(4, i)] for i in range(3, 20)}
        self.session.set_dual(3, False, keep="left")
        self.run_for(2.0)
        self.assertEqual(self.sim.state[(3, 11)], 0)
        self.assertEqual({i: self.sim.state[(4, i)] for i in range(3, 20)}, left)
        self.assertEqual([r for r in self.verified() if any(s != a for s, a in r.values())], [])

    def test_dual_eq_off_keeping_right(self):
        self.connect()
        right = {i: self.sim.state[(5, i)] for i in range(3, 20)}
        self.session.set_dual(3, False, keep="right")
        self.run_for(2.0)
        self.assertEqual(self.sim.state[(3, 11)], 0)
        self.assertEqual({i: self.sim.state[(4, i)] for i in range(3, 20)}, right)   # the shared set is right's
        self.assertEqual({i: self.session.state[(5, i)] for i in range(3, 20)}, right)
        self.assertEqual([r for r in self.verified() if any(s != a for s, a in r.values())], [])

    def test_dual_eq_off_keeping_right_keeps_its_eq_enable(self):
        self.connect()
        self.sim.front_panel([(5, 2, 0)])                        # front panel L: the right EQ is off
        self.run_for(1.0)
        self.session.set_dual(3, False, keep="right")
        self.run_for(3.0)
        self.assertEqual((self.sim.state[(3, 11)], self.sim.state[(4, 2)]), (0, 0))

    def test_reload_parameter_goes_alone_and_is_read_back_first(self):
        self.connect()
        self.session.set((4, 7), -2)
        self.session.set((4, 2), 0)                              # EQ Enable: a reload parameter
        self.session.set((4, 10), -4)
        self.run_for(0.4)
        self.session.set((4, 13), -6)                            # while EQ Enable is out, not yet read back
        self.run_for(3.0)
        sent = []
        for m in self.sim.received:
            if m[5] == 0x03 and m[6] == 0x09:
                sent.append("dump")
            elif m[5] == 0x02:
                sent.append(sorted(codec.decode_triplet(*t)[:2] for t in codec.parameter_triplets([m])))
        writes = [i for i, x in enumerate(sent) if x != "dump"]
        self.assertEqual([sent[i] for i in writes], [[(4, 7), (4, 10)], [(4, 2)], [(4, 13)]])
        self.assertIn("dump", sent[writes[1] + 1:writes[2]])    # read back before anything follows
        self.assertEqual((self.sim.state[(4, 2)], self.sim.state[(4, 13)]), (0, -6))

    def test_dual_eq_on_duplicates(self):
        self.connect()
        self.session.set_dual(3, False, keep="left")
        self.run_for(2.0)
        self.session.set_dual(3, True)
        self.run_for(2.0)
        self.assertEqual(self.sim.state[(3, 11)], 1)
        self.assertTrue(all(self.sim.state[(5, i)] == self.sim.state[(4, i)] for i in range(3, 20)))

    def test_the_input_on_all_outputs_at_once(self):
        self.connect()
        optical = P.INPUTS.index("Optical")
        self.session.set_source(optical)
        self.run_for(2.0)
        writes = [m for m in self.sim.received if m[5] == 0x02]
        self.assertEqual(len(writes), 1)                                  # in one write
        self.assertEqual([self.sim.state[(out, P.SOURCE)] for out in P.OUTPUT_ADDRESSES], [optical] * 3)
        self.assertEqual(self.verified(), [{(out, P.SOURCE): (optical, optical) for out in P.OUTPUT_ADDRESSES}])

    def test_volume_rises_a_held_step_at_most_and_falls_any_amount(self):
        self.connect()
        v = self.session.state[(6, P.VOLUME)]                    # Phones, Auto Ref Level off
        step = P.volume_held_step(v)
        with self.assertRaises(ValueError):
            self.session.set((6, P.VOLUME), v + step + 5)
        self.session.set((6, P.VOLUME), v + step)
        self.session.set((6, P.VOLUME), v + step + P.volume_held_step(v + step))   # a step from where it is now
        self.run_for(2.0)
        self.assertEqual(self.sim.state[(6, P.VOLUME)], v + step + P.volume_held_step(v + step))
        self.session.set((6, P.VOLUME), v - 200)
        self.run_for(2.0)
        self.assertEqual(self.sim.state[(6, P.VOLUME)], v - 200)

    def test_out_of_dim_volume_rises_a_step_as_any_other(self):
        self.connect()
        self.sim.plug(6)                                                      # Phones active: Dim moves Volume
        self.run_for(1.5)
        v = self.session.state[(6, P.VOLUME)]
        self.session.set((6, P.DIM), 1)
        self.run_for(2.0)
        self.assertEqual(self.session.state[(6, P.VOLUME)], v - 200)          # Volume itself 20 dB down
        with self.assertRaises(ValueError):
            self.session.set((6, P.VOLUME), v)                                # no jump back
        self.session.set((6, P.VOLUME), v - 200 + 5)
        self.run_for(2.0)
        self.assertEqual((self.sim.state[(6, P.VOLUME)], self.session.state[(6, P.DIM)]), (v - 195, 0))

    def test_volume_is_not_writable_with_lock_volume(self):
        self.connect()
        self.session.set((6, P.LOCK_VOLUME), 1)
        self.run_for(2.0)
        self.assertFalse(self.session.writable((6, P.VOLUME)))           # the device refuses it
        self.assertTrue(self.session.writable((3, P.VOLUME)))            # per output

    def test_ref_level_is_the_devices_while_auto_ref_level_is_on(self):
        self.connect()
        self.assertEqual(self.session.state[(3, P.AUTO_REF_LEVEL)], 1)
        self.assertFalse(self.session.writable((3, P.REF_LEVEL)))
        self.session.set((3, P.AUTO_REF_LEVEL), 0)
        self.run_for(2.0)
        self.assertTrue(self.session.writable((3, P.REF_LEVEL)))
        self.assertFalse(self.session.writable((9, P.REF_LEVEL)))       # IEM has none
        with self.assertRaises(ValueError):
            self.session.set((6, P.REF_LEVEL), 2)                         # Phones: Lo-Power and Hi-Power only

    def test_right_is_not_writable_with_dual_eq_off(self):
        self.connect()
        self.assertTrue(self.session.writable((5, 4)))
        self.sim.front_panel([(3, 11, 0)])
        self.run_for(2.0)
        self.assertFalse(self.session.writable((5, 4)))
        self.assertFalse(self.session.writable((5, 21)))        # never: shared Bass/Treble
        with self.assertRaises(ValueError):
            self.session.set((5, 4), 0)

    def test_a_held_control_is_read_back_once_let_go(self):
        self.connect()
        v = self.session.state[(3, P.VOLUME)] + 5
        self.session.hold(True)
        self.session.set((3, P.VOLUME), v)
        self.run_for(2.0)
        self.assertEqual((self.sim.state[(3, P.VOLUME)], self.verified()), (v, []))   # written, not read back
        self.session.hold(False)
        self.run_for(1.5)
        self.assertEqual(self.verified(), [{(3, P.VOLUME): (v, v)}])


class Follow(Harness):
    def test_front_panel_change_arrives_and_is_refreshed(self):
        self.connect()
        self.sim.front_panel([(4, 4, -10)])
        self.run_for(0.1)
        self.assertEqual(self.events, [("changed", "device", ((4, 4),))])
        self.assertEqual(self.session.state[(4, 4)], -10)
        self.run_for(2.0)
        dumps = [m for m in self.sim.received if m[5:7] == [0x03, 0x09]]
        self.assertEqual(len(dumps), 2)                          # load, then a refresh after the change

    def test_idle_refresh_sees_what_another_program_wrote(self):
        self.connect()
        self.sim.state[(4, 7)] = 6                               # written by the Remote app: no echo
        self.run_for(1.0)
        self.assertNotEqual(self.session.state[(4, 7)], 6)
        self.run_for(3.5)
        self.assertEqual(self.session.state[(4, 7)], 6)
        self.assertIn(("changed", "device", ((4, 7),)), self.events)

    def test_a_dump_under_way_does_not_undo_a_queued_write(self):
        self.connect()
        for _ in range(500):                                     # until a dump has just been asked for
            if self.session._dump is not None:
                break
            self.run_for(0.02)
        old = self.sim.state[(4, 4)]
        self.session.set((4, 4), old - 4)                        # queued: it waits for the dump
        while self.session._dump is not None:
            self.run_for(0.02)
        self.assertEqual(self.session.state[(4, 4)], old - 4)   # the dump, older than the write, did not undo it
        self.run_for(2.0)
        self.assertEqual((self.sim.state[(4, 4)], self.verified()[-1]), (old - 4, {(4, 4): (old - 4, old - 4)}))

    def test_panel_change_after_our_write_wins(self):
        self.connect()
        self.session.set((4, 4), -12)
        self.run_for(0.1)                                        # sent, not yet verified
        self.sim.front_panel([(4, 4, -2)])
        self.run_for(2.0)
        self.assertEqual(self.session.state[(4, 4)], -2)
        self.assertEqual([r for r in self.verified() if r], [])  # no false mismatch

    def test_dual_eq_off_and_on_on_the_device_is_followed(self):
        self.connect()
        self.sim.front_panel([(3, 11, 0)])
        self.run_for(2.0)
        self.sim.front_panel([(3, 11, 1)])                      # the device reports only Dual EQ itself ...
        self.run_for(2.0)
        s = self.session.state                                   # ... the refresh shows right as a copy of left
        self.assertTrue(all(s[(5, i)] == s[(4, i)] for i in range(3, 20)))


class Slots(Harness):
    def asked(self):
        """What the session asked for, in order: 0 for a dump, n for slot n."""
        return [m[6] - 0x09 for m in self.sim.received if m[5] == 0x03]

    def test_reads_the_twenty_slots_after_loading(self):
        self.connect()
        self.run_for(3.0)
        s = self.session.slots
        self.assertEqual(sorted(s), list(range(1, 21)))
        self.assertEqual([n for n in s if s[n]["used"]], [1, 2, 3, 4, 19, 20])
        self.assertEqual(s[1]["name"], "   EQ Preset 1")              # literally, leading spaces included
        self.assertEqual(s[5], {"used": False, "dual": None, "name": "  EQ Preset 5", "vals": {}})
        for n in (1, 2, 3, 4, 19, 20):
            self.assertEqual((s[n]["dual"], s[n]["vals"]), (self.sim.slots[n]["dual"], self.sim.slots[n]["vals"]))
        self.assertEqual(self.slot_events, [[n] for n in range(1, 21)])

    def test_one_slot_at_a_time_after_every_dump(self):
        self.connect()
        self.run_for(6.0)
        self.assertEqual(self.asked()[:42], ([0] + list(range(1, 21))) * 2)
        self.assertEqual(self.slot_events, [[n] for n in range(1, 21)])   # the second round: nothing new

    def test_a_slot_written_elsewhere_is_seen_in_the_next_round(self):
        self.connect()
        self.run_for(3.0)
        self.slot_events.clear()
        self.sim.slots[6] = dict(self.sim.slots[2], name=list(b"Elsewhere") + [0] * 7)   # by the Remote app
        self.run_for(3.0)
        self.assertEqual(self.slot_events, [[6]])
        self.assertEqual((self.session.slots[6]["name"], self.session.slots[6]["vals"]),
                         ("Elsewhere", self.sim.slots[2]["vals"]))

    def test_a_write_goes_in_between_two_slots(self):
        self.connect()                                                  # the round is under way
        self.session.set((4, 4), -12)
        self.run_for(1.0)
        self.assertEqual(self.verified(), [{(4, 4): (-12, -12)}])
        order = ["write" if m[5] == 0x02 else m[6] - 0x09 for m in self.sim.received if m[5] in (0x02, 0x03)]
        w = order.index("write")
        self.assertGreater(order[w - 1], 0)
        self.assertEqual(order[w + 1:w + 3], [0, order[w - 1] + 1])     # read back, then the round goes on

    def test_an_answer_that_does_not_come_is_asked_again(self):
        answer, lost = self.sim._answer_preset, []

        def lose_the_first_for_slot_3(slot):
            if slot == 3 and not lost:
                lost.append(slot)
                return
            answer(slot)

        self.sim._answer_preset = lose_the_first_for_slot_3
        self.connect()
        self.run_for(4.0)
        self.assertEqual(self.asked()[:5], [0, 1, 2, 3, 3])
        self.assertEqual(sorted(self.session.slots), list(range(1, 21)))

    def test_device_gone_forgets_the_slots(self):
        self.connect()
        self.run_for(3.0)
        self.slot_events.clear()
        self.sim.power(False)
        self.run_for(1.0)
        self.assertEqual((self.session.slots, self.slot_events), ({}, [list(range(1, 21))]))


class Select(Harness):
    """The source of an output (index 28) and Load B/T with Preset (27), on Phones: Dual EQ off, Load B/T off."""

    def setUp(self):
        super().setUp()
        self.connect()
        self.run_for(3.0)                                               # the slots are in

    def reported(self):
        return {k: v for k, v in self.sim.reported().items() if k[0] not in (13, 14)}

    def test_a_preset_loads_its_bands(self):
        self.session.set((7, 28), 3)                                    # Preset 2
        self.run_for(2.0)
        s, slot = self.session.state, self.session.slots[2]
        self.assertEqual(self.verified(), [{(7, 28): (3, 3)}])
        self.assertEqual({i: s[(7, i)] for i in range(3, 20)}, {i: slot["vals"][(13, i)] for i in range(3, 20)})
        self.assertEqual(s, self.reported())

    def test_tuning_a_preset_makes_temp(self):
        self.session.set((7, 28), 3)
        self.run_for(2.0)
        self.session.set((7, 7), self.session.state[(7, 7)] + 2)
        self.run_for(2.0)
        self.assertEqual((self.session.state[(7, 28)], self.sim.state[(7, 28)]), (1, 1))
        self.assertEqual(self.session.state, self.reported())

    def test_load_bt_switches_bt_enable_off(self):
        self.session.set((7, 27), 1)
        self.run_for(2.0)
        self.assertEqual(self.verified(), [{(7, 27): (1, 1)}])
        self.assertEqual((self.session.state[(7, 20)], self.sim.state[(7, 20)]), (0, 0))

    def test_a_preset_brings_its_bass_treble_only_with_load_bt_on(self):
        self.session.set((7, 21), 6)                                    # Bass +3 dB, not in any slot
        self.run_for(2.0)
        self.session.set((7, 28), 3)
        self.run_for(2.0)
        self.assertEqual(self.session.state[(7, 21)], 6)
        self.session.set((7, 28), 0)                                    # back to Manual
        self.session.set((7, 27), 1)
        self.run_for(3.0)
        self.session.set((7, 28), 3)
        self.run_for(2.0)
        self.assertEqual([self.session.state[(7, i)] for i in range(21, 27)],
                         [self.session.slots[2]["vals"][(13, i)] for i in range(21, 27)])
        self.assertEqual(self.session.state, self.reported())


class Stale(Harness):
    """An output that keeps an earlier copy of its source preset: IEM with Preset 2, not active (Line Out is), Dual EQ
    off, Load B/T off."""

    def setUp(self):
        super().setUp()
        self.stale_events = []
        self.session.on_stale.append(self.stale_events.append)
        self.connect()
        self.run_for(3.0)                                               # the slots are in
        self.session.set((10, 28), 3)
        self.run_for(3.0)

    def write_elsewhere(self, key, value):
        """Preset 2 written by the Remote app: an output that is not active keeps what it had."""
        self.sim.slots[2] = dict(self.sim.slots[2], vals=self.sim.slots[2]["vals"] | {key: value})
        self.run_for(4.0)

    def test_a_preset_written_elsewhere_leaves_an_earlier_copy(self):
        gain = self.sim.slots[2]["vals"][(13, 7)]
        self.write_elsewhere((13, 7), gain + 2)
        self.assertEqual(self.session.stale(9), {(13, 7): (gain, gain + 2)})
        self.assertEqual(self.session.stale(3), {})
        self.assertEqual(self.stale_events, [[9]])

    def test_choosing_it_again_loads_it_as_it_is_now(self):
        self.write_elsewhere((13, 7), 0)
        self.session.set((10, 28), 3)
        self.assertEqual(self.session.stale(9), {})                     # at once: the choice is under way
        self.run_for(3.0)
        self.assertEqual(self.session.stale(9), {})
        self.assertEqual(self.sim.state[(10, 7)], 0)
        self.assertEqual(self.stale_events, [[9], [9]])

    def test_choosing_and_tuning_are_no_earlier_copy(self):
        self.assertEqual(self.stale_events, [])                         # selecting Preset 2, in setUp
        self.session.set((10, 7), self.session.state[(10, 7)] + 2)
        self.run_for(4.0)
        self.assertEqual((self.session.state[(10, 28)], self.stale_events), (1, []))   # Temp

    def test_a_change_queued_during_a_dump_is_no_earlier_copy(self):
        since = len(self.sim.received)
        while not any(m[5:7] == [0x03, 0x09] for m in self.sim.received[since:]):
            self.run_for(0.02)                                          # until the next dump is asked
        self.session.set((10, 7), self.session.state[(10, 7)] + 2)      # goes out after it, then Temp
        self.run_for(4.0)
        self.assertEqual((self.session.state[(10, 28)], self.stale_events), (1, []))

    def test_the_right_side_only_with_dual_eq_on(self):
        self.write_elsewhere((14, 7), 0)
        self.assertEqual(self.session.stale(9), {})
        self.sim.slots[2] = dict(self.sim.slots[2], dual=1)
        self.run_for(4.0)
        self.assertEqual(self.session.stale(9), {"dual": (0, 1)})
        self.session.set((10, 28), 3)
        self.run_for(3.0)
        self.assertEqual((self.session.state[(9, P.DUAL_EQ)], self.session.stale(9)), (1, {}))
        self.write_elsewhere((14, 7), 4)
        self.assertEqual(self.session.stale(9), {(14, 7): (0, 4)})

    def test_bass_treble_only_with_load_bt_on(self):
        bass = self.session.state[(10, 21)]
        self.write_elsewhere((13, 21), bass + 6)
        self.assertEqual(self.session.stale(9), {})
        self.session.set((10, 27), 1)
        self.run_for(4.0)
        self.assertEqual(self.session.stale(9), {(13, 21): (bass, bass + 6)})

    def test_an_unused_preset_against_the_factory_state(self):
        self.session.set((10, 28), 6)                                   # Preset 5
        self.run_for(4.0)
        self.assertEqual((self.session.state[(10, 28)], self.session.stale(9), self.stale_events), (6, {}, []))


class StoreWrite(Harness):
    """Store and Write, from Phones (Dual EQ off, source Manual) with Line Out active; slot 7 and 8 unused."""

    def setUp(self):
        super().setUp()
        self.operations = []
        self.session.on_operation.append(lambda kind, slot, result: self.operations.append((kind, slot, result)))
        self.connect()
        self.run_for(3.0)                                               # the slots are in

    def name(self, slot):
        return bytes(self.sim.slots[slot]["name"]).split(b"\0")[0].decode()

    def requests(self, since=0):
        """What the session sent: 'dump', ('slot', n), ('name', n), 'write' or the keys of a select."""
        out = []
        for m in self.sim.received[since:]:
            if m[5] == 0x03:
                out.append("dump" if m[6] == 0x09 else ("slot", m[6] - 0x09))
            elif m[5] == 0x06:
                out.append(("name", m[6]))
            elif m[5] == 0x02:
                keys = [codec.decode_triplet(*t)[:2] for t in codec.parameter_triplets([m])]
                out.append(keys[0] if keys[0][1] == P.EQ_PRESET_SELECT else "write")
        return out

    def test_store_writes_what_sounds_under_the_slots_own_name(self):
        self.session.set((7, 7), -6)                                    # queued: written first, then stored
        self.session.store(6, 7)
        self.run_for(8.0)
        self.assertEqual(self.operations, [("store", 7, {})])
        s = self.sim.slots[7]
        self.assertEqual((s["used"], s["dual"], self.name(7)), (True, 0, "  EQ Preset 7"))
        self.assertEqual({i: s["vals"][(13, i)] for i in range(3, 20)}, {i: self.sim.state[(7, i)] for i in range(3, 20)})
        self.assertEqual(s["vals"][(13, 7)], -6)
        self.assertEqual((self.sim.state[(7, 28)], self.session.state[(7, 28)]), (8, 8))   # Preset 7 is the source
        self.assertEqual(self.session.slots[7]["vals"], s["vals"])

    def test_store_chooses_the_slot_again_where_it_is_the_source(self):
        self.session.set((10, 28), 3)                                   # IEM: Preset 2, not active
        self.run_for(2.0)
        self.session.set((7, 7), -6)
        self.session.store(6, 2)
        self.run_for(8.0)
        self.assertEqual(self.operations, [("store", 2, {})])
        self.assertEqual([self.sim.state[(l, 28)] for l in (4, 7, 10)], [0, 3, 3])
        self.assertEqual(self.sim.state[(10, 7)], -6)                   # the new content, not the old copy

    def test_the_operation_under_way_can_be_asked(self):
        self.assertIsNone(self.session.operation())
        self.session.write_slot(2, self.content(2, name="Room"))
        self.assertEqual(self.session.operation(), ("write", 2, "          Room"))
        self.run_for(5.0)
        self.assertIsNone(self.session.operation())
        self.session.store(6, 7)
        self.assertEqual(self.session.operation(), ("store", 7, None))
        self.run_for(8.0)

    def content(self, slot, **changes):
        """What slot n holds, as write_slot takes it, with changes: name, dual, or (13|14, index) values."""
        c = dict(loaded(self.session.slots[slot]), name=self.session.slots[slot]["name"])
        c["vals"] = dict(c["vals"])
        for k, v in changes.items():
            c[k] = v
        return c

    def test_write_puts_the_content_and_the_name_in_the_slot(self):
        c = self.content(2, name="Room")
        c["vals"][(13, 4)], c["vals"][(14, 17)] = 6, -3
        live, since = self.sim.reported(), len(self.sim.received)
        self.session.write_slot(2, c)
        self.run_for(5.0)
        self.assertEqual(self.operations, [("write", 2, {})])
        s = self.sim.slots[2]
        self.assertEqual((self.name(2), s["vals"][(13, 4)], s["vals"][(14, 17)]), ("          Room", 6, -3))
        self.assertEqual(self.session.slots[2]["name"], "          Room")
        self.assertNotIn((7, 28), self.requests(since))                # selected nowhere: nothing changes that sounds
        self.assertEqual(self.sim.reported(), live)

    def test_an_unused_slot_becomes_used(self):
        c = dict(loaded(self.session.slots[8]), name="Spare")
        self.session.write_slot(8, c)
        self.run_for(5.0)
        self.assertEqual(self.operations, [("write", 8, {})])
        s = self.sim.slots[8]
        self.assertEqual((s["used"], s["dual"], s["vals"], self.name(8)), (True, 0, c["vals"], "         Spare"))

    def test_write_chooses_the_slot_again_where_it_is_the_source(self):
        self.session.set((10, 28), 3)                                   # IEM: Preset 2, not active
        self.run_for(2.0)
        c = self.content(2)
        c["vals"][(13, 7)] = -6
        self.session.write_slot(2, c)
        self.run_for(8.0)
        self.assertEqual(self.operations, [("write", 2, {})])
        self.assertEqual([self.sim.state[(l, 28)] for l in (4, 7, 10)], [0, 0, 3])
        self.assertEqual(self.sim.state[(10, 7)], -6)                   # the new content, not the old copy
        self.assertEqual(self.session.stale(9), {})

    def test_only_the_signs_of_the_front_panel(self):
        for name in ("A~B", "Café", "50%", "x" * 15):
            with self.assertRaises(ValueError):
                self.session.write_slot(3, self.content(3, name=name))
        self.assertFalse(self.session.operating())

    def test_only_values_in_range_and_a_whole_slot(self):
        c = self.content(3)
        c["vals"][(13, 5)] = 19                                         # below 20 Hz: the slot would take it
        with self.assertRaises(ValueError):
            self.session.write_slot(3, c)
        c = self.content(3)
        del c["vals"][(14, 19)]
        with self.assertRaises(ValueError):
            self.session.write_slot(3, c)
        self.assertFalse(self.session.operating())

    def test_nothing_else_goes_out_while_it_runs(self):
        since = len(self.sim.received)
        self.session.store(6, 7)
        self.run_for(0.2)
        self.assertFalse(self.session.writable((7, 10)))
        with self.assertRaises(ValueError):
            self.session.set_dual(6, True)
        self.run_for(8.0)
        ask = self.requests(since)
        start = ask.index("dump")
        self.assertEqual(ask[start:start + 9], ["dump", ("slot", 7), ("name", 7), "write", "write", "write",
                                                ("slot", 7), (7, 28), "dump"])
        self.assertTrue(self.session.writable((7, 10)))

    def test_a_slot_that_does_not_read_back_is_written_once_more(self):
        commit, mangled = self.sim._commit, []

        def commit_once_wrong(flag):
            if not mangled:
                mangled.append(flag)
                self.sim.pending[(13, 4)] += 2
            commit(flag)

        self.sim._commit = commit_once_wrong
        since = len(self.sim.received)
        self.session.store(6, 7)
        self.run_for(10.0)
        self.assertEqual(self.operations, [("store", 7, {})])
        self.assertEqual(self.requests(since).count(("name", 7)), 2)

    def test_then_the_difference_is_reported(self):
        commit = self.sim._commit

        def commit_wrong(flag):
            self.sim.pending[(13, 4)] += 2
            commit(flag)

        self.sim._commit = commit_wrong
        since = len(self.sim.received)
        self.session.store(6, 7)
        self.run_for(10.0)
        gain = self.sim.state[(7, 4)]
        self.assertEqual(self.operations, [("store", 7, {(13, 4): (gain, gain + 2)})])
        self.assertEqual(self.requests(since).count(("name", 7)), 2)
        self.assertNotIn((7, 28), self.requests(since))                # not selected again
        self.assertFalse(self.session.operating())

    def test_device_gone_during_the_operation(self):
        self.session.store(6, 7)
        self.run_for(1.5)
        self.sim.power(False)
        self.run_for(1.0)
        self.assertEqual(self.operations, [("store", 7, None)])
        self.assertFalse(self.session.operating())


class EqOnly(Harness):
    """An ADI-2 Pro: Commander writes the EQ of Line Out and Phones 3/4, and nothing else."""

    def setUp(self):
        super().setUp()
        self.sim = SimulatedAdi2.factory(PRO, presets=PRESETS, clock=self.clock)
        self.operations = []
        self.session.on_operation.append(lambda kind, slot, result: self.operations.append((kind, slot, result)))
        self.connect()
        self.run_for(3.0)                                               # the slots

    def written(self, since=0):
        return [codec.decode_triplet(*t)[:2] for m in self.sim.received[since:] if m[5] == 0x02
                for t in codec.parameter_triplets([m])]

    def test_what_it_writes(self):
        writable = [k for k in [(4, 4), (5, 4), (10, 4), (4, 21), (4, 28), (3, 20), (3, 23), (9, 21)]
                    if self.session.writable(k)]
        self.assertEqual(writable, [(4, 4), (10, 4), (4, 21), (4, 28), (3, 20), (3, 23), (9, 21)])  # right: Dual EQ off
        for key in [(7, 4), (8, 4), (6, 20), (3, 1), (3, 2), (3, 12), (3, 15), (9, 9), (0, 1), (1, 4), (12, 6)]:
            self.assertFalse(self.session.writable(key), key)
        self.assertEqual((self.session.controls(3), self.session.controls(6), self.session.controls(9)),
                         (True, False, True))

    def test_dual_eq_store_and_source_only_where_it_controls(self):
        self.session.set_dual(3, True)
        self.run_for(2.0)
        self.assertEqual(self.sim.state[(3, 11)], 1)
        for act in (lambda: self.session.set_dual(6, True), lambda: self.session.store(6, 2),
                    lambda: self.session.set_source(1)):
            with self.assertRaises(ValueError):
                act()

    def test_store_selects_again_only_where_it_controls(self):
        self.sim.front_panel([(7, 28, 3), (10, 28, 3)])                 # Preset 2 on Phones 1/2 and Phones 3/4
        self.run_for(2.0)
        since = len(self.sim.received)
        self.session.set((4, 7), -6)
        self.session.store(3, 2)
        self.run_for(8.0)
        self.assertEqual(self.operations, [("store", 2, {})])
        self.assertEqual({k for k in self.written(since) if k[1] == P.EQ_PRESET_SELECT}, {(4, 28), (10, 28)})
        self.assertNotIn(7, {a for a, _ in self.written()})


if __name__ == "__main__":
    unittest.main()
