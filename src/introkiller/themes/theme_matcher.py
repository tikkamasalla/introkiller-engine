"""Windowed theme matcher: theme core vs cached episode head/tail at 8 kHz."""
import json
import os

import numpy as np

from . import settings as S
from ..align import Spec, prep, top_lags

WIN = int(S.WIN_S * S.SR)
HOP = int(S.HOP_S * S.SR)


def load_ep(name, kind, audio_dir):
    m = json.load(open(os.path.join(audio_dir, name + ".json"), encoding="utf-8"))
    if kind in ("OP", "intro"):
        x = np.fromfile(os.path.join(audio_dir, name + ".head.f32"), "<f4")
        off = float(m["head_off"])
        if S.MASK_TAIL_OP_S > 0:
            x = x[:max(0, len(x) - int(S.MASK_TAIL_OP_S * S.SR))]
    else:
        x = np.fromfile(os.path.join(audio_dir, name + ".tail.f32"), "<f4")
        off = float(m["tail_off"])
    return x.astype(np.float32), off


def resample(x, speed):
    if speed == 1.0:
        return x
    n = int(len(x) * speed)
    old = np.arange(len(x))
    new = np.arange(n) / speed
    return np.interp(new, old, x).astype(np.float32)


def win_nccs(thp, epp, lag):
    n = (len(thp) - WIN) // HOP + 1
    out = []
    for i in range(n):
        s = i * HOP
        e = lag + s
        if e < 0 or e + WIN > len(epp):
            continue
        w = thp[s:s + WIN].astype(np.float64)
        g = epp[e:e + WIN].astype(np.float64)
        w -= w.mean()
        g -= g.mean()
        d = float(np.dot(w, g) / np.sqrt(np.dot(w, w) * np.dot(g, g) + 1e-12))
        out.append((s / S.SR, d))
    return out


LOOSE_LAG = 0.12
LOOSE_MED = 0.25
LOOSE_HI = 1


def match_epx(epx, off, meta, core, kind, name, base, loose=False):
    """Score preloaded episode samples against a theme core. Same gates as match()."""
    epp_full = prep(epx)
    best = None
    for speed in S.SPEEDS:
        th = resample(core, speed)
        thp = prep(th)
        nfft = 1
        while nfft < len(thp) + len(epp_full):
            nfft *= 2
        lags = top_lags(Spec(thp, nfft), Spec(epp_full, nfft), k=1)
        if not lags:
            continue
        lag, ncc, _noise = lags[0]
        ep_start = lag + 0 if lag >= 0 else lag
        # lag k: th[m] ~ ep[m-k]; episode core-start sample = -k
        ep_core = -lag
        if ep_core < 0 or ep_core + len(th) > len(epp_full):
            continue
        wins = win_nccs(thp, epp_full, ep_core)
        if not wins:
            continue
        vals = sorted(v for _, v in wins)
        med = float(vals[len(vals) // 2])
        hi = sum(v > S.HI_TH for _, v in wins)
        span = (lambda xs: xs[-1][0] - xs[0][0] if xs else 0.0)(
            [p for p in wins if p[1] > S.HI_TH] or wins)
        cand = {"speed": speed, "lag": int(lag), "lag_ncc": float(ncc),
                "median": med, "hi_n": int(hi), "wins": len(wins), "span": float(span),
                "wins_list": wins, "th_len": len(th)}
        if best is None or cand["lag_ncc"] > best["lag_ncc"]:
            best = cand
    if best is None:
        return {"name": name, "kind": kind, "theme": base, "match": False}
    if loose:
        ok = (best["lag_ncc"] >= LOOSE_LAG and best["median"] >= LOOSE_MED
              and best["hi_n"] >= LOOSE_HI)
    else:
        ok = (best["wins"] >= S.MIN_WINS and best["span"] >= S.SPAN_S
              and best["median"] >= S.MED_TH and best["hi_n"] >= S.HI_N)
    lead_s = meta["lead"] / S.SR / best["speed"]
    trail_s = meta["trail"] / S.SR / best["speed"]
    core_start = off + (-best["lag"]) / S.SR
    out = {"name": name, "kind": kind, "theme": base, "match": bool(ok),
           "design_pass": bool(ok), "start_s": round(core_start - lead_s, 3),
           "end_s": round(core_start + best["th_len"] / S.SR + trail_s, 3),
           "core_start": round(core_start, 3), "median_corr": round(best["median"], 3),
           "windows_matched": best["wins"], "span": round(best["span"], 1),
           "lag_ncc": round(best["lag_ncc"], 3), "speed": best["speed"],
           "hi_n": best["hi_n"], "loose": bool(loose)}
    return out


def match(name, kind, base, audio_dir, cache_dir, loose=False):
    meta = json.load(open(os.path.join(cache_dir, base + ".json"), encoding="utf-8"))
    core = np.load(os.path.join(cache_dir, base + ".npy")).astype(np.float32)
    epx, off = load_ep(name, kind, audio_dir)
    return match_epx(epx, off, meta, core, kind, name, base, loose=loose)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep", required=True)
    ap.add_argument("--theme", required=True)
    ap.add_argument("--kind", default="OP")
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--cache-dir", required=True)
    a = ap.parse_args()
    print(json.dumps(match(a.ep, a.kind, a.theme, a.audio_dir, a.cache_dir), indent=1))


if __name__ == "__main__":
    main()
