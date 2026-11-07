"""The live link to the device, without blocking: the UI calls tick() every few tens of milliseconds.

It finds and opens the port, loads the full state with a dump, follows unsolicited changes from the
front panel, and writes: changes queue up, go out bundled at most ~6 times per second, and are verified by
a dump once it has been quiet for a moment. The device is the truth: whatever it reports is the state.

The first dump request also tells the model: it goes out under each device ID in turn, the one the port name
suggests first, and the ID that answers is the model (device/models.py). A model Commander does not support is let
go at once, its port closed for other programs, and the session waits until it is gone.

The dump does not hold the twenty preset slots. After every dump they are read with 03 0A+n, one at a time:
asked before the previous answer is complete, the device loses parameter messages. A write goes in between
two slots.

Store and Write put a whole slot on the device: the name with 0x06, the left side on address 13, the right side
on 14, then the flag word on 13/2, which commits it. Each is one operation, read back afterwards and written once
more if it does not read back as sent; while it runs, nothing else goes out and nothing is writable.

No Qt here; listeners are plain callables:
    on_connection(status, detail)   status: 'searching', 'busy', 'loading', 'ready', 'unsupported' (see model)
    on_changed(keys, origin)        origin: 'load', 'device' (front panel), 'write' (our own, optimistic)
    on_verified(results)            {(address, index): (sent, actual)} after a write was read back
    on_slots(numbers)               preset slots that read differently than before, or are gone
    on_stale(outputs)               outputs that came to differ from the preset they have as source, or no longer do
    on_operation(kind, slot, result)
                                    kind: 'store' or 'write'; result: {} when the slot read back as sent, else
                                    {key: (sent, actual)} with key (13|14, index), 'name', 'dual', or the
                                    source (left EQ address, 28) selected again afterwards; None when the device
                                    went away first
    on_device_status(status)        a status.Status from the device's status message, when it reads differently;
                                    None when the device went away
"""

import time

from .device import codec
from .device import models
from .device import params as P
from .device import status as S
from .device.connection import REQUIRED, DeviceNotFound, PortBusy, build_messages

SEARCH_INTERVAL = 2.0          # seconds between attempts to find the port
SEND_INTERVAL = 1 / 6          # at most ~6 writes per second
VERIFY_AFTER = 0.3             # quiet time after the last write before reading back
REFRESH_AFTER = 0.5            # quiet time after a front panel change before reading everything back:
                               # the device reports only the parameter itself, not its side effects
                               # (Dual EQ copying left to right, a preset loading bands, Ref Level)
IDLE_REFRESH = 3.0             # read everything back when nothing else happens: the device does not echo
                               # what another program (the ADI-2 Remote app) writes
DUMP_TIMEOUT = 3.0             # a dump takes ~0.5 s on the device
PROBE_TIMEOUT = 1.0            # per device ID while the model is not known: the first answer comes within ~0.1 s
PRESENCE_INTERVAL = 0.5       # how often to check that the port still exists: in standby or when unplugged
                               # it leaves the port list at once, also while it is open here
STATUS_TIMEOUT = 3.5           # the safety net: the device sends a status message every ~1 s (up to ~2 s
                               # just after power on); after ~3 missed ones it is gone
SLOT_TIMEOUT = 1.0             # a slot answers within ~0.12 s
SLOTS = range(1, 21)
# a used slot: the left side on address 13 (bands and Bass/Treble), the right side on address 14 (bands);
# the flag word comes back on 13/1: (slot - 1) << 4 | Dual EQ, the four low bits set when the slot is unused
SLOT_LEFT = list(range(3, 20)) + list(range(21, 27))
SLOT_RIGHT = list(range(3, 20))
SLOT_KEYS = {(13, i) for i in SLOT_LEFT} | {(14, i) for i in SLOT_RIGHT}
SLOT_FLAG = (13, 1)
TRANSFER_SPACING = 0.3         # between the messages of a slot transfer
TRANSFER_SETTLE = 1.0          # after the flag word, before reading the slot back
RELOAD = {P.EQ_ENABLE, P.EQ_PRESET_SELECT}  # make the device rebuild its filters: sent on their own and read
                                           # back before anything follows

LEFT = {left: out for _, out, left, _ in P.OUTPUTS}
RIGHT = {right: out for _, out, _, right in P.OUTPUTS}
# what Commander writes with set() on the address of an output of a model it controls only the EQ of
# (models.Model.eq_only); Dual EQ goes by set_dual()
EQ_ONLY = {P.LOUDNESS_ENABLE, P.LD_BASS, P.LD_TREBLE, P.LD_LOW_VOL_REF}


def output_content(state, out):
    """The EQ of output out as a slot holds it: {'dual', 'vals' {(13|14, index): value}}. With Dual EQ off the
    right side is the left's, as the device reports it."""
    _, out, left, right = next(o for o in P.OUTPUTS if o[1] == out)
    vals = {(13, i): state[(left, i)] for i in SLOT_LEFT}
    vals.update({(14, i): state[(right, i)] for i in SLOT_RIGHT})
    return {"dual": state[(out, P.DUAL_EQ)], "vals": vals}


def loaded(slot):
    """What selecting a slot loads: {'dual', 'vals'}; for an unused slot the factory state, Dual EQ off."""
    if slot["used"]:
        return {"dual": slot["dual"], "vals": dict(slot["vals"])}
    vals = {(a, i): v for a in (13, 14) for i, v in P.FACTORY_BANDS.items()}
    vals.update({(13, i): v for i, v in P.FACTORY_BT.items()})
    return {"dual": 0, "vals": vals}


def differences(live, preset, load_bt):
    """Where an output's EQ differs from what selecting the preset loads: {key: (live, preset)}, key 'dual' or
    (13|14, index). The right side only with Dual EQ on (off, the device uses the left side for both), Bass/Treble
    only with Load B/T on (off, it belongs to the output)."""
    keys = [(13, i) for i in SLOT_LEFT if load_bt or i < P.BASS[0]]
    if live["dual"] == preset["dual"] == 1:
        keys += [(14, i) for i in SLOT_RIGHT]
    diff = {k: (live["vals"][k], preset["vals"][k]) for k in keys if live["vals"][k] != preset["vals"][k]}
    if live["dual"] != preset["dual"]:
        diff["dual"] = (live["dual"], preset["dual"])
    return diff


class Session:
    def __init__(self, open_port, clock=time.monotonic):
        self.open_port = open_port               # () -> port; raises DeviceNotFound or PortBusy
        self.clock = clock
        self.port = None
        self.status = None
        self.model = None                        # the model messages go to, a models.Model; known once identified
        self._identified = False
        self.state = {}
        self.pending = {}                        # queued writes {(address, index): value}
        self.sent = {}                           # written, awaiting read-back
        # the preset slots as last read: {n: {'used', 'dual', 'name', 'vals' {(13|14, index): value}}};
        # an unused slot has no Dual EQ (None) and no values
        self.slots = {}
        self._stale = {}                         # {output: (source, differences)} as judged when last settled
        self.device_status = None                # what the device's status message says, a status.Status
        self._refresh_at = None
        self._last_dump_done = 0.0
        self.on_connection = []
        self.on_changed = []
        self.on_verified = []
        self.on_slots = []
        self.on_stale = []
        self.on_operation = []
        self.on_device_status = []
        self._next_search = 0.0
        self._last_send = -1e9
        self._verify_at = None
        self._dump = None                        # {'purpose': 'load'|'verify', 'since': t, 'tries': n, 'end': bool}
        self._slot = None                        # {'n', 'since', 'tries', 'name', 'vals'} while a slot answers
        self._slots_due = []                     # slots still to read in this round
        self._op = None                          # a Store or Write: {'kind', 'slot', 'step', ...}
        self._last_status = None
        self._next_presence = 0.0
        self._candidates = []                    # models still to ask while the model is not known
        self._let_go = None                      # the closed port of an unsupported model, watched until it is gone
        self._held = False                       # a held control repeats its steps: see hold()

    # -- public -------------------------------------------------------------------------------
    def ready(self):
        return self.status == "ready"

    def dual(self, out):
        return self.state.get((out, P.DUAL_EQ), 1) == 1

    def revision(self):
        """The device revision from its status message; None before the first."""
        return None if self.device_status is None else self.device_status.revision

    def bypassed(self):
        """True while the device plays DSD: it has no DSP for DSD, so whatever is on is bypassed."""
        return self.device_status is not None and self.device_status.dsd

    def eq_bypassed(self, out):
        """True while the EQ of output out is bypassed for the EQ of the input: on an ADI-2 Pro and ADI-2/4 Pro from
        one_eq_from on (models.py), the device runs the input's EQ while it is on, instead of those of the outputs."""
        if self.model is None or self.model.one_eq_from is None or out not in P.OUTPUT_ADDRESSES:
            return False
        index = self.state.get(P.SAMPLE_RATE)
        if index not in range(len(P.SAMPLE_RATES)) or P.SAMPLE_RATES[index] < self.model.one_eq_from:
            return False
        left, right = P.INPUT_EQ
        dual = self.state.get(P.INPUT_DUAL_EQ) == 1
        return self.state.get((left, P.EQ_ENABLE)) == 1 or dual and self.state.get((right, P.EQ_ENABLE)) == 1

    def controls(self, out):
        """Whether Commander controls output out of the device connected: on an ADI-2 Pro and ADI-2/4 Pro Phones 1/2
        only while it has settings of its own (models.py)."""
        if self.model is None:
            return False
        need = dict(self.model.separate).get(out)
        return out in self.model.controlled or need is not None and all(
            self.state.get((12, i)) == 1 for i in need)

    def writable(self, key):
        a, i = key
        if not self.ready() or self._op is not None or key not in self.state:
            return False
        if a in P.OUTPUT_ADDRESSES:
            if not self.controls(a) or (self.model.eq_only and i not in EQ_ONLY):
                return False
            if i == P.REF_LEVEL and self.state.get((a, P.AUTO_REF_LEVEL)) == 1:
                return False                             # the device chooses it; written, it moves Volume a step
            if i == P.VOLUME and self.state.get((a, P.LOCK_VOLUME)) == 1:
                return False                             # the device refuses it while Lock Volume is on
            if i == P.DA_FILTER and P.da_filters(self.revision()) is None:
                return False                             # what its values mean is not known
            return i in P.OUTPUT_RANGES and not P.absent(i, self.state[key])
        if i not in P.EQ_RANGES:
            return False
        if a in RIGHT:
            return i <= 19 and self.controls(RIGHT[a]) and self.dual(RIGHT[a])   # with Dual EQ off an alias of left
        return a in LEFT and self.controls(LEFT[a])

    def hold(self, on):
        """While a held control repeats its steps, what is written, and what the device changed besides (Ref Level
        under Auto Ref Level), is read back only once it is let go: a dump takes ~0.5 s, and nothing goes out
        meanwhile, so the next step would wait for it."""
        self._held = on

    def set(self, key, value):
        """Queue a write. The value must already be on the device's grid and within range; Volume rises at most a
        held step from where it is (params.volume_held_step, as fast as the remote control), Dim or not, and may fall
        any amount."""
        if not self.writable(key):
            raise ValueError("parameter %d/%d is not writable now" % key)
        lo, hi = P.limits(key, self.revision())
        if not lo <= value <= hi:
            raise ValueError("%d/%d: %d outside %d..%d" % (key + (value, lo, hi)))
        if key[0] in P.OUTPUT_ADDRESSES and key[1] == P.VOLUME:
            now = self.state[key]
            most = P.volume_held_step(now + P.volume_offset(self.state, key[0]))
            if value - now > most:
                raise ValueError("Volume: %d is more than %.1f dB above %d" % (value, most / 10, now))
        self.pending[key] = value
        self.sent.pop(key, None)
        if self.state.get(key) != value:
            self.state[key] = value
            self._emit(self.on_changed, [key], "write")

    def set_source(self, value):
        """Choose the input, an index into params.INPUTS. It is one setting of the whole device, on every output
        address: written to all three at once, as the device reports a change on its front panel."""
        keys = [(out, P.SOURCE) for out in P.OUTPUT_ADDRESSES]
        if not all(self.writable(k) for k in keys):
            raise ValueError("the input is not writable now")
        for k in keys:
            self.set(k, value)

    def set_dual(self, out, on, keep="left"):
        """Switch Dual EQ of one output.
        Off: one EQ for both channels. keep='left' or 'right' says which channel's bands become the shared
        set; the device uses the left set, so for 'right' the left bands get the right values first.
        On: the device starts both channels from the shared set (it copies left to right)."""
        if (not self.ready() or self._op is not None or (out, P.DUAL_EQ) not in self.state
                or not self.controls(out)):
            raise ValueError("Dual EQ of output %d is not writable now" % out)
        left, right = next((l, r) for _, o, l, r in P.OUTPUTS if o == out)
        if not on and self.dual(out) and keep == "right":
            for i in range(2, 20):                       # EQ Enable too: the right channel as it is
                if (right, i) in self.state and self.state.get((left, i)) != self.state[(right, i)]:
                    self.set((left, i), self.state[(right, i)])
        self.pending[(out, P.DUAL_EQ)] = 1 if on else 0
        self.sent.pop((out, P.DUAL_EQ), None)
        self.state[(out, P.DUAL_EQ)] = 1 if on else 0
        for i in range(2, 20):                           # what the device will report for the right channel
            if (right, i) in self.state:
                self.state[(right, i)] = self.state[(left, i)]
        self._emit(self.on_changed, [(out, P.DUAL_EQ)] + [(right, i) for i in range(2, 20)], "write")

    def store(self, out, slot):
        """The EQ of output out as it is now, Bass/Treble included, goes to preset slot n, under the name the slot
        has. Queued writes go first, and what is stored is what a dump after them reports. Afterwards the slot is
        selected again on out and on every output that has it as source: the device itself updates only the active
        output."""
        if out not in P.OUTPUT_ADDRESSES or (self.model is not None and not self.controls(out)):
            raise ValueError("output %s" % out)
        self._start("store", slot, out=out)

    def write_slot(self, slot, content):
        """Preset slot n gets this content: {'name', 'dual', 'vals' {(13|14, index): value}}, as loaded() gives
        it. A name is aligned right on 14 signs, as the front panel does. The slot takes any value, so each must be
        within its range. Afterwards the slot is selected again on every output that has it as source, as after
        Store."""
        name = content["name"]
        if not P.valid_name(name):
            raise ValueError("preset name %r: up to %d of the signs the front panel offers" % (name, P.NAME_LENGTH))
        vals = content["vals"]
        if set(vals) != SLOT_KEYS or content["dual"] not in (0, 1):
            raise ValueError("preset content incomplete")
        for (a, i), v in vals.items():
            lo, hi = P.EQ_RANGES[i]
            if not lo <= v <= hi:
                raise ValueError("%d/%d: %d outside %d..%d" % (a, i, v, lo, hi))
        self._start("write", slot, name=name.rjust(P.NAME_LENGTH),
                    content={"name": name.rjust(P.NAME_LENGTH), "dual": content["dual"], "vals": dict(vals)})

    def stale(self, out):
        """Where output out differs from the preset it has as source, as differences() gives it. A preset written
        while it is the source changes the EQ only on the active output; the others keep an earlier copy. Judged
        only when nothing is under way, so a choice or a change still in flight does not count: {} meanwhile."""
        key = (next(l for _, o, l, _ in P.OUTPUTS if o == out), P.EQ_PRESET_SELECT)
        source, diff = self._stale.get(out, (None, {}))
        if source != self.state.get(key) or key in self.pending or key in self.sent:
            return {}
        return diff

    def operating(self):
        return self._op is not None

    def operation(self):
        """The Store or Write under way as (kind, slot, new name or None), or None."""
        op = self._op
        return None if op is None else (op["kind"], op["slot"], op.get("name"))

    def close(self):
        if self.port is not None:
            self.port.close()
            self.port = None

    # -- the loop -----------------------------------------------------------------------------
    def tick(self):
        now = self.clock()
        if self.port is None:
            if self._let_go is not None:
                self._watch_let_go(now)
            elif now >= self._next_search:
                self._connect(now)
            return
        try:
            self._receive(now)
            if self.port is not None:
                self._write(now)
                self._watch(now)
        except OSError as e:
            self._drop("device lost (%s)" % e)

    def _connect(self, now):
        self._next_search = now + SEARCH_INTERVAL
        try:
            self.port = self.open_port()
        except PortBusy as e:
            self._set_status("busy", str(e))
            return
        except DeviceNotFound as e:
            self._set_status("searching", str(e))
            return
        self.state = {}
        self._last_status = None
        self._identified = False
        self.model, *self._candidates = models.probe_order(self.port.names[0])
        self._set_status("loading", "reading the device")
        self._request_dump(now, "load")

    def _identify(self, now, model):
        """The first message under a known device ID: that is the model. False when it is let go."""
        self._identified = True
        self._last_status = None
        if not model.supported:
            self.model, self._let_go = model, self.port
            self.close()
            self._dump = None
            self._set_status("unsupported", "This version of Commander works with the %s" % models.DAC.name)
            return False
        if model != self.model:                          # a late answer to an earlier request
            self.model = model
            self._request_dump(now, "load")
        return True

    def _watch_let_go(self, now):
        if now >= self._next_presence:
            self._next_presence = now + PRESENCE_INTERVAL
            if not self._let_go.present():
                self._let_go = None
                self.model, self._identified = None, False
                self._next_search = now
                self._set_status("searching", "the device went away (standby, switched off or unplugged)")

    def _drop(self, why):
        self.close()
        self.pending.clear()
        self.sent.clear()
        self._verify_at = None
        self._refresh_at = None
        self._dump = None
        self._slot = None
        self._slots_due = []
        self.state = {}
        self.model, self._identified = None, False
        self._emit(self.on_changed, [], "load")
        gone, self.slots, self._stale = list(self.slots), {}, {}
        if gone:
            self._emit(self.on_slots, gone)
        op, self._op = self._op, None
        if op is not None:
            self._emit(self.on_operation, op["kind"], op["slot"], None)
        if self.device_status is not None:
            self.device_status = None
            self._emit(self.on_device_status, None)
        self._next_search = self.clock() + SEARCH_INTERVAL
        self._set_status("searching", why)

    def _request_dump(self, now, purpose, tries=0):
        self._dump = {"purpose": purpose, "since": now, "tries": tries, "end": False}
        self.port.send(codec.header(self.model.id) + [0x03, 0x09, 0xF7])

    def _request_slot(self, now, n, tries=0):
        self._slot = {"n": n, "since": now, "tries": tries, "name": None, "vals": {}}
        self.port.send(codec.header(self.model.id) + [0x03, 0x09 + n, 0xF7])

    def _receive(self, now):
        changed = []
        for m in self.port.receive():
            if len(m) < 7 or list(m[:4]) != codec.PREFIX:
                continue
            if not self._identified and m[4] in models.BY_ID and not self._identify(now, models.BY_ID[m[4]]):
                return
            if m[4] != self.model.id:
                continue
            if m[5] == 0x07:
                self._last_status = now
                body = m[6:-1]
                if len(body) >= S.LENGTH and S.decode(body) != self.device_status:
                    self.device_status = S.decode(body)
                    self._emit(self.on_device_status, self.device_status)
            elif m[5] == 0x01:
                for t in codec.parameter_triplets([m]):
                    a, i, v, _ = codec.decode_triplet(*t)
                    if a in (13, 14):
                        if self._slot is not None:
                            self._slot["vals"][(a, i)] = v
                        continue
                    if self._dump is not None and (a, i) in self.pending:
                        continue                         # still queued: the dump is older than the write, which
                                                         # goes out after it and is read back then
                    if self.state.get((a, i)) != v:
                        self.state[(a, i)] = v
                        changed.append((a, i))
                    if self._dump is None:
                        self.sent.pop((a, i), None)     # a front panel change after our write wins
                        self.pending.pop((a, i), None)
            elif m[5] == 0x05 and m[6] == 0x29 and self._dump is not None:
                self._dump["end"] = True
            elif m[5] == 0x05 and self._slot is not None and m[6] == self._slot["n"]:
                self._slot["name"] = m[7:-1]
        if self._slot is not None:
            self._slot_progress(now)
        if self._dump is not None:
            self._dump_progress(now, changed)
        elif changed:
            self._refresh_at = now + REFRESH_AFTER
            self._emit(self.on_changed, changed, "device")

    def _dump_progress(self, now, changed):
        d = self._dump
        if changed and d["purpose"] != "load":
            # report a change the moment its message is in: a dump arrives spread over ~0.4 s, and the
            # cell shows the new value right away, so its flash must start right away too
            self._emit(self.on_changed, changed, "device")
        if d["end"] and not REQUIRED - set(self.state):
            self._dump = None
            self._last_dump_done = now
            if not self._slots_due:
                self._slots_due = list(SLOTS)
            if d["purpose"] == "load":
                self._set_status("ready", "")
                self._emit(self.on_changed, list(self.state), "load")
                return
            if d["purpose"] == "verify":
                results = {k: (v, self.state.get(k)) for k, v in self.sent.items()}
                self.sent.clear()
                self._emit(self.on_verified, results)
            if d["purpose"] == "operation":
                self._operation_dump()
            self._judge()
            return
        if not self._identified:
            if now - d["since"] > PROBE_TIMEOUT:
                if not self._candidates:
                    self._drop("no answer under any ADI-2 device ID")
                    return
                self.model = self._candidates.pop(0)
                self._request_dump(now, "load")
            return
        if now - d["since"] > DUMP_TIMEOUT:
            if d["tries"] >= 2:
                raise OSError("no complete dump after 3 requests")
            self._request_dump(now, d["purpose"], d["tries"] + 1)

    def _slot_progress(self, now):
        """Complete: the flag word for this slot and the name, and for a used slot all its values."""
        s = self._slot
        flag = s["vals"].get(SLOT_FLAG)
        if flag is not None and (flag >> 4) + 1 != s["n"]:
            flag = None                                  # part of another answer
        used = flag is not None and flag & 0x0F != 0x0F
        if flag is not None and s["name"] is not None and (not used or not SLOT_KEYS - set(s["vals"])):
            self._slot = None
            slot = {"used": used, "dual": flag & 1 if used else None,
                    "name": bytes(s["name"]).split(b"\0")[0].decode("ascii", "replace"),
                    "vals": {k: v for k, v in s["vals"].items() if k in SLOT_KEYS} if used else {}}
            if self.slots.get(s["n"]) != slot:
                self.slots[s["n"]] = slot
                self._emit(self.on_slots, [s["n"]])
                self._judge()
            if self._op is not None and self._op["slot"] == s["n"] and self._op["step"] in ("reading", "verifying"):
                self._operation_slot(now, slot)
            return
        if now - s["since"] > SLOT_TIMEOUT:
            if s["tries"] >= 2:
                raise OSError("no complete answer for preset slot %d after 3 requests" % s["n"])
            self._request_slot(now, s["n"], s["tries"] + 1)

    def _judge(self):
        """Compare each output with the preset it has as source, once the state has settled: nothing queued, sent
        or still to be read back."""
        if self.pending or self.sent or self._dump is not None or self._refresh_at is not None:
            return
        judged = {}
        for _, out, left, _ in P.OUTPUTS:
            source = self.state.get((left, P.EQ_PRESET_SELECT))
            slot = self.slots.get(source - 1) if source is not None else None   # Preset n is n + 1
            if slot is not None:
                diff = differences(output_content(self.state, out), loaded(slot),
                                   self.state.get((left, P.LOAD_BT)) == 1)
                if diff:
                    judged[out] = (source, diff)
        changed = [o for o in P.OUTPUT_ADDRESSES if judged.get(o) != self._stale.get(o)]
        self._stale = judged
        if changed:
            self._emit(self.on_stale, changed)

    def _holding(self):
        """A reload parameter is out and not read back yet: nothing else goes out until it is."""
        return any(i in RELOAD for _, i in self.sent)

    def _next_batch(self):
        """Everything queued in one go, except the reload parameters; those one at a time, last."""
        plain = {k: v for k, v in self.pending.items() if k[1] not in RELOAD}
        if plain:
            return plain
        k = min(self.pending)
        return {k: self.pending[k]}

    def _write(self, now):
        if self.status != "ready" or self._dump is not None or self._slot is not None:
            return
        if self._op is not None and self._operate(now):
            return
        if self.pending and not self._holding() and now - self._last_send >= SEND_INTERVAL:
            batch = self._next_batch()
            params = [(a, i, v, a in codec.EQ_ADDRESSES and i in P.FREQ_INDICES) for (a, i), v in sorted(batch.items())]
            for m in build_messages(self.model.id, params):
                self.port.send(m)
            self.sent.update(batch)
            for k in batch:
                del self.pending[k]
            self._last_send = now
            self._verify_at = now + VERIFY_AFTER
        elif ((not self.pending or self._holding()) and self._verify_at is not None
              and now >= self._verify_at and not self._held):
            self._verify_at = None
            self._refresh_at = None                      # the verify dump refreshes everything too
            if self.sent:
                self._request_dump(now, "verify")
        elif not self.pending and self._refresh_at is not None and now >= self._refresh_at and not self._held:
            self._refresh_at = None
            self._request_dump(now, "refresh")
        elif self._op is not None:
            return                                       # the operation waits until the queue is verified
        elif self._slots_due and not self.pending and not self.sent and self._verify_at is None:
            self._request_slot(now, self._slots_due.pop(0))
        elif (not self.pending and not self.sent and self._verify_at is None and self._refresh_at is None
              and now - self._last_dump_done >= IDLE_REFRESH):
            self._request_dump(now, "refresh")

    # -- Store and Write ------------------------------------------------------------------------
    # settle -> dumping -> read -> reading -> transfer -> settled -> verifying; then per output that selects the
    # slot again: select -> selected -> select-dumping

    def _start(self, kind, slot, **kw):
        if not self.ready() or self._op is not None or slot not in SLOTS:
            raise ValueError("preset slot %s cannot be written now" % slot)
        self._op = dict(kind=kind, slot=slot, step="settle", tries=0, selects=[], result={}, **kw)

    def _operate(self, now):
        """One step. False while queued writes are still being written and verified."""
        op = self._op
        step = op["step"]
        if step == "settle":
            if self.pending or self.sent or self._verify_at is not None:
                return False
            op["step"] = "dumping"
            self._refresh_at = None
            self._request_dump(now, "operation")
        elif step == "read":
            op["step"] = "reading"
            self._request_slot(now, op["slot"])
        elif step == "transfer" and now >= op["at"]:
            self.port.send(op["messages"].pop(0))
            if op["messages"]:
                op["at"] = now + TRANSFER_SPACING
            else:
                op["step"], op["at"] = "settled", now + TRANSFER_SETTLE
        elif step == "settled" and now >= op["at"]:
            op["step"] = "verifying"
            self._request_slot(now, op["slot"])
        elif step == "select":
            if not op["selects"]:
                self._finish()
                return True
            key = (op["selects"][0], P.EQ_PRESET_SELECT)
            for m in build_messages(self.model.id, [key + (op["slot"] + 1, False)]):
                self.port.send(m)
            if self.state.get(key) != op["slot"] + 1:
                self.state[key] = op["slot"] + 1
                self._emit(self.on_changed, [key], "write")
            op["step"], op["at"] = "selected", now + VERIFY_AFTER
        elif step == "selected" and now >= op["at"]:
            op["step"] = "select-dumping"
            self._request_dump(now, "operation")
        return True

    def _operation_dump(self):
        op = self._op
        if op["step"] == "dumping":
            op["step"] = "read"
        elif op["step"] == "select-dumping":
            key = (op["selects"].pop(0), P.EQ_PRESET_SELECT)
            if self.state.get(key) != op["slot"] + 1:
                op["result"][key] = (op["slot"] + 1, self.state.get(key))
            op["step"] = "select"

    def _operation_slot(self, now, slot):
        op = self._op
        if op["step"] == "reading":
            op["content"] = self._content(op, slot)
            self._transfer(now)
            return
        c = op["content"]
        diff = {k: (v, slot["vals"].get(k)) for k, v in c["vals"].items() if slot["vals"].get(k) != v}
        for k in ("name", "dual"):
            if slot[k] != c[k]:
                diff[k] = (c[k], slot[k])
        if diff and op["tries"] == 0:
            op["tries"] = 1
            self._transfer(now)
        elif diff:
            op["result"].update(diff)
            self._finish()
        else:
            op["selects"] = [left for _, out, left, _ in P.OUTPUTS if self.controls(out) and (
                out == op.get("out") or self.state.get((left, P.EQ_PRESET_SELECT)) == op["slot"] + 1)]
            op["step"] = "select"

    def _content(self, op, slot):
        """What goes into the slot: {'name', 'dual', 'vals' {(13|14, index): value}}."""
        if op["kind"] == "store":
            return dict(output_content(self.state, op["out"]), name=slot["name"])
        return op["content"]

    def _transfer(self, now):
        op = self._op
        c, n = op["content"], op["slot"]
        name = list(c["name"].encode("ascii", "replace")[:15])
        d = self.model.id
        op["messages"] = ([codec.header(d) + [0x06, n] + name + [0] * (16 - len(name)) + [0xF7]]
                          + build_messages(d, [(13, i, c["vals"][(13, i)], i in P.FREQ_INDICES) for i in SLOT_LEFT])
                          + build_messages(d, [(14, i, c["vals"][(14, i)], i in P.FREQ_INDICES) for i in SLOT_RIGHT])
                          + build_messages(d, [(13, 2, (n - 1) << 4 | c["dual"], False)]))
        op["step"], op["at"] = "transfer", now

    def _finish(self):
        op, self._op = self._op, None
        self._emit(self.on_operation, op["kind"], op["slot"], op["result"])

    def _watch(self, now):
        if now >= self._next_presence:
            self._next_presence = now + PRESENCE_INTERVAL
            if not self.port.present():
                self._drop("the device went away (standby, switched off or unplugged)")
                return
        if not self._identified:
            return                                       # the probe has its own timeout
        if self._last_status is None:
            self._last_status = now                      # the stream starts ~0.7 s after the first message
        elif now - self._last_status > STATUS_TIMEOUT:
            self._drop("no status from the device for %.1f s" % (now - self._last_status))

    # -- helpers ------------------------------------------------------------------------------
    def _set_status(self, status, detail):
        if status != self.status:
            self.status = status
            self._emit(self.on_connection, status, detail)

    @staticmethod
    def _emit(listeners, *args):
        for f in listeners:
            f(*args)
