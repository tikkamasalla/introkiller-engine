"""Intro / credits / preview extraction: one season at a time (docs/METHOD.md has the full method).

Input : 2+ episodes of one season (local files or HTTP(S) URLs; only the needed windows are read).
Output: per episode a JSON with segments {type, start, end, confidence, gates} and the candidates it rejected.

Stages (see docs/METHOD.md for the gates)
  1. audio alignment of the head window and the tail window against the other episodes (align.py)
  2. cluster the per-reference stretches; gates: correlation, two-reference agreement, clip, length
  3. visual edge refinement to the exact frame (edges.py), inward-shrink if the audio edge is already story
  4. classification (intro / credits / preview-or-other) with the visual-share check; post-credit cut
  5. preview stage (preview.py): credits end -> EOF, only with a season-wide length and a shared card or jingle
Uncertain = no segment.  The pipeline never reads container chapters.
"""
import json
import os
import sys
import time

import numpy as np

from . import align, edges, media, preview, recap, visual

SR = media.SR
QUIET = False

CFG = {
    "head_stages": [300.0, 720.0],       # seconds from the start that are searched (second stage only if needed)
    "tail_stages": [300.0, 600.0],       # seconds before the end
    "ncc_min": 0.85,                     # gate: overall correlation of a stretch (AAC rips of the same OP measure 0.895-0.99)
    "ref_agree": 0.20,                   # supporters agreeing within this (s) -> median edges
    "ref_loose": 3.0,                    # supporters agreeing within this (s) -> INNER intersection of their edges (never wider than any reference)
    "edge_unclip": True,                 # clipped supporters constrain only the edge they saw
    "min_refs": 2,                       # gate: independent references that must agree
    "single_ref_ncc": 0.95,              # when only 2 episodes exist: pair-only rule
    "cut_trim_rest": 2.5,                # an unverified credits end with more than this left in the file is cut back to a hard cut (LOGH S1E06/E12 ran 5 s into the next-episode card)
    "true_end": True,                    # where the container's duration overshoots the streams, the audio end is the file end
    "true_end_min": 2.0,                 #     overshoot (s) below which the container duration stands
    "end_anchored": True,                # credits seen by ONE other episode, at the same distance from EOF in both
    "end_anchored_tol": 3.0,             #     distance-from-EOF agreement (s)
    "end_anchored_max_eof": 90.0,        #     ... and the stretch must actually end near EOF, not merely at an equal distance
    "end_anchored_ncc": 0.95,            #     correlation bar of that one reference
    "end_anchored_vis": 0.80,            #     picture share bar; both edges must sit on a confirmed transition
    "preview": True,                     # preview stage (preview.py)
    "preview_len": (10.0, 75.0),         #     seconds, credits end to EOF
    "preview_tol": 1.5,                  #     length agreement with another episode (s)
    "preview_spread": 3.0,               #     longest allowed spread of the lengths in one season group (s)
    "preview_min_peers": 2,              #     other episodes that must agree on the length AND share a card or jingle
    "preview_win": 3.0,                  #     seconds looked at, at the preview start and at its end
    "preview_card_frac": 0.80,           #     card: share of the non-black frames matching the reference
    "preview_card_nonblack": 0.25,       #     card: share of the frames that must be non-black
    "preview_jingle_ncc": 0.80,          #     jingle: correlation of the window against the reference
    "max_refs": 5,
    "intro_len": (5.0, 240.0),
    "short_intro": 20.0,                 # intros shorter than this need both edges visually verified
    "credits_len": (15.0, 700.0),
    "vis_share_min": 0.60,               # credits: share of frames matching a reference picture (or black)
    "lookback": 1.0,                     # max visual move OUTWARD from the audio edge (s); recurring cards share footage with story edges
    "inward": 6.0,                       # max visual move INWARD (audio edge frame already story)
    "clip_tol": 0.35,
    "slot_merge": True, "slot_tol": 0.25, "slot_min_frac": 0.4,   # merge of a same-duration "template slot" gap (see _gap_shared)
    "merge_gap": 25.0,                   # two same-type segments closer than this are merged if every gap frame is shared/black
    "visual_fallback": True,             # head only: when audio finds no intro in an episode, look for a pixel-identical title sequence
    "vis_window": 300.0,                 # seconds from the start hashed for the visual fallback
    "vis_stride": 2,                     # every n-th frame is compared
    "vis_tight": 1.0, "vis_min_len": 8.0, "vis_gap": 1.0, "vis_fill": 0.85, "vis_mad_med": 5.0, "vis_mad_p90": 12.0,
    "recap": False,                      # optional stage: needs the FULL audio of every other episode
}


def log(*a):
    if not QUIET:
        print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


class Ep:
    def __init__(self, idx, spec, name, cache):
        self.idx, self.spec, self.name = idx, spec, name
        self.src = media.Source(spec, name, cache)
        self.D = None
        self.E = None                               # effective file end (see Season._true_end); container duration until measured
        self.found = {"head": [], "tail": []}      # accepted raw segments
        self.rejected = []                          # candidates with reason
        self.win = {}


def refs_of(i, n, max_refs):
    others = [j for j in range(n) if j != i]
    if len(others) <= max_refs:
        return others
    others.sort(key=lambda j: abs(j - i))
    return others[:max_refs]


def window(ep, kind, stage_s):
    D = ep.D
    if kind == "head":
        return 0.0, min(stage_s, D * 0.6)
    return max(0.0, D - stage_s), D


def get_audio(ep, kind, a, b):
    parts = []
    step = 300.0
    t = a
    while t < b - 1e-6:
        e = min(b, t + step)
        chunk = ep.src.audio(t, e)
        expect = int(round((e - t) * SR))
        if e < b - 1e-6 and 0 < len(chunk) < expect:   # keep the concatenated array on the request clock
            chunk = np.pad(chunk, (0, expect - len(chunk)))
        parts.append(chunk)
        t = e
    return np.concatenate(parts)


def spans_overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


class Season:
    def __init__(self, specs, names, cache, cfg=None):
        self.cfg = dict(CFG, **(cfg or {}))
        self.eps = [Ep(i, s, n, cache) for i, (s, n) in enumerate(zip(specs, names))]
        for e in self.eps:
            e.D = e.E = e.src.duration
        self.n = len(self.eps)

    def _true_end(self, e, a, x):
        """x = decoded audio of the tail window from a to the listed file end.  Container durations can overshoot the streams (Blood+
        e06 by 43 s: 1479.2 listed, audio to 1436.1, in the original file; a chapter-stripped remux does not show this).  Source.audio
        has already checked that a short decode is the real end of the stream."""
        end = a + len(x) / SR
        if self.cfg["true_end"] and e.D - end >= self.cfg["true_end_min"]:
            e.E = end
            log(e.name, "file end: audio stops at %.2f, container lists %.2f" % (end, e.D))

    # ------------------------------------------------------------------ stage 1+2: audio
    def search(self, kind):
        cfg = self.cfg
        stages = cfg["head_stages"] if kind == "head" else cfg["tail_stages"]
        for si, stage_s in enumerate(stages):
            todo = [e for e in self.eps if self._needs(e, kind, si)]
            if not todo:
                break
            log("search", kind, "stage", si, "window", stage_s, "targets", [e.name for e in todo])
            # windows + audio for ALL episodes (refs need it too)
            sig = {}
            for e in self.eps:
                a, b = window(e, kind, stage_s)
                raw = get_audio(e, kind, a, b)
                if kind == "tail" and si == 0:
                    self._true_end(e, a, raw)
                x = align.prep(raw)
                sig[e.idx] = {"a": a, "b": b, "x": x}
            nmax = max(len(v["x"]) for v in sig.values())
            nfft = 1 << int(np.ceil(np.log2(2 * nmax)))
            specs = {i: align.Spec(v["x"], nfft) for i, v in sig.items()}
            pair_cache = {}
            for e in todo:
                cands = []
                for r in refs_of(e.idx, self.n, cfg["max_refs"]):
                    key = (min(e.idx, r), max(e.idx, r))
                    if key not in pair_cache:
                        pair_cache[key] = self._pair(key[0], key[1], sig, specs)
                    for c in pair_cache[key]:
                        cands.append(c if c["t"] == e.idx else self._mirror(c))
                self._accept(e, kind, cands, sig, si, stage_s)
            del specs
        if kind == "head" and cfg["visual_fallback"] and self.n >= 3:
            self.visual_fallback(kind)

    def visual_fallback(self, kind):
        cfg = self.cfg
        todo = [e for e in self.eps if not e.found[kind]]
        if not todo:
            return
        log("visual fallback", kind, "targets", [e.name for e in todo])
        P = {}
        for e in self.eps:
            a, b = window(e, kind, cfg["vis_window"])
            ts, fr = e.src.grab(a, b)
            P[e.idx] = visual.prep_frames(ts, fr, cfg["vis_stride"])
        for e in todo:
            cands = []
            for r in refs_of(e.idx, self.n, cfg["max_refs"]):
                for c in visual.runs_against(P[e.idx], P[r], cfg):
                    cands.append({"t": e.idx, "r": r, "lag": 0, "off": c["off"], "start": c["start"], "end": c["end"],
                                  "len": c["end"] - c["start"], "ncc": 1.0, "peak": 0.0, "clip_start": False,
                                  "clip_end": c["end"] >= P[e.idx]["ts"][-1] - 0.3, "live": 1.0, "visual": True,
                                  "mad_med": c["mad_med"], "frac": c["frac"]})
            self._accept(e, kind, cands, {e.idx: {"a": 0.0, "b": cfg["vis_window"]}}, 0, cfg["vis_window"])

    def _needs(self, e, kind, si):
        if si == 0:
            return True
        if any(not g.get("end_anchored") for g in e.found[kind]):   # an end-anchored pair may still be replaced by a real cluster
            return False
        # second stage: only episodes with nothing yet, or with a clipped candidate
        return True

    def _pair(self, i, j, sig, specs):
        """Alignment candidates between episodes i<j.  Each is expressed for target i (t=i, r=j)."""
        out = []
        lags = align.top_lags(specs[i], specs[j], k=3)
        ei, ej = self.eps[i], self.eps[j]
        for lag, peak, noise in lags:
            off = (sig[i]["a"] - sig[j]["a"]) + lag / SR      # time_i = time_j + off
            for st in align.stretches(sig[i]["x"], sig[j]["x"], lag):
                s, e = st["start"] + sig[i]["a"], st["end"] + sig[i]["a"]
                # which clock limits the stretch?  clip flags are overlap limits: translate to file/window limits
                clip_s = st["clip_start"] and not self._is_file_edge(i, j, s, off, "start", sig)
                clip_e = st["clip_end"] and not self._is_file_edge(i, j, e, off, "end", sig)
                out.append({"t": i, "r": j, "lag": lag, "off": off, "start": s, "end": e, "len": e - s, "ncc": st["ncc"],
                            "peak": peak, "clip_start": bool(clip_s), "clip_end": bool(clip_e), "live": st["live"],
                            "edge_s_file": bool(st["clip_start"] and not clip_s),
                            "edge_e_file": bool(st["clip_end"] and not clip_e)})
        return out

    def _is_file_edge(self, i, j, t, off, which, sig):
        """A clipped stretch edge is genuine only if the target (and the ref) are at the *file* boundary there.
        End edge: either episode at its own EOF is enough -- the pair's overlap really ends there, and the
        other episode can only make the segment longer, never move this edge into story (Texhnolyze e04 is
        a shorter file: its stretch ends 1.5 s before the references' EOF in their clocks).  Symmetric in
        i/j, because candidates are mirrored with their clip flags."""
        tol = 0.3
        ti, tj = t, t - off
        Di, Dj = self.eps[i].E, self.eps[j].E
        if which == "start":
            return ti <= tol and tj <= tol
        return abs(ti - Di) <= tol + 0.5 or abs(tj - Dj) <= tol + 0.5

    def _mirror(self, c):
        m = dict(c)
        m["t"], m["r"] = c["r"], c["t"]
        m["off"] = -c["off"]
        m["start"], m["end"] = c["start"] - c["off"], c["end"] - c["off"]
        return m

    def _accept(self, e, kind, cands, sig, si, stage_s):
        cfg = self.cfg
        a0, b0 = sig[e.idx]["a"], sig[e.idx]["b"]
        pool = [c for c in cands if c["ncc"] >= cfg["ncc_min"]]
        used = set()
        got = []
        # greedy: best-supported group first
        while True:
            best = None
            for s in pool:
                if id(s) in used:
                    continue
                sup = {}
                for c in pool:
                    if id(c) in used:
                        continue
                    if abs(c["start"] - s["start"]) <= cfg["ref_loose"] and abs(c["end"] - s["end"]) <= cfg["ref_loose"]:
                        sup.setdefault(c["r"], c)
                score = (len(sup), s["end"] - s["start"])
                if best is None or score > best[0]:
                    best = (score, sup)
            if best is None:
                break
            sup = list(best[1].values())
            for c in pool:
                m0 = np.median([x["start"] for x in sup])
                m1 = np.median([x["end"] for x in sup])
                if spans_overlap(c["start"], c["end"], m0, m1) > 0.5 * (m1 - m0):
                    used.add(id(c))
            got.append(self._group(e, kind, sup, sig, si, stage_s))
        # candidates below the correlation bar are reported once for the record
        for c in cands:
            if c["ncc"] < cfg["ncc_min"] and c["end"] - c["start"] >= 10.0:
                e.rejected.append({"kind": kind, "start": round(c["start"], 2), "end": round(c["end"], 2),
                                   "ref": self.eps[c["r"]].name, "reason": "ncc %.3f < %.2f" % (c["ncc"], cfg["ncc_min"])})
        for g in sorted(got, key=lambda x: bool(x.get("end_anchored"))):      # clusters first, end-anchored pairs after them
            if g.get("accepted"):
                over = [h for h in e.found[kind] if spans_overlap(g["start"], g["end"], h["start"], h["end"]) > 0]
                if g.get("end_anchored") and (over or any(not h.get("end_anchored") for h in e.found[kind])):
                    e.rejected.append({"kind": kind, "start": round(g["start"], 3), "end": round(g["end"], 3), "n_refs": 1,
                                       "reason": "end-anchored pair overlaps an accepted candidate"})
                    continue
                if not g.get("end_anchored"):                                 # a real cluster replaces any end-anchored pair of this kind
                    drop = {id(h) for h in e.found[kind] if h.get("end_anchored")}
                    e.found[kind] = [h for h in e.found[kind] if id(h) not in drop]
                if not any(abs(g["start"] - h["start"]) < 1.0 and abs(g["end"] - h["end"]) < 1.0 for h in e.found[kind]):
                    e.found[kind].append(g)
            else:
                e.rejected.append({k: g[k] for k in g if k not in ("sup",)})

    def _group(self, e, kind, sup, sig, si, stage_s):
        cfg = self.cfg
        s = float(np.median([c["start"] for c in sup]))
        t1 = float(np.median([c["end"] for c in sup]))
        tight = max(max(abs(c["start"] - s), abs(c["end"] - t1)) for c in sup) <= cfg["ref_agree"]
        if not tight:
            s = float(max(c["start"] for c in sup))
            t1 = float(min(c["end"] for c in sup))
        g = {"tight": bool(tight), "kind": kind, "start": s, "end": t1, "len": t1 - s, "n_refs": len(sup),
             "ncc_min": min(c["ncc"] for c in sup), "refs": [(self.eps[c["r"]].name, c["off"]) for c in sup],
             "spread_s": max(abs(c["start"] - s) for c in sup), "spread_e": max(abs(c["end"] - t1) for c in sup),
             "sup": sup, "stage": si}
        clip_s = any(c["clip_start"] for c in sup)
        clip_e = any(c["clip_end"] for c in sup)
        if (clip_s or clip_e) and cfg["edge_unclip"]:
            # a supporter whose stretch is cut by ITS OWN window/file limit says nothing about that edge: take each edge only from the
            # supporters that saw it (>= min_refs of them), never wider than those.  (Rejecting the whole candidate when one of five
            # references was clipped lost the Beelzebub e14/e22 OP and the Haibane ED.)
            us = [c for c in sup if not c["clip_start"]]
            ue = [c for c in sup if not c["clip_end"]]
            if len(us) >= cfg["min_refs"] and len(ue) >= cfg["min_refs"]:
                ms = float(np.median([c["start"] for c in us]))
                me = float(np.median([c["end"] for c in ue]))
                ts_ = max(abs(c["start"] - ms) for c in us) <= cfg["ref_agree"]
                te_ = max(abs(c["end"] - me) for c in ue) <= cfg["ref_agree"]
                s2 = ms if ts_ else float(max(c["start"] for c in us))
                t2 = me if te_ else float(min(c["end"] for c in ue))
                g.update({"start": s2, "end": t2, "len": t2 - s2, "tight": bool(ts_ and te_),
                          "spread_s": max(abs(c["start"] - s2) for c in us), "spread_e": max(abs(c["end"] - t2) for c in ue),
                          "unclipped_edges": True, "ncc_min": min(c["ncc"] for c in sup)})
                clip_s = clip_e = False
        g["clipped"] = bool(clip_s or clip_e)
        g["visual_only"] = all(c.get("visual") for c in sup)
        lo, hi = (cfg["intro_len"] if kind == "head" else cfg["credits_len"])
        reason = None
        if len(sup) < cfg["min_refs"]:
            # pair-only: a verbatim recap/flashback replay looks exactly like an OP/ED to one reference, so the
            # segment must also sit where an OP/ED sits in BOTH episodes (head: near the start in one of them,
            # tail: near EOF).  Anything else is indistinguishable from replayed story.
            pos_ok = False
            if len(sup) == 1:
                c0 = sup[0]
                st, sr = c0["start"], c0["start"] - c0["off"]           # the same picture in this episode and in the reference
                if kind == "tail":
                    pos_ok = e.E - g["end"] <= 120.0 and self.eps[c0["r"]].E - (c0["end"] - c0["off"]) <= 120.0
                else:
                    pos_ok = min(st, sr) <= 90.0 and (abs(c0["off"]) <= 90.0 or max(st, sr) <= 90.0)
            if self.n == 2 and g["ncc_min"] >= cfg["single_ref_ncc"] and pos_ok:
                g["single_ref"] = True
            elif kind == "tail" and self._end_anchored(e, sup):
                g["end_anchored"] = True
            else:
                reason = "only %d reference(s) agree (need %d)" % (len(sup), cfg["min_refs"])
        if reason is None and not (lo <= g["len"] <= hi):
            reason = "length %.1f s outside %.0f-%.0f" % (g["len"], lo, hi)
        if reason is None and g["visual_only"] and max(g["spread_s"], g["spread_e"]) > cfg["vis_tight"]:
            reason = "visual-only candidate: references disagree by %.1f s (> %.1f s); partly re-used footage, not a title sequence" % (
                max(g["spread_s"], g["spread_e"]), cfg["vis_tight"])
        if reason is None and g["clipped"]:
            more = si + 1 < len(cfg["head_stages" if kind == "head" else "tail_stages"])
            reason = "clipped at analysis window or reference limit" + (" (next stage will widen)" if more else "")
        if reason is None and kind == "head" and g["start"] > 0.6 * e.D:
            reason = "head segment starts late"
        if reason is None and kind == "tail" and g["start"] < 0.5 * e.D:
            reason = "tail segment starts early"
        if reason:
            g["accepted"] = False
            g["reason"] = reason
        else:
            g["accepted"] = True
        return g

    def _end_anchored(self, e, sup):
        """One reference only: credits are accepted (later gates in _finish) when the stretch sits at the same distance from
        EOF in both episodes.  A flashback replay of the other episode's scene has no reason to do that."""
        cfg = self.cfg
        if not cfg["end_anchored"] or len(sup) != 1 or sup[0]["ncc"] < cfg["end_anchored_ncc"]:
            return False
        c = sup[0]
        dist_t = e.E - c["end"]
        dist_r = self.eps[c["r"]].E - (c["end"] - c["off"])
        return dist_t <= cfg.get("end_anchored_max_eof", 90.0) and abs(dist_t - dist_r) <= cfg["end_anchored_tol"]

    # ------------------------------------------------------------------ stage 3+4
    def refine_and_classify(self):
        cfg = self.cfg
        for e in self.eps:
            e.segments = []
            for kind in ("head", "tail"):
                for g in e.found[kind]:
                    seg = self._finish(e, kind, g)
                    if seg:
                        e.segments.append(seg)
            e.segments.sort(key=lambda x: x["start"])
            e.segments = self._merge_split(e, e.segments)

    def _merge_split(self, e, segs):
        """Two segments of the same type with a gap <= merge_gap s are one segment whose middle did not correlate in
        audio (music replaced by a jingle, a voice-over...).  They are merged ONLY when every frame of the gap is
        near-black or matches (pHash) the same footage in >= 2 reference episodes at the references' own time offsets
        (offsets of the two parts must agree within 0.5 s).  Otherwise they stay split (the gap may be story)."""
        cfg = self.cfg
        out = []
        for sg in segs:
            prev = out[-1] if out else None
            if prev is not None and prev["type"] == sg["type"] and 0.0 < sg["start"] - prev["end"] <= cfg["merge_gap"]:
                ok, info = self._gap_shared(e, prev, sg)
                e.rejected.append({"kind": "merge", "start": round(prev["end"], 3), "end": round(sg["start"], 3), "type": sg["type"],
                                   "reason": ("merged: " if ok else "kept split: ") + info})
                if ok:
                    prev["end"] = sg["end"]
                    prev["length"] = round(prev["end"] - prev["start"], 3)
                    prev["confidence"] = min(prev["confidence"], sg["confidence"])
                    prev["gates"]["edge_end"] = sg["gates"]["edge_end"]
                    prev["gates"]["audio_end"] = sg["gates"]["audio_end"]
                    prev["gates"]["merged_gap"] = info
                    continue
            out.append(sg)
        return out

    def _gap_shared(self, e, a, b):
        cfg = self.cfg
        offs_a = dict(a["gates"]["ref_offsets"])
        offs_b = dict(b["gates"]["ref_offsets"])
        common = [(n, offs_a[n]) for n in offs_a if n in offs_b and abs(offs_a[n] - offs_b[n]) <= 0.5]
        if len(common) < 2:
            return False, "fewer than 2 references with agreeing offsets"
        t0, t1 = a["end"], b["start"]
        ts, fr = e.src.grab(t0, t1)
        if len(ts) < 3:
            return False, "no gap frames"
        refs = [(self.eps[self._idx(n)].src, off) for n, off in common]
        hs = edges.hashes(fr)
        blk = edges.is_black(fr)
        nm = np.sum([edges._ref_match(ts, hs, r, off, t0, t1) <= edges.HT for r, off in refs], axis=0)
        ok = blk | (nm >= 2)
        frac = float(np.mean(ok))
        if bool(ok.all()):
            return True, "all %d gap frames shared/black (%d refs)" % (len(ts), len(common))
        # Template slot: the gap has the SAME duration in >= 2 reference episodes (both parts of the segment sit at the same time
        # offset to each reference within slot_tol) and at least slot_min_frac of its frames are shared/black.  Story cannot sit
        # between two parts of a title sequence at an identical duration in several episodes; what differs is episode-specific
        # clips shown inside the sequence (Detective Conan teaser montage).  Unmatched frames must lie in the middle:
        # the first and the last second of the gap are required to be shared/black.
        tight = [(n, o) for n, o in common if abs(offs_a[n] - offs_b[n]) <= cfg["slot_tol"]]
        edge_ok = bool(ok[:max(1, int(len(ts) * 1.0 / max(1e-6, t1 - t0)))].all() and ok[-max(1, int(len(ts) * 1.0 / max(1e-6, t1 - t0))):].all())
        if cfg["slot_merge"] and len(tight) >= 2 and frac >= cfg["slot_min_frac"] and edge_ok:
            return True, "template slot: gap %.1f s has the same duration in %d refs (offsets agree <= %.2f s), %.0f%% of %d gap frames shared/black, rest episode-specific" % (
                t1 - t0, len(tight), cfg["slot_tol"], 100 * frac, len(ts))
        return False, "%.1f%% of %d gap frames shared/black (need all, or a same-duration template slot with >= %.0f%%)" % (100 * frac, len(ts), 100 * cfg["slot_min_frac"])

    def _finish(self, e, kind, g):
        cfg = self.cfg
        refs = [(self.eps[self._idx(n)].src, off) for n, off in g["refs"][:4]]
        a_s, a_e = g["start"], g["end"]
        res = edges.refine(e.src, a_s, a_e, refs, refs, lookback=cfg["lookback"], min_refs=1 if g.get("end_anchored") else 2)
        s, t1 = res["start"], res["end"]
        if g.get("visual_only"):
            good = ("cut", "black_end", "black_start", "file_start", "black_end(file_start)", "none(lookback exhausted)")
            bad = [k for k in (res["start_kind"], res["end_kind"]) if k not in good]
            if bad:
                e.rejected.append({"kind": kind, "start": round(a_s, 3), "end": round(a_e, 3), "type": "intro", "reason":
                                   "visual-only segment: edge not confirmed by a visual transition (%s)" % ", ".join(bad),
                                   "n_refs": g["n_refs"]})
                return None
        notes = {"start_kind": res["start_kind"], "end_kind": res["end_kind"]}
        story_safe = True
        # never move more than the lookback; never beyond the audio edge into unshared picture
        if s < a_s - cfg["lookback"] - 0.6 or t1 > a_e + cfg["lookback"] + 0.6:
            s, t1 = a_s, a_e
            notes["revert"] = "move exceeds lookback"
        # inward shrink: audio edge frame not shared  -> look for the last/first shared frame inside
        s2, k2 = self._inward(e, refs, s, t1, "s", res["start_kind"])
        t2, k3 = self._inward(e, refs, s2, t1, "e", res["end_kind"])
        if k2:
            notes["start_kind"] = k2
        if k3:
            notes["end_kind"] = k3
        s, t1 = s2, t2
        # Verification is what refine/_inward established against the REFERENCES.  The target-only trims below
        # (black at the edge, last hard cut) may move the edge inward, but they must not launder an unverified
        # edge into a verified one for the gates.
        raw_s_kind, raw_e_kind = notes["start_kind"], notes["end_kind"]
        verified_s = not raw_s_kind.startswith("none")
        verified_e = not raw_e_kind.startswith("none")
        # black / fade frames at either end belong to the transition, not to the segment: trim inward (<= 4 s)
        s, kb1 = self._trim_black(e, s, "s")
        t1, kb2 = self._trim_black(e, t1, "e")
        if kb1:
            notes["start_kind"] = kb1
        if kb2:
            notes["end_kind"] = kb2
        if kind == "tail" and notes["end_kind"].startswith("none") and e.E - t1 > cfg["cut_trim_rest"]:
            # unverified end with something after it (preview jingle/card shares audio AND picture with the credits):
            # stop at the last hard cut within 8 s of the audio end, never later
            c, how = self._last_transition(e, t1, 8.0)
            if c is not None:
                t1 = c
                notes["end_kind"] = how
        if kind == "head" and notes["end_kind"].startswith("none"):
            # unverified intro end: music bleeds into the first story scene (which can be shared footage); stop at the
            # last hard cut within 2.5 s of the audio end, never later
            c = self._last_cut(e, t1, 2.5)
            if c is not None:
                t1 = c
                notes["end_kind"] = "cut_trim"
        vis = None
        typ = None
        reason = None
        if kind == "head":
            typ = "intro"
            # Head candidates get the same picture-share measurement as tail ones: an OP song played over
            # story (premiere/finale) or bleeding seconds past the OP visuals is audio-shared but not an intro.
            vis, cut, pre = self._vis_share(e, refs, s, t1)
            notes["vis_share"] = round(vis, 3)
            if pre is not None and pre < s + 0.6 * (t1 - s):
                notes["pre_cut"] = "shared picture starts at %.2f, rest before it not intro" % pre
                s = pre
                notes["start_kind"] = "pre_cut"
                verified_s = True
            if cut is not None and cut > s + 0.4 * (t1 - s):
                notes["post_cut"] = "shared picture ends at %.2f, rest not intro" % cut
                t1 = cut
                notes["end_kind"] = "post_cut"
                verified_e = True
            if g["len"] < cfg["short_intro"] and not (verified_s and verified_e):
                reason = "short (%.1f s) and edges not visually verified" % g["len"]
            # The picture inside BOTH ends matches fewer than 2 references (or the edge frame is not
            # shared and no inward run was found): the audio clock and the picture clock disagree, so
            # the stretch is not where the audio says it is.  A transition the walk could not pin down
            # (soft / lookback exhausted) is not this.  LOGH S1E02 (shifted decode) is the measured case.
            bad_edge = ("none(<2 similar refs)", "none(edge frame not shared)")
            if reason is None and raw_s_kind in bad_edge and raw_e_kind in bad_edge \
                    and notes["start_kind"] != "pre_cut" and notes["end_kind"] != "post_cut":
                reason = "picture at both edges is not shared (audio/picture clocks disagree)"
            if reason is None and not g.get("visual_only") and t1 - s >= 6.0 and vis < cfg["vis_share_min"]:
                reason = "head audio match with picture share %.2f < %.2f (song over story)" % (vis, cfg["vis_share_min"])
        else:
            vis, cut, pre = self._vis_share(e, refs, s, t1)
            notes["vis_share"] = round(vis, 3)
            if pre is not None and pre < s + 0.6 * (t1 - s):
                notes["pre_cut"] = "shared picture starts at %.2f, lead-in not credits" % pre
                s = pre
                notes["start_kind"] = "pre_cut"
                verified_s = True
            if cut is not None and cut > s + 0.4 * (t1 - s):
                notes["post_cut"] = "shared picture ends at %.2f, rest not credits" % cut
                t1 = cut
                notes["end_kind"] = "post_cut"
                verified_e = True
            if vis >= cfg["vis_share_min"] or (g.get("single_ref") is None and False):
                typ = "credits"
            else:
                typ = "other"
                reason = "tail audio match with picture share %.2f < %.2f (preview / post-credit / non-credits)" % (vis, cfg["vis_share_min"])
        if g.get("single_ref"):
            if (vis or 0) < 0.8:
                reason = reason or "single reference needs picture share >= 0.8"
            if kind == "head" and not (verified_s and verified_e):
                reason = reason or "single reference needs verified edges"
        if g.get("end_anchored"):
            good = ("cut", "black_end", "black_start", "inward_cut", "post_cut", "pre_cut")
            bad = [k for k in (notes["start_kind"] if notes["start_kind"] == "pre_cut" else raw_s_kind,
                               notes["end_kind"] if notes["end_kind"] == "post_cut" else raw_e_kind) if k not in good]
            if (vis or 0) < cfg["end_anchored_vis"]:
                reason = reason or "end-anchored pair needs picture share >= %.2f (%.2f)" % (cfg["end_anchored_vis"], vis or 0)
            elif bad:
                reason = reason or "end-anchored pair: edge not confirmed (%s)" % ", ".join(bad)
            elif notes["end_kind"] == "post_cut" and not self._on_transition(e, t1):
                reason = reason or "end-anchored pair: post-credit cut %.2f is not on a transition" % t1
            elif notes["start_kind"] == "pre_cut" and not self._on_transition(e, s):
                reason = reason or "end-anchored pair: lead-in cut %.2f is not on a transition" % s
        L = t1 - s
        lo, hi = (cfg["intro_len"] if typ == "intro" else cfg["credits_len"])
        if reason is None and not (lo <= L <= hi):
            reason = "refined length %.1f outside %.0f-%.0f" % (L, lo, hi)
        if reason:
            e.rejected.append({"kind": kind, "start": round(s, 3), "end": round(t1, 3), "type": typ, "reason": reason,
                               "n_refs": g["n_refs"], "ncc_min": round(g["ncc_min"], 3)})
            return None
        conf = 0.55 + 0.20 * min(1.0, max(0.0, (g["ncc_min"] - 0.90) / 0.08))
        conf += 0.10 if g["n_refs"] >= 3 else 0.0
        conf += 0.05 * (1 if verified_s else 0) + 0.05 * (1 if verified_e else 0)
        if not g["tight"]:
            conf -= 0.10
        if kind == "tail":
            conf += 0.05 * min(1.0, (vis or 0))
        if g.get("single_ref") or g.get("end_anchored"):
            conf -= 0.15
        if g.get("visual_only"):
            conf = min(conf, 0.75)
        conf = round(min(conf, 0.99), 3)
        return {"type": typ, "start": round(s, 3), "end": round(t1, 3), "length": round(L, 3), "confidence": conf,
                "method": "visual-only+visual-edges" if g.get("visual_only") else "audio-align+visual-edges",
                "gates": {"ncc_min": round(g["ncc_min"], 4), "ncc_ok": g["ncc_min"] >= cfg["ncc_min"],
                          "n_refs": g["n_refs"], "ref_spread_s": round(max(g["spread_s"], g["spread_e"]), 3),
                          "ref_agree_ok": bool(g["tight"]), "edges_rule": "median" if g["tight"] else "inner intersection (refs disagree by 0.2-3.0 s)",
                          "length_ok": True, "not_clipped": not g["clipped"],
                          "edge_start": notes["start_kind"], "edge_end": notes["end_kind"],
                          "audio_start": round(a_s, 3), "audio_end": round(a_e, 3),
                          "vis_share": notes.get("vis_share"), "single_ref": bool(g.get("single_ref")),
                          "end_anchored": bool(g.get("end_anchored")),
                          "ref_offsets": [(n, round(o, 3)) for n, o in g["refs"]],
                          "extra": {k: v for k, v in notes.items() if k not in ("start_kind", "end_kind", "vis_share")}},
                "refs": [n for n, _ in g["refs"]]}

    def _on_transition(self, e, t, tol=0.25):
        """A hard cut or a black edge within tol s of t."""
        ts, fr = e.src.grab(t - tol - 0.1, t + tol + 0.1)
        if len(ts) < 3:
            return False
        cs, blk = edges.cut_scores(fr), edges.is_black(fr)
        return any((cs[i] >= edges.CUT_DIFF or blk[i] != blk[i - 1]) and abs(ts[i] - t) <= tol for i in range(1, len(ts)))

    def _last_transition(self, e, t, span):
        """First black run (>= 0.25 s) within span s before t, else the last hard cut: (time, end kind) or (None, None).  An ED that fades
        through black into a next-episode card has no hard cut at all (LOGH S1E06/E12: the card's jingle is shared, audio end 5 s into it);
        a cut after the black run belongs to whatever follows the credits, so it must not win."""
        ts, fr = e.src.grab(t - span, t + 0.3)
        if len(ts) < 4:
            return None, None
        cs, blk = edges.cut_scores(fr), edges.is_black(fr)
        need = max(2, int(0.25 * len(ts) / max(1e-6, ts[-1] - ts[0])))
        best = None, None
        for i in range(1, len(ts)):
            if ts[i] > t + 0.05:
                break
            if blk[i] and not blk[i - 1] and len(blk[i:i + need]) == need and blk[i:i + need].all():
                return float(ts[i]), "black_trim"
            if cs[i] >= edges.CUT_DIFF:
                best = float(ts[i]), "cut_trim"
        return best

    def _last_cut(self, e, t, span):
        ts, fr = e.src.grab(t - span, t + 0.3)
        if len(ts) < 4:
            return None
        cs = edges.cut_scores(fr)
        idx = [i for i in range(1, len(ts)) if cs[i] >= edges.CUT_DIFF and ts[i] <= t + 0.05]
        return float(ts[idx[-1]]) if idx else None

    def _trim_black(self, e, t, which):
        lim = 4.0
        lo, hi = (t - 0.2, t + lim) if which == "s" else (t - lim, t + 0.2)
        ts, fr = e.src.grab(lo, hi)
        if len(ts) < 3:
            return t, None
        blk = edges.is_black(fr)
        if which == "s":
            i0 = int(np.argmin(np.abs(ts - t)))
            if not blk[i0]:
                return t, None
            j = i0
            while j < len(ts) and blk[j]:
                j += 1
            if j >= len(ts):
                return t, None
            return float(ts[j]), "black_trim"
        i0 = int(np.searchsorted(ts, t, side="left")) - 1   # last frame INSIDE [.., t): the frame at t is already outside
        if i0 < 0 or not blk[i0]:
            return t, None
        j = i0
        while j >= 0 and blk[j]:
            j -= 1
        if j < 0:
            return t, None
        return float(ts[j + 1]), "black_trim"

    def _idx(self, name):
        for e in self.eps:
            if e.name == name:
                return e.idx
        raise KeyError(name)

    def _inward(self, e, refs, s, t, which, kind):
        """If the (audio) edge frame is neither shared nor black, move the edge inward to the nearest transition
        into shared picture (>= 1 s of shared/black frames beyond it, containing shared frames).  The boundary
        may be a hard cut or the edge of a black/fade run (a fade has no cut); the edge never moves outward."""
        if not (kind.startswith("none(edge frame not shared)") or kind.startswith("none(<")):
            return (s if which == "s" else t), None
        cfg = self.cfg
        edge = s if which == "s" else t
        lo, hi = (edge, min(t, edge + cfg["inward"])) if which == "s" else (max(s, edge - cfg["inward"]), edge)
        ts, fr = e.src.grab(lo, hi)
        if len(ts) < 3:
            return edge, kind
        hs = edges.hashes(fr)
        blk = edges.is_black(fr)
        sel = [edges._ref_match(ts, hs, r, off, lo, hi) for r, off in refs]
        if not sel:
            return edge, kind
        nm = np.sum([d <= edges.HT for d in sel], axis=0)
        shared = (nm >= min(2, len(sel))) & ~blk      # black against black hashes to distance 0: never evidence of shared picture
        ok = blk | shared
        fps = max(1.0, len(ts) / max(1e-6, ts[-1] - ts[0]))
        need = max(2, int(round(1.0 * fps)))
        need_real = max(2, int(round(0.25 * fps)))    # one dark fade frame that happens to match is not shared picture
        idx = range(len(ts)) if which == "s" else range(len(ts) - 1, -1, -1)
        run = 0
        first = None
        n_real = 0
        for k in idx:
            if ok[k]:
                run += 1
                if run == 1:
                    first = k
                    n_real = 0
                n_real += int(shared[k])
                if run >= need and n_real >= need_real:   # keep walking through a black run: the shared frames may come after it
                    break
            else:
                run = 0
                first = None
                n_real = 0
        if run >= need and first is not None and n_real >= need_real:
            if which == "s":
                if first > 0 or (kind.startswith("none(edge") and ts[0] > edge + 1e-6):   # the edge frame sits just before the window: the first frame inside is still a transition
                    return float(ts[first]), "inward_cut"
            else:
                if first + 1 < len(ts):
                    return float(ts[first + 1]), "inward_cut"
        return edge, kind

    def _cut_before(self, e, refs, t, span=10.0, limit_s=None):
        """First frame after the last run (>= 0.5 s) of shared/black frames that holds real shared picture, in [limit_s or t-span, t].
        A black-only run is a fade inside story, not the end of the shared picture.  With an explicit limit_s, returns None
        when no such run exists (the boundary is unknown, not t-span inside story)."""
        lo = t - span if limit_s is None else limit_s
        ts, fr = e.src.grab(lo, t)
        if len(ts) < 4:
            return None if limit_s is not None else t - span
        best = np.full(len(ts), 99)
        for r, off in refs:
            best = np.minimum(best, edges._ref_match(ts, edges.hashes(fr), r, off, ts[0], ts[-1]))
        blk = edges.is_black(fr)
        real = (best <= edges.HT) & ~blk
        ok = blk | real
        need = max(2, int(0.5 * len(ts) / max(1e-6, ts[-1] - ts[0])))
        need_real = max(2, need // 2)
        run = n_real = 0
        end = None
        for k in range(len(ts) - 1, -1, -1):
            if ok[k]:
                if run == 0:
                    end = k
                    n_real = 0
                run += 1
                n_real += int(real[k])
                if run >= need and n_real >= need_real:
                    return float(ts[end + 1]) if end + 1 < len(ts) else float(t)
            else:
                run = 0
        return None if limit_s is not None else t - span

    def _cut_after(self, e, refs, s, limit_t):
        """First frame of the first shared/black run (>= 0.5 s, containing shared frames) in [s, limit_t], or None."""
        ts, fr = e.src.grab(s, limit_t)
        if len(ts) < 4:
            return None
        best = np.full(len(ts), 99)
        for r, off in refs:
            best = np.minimum(best, edges._ref_match(ts, edges.hashes(fr), r, off, ts[0], ts[-1]))
        blk = edges.is_black(fr)
        shared = (best <= edges.HT) & ~blk
        ok = blk | shared
        need = max(2, int(0.5 * len(ts) / max(1e-6, ts[-1] - ts[0])))
        return self._first_shared_run(ts, ok, shared, need, max(2, need // 2))

    @staticmethod
    def _first_shared_run(ts, ok, real, need, need_real):
        """Time of the first frame of the first run of >= need ok frames holding >= need_real frames of real shared picture, or None."""
        run = n_real = 0
        first = None
        for k in range(len(ts)):
            if ok[k]:
                if run == 0:
                    first = k
                    n_real = 0
                run += 1
                n_real += int(real[k])
                if run >= need and n_real >= need_real:
                    return float(ts[first])
            else:
                run = 0
        return None

    def _vis_share(self, e, refs, s, t):
        """Share of frames that match a reference picture (or are black), measured on three chunks of the segment
        (start, middle, end; <= 15 s each, all frames; one chunk when the segment is <= 47 s).  Also returns
        (cut, pre): the start of a >= 3 s non-shared run at the end (post-credit scene inside the music) and the
        end of a >= 3 s non-shared lead-in at the start (song starting over the final story scene), each
        recovered by an extended search when the boundary lies between chunks; (0.0, None, None) when the end
        is unshared and no boundary exists back to 40 % of the segment."""
        if not refs or t - s < 6.0:
            return 0.0, None, None
        L = t - s
        n = 15.0
        if L <= 3 * n + 2:
            chunks = [(s, t)]
        else:
            m = (s + t) / 2
            chunks = [(s + 0.5, s + 0.5 + n), (m - n / 2, m + n / 2), (t - 0.5 - n, t - 0.5)]
        oks, cut, pre, shares = [], None, None, []
        first_ts = None
        pre_search = False
        cut_extended = False
        cut_failed = False
        for ci, (a, b) in enumerate(chunks):
            ts, fr = e.src.grab(a, b)
            if len(ts) < 4:
                continue
            hs = edges.hashes(fr)
            blk = edges.is_black(fr)
            best = np.full(len(ts), 99)
            for r, off in refs:          # all of them, not the first two; an ED can come in picture variants over one song (LOGH S4E10 matches E12, not E09/E11)
                d = edges._ref_match(ts, hs, r, off, ts[0], ts[-1])
                best = np.minimum(best, d)
            real = (best <= edges.HT) & ~blk     # black counts toward the share, but it is no evidence of where shared picture starts or ends
            ok = blk | real
            oks.append(ok)
            shares.append(float(np.mean(ok)))
            fps = max(1.0, len(ts) / max(1e-6, ts[-1] - ts[0]))
            need3 = int(3 * fps)
            if ci == 0:
                first_ts = ts
                lead = int(np.argmax(real)) if real.any() else len(ts)   # frames before the first real shared frame
                if lead >= need3:
                    p = self._first_shared_run(ts, ok, real, max(2, int(round(1.0 * fps))), max(2, int(round(0.25 * fps))))
                    if p is not None:
                        pre = p if p > float(ts[0]) else None    # a run from the first frame: only black before the picture, nothing to trim
                    elif len(chunks) > 1:
                        pre_search = True
            if ci == len(chunks) - 1:
                run = 0
                for k in range(len(ts)):
                    run = run + 1 if not ok[k] else 0
                    if run >= need3:
                        i = k - need3 + 1
                        cut = float(ts[i])
                        if a > s + 1.0 and int(np.sum(real[:i])) < int(0.5 * fps):   # no real shared picture in this chunk before the run: it began earlier, search back to 40 %
                            cut = self._cut_before(e, refs, cut, limit_s=s + 0.4 * L)
                            cut_extended = True
                            cut_failed = cut is None
                        break
        if not oks:
            return 0.0, None, None
        if cut_failed:
            return 0.0, None, None
        share = float(np.mean(np.concatenate(oks)))
        if cut is not None and len(chunks) > 1 and len(shares) > 1 and not cut_extended and min(shares[:-1]) < 0.8:
            ext = self._cut_before(e, refs, cut, limit_s=s + 0.4 * L)   # boundary is before the last chunk
            if ext is None:
                return 0.0, None, None
            cut = ext
        if cut is not None and len(chunks) == 1 and first_ts is not None:
            m = first_ts < cut
            if not m.any() or float(np.mean(oks[0][m])) < 0.8:
                cut = None
        if pre_search:
            pre = self._cut_after(e, refs, s, s + 0.6 * L) if len(shares) > 1 and min(shares[1:]) >= 0.8 else None
            if pre is not None and pre <= s + 0.1:
                pre = None
        elif pre is not None:
            if len(chunks) > 1 and not (len(shares) > 1 and min(shares[1:]) >= 0.8):
                pre = None
            elif len(chunks) == 1 and first_ts is not None:
                m = first_ts >= pre
                if not m.any() or float(np.mean(oks[0][m])) < 0.8:
                    pre = None
        return share, cut, pre


    # ------------------------------------------------------------------ optional: recap
    def find_recaps(self):
        """Recap = head region (before the first intro, max 300 s) whose audio replays ONE other episode."""
        full = {}
        for e in self.eps:
            parts, t = [], 0.0
            while t < e.D - 1e-3:
                parts.append(e.src.audio(t, min(e.D, t + 300.0)))
                t += 300.0
            full[e.name] = np.concatenate(parts)
        for e in self.eps:
            if e.idx == 0:   # a recap can only replay an EARLIER episode; indexing future episodes marks original story
                continue
            intro = [g for g in e.segments if g["type"] == "intro"]
            region = min(intro[0]["start"] if intro else 240.0, 300.0)
            if region < 12.0:
                continue
            idx = recap.Index({p.name: full[p.name] for p in self.eps[:e.idx]})
            r = recap.find_recap(full[e.name][:int(region * SR)], idx, region)
            if r:
                e.segments.append({"type": "recap", "start": round(r["start"], 3), "end": round(r["end"], 3),
                                   "length": round(r["end"] - r["start"], 3), "confidence": 0.7, "method": "audio-landmarks",
                                   "gates": {"sources": r["sources"], "matched_frac": round(r["matched_frac"], 3), "votes_min": r["votes_min"],
                                             "edges": "landmark times (conservative, +-0.5 s)"}})
                e.segments.sort(key=lambda x: x["start"])
            del idx

    # ------------------------------------------------------------------ output
    def result(self):
        out = []
        for e in self.eps:
            out.append({"episode": e.name, "spec": e.spec if not e.spec.startswith("http") else "url", "duration": round(e.D, 3), "file_end": round(e.E, 3),
                        "segments": e.segments, "rejected": e.rejected,
                        "config": {k: v for k, v in self.cfg.items()}})
        return out


def run_season(specs, names, cache, outdir=None, cfg=None):
    t0 = time.time()
    se = Season(specs, names, cache, cfg)
    se.search("head")
    se.search("tail")
    se.refine_and_classify()
    if se.cfg.get("recap"):
        se.find_recaps()
    if se.cfg.get("preview"):
        preview.derive(se)
    res = se.result()
    for r in res:
        r["seconds"] = round(time.time() - t0, 1)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        for r in res:
            json.dump(r, open(os.path.join(outdir, r["episode"] + ".json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return res

