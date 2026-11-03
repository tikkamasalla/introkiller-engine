"""Backup stage: official anime opening and ending themes.

A theme result is used only for a segment type the main pipeline did not find
in that episode. It never overrides or extends a main result. Every theme
result is trimmed 2 s inward at each end.
"""
import json
import os
import time

import numpy as np

from . import media
from .themes import settings as S
from .themes import theme_cache, theme_matcher, theme_resolver

TRIM_S = 2.0
HEAD_S = 360.0
TAIL_S = 300.0


def ep_no(name):
    import re
    m = re.search(r"_e(\d+)$", name)
    if m:
        return int(m.group(1))
    m = re.search(r"[Ss](\d{1,3})[ ._-]*[Ee][Pp]?[ ._-]*(\d{1,4})", name)
    if m:
        return int(m.group(2))
    m = re.search(r"\b(\d{1,2})x(\d{1,4})\b", name)
    return int(m.group(2)) if m else None


def ep_in_range(epstr, n):
    """True/False/None (unknown). Handles open-ended ranges such as 1203-."""
    if not epstr:
        return None
    if n is None:
        return None
    for part in epstr.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                lo = int(a) if a else 1
                hi = int(b) if b else 10 ** 9
            except ValueError:
                continue
            if lo <= n <= hi:
                return True
        else:
            try:
                if int(part) == n:
                    return True
            except ValueError:
                pass
    return False


def rank(themes, n, kind):
    ts = [t for t in themes if t["type"] == kind]
    a = [t for t in ts if ep_in_range(t.get("episodes"), n) is True]
    b = [t for t in ts if ep_in_range(t.get("episodes"), n) is None]
    c = [t for t in ts if ep_in_range(t.get("episodes"), n) is False]
    key = lambda t: (t["sequence"] if t["sequence"] is not None else 999)
    return sorted(a, key=key) + sorted(b, key=key) + sorted(c, key=key)


def trimmed(m, trim=TRIM_S):
    s, e = round(m["start_s"] + trim, 3), round(m["end_s"] - trim, 3)
    return (s, e) if e > s else None


def ensure_show(slug, theme_dir):
    """Fetch one show's themes over GraphQL and cache them locally. Nothing else is fetched."""
    os.makedirs(theme_dir, exist_ok=True)
    man_path = os.path.join(theme_dir, slug + ".manifest.json")
    if os.path.exists(man_path):
        man = json.load(open(man_path, encoding="utf-8"))
    else:
        man = theme_resolver.fetch_anime(slug)
        json.dump(man, open(man_path, "w", encoding="utf-8"), indent=1)
    items = man["themes"]
    for i, t in enumerate(items):
        base = "%s-%s" % (slug, t["slug"])
        ogg = os.path.join(theme_dir, base + ".ogg")
        f32 = os.path.join(theme_dir, base + ".f32")
        npy = os.path.join(theme_dir, base + ".npy")
        meta = os.path.join(theme_dir, base + ".json")
        if os.path.exists(npy) and os.path.exists(meta):
            continue
        if i:
            time.sleep(S.API_DELAY_S)
        if not os.path.exists(ogg):
            theme_cache.fetch(t["audio"], ogg)
        if not os.path.exists(f32):
            theme_cache.to_f32(ogg, f32)
        import numpy as _np
        x = _np.fromfile(f32, "<f4")
        la, lb, core = theme_cache.trim_silence(x)
        _np.save(npy, core)
        json.dump({"ogg": os.path.basename(ogg), "ogg_bytes": os.path.getsize(ogg),
                   "sr": S.SR, "total": len(x), "lead": la, "trail": len(x) - lb,
                   "core": len(core), "audio": t["audio"]},
                  open(meta, "w", encoding="utf-8"), indent=1)
    return man


def match_kind(src, D, kind, slug, cands, theme_dir, loose):
    from .themes.theme_matcher import match_epx
    if kind in ("OP", "intro"):
        epx = src.audio(0.0, min(HEAD_S, D)).astype(np.float32)
        if S.MASK_TAIL_OP_S > 0:
            epx = epx[:max(0, len(epx) - int(S.MASK_TAIL_OP_S * S.SR))]
        off = 0.0
    else:
        off = max(0.0, D - TAIL_S)
        epx = src.audio(off, D).astype(np.float32)
    for t in cands[:S.MAX_CAND]:
        base = "%s-%s" % (slug, t["slug"])
        try:
            meta = json.load(open(os.path.join(theme_dir, base + ".json"), encoding="utf-8"))
            core = np.load(os.path.join(theme_dir, base + ".npy")).astype(np.float32)
            m = match_epx(epx, off, meta, core, kind, slug + "/" + base, base, loose=loose)
        except Exception:
            continue
        if m.get("match"):
            return m
    return None


def fill_gaps(spec, name, number, slug, segments, cache_dir, theme_dir, loose=False):
    """Theme segments for intro/credits types missing from segments. Never touches existing ones."""
    have = {s["type"] for s in segments}
    man = ensure_show(slug, theme_dir)
    src = media.Source(spec, name, cache_dir)
    try:
        D = src.duration
    except Exception:
        return []
    added = []
    for want, kind in (("intro", "OP"), ("credits", "ED")):
        if want in have:
            continue
        m = match_kind(src, D, kind, slug, rank(man["themes"], number, kind), theme_dir, loose)
        if not m:
            continue
        te = trimmed(m)
        if not te:
            continue
        s, e = te
        added.append({"type": want, "start": s, "end": e, "length": round(e - s, 3),
                      "confidence": 0.6, "method": "theme-match",
                      "gates": {"theme": m["theme"], "gate": "loose" if loose else "strict",
                                "trim_s": TRIM_S, "median_corr": m.get("median_corr"),
                                "lag_ncc": m.get("lag_ncc"), "hi_n": m.get("hi_n")}})
    added.sort(key=lambda s: s["start"])
    return added
