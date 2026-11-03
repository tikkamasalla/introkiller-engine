"""Audio alignment of shared segments (OP / ED / any recurring music) between two episodes.

numpy only.  For a target x and a reference y (mono 8 kHz windows):
  1. lag candidates : FFT cross-correlation normalised by overlap energy; top-K peaks.
  2. stretches      : at each lag a 0.1 s sliding normalised correlation (hop 0.025 s) marks the stretches
                      where the two signals are the same recording (thr 0.5, gaps <= 0.6 s bridged); every
                      stretch >= MIN_STRETCH s is returned with its overall correlation (seg_ncc).
All times are seconds from the start of the *window*; the caller adds the window offset.
"""
import numpy as np

SR = 8000
WIN = 800            # 0.1 s
HOP = 200            # 0.025 s
THR = 0.5
GAP = int(0.6 / (HOP / SR))
MIN_OVERLAP = 20 * SR
MIN_STRETCH = 4.0


BAND = (80.0, 1500.0)    # Hz.  Lossy codecs (AAC/Opus) re-synthesise the highs per file, so only the band below
                         # ~1.5 kHz is a reliable fingerprint of the same recording (a pre-emphasised full band
                         # scored 0.58 on AAC rips of one and the same OP, the band-limited signal 0.98).


def prep(x, band=BAND):
    x = np.asarray(x, dtype=np.float32)
    x = x - x.mean()
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    X *= ((f >= band[0]) & (f <= band[1])).astype(np.float32)
    y = np.fft.irfft(X, n).astype(np.float32)
    # automatic gain control: a short quiet theme must weigh as much as loud dialogue in the lag search
    c = np.concatenate([[0.0], np.cumsum(y.astype(np.float64) ** 2)])
    w = SR                                                   # 1 s
    i0 = np.clip(np.arange(n) - w // 2, 0, n)
    i1 = np.clip(np.arange(n) + w // 2, 0, n)
    env = np.sqrt((c[i1] - c[i0]) / np.maximum(i1 - i0, 1))
    env = env + 0.2 * float(np.median(env) + 1e-9)
    return (y / env).astype(np.float32)


class Spec:
    """Pre-computed FFT of one prepped window so that it can be reused against many partners."""

    def __init__(self, x, nfft):
        self.x = x
        self.nfft = nfft
        self.F = np.fft.rfft(x, nfft)
        self.c2 = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])


def top_lags(a, b, k=3, min_sep=2.0, min_overlap=MIN_OVERLAP):
    """Lag candidates (samples) k with x[m] ~ y[m-k]; returns [(lag, ncc, noise_level)] best first."""
    nx, ny = len(a.x), len(b.x)
    nfft = a.nfft
    c = np.fft.irfft(a.F * np.conj(b.F), nfft)
    ks = np.arange(-(ny - min_overlap), nx - min_overlap + 1)
    lo = np.maximum(0, ks)
    hi = np.minimum(nx, ny + ks)
    ex = a.c2[hi] - a.c2[lo]
    ey = b.c2[hi - ks] - b.c2[lo - ks]
    cc = c[np.where(ks >= 0, ks, nfft + ks)]
    ncc = (cc / np.sqrt(ex * ey + 1e-9)).astype(np.float64)
    noise = float(np.median(np.abs(ncc)))
    work = ncc.copy()
    out = []
    sep = int(min_sep * SR)
    for _ in range(k):
        i = int(np.argmax(work))
        v = float(work[i])
        if v < max(0.012, 8.0 * noise):
            break
        out.append((int(ks[i]), v, noise))
        work[max(0, i - sep):i + sep + 1] = -1.0
    return out


def stretches(x, y, k, min_len=MIN_STRETCH):
    """All matching stretches of x against y shifted by lag k (times relative to window start)."""
    nx, ny = len(x), len(y)
    lo, hi = max(0, k), min(nx, ny + k)
    if hi - lo < 2 * WIN:
        return []
    xs, ys = x[lo:hi].astype(np.float64), y[lo - k:hi - k].astype(np.float64)
    P = np.concatenate([[0.0], np.cumsum(xs * ys)])
    Ex = np.concatenate([[0.0], np.cumsum(xs * xs)])
    Ey = np.concatenate([[0.0], np.cumsum(ys * ys)])
    n = len(xs)
    w0 = np.arange(0, n - WIN, HOP)
    p = P[w0 + WIN] - P[w0]
    ex = Ex[w0 + WIN] - Ex[w0]
    ey = Ey[w0 + WIN] - Ey[w0]
    ncc = p / np.sqrt(ex * ey + 1e-12)
    floor = 1e-4 * float(np.median(ex[ex > 0])) if (ex > 0).any() else 0.0
    live = (ex > floor) & (ey > floor)
    ncc = np.where(live, ncc, -1.0)
    match = ncc >= THR
    centers = (lo + w0 + WIN / 2.0) / SR
    m = len(match)
    runs = []
    i = 0
    while i < m:
        if not match[i]:
            i += 1
            continue
        j, last, cnt = i, i, 0
        while j < m and j - last <= GAP:
            if match[j]:
                last = j
                cnt += 1
            j += 1
        runs.append((i, last, cnt))
        i = last + 1
    res = []
    for a, b, cnt in runs:
        if a == 0:
            s, s_clip = centers[0], True
        else:
            n0, n1 = ncc[a - 1], ncc[a]
            f = (THR - n0) / (n1 - n0) if n1 != n0 else 0.0
            s, s_clip = centers[a - 1] + f * (centers[a] - centers[a - 1]), False
        if b == m - 1:
            e, e_clip = centers[-1], True
        else:
            n0, n1 = ncc[b], ncc[b + 1]
            f = (n0 - THR) / (n0 - n1) if n0 != n1 else 0.0
            e, e_clip = centers[b] + f * (centers[b + 1] - centers[b]), False
        if e - s < min_len:
            continue
        i0 = max(int(round(s * SR)) - lo, 0)
        i1 = min(int(round(e * SR)) - lo, n)
        seg = float((P[i1] - P[i0]) / np.sqrt((Ex[i1] - Ex[i0]) * (Ey[i1] - Ey[i0]) + 1e-12))
        # fraction of 0.1 s windows inside that are live (carry energy) and matched
        ia, ib = a, b + 1
        live_frac = float(np.mean(live[ia:ib])) if ib > ia else 0.0
        res.append({"start": float(s), "end": float(e), "len": float(e - s), "ncc": seg,
                    "clip_start": bool(s_clip), "clip_end": bool(e_clip), "live": live_frac,
                    "windows": int(cnt)})
    return res
