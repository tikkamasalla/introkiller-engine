"""Shared drawing kit for the animated README cards. Standard library only.

Every card is 880 wide. Feature cards are 880 x 300, the hero is 880 x 340.
Each card is written twice, light and dark, from the same drawing code.
"""
import html
import random

W = 880
PAD = 32
SANS = "ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,'SF Mono','Cascadia Mono',Consolas,Menlo,monospace"

HUES = ("violet", "teal", "coral", "amber", "green", "blue", "pink")
THEMES = {
    "dark": dict(
        bg0="#121a2e", bg1="#0c1222", edge="#243050", ink="#f1f4ff", ink2="#b3bcd9", mute="#7883a6",
        track="#1f2840", track2="#2a3555", panel="#182039", panel2="#1d2746", shadow="#000000", shadow_op=0.45,
        violet="#8f7dff", teal="#2bd5c0", coral="#ff6f82", amber="#ffb84d", green="#4fdc85", blue="#5aa8ff", pink="#f774c9",
        glow_op=0.22, tint_op=0.18, on_hue="#0c1222",
    ),
    "light": dict(
        bg0="#ffffff", bg1="#f1f4fb", edge="#dfe4f0", ink="#141a2e", ink2="#4a5474", mute="#8790ab",
        track="#e7ebf5", track2="#d6dcea", panel="#ffffff", panel2="#f6f8fd", shadow="#1d2a55", shadow_op=0.14,
        violet="#6a4ff2", teal="#0b9d8c", coral="#e2405a", amber="#d98200", green="#16a150", blue="#2b74e6", pink="#d23c98",
        glow_op=0.13, tint_op=0.12, on_hue="#ffffff",
    ),
}
# What each colour means, in both repos.
SEG = dict(recap="pink", intro="violet", credits="amber", preview="green", story="blue", ok="teal", bad="coral")


def esc(s):
    return html.escape(str(s), quote=True)


def mix(c1, c2, f):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * f) for i in range(3))


def f1(v):
    s = ("%.1f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def attrs(**kw):
    out = []
    for k, v in kw.items():
        if v is None:
            continue
        k = k.rstrip("_").replace("_", "-")
        out.append('%s="%s"' % (k, f1(v) if isinstance(v, float) else esc(v)))
    return " ".join(out)


def rect(x, y, w, h, fill, rx=0, **kw):
    return '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" %s/>' % (
        f1(x), f1(y), f1(max(w, 0)), f1(max(h, 0)), f1(rx), fill, attrs(**kw))


def circle(cx, cy, r, fill, **kw):
    return '<circle cx="%s" cy="%s" r="%s" fill="%s" %s/>' % (f1(cx), f1(cy), f1(r), fill, attrs(**kw))


def text(x, y, s, size=14, fill="#000", anchor="start", weight=500, family=SANS, **kw):
    return '<text x="%s" y="%s" font-size="%s" fill="%s" text-anchor="%s" font-weight="%s" font-family="%s" %s>%s</text>' % (
        f1(x), f1(y), size, fill, anchor, weight, family, attrs(**kw), esc(s))


def g(body, **kw):
    return "<g %s>%s</g>" % (attrs(**kw), "".join(body) if isinstance(body, list) else body)


def text_w(s, size, weight=500, mono=False):
    """Rough advance width for system sans or mono, used only to size pills."""
    if mono:
        return len(s) * size * 0.61
    wide = sum(1 for ch in s if ch in "MWmw@%")
    narrow = sum(1 for ch in s if ch in "ilIj.,:;'|! ft")
    caps = sum(1 for ch in s if ch.isupper() and ch not in "MWI")
    k = 0.56 if weight >= 600 else 0.53
    rest = len(s) - wide - narrow - caps
    return size * (k * rest + 0.85 * wide + 0.30 * narrow + 0.68 * caps)


class Card:
    """One SVG card. Draw into self.b, register CSS in self.css, then .svg()."""

    def __init__(self, theme, h=300, dur=8.0, accent="violet", title="", desc="", glow=None):
        self.t = THEMES[theme]
        self.mode = theme
        self.h, self.dur, self.accent = h, dur, accent
        self.title, self.desc = title, desc
        self.b, self.css, self.defs = [], [], []
        self.glow = glow or [(accent, 0.92, 0.0), ("teal", 0.0, 1.0)]
        self._n = 0

    # ---------- colour helpers
    def c(self, name):
        return self.t.get(name, name)

    def grad(self, hue):
        return "url(#g-%s)" % hue

    def tint(self, hue, f=None):
        base = self.t["panel"] if self.mode == "light" else self.t["bg1"]
        return mix(base, self.c(hue), self.t["tint_op"] if f is None else f)

    # ---------- animation helpers
    def anim(self, frames, ease="cubic-bezier(.45,0,.25,1)", origin=None):
        """frames: list of (seconds, css). Returns a class name with a looping animation."""
        self._n += 1
        name = "a%d" % self._n
        steps = []
        for sec, css in frames:
            pct = 100.0 * sec / self.dur
            steps.append("%s%%{%s}" % (f1(pct) if pct not in (0, 100) else int(pct), css))
        extra = ""
        if origin:
            extra = "transform-box:fill-box;transform-origin:%s;" % origin
        self.css.append(".%s{animation:%s %ss %s infinite;%s}@keyframes %s{%s}" % (
            name, name, f1(self.dur), ease, extra, name, "".join(steps)))
        return name

    def show(self, t_in, t_out, fade=0.35, start=0.0, end=None, extra_in="", extra_out=""):
        """Opacity window: hidden, fades in at t_in, holds, fades out at t_out."""
        end = self.dur if end is None else end
        fr = [(0, "opacity:0;" + extra_out)]
        fr.append((max(t_in, 0.001), "opacity:0;" + extra_out))
        fr.append((t_in + fade, "opacity:1;" + extra_in))
        fr.append((t_out, "opacity:1;" + extra_in))
        fr.append((min(t_out + fade, self.dur), "opacity:0;" + extra_out))
        fr.append((self.dur, "opacity:0;" + extra_out))
        return self.anim(fr)

    # ---------- furniture
    def frame(self):
        t = self.t
        d = ['<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
             '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>' % (t["bg0"], t["bg1"])]
        for i, (hue, gx, gy) in enumerate(self.glow):
            d.append('<radialGradient id="glow%d" cx="%s" cy="%s" r="0.75">'
                     '<stop offset="0" stop-color="%s" stop-opacity="%s"/><stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>'
                     % (i, f1(gx), f1(gy), self.c(hue), f1(t["glow_op"]), self.c(hue)))
        for hue in HUES:
            top = mix(self.c(hue), "#ffffff", 0.28)
            d.append('<linearGradient id="g-%s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="%s"/>'
                     '<stop offset="1" stop-color="%s"/></linearGradient>' % (hue, top, self.c(hue)))
            d.append('<linearGradient id="h-%s" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="%s"/>'
                     '<stop offset="1" stop-color="%s"/></linearGradient>' % (hue, self.c(hue), mix(self.c(hue), "#ffffff", 0.22)))
        d.append('<filter id="lift" x="-10%%" y="-20%%" width="120%%" height="160%%"><feDropShadow dx="0" dy="3" stdDeviation="4" '
                 'flood-color="%s" flood-opacity="%s"/></filter>' % (t["shadow"], f1(t["shadow_op"])))
        d.append('<filter id="soft" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="7"/></filter>')
        d.append('<clipPath id="card"><rect x="0" y="0" width="%d" height="%d" rx="18"/></clipPath>' % (W, self.h))
        self.defs = d + self.defs
        bg = [rect(0, 0, W, self.h, "url(#bg)", 18)]
        for i in range(len(self.glow)):
            bg.append(rect(0, 0, W, self.h, "url(#glow%d)" % i, 18))
        bg.append(rect(0.75, 0.75, W - 1.5, self.h - 1.5, "none", 17.5, stroke=t["edge"], stroke_width=1.5))
        return bg

    def eyebrow(self, label, hue=None, x=PAD, y=26):
        hue = hue or self.accent
        w = text_w(label.upper(), 12, 700) + 0.9 * len(label) + 38
        return g([rect(x, y, w, 26, self.tint(hue, 0.22 if self.mode == "dark" else 0.14), 13),
                  circle(x + 14, y + 13, 4.5, self.grad(hue)),
                  text(x + 25, y + 17.5, label.upper(), 12, self.c(hue), weight=750, letter_spacing="0.9")])

    def steps(self, items, y=26):
        """items: list of (label, hue, t_on, t_off). Pills right-aligned in the header."""
        t = self.t
        widths = [text_w(lab, 12.5, 600) + 44 for lab, _h, _a, _b in items]
        x = W - PAD - sum(widths) - 8 * (len(items) - 1)
        out = []
        for (lab, hue, t_on, t_off), w in zip(items, widths):
            base = [rect(x, y, w, 26, t["track"], 13), circle(x + 14, y + 13, 9, t["track2"]),
                    text(x + 14, y + 17.3, str(items.index((lab, hue, t_on, t_off)) + 1), 11.5, t["mute"], "middle", 700),
                    text(x + 30, y + 17.5, lab, 12.5, t["ink2"], weight=600)]
            cls = self.show(t_on, t_off, fade=0.3)
            on = g([rect(x, y, w, 26, self.tint(hue, 0.3 if self.mode == "dark" else 0.18), 13),
                    circle(x + 14, y + 13, 9, self.grad(hue)),
                    text(x + 14, y + 17.3, str(items.index((lab, hue, t_on, t_off)) + 1), 11.5, t["on_hue"], "middle", 800),
                    text(x + 30, y + 17.5, lab, 12.5, t["ink"], weight=650)], class_=cls)
            out += base + [on]
            x += w + 8
        return out

    def pill(self, x, y, label, hue, h=28, size=13, solid=False, mono=False, icon=None, w=None, anchor="start"):
        t = self.t
        tw = text_w(label, size, 650, mono)
        w = w or tw + 26 + (18 if icon else 0)
        if anchor == "middle":
            x -= w / 2
        elif anchor == "end":
            x -= w
        fill = self.grad(hue) if solid else self.tint(hue, 0.24 if self.mode == "dark" else 0.15)
        ink = t["on_hue"] if solid else (self.c(hue) if self.mode == "light" else mix(self.c(hue), "#ffffff", 0.35))
        out = [rect(x, y, w, h, fill, h / 2)]
        tx = x + 13
        if icon == "check":
            out.append(circle(x + 15, y + h / 2, 7, t["on_hue"] if solid else self.c(hue)))
            out.append('<path d="M%s %sl2.6 2.6 4.6-5.2" fill="none" stroke="%s" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
                       % (f1(x + 11.6), f1(y + h / 2), self.c(hue) if solid else t["on_hue"]))
            tx = x + 28
        elif icon == "cross":
            out.append(circle(x + 15, y + h / 2, 7, t["on_hue"] if solid else self.c(hue)))
            out.append('<path d="M%s %sl5 5m0-5l-5 5" fill="none" stroke="%s" stroke-width="2.2" stroke-linecap="round"/>'
                       % (f1(x + 12.5), f1(y + h / 2 - 2.5), self.c(hue) if solid else t["on_hue"]))
            tx = x + 28
        elif icon == "dot":
            out.append(circle(x + 14, y + h / 2, 4.5, self.c(hue) if not solid else t["on_hue"]))
            tx = x + 25
        out.append(text(tx, y + h / 2 + size * 0.36, label, size, ink, weight=650, family=MONO if mono else SANS))
        return out, w

    def svg(self):
        style = "".join(self.css)
        style += ("@media (prefers-reduced-motion:reduce){*{animation-play-state:paused!important;animation-delay:-%ss!important}}"
                  % f1(self.still if hasattr(self, "still") else self.dur * 0.62))
        body = self.frame() + ['<g clip-path="url(#card)">'] + self.b + ["</g>"]
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s">'
                "<title>%s</title><desc>%s</desc><defs>%s</defs><style>%s</style>%s</svg>\n"
                % (W, self.h, W, self.h, esc(self.title), esc(self.title), esc(self.desc), "".join(self.defs), style, "".join(body)))


# ---------------------------------------------------------------- audio shapes
def amp_story(n, seed):
    """Speech-like: bursts with short gaps."""
    r = random.Random(seed)
    out, v = [], 0.3
    for i in range(n):
        if r.random() < 0.08:
            v = 0.08
        else:
            v = 0.55 * v + 0.45 * (0.18 + 0.5 * r.random())
        out.append(v)
    return out


def amp_music(n, seed=7, beat=6):
    """Theme-like: steady rhythm with a swelling envelope."""
    r = random.Random(seed)
    out = []
    for i in range(n):
        env = 0.55 + 0.35 * (i / max(n - 1, 1)) ** 0.6
        pulse = 0.72 + 0.28 * (1 if i % beat in (0, 1) else 0.35)
        out.append(min(1.0, env * pulse * (0.82 + 0.18 * r.random())))
    return out


def bars(x, yc, amps, step=4.6, bw=3.0, hmax=24, hmin=1.5):
    """Filled symmetric bar waveform as one path string."""
    d = []
    for i, a in enumerate(amps):
        if a <= 0:
            continue
        h = max(hmin, a * hmax)
        d.append("M%s %sh%sv%sh-%sz" % (f1(x + i * step), f1(yc - h), f1(bw), f1(2 * h), f1(bw)))
    return "".join(d)


def wave(x, yc, amps, fill, step=4.6, bw=3.0, hmax=24, **kw):
    return '<path d="%s" fill="%s" %s/>' % (bars(x, yc, amps, step, bw, hmax), fill, attrs(**kw))
