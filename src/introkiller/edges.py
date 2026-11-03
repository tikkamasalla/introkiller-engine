"""Visual edge refinement of audio-aligned intro/outro segments (numpy + cv2 + ffmpeg).

Frame sources are media.Source objects.  Public entry point:

    refine(target, a_start, a_end, refs, lookback=6.0, ...) -> dict

  target : Src   frame source of the episode whose segment was audio-aligned
  refs   : [(Src, offset)]   candidate reference episodes (any number; the ones showing the same footage next to the
           edge are picked automatically, >= 2 needed); offset = (time in target) - (time in ref) of the same
           picture = target audio edge - ref audio edge
  a_start, a_end : audio-aligned segment, target clock, seconds

Rule (one-frame precision):
  START  walk backwards from a_start, at most `lookback` s, while the target frame is either near-black
         or visually matched (perceptual-hash Hamming distance <= HT, searched +-1 frame) in >= 2 references.
         The walk stops at the first frame that is neither (= story content, never swallowed).  Leading
         near-black frames are trimmed (start = first non-black frame, i.e. end of the black/fade run).
         The new start is accepted only if it sits on a real visual transition (hard cut, end of black,
         or start of file); otherwise start = a_start.
  END    mirror image going forward (trailing black trimmed -> end = start of the black run).
  Frame times are exact presentation timestamps from ffmpeg (-copyts + showinfo).
"""
import numpy as np
import cv2

from .media import W, H

BLACK_MEAN = 22.0      # mean luma (limited range black = 16)
BLACK_P99 = 40.0
HT = 8                 # pHash Hamming threshold (of 63 bits) for "same footage"
CUT_DIFF = 18.0        # mean abs diff of consecutive 64x36 frames that counts as a hard cut
FLASH_S = 0.25         # a black run this short with shared picture (FLASH_FRAMES non-uniform frames) on its outer side is a flash, not a transition
FLASH_FRAMES = 6


def phash(img):
    """63-bit DCT perceptual hash of a gray frame."""
    a = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    d = cv2.dct(a)[:8, :8].flatten()[1:]
    return d > np.median(d)


def hashes(frames):
    return np.array([phash(f) for f in frames])


def is_black(frames):
    m = frames.reshape(len(frames), -1)
    return (m.mean(axis=1) <= BLACK_MEAN) & (np.percentile(m, 99, axis=1) <= BLACK_P99)


def cut_scores(frames):
    d = np.abs(frames[1:].astype(np.int16) - frames[:-1].astype(np.int16)).reshape(len(frames) - 1, -1).mean(axis=1)
    return np.concatenate([[0.0], d])    # score[i] = change between frame i-1 and i


def _ref_match(ts, hs, ref, offset, t_lo, t_hi):
    """bool per target frame: matched in this reference (best of +-1 ref frames)."""
    rt, rf = ref.grab(t_lo - offset - 1.0, t_hi - offset + 1.0)
    dist = np.full(len(ts), 99)
    if len(rt) == 0:
        return dist
    rh = hashes(rf)
    want = ts - offset
    j = np.clip(np.searchsorted(rt, want), 1, len(rt) - 1)
    j = np.where(np.abs(rt[j - 1] - want) <= np.abs(rt[j] - want), j - 1, j) if len(rt) > 1 else np.zeros(len(ts), int)
    for k in (-1, 0, 1):
        idx = j + k
        okk = (idx >= 0) & (idx < len(rt))
        okk[okk] &= np.abs(rt[idx[okk]] - want[okk]) <= 0.12    # no reference frame near `want` (past the file start/end) = no match, never the clamped boundary frame
        d = np.full(len(ts), 99)
        d[okk] = (hs[okk] != rh[idx[okk]]).sum(axis=1)
        dist = np.minimum(dist, d)
    return dist


def _select_refs(ts, hs, blk, refs, a, side, lookback):
    """Keep references that show the SAME footage as the target inside the segment next to this edge
    (median pHash distance <= HT over 2 s of segment interior).  Different variants of a recurring
    card/credit shot (alternating per episode) are therefore never used as evidence.  Black target
    frames are excluded: a fade that every episode shares at the song boundary would otherwise admit
    references whose visible footage is completely different (phash of any uniform frame is all-zero)."""
    if side == "s":
        sel = (ts >= a + 0.3) & (ts <= a + 2.3) & (~blk)
    else:
        sel = (ts >= a - 2.3) & (ts <= a - 0.3) & (~blk)
    if np.sum(sel) < 4:
        return []
    keep = []
    for r, off in refs:
        d = _ref_match(ts[sel], hs[sel], r, off, ts[sel][0], ts[sel][-1]) if sel.any() else np.array([99])
        if np.median(d) <= HT:
            keep.append((r, off))
    return keep


def _edge(target, a, refs, side, lookback, ht, min_refs=2):
    """Returns (new_time, kind, info)."""
    if side == "s":
        lo, hi = max(0.0, a - lookback - 0.5), a + 2.4
    else:
        lo, hi = a - 2.4, a + lookback + 0.5
    ts, fr = target.grab(lo, hi)
    for r, off in refs:                                   # one decode per reference; sub-windows are then free
        r.grab(lo - off - 1.0, hi - off + 1.0)
    hs = hashes(fr)
    blk = is_black(fr)
    cuts = cut_scores(fr)
    sel = _select_refs(ts, hs, blk, refs, a, side, lookback)
    info = {"refs_used": [getattr(r, "name", "?") for r, _ in sel]}
    if len(sel) < min_refs:
        return a, "none(<%d similar refs)" % min_refs, info
    dists = [_ref_match(ts, hs, r, off, lo, hi) for r, off in sel]
    shared = np.sum([d <= ht for d in dists], axis=0) >= min_refs
    shared_picture = lambda p, q: p >= 0 and q <= len(ts) and bool((shared[p:q] & ~blk[p:q] & hs[p:q].any(axis=1)).all())
    i0 = int(np.argmin(np.abs(ts - a)))
    # The outward walk runs in two phases -- shared non-black frames, then one contiguous black run -- and
    # never steps onto non-black frames beyond that black run: black is a separator, and a dark fade frame
    # on the story side hash-matches the references' fade frames, which must not pull the edge into story.
    if side == "s":
        i_in = i0
        while blk[i_in] and i_in + 1 < len(ts) and ts[i_in + 1] <= a + 2.3:
            i_in += 1
        if blk[i_in] or not shared[i_in]:   # edge on black is verified only by the first non-black frame inside
            return a, "none(edge frame not shared)", info
        j = i_in
        while j - 1 >= 0 and shared[j - 1] and not blk[j - 1] and ts[j - 1] >= a - lookback - 1e-6:
            j -= 1
        if j - 1 >= 0 and shared[j - 1] and not blk[j - 1]:
            return a, "none(lookback exhausted)", info
        b = j
        while b - 1 >= 0 and blk[b - 1] and ts[b - 1] >= a - lookback - 1e-6:
            b -= 1
        if b - 1 >= 0 and blk[b - 1]:
            return a, "none(lookback exhausted)", info
        if b < j and ts[j] - ts[b] <= FLASH_S and shared_picture(b - FLASH_FRAMES, b):   # a flash inside shared picture is no transition
            return a, "none(lookback exhausted)", info
        if b < j or i_in > i0:               # segment starts where the black / fade-from-black run ends
            return float(ts[j]), ("black_end" if b > 0 or ts[0] > 0.05 else "black_end(file_start)"), info
        if j == 0 and ts[0] <= 0.05:
            return float(ts[0]), "file_start", info
        if j == i0 and cuts[j] < CUT_DIFF:
            return a, "none(no transition)", info
        if cuts[j] >= CUT_DIFF:
            return float(ts[j]), "cut", info
        return a, "none(soft transition)", info
    else:
        i_in = i0
        while blk[i_in] and i_in - 1 >= 0 and ts[i_in - 1] >= a - 2.3:
            i_in -= 1
        if blk[i_in] or not shared[i_in]:
            return a, "none(edge frame not shared)", info
        j = i_in
        while j + 1 < len(ts) and shared[j + 1] and not blk[j + 1] and ts[j + 1] <= a + lookback + 1e-6:
            j += 1
        if j + 1 < len(ts) and shared[j + 1] and not blk[j + 1]:
            return a, "none(lookback exhausted)", info
        b = j
        while b + 1 < len(ts) and blk[b + 1] and ts[b + 1] <= a + lookback + 1e-6:
            b += 1
        if b + 1 < len(ts) and blk[b + 1]:
            return a, "none(lookback exhausted)", info
        if b > j and ts[b] - ts[j] <= FLASH_S and shared_picture(b + 1, b + 1 + FLASH_FRAMES):
            return a, "none(lookback exhausted)", info
        nxt = lambda k: float(ts[k + 1]) if k + 1 < len(ts) else float(ts[k] + 1 / 24.0)
        if b > j or i_in < i0:               # trailing black: segment ends where black starts
            return nxt(j), "black_start", info
        if j + 1 < len(ts) and cuts[j + 1] >= CUT_DIFF:
            return nxt(j), "cut", info
        if j == i0:
            return a, "none(no transition)", info
        return a, "none(soft transition)", info


def refine(target, a_start, a_end, refs_s, refs_e=None, lookback=6.0, ht=HT, min_refs=2):
    """refs_s / refs_e: [(Src, offset)] for the start / end edge (offset = target audio edge - ref audio edge).
    min_refs: references that must show a frame for it to count as shared (1 only for the end-anchored single-reference rule)."""
    s, sk, si = _edge(target, a_start, refs_s, "s", lookback, ht, min_refs)
    e, ek, ei = _edge(target, a_end, refs_e if refs_e is not None else refs_s, "e", lookback, ht, min_refs)
    return {"a_start": a_start, "a_end": a_end, "start": s, "start_kind": sk, "start_info": si,
            "end": e, "end_kind": ek, "end_info": ei, "start_ext": a_start - s, "end_ext": e - a_end}


RING = np.ones((H, W), bool)
RING[5:-5, 8:-8] = False


def ring_match(ts, fr, ref, offset, t_lo, t_hi):
    """Per target frame: mean abs gray difference of the OUTER RING (5 px / 8 px at 64x36) against the reference frame at the
    same time (best of +-1 frames), and the std of the target's ring.  Finds an overlay frame/border that every episode shares
    while the picture inside differs (episode-specific clips played inside a shared decorative frame)."""
    rt, rf = ref.grab(t_lo - offset - 1.0, t_hi - offset + 1.0)
    mad = np.full(len(ts), 99.0)
    std = fr[:, RING].astype(np.float32).std(axis=1)
    if len(rt) < 2:
        return mad, std
    want = ts - offset
    j = np.clip(np.searchsorted(rt, want), 1, len(rt) - 1)
    j = np.where(np.abs(rt[j - 1] - want) <= np.abs(rt[j] - want), j - 1, j)
    a = fr[:, RING].astype(np.int16)
    for k in (-1, 0, 1):
        idx = np.clip(j + k, 0, len(rt) - 1)
        near = np.abs(rt[idx] - want) <= 0.12
        d = np.abs(a - rf[idx][:, RING].astype(np.int16)).mean(axis=1)
        mad = np.minimum(mad, np.where(near, d, 99.0))
    return mad, std
