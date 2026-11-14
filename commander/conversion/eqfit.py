"""From a curve to the device setting that comes closest to it, all bands together.

The curve is dB at filters.FREQS. The device: five bands (a choice of type only on band 1 and 5), optionally Bass
and Treble, each a biquad as filters.coefficients computes it, on the device's grid. The error is the RMS difference
over FREQS, every point alike; with a free level (the default) a constant difference does not count, since the
volume takes it; with a fixed level it does, and the bands have to make the curve at its own level.

Which filter sits on which band does not change the curve, so the filters are fitted as a set: a set is possible when
every filter has a band of its own that takes its kind, frequency and Q. After every refinement the bands are chosen
anew, keeping the filters furthest from their band's limits.

The search, from several starts, each taken to the end:
1. filter by filter, the candidate (any kind, on any band still free for it, from a grid of frequencies and Qs, the
   gain by projection) that takes most off what is left;
2. Levenberg-Marquardt on all filters together, within the limits of their bands;
3. per filter, then per pair: take it out, put the best candidates in its place for what is then left, refine all;
   keep it when better; again until nothing helps;
4. a High Pass or High Cut gives way to the best filter of another kind unless that is more than THRESHOLD dB RMS
   worse: a roll-off only where the curve itself rolls off;
5. onto the grid, then to neighbouring grid values one at a time while that helps; of the best few, the one that is
   best on the grid.

The starts: greedy with and without refining along the way, one for each first band, then up to RANDOM random ones,
mostly wild (every band drawn over its whole range, so that any setting has a chance and with starts enough the search
ends in any optimum), else greedy with one of the TOP best candidates at random. The draws follow from the shape of
the curve, not its level: the same curve gives the same setting.
"""

import hashlib
import math
import random
import time
from collections import namedtuple

import numpy as np

from ..device import params as P
from ..device.filters import FREQS, FS, terms

THRESHOLD = 0.1                                  # dB RMS a High Pass / High Cut must win by
PRUNE = 10                                       # a trial this many times worse than the current is not refined
TRIAL_ITERS = 25                                 # refinement of a trial before it is judged
CANDIDATE_S = 0.05                               # a setting being tried is passed on at most this often
EXTEND = 2                                       # the best this many of the five bands go on to Bass/Treble and the grid
RANDOM = 4                                       # random starts at most, after the fixed ones
WILD = 0.75                                      # the chance that a random start is wild
TOP = 5                                          # a greedy random start picks among this many best candidates
FLOOR = 0.001                                    # dB RMS: below this there is nothing left to gain
NO_GAIN = ("HP", "LP")
GAIN = P.EQ_RANGES[P.BANDS[1][1]][1] / 2         # dB either way, on every band and on Bass/Treble
CODES = {"PK": 0, "LS": 1, "HS": 2, "HP": 3, "LP": 4}
KINDS = list(CODES)
CAND_STEP = 1 / 6                                # octaves between candidate frequencies
CAND_Q = {"PK": (0.5, 0.7, 1.0, 1.4, 2.0, 3.0, 4.5, 6.5, 9.9), "LS": (0.5, 0.7, 1.0, 1.5, 2.5, 4.0, 7.0),
          "HP": (0.5, 0.7, 1.0, 1.5, 3.0, 6.0)}
CAND_Q["HS"], CAND_Q["LP"] = CAND_Q["LS"], CAND_Q["HP"]

# One band: its name ("1".."5", "B", "T"), the kinds it takes, frequency range and index, Q range, and the
# frequency and Q it has when it is not used (flat, as Clear leaves it)
Slot = namedtuple("Slot", "name kinds flo fhi fi qlo qhi rest")
# One band set: kind PK, LS, HS, HP or LP; freq in Hz, gain in dB, Q as the device shows them
Setting = namedtuple("Setting", "name kind freq gain q")
# settings: one per band, in the order of the bands. level: how much louder the setting is than the curve, a
# constant in dB (0 with a fixed level). rms and peak: what is left after that, in dB.
Result = namedtuple("Result", "settings rms peak level")


class Cancelled(Exception):
    pass


def slots(tone):
    """The bands to fit: 1..5, and Bass and Treble when tone."""
    out = []
    for band, (ti, gi, fi, qi) in P.BANDS.items():
        kinds = tuple(P.TYPE_ABBR[band]) if ti is not None else ("PK",)
        (flo, fhi), (qlo, qhi) = P.EQ_RANGES[fi], P.EQ_RANGES[qi]
        rest = (float(P.FACTORY_BANDS[fi]), P.FACTORY_BANDS[qi] / 10)
        out.append(Slot(str(band), kinds, flo, fhi, fi, qlo / 10, qhi / 10, rest))
    if tone:
        for name, kind, (gi, fi, qi) in (("B", "LS", P.BASS), ("T", "HS", P.TREBLE)):
            (flo, fhi), (qlo, qhi) = P.EQ_RANGES[fi], P.EQ_RANGES[qi]
            rest = (float(P.FACTORY_BT[fi]), P.FACTORY_BT[qi] / 10)
            out.append(Slot(name, (kind,), flo, fhi, fi, qlo / 10, qhi / 10, rest))
    return out


class Model:
    """Responses at FREQS for one fs, of many filters at once."""

    def __init__(self, fs):
        self.fs = fs
        z = np.exp(-2j * np.pi * FREQS / fs)
        self.zk = np.vstack([np.ones_like(z), z, z * z])

    def db(self, kind, f, g, q):
        return self.mixed(np.array([CODES[kind]]), np.array([f], float), np.array([g], float),
                          np.array([q], float))[0]

    def mixed(self, code, f, g, q):
        """Responses of filters of mixed kinds (code per filter, broadcast against f, g, q), shape f.shape +
        (len(FREQS),): filters.terms for all filters of a kind together."""
        shape = np.shape(f)
        f, g, q = (np.asarray(x, float).ravel() if np.shape(x) == shape else np.broadcast_to(x, shape).ravel()
                   for x in (f, g, q))
        code = np.asarray(code)
        b = np.empty((len(f), 3))
        a = np.empty((len(f), 3))
        if code.size == 1:
            groups = [(int(code.flat[0]), slice(None))]
        else:
            code = (code if code.shape == shape else np.broadcast_to(code, shape)).ravel()
            groups = [(c, code == c) for c in set(code.tolist())]
        for c, i in groups:
            bi, ai = terms(KINDS[c], f[i], g[i], q[i], self.fs)
            for k in range(3):
                b[i, k], a[i, k] = bi[k], ai[k]
        h = (b @ self.zk) / (a @ self.zk)
        return (20 * np.log10(np.maximum(np.abs(h), 1e-12))).reshape(shape + (self.zk.shape[1],))


class Candidates:
    """Per band and kind: a grid of frequencies and Qs, with the response of each (at +6 dB for a kind with gain,
    scaled to 1 dB: the gain then follows by projection)."""

    def __init__(self, model, sl):
        self.table, self.centred = {}, {}
        for s in sl:
            for kind in s.kinds:
                n = int(math.log2(s.fhi / s.flo) / CAND_STEP) + 1
                fs_ = np.geomspace(s.flo, s.fhi, n)
                qs = np.array([q for q in CAND_Q[kind] if s.qlo <= q <= s.qhi])
                F, Q = np.meshgrid(fs_, qs, indexing="ij")
                F, Q = F.ravel(), Q.ravel()
                if kind in NO_GAIN:
                    shape = model.mixed(np.array(CODES[kind]), F, np.zeros_like(F), Q)
                else:
                    shape = model.mixed(np.array(CODES[kind]), F, np.full_like(F, 6.0), Q) / 6
                self.table[(s.name, kind)] = (F, Q, shape)
                c = shape - shape.mean(1, keepdims=True)
                self.centred[(s.name, kind)] = (c, (c * c).sum(1))

    def best(self, model, s, r, offset):
        """The candidate for band s that leaves least of r: (kind, f, g, q, response). The cost of a response S with
        gain g, without forming the residuals: |r|² - 2g S·r + g² |S|²."""
        best = None
        for kind in s.kinds:
            F, Q, S = self.table[(s.name, kind)]
            if offset:
                S, SS = self.centred[(s.name, kind)]
                rr = r - r.mean()
            else:
                SS, rr = (S * S).sum(1), r
            Sr = S @ rr
            if kind in NO_GAIN:
                G = np.zeros(len(F))
                cost = rr @ rr - 2 * Sr + SS
            else:
                G = np.clip(Sr / np.maximum(SS, 1e-12), -GAIN, GAIN)
                cost = rr @ rr - 2 * G * Sr + G * G * SS
            i = int(np.argmin(cost))
            if best is None or cost[i] < best[0]:
                best = (float(cost[i]), kind, float(F[i]), float(G[i]), float(Q[i]))
        _, kind, f, g, q = best
        return kind, f, g, q, model.db(kind, f, g, q)


def bounds(s, kind):
    lo = [math.log2(s.flo)] + ([] if kind in NO_GAIN else [-GAIN]) + [math.log2(s.qlo)]
    hi = [math.log2(s.fhi)] + ([] if kind in NO_GAIN else [GAIN]) + [math.log2(s.qhi)]
    return lo, hi


def pack(kind, f, g, q):
    return [math.log2(f)] + ([] if kind in NO_GAIN else [g]) + [math.log2(q)]


class Problem:
    """Bands with their kinds fixed, as one parameter vector p; every evaluation in one go."""

    def __init__(self, model, sl, kinds, target, offset):
        self.m, self.sl, self.kinds, self.t, self.offset = model, sl, kinds, target, offset
        self.sizes = [len(bounds(s, k)[0]) for s, k in zip(sl, kinds)]
        self.lo = np.concatenate([bounds(s, k)[0] for s, k in zip(sl, kinds)])
        self.hi = np.concatenate([bounds(s, k)[1] for s, k in zip(sl, kinds)])
        self.code = np.array([CODES[k] for k in kinds])
        fi, gi, qi, i = [], [], [], 0
        for n in self.sizes:
            fi.append(i)
            gi.append(i + 1 if n == 3 else -1)
            qi.append(i + n - 1)
            i += n
        self.fi, self.gi, self.qi = np.array(fi), np.array(gi), np.array(qi)
        self.owner = np.repeat(np.arange(len(sl)), self.sizes)          # the band of each parameter

    def fgq(self, p):
        """f, g, q per band from one parameter vector."""
        return 2 ** p[self.fi], np.where(self.gi >= 0, p[np.maximum(self.gi, 0)], 0.0), 2 ** p[self.qi]

    def jacobian(self, p, parts, h=1e-5):
        """d(total)/dp by forward differences, each column from its own band only: one evaluation of len(p)
        filters instead of len(p) evaluations of all of them."""
        M = len(p)
        P_ = p + h * np.eye(M)
        f, q = 2 ** P_[np.arange(M), self.fi[self.owner]], 2 ** P_[np.arange(M), self.qi[self.owner]]
        gidx = self.gi[self.owner]
        g = np.where(gidx >= 0, P_[np.arange(M), np.maximum(gidx, 0)], 0.0)
        pert = self.m.mixed(self.code[self.owner], f, g, q)
        return ((pert - parts[self.owner]) / h).T

    def vector(self, values):
        return np.array([x for k, v in zip(self.kinds, values) for x in pack(k, *v)])

    def values(self, p):
        f, g, q = self.fgq(p)
        return [(float(a), float(b), float(c)) for a, b, c in zip(f, g, q)]

    def totals(self, P_):
        P_ = np.atleast_2d(P_)
        f = 2 ** P_[:, self.fi]
        g = np.where(self.gi >= 0, P_[:, np.maximum(self.gi, 0)], 0.0)
        q = 2 ** P_[:, self.qi]
        return self.m.mixed(self.code, f, g, q).sum(1)

    def residual(self, total):
        r = total - self.t
        return r - r.mean(-1, keepdims=True) if self.offset else r

    def lm(self, p, iters=60):
        """Levenberg-Marquardt within the bounds (steps clipped onto them)."""
        p = np.clip(np.asarray(p, float), self.lo, self.hi)
        parts = self.m.mixed(self.code, *self.fgq(p))
        r = self.residual(parts.sum(0))
        cost = r @ r
        lam, M = 1e-2, len(p)
        for _ in range(iters):
            J = self.jacobian(p, parts)
            if self.offset:
                J = J - J.mean(0, keepdims=True)
            A, g = J.T @ J, J.T @ r
            while True:
                step = np.linalg.solve(A + lam * (np.diag(np.diag(A)) + 1e-9 * np.eye(M)), -g)
                pn = np.clip(p + step, self.lo, self.hi)
                pparts = self.m.mixed(self.code, *self.fgq(pn))
                rn = self.residual(pparts.sum(0))
                cn = rn @ rn
                if cn < cost:
                    break
                lam *= 4
                if lam > 1e10:
                    return p, cost
            done = cost - cn < 1e-7 * max(cost, 1e-12)
            p, parts, r, cost = pn, pparts, rn, cn
            lam = max(lam / 3, 1e-9)
            if done:
                break
        return p, cost


def fits(s, kind, f, q):
    return kind in s.kinds and s.flo * (1 - 1e-9) <= f <= s.fhi * (1 + 1e-9) and s.qlo - 1e-9 <= q <= s.qhi + 1e-9


def margin(s, f, q):
    """How far a filter is from the limits of a band, in octaves, at most 1."""
    m = min(math.log2(f / s.flo), math.log2(s.fhi / f), math.log2(s.qhi / q), math.log2(q / s.qlo))
    return min(max(m, 0.0), 1.0)


def assign(sl, kinds, vals, free=None):
    """The band of each filter (indices into sl, all different) among those it fits, keeping the filters furthest
    from their band's limits (the smallest margin first, then the next); None when there is no assignment. free:
    the bands to use (all by default)."""
    free = range(len(sl)) if free is None else free
    ok = [[j for j in free if fits(sl[j], k, v[0], v[2])] for k, v in zip(kinds, vals)]
    order = sorted(range(len(kinds)), key=lambda i: len(ok[i]))
    cur, used, best = [None] * len(kinds), set(), [None, None]

    def rec(n):
        if n == len(order):
            score = sorted(margin(sl[cur[i]], vals[i][0], vals[i][2]) for i in range(len(kinds)))
            if best[0] is None or score > best[0]:
                best[0], best[1] = score, list(cur)
            return
        i = order[n]
        for j in ok[i]:
            if j not in used:
                used.add(j)
                cur[i] = j
                rec(n + 1)
                used.discard(j)

    rec(0)
    return best[1]


def available(sl, kinds, vals):
    """The bands a further filter can take: those the filters there are can do without."""
    return [j for j in range(len(sl)) if assign(sl, kinds, vals, [x for x in range(len(sl)) if x != j]) is not None]


def place(model, cands, sl, kinds, vals, r, offset, bands=None, only=None):
    """Beside the filters there are, the candidate that leaves least of r, on any band free for it (or among
    bands): (band, kind, f, g, q, response). only: the kinds allowed."""
    bands = available(sl, kinds, vals) if bands is None else bands
    best, seen = None, set()
    for j in bands:
        s = sl[j]
        ks = tuple(k for k in s.kinds if only is None or k in only)
        sig = (ks, s.flo, s.fhi, s.qlo, s.qhi)
        if not ks or sig in seen:                              # bands 2 and 3 are the same
            continue
        seen.add(sig)
        kind, f, g, q, resp = cands.best(model, s._replace(kinds=ks), r, offset)
        rr = r - resp
        cost = ((rr - rr.mean()) ** 2).sum() if offset else (rr ** 2).sum()
        if best is None or cost < best[0]:
            best = (cost, j, kind, f, g, q, resp)
    return best[1:]


class State:
    """A setting under way: per filter its kind, (f, g, q) and band, refined together. seen(state): called after
    every refinement, of this state and of the trials made from it."""

    def __init__(self, model, sl, target, offset, kinds, values, seen=None):
        self.m, self.sl, self.t, self.offset, self.seen = model, sl, target, offset, seen
        self.kinds, self.vals = list(kinds), list(values)
        self.bands = assign(sl, self.kinds, self.vals)
        self.refine()

    def refine(self, iters=60):
        for _ in range(3):                                     # again while a filter is better off on another band
            prob = Problem(self.m, [self.sl[j] for j in self.bands], self.kinds, self.t, self.offset)
            p, self.cost = prob.lm(prob.vector(self.vals), iters)
            self.vals = prob.values(p)
            bands = assign(self.sl, self.kinds, self.vals)
            if bands == self.bands:
                break
            self.bands = bands
        if self.seen is not None:
            self.seen(self)

    def parts(self):
        return [self.m.db(k, *v) for k, v in zip(self.kinds, self.vals)]

    def copy(self):
        s = State.__new__(State)
        s.__dict__.update(self.__dict__)
        s.kinds, s.vals, s.bands = list(self.kinds), list(self.vals), list(self.bands)
        return s

    def replace(self, kinds, vals):
        s = self.copy()
        s.kinds, s.vals = list(kinds), list(vals)
        s.bands = assign(self.sl, s.kinds, s.vals)
        return s

    def settings(self):
        """In the order of the bands."""
        order = sorted(range(len(self.sl)), key=lambda i: self.bands[i])
        return [Setting(self.sl[self.bands[i]].name, self.kinds[i], *self.vals[i]) for i in order]


def fill(model, cands, sl, target, refine, first=None, offset=True):
    """Fill the bands one filter at a time with the candidate, on any band still free for it, that takes most off
    what is left. refine: after each, refine all filters so far. first: the band of the first filter, for another
    start than the greedy one. offset: a constant does not count (a free level)."""
    kinds, vals = [], []
    r = target.copy()
    while len(kinds) < len(sl):
        bands = [first] if first is not None and not kinds else None
        _, kind, f, g, q, resp = place(model, cands, sl, kinds, vals, r, offset, bands)
        kinds.append(kind)
        vals.append((f, g, q))
        if refine:
            prob = Problem(model, [sl[j] for j in assign(sl, kinds, vals)], kinds, target, offset)
            p, _ = prob.lm(prob.vector(vals), 25)
            vals = prob.values(p)
            r = target - prob.totals(p)[0]
        else:
            r = r - resp
    return kinds, vals


def seed_of(target, fs, tone):
    """The seed of the random starts: from the shape of target (its mean taken off), fs and tone."""
    shape = np.round(target - target.mean(), 6)
    return int.from_bytes(hashlib.sha256(shape.tobytes() + repr((float(fs), bool(tone))).encode()).digest()[:8], "big")


def wild_fill(rng, sl):
    """Per band a kind, frequency, Q and gain drawn over its whole range."""
    kinds, vals = [], []
    for s in sl:
        kind = rng.choice(s.kinds)
        f = 2 ** rng.uniform(math.log2(s.flo), math.log2(s.fhi))
        q = 2 ** rng.uniform(math.log2(s.qlo), math.log2(s.qhi))
        kinds.append(kind)
        vals.append((f, 0.0 if kind in NO_GAIN else rng.uniform(-GAIN, GAIN), q))
    return kinds, vals


def random_fill(rng, model, cands, sl, target, offset=True):
    """As fill, refining along the way, but each filter one of the TOP best candidates at random."""
    kinds, vals = [], []
    r = target.copy()
    while len(kinds) < len(sl):
        options, seen = [], set()
        rr = r - r.mean() if offset else r
        for j in available(sl, kinds, vals):
            s = sl[j]
            sig = (s.kinds, s.flo, s.fhi, s.qlo, s.qhi)
            if sig in seen:
                continue
            seen.add(sig)
            for kind in s.kinds:
                F, Q, S = cands.table[(s.name, kind)]
                S, SS = cands.centred[(s.name, kind)] if offset else (S, (S * S).sum(1))
                Sr = S @ rr
                if kind in NO_GAIN:
                    G = np.zeros(len(F))
                    cost = rr @ rr - 2 * Sr + SS
                else:
                    G = np.clip(Sr / np.maximum(SS, 1e-12), -GAIN, GAIN)
                    cost = rr @ rr - 2 * G * Sr + G * G * SS
                for i in np.argsort(cost)[:TOP]:
                    options.append((float(cost[i]), kind, float(F[i]), float(G[i]), float(Q[i])))
        options.sort()
        _, kind, f, g, q = rng.choice(options[:TOP])
        kinds.append(kind)
        vals.append((f, g, q))
        prob = Problem(model, [sl[j] for j in assign(sl, kinds, vals)], kinds, target, offset)
        p, _ = prob.lm(prob.vector(vals), 25)
        vals = prob.values(p)
        r = target - prob.totals(p)[0]
    return kinds, vals


def backfit(st, cands, tick, rounds=6, improved=None):
    """Per filter, then per pair: out, put the best candidates for what is then left on any band that can be freed
    for them, refine all; keep when better. Which band a filter lands on does not matter, so a pair needs one order
    only. improved(state): called with every state kept."""
    n = len(st.sl)
    singles = [(k,) for k in range(n)]
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]

    def sweep(st, groups):
        better = False
        for grp in groups:
            tick()
            parts = st.parts()
            r = st.t - (sum(parts) - sum(parts[k] for k in grp))
            kinds = [k for i, k in enumerate(st.kinds) if i not in grp]
            vals = [v for i, v in enumerate(st.vals) if i not in grp]
            new = {}
            for k in grp:
                _, kind, f, g, q, resp = place(st.m, cands, st.sl, kinds, vals, r, st.offset)
                kinds, vals, r = kinds + [kind], vals + [(f, g, q)], r - resp
                new[k] = (kind, (f, g, q))
            rr = r - r.mean() if st.offset else r
            if rr @ rr > PRUNE * st.cost + 1e-9:
                continue
            trial = st.replace([new[i][0] if i in new else k for i, k in enumerate(st.kinds)],
                               [new[i][1] if i in new else v for i, v in enumerate(st.vals)])
            trial.refine(iters=TRIAL_ITERS)
            if trial.cost < st.cost * (1 - 1e-6) - 1e-12:
                trial.refine()
                st, better = trial, True
                if improved is not None:
                    improved(st)
        return st, better

    for _ in range(rounds):
        st, better = sweep(st, singles)                         # one filter at a time until that is stuck
        if better:
            continue
        st, better = sweep(st, pairs)                           # then pairs
        if not better:
            break
    return st


def drop_passes(st, cands, tick):
    """A High Pass or High Cut gives way to the best filter of another kind, on any band free for it, unless that is
    more than THRESHOLD dB RMS worse."""
    n = len(st.t)
    for k in range(len(st.kinds)):
        if st.kinds[k] not in NO_GAIN:
            continue
        tick()
        parts = st.parts()
        rest = st.t - (sum(parts) - parts[k])
        kinds = [x for i, x in enumerate(st.kinds) if i != k]
        vals = [x for i, x in enumerate(st.vals) if i != k]
        _, kind, f, g, q, _ = place(st.m, cands, st.sl, kinds, vals, rest, st.offset, only=("PK", "LS", "HS"))
        trial = st.replace(st.kinds[:k] + [kind] + st.kinds[k + 1:], st.vals[:k] + [(f, g, q)] + st.vals[k + 1:])
        trial.refine()
        if math.sqrt(trial.cost / n) <= math.sqrt(st.cost / n) + THRESHOLD:
            st = trial
    return st


def on_grid(slot, kind, f, g, q):
    f = P.snap_freq(f, slot.fi)
    g = 0.0 if kind in NO_GAIN else min(max(round(g * 2) / 2, -GAIN), GAIN)
    q = min(max(round(q * 10) / 10, slot.qlo), slot.qhi)
    return f, g, q


def freq_neighbours(slot, f):
    out = set()
    a = b = f
    for _ in range(3):
        a, b = P.next_on_grid(a, 1), P.next_on_grid(b, -1)
        out |= {a, b}
    for o in (1 / 24, 1 / 12, 1 / 6):
        out |= {P.snap_freq(f * 2 ** o, slot.fi), P.snap_freq(f / 2 ** o, slot.fi)}
    return [x for x in out if slot.flo <= x <= slot.fhi and x != f]


def grid_search(model, sl, kinds, settings, target, offset=True):
    """From the rounded fit, move one value at a time to a neighbouring grid value while that helps. offset: a
    constant does not count (a free level)."""
    cur = [list(x) for x in settings]
    parts = [model.db(k, *x) for k, x in zip(kinds, cur)]
    total = sum(parts)
    best = _cost(total, target, offset)
    for _ in range(40):
        better = False
        for k, s in enumerate(sl):
            f, g, q = cur[k]
            cands = [(x, g, q) for x in freq_neighbours(s, f)]
            if kinds[k] not in NO_GAIN:
                cands += [(f, g + d, q) for d in (-1, -0.5, 0.5, 1) if -GAIN <= g + d <= GAIN]
            cands += [(f, g, round(q + d, 1)) for d in (-0.3, -0.2, -0.1, 0.1, 0.2, 0.3)
                      if s.qlo <= round(q + d, 1) <= s.qhi]
            C = np.array(cands, float)
            resp = model.mixed(np.array(CODES[kinds[k]]), C[:, 0], C[:, 1], C[:, 2])
            R = total - parts[k] + resp - target
            if offset:
                R = R - R.mean(1, keepdims=True)
            costs = (R ** 2).sum(1)
            j = int(np.argmin(costs))
            if costs[j] < best - 1e-12:
                best = float(costs[j])
                total = total - parts[k] + resp[j]
                parts[k], cur[k] = resp[j], list(cands[j])
                better = True
        if not better:
            break
    return [tuple(x) for x in cur]


def _cost(total, target, offset=True):
    r = total - target
    if offset:
        r = r - r.mean()
    return float(r @ r)


def result(settings, target, fs, free_level=True):
    """A Result for settings against target (dB at FREQS); with a fixed level, its level is 0."""
    diff = response(settings, fs) - target
    level = float(diff.mean()) if free_level else 0.0
    diff = diff - level
    return Result(list(settings), float(np.sqrt((diff ** 2).mean())), float(np.abs(diff).max()), level)


def _start(sl, settings):
    """A start as kinds and values for every band of sl, onto the grid; a band it does not set is flat."""
    given = {s.name: s for s in settings}
    names = {s.name for s in sl}
    if not set(given) <= names:
        raise ValueError("no such band: %s" % ", ".join(sorted(set(given) - names)))
    kinds, vals = [], []
    for s in sl:
        x = given.get(s.name)
        if x is None:                                           # the first kind: Peak, or the shelf of Bass/Treble
            kind, f, g, q = s.kinds[0], s.rest[0], 0.0, s.rest[1]
        else:
            if x.kind not in s.kinds:
                raise ValueError("band %s does not take %s" % (s.name, x.kind))
            kind, (f, g, q) = x.kind, on_grid(s, x.kind, x.freq, x.gain, x.q)
        kinds.append(kind)
        vals.append((f, g, q))
    return kinds, vals


def fit(target, fs=FS, tone=False, starts=(), progress=None, cancel=None, candidate=None, free_level=True):
    """The device setting closest to target (dB at FREQS): a Result with a setting for every band.

    free_level: a constant difference does not count, the volume takes it; else the bands make target at its own
    level. tone: Bass and Treble take part. starts: settings to start from as well, each a list of Setting by band name
    (for instance the filters of a file put on the bands one by one); the result is never worse than any of them.
    progress(fraction, result): called as the search goes on, with the best so far (not yet on the grid).
    candidate(result): called with a setting the search is trying now, better or not, at most every CANDIDATE_S
    seconds. cancel(): asked now and then; when it says True, fit raises Cancelled."""
    model = Model(fs)
    curve = np.asarray(target, float)
    free = free_level
    target = np.round(curve - curve.mean() if free else curve, 9)   # free: the shape only, to the last bit
    sl = slots(tone)
    cands = Candidates(model, sl)
    five = sl[:5]
    given = [_start(sl, s) for s in starts]

    def tick():
        if cancel is not None and cancel():
            raise Cancelled

    # Independent starts for the five bands: greedy with and without refining along the way, and one for each
    # first band; a first band like an earlier one (2 and 3) gives the same start.
    firsts, seen = [], set()
    for k, s in enumerate(five):
        if (s.kinds, s.flo, s.fhi, s.qlo, s.qhi) not in seen:
            seen.add((s.kinds, s.flo, s.fhi, s.qlo, s.qhi))
            firsts.append(k)
    plans = [(True, None), (False, None)] + [(True, k) for k in firsts]
    steps = len(plans) + RANDOM + (EXTEND if tone else 0) + len(given)
    done = [0]

    def report(st):
        done[0] += 1
        if progress is not None:
            progress(done[0] / steps, result(st.settings(), curve, fs, free))

    last = [0.0]

    def seen(st):
        now = time.perf_counter()
        if now - last[0] >= CANDIDATE_S:
            last[0] = now
            candidate(result(st.settings(), curve, fs, free))

    seen = seen if candidate is not None else None

    def interim(st, pool):
        """Within a start, as it gets better: the best so far of this phase, the start included."""
        if progress is not None:
            progress(done[0] / steps, result(min(pool + [st], key=lambda s: s.cost).settings(), curve, fs, free))

    found = []
    for refine, first in plans:
        tick()
        kinds, vals = fill(model, cands, five, target, refine, first, free)
        st = State(model, five, target, free, kinds, vals, seen)
        interim(st, found)
        st = backfit(st, cands, tick, improved=lambda st: interim(st, found))
        found.append(drop_passes(st, cands, tick))
        report(min(found, key=lambda s: s.cost))

    # The random starts, searched to the end the same way, while there is something left to gain.
    rng = random.Random(seed_of(target, fs, tone))
    for _ in range(RANDOM):
        if math.sqrt(min(s.cost for s in found) / len(target)) < FLOOR:
            break
        tick()
        kinds, vals = (wild_fill(rng, five) if rng.random() < WILD else
                       random_fill(rng, model, cands, five, target, free))
        st = State(model, five, target, free, kinds, vals, seen)
        interim(st, found)
        st = backfit(st, cands, tick, improved=lambda st: interim(st, found))
        found.append(drop_passes(st, cands, tick))
        report(min(found, key=lambda s: s.cost))
    if done[0] < len(plans) + RANDOM:                           # stopped early: on past the starts not needed
        done[0] = len(plans) + RANDOM - 1
        report(min(found, key=lambda s: s.cost))
    found.sort(key=lambda s: s.cost)

    # With tone, the best few go on with Bass and Treble at 0 dB: never worse than without. The given starts go on
    # in any case.
    ext = [] if tone else found[:EXTEND]
    bases = [(b.kinds + [s.kinds[0] for s in sl[5:]], b.vals + [(s.rest[0], 0.0, s.rest[1]) for s in sl[5:]])
             for b in found[:EXTEND]] if tone else []
    for kinds, vals in bases + given:
        tick()
        st = State(model, sl, target, free, kinds, vals, seen)
        interim(st, ext)
        st = backfit(st, cands, tick, improved=lambda st: interim(st, ext))
        ext.append(drop_passes(st, cands, tick))
        report(min(ext, key=lambda s: s.cost))

    # Rounding costs each a little differently: the one best on the grid wins.
    out = result(min((to_grid(st.settings(), target, fs, free) for st in ext), key=lambda r: r.rms).settings,
                 curve, fs, free)
    for kinds, vals in given:                                   # a start as it was may still be better on the grid
        start = result([Setting(s.name, k, *v) for s, k, v in zip(sl, kinds, vals)], curve, fs, free)
        if start.rms < out.rms:
            out = start
    return out


def to_grid(settings, target, fs=FS, free_level=True):
    """Settings off the grid (a best so far that progress reported) onto it, then to neighbouring grid values one at
    a time while that helps: a Result, as fit ends (free_level as there)."""
    by_name = {s.name: s for s in slots(True)}
    rounded = [on_grid(by_name[x.name], x.kind, x.freq, x.gain, x.q) for x in settings]
    rounded = grid_search(Model(fs), [by_name[x.name] for x in settings], [x.kind for x in settings], rounded,
                          np.asarray(target, float), free_level)
    return result([Setting(x.name, x.kind, *v) for x, v in zip(settings, rounded)], target, fs, free_level)


def response(settings, fs=FS):
    """The summed response in dB at FREQS of a list of Setting."""
    model = Model(fs)
    return sum((model.db(s.kind, s.freq, s.gain, s.q) for s in settings), np.zeros(len(FREQS)))
