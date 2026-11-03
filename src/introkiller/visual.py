"""Visual-only discovery of a shared title sequence (fallback when the audio alignment finds nothing).

Used for shows whose theme music is not the same recording in every episode (re-recorded / re-mixed / sub-gate
correlation) but whose title PICTURES are identical.  For a target episode and one reference the first `window` seconds of
both are hashed (63-bit pHash, every `stride`-th frame); a stretch of the target that matches the reference at ONE constant
time offset is a candidate.  A candidate is kept only if
  * it is >= `min_len` s long, bridged over gaps <= `gap` s, and >= `fill` of its frames are matched non-black pairs
  * the matched frame pairs are pixel-identical in the 64x36 gray domain (median mean-abs-diff <= `mad_med`, 90th pct <= `mad_p90`):
    the same room/set with different actors never passes this, only the same footage does
The caller (pipeline.Season) still requires >= 2 independent references to agree on start and end (same cluster rule as
the audio candidates) and then runs the normal edge refinement and gates.
"""
import numpy as np

from . import edges


def prep_frames(ts, fr, stride):
    idx = np.arange(0, len(ts), stride)
    f = fr[idx]
    h = edges.hashes(f)
    blk = edges.is_black(f)
    sgn = np.where(h, 1.0, -1.0).astype(np.float32)
    return {"ts": ts[idx], "fr": f, "sgn": sgn, "blk": blk}


def runs_against(A, B, cfg):
    """Matched runs of A (target) against B (reference).  Returns [{start,end,off,frac,mad_med,mad_p90}] in seconds."""
    nb = A["sgn"].shape[1]
    D = 0.5 * (nb - A["sgn"] @ B["sgn"].T)                  # hamming distance matrix
    M = (D <= edges.HT) & (~A["blk"])[:, None] & (~B["blk"])[None, :]
    nA, nB = M.shape
    dt = float(np.median(np.diff(A["ts"]))) if nA > 1 else 1 / 24.0
    gap = int(round(cfg["vis_gap"] / dt))
    minlen = cfg["vis_min_len"]
    out = []
    for k in range(-(nA - 1), nB):                          # diagonal: A index a <-> B index a + k
        d = np.diagonal(M, k)
        if d.sum() < minlen / dt * cfg["vis_fill"]:
            continue
        idx = np.flatnonzero(d)
        cut = np.flatnonzero(np.diff(idx) > gap + 1)
        starts = np.concatenate([[0], cut + 1])
        ends = np.concatenate([cut, [len(idx) - 1]])
        a0 = max(0, -k)
        for s, e in zip(starts, ends):
            ia, ib = idx[s] + a0, idx[e] + a0
            span = (ib - ia + 1) * dt
            cnt = e - s + 1
            if span < minlen or cnt * dt / span < cfg["vis_fill"]:
                continue
            pa = idx[s:e + 1] + a0
            pb = pa + k
            mad = np.abs(A["fr"][pa].astype(np.int16) - B["fr"][pb].astype(np.int16)).reshape(len(pa), -1).mean(axis=1)
            med, p90 = float(np.median(mad)), float(np.percentile(mad, 90))
            if med > cfg["vis_mad_med"] or p90 > cfg["vis_mad_p90"]:
                continue
            off = float(np.median(A["ts"][pa] - B["ts"][pb]))
            out.append({"start": float(A["ts"][ia]), "end": float(A["ts"][ib] + dt), "off": off, "frac": cnt * dt / span,
                        "mad_med": med, "mad_p90": p90})
    return out
