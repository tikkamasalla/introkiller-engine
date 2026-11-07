#!/usr/bin/env python3
"""Rebuild the animated cards in assets/ (hero and feature cards). Standard library only.

    python tools/build_cards.py
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artkit import (Card, MONO, W, amp_music, amp_story, circle, f1, g, mix, rect, text, text_w, wave)  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
X0, X1 = 32, W - 32


def heat_fill(c, v):
    """0..9 shared-episode count to a multi-hue ramp: track, blue, violet, pink, amber."""
    stops = [(0, c.t["track"]), (3, c.c("blue")), (6, c.c("violet")), (8, c.c("pink")), (9, c.c("amber"))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if v <= b:
            return mix(ca, cb, (v - a) / (b - a))
    return stops[-1][1]


def heat_rows(c, rows, x, y, w, rh, gap, mono=None):
    out = []
    for r, row in enumerate(rows):
        digits = row["head"]
        n, i = len(digits), 0
        while i < n:
            j = i
            while j < n and digits[j] == digits[i]:
                j += 1
            v = int(digits[i])
            if v:
                fill = mono if mono else ("url(#heatx)" if v >= 7 else heat_fill(c, v))
                out.append(rect(x + i * w / n, y + r * (rh + gap), (j - i) * w / n + 0.3, rh, fill, 0))
            i = j
    return out


# ------------------------------------------------------------------ hero
def hero(theme, heat):
    c = Card(theme, h=340, dur=8, accent="violet", title="IntroKiller Engine",
             desc="Project title and tagline over real data: twelve episodes of one season, first five minutes each. "
                  "A sweep colours the seconds whose audio the episodes share, and the intro band appears at a different place in each row.",
             glow=[("violet", 0.0, 0.0), ("amber", 1.0, 0.0), ("teal", 0.5, 1.2)])
    t, b = c.t, c.b
    b.append('<linearGradient id="logo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>'
             % (c.c("amber"), c.c("pink")))
    b.append(rect(X0, 34, 64, 64, "url(#logo)", 18, filter="url(#lift)"))
    for i, hgt in enumerate((14, 30, 22, 36, 18)):
        b.append(rect(X0 + 13 + i * 8, 66 - hgt / 2, 5, hgt, "#ffffff", 2.5))
    b.append(text(X0 + 84, 68, "IntroKiller Engine", 38, t["ink"], weight=800, letter_spacing="-0.6"))
    b.append(text(X0 + 86, 94, "Also kills credits, previews and recaps. Never touches your files.", 16, t["ink2"], weight=500))
    chips = [("Audio alignment", "blue"), ("Frame-exact edges", "teal"), ("Preview matching", "green"),
             ("Recap detection", "pink"), ("Credits OCR", "amber"), ("Player exports", "violet")]
    cw = (X1 - X0 - 5 * 8) / 6
    for i, (lab, hue) in enumerate(chips):
        p, w = c.pill(X0 + i * (cw + 8), 120, lab, hue, h=28, size=12, icon="dot", w=cw)
        b += p
    # real heat strip
    hx, hy, hw, rh, gap = X0 + 52, 172, X1 - X0 - 52, 9, 2.6
    rows = heat["rows"]
    for r, row in enumerate(rows):
        b.append(text(X0, hy + r * (rh + gap) + rh - 0.5, row["label"], 9.5, t["mute"], weight=650, family=MONO))
    b.append(rect(hx, hy, hw, len(rows) * (rh + gap) - gap, t["track"], 4, opacity=0.6))
    grey = mix(t["track2"], t["ink2"], 0.18)
    b.append('<linearGradient id="heatx" gradientUnits="userSpaceOnUse" x1="%s" y1="0" x2="%s" y2="0">'
             '<stop offset="0" stop-color="%s"/><stop offset="0.35" stop-color="%s"/><stop offset="0.7" stop-color="%s"/><stop offset="1" stop-color="%s"/>'
             '</linearGradient>' % (f1(hx), f1(hx + hw), c.c("blue"), c.c("violet"), c.c("pink"), c.c("amber")))
    b.append(g(heat_rows(c, rows, hx, hy, hw, rh, gap, mono=grey)))
    reveal = c.anim([(0, "transform:scaleX(0);opacity:1"), (0.3, "transform:scaleX(0);opacity:1"), (4.8, "transform:scaleX(1);opacity:1"),
                     (7.3, "transform:scaleX(1);opacity:1"), (7.8, "transform:scaleX(1);opacity:0"), (8, "transform:scaleX(0);opacity:0")],
                    ease="linear", origin="0% 50%")
    b.append('<clipPath id="rv"><rect x="%s" y="%s" width="%s" height="%s" class="%s"/></clipPath>' % (f1(hx), f1(hy - 4), f1(hw), f1(len(rows) * (rh + gap) + 8), reveal))
    b.append(g(heat_rows(c, rows, hx, hy, hw, rh, gap), clip_path="url(#rv)"))
    head = c.anim([(0, "transform:translateX(0px);opacity:0"), (0.3, "transform:translateX(0px);opacity:1"), (4.8, "transform:translateX(%spx);opacity:1" % f1(hw)),
                   (5.1, "transform:translateX(%spx);opacity:0" % f1(hw)), (8, "transform:translateX(%spx);opacity:0" % f1(hw))], ease="linear")
    b.append(rect(hx - 2, hy - 6, 4, len(rows) * (rh + gap) + 8, c.grad("amber"), 2, class_=head))
    ly = hy + len(rows) * (rh + gap) + 18
    b.append(text(hx, ly, "0:00", 11, t["mute"], weight=600, family=MONO))
    b.append(text(hx + hw / 2, ly, "first five minutes of twelve episodes", 11.5, t["mute"], "middle", 600))
    b.append(text(X1, ly, "5:00", 11, t["mute"], "end", 600, family=MONO))
    c.still = 6.0
    return c.svg()


# ------------------------------------------------------------------ audio alignment
def align(theme):
    c = Card(theme, dur=8, accent="blue", title="Band-limited audio alignment",
             desc="Two episodes' audio, filtered to the low band. A cross-correlation curve is drawn offset by offset until its peak, "
                  "then the second episode slides by that offset and the stretch both carry lights up.",
             glow=[("blue", 0.0, 0.0), ("violet", 1.0, 1.0)])
    t, b = c.t, c.b
    b.append(c.eyebrow("Band-limited audio alignment", "blue"))
    b += c.steps([("Filter", "blue", 0.2, 1.2), ("Correlate", "pink", 1.2, 3.6), ("Align", "violet", 3.6, 7.4)])
    wx, step = 150, 4.6
    n = int((X1 - wx) // step)
    shared = amp_music(30, seed=4)
    rows = [("E03", 92, 30, "blue"), ("E07", 136, 74, "pink")]
    b.append('<clipPath id="wl"><rect x="%s" y="68" width="%s" height="96" rx="8"/></clipPath>' % (wx - 6, f1(X1 - wx + 6)))
    shift = (74 - 30) * step
    bx = wx + 30 * step - 5
    b.append(rect(bx, 70, 30 * step + 8, 90, c.tint("violet", 0.28 if c.mode == "dark" else 0.15), 10, class_=c.show(4.4, 7.3, fade=0.35)))
    for lab, yc, at, hue in rows:
        p, w = c.pill(X0, yc - 13, lab, hue, h=26, size=12.5, icon="dot", w=100)
        b += p
        b.append(rect(wx - 6, yc - 19, X1 - wx + 6, 38, t["track"], 9, opacity=0.35))
        pre = 50 if lab == "E07" else 0
        amps = amp_story(n + pre, 3 if lab == "E03" else 8)
        for i in range(30):
            amps[at + i] = shared[i]
        hl = [0.0] * len(amps)
        for i in range(30):
            hl[at + i] = shared[i]
        neutral = mix(t["track2"], t["ink2"], 0.22 if c.mode == "dark" else 0.14)
        filt = c.show(0.4, 7.3, fade=0.5)
        inner = [wave(wx, yc, amps, neutral, step, 3, 15), wave(wx, yc, amps, c.grad(hue), step, 3, 15, class_=filt, opacity=0.85),
                 wave(wx, yc, hl, c.grad("violet"), step, 3, 15, class_=c.show(4.4, 7.3, fade=0.35))]
        if lab == "E07":
            sl = c.anim([(0, "transform:translateX(0px)"), (3.6, "transform:translateX(0px)"), (4.4, "transform:translateX(-%spx)" % f1(shift)),
                         (7.4, "transform:translateX(-%spx);opacity:1" % f1(shift)), (7.8, "transform:translateX(-%spx);opacity:0" % f1(shift)),
                         (8, "transform:translateX(0px);opacity:0")])
            inner = [g(inner, class_=sl)]
        b.append(g(inner, clip_path="url(#wl)"))
    # correlation chart
    cy0, cy1 = 184, 266
    cx0, cx1 = wx, X1
    b.append(text(X0, cy0 + 20, "correlation", 12.5, t["ink2"], weight=700))
    b.append(text(X0, cy0 + 38, "by time offset", 12, t["mute"], weight=550))
    b.append(rect(cx0 - 6, cy0 - 4, cx1 - cx0 + 6, cy1 - cy0 + 8, t["track"], 10, opacity=0.6))
    r = random.Random(5)
    pts, npts = [], 120
    peak = 0.62
    for i in range(npts + 1):
        u = i / npts
        v = 0.10 + 0.10 * r.random() + 0.08 * abs(((u * 7) % 2) - 1)
        v += 0.78 * max(0.0, 1 - abs(u - peak) / 0.025) ** 1.6
        pts.append((cx0 + u * (cx1 - cx0), cy1 - v * (cy1 - cy0 - 6)))
    d = "M%s %s" % (f1(cx0), f1(cy1)) + "".join("L%s %s" % (f1(x), f1(y)) for x, y in pts) + "L%s %sZ" % (f1(cx1), f1(cy1))
    b.append('<linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s" stop-opacity="0.35"/></linearGradient>'
             % (c.c("pink"), c.c("violet")))
    draw = c.anim([(0, "transform:scaleX(0)"), (1.2, "transform:scaleX(0)"), (3.5, "transform:scaleX(1)"), (7.4, "transform:scaleX(1);opacity:1"),
                   (7.8, "transform:scaleX(1);opacity:0"), (8, "transform:scaleX(0);opacity:0")], ease="linear", origin="0% 50%")
    b.append('<clipPath id="cc"><rect x="%s" y="%s" width="%s" height="%s" class="%s"/></clipPath>' % (f1(cx0), cy0 - 4, f1(cx1 - cx0), cy1 - cy0 + 8, draw))
    b.append('<path d="%s" fill="url(#cg)" clip-path="url(#cc)"/>' % d)
    px = cx0 + peak * (cx1 - cx0)
    py = cy1 - 0.97 * (cy1 - cy0 - 6)
    pk = c.show(3.1, 7.3, fade=0.3)
    b.append(g([circle(px, py, 9, c.c("pink"), opacity=0.35), circle(px, py, 5.5, "#ffffff"), circle(px, py, 3.2, c.c("pink"))], class_=pk))
    p, w = c.pill(px + 16, py - 4, "best offset", "pink", h=26, size=12, solid=True, icon="check")
    b.append(g(p, class_=pk, filter="url(#lift)"))
    c.still = 5.5
    return c.svg()


# ------------------------------------------------------------------ frame-exact edges
def edges(theme):
    c = Card(theme, dur=8, accent="teal", title="Frame-exact edge snapping",
             desc="A strip of frames around the start of an intro. The edge found from the audio walks back frame by frame across a frame that "
                  "matches other episodes and a black frame, stops at the first story frame, and settles where the black ends.",
             glow=[("teal", 0.0, 1.0), ("coral", 1.0, 0.0)])
    t, b = c.t, c.b
    b.append(c.eyebrow("Frame-exact edge snapping", "teal"))
    b += c.steps([("Audio edge", "blue", 0.2, 1.4), ("Walk frames", "teal", 1.4, 4.4), ("Snap", "violet", 4.4, 7.4)])
    nf = 14
    fx0 = X0
    fw = (X1 - X0 - (nf - 1) * 6) / nf
    fy, fh = 98, 70
    kinds = ["story"] * 6 + ["black"] + ["intro"] * 7
    b.append(rect(X0 - 8, fy - 14, X1 - X0 + 16, fh + 28, "#151a2c" if c.mode == "dark" else "#232a40", 12))
    for i in range(nf + 1):
        hx = fx0 + i * (fw + 6) - 6 + fw / 2
        b.append(rect(hx - 3, fy - 9, 6, 4, "#ffffff", 1.5, opacity=0.25))
        b.append(rect(hx - 3, fy + fh + 5, 6, 4, "#ffffff", 1.5, opacity=0.25))
    for i, k in enumerate(kinds):
        x = fx0 + i * (fw + 6)
        if k == "story":
            gid = "st%d" % i
            b.append('<linearGradient id="%s" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>'
                     % (gid, mix(c.c("amber"), "#ffffff", 0.2), mix(c.c("coral"), "#000000", 0.2 + 0.03 * i)))
            b.append(rect(x, fy, fw, fh, "url(#%s)" % gid, 6))
            b.append(circle(x + fw * (0.3 + 0.07 * i), fy + fh * 0.62, fh * 0.2, mix(c.c("coral"), "#000000", 0.45), opacity=0.8))
        elif k == "black":
            b.append(rect(x, fy, fw, fh, "#05070d", 6))
        else:
            b.append(rect(x, fy, fw, fh, "url(#g-violet)", 6))
            b.append(rect(x + fw * 0.18, fy + fh * 0.42, fw * 0.64, 8, "#ffffff", 4, opacity=0.85))
            b.append(rect(x + fw * 0.3, fy + fh * 0.6, fw * 0.4, 6, "#ffffff", 3, opacity=0.55))
    # verdict chips under frames: walk from frame 9 back to frame 5
    walk = [(9, 1.6, "ok"), (8, 2.2, "ok"), (7, 2.8, "ok"), (6, 3.4, "ok"), (5, 4.0, "bad")]
    labels = {9: "match", 8: "match", 7: "match", 6: "black", 5: "story"}
    for idx, t0, kind in walk:
        x = fx0 + idx * (fw + 6)
        hue = "teal" if kind == "ok" else "coral"
        p, w = c.pill(x + fw / 2, fy + fh + 18, labels[idx], hue, h=24, size=11, solid=True, anchor="middle", w=fw + 4)
        b.append(g(p, class_=c.show(t0, 7.3, fade=0.25)))
    # edge marker
    def mx(idx):
        return fx0 + idx * (fw + 6) - 3
    start = mx(10)
    fr = [(0, "transform:translateX(0px);opacity:0"), (0.4, "transform:translateX(0px);opacity:1"), (1.5, "transform:translateX(0px)")]
    for k, (idx, t0, kind) in enumerate(walk[:-1]):
        fr.append((t0 + 0.35, "transform:translateX(%spx)" % f1(mx(idx) - start)))
    fr.append((4.0, "transform:translateX(%spx)" % f1(mx(6) - start)))
    fr.append((4.25, "transform:translateX(%spx)" % f1(mx(5) - start + 14)))
    fr.append((4.6, "transform:translateX(%spx)" % f1(mx(6) - start)))
    fr.append((5.1, "transform:translateX(%spx)" % f1(mx(7) - start)))
    fr += [(7.3, "transform:translateX(%spx);opacity:1" % f1(mx(7) - start)), (7.7, "transform:translateX(%spx);opacity:0" % f1(mx(7) - start)),
           (8, "transform:translateX(0px);opacity:0")]
    mk = c.anim(fr)
    b.append(g([rect(start - 2, fy - 22, 10, fh + 44, c.grad("blue"), 5, filter="url(#lift)"),
                circle(start + 3, fy - 24, 9, c.c("blue")), '<path d="M%s %sl-6 6 6 6z" fill="#ffffff"/>' % (f1(start + 5), f1(fy - 30))], class_=mk))
    # captions
    p, w = c.pill(X0, 236, "audio edge", "blue", h=28, size=12.5, icon="dot")
    b.append(g(p, class_=c.show(0.4, 1.6, fade=0.25)))
    p, w = c.pill(X0, 236, "walks out while frames match 2 other episodes or are black", "teal", h=28, size=12.5, icon="dot")
    b.append(g(p, class_=c.show(1.6, 4.4, fade=0.25)))
    p, w = c.pill(X0, 236, "black is trimmed, the edge lands on a real transition", "violet", h=28, size=12.5, solid=True, icon="check")
    b.append(g(p, class_=c.show(4.5, 7.3, fade=0.25), filter="url(#lift)"))
    c.still = 5.2
    return c.svg()


# ------------------------------------------------------------------ previews
def previews(theme):
    c = Card(theme, dur=8, accent="green", title="Preview shape matching",
             desc="The last minutes of three episodes, lined up at the end of the file. Their previews have new footage but the same length "
                  "and the same title card, so the preview is reported, as a button only.",
             glow=[("green", 1.0, 0.0), ("amber", 0.0, 1.0)])
    t, b = c.t, c.b
    b.append(c.eyebrow("Preview shape matching", "green"))
    b += c.steps([("Measure", "amber", 0.2, 2.2), ("Match card", "pink", 2.2, 4.2), ("Button only", "green", 4.2, 7.4)])
    lx = 150
    span = X1 - lx
    rows = [("E04", 0.61, 0.835, 0.0), ("E05", 0.58, 0.832, 1.0), ("E06", 0.64, 0.838, 2.0)]
    for i, (lab, cs, ps, seed) in enumerate(rows):
        y = 78 + i * 44
        p, w = c.pill(X0, y + 2, lab, "blue", h=28, size=12.5, icon="dot", w=100)
        b += p
        b.append(rect(lx, y, span, 32, t["track"], 9))
        b.append(rect(lx + span * cs, y, span * (ps - cs), 32, c.grad("amber"), 0))
        b.append(text(lx + span * (cs + ps) / 2, y + 21, "credits", 12, t["on_hue"], "middle", 750))
        b.append(rect(lx + span * ps, y, span * (1 - ps), 32, c.grad("green"), 0))
        b.append(rect(lx + span * ps, y, 5, 32, c.grad("pink"), 0, class_=c.show(2.4 + 0.25 * i, 7.3, fade=0.25)))
        # new footage in each preview: different stripes
        r = random.Random(int(seed) + 4)
        for k in range(4):
            sx = lx + span * ps + 10 + k * 26 + r.random() * 6
            b.append(rect(sx, y + 9, 16, 14, "#ffffff", 3, opacity=0.35))
    b.append(rect(lx - 1, 76, span + 2, 36 + 88, "none", 10, stroke=t["edge"], stroke_width=0))
    # length bracket
    br_x = lx + span * 0.835
    br = c.show(0.6, 7.3, fade=0.3)
    b.append(g([rect(br_x, 214, X1 - br_x, 8, c.grad("green"), 4), rect(br_x, 206, 4, 22, c.grad("green"), 2), rect(X1 - 4, 206, 4, 22, c.grad("green"), 2)], class_=br))
    px = X0
    for lab, hue, t0, icon in (("lengths agree within 1.5 s", "amber", 1.2, "check"), ("same card or jingle at an edge", "pink", 2.8, "check"),
                               ("reported as a Skip preview button only", "green", 4.4, None)):
        p, w = c.pill(px, 244, lab, hue, h=28, size=12.5, solid=True, icon=icon)
        b.append(g(p, class_=c.show(t0, 7.3, fade=0.3, extra_in="transform:translateY(0px)", extra_out="transform:translateY(6px)"), filter="url(#lift)"))
        px += w + 10
    for i in range(3):
        b.append(text(lx + 14, 78 + i * 44 + 21, "story", 12, t["mute"], weight=650))
    b.append(text(br_x - 10, 224, "end of file, lined up", 11.5, t["mute"], "end", 650))
    c.still = 5.5
    return c.svg()


# ------------------------------------------------------------------ recaps
def recaps(theme):
    c = Card(theme, dur=8, accent="pink", title="Recap replay matching",
             desc="Short pieces from episodes 1, 2 and 3 are found again at the start of episode 4. "
                  "Together they form a run of replayed audio, which is reported as the recap.",
             glow=[("pink", 0.0, 0.0), ("blue", 1.0, 1.0)])
    t, b = c.t, c.b
    b.append(c.eyebrow("Recap replay matching", "pink"))
    b += c.steps([("Earlier episodes", "blue", 0.2, 1.2), ("Find replays", "teal", 1.2, 4.2), ("Mark recap", "pink", 4.2, 7.4)])
    lx = 150
    span = X1 - lx
    src = [("E01", "blue", [0.22, 0.70]), ("E02", "teal", [0.40]), ("E03", "amber", [0.15, 0.55])]
    for i, (lab, hue, spots) in enumerate(src):
        y = 74 + i * 34
        p, w = c.pill(X0, y, lab, hue, h=24, size=12, icon="dot", w=100)
        b += p
        b.append(rect(lx, y + 3, span, 18, t["track"], 9))
    # E04 head with buckets
    ey = 196
    p, w = c.pill(X0, ey + 4, "E04 start", "pink", h=28, size=12.5, icon="dot", w=100)
    b += p
    b.append(rect(lx, ey, span, 36, t["track"], 10))
    bw = 34
    order = [(0, 0), (2, 0), (1, 0), (0, 1), (2, 1)]  # (source row, spot)
    slot_x0 = lx + 16
    for k, (row, spot) in enumerate(order):
        lab, hue, spots = src[row]
        sx = lx + span * spots[spot]
        sy = 74 + row * 34 + 3
        tx = slot_x0 + k * (bw + 4)
        t0 = 1.3 + 0.5 * k
        b.append(rect(sx, sy, bw, 18, c.grad(hue), 9, class_=c.show(0.3 + 0.1 * k, 7.3, fade=0.3)))
        mv = c.anim([(0, "transform:translate(0px,0px);opacity:0"), (t0, "transform:translate(0px,0px);opacity:0"),
                     (t0 + 0.1, "transform:translate(0px,0px);opacity:1"), (t0 + 0.7, "transform:translate(%spx,%spx);opacity:1" % (f1(tx - sx), f1(ey + 9 - sy))),
                     (7.3, "transform:translate(%spx,%spx);opacity:1" % (f1(tx - sx), f1(ey + 9 - sy))),
                     (7.7, "transform:translate(%spx,%spx);opacity:0" % (f1(tx - sx), f1(ey + 9 - sy))), (8, "transform:translate(0px,0px);opacity:0")])
        b.append(g([rect(sx, sy, bw, 18, c.grad(hue), 9)], class_=mv, filter="url(#lift)"))
    rw = 5 * (bw + 4) + 24
    rc = c.show(4.3, 7.3, fade=0.3)
    b.append(rect(lx + 4, ey - 6, rw, 48, "none", 12, stroke=c.c("pink"), stroke_width=3.5, class_=rc))
    p, w = c.pill(lx + 4 + rw / 2, ey + 50, "Recap", "pink", h=26, size=12.5, solid=True, icon="check", anchor="middle")
    b.append(g(p, class_=rc, filter="url(#lift)"))
    ix = lx + 4 + rw + 18
    b.append(rect(ix, ey + 6, 150, 24, c.grad("violet"), 8, opacity=0.9))
    b.append(text(ix + 75, ey + 22.5, "intro", 12, t["on_hue"], "middle", 750))
    b.append(text(X1 - 8, ey + 23, "story", 12.5, t["mute"], "end", 650))
    p, w = c.pill(X1, 32 + 222, 'or a "Previously on" card, with --ocr', "amber", h=26, size=12, anchor="end")
    b += p
    c.still = 5.5
    return c.svg()


# ------------------------------------------------------------------ credits OCR
def ocr(theme):
    c = Card(theme, dur=8, accent="amber", title="On-screen credits reader",
             desc="Credits roll on a dark frame and each text line is boxed as it is read. On the timeline below, the text run is kept "
                  "because it reaches the end of the file, and a run that stops early is refused.",
             glow=[("amber", 0.0, 0.0), ("teal", 1.0, 1.0)])
    t, b = c.t, c.b
    b.append(c.eyebrow("On-screen credits reader", "amber"))
    b += c.steps([("Read text", "amber", 0.2, 3.0), ("Reach the end", "teal", 3.0, 7.4)])
    fx, fy, fw, fh = X0, 70, 360, 206
    b.append(g([rect(fx, fy, fw, fh, "#0a0d18", 14)], filter="url(#lift)"))
    b.append('<clipPath id="fr"><rect x="%s" y="%s" width="%s" height="%s" rx="14"/></clipPath>' % (fx, fy, fw, fh))
    r = random.Random(9)
    lines, y = [], 0
    while y < 300:
        w1 = 60 + r.random() * 70
        w2 = 70 + r.random() * 90
        lines.append((y, w1, w2))
        y += 30
    period = y
    body = []
    for rep in (0, 1):
        for (ly, w1, w2) in lines:
            yy = fy + 24 + ly + rep * period
            cx = fx + fw / 2
            body.append(rect(cx - 8 - w1, yy, w1, 9, "#9aa3c7", 4.5))
            body.append(rect(cx + 8, yy, w2, 9, "#ffffff", 4.5))
            body.append(rect(cx - 14 - w1, yy - 6, w1 + w2 + 28, 21, mix(c.c("amber"), "#0a0d18", 0.55), 6, opacity=0.55))
    scroll = c.anim([(0, "transform:translateY(0px)"), (8, "transform:translateY(-%spx)" % f1(period))], ease="linear")
    b.append(g([g(body, class_=scroll)], clip_path="url(#fr)"))
    b.append(rect(fx, fy, fw, 32, "#0a0d18", 0, opacity=0.96, clip_path="url(#fr)"))
    b.append(text(fx + 14, fy + 20, "keyframes from the last 450 s", 11.5, "#c9cfe6", weight=650))
    # timeline right
    tx0, tx1 = 420, X1
    span = tx1 - tx0
    rows = [("kept", "teal", 0.48, 1.0, 92, "text runs to the end of the file"),
            ("refused", "coral", 0.30, 0.74, 192, "text stops before the end")]
    for lab, hue, a, z, y, note in rows:
        b.append(text(tx0, y - 8, note, 12.5, t["ink2"], weight=650))
        b.append(rect(tx0, y, span, 30, t["track"], 9))
        grow = c.anim([(0, "transform:scaleX(0)"), (0.4, "transform:scaleX(0)"), (3.0, "transform:scaleX(1)"), (7.3, "transform:scaleX(1);opacity:1"),
                       (7.7, "transform:scaleX(1);opacity:0"), (8, "transform:scaleX(0);opacity:0")], ease="linear", origin="0% 50%")
        b.append(rect(tx0 + span * a, y, span * (z - a), 30, c.grad("amber"), 9, class_=grow))
        b.append(rect(tx1 - 6, y - 4, 6, 38, t["ink2"], 3))
        p, w = c.pill(tx0 + span * a + 8, y + 3, lab, hue, h=24, size=12, solid=True, icon="check" if hue == "teal" else "cross")
        b.append(g(p, class_=c.show(3.2, 7.3, fade=0.3), filter="url(#lift)"))
    b.append(text(tx1, 160, "end of file", 11.5, t["mute"], "end", 650))
    c.still = 5.0
    return c.svg()


# ------------------------------------------------------------------ exports
def exports(theme):
    c = Card(theme, dur=8, accent="violet", title="Player-ready exports",
             desc="The engine writes times.json, then exports an EDL file for Kodi, an EDL for mpv and a chapters file for ffmpeg. "
                  "Intro and credits go into every file. The preview stays out of the two skip lists.",
             glow=[("violet", 0.0, 0.0), ("green", 1.0, 1.0)])
    t, b = c.t, c.b
    b.append(c.eyebrow("Player-ready exports", "violet"))
    b += c.steps([("Write times", "violet", 0.2, 1.6), ("Export", "blue", 1.6, 7.4)])
    # source doc
    dx, dy, dw, dh = X0, 72, 230, 202
    b.append(g([rect(dx, dy, dw, dh, t["panel"] if c.mode == "light" else t["panel2"], 14)], filter="url(#lift)"))
    b.append(rect(dx, dy, dw, 34, c.grad("violet"), 14))
    b.append(rect(dx, dy + 20, dw, 14, c.grad("violet"), 0))
    b.append(text(dx + 16, dy + 22, "times.json", 13.5, "#ffffff", weight=750, family=MONO))
    code = [("intro", "violet", 0.62), ("credits", "amber", 0.70), ("preview", "green", 0.58)]
    for i, (k, hue, wfrac) in enumerate(code):
        y = dy + 56 + i * 46
        b.append(rect(dx + 16, y, 58, 22, c.grad(hue), 7))
        b.append(text(dx + 45, y + 15, k, 11.5, t["on_hue"], "middle", 750))
        b.append(rect(dx + 82, y + 2, (dw - 100) * wfrac, 8, t["track2"], 4))
        b.append(rect(dx + 82, y + 14, (dw - 100) * wfrac * 0.6, 6, t["track2"], 3))
    # targets
    tw = 236
    tx = X1 - tw
    targets = [("ep.edl", "Kodi skips it", "blue", False), ("ep.mpv.edl", "mpv plays without it", "pink", False), ("ep.ffmeta", "chapters, via ffmpeg", "teal", True)]
    for i, (fn, note, hue, has_prev) in enumerate(targets):
        y = 72 + i * 70
        b.append(g([rect(tx, y, tw, 58, t["panel"] if c.mode == "light" else t["panel2"], 14)], filter="url(#lift)"))
        b.append(rect(tx + 10, y + 10, 38, 38, c.grad(hue), 10))
        b.append(rect(tx + 20, y + 20, 18, 3.5, "#ffffff", 1.75))
        b.append(rect(tx + 20, y + 27, 18, 3.5, "#ffffff", 1.75))
        b.append(rect(tx + 20, y + 34, 11, 3.5, "#ffffff", 1.75))
        b.append(text(tx + 60, y + 26, fn, 13.5, t["ink"], weight=750, family=MONO))
        b.append(text(tx + 60, y + 44, note, 12, t["mute"], weight=600))
        # tube
        y0 = dy + dh / 2
        y1 = y + 29
        x0 = dx + dw + 8
        x1 = tx - 8
        b.append('<path d="M%s %sC%s %s %s %s %s %s" fill="none" stroke="%s" stroke-width="12" stroke-linecap="round" opacity="0.8"/>'
                 % (f1(x0), f1(y0), f1((x0 + x1) / 2), f1(y0), f1((x0 + x1) / 2), f1(y1), f1(x1), f1(y1), t["track"]))
        pid = "tube%d" % i
        b.append('<path id="%s" d="M%s %sC%s %s %s %s %s %s" fill="none"/>' % (pid, f1(x0), f1(y0), f1((x0 + x1) / 2), f1(y0), f1((x0 + x1) / 2), f1(y1), f1(x1), f1(y1)))
        segs = [("violet", 1.7), ("amber", 2.3)] + ([("green", 2.9)] if has_prev else [])
        for hue2, t0 in segs:
            t0 += 0.25 * i
            b.append('<circle r="8" fill="%s" opacity="0" filter="url(#lift)"><animateMotion dur="8s" repeatCount="indefinite" keyPoints="0;0;1;1" '
                     'keyTimes="0;%s;%s;1" calcMode="linear"><mpath href="#%s"/></animateMotion>'
                     '<animate attributeName="opacity" dur="8s" repeatCount="indefinite" values="0;0;1;1;0;0" keyTimes="0;%s;%s;%s;%s;1"/></circle>'
                     % (c.c(hue2), f1(t0 / 8), f1((t0 + 1.2) / 8), pid, f1(t0 / 8), f1((t0 + 0.1) / 8), f1((t0 + 1.1) / 8), f1((t0 + 1.3) / 8)))
        for k, (hue2, t0) in enumerate([("violet", 1.7), ("amber", 2.3), ("green", 2.9)]):
            cx = tx + tw - 58 + k * 22
            b.append(circle(cx, y + 29, 7.5, t["track2"] if c.mode == "dark" else t["track"]))
            if hue2 == "green" and not has_prev:
                b.append(rect(cx - 4.5, y + 27.5, 9, 3, t["mute"], 1.5))
                continue
            b.append(circle(cx, y + 29, 7.5, c.grad(hue2), class_=c.show(t0 + 0.25 * i + 1.1, 7.3, fade=0.2)))
    lg = [("intro", "violet"), ("credits", "amber"), ("preview", "green")]
    lxp = tx
    b.append(text(X1, 290, "previews stay out of both skip lists", 12, t["mute"], "end", 650))
    c.still = 6.0
    return c.svg()


CARDS = {"align": align, "edges": edges, "previews": previews, "recaps": recaps, "ocr": ocr, "exports": exports}


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets"
    out.mkdir(exist_ok=True)
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data"
    heat = json.loads((data / "heat_logh_s3.json").read_text(encoding="utf-8"))
    for theme in ("light", "dark"):
        items = {"hero": hero(theme, heat)}
        items.update({k: f(theme) for k, f in CARDS.items()})
        for name, s in items.items():
            (out / ("%s-%s.svg" % (name, theme))).write_text(s, encoding="utf-8", newline="\n")
            print("%-10s %-5s %5.1f KB" % (name, theme, len(s.encode()) / 1024))


if __name__ == "__main__":
    main()
