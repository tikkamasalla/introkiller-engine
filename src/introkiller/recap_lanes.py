"""Recap detection for --recap: card lane plus full-replay lane.

Lane 5 finds a PREVIOUSLY card in the first 3 minutes. Lane 6 matches head
audio against whole earlier episodes. Combined uses audio first, card as
fallback. Measured on 43 recaps: 13 found, 0 false, 0.0 s worst overrun.
"""
import re
import subprocess

import numpy as np

from . import edges, media, recap

SR = media.SR
RECAP_MIN = 8.0
CARD_WIN = 180.0
CARD_LEAD = 30.0
CARD_MAX_SPAN = 240.0
CARD_RE = re.compile(r"previous", re.I)
REPLAY_REGION = 180.0
MIN_PLACES = 3
PLACE_GAP = 25.0
RUN_LINK_GAP = 7
TRIM_SPAN = 15.0
RUN_MIN = 8.0
RUN_FRAC = 0.5

def _audio(src, a, b):
    parts, t = [], a
    while t < b - 1e-6:
        e = min(b, t + 300.0)
        parts.append(src.audio(t, e))
        t = e
    return np.concatenate(parts) if parts else np.zeros(0, np.float32)

class _CardOCR:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self._eng = RapidOCR(det_model_path=None, det_limit_side_len=640, det_limit_type="max")
    def read(self, gray):
        res, _el = self._eng(gray)
        boxes, texts = [], []
        for item in res or []:
            poly = item[0]
            xs = [int(round(p[0])) for p in poly]
            ys = [int(round(p[1])) for p in poly]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
            texts.append(item[1])
        return tuple(boxes), texts

def _card_frames_1fps(path, t_max):
    vf = "scale=640:360:flags=neighbor,format=gray,fps=1,showinfo"
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-copyts", "-ss", "0", "-i", path,
           "-to", "%.3f" % t_max, "-an", "-sn", "-vf", vf, "-fps_mode", "passthrough",
           "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=media.NOWIN, timeout=900)
    raw = np.frombuffer(p.stdout, np.uint8)
    n = len(raw) // (640 * 360)
    if n == 0:
        return np.zeros(0), np.zeros((0, 360, 640), np.uint8)
    fr = raw[:n * 640 * 360].reshape(n, 360, 640)
    ts = np.array([float(m) for m in re.findall(r"pts_time:\s*(-?[\d.]+)", p.stderr.decode(errors="replace"))][:n])
    fr = fr[:len(ts)]
    keep = (ts >= -1e-6) & (ts <= t_max + 1e-6)
    ts, fr = ts[keep], fr[keep]
    order = np.argsort(ts, kind="stable")
    return ts[order], fr[order]

def _card_start(hits):
    secs = {}
    for t, txt in hits:
        secs.setdefault(int(t), txt)
    order = sorted(secs)
    if not order:
        return None
    return float(order[0]), secs[order[0]]

def lane5_text_card(target, intro_start=None, t_max=CARD_WIN, detector=None):
    t_max = min(float(t_max), float(target.duration))
    if t_max < RECAP_MIN:
        return None
    try:
        det = detector or _CardOCR()
        ts, fr = _card_frames_1fps(target.path(), t_max)
    except Exception:
        return None
    hits = []
    for i in range(len(ts)):
        try:
            boxes, texts = det.read(fr[i])
        except Exception:
            continue
        if not boxes or len(boxes) > 8:
            continue
        txt = " ".join(texts)
        if CARD_RE.search(txt):
            hits.append((float(ts[i]), txt[:80]))
    c = _card_start(hits)
    if c is None:
        return None
    card_t0, card_txt = c
    if card_t0 > CARD_LEAD:
        return None
    start = 0.0 if card_t0 <= 10.0 else round(card_t0 - 2.0, 3)
    end = _card_end(target, start, intro_start, t_max)
    if end is None:
        return None
    return {"start": round(float(start), 3), "end": round(float(end), 3),
            "card_at": round(float(card_t0), 3), "card_text": card_txt, "lane": "card"}

def _card_end(target, start, intro_start, t_max=CARD_WIN):
    if intro_start is None or float(intro_start) > t_max:
        return None
    end0 = float(intro_start)
    if end0 - start < RECAP_MIN or end0 - start > CARD_MAX_SPAN:
        return None
    try:
        cts, cfr = target.grab(max(0.0, end0 - 5.0), min(float(target.duration), end0 + 0.5))
        scores = edges.cut_scores(cfr)
        best = None
        for i in range(1, len(cts)):
            if cts[i] <= end0 + 1e-6 and scores[i] >= edges.CUT_DIFF:
                best = float(cts[i])
        end = best if best is not None else end0
    except Exception:
        end = end0
    if end - start < RECAP_MIN:
        return None
    return float(end)

def _trim_shared_ends(gd, tol=2.0, min_span=TRIM_SPAN):
    gd = list(gd)
    for _ in range(2):
        if len(gd) < 2:
            break
        for side in ("lead", "trail"):
            seq = gd if side == "lead" else gd[::-1]
            o0 = seq[0]["off_s"]
            j = 0
            while j + 1 < len(seq) and abs(seq[j + 1]["off_s"] - o0) <= tol:
                j += 1
            span = abs(seq[j]["t_first"] - seq[0]["t_first"])
            if span >= min_span:
                gd = gd[j + 1:] if side == "lead" else gd[:len(gd) - j - 1]
                break
    return gd

def _source_places(gd, gap=PLACE_GAP):
    sts = sorted(d["t_first"] + d["off_s"] for d in gd)
    n = 1
    for a, b in zip(sts, sts[1:]):
        if b - a >= gap:
            n += 1
    return n

def _best_run(gd, ep, region, link_gap, lane):
    runs, cur = [], []
    for d in gd:
        if cur and d["bucket"] - cur[-1]["bucket"] > link_gap + 1:
            runs.append(cur)
            cur = []
        cur.append(d)
    if cur:
        runs.append(cur)
    best = None
    for r in runs:
        r = _trim_shared_ends(r)
        while len(r) >= 2 and r[-1]["bucket"] - r[-2]["bucket"] > 1:
            r = r[:-1]
        if len(r) < MIN_PLACES:
            continue
        s, e = r[0]["t_first"], r[-1]["t_last"]
        frac = len(r) / (r[-1]["bucket"] - r[0]["bucket"] + 1)
        if (e - s < RUN_MIN or frac < RUN_FRAC or s > 150.0 or e > region + 1e-6
                or _source_places(r) < MIN_PLACES):
            continue
        if best is None or (e - s) > (best["end"] - best["start"]):
            best = {"start": round(float(s), 3), "end": round(float(e), 3),
                    "sources": [ep], "places": _source_places(r),
                    "matched_frac": round(float(frac), 3), "lane": lane}
    return best

def lane6_full_replay(target, earlier_srcs, intro_start=None, region=REPLAY_REGION):
    if not earlier_srcs:
        return None
    region = min(float(region), float(intro_start)) if intro_start else min(float(region), float(target.duration))
    if region < RECAP_MIN:
        return None
    full = {}
    for s in earlier_srcs:
        try:
            full[s.name] = _audio(s, 0.0, s.duration)
        except Exception:
            continue
    if not full:
        return None
    try:
        head = _audio(target, 0.0, min(region, float(target.duration)))
    except Exception:
        return None
    idx = recap.Index(full)
    v = idx.votes(head)
    good = [d for d in v if d["n_strong"] == 1 and d["off_s"] >= 20.0 and d["t_first"] <= region]
    if len(good) < MIN_PLACES:
        return None
    by_ep = {}
    for d in good:
        by_ep.setdefault(d["ep"], []).append(d)
    ep = max(by_ep, key=lambda e: len(by_ep[e]))
    gd = sorted(by_ep[ep], key=lambda d: d["bucket"])
    if len(gd) < MIN_PLACES:
        return None
    return _best_run(gd, ep, region, RUN_LINK_GAP, "full-replay")

def combined_recap(target, earlier_srcs, intro_start=None, detector=None):
    audio = None
    try:
        audio = lane6_full_replay(target, earlier_srcs, intro_start)
    except Exception:
        audio = None
    card = None
    try:
        card = lane5_text_card(target, intro_start, CARD_WIN, detector)
    except Exception:
        card = None
    if audio is not None and card is not None:
        out = dict(audio)
        out["lanes"] = ["full-replay", "card"]
        return out
    if audio is not None:
        out = dict(audio)
        out["lanes"] = ["full-replay"]
        return out
    if card is not None:
        out = dict(card)
        out["lanes"] = ["card"]
        return out
    return None
