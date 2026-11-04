r"""The ADI-2 DAC directly over MIDI SysEx (winmm via ctypes).

Pitfalls of the device, and what follows from them:
  - only command 0x02 writes; the device confirms nothing and clamps silently -> after every write a dump
    and a comparison;
  - EQ Enable and EQ Preset Select rebuild the filter set -> sent on their own, then read back;
  - never an index > 19 to address 5 (that hits the shared Bass/Treble);
  - the status stream (0x07) must not hold a buffer.
"""

import ctypes as C
import threading
import time
from ctypes import wintypes as W

from . import codec

HEADER = codec.HEADER


def build_messages(params):
    """SysEx messages (cmd 0x02) for a list of parameters [(address, index, value, is_freq)];
    split to stay under 256 bytes."""
    for address, index, _, _ in params:
        if address == 5 and index > 19:
            raise ValueError("address 5 index %d hits the shared Bass/Treble" % index)
    triplets = [codec.encode(a, i, v, f) for a, i, v, f in params]
    return [codec.sysex(triplets[i:i + 80], 0x02) for i in range(0, len(triplets), 80)]


# A dump is complete when all of these are in it.
REQUIRED = ({(3, i) for i in list(range(1, 19)) + [20, 21, 22, 23]} | {(4, i) for i in range(2, 29)}
            | {(5, i) for i in range(2, 20)} | {(12, 2)})

# ---------------------------------------------------------------------------------------------
# winmm

class MIDIHDR(C.Structure):
    _fields_ = [("lpData", C.c_void_p), ("dwBufferLength", W.DWORD), ("dwBytesRecorded", W.DWORD),
                ("dwUser", C.c_size_t), ("dwFlags", W.DWORD), ("lpNext", C.c_void_p),
                ("reserved", C.c_size_t), ("dwOffset", W.DWORD), ("dwReserved", C.c_size_t * 8)]


class MIDIINCAPSW(C.Structure):
    _fields_ = [("wMid", W.WORD), ("wPid", W.WORD), ("vDriverVersion", C.c_uint),
                ("szPname", C.c_wchar * 32), ("dwSupport", W.DWORD)]


class MIDIOUTCAPSW(C.Structure):
    _fields_ = [("wMid", W.WORD), ("wPid", W.WORD), ("vDriverVersion", C.c_uint),
                ("szPname", C.c_wchar * 32), ("wTechnology", W.WORD), ("wVoices", W.WORD),
                ("wNotes", W.WORD), ("wChannelMask", W.WORD), ("dwSupport", W.DWORD)]


MHDR_DONE, MHDR_PREPARED = 1, 2
_mm = C.WinDLL("winmm")
_H = C.c_void_p
_mm.midiInGetNumDevs.restype = C.c_uint
_mm.midiOutGetNumDevs.restype = C.c_uint
_mm.midiInGetDevCapsW.argtypes = [C.c_size_t, C.POINTER(MIDIINCAPSW), C.c_uint]
_mm.midiOutGetDevCapsW.argtypes = [C.c_size_t, C.POINTER(MIDIOUTCAPSW), C.c_uint]
_mm.midiInOpen.argtypes = [C.POINTER(_H), C.c_uint, C.c_size_t, C.c_size_t, W.DWORD]
_mm.midiOutOpen.argtypes = [C.POINTER(_H), C.c_uint, C.c_size_t, C.c_size_t, W.DWORD]
for _f in ("midiInPrepareHeader", "midiInUnprepareHeader", "midiInAddBuffer",
           "midiOutPrepareHeader", "midiOutUnprepareHeader", "midiOutLongMsg"):
    getattr(_mm, _f).argtypes = [_H, C.POINTER(MIDIHDR), C.c_uint]
for _f in ("midiInStart", "midiInStop", "midiInReset", "midiInClose", "midiOutClose", "midiOutReset"):
    getattr(_mm, _f).argtypes = [_H]
for _f in ("midiInOpen", "midiOutOpen", "midiInPrepareHeader", "midiInUnprepareHeader", "midiInAddBuffer",
           "midiOutPrepareHeader", "midiOutUnprepareHeader", "midiOutLongMsg", "midiInStart", "midiInStop",
           "midiInReset", "midiInClose", "midiOutClose", "midiOutReset", "midiInGetDevCapsW",
           "midiOutGetDevCapsW"):
    getattr(_mm, _f).restype = C.c_uint


def list_ports():
    """([input port names], [output port names])"""
    ins, outs = [], []
    for i in range(_mm.midiInGetNumDevs()):
        c = MIDIINCAPSW()
        _mm.midiInGetDevCapsW(i, C.byref(c), C.sizeof(c))
        ins.append(c.szPname)
    for i in range(_mm.midiOutGetNumDevs()):
        c = MIDIOUTCAPSW()
        _mm.midiOutGetDevCapsW(i, C.byref(c), C.sizeof(c))
        outs.append(c.szPname)
    return ins, outs


# The first winmm call waits until Windows has started its MIDI service, which it does on demand: some 10 s on a
# fresh system. warm_up makes that call on a thread of its own; until it returns, WinmmPort finds no device.
_started = threading.Event()
_started.set()


def warm_up():
    """Start Windows' MIDI service now, off the calling thread (the GUI's)."""
    def first_call():
        list_ports()
        _started.set()
    _started.clear()
    threading.Thread(target=first_call, daemon=True).start()


MMSYSERR_ALLOCATED = 4


class DeviceNotFound(RuntimeError):
    """No ADI-2 MIDI port: the device is off, in standby or not connected."""


class PortBusy(OSError):
    """The ADI-2 MIDI port is held by another program."""


def _check(result, what):
    if result == MMSYSERR_ALLOCATED and what in ("midiInOpen", "midiOutOpen"):
        raise PortBusy("%s: the ADI-2 MIDI port is in use by another program" % what)
    if result != 0:
        raise OSError("%s failed (winmm %d)" % (what, result))


class WinmmPort:
    """The ADI-2 MIDI ports through winmm: raw SysEx out, raw SysEx in. The simulator replaces this."""
    NBUF, BUFLEN = 32, 1024

    def __init__(self):
        if not _started.is_set():
            raise DeviceNotFound("Windows is starting its MIDI service")
        ins, outs = list_ports()
        ii = [i for i, n in enumerate(ins) if "ADI-2" in n]
        oo = [i for i, n in enumerate(outs) if "ADI-2" in n]
        if not ii or not oo:
            raise DeviceNotFound("no ADI-2 MIDI port found (in: %s; out: %s)" % (ins, outs))
        self.names = (ins[ii[0]], outs[oo[0]])
        self.h_in, self.h_out = _H(), _H()
        try:
            _check(_mm.midiInOpen(C.byref(self.h_in), ii[0], 0, 0, 0), "midiInOpen")
            _check(_mm.midiOutOpen(C.byref(self.h_out), oo[0], 0, 0, 0), "midiOutOpen")
            self.bufs = [C.create_string_buffer(self.BUFLEN) for _ in range(self.NBUF)]
            self.hdrs = []
            for b in self.bufs:
                h = MIDIHDR()
                h.lpData = C.cast(b, C.c_void_p)
                h.dwBufferLength = self.BUFLEN
                _check(_mm.midiInPrepareHeader(self.h_in, C.byref(h), C.sizeof(h)), "midiInPrepareHeader")
                _check(_mm.midiInAddBuffer(self.h_in, C.byref(h), C.sizeof(h)), "midiInAddBuffer")
                self.hdrs.append(h)
            _check(_mm.midiInStart(self.h_in), "midiInStart")
        except Exception:
            self.close()
            raise

    def close(self):
        if self.h_in:
            _mm.midiInStop(self.h_in)
            _mm.midiInReset(self.h_in)
            for h in getattr(self, "hdrs", []):
                _mm.midiInUnprepareHeader(self.h_in, C.byref(h), C.sizeof(h))
            _mm.midiInClose(self.h_in)
            self.h_in = None
        if self.h_out:
            _mm.midiOutClose(self.h_out)
            self.h_out = None

    def send(self, msg):
        """Send one SysEx message and wait until winmm has delivered it."""
        data = bytes(msg)
        buf = C.create_string_buffer(data, len(data))
        h = MIDIHDR()
        h.lpData = C.cast(buf, C.c_void_p)
        h.dwBufferLength = len(data)
        _check(_mm.midiOutPrepareHeader(self.h_out, C.byref(h), C.sizeof(h)), "midiOutPrepareHeader")
        _check(_mm.midiOutLongMsg(self.h_out, C.byref(h), C.sizeof(h)), "midiOutLongMsg")
        t0 = time.time()
        while not (h.dwFlags & MHDR_DONE):
            if time.time() - t0 > 3:
                _mm.midiOutReset(self.h_out)
                raise TimeoutError("SysEx not delivered")
            time.sleep(0.005)
        _mm.midiOutUnprepareHeader(self.h_out, C.byref(h), C.sizeof(h))

    def present(self):
        """Whether the device is still there. In standby, switched off or unplugged its ports leave the
        port list at once, also while they are open here."""
        ins, outs = list_ports()
        return self.names[0] in ins and self.names[1] in outs

    def receive(self):
        """Every message that has come in since the last call, status messages included. Each buffer
        goes straight back into the pool, so that the status stream cannot exhaust it."""
        out = []
        for h in self.hdrs:
            if not (h.dwFlags & MHDR_DONE):
                continue
            n = h.dwBytesRecorded
            if n:
                out.append(list(C.string_at(h.lpData, n)))
            h.dwBytesRecorded = 0
            h.dwFlags = MHDR_PREPARED
            _mm.midiInAddBuffer(self.h_in, C.byref(h), C.sizeof(h))
        return out
