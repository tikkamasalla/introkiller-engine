"""Preview stage.

A next-episode preview does not repeat across episodes, but its STRUCTURE does: same length, ends at EOF, directly after the
credits, usually with a shared card or jingle.  A segment [p0, EOF] is published as type "preview" (a button, never an auto-skip)
only when ALL of these hold; everything refused is listed in `rejected` (kind "preview").

  anchor   the credits end where a visual transition confirmed it (a post-credit cut included: there the audio is shared past the
           credits); otherwise the end of the credits' shared audio if that is later.
  length   L = duration - anchor.  Episodes are grouped by L (chain of gaps <= preview_tol, whole group <= preview_spread).
           A target needs >= preview_min_peers other episodes within preview_tol, and L inside preview_len.
           Story after the credits differs in length per episode, so it never forms a group (Humanity Part C: 91 s vs 32 s).
  start    p0 = duration - (shortest L of the group): the latest start the season supports, so credits never leak in.
  shared   a card (same picture) or a jingle (same audio) in the first or last preview_win seconds, against >= preview_min_peers
           of those episodes.  Black frames and silence are not evidence.
"""
import numpy as np

from . import align, edges
from .media import SR


def _anchor(seg):
    g = seg["gates"]
    if g.get("edge_end") in ("post_cut", "cut", "black_start", "black_trim", "inward_cut"):
        return seg["end"]                                      # the picture says where the credits end
    return max(seg["end"], g.get("audio_end") or seg["end"])   # unverified end: the shared audio is the latest they can reach


def groups(rows, tol, spread):
    """rows: [(L, ep)].  Chains of neighbours <= tol apart; a chain wider than `spread` is ambiguous and dropped."""
    rows = sorted(rows, key=lambda r: r[0])
    out, cur = [], []
    for r in rows:
        if cur and r[0] - cur[-1][0] > tol:
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return [g for g in out if g[-1][0] - g[0][0] <= spread]


class Tail:
    """The two small windows of one episode that the evidence looks at, read once: around the preview start and before EOF.
    Frames stay in the Source's window cache; audio is sliced from here."""

    def __init__(self, e, Lmin, cfg):
        w = cfg["preview_win"]
        self.e = e
        p0 = e.E - Lmin
        e.src.grab(p0 - 1.5, p0 + 2 * w + 1.5)
        e.src.grab(e.E - w - 2.0, e.E + 1.0)
        self.win = [(p0 - 2.5, p0 + 2 * w + 2.5), (e.E - w - 2.5, e.E)]
        self.aud = [e.src.audio(a, b) for a, b in self.win]

    def audio(self, a, b):
        for (w0, w1), x in zip(self.win, self.aud):   # a window that fully contains [a, b] wins over a partial overlap
            if a >= w0 - 0.01 and b <= w1 + 0.01:
                i0, i1 = int(round((max(a, w0) - w0) * SR)), int(round((min(b, w1) - w0) * SR))
                return x[i0:i1]
        for (w0, w1), x in zip(self.win, self.aud):
            if a >= w0 - 0.01 and a < w1 and b > w0:
                i0, i1 = int(round((max(a, w0) - w0) * SR)), int(round((min(b, w1) - w0) * SR))
                return x[i0:i1]
        return np.zeros(0, np.float32)


def card(e, r, t0, t1, off):
    """(non-black share, matched share of the non-black frames) of target [t0, t1] against reference r at offset off."""
    ts, fr = e.src.grab(t0, t1)
    if len(ts) < 4:
        return 0.0, 0.0
    nb = ~edges.is_black(fr)
    if not nb.any():
        return 0.0, 0.0
    rt, rf = r.src.grab(t0 - off, t1 - off)   # black is not evidence on the reference side either (uniform hashes are all-zero)
    if len(rt) < 4 or float((~edges.is_black(rf)).mean()) < 0.5:
        return 0.0, 0.0
    d = edges._ref_match(ts, edges.hashes(fr), r.src, off, t0, t1)
    return float(nb.mean()), float(np.mean(d[nb] <= edges.HT))


def jingle(tail_e, tail_r, t0, t1, off, search=1.0):
    """Best correlation of target audio [t0, t1] against the reference around offset off (+- search s)."""
    x = tail_e.audio(t0, t1)
    y = tail_r.audio(t0 - off - search, t1 - off + search)
    if len(x) < SR or len(y) < len(x):
        return 0.0
    # silence is not evidence: after prep()'s AGC a short shared click inside silence correlates on its own
    if float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) < 1e-3:
        return 0.0
    nb = len(x) // (SR // 4)
    if nb and float(np.mean(np.sqrt(np.mean(x[:nb * (SR // 4)].reshape(nb, SR // 4).astype(np.float64) ** 2, axis=1)) > 1e-3)) < 0.5:
        return 0.0
    x, y = align.prep(x).astype(np.float64), align.prep(y).astype(np.float64)
    n = len(x) + len(y)
    c = np.fft.irfft(np.fft.rfft(y, n) * np.conj(np.fft.rfft(x, n)), n)[:len(y) - len(x) + 1]
    e2 = np.concatenate([[0.0], np.cumsum(y * y)])
    ey = e2[len(x):] - e2[:-len(x)]
    ex = float(np.sum(x * x))
    if ex <= 1e-9:
        return 0.0
    return float(np.max(c / np.sqrt(ex * np.maximum(ey, 1e-9))))


def evidence(te, tr, p0, cfg):
    """What e shares with r inside the preview.  Both windows are aligned on EOF: the previews have the same length."""
    e, r = te.e, tr.e
    w = cfg["preview_win"]
    off = e.E - r.E
    t_end = e.E - 0.2
    search = cfg["preview_tol"] + 0.5                         # two previews agree in length only within preview_tol, so EOF alignment can be that far off
    out = {"card_start": card(e, r, p0, p0 + w, off), "card_end": card(e, r, t_end - w, t_end, off),
           "jingle_start": jingle(te, tr, p0, p0 + w, off, search), "jingle_end": jingle(te, tr, t_end - w, t_end, off, search)}
    is_card = lambda v: v[0] >= cfg["preview_card_nonblack"] and v[1] >= cfg["preview_card_frac"]
    out["card"] = bool(is_card(out["card_start"]) or is_card(out["card_end"]))
    out["jingle"] = bool(max(out["jingle_start"], out["jingle_end"]) >= cfg["preview_jingle_ncc"])
    out["shared"] = out["card"] or out["jingle"]
    return out


def _rounded(v):
    if isinstance(v, (tuple, list)):
        return [_rounded(x) for x in v]
    return round(v, 3) if isinstance(v, float) else v


def derive(season):
    """Append preview segments to the episodes of a finished Season (needs e.segments with their gates)."""
    cfg = season.cfg
    lo, hi = cfg["preview_len"]
    rows = []
    for e in season.eps:
        c = [s for s in e.segments if s["type"] == "credits"]
        if c:
            rows.append((e.E - _anchor(c[-1]), e))
    for g in groups(rows, cfg["preview_tol"], cfg["preview_spread"]):
        Lmin = g[0][0]
        inside = [(L, e) for L, e in g if lo <= L <= hi]      # outside the range: credits run to EOF, or too much follows them
        for L, e in inside:
            peers = [x for M, x in g if x is not e and abs(M - L) <= cfg["preview_tol"]]
            if len(peers) < cfg["preview_min_peers"] or Lmin < lo:
                e.rejected.append({"kind": "preview", "start": round(e.E - L, 3), "end": round(e.E, 3),
                                   "reason": "length %.1f s: %d other episode(s) agree, shortest in the group %.1f s" % (L, len(peers), Lmin)})
        todo = [(L, e) for L, e in inside if Lmin >= lo and sum(1 for M, x in g if x is not e and abs(M - L) <= cfg["preview_tol"]) >= cfg["preview_min_peers"]]
        if not todo:
            continue
        tails = {}
        for L, e in g:
            tails[e.idx] = Tail(e, Lmin, cfg)
        for L, e in todo:
            peers = [x for M, x in g if x is not e and abs(M - L) <= cfg["preview_tol"]]
            p0 = e.E - Lmin
            ts, fr = e.src.grab(p0, p0 + cfg["preview_win"])  # a black run at the join belongs to the transition
            if len(ts):
                nb = ~edges.is_black(fr)
                if nb.any() and not nb[0]:
                    p0 = float(ts[int(np.argmax(nb))])
            ev = {r.name: evidence(tails[e.idx], tails[r.idx], p0, cfg) for r in peers}
            sh = [n for n, v in ev.items() if v["shared"]]
            detail = {n: {k: _rounded(x) for k, x in v.items()} for n, v in ev.items()}
            if len(sh) < cfg["preview_min_peers"]:
                e.rejected.append({"kind": "preview", "start": round(p0, 3), "end": round(e.E, 3), "evidence": detail,
                                   "reason": "shared card or jingle with only %d of %d episodes of the same length" % (len(sh), len(ev))})
                continue
            e.segments.append({"type": "preview", "start": round(p0, 3), "end": round(e.E, 3), "length": round(e.E - p0, 3),
                               "confidence": 0.75 if len(sh) >= 3 else 0.65, "method": "credits-end+season-length+shared-card-or-jingle",
                               "action": "button", "refs": sh,
                               "gates": {"length_from_anchor": round(L, 3), "season_length": round(Lmin, 3),
                                         "length_peers": [x.name for x in peers], "shared_with": sh, "evidence": detail}})
    for e in season.eps:
        e.segments.sort(key=lambda s: s["start"])
