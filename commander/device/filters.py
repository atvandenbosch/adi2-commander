"""The EQ filters as the device runs them, and their response. No Qt.

Every band and the Bass and Treble shelves are one biquad in the form of the Audio EQ Cookbook (RBJ), with
f0 and gain exactly as set. Only alpha, the term that holds Q, differs: the ADI-2 uses sin(w0 / 2Q) where
the Cookbook has sin(w0) / 2Q (confirmed by RME: forum.rme-audio.de/viewtopic.php?id=39621).
"""

from collections import namedtuple

import numpy as np

from . import params as P

FS = 48000.0
FREQS = np.logspace(np.log10(20), np.log10(20000), 241)       # where curves are compared: 1/24 octave

# One filter of a channel. name: "1".."5", "B", "T". kind: PK, LS, HS, HP, LP. freq in Hz, gain in dB, Q as
# set. active: in the signal path now. address and indices (type, gain, freq, Q; type None) say where it lives.
Filter = namedtuple("Filter", "name band kind freq gain q active address indices")


def coefficients(kind, f0, gain, q, fs=FS, cookbook=False):
    """(b, a) of one biquad, normalised on a0. cookbook: alpha as in the Cookbook, for a filter from a file."""
    b, a = terms(kind, f0, gain, q, fs, cookbook)
    return np.array(b, float), np.array(a, float)


def terms(kind, f0, gain, q, fs=FS, cookbook=False):
    """coefficients as two lists of three terms, (b0, b1, b2) and (a0, a1, a2), each as f0 is (a number or an array of
    filters): for many filters at once without stacking."""
    A = 10 ** (gain / 40)
    w0 = 2 * np.pi * f0 / fs
    c = np.cos(w0)
    al = np.sin(w0) / (2 * q) if cookbook else np.sin(w0 / (2 * q))
    if kind == "PK":
        b = [1 + al * A, -2 * c, 1 - al * A]
        a = [1 + al / A, -2 * c, 1 - al / A]
    elif kind == "LS":
        r = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * c + r), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - r)]
        a = [(A + 1) + (A - 1) * c + r, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - r]
    elif kind == "HS":
        r = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * c + r), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - r)]
        a = [(A + 1) - (A - 1) * c + r, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - r]
    elif kind == "HP":
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
        a = [1 + al, -2 * c, 1 - al]
    elif kind == "LP":
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]
        a = [1 + al, -2 * c, 1 - al]
    else:
        raise ValueError(kind)
    a0 = a[0]
    return [x / a0 for x in b], [x / a0 for x in a]


def cookbook_q(q, f0, fs=FS):
    """The Q of the Cookbook biquad with the same response as the device set to q: sin(w0) / (2 sin(w0/2q)).
    Equal at Q 0.5; apart more as f0 nears fs/2."""
    w0 = 2 * np.pi * f0 / fs
    return float(np.sin(w0) / (2 * np.sin(w0 / (2 * q))))


def device_qs(q_cookbook, f0, fs=FS):
    """The two device Qs (unrounded) with the response of a Cookbook biquad with q_cookbook: w0/2Q below
    pi/2, and beyond it (a smaller Q, mostly far below the device's 0.5); none when the Cookbook filter is
    broader than the device can make it there (2 Q_cookbook < sin(w0))."""
    w0 = 2 * np.pi * f0 / fs
    x = np.sin(w0) / (2 * q_cookbook)
    if x > 1:
        return []
    return [float(w0 / (2 * np.arcsin(x))), float(w0 / (2 * (np.pi - np.arcsin(x))))]


def response(b, a, f, fs=FS):
    """Complex response of one biquad at the frequencies f (Hz)."""
    z = np.exp(-2j * np.pi * np.asarray(f, float) / fs)
    return (b[0] + b[1] * z + b[2] * z * z) / (1 + a[1] * z + a[2] * z * z)


def response_db(flt, f, fs=FS, cookbook=False):
    """Magnitude in dB of one Filter at the frequencies f."""
    h = response(*coefficients(flt.kind, flt.freq, flt.gain, flt.q, fs, cookbook), f, fs)
    return 20 * np.log10(np.maximum(np.abs(h), 1e-12))


def total_db(filters, f, fs=FS):
    """The summed response of the filters that are in the signal path."""
    total = np.zeros(len(f))
    for flt in filters:
        if flt.active:
            total += response_db(flt, f, fs)
    return total


def band_filters(state, address, left):
    """The five bands of one EQ address (left or right channel), from the session state; [] while the state
    is incomplete. Each address has its own EQ Enable: with Dual EQ on, 0 on the left address takes only the
    left PEQ out of the path and 0 on the right address only the right one (the front panel's ON/OFF/L/R);
    with Dual EQ off both channels run the left set and the left EQ Enable takes both out."""
    out = []
    for band, (ti, gi, fi, qi) in P.BANDS.items():
        keys = [(address, i) for i in (ti, gi, fi, qi) if i is not None]
        if any(k not in state for k in keys):
            return []
        typ = state[(address, ti)] if ti is not None else 0
        kind = P.TYPE_ABBR[band][typ] if ti is not None else "PK"
        active = state.get((address, P.EQ_ENABLE)) == 1
        out.append(Filter(str(band), band, kind, state[(address, fi)], state[(address, gi)] / 2,
                          state[(address, qi)] / 10, active, address, (ti, gi, fi, qi)))
    return out


def bt_filters(state, left):
    """Bass and Treble: shared by both channels, on the left address only. Only B/T Enable takes them out of
    the path; EQ Enable does not."""
    out = []
    for name, kind, (gi, fi, qi) in (("B", "LS", P.BASS), ("T", "HS", P.TREBLE)):
        if any((left, i) not in state for i in (gi, fi, qi)):
            return []
        out.append(Filter(name, None, kind, state[(left, fi)], state[(left, gi)] / 2, state[(left, qi)] / 10,
                          state.get((left, P.BT_ENABLE)) == 1, left, (None, gi, fi, qi)))
    return out


LOUDNESS_RANGE = 20.0                            # dB of volume over which the boost goes from full to none
# Loudness: a fixed low and high shelf; only their gain moves with the volume. Frequency and Q from RME
# (forum.rme-audio.de/viewtopic.php?id=40565).
LOUDNESS_SHELVES = (("LB", "LS", 70.0, 0.7), ("LT", "HS", 3500.0, 0.7))


def loudness_gain(max_gain, low_vol_ref, volume):
    """The Loudness boost in dB of Bass or Treble at a volume (dB, also an array): the full gain at and below
    Low Vol Ref, falling linearly to none 20 dB above it (manual 8.5 and 12.4, RME on the forum as above)."""
    return max_gain * np.clip((low_vol_ref + LOUDNESS_RANGE - np.asarray(volume, float)) / LOUDNESS_RANGE, 0, 1)


def loudness_db(state, out, volumes, f, fs=FS):
    """The Loudness boost in dB at each of the volumes (rows) and frequencies f (columns), Loudness Enable aside: as
    total_db of loudness_filters per volume, in one go: per shelf the biquads of all the volumes against the same
    powers of z. The state must be complete."""
    z = np.exp(-2j * np.pi * np.asarray(f, float) / fs)
    zk = np.vstack([np.ones_like(z), z, z * z])
    ref = state[(out, P.LD_LOW_VOL_REF)] / 2
    total = np.zeros((len(volumes), len(z)))
    for (_, kind, freq, q), gi in zip(LOUDNESS_SHELVES, (P.LD_BASS, P.LD_TREBLE)):
        ba = [coefficients(kind, freq, g, q, fs) for g in loudness_gain(state[(out, gi)] / 2, ref, volumes)]
        h = np.array([b for b, _ in ba]) @ zk / (np.array([a for _, a in ba]) @ zk)
        total += 20 * np.log10(np.maximum(np.abs(h), 1e-12))
    return total


def loudness_filters(state, out, volume=None):
    """The Loudness shelves of one output address at a volume in dB (default: the output's own), with
    active = Loudness Enable; [] while the state is incomplete."""
    keys = [(out, i) for i in (P.LOUDNESS_ENABLE, P.LD_BASS, P.LD_TREBLE, P.LD_LOW_VOL_REF, P.VOLUME)]
    if any(k not in state for k in keys):
        return []
    on, bass, treble, ref, vol = (state[k] for k in keys)
    volume = vol / 10 if volume is None else volume
    return [Filter(name, None, kind, freq, float(loudness_gain(gain / 2, ref / 2, volume)), q, on == 1, out,
                   (None, gi, None, None))
            for (name, kind, freq, q), gain, gi in zip(LOUDNESS_SHELVES, (bass, treble), (P.LD_BASS, P.LD_TREBLE))]
