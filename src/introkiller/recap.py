"""Audio landmark fingerprints for the recap replay lane (spectral peak pairs).

The head region of a target episode is matched against the full audio of
earlier episodes. recap_lanes.lane6_full_replay applies the run, place and
trim gates on top of Index.votes. numpy + cv2 only.
"""
import numpy as np
import cv2

SR = 8000
NFFT = 1024
HOP = 256              # 32 ms
F0, F1 = 5, 190        # bins 39-1480 Hz
BUCKET = 64            # frames = 2.05 s
MIN_VOTES = 7


def _spec(x):
    x = np.asarray(x, np.float32)
    n = (len(x) - NFFT) // HOP + 1
    if n <= 0:
        return np.zeros((0, F1 - F0), np.float32)
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    fr = x[idx] * np.hanning(NFFT).astype(np.float32)
    S = np.abs(np.fft.rfft(fr, axis=1))[:, F0:F1]
    return np.log1p(S).astype(np.float32)


def landmarks(x, per_frame=3):
    S = _spec(x)
    if len(S) == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    m = cv2.dilate(S, np.ones((9, 15), np.uint8))          # rows = time, cols = freq
    thr = S.mean(axis=1, keepdims=True) + 1.2 * S.std(axis=1, keepdims=True)
    pk = (S == m) & (S > thr)
    t, f = np.nonzero(pk)
    # keep the strongest `per_frame` peaks per frame
    keep = np.zeros(len(t), bool)
    order = np.lexsort((-S[t, f], t))
    t, f = t[order], f[order]
    first = np.r_[0, np.nonzero(np.diff(t))[0] + 1]
    rank = np.arange(len(t)) - np.repeat(first, np.diff(np.r_[first, len(t)]))
    sel = rank < per_frame
    t, f = t[sel], f[sel]
    o = np.argsort(t, kind="stable")
    return t[o].astype(np.int64), f[o].astype(np.int64)


def hashes(t, f, fan=5, dmin=2, dmax=60):
    hs, ts = [], []
    n = len(t)
    for k in range(1, fan + 1):
        a = np.arange(0, n - k)
        dt = t[a + k] - t[a]
        ok = (dt >= dmin) & (dt <= dmax)
        a = a[ok]
        hs.append((f[a] << 24) | (f[a + k] << 12) | dt[ok])
        ts.append(t[a])
    if not hs:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    return np.concatenate(hs), np.concatenate(ts)


class Index:
    def __init__(self, sources):
        """sources: {name: audio float32}"""
        H, T, E = [], [], []
        self.names = list(sources)
        for i, nme in enumerate(self.names):
            t, f = landmarks(sources[nme])
            h, tt = hashes(t, f)
            H.append(h); T.append(tt); E.append(np.full(len(h), i, np.int32))
        H, T, E = np.concatenate(H), np.concatenate(T), np.concatenate(E)
        o = np.argsort(H, kind="stable")
        self.H, self.T, self.E = H[o], T[o], E[o]

    def votes(self, x):
        """per-bucket best vote: list of dict(bucket, ep, count, t_first, t_last, n_eps_strong)"""
        t, f = landmarks(x)
        h, tq = hashes(t, f)
        lo = np.searchsorted(self.H, h, "left")
        hi = np.searchsorted(self.H, h, "right")
        cnt = hi - lo
        ok = (cnt > 0) & (cnt <= 40)
        qi = np.repeat(np.nonzero(ok)[0], cnt[ok])
        pos = np.concatenate([np.arange(a, b) for a, b in zip(lo[ok], hi[ok])]) if ok.any() else np.zeros(0, int)
        if len(pos) == 0:
            return []
        off = self.T[pos] - tq[qi]
        ep = self.E[pos]
        tqq = tq[qi]
        out = []
        buck = tqq // BUCKET
        for sh in (0, 1):                                  # double-count into two offset bins: tolerance of 1 frame
            pass
        key = ((off + (1 << 22)) >> 1).astype(np.int64)
        comb = buck.astype(np.int64) * (1 << 40) + ep.astype(np.int64) * (1 << 30) + key
        u, inv, c = np.unique(comb, return_inverse=True, return_counts=True)
        # merge neighbouring offset bins
        bk = u >> 40
        ee = (u >> 30) & 1023
        kk = u & ((1 << 30) - 1)
        d = {}
        for a, b, e, k, n in zip(range(len(u)), bk, ee, kk, c):
            d[(int(b), int(e), int(k))] = int(n)
        best = {}
        for (b, e, k), n in d.items():
            tot = n + d.get((b, e, k - 1), 0) + d.get((b, e, k + 1), 0)
            cur = best.setdefault(b, {})
            if tot > cur.get(e, (0, 0))[0]:
                cur[e] = (tot, k)
        for b, per_ep in sorted(best.items()):
            strong = [(v[0], e) for e, v in per_ep.items() if v[0] >= MIN_VOTES]
            if not strong:
                continue
            tot, e = max(strong)
            sel = (buck == b) & (ep == e) & (np.abs(key - per_ep[e][1]) <= 1)
            off_s = float((per_ep[e][1] * 2 - (1 << 22)) * HOP / SR)      # source time - target time
            out.append({"bucket": b, "ep": self.names[e], "count": tot, "off_s": off_s, "t_first": float(tqq[sel].min() * HOP / SR) if sel.any() else b * BUCKET * HOP / SR,
                        "t_last": float(tqq[sel].max() * HOP / SR) if sel.any() else (b + 1) * BUCKET * HOP / SR,
                        "n_strong": len(strong)})
        return out
