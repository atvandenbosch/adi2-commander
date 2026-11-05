"""A client of the device for the tests: send, receive, dump, and a write verified by a dump. It talks to the
simulator's port as to WinmmPort."""

import time

from commander.device import codec
from commander.device.connection import REQUIRED, WinmmPort, build_messages
from commander.device.models import DAC

HEADER = codec.header(DAC.id)


def parse(msgs):
    """{(address, index): value} from parameter messages (0x01 or 0x02)."""
    state = {}
    for t in codec.parameter_triplets(msgs):
        address, index, value, _ = codec.decode_triplet(*t)
        state[(address, index)] = value
    return state


def read_state(path, with_presets=False):
    """{(address, index): value} from a dump file."""
    return {k: v for k, v in parse(codec.read_dump(path)).items() if with_presets or k[0] not in (13, 14)}


def roundtrip_mismatches(path):
    """Decode every triplet in a dump and encode it again. The triplets that do not come back byte for byte:
    [(address, index, value, original bytes, re-encoded bytes)]."""
    out = []
    for t in codec.parameter_triplets(codec.read_dump(path)):
        address, index, value, is_freq = codec.decode_triplet(*t)
        back = codec.encode(address, index, value, is_freq)
        if back != list(t):
            out.append((address, index, value, list(t), back))
    return out


class Adi2:
    """Send, receive, dump and verified write. Use as a context manager.

    port: a WinmmPort (default) or anything with the same send/receive/close/names, such as the
    simulator's port."""

    def __init__(self, log=print, port=None):
        self.log = log
        self.port = port if port is not None else WinmmPort()
        self.ports = self.port.names
        self.n_status = 0
        self.messages = []                              # the messages of the last dump

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        self.port.close()

    # -- low level ------------------------------------------------------------------------------
    def send(self, msg, pause=0.25):
        self.port.send(msg)
        time.sleep(pause)

    def collect(self):
        """Everything that has come in; status messages are counted but not returned."""
        out = []
        for m in self.port.receive():
            if len(m) > 5 and m[5] == 0x07:
                self.n_status += 1
            else:
                out.append(m)
        return out

    # -- dump ---------------------------------------------------------------------------------
    def dump(self, silence=1.0, max_duration=12.0, attempts=3):
        """Full state. Complete = all REQUIRED parameters and the last setup name (05 29). Status messages do not
        count as traffic: they arrive every second and would keep the wait for silence going."""
        for attempt in range(attempts):
            self.collect()                                  # discard old traffic
            self.send(HEADER + [0x03, 0x09, 0xF7], pause=0.0)
            msgs, t0, last = [], time.time(), time.time()
            while time.time() - t0 < max_duration:
                new = self.collect()
                if new:
                    msgs += new
                    last = time.time()
                done = any(len(m) > 6 and m[5] == 0x05 and m[6] == 0x29 for m in msgs)
                if done and time.time() - last > 0.3:
                    break
                if msgs and time.time() - last > silence and not done:
                    break
                time.sleep(0.01)
            state = parse(msgs)
            missing = REQUIRED - set(state)
            if not missing:
                self.messages = msgs
                return state
            self.log("   dump incomplete (%d parameters missing), retrying" % len(missing))
            time.sleep(1.0)
        raise RuntimeError("dump still incomplete after %d attempts" % attempts)

    # -- verified write -----------------------------------------------------------------------
    def write(self, params, attempts=2, reload=False):
        """Write and verify through a dump. params: [(address, index, value, is_freq)].
        reload=True for EQ Enable / EQ Preset Select: exactly one parameter, sent on its own with a longer
        pause."""
        if reload and len(params) != 1:
            raise ValueError("a reload parameter goes on its own")
        for attempt in range(attempts):
            for m in build_messages(DAC.id, params):
                self.send(m, pause=1.0 if reload else 0.25)
            state = self.dump()
            wrong = [(a, i, v, state.get((a, i))) for a, i, v, _ in params if state.get((a, i)) != v]
            if not wrong:
                return state
            self.log("   did not arrive: %s" % ", ".join("%d/%d want %d is %s" % w for w in wrong[:6]))
        raise RuntimeError("write failed after %d attempts" % attempts)
