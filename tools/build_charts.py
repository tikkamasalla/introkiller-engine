#!/usr/bin/env python3
"""Rebuild every graphic in assets/ from the files in data/. Standard library only.

    python tools/build_charts.py
"""
import collections
import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "assets"
SANS = "ui-sans-serif,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,'SF Mono','Cascadia Mono',Consolas,Menlo,monospace"
KINDS = ("recap", "intro", "credits", "preview")
THEMES = {
    "light": dict(panel="#fbf8f3", edge="#e8e0d4", ink="#241b12", ink2="#5f5344", mute="#8a7d6d", story="#e9e2d6",
                  heat0=(240, 233, 222), heat1=(226, 150, 50), heat2=(150, 62, 14),
                  intro="#d9730d", credits="#a83a14", preview="#c99a12", recap="#b0553f"),
    "dark": dict(panel="#17130f", edge="#2e2720", ink="#f5eee4", ink2="#c4b7a6", mute="#928573", story="#2b251e",
                 heat0=(35, 30, 24), heat1=(196, 110, 22), heat2=(255, 190, 80),
                 intro="#d07a12", credits="#a33d18", preview="#ad8c14", recap="#c25f6c"),
}


def esc(s):
    return html.escape(str(s), quote=True)


def text(x, y, s, size=15, fill="#000", anchor="start", weight=400, family=SANS, extra=""):
    return ('<text x="%.1f" y="%.1f" font-size="%s" fill="%s" text-anchor="%s" font-weight="%s" font-family="%s" %s>%s</text>'
            % (x, y, size, fill, anchor, weight, family, extra, esc(s)))


def rect(x, y, w, h, fill, rx=0, extra=""):
    return '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="%s" %s/>' % (x, y, max(w, 0), h, fill, rx, extra)


def svg(w, h, t, body, title, desc, style=""):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s">'
            '<title>%s</title><desc>%s</desc>%s%s%s</svg>\n'
            % (w, h, w, h, esc(title), esc(title), esc(desc), ("<style>%s</style>" % style) if style else "",
               rect(0.5, 0.5, w - 1, h - 1, t["panel"], 14, 'stroke="%s"' % t["edge"]), "".join(body)))


def heat_color(t, v):
    """v from 0 to 9, one hue: faint, then amber, then the far end of the ramp."""
    a = v / 9.0
    lo, hi, f = (t["heat0"], t["heat1"], a / 0.6) if a < 0.6 else (t["heat1"], t["heat2"], (a - 0.6) / 0.4)
    return "#%02x%02x%02x" % tuple(round(lo[i] + (hi[i] - lo[i]) * f) for i in range(3))


def strip(t, digits, x, y, w, h):
    """Draw one row of per-second digits as merged runs."""
    out, i, n = [], 0, len(digits)
    while i < n:
        j = i
        while j < n and digits[j] == digits[i]:
            j += 1
        out.append(rect(x + i * w / n, y, (j - i) * w / n + 0.2, h, heat_color(t, int(digits[i]))))
        i = j
    return out


def clock(sec):
    return "%d:%02d" % (sec // 60, round(sec % 60)) if round(sec % 60) < 60 else "%d:00" % (sec // 60 + 1)


# ------------------------------------------------------------------ graphics
def hero(t, heat):
    W, H = 1000, 300
    b = [text(44, 92, "IntroKiller Engine", 58, t["ink"], weight=800),
         text(46, 134, "Also kills credits, previews and recaps.", 25, t["ink2"], weight=500),
         text(46, 168, "Never touches your files.", 25, t["ink"], weight=700)]
    x0, y0, w, rh = 44, 192, W - 88, 6.6
    b.append('<g>')
    for i, row in enumerate(heat["rows"]):
        b += strip(t, row["head"], x0, y0 + i * (rh + 0.6), w, rh)
    b.append('</g>')
    b.append(rect(x0, y0 - 3, 2.5, 12 * (rh + 0.6) + 6, t["ink"], 1, 'class="scan"'))
    style = (".scan{animation:scan 9s linear infinite}"
             "@keyframes scan{from{transform:translateX(0)}to{transform:translateX(%dpx)}}"
             "@media (prefers-reduced-motion:reduce){.scan{animation:none;opacity:0}}" % (w - 2))
    return svg(W, H, t, b, "IntroKiller Engine", "Project title and tagline over a strip of real data: twelve episodes, first five minutes, "
               "with the audio they share drawn as bright bands.", style)


def heat_chart(t, heat):
    W, top, rh, gap, left = 1000, 96, 22, 3, 62
    n = len(heat["rows"])
    pw = (W - left - 34 - 40) / 2
    x2 = left + pw + 40
    H = top + n * (rh + gap) + 96
    b = [text(left, 36, "First five minutes", 17, t["ink"], weight=700), text(x2, 36, "Last five minutes", 17, t["ink"], weight=700)]
    for k in range(6):
        for x, lab in ((left + k * pw / 5, clock(60 * k)), (x2 + k * pw / 5, "-" + clock(300 - 60 * k) if k < 5 else "end")):
            b.append(text(x, 62, lab, 13, t["mute"], "middle" if 0 < k < 5 else ("start" if k == 0 else "end"), family=MONO))
            b.append(rect(x - 0.5, 69, 1, 8, t["mute"]))
    for i, row in enumerate(heat["rows"]):
        y = top - 12 + i * (rh + gap)
        b.append(text(left - 10, y + rh - 6, row["label"], 14, t["ink2"], "end", family=MONO))
        b += strip(t, row["head"], left, y, pw, rh)
        b += strip(t, row["tail"], x2, y, pw, rh)
    ly = top + n * (rh + gap) + 8
    b.append(text(left, ly + 8, "The intro starts anywhere from 0:01 to 2:39.", 15, t["ink"], weight=600))
    b.append(text(x2, ly + 8, "The credits stay put, counted from the end.", 15, t["ink"], weight=600))
    lx, ly2 = left, ly + 40
    b.append(text(lx, ly2 + 12, "Other episodes sharing this second:", 14, t["ink2"]))
    bx = lx + 244
    for v in range(10):
        b.append(rect(bx + v * 24, ly2, 24, 16, heat_color(t, v)))
    b.append(text(bx - 6 + 240 + 12, ly2 + 13, "none to all 11", 14, t["ink2"]))
    return svg(W, H, t, b, "Shared audio in twelve episodes", "Twelve rows, one per episode of %s. Time runs left to right. A bright band marks "
               "seconds whose audio also appears in the other episodes. The intro band moves from episode to episode; the credits band lines up near the end." % heat["title"])


def anatomy(t, rows):
    W, left = 1000, 30
    bw = W - 2 * left
    rh, H = 34, 58 + 134 * len(rows) - 8
    b = []
    for i, ep in enumerate(rows):
        y = 58 + i * 134
        b.append(text(left, y - 26, ep["title"], 16, t["ink"], weight=700))
        b.append(text(W - left, y - 26, "runtime " + clock(ep["duration"]), 14, t["mute"], "end", family=MONO))
        b.append(rect(left, y, bw, rh, t["story"], 5))
        for s in ep["segments"]:
            x, w = left + bw * s["start"] / ep["duration"], bw * (s["end"] - s["start"]) / ep["duration"]
            b.append(rect(x, y, w, rh, t[s["type"]], 2))
            if s.get("label_up"):
                b.append(rect(x + w / 2 - 0.5, y - 8, 1, 8, t["mute"]))
        for s in ep["segments"]:
            x, w = left + bw * s["start"] / ep["duration"], bw * (s["end"] - s["start"]) / ep["duration"]
            cx = max(left + 30, min(W - left - 30, x + w / 2)) + s.get("nudge", 0)
            b.append(text(cx, y + rh + 21, s["type"].capitalize(), 15, t["ink"], "middle", 700))
            b.append(text(cx, y + rh + 39, "%s-%s" % (clock(s["start"]), clock(s["end"])), 13, t["ink2"], "middle", family=MONO))
        st = ep.get("story_x", 0.45)
        b.append(text(left + bw * st, y + 23, "story", 15, t["ink2"], "middle"))
    return svg(W, H, t, b, "Anatomy of two real episodes", "Timelines of two real episodes with their recap, intro, credits and preview drawn to scale over the story.")


def scoreboard(t, sc):
    W, left, bw = 1000, 150, 670
    rows = [("intro", "Intro"), ("credits", "Credits"), ("preview", "Preview"), ("recap", "Recap")]
    maxn = max(v["hit"] + v["miss"] for v in sc["headline"].values())
    scale = bw / maxn
    rh, block = 22, 78
    H = 60 + block * len(rows) + 2
    b = [rect(left, 20, 20, 14, t["intro"], 3), text(left + 27, 32, "found", 14, t["ink2"]),
         rect(left + 90, 20.5, 19, 13, "none", 3, 'stroke="%s" stroke-width="1.4"' % t["mute"]), text(left + 116, 32, "missed", 14, t["ink2"]),
         text(W - 30, 32, "false / flagged", 14, t["ink2"], "end")]
    for i, (k, lab) in enumerate(rows):
        y = 60 + i * block
        b.append(text(left - 66, y + 30, lab, 17, t["ink"], "end", 700))
        for j, (which, name) in enumerate((("old_version", "old"), ("headline", "now"))):
            v = sc[which][k]
            yy = y + j * (rh + 6)
            b.append(text(left - 10, yy + 16, name, 13, t["mute"], "end", family=MONO))
            hw, mw = v["hit"] * scale, v["miss"] * scale
            if v["hit"]:
                b.append(rect(left, yy, hw - 1, rh, t[k], 3))
            b.append(rect(left + hw + 1, yy + 0.7, max(mw - 2, 1), rh - 1.4, "none", 3, 'stroke="%s" stroke-width="1.4"' % t["mute"]))
            b.append(text(left + hw + mw + 8, yy + 16, "%d of %d" % (v["hit"], v["hit"] + v["miss"]), 14, t["ink"], weight=600 if j else 400))
            b.append(text(W - 30, yy + 16, "%d / %d" % (v["false"], v["flagged"]), 14, t["ink2"], "end", family=MONO))
    return svg(W, H, t, b, "Scoreboard, old version against current", "Paired bars for intro, credits, preview and recap on 123 episodes, showing how many were found and missed, plus false results and flagged segments.")


def show_grid(t, sc):
    W, left, top = 1000, 262, 66
    cols = [("intro", "Intro"), ("credits", "Credits"), ("preview", "Preview"), ("recap", "Recap")]
    cw, rh = (W - left - 24) / 4, 25
    rows = sorted(sc["per_set"], key=lambda s: s["set"])
    H = top + rh * len(rows) + 22
    b = []
    for j, (_k, lab) in enumerate(cols):
        b.append(text(left + j * cw + 2, 44, lab, 15, t["ink"], weight=700))
    b.append(text(left - 12, 44, "eps", 13, t["mute"], "end", family=MONO))
    for i, s in enumerate(rows):
        y = top + i * rh
        b.append(text(24, y + 16, s["set"], 14.5, t["ink"]))
        b.append(text(left - 12, y + 16, str(s["episodes"]), 13, t["mute"], "end", family=MONO))
        for j, (k, _lab) in enumerate(cols):
            x, c, cell = left + j * cw, cw - 74, s[k]
            if cell is None:
                b.append(rect(x, y + 11, c, 1, t["edge"]))
                continue
            key = cell["key"]
            b.append(rect(x, y + 4, c, 15, t["story"], 3))
            if key and cell["hit"]:
                b.append(rect(x, y + 4, c * cell["hit"] / key, 15, t[k], 3))
            label = "%d/%d" % (cell["hit"], key) if key else "0/0"
            b.append(text(x + c + 7, y + 16, label, 13, t["ink"], family=MONO))
            if cell["false"]:
                b.append(text(x + c + 42, y + 16, "+%df" % cell["false"], 12, t["ink2"], family=MONO))
    return svg(W, H, t, b, "Results per show", "One row per test set with found out of reference count for intro, credits, preview and recap. A dash means the reference has none. +3f means three false results.")


def hours_chart(t, rows):
    W, left, top, rh = 1000, 262, 124, 21
    shows = collections.defaultdict(lambda: {"secs": collections.Counter(), "runtime": {}})
    for r in rows:
        s = shows[r["show"]]
        s["secs"][r["type"]] += (int(r["end_ms"]) - int(r["start_ms"])) / 1000
        s["runtime"][(r["season"], r["episode"])] = int(r["duration_ms"]) / 1000
    total = sum(sum(s["secs"].values()) for s in shows.values())
    runtime = sum(sum(s["runtime"].values()) for s in shows.values())
    eps = sum(len(s["runtime"]) for s in shows.values())
    order = sorted(shows.items(), key=lambda kv: -sum(kv[1]["secs"].values()) / sum(kv[1]["runtime"].values()))
    H = top + rh * len(order) + 40
    b = [text(24, 62, "%.1f hours" % (total / 3600), 46, t["ink"], weight=800),
         text(24, 90, "of %.1f hours of runtime, %d episodes of %d shows. That is %.1f%%." % (runtime / 3600, eps, len(order), 100 * total / runtime), 16, t["ink2"])]
    lx = W - 24
    for k in ("recap", "preview", "credits", "intro"):
        lx -= 14 + len(k) * 8 + 16
        b.append(rect(lx, 36, 13, 13, t[k], 3))
        b.append(text(lx + 18, 47, k, 14, t["ink2"]))
    pw = W - left - 90
    maxshare = max(sum(s["secs"].values()) / sum(s["runtime"].values()) for _n, s in order)
    for i, (name, s) in enumerate(order):
        y = top + i * rh
        b.append(text(left - 12, y + 14, name, 14, t["ink"], "end"))
        x, rt = left, sum(s["runtime"].values())
        for k in ("recap", "intro", "credits", "preview"):
            if s["secs"][k]:
                w = pw * (s["secs"][k] / rt) / maxshare
                b.append(rect(x, y + 2, max(w - 1.5, 1), rh - 6, t[k], 2))
                x += w
        b.append(text(x + 6, y + 14, "%.1f%%" % (100 * sum(s["secs"].values()) / rt), 13, t["ink2"], family=MONO))
    return svg(W, H, t, b, "Time given back per show", "Share of each show's runtime covered by the published segments, sorted, split into recap, intro, credits and preview.")


def demo_chart(t, demo):
    rows = demo["episodes"]
    W, left, rh = 1000, 70, 30
    bw = W - left - 30
    longest = max(e["duration"] for e in rows)
    H = 62 + len(rows) * (rh + 8) + 44
    b = [text(left, 34, demo["caption"], 15, t["ink2"])]
    present = sorted({s["type"] for e in rows for s in e["segments"]}, key=KINDS.index)
    lx = W - 30
    for k in reversed(present):
        lx -= 18 + len(k) * 8 + 8
        b.append(rect(lx, 23, 13, 13, t[k], 3))
        b.append(text(lx + 18, 34, k, 14, t["ink2"]))
    for i, e in enumerate(rows):
        y = 52 + i * (rh + 8)
        b.append(text(left - 10, y + 20, e["label"], 14, t["ink2"], "end", family=MONO))
        b.append(rect(left, y, bw * e["duration"] / longest, rh, t["story"], 4))
        for s in e["segments"]:
            b.append(rect(left + bw * s["start"] / longest, y, max(bw * (s["end"] - s["start"]) / longest, 1.5), rh, t[s["type"]], 2))
    y = 52 + len(rows) * (rh + 8) + 18
    for k in range(0, int(longest // 600) + 1):
        x = left + bw * k * 600 / longest
        b.append(text(x, y, "%d min" % (k * 10), 13, t["mute"], "middle", family=MONO))
    return svg(W, H, t, b, "Pioneer One, what the engine reports", "One timeline per episode of Pioneer One with each reported segment drawn to scale.")


def main():
    OUT.mkdir(exist_ok=True)
    heat = json.loads((DATA / "heat_logh_s3.json").read_text(encoding="utf-8"))
    sc = json.loads((DATA / "scoreboard.json").read_text(encoding="utf-8"))
    anat = json.loads((DATA / "anatomy.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(DATA / "published.csv", encoding="utf-8", newline="")))
    demo_file = DATA / "demo_pioneer_one.json"
    demo = json.loads(demo_file.read_text(encoding="utf-8")) if demo_file.exists() else None
    for mode, t in THEMES.items():
        items = {"hero": hero(t, heat), "heat": heat_chart(t, heat), "anatomy": anatomy(t, anat), "scoreboard": scoreboard(t, sc),
                 "shows": show_grid(t, sc), "hours": hours_chart(t, rows)}
        if demo:
            items["demo"] = demo_chart(t, demo)
        for name, content in items.items():
            (OUT / ("%s-%s.svg" % (name, mode))).write_text(content, encoding="utf-8", newline="\n")
    total = sum(p.stat().st_size for p in OUT.iterdir())
    print("assets: %d files, %.0f KB" % (len(list(OUT.iterdir())), total / 1024))


if __name__ == "__main__":
    main()
