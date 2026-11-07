"""Scene pages for introkiller-engine. python scenes.py pages"""
import json
import math
import random
import sys
from pathlib import Path

from scenekit import (MONO, OUT, Scene, env_path, envelope, esc, still, svg)

DATA = Path(__file__).resolve().parents[2] / "data"


def winbar(title, right=""):
    return ('<div style="position:absolute;left:0;right:0;top:0;height:30px;border-bottom:1px solid rgba(255,255,255,.06);display:flex;align-items:center;padding:0 14px;gap:10px">'
            '<span class="mono" style="font-size:11px;color:#c9cdd2">%s</span><span class="mono" style="font-size:10.5px;color:#6b7079;margin-left:auto">%s</span></div>' % (title, right))


# ------------------------------------------------------------------ hero (real data: 12 episodes, first 5 minutes)
def hero(data=DATA):
    heat = json.loads((data / "heat_logh_s3.json").read_text(encoding="utf-8"))
    sc = Scene(0, "", "cyan", dur=7.0)
    b = sc.body
    b.append('<div style="position:absolute;left:0;top:34px;width:300px">'
             '<div class="lbl" style="color:var(--acc)">IntroKiller Engine</div>'
             '<div style="font-size:30px;line-height:1.12;font-weight:650;letter-spacing:-.02em;margin-top:14px;color:#f5f6f8">Finds the intro in every episode.</div>'
             '<div style="font-size:13.5px;line-height:1.55;color:#9aa0a8;margin-top:14px">Also credits, previews and recaps. It compares the audio of a season, writes the times, and never touches your files.</div>'
             '<div class="mono" style="font-size:11px;color:#6f757e;margin-top:22px;letter-spacing:.04em">PYTHON  ·  FFMPEG  ·  OFFLINE</div></div>')
    gx, gw, gy = 340, 476, 30
    rows = heat["rows"]
    rh = 21
    body = []
    for i, row in enumerate(rows):
        y = i * rh
        body.append('<text x="0" y="%d" font-family="JetBrains Mono" font-size="10" fill="#6b7079">%s</text>' % (y + 12, row["label"]))
        body.append('<rect x="40" y="%d" width="%d" height="9" fill="rgba(255,255,255,.06)"/>' % (y + 4, gw - 40))
        digits = row["head"]
        n = len(digits)
        j = 0
        while j < n:
            k = j
            while k < n and (digits[k] >= "7") == (digits[j] >= "7"):
                k += 1
            if digits[j] >= "7":
                body.append('<rect x="%.1f" y="%d" width="%.1f" height="9" fill="var(--acc)"/>' % (40 + (gw - 40) * j / n, y + 4, (gw - 40) * (k - j) / n))
            j = k
    lit = sc.k([(0, "clip-path:inset(0 100% 0 0)"), (0.3, "clip-path:inset(0 100% 0 0)"), (3.6, "clip-path:inset(0 0% 0 0)"), (6.5, "clip-path:inset(0 0% 0 0);opacity:1"),
                (6.9, "opacity:0"), (7, "clip-path:inset(0 100% 0 0);opacity:0")], ease="linear")
    grey = "".join(x for x in body if 'var(--acc)' not in x)
    lit_part = "".join(x for x in body if 'var(--acc)' in x)
    b.append(svg(gw, len(rows) * rh, grey + '<g class="%s" style="filter:drop-shadow(0 0 6px rgba(34,184,224,.6))">%s</g>' % (lit, lit_part), style="left:%dpx;top:%dpx" % (gx, gy)))
    head = sc.k([(0, "transform:translateX(0);opacity:0"), (0.3, "transform:translateX(0);opacity:1"), (3.6, "transform:translateX(%dpx);opacity:1" % (gw - 40)),
                 (3.8, "transform:translateX(%dpx);opacity:0" % (gw - 40)), (7, "opacity:0")], ease="linear")
    b.append('<div class="%s" style="position:absolute;left:%dpx;top:%dpx;width:1px;height:%dpx;background:#fff;box-shadow:0 0 10px #fff"></div>' % (head, gx + 40, gy - 4, len(rows) * rh + 4))
    b.append('<div class="mono" style="position:absolute;left:%dpx;top:%dpx;font-size:10px;color:#5d636c">00:00</div>' % (gx + 40, gy + len(rows) * rh + 6))
    b.append('<div class="mono" style="position:absolute;left:%dpx;top:%dpx;font-size:10px;color:#5d636c;transform:translateX(-100%%)">05:00</div>' % (gx + gw, gy + len(rows) * rh + 6))
    b.append('<div class="mono %s" style="position:absolute;left:%dpx;top:%dpx;font-size:10.5px;color:var(--acc)">shared audio: the intro moves, the engine follows it</div>'
             % (sc.fade(3.6, 6.6, 0.4), gx + 40, gy + len(rows) * rh + 24))
    return sc


# ------------------------------------------------------------------ audio alignment
def align():
    sc = Scene(1, "Band-limited audio alignment", "teal", dur=8.0)
    sc.cap("<b>1</b>  keep 80 Hz to 1.5 kHz", 0.15, 1.8)
    sc.cap("<b>2</b>  FFT cross-correlation finds the offset", 1.8, 4.2)
    sc.cap("<b>3</b>  shared stretch kept, 4 s or longer", 4.2, 7.5)
    b = sc.body
    lx, lw = 64, 560
    n = 260
    step = lw / n
    pre = 60
    m_from, m_len, shift = 70, 60, 70
    # band-pass panel
    bp = ['<div class="win" style="left:648px;top:0;width:168px;height:132px">', winbar("band-pass")]
    pts = []
    for i in range(61):
        f = i / 60
        v = 0.3 + 0.5 * math.exp(-((f - 0.35) / 0.25) ** 2) + 0.1 * math.sin(i * 1.7)
        pts.append("%.1f %.1f" % (12 + f * 144, 112 - v * 60))
    body = '<path d="M%s" fill="none" stroke="#5d636c" stroke-width="1.2"/>' % "L".join(pts)
    body += '<rect x="%.1f" y="40" width="%.1f" height="76" fill="rgba(46,196,182,.12)" class="%s"/>' % (12 + 0.08 * 144, 0.42 * 144, sc.fade(0.3, 7.5, 0.4))
    body += '<path d="M%.1f 40V116M%.1f 40V116" stroke="var(--acc)" stroke-width="1" class="%s"/>' % (12 + 0.08 * 144, 12 + 0.5 * 144, sc.fade(0.3, 7.5, 0.4))
    bp.append(svg(168, 132, body, style="left:0;top:0"))
    bp.append('<div class="mono" style="position:absolute;left:12px;top:116px;font-size:9.5px;color:#6b7079">80 Hz</div><div class="mono" style="position:absolute;left:76px;top:116px;font-size:9.5px;color:#6b7079">1.5 kHz</div></div>')
    b.append("".join(bp))
    lanes = [("E03", 40, 4), ("E07", 110, 9)]
    for lab, yc, seed in lanes:
        b.append('<div class="mono" style="position:absolute;left:0;top:%dpx;font-size:12px;color:#e8eaed">%s</div>' % (yc - 8, lab))
        mf = m_from + (shift if lab == "E07" else 0)
        amps = envelope(n + 2 * pre + shift, seed, mf + pre, m_len)
        d = env_path(-pre * step, 30, step, amps, 26)
        clip = '<clipPath id="c%s"><rect x="%.1f" y="0" width="%.1f" height="60"/></clipPath>' % (lab, (mf) * step, m_len * step)
        layer = '<path d="%s" fill="#4a5059"/><g clip-path="url(#c%s)"><path d="%s" fill="var(--acc)" class="%s"/></g>%s' % (d, lab, d, sc.fade(4.2, 7.5, 0.35), clip)
        if lab == "E07":
            mv = sc.k([(0, "transform:translateX(0)"), (3.4, "transform:translateX(0)"), (4.2, "transform:translateX(%.1fpx)" % (-shift * step)),
                       (7.5, "transform:translateX(%.1fpx);opacity:1" % (-shift * step)), (7.9, "transform:translateX(%.1fpx);opacity:0" % (-shift * step)),
                       (8, "transform:translateX(0);opacity:0")])
            layer = '<g class="%s">%s</g>' % (mv, layer)
        b.append(svg(lw, 60, '<clipPath id="l%s"><rect width="%d" height="60"/></clipPath><g clip-path="url(#l%s)">%s</g>' % (lab, lw, lab, layer), style="left:%dpx;top:%dpx" % (lx, yc - 30)))
    # correlation plot
    cy, ch = 172, 140
    b.append('<div class="lbl" style="position:absolute;left:0;top:%dpx">Cross-correlation by offset</div>' % (cy - 2))
    r = random.Random(5)
    peak = 0.5 + shift / 400
    pts = []
    for i in range(301):
        u = i / 300
        v = 0.12 + 0.12 * r.random() + 0.06 * math.sin(u * 37)
        v += 0.8 * math.exp(-((u - peak) / 0.01) ** 2) + 0.18 * math.exp(-((u - peak + 0.12) / 0.01) ** 2)
        pts.append((u * 752, ch - 10 - v * (ch - 34)))
    d = "M" + "L".join("%.1f %.1f" % p for p in pts)
    area = d + "L752 %dL0 %dZ" % (ch - 10, ch - 10)
    grid = "".join('<path d="M%.1f 14V%d" stroke="rgba(255,255,255,.05)"/>' % (752 * k / 8, ch - 10) for k in range(9))
    draw = sc.k([(0, "clip-path:inset(0 100% 0 0)"), (1.8, "clip-path:inset(0 100% 0 0)"), (3.4, "clip-path:inset(0 0% 0 0)"), (7.5, "clip-path:inset(0 0% 0 0);opacity:1"),
                 (7.9, "opacity:0"), (8, "clip-path:inset(0 100% 0 0);opacity:0")], ease="linear")
    body = grid + '<path d="M0 %dH752" stroke="rgba(255,255,255,.12)"/>' % (ch - 10)
    body += '<g class="%s"><path d="%s" fill="rgba(46,196,182,.10)"/><path d="%s" fill="none" stroke="var(--acc)" stroke-width="1.4"/></g>' % (draw, area, d)
    px = peak * 752
    pk = sc.fade(3.4, 7.5, 0.3)
    body += '<g class="%s"><path d="M%.1f 14V%d" stroke="var(--acc)" stroke-dasharray="2 3"/><circle cx="%.1f" cy="%.1f" r="4" fill="var(--acc)"/></g>' % (pk, px, ch - 10, px, ch - 10 - 0.98 * (ch - 34) - 2)
    b.append(svg(752, ch, body, style="left:64px;top:%dpx" % (cy + 6)))
    b.append('<div class="mono %s" style="position:absolute;left:%.1fpx;top:%dpx;font-size:10.5px;color:var(--acc)">best offset  ·  corr 0.98</div>' % (pk, 64 + px + 10, cy + 16))
    b.append('<div class="mono" style="position:absolute;left:64px;top:%dpx;font-size:9.5px;color:#5d636c">-150 s</div><div class="mono" style="position:absolute;right:0;top:%dpx;font-size:9.5px;color:#5d636c">+150 s</div>' % (cy + ch + 8, cy + ch + 8))
    return sc


# ------------------------------------------------------------------ edges
def edges():
    sc = Scene(2, "Frame-exact edge snapping", "amber", dur=8.0)
    sc.cap("<b>1</b>  audio edge, close but not exact", 0.15, 1.5)
    sc.cap("<b>2</b>  walk while frames match 2 episodes or are black", 1.5, 4.6)
    sc.cap("<b>3</b>  black trimmed  ·  edge on a real transition", 4.6, 7.5)
    b = sc.body
    nf = 9
    fw, fh, gap = 84, 47, 6
    x0 = 6
    y0 = 70
    kinds = ["story", "story", "story", "black", "title", "title", "title", "title", "title"]
    b.append('<div style="position:absolute;left:0;right:0;top:%dpx;height:%dpx;background:#0b0c0e;border-radius:3px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.05)"></div>' % (y0 - 22, fh + 44))
    for k in range(40):
        b.append('<div style="position:absolute;left:%dpx;top:%dpx;width:8px;height:5px;border-radius:1px;background:rgba(255,255,255,.12)"></div>' % (12 + k * 20, y0 - 14))
        b.append('<div style="position:absolute;left:%dpx;top:%dpx;width:8px;height:5px;border-radius:1px;background:rgba(255,255,255,.12)"></div>' % (12 + k * 20, y0 + fh + 9))
    for i, kd in enumerate(kinds):
        x = x0 + i * (fw + gap)
        if kd == "story":
            b.append(still(x, y0, fw, fh, 0, extra_style="filter:brightness(%.2f)" % (0.9 + 0.04 * i)))
        elif kd == "black":
            b.append('<div class="still" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx;background:#030303"></div>' % (x, y0, fw, fh))
        else:
            b.append(still(x, y0, fw, fh, 1, title=True))
        b.append('<div class="mono" style="position:absolute;left:%dpx;top:%dpx;font-size:9.5px;color:#5d636c">%04d</div>' % (x, y0 + fh + 20, 2161 + i))
    walk = [(6, 1.7, "match"), (5, 2.3, "match"), (4, 2.9, "match"), (3, 3.5, "black"), (2, 4.1, "story")]
    for idx, t0, lab in walk:
        x = x0 + idx * (fw + gap)
        col = "#e5534b" if lab == "story" else "var(--acc)"
        b.append('<div class="mono %s" style="position:absolute;left:%dpx;width:%dpx;top:%dpx;font-size:10.5px;color:%s;text-align:center;border-top:2px solid %s;padding-top:6px">%s</div>'
                 % (sc.fade(t0, 7.5, 0.25), x, fw, y0 + fh + 40, col, col, lab))
    mx = lambda idx: x0 + idx * (fw + gap) - gap / 2
    start = mx(7)
    fr = [(0, "transform:translateX(0);opacity:0"), (0.3, "transform:translateX(0);opacity:1"), (1.6, "transform:translateX(0)")]
    for idx, t0, lab in walk[:-1]:
        fr.append((t0 + 0.35, "transform:translateX(%.1fpx)" % (mx(idx) - start)))
    fr += [(4.1, "transform:translateX(%.1fpx)" % (mx(3) - start)), (4.35, "transform:translateX(%.1fpx)" % (mx(3) - start - 14)), (4.7, "transform:translateX(%.1fpx)" % (mx(3) - start)),
           (5.3, "transform:translateX(%.1fpx)" % (mx(4) - start)), (7.5, "transform:translateX(%.1fpx);opacity:1" % (mx(4) - start)),
           (7.9, "transform:translateX(%.1fpx);opacity:0" % (mx(4) - start)), (8, "transform:translateX(0);opacity:0")]
    b.append('<div class="%s" style="position:absolute;left:%.1fpx;top:%dpx;width:2px;height:%dpx;background:var(--acc);box-shadow:0 0 14px var(--acc)">'
             '<div class="mono" style="position:absolute;left:6px;top:-2px;font-size:10px;color:var(--acc);white-space:nowrap">edge</div></div>' % (sc.k(fr), start - 1, y0 - 34, fh + 64))
    # timeline readout
    ty = 250
    b.append('<div class="lbl" style="position:absolute;left:0;top:%dpx">Intro start</div>' % ty)
    rows = [("audio", "00:01:12.120", 0.3, 4.7, "#9aa0a8"), ("frame", "00:01:12.083", 5.0, 7.5, "var(--acc)")]
    for i, (k, v, a, z, col) in enumerate(rows):
        b.append('<div class="mono %s" style="position:absolute;left:0;top:%dpx;font-size:13px;color:%s"><span style="color:#6b7079;display:inline-block;width:64px">%s</span>%s</div>'
                 % (sc.fade(a, 7.5, 0.3), ty + 22 + 22 * i, col, k, v))
    b.append('<div class="mono" style="position:absolute;left:300px;top:%dpx;font-size:11px;color:#6b7079;line-height:1.7;width:516px;white-space:nowrap">walks at most 1 s while frames are shared or black<br>'
             'the first story frame is never taken<br>edges land on a hard cut, the end of black or the file start</div>' % (ty + 22))
    return sc


# ------------------------------------------------------------------ previews
def previews():
    sc = Scene(3, "Preview shape matching", "green", dur=8.0)
    sc.cap("<b>1</b>  line up the last minutes at the end of the file", 0.15, 2.0)
    sc.cap("<b>2</b>  same length within 1.5 s, same card", 2.0, 4.4)
    sc.cap("<b>3</b>  reported as a button, never an automatic skip", 4.4, 7.5)
    b = sc.body
    rows = [("E04", 0.585, 4), ("E05", 0.57, 5), ("E06", 0.6, 7)]
    tx, tw = 64, 752
    for i, (lab, cs, seed) in enumerate(rows):
        y = 10 + i * 74
        b.append('<div class="mono" style="position:absolute;left:0;top:%dpx;font-size:12px;color:#e8eaed">%s</div>' % (y + 20, lab))
        ps = 0.78
        # credits crawl frame
        cr = '<div style="position:absolute;left:%.1fpx;top:%dpx;width:%.1fpx;height:54px;background:#08090b;overflow:hidden">' % (tx + tw * cs, y, tw * (ps - cs))
        for k in range(5):
            cr += '<div style="position:absolute;left:%d%%;top:%dpx;width:%d%%;height:3px;background:rgba(255,255,255,.35)"></div>' % (30 + (k % 2) * 6, 8 + k * 9, 30 + (k * 7) % 20)
        cr += '<div class="mono" style="position:absolute;left:8px;bottom:6px;font-size:9.5px;color:#7d838d">credits</div></div>'
        b.append(cr)
        b.append('<div style="position:absolute;left:%dpx;top:%dpx;width:%.1fpx;height:54px;background:rgba(255,255,255,.04)"></div>' % (tx, y, tw * cs - 2))
        b.append('<div class="mono" style="position:absolute;left:%dpx;top:%dpx;font-size:9.5px;color:#5d636c">story</div>' % (tx + 8, y + 38))
        # preview: title card then new footage
        px0 = tx + tw * ps + 2
        pw = tw * (1 - ps) - 2
        b.append(still(px0, y, 30, 54, 0, title=True))
        for k in range(3):
            b.append(still(px0 + 32 + k * ((pw - 32) / 3), y, (pw - 32) / 3 - 2, 54, seed + k * 3))
        card = sc.fade(2.4 + 0.2 * i, 7.5, 0.25)
        b.append('<div class="%s" style="position:absolute;left:%.1fpx;top:%dpx;width:30px;height:54px;box-shadow:inset 0 0 0 2px var(--acc),0 0 14px rgba(63,185,80,.6)"></div>' % (card, px0, y))
    # length brackets
    br = sc.fade(0.8, 7.5, 0.35)
    bx = tx + tw * 0.78 + 2
    b.append('<div class="%s" style="position:absolute;left:%.1fpx;top:232px;width:%.1fpx;height:10px;border:2px solid var(--acc);border-top:none"></div>' % (br, bx, tx + tw - bx))
    b.append('<div class="mono %s" style="position:absolute;left:%.1fpx;top:250px;font-size:10.5px;color:var(--acc);transform:translateX(-50%%);white-space:nowrap">lengths within 1.5 s</div>' % (br, (bx + tx + tw) / 2))
    b.append('<div class="mono %s" style="position:absolute;left:%.1fpx;top:232px;font-size:10.5px;color:var(--acc);transform:translateX(-100%%);padding-right:12px">shared card at the start</div>' % (sc.fade(2.8, 7.5, 0.3), bx))
    # result: button only
    btn = sc.k([(0, "opacity:0;transform:translateY(8px)"), (4.5, "opacity:0;transform:translateY(8px)"), (5.0, "opacity:1;transform:translateY(0)"), (7.5, "opacity:1;transform:translateY(0)"),
                (7.9, "opacity:0;transform:translateY(0)"), (8, "opacity:0;transform:translateY(8px)")], ease=OUT)
    b.append('<div class="skipbtn %s" style="left:64px;top:282px">Skip Preview</div>' % btn)
    b.append('<div class="mono %s" style="position:absolute;left:200px;top:292px;font-size:11px;color:#9aa0a8">a button only  ·  skip lists leave previews out</div>' % sc.fade(5.0, 7.5, 0.3))
    return sc


# ------------------------------------------------------------------ recaps
def recaps():
    sc = Scene(4, "Recap replay matching", "coral", dur=8.0)
    sc.cap("<b>1</b>  fingerprint the start of E04", 0.15, 1.4)
    sc.cap("<b>2</b>  find each 2 s piece in an earlier episode", 1.4, 4.6)
    sc.cap("<b>3</b>  a run of 8 s or more is the recap", 4.6, 7.5)
    b = sc.body
    tx, tw = 64, 752
    src = [("E01", [0.18, 0.62], 2), ("E02", [0.41], 5), ("E03", [0.27, 0.74], 6)]
    for i, (lab, spots, seed) in enumerate(src):
        y = 6 + i * 50
        b.append('<div class="mono" style="position:absolute;left:0;top:%dpx;font-size:12px;color:#9aa0a8">%s</div>' % (y + 12, lab))
        for k in range(16):
            b.append(still(tx + k * (tw / 16), y, tw / 16 - 2, 38, seed + (k * 3) % 5, extra_style="filter:brightness(.55) saturate(.7)"))
        for sp in spots:
            b.append('<div class="%s" style="position:absolute;left:%.1fpx;top:%dpx;width:%.1fpx;height:38px;box-shadow:inset 0 0 0 2px var(--acc)"></div>'
                     % (sc.fade(0.6, 7.5, 0.3), tx + tw * sp, y, tw / 16 - 2))
    ey = 186
    b.append('<div class="mono" style="position:absolute;left:0;top:%dpx;font-size:12px;color:#e8eaed">E04</div>' % (ey + 22))
    b.append('<div style="position:absolute;left:%dpx;top:%dpx;width:%dpx;height:62px;background:rgba(255,255,255,.04)"></div>' % (tx, ey, tw))
    order = [(0, 0), (2, 0), (1, 0), (0, 1), (2, 1)]
    pw = 58
    for k, (row, spot) in enumerate(order):
        lab, spots, seed = src[row]
        sx = tx + tw * spots[spot]
        sy = 6 + row * 50
        dx = tx + 8 + k * (pw + 4)
        t0 = 1.5 + 0.55 * k
        mv = sc.k([(0, "opacity:0;transform:translate(0,0) scale(1)"), (t0, "opacity:0;transform:translate(0,0)"), (t0 + 0.1, "opacity:1;transform:translate(0,0)"),
                   (t0 + 0.75, "opacity:1;transform:translate(%.1fpx,%dpx)" % (dx - sx, ey + 8 - sy)), (7.5, "opacity:1;transform:translate(%.1fpx,%dpx)" % (dx - sx, ey + 8 - sy)),
                   (7.9, "opacity:0;transform:translate(%.1fpx,%dpx)" % (dx - sx, ey + 8 - sy)), (8, "opacity:0;transform:translate(0,0)")])
        b.append('<div class="%s" style="position:absolute;left:%.1fpx;top:%dpx;width:%dpx;height:46px;box-shadow:0 8px 20px rgba(0,0,0,.5)">%s'
                 '<div class="mono" style="position:absolute;left:4px;bottom:3px;font-size:9px;color:#fff;text-shadow:0 1px 2px #000">%s</div></div>'
                 % (mv, sx, sy, pw, still(0, 0, pw, 46, seed + (int(spots[spot] * 16) * 3) % 5), lab))
    rw = 5 * (pw + 4) + 12
    rc = sc.fade(4.7, 7.5, 0.3)
    b.append('<div class="%s" style="position:absolute;left:%dpx;top:%dpx;width:%dpx;height:62px;box-shadow:inset 0 0 0 2px var(--acc),0 0 22px rgba(255,107,90,.35)"></div>' % (rc, tx, ey, rw))
    b.append('<div class="mono %s" style="position:absolute;left:%dpx;top:%dpx;font-size:11px;color:var(--acc)">recap  00:00:00 to 00:00:10</div>' % (rc, tx, ey + 72))
    b.append(still(tx + rw + 10, ey, 150, 62, 1, title=True))
    b.append('<div class="mono" style="position:absolute;left:%dpx;top:%dpx;font-size:10px;color:#7d838d">intro</div>' % (tx + rw + 10, ey + 72))
    b.append('<div class="mono" style="position:absolute;left:%dpx;top:%dpx;font-size:10.5px;color:#6b7079;width:330px;text-align:right">with --ocr: "Previously on" cards too</div>' % (tx + tw - 330, ey + 72))
    return sc


# ------------------------------------------------------------------ OCR credits
NAMES = [("Directed by", "Ilse Varga"), ("Written by", "Tomas Reyes"), ("Produced by", "Mei Okafor"), ("Director of Photography", "Jon Ashby"),
         ("Edited by", "Rhea Lindqvist"), ("Music by", "Dario Pell"), ("Production Design", "Ana Kowal"), ("Sound", "Ravi Ostrom"),
         ("Costume Design", "Lena Moor"), ("Casting", "Paul Iwata")]


def ocr():
    sc = Scene(5, "On-screen credits reader", "gold", dur=8.0)
    sc.cap("<b>1</b>  read text in the last 450 s", 0.15, 3.6)
    sc.cap("<b>2</b>  runs to the end of the file: kept", 3.6, 7.5)
    b = sc.body
    fw, fh = 440, 248
    roll = []
    for rep in (0, 1):
        for i, (role, name) in enumerate(NAMES):
            y = 30 + (i + rep * len(NAMES)) * 46
            roll.append('<div style="position:absolute;left:0;right:0;top:%dpx;text-align:center">'
                        '<div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:rgba(255,255,255,.55)">%s</div>'
                        '<div style="font-size:15px;color:#fff;margin-top:3px;font-weight:500">%s</div>'
                        '<div style="position:absolute;left:50%%;top:-5px;width:%dpx;height:42px;transform:translateX(-50%%);box-shadow:inset 0 0 0 1.5px rgba(227,179,65,.85);background:rgba(227,179,65,.06)"></div></div>'
                        % (y, role, name, 34 + max(len(role) * 8, len(name) * 9)))
    period = len(NAMES) * 46
    sc_cls = sc.k([(0, "transform:translateY(0)"), (8, "transform:translateY(-%dpx)" % period)], ease="linear")
    b.append('<div class="player" style="left:0;top:8px;width:%dpx;height:%dpx;background:#050506"><div class="%s" style="position:absolute;inset:0">%s</div>'
             '<div style="position:absolute;inset:0;background:linear-gradient(180deg,#050506,transparent 18%%,transparent 82%%,#050506)"></div>'
             '<div style="position:absolute;left:0;right:0;top:0;height:30px;background:#050506;box-shadow:0 8px 14px #050506;border-bottom:1px solid rgba(255,255,255,.06)">'
             '<div class="mono" style="position:absolute;left:12px;top:10px;font-size:10px;color:var(--acc)">text detector  ·  320 x 180 keyframes</div></div></div>' % (fw, fh, sc_cls, "".join(roll)))
    # timeline of the tail
    rx, rw = 476, 340
    cases = [("kept", "reaches the end of the file", 0.42, 1.0, 40, "#3fb950"), ("refused", "stops before the end", 0.2, 0.7, 150, "#e5534b")]
    for lab, note, a, z, y, col in cases:
        b.append('<div style="position:absolute;left:%dpx;top:%dpx;font-size:13px;color:#c9cdd2">%s</div>' % (rx, y, note))
        b.append('<div style="position:absolute;left:%dpx;top:%dpx;width:%dpx;height:22px;background:rgba(255,255,255,.05)"></div>' % (rx, y + 26, rw))
        grow = sc.k([(0, "transform:scaleX(0)"), (0.4, "transform:scaleX(0)"), (3.4, "transform:scaleX(1)"), (7.5, "transform:scaleX(1);opacity:1"), (7.9, "opacity:0"), (8, "transform:scaleX(0);opacity:0")], ease="linear")
        b.append('<div class="%s" style="position:absolute;left:%.1fpx;top:%dpx;width:%.1fpx;height:22px;background:linear-gradient(90deg,rgba(227,179,65,.35),rgba(227,179,65,.75));transform-origin:0 50%%"></div>'
                 % (grow, rx + rw * a, y + 26, rw * (z - a)))
        b.append('<div style="position:absolute;left:%dpx;top:%dpx;width:2px;height:32px;background:#c9cdd2"></div>' % (rx + rw - 2, y + 21))
        b.append('<div class="mono %s" style="position:absolute;left:%dpx;top:%dpx;font-size:11px;color:%s">%s</div>' % (sc.fade(3.6, 7.5, 0.3), rx, y + 56, col, lab))
    b.append('<div class="mono" style="position:absolute;left:%dpx;top:%dpx;font-size:10px;color:#5d636c;transform:translateX(-100%%);white-space:nowrap">end of file</div>' % (rx + rw, 20))
    b.append('<div class="mono" style="position:absolute;left:%dpx;top:252px;font-size:10.5px;color:#6b7079;line-height:1.7;width:340px">dialogue subtitles, lower-thirds and<br>static overlays are filtered out</div>' % rx)
    return sc


# ------------------------------------------------------------------ exports
def exports():
    sc = Scene(6, "Player-ready exports", "blue", dur=8.0)
    sc.cap("<b>1</b>  scan a season", 0.15, 2.6)
    sc.cap("<b>2</b>  JSON, Kodi EDL, mpv EDL, FFmpeg chapters", 2.6, 7.5)
    b = sc.body
    lines = [('$ introkiller scan "Pioneer One" --format edl,mpv,chapters', "#e8eaed", 0.3),
             ("Pioneer One E03  (31:14.7)", "#9aa0a8", 1.0), ("  intro      4:30.0 -   4:59.2", "var(--acc)", 1.2),
             ("Pioneer One E04  (33:46.7)", "#9aa0a8", 1.5), ("  intro      4:40.4 -   5:00.0", "var(--acc)", 1.7),
             ("Pioneer One E05  (37:44.0)", "#9aa0a8", 2.0), ("  intro      3:07.6 -   3:40.9", "var(--acc)", 2.2),
             ("wrote skip-times/  json edl mpv chapters", "#6b7079", 2.6)]
    term = ['<div class="win" style="left:0;top:0;width:480px;height:330px;background:#0c0d10">', winbar("terminal", "bash")]
    for i, (txt, col, t0) in enumerate(lines):
        if i == 0:
            typ = sc.k([(0, "clip-path:inset(0 100% 0 0)"), (0.2, "clip-path:inset(0 100% 0 0)"), (0.95, "clip-path:inset(0 0% 0 0)"), (7.5, "clip-path:inset(0 0% 0 0);opacity:1"),
                        (7.9, "opacity:0"), (8, "clip-path:inset(0 100% 0 0);opacity:0")], ease="steps(40,end)")
        else:
            typ = sc.fade(t0, 7.5, 0.12)
        term.append('<div class="mono %s" style="position:absolute;left:16px;top:%dpx;font-size:11.5px;color:%s;white-space:pre">%s</div>' % (typ, 46 + i * 26, col, esc(txt)))
    term.append('</div>')
    b.append("".join(term))
    files = [("times.json", "your player, addon or database", "1.2 KB"), ("ep.edl", "Kodi skips each part once", "64 B"),
             ("ep.mpv.edl", "mpv plays without them", "180 B"), ("ep.ffmeta", "chapters for FFmpeg", "410 B")]
    fx = 504
    b.append('<div class="lbl" style="position:absolute;left:%dpx;top:6px">skip-times/</div>' % fx)
    for i, (fn, note, size) in enumerate(files):
        y = 30 + i * 74
        t0 = 2.7 + 0.3 * i
        ent = sc.k([(0, "opacity:0;transform:translateX(12px)"), (t0, "opacity:0;transform:translateX(12px)"), (t0 + 0.45, "opacity:1;transform:translateX(0)"),
                    (7.5, "opacity:1;transform:translateX(0)"), (7.9, "opacity:0;transform:translateX(0)"), (8, "opacity:0;transform:translateX(12px)")], ease=OUT)
        b.append('<div class="win %s" style="left:%dpx;top:%dpx;width:312px;height:62px">'
                 '<div style="position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--acc)"></div>'
                 '<div class="mono" style="position:absolute;left:18px;top:12px;font-size:13px;color:#f1f3f5">%s</div>'
                 '<div style="position:absolute;left:18px;top:34px;font-size:12px;color:#8b9099">%s</div>'
                 '<div class="mono" style="position:absolute;right:14px;top:13px;font-size:10.5px;color:#6b7079">%s</div></div>' % (ent, fx, y, fn, note, size))
    return sc


SCENES = {"hero": hero, "align": align, "edges": edges, "previews": previews, "recaps": recaps, "ocr": ocr, "exports": exports}


# Settled moments for the PNG fallbacks: every part of the scene is on screen and nothing is mid-transition.
STILLS = {"hero": 5.0, "align": 6.0, "edges": 6.2, "previews": 6.0, "recaps": 6.0, "ocr": 5.0, "exports": 6.0}


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA
    for name in (sys.argv[3:] or SCENES):
        sc = SCENES[name](data) if name == "hero" else SCENES[name]()
        sc.still = STILLS.get(name)
        (out / (name + ".html")).write_text(sc.html(), encoding="utf-8", newline="\n")
        print("scene", name)


if __name__ == "__main__":
    main()
