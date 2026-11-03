"""Command line: scan a folder (or a list of files or URLs) of episodes and report segment times."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

from . import CLI_NAME, DISPLAY_NAME, __version__, formats, media, pipeline, themes_stage

VIDEO = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".ts", ".m2ts", ".mpg", ".mpeg", ".wmv", ".ogv"}
FORMATS = ("json", "edl", "mpv", "chapters")
EOF_TOLERANCE = 1.0                  # a text-only credits result is kept only if it reaches the end of the file
PATTERNS = (r"[Ss](\d{1,3})[ ._-]*[Ee][Pp]?[ ._-]*(\d{1,4})", r"\b(\d{1,2})x(\d{1,4})\b")
EPISODE_ONLY = r"(?:^|[ ._\-\[(])(?:[Ee][Pp]?(?:isode)?)[ ._-]*(\d{1,4})\b"


def natural(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text)]


def parse_number(name):
    """(season, episode) read from a file name; either can be None."""
    for pat in PATTERNS:
        m = re.search(pat, name)
        if m:
            return int(m.group(1)), int(m.group(2))
    m = re.search(EPISODE_ONLY, name)
    return (None, int(m.group(1))) if m else (None, None)


def collect(inputs):
    """Turn folders, files and URLs into episode dicts, in natural order."""
    specs = []
    for item in inputs:
        if item.startswith(("http://", "https://")):
            specs.append(item)
        elif os.path.isdir(item):
            found = [str(p) for p in Path(item).iterdir() if p.suffix.lower() in VIDEO]
            specs += sorted(found, key=natural)
        elif os.path.isfile(item):
            specs.append(item)
        else:
            raise SystemExit("%s: no such file or folder: %s" % (CLI_NAME, item))
    episodes, used = [], set()
    for spec in specs:
        base = urllib.parse.unquote(spec.split("?")[0].rsplit("/", 1)[-1]) if spec.startswith("http") else os.path.basename(spec)
        stem = os.path.splitext(base)[0]
        name, k = stem, 2
        while name in used:
            name, k = "%s_%d" % (stem, k), k + 1
        used.add(name)
        season, number = parse_number(stem)
        episodes.append({"spec": spec, "name": name, "season": season, "episode": number})
    return episodes


def by_season(episodes):
    """Group by season. Detection compares episodes of one season, so this grouping matters."""
    groups = {}
    for e in episodes:
        groups.setdefault(e["season"] if e["season"] is not None else 1, []).append(e)
    for eps in groups.values():
        if any(e["episode"] is None for e in eps) or len({e["episode"] for e in eps}) < len(eps):
            for i, e in enumerate(eps):      # names without usable numbers: fall back to the order in the folder
                e["episode"] = i + 1
    return dict(sorted(groups.items()))


def cache_dir(base, eps):
    """One cache per set of input files, so a replaced file can never reuse old windows."""
    h = hashlib.sha1()
    for e in eps:
        st = os.stat(e["spec"]) if os.path.exists(e["spec"]) else None
        h.update(("%s|%s|%s\n" % (e["spec"], st.st_size if st else "", st.st_mtime if st else "")).encode("utf-8"))
    return os.path.join(base, h.hexdigest()[:12])


def text_credits(result, spec, cache):
    """Optional stage: on-screen text, only where matching found no credits, kept only if it reaches the file end."""
    from . import ocr_credits
    if any(s["type"] == "credits" for s in result["segments"]):
        return
    seg = ocr_credits.detect_credits(spec, name=result["episode"], cache_dir=cache)
    if seg is None:
        return
    if abs(seg["end"] - result["duration"]) > EOF_TOLERANCE:
        result["rejected"].append({"kind": "text-credits", "start": seg["start"], "end": seg["end"],
                                   "reason": "text run does not reach the end of the file"})
        return
    s0, s1 = round(float(seg["start"]), 3), round(float(seg["end"]), 3)
    result["segments"].append({"type": "credits", "start": s0, "end": s1, "length": round(s1 - s0, 3), "confidence": 0.5,
                               "method": seg.get("method", "credits"), "gates": {"detail": seg.get("detail")}})
    result["segments"].sort(key=lambda s: s["start"])


def clock(t):
    tenths = round(t * 10)
    h, m, s = tenths // 36000, tenths // 600 % 60, tenths % 600 / 10
    return "%d:%02d:%04.1f" % (h, m, s) if h else "%d:%04.1f" % (m, s)


def write_sidecars(outdir, result, spec, which):
    segs, dur, stem = result["segments"], result["duration"], os.path.join(outdir, result["episode"])
    files = {"edl": (".edl", lambda: formats.kodi_edl(segs)), "chapters": (".ffmeta", lambda: formats.ffmeta(segs, dur)),
             "mpv": (".mpv.edl", lambda: formats.mpv_edl(os.path.abspath(spec) if os.path.exists(spec) else spec, segs, dur))}
    for key, (ext, make) in files.items():
        if key in which and segs:
            with open(stem + ext, "w", encoding="utf-8", newline="\n") as f:
                f.write(make())


def scan(a):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise SystemExit("%s: ffmpeg and ffprobe must be on the PATH (version 5.1 or newer)." % CLI_NAME)
    which = {f.strip() for f in a.format.split(",")}
    bad = which - set(FORMATS)
    if bad:
        raise SystemExit("%s: unknown format %s (choose from %s)" % (CLI_NAME, ", ".join(sorted(bad)), ", ".join(FORMATS)))
    if a.ocr:
        try:
            import rapidocr_onnxruntime  # noqa: F401
        except ImportError:
            raise SystemExit("%s: --ocr needs the optional extra: pip install \"introkiller[ocr]\"" % CLI_NAME)
    episodes = collect(a.inputs)
    groups = by_season(episodes)
    usable = {s: eps for s, eps in groups.items() if len(eps) >= 2}
    if not usable:
        raise SystemExit("%s: need at least two episodes of one season, found %d file(s)." % (CLI_NAME, len(episodes)))
    first = a.inputs[0]
    outdir = a.out or os.path.join(first if os.path.isdir(first) else ".", "skip-times")
    details = os.path.join(outdir, "details")
    os.makedirs(details, exist_ok=True)
    base_cache = a.cache or os.path.join(outdir, "cache")
    media.lowprio()
    pipeline.QUIET = a.quiet
    cfg = {"recap": True} if a.recap else {}
    if a.config:
        cfg.update(json.loads(a.config))
    t0 = time.time()
    times = {"v": 1, "s": {}}
    for season, eps in usable.items():
        cache = cache_dir(base_cache, eps)
        results = pipeline.run_season([e["spec"] for e in eps], [e["name"] for e in eps], cache, None, cfg)
        for e, r in zip(eps, results):
            if a.ocr:
                text_credits(r, e["spec"], cache)
            if a.themes:
                try:
                    added = themes_stage.fill_gaps(
                        e["spec"], r["episode"], themes_stage.ep_no(r["episode"]),
                        a.themes, r["segments"], cache, os.path.join(base_cache, "themes"))
                except Exception as ex:
                    r["rejected"].append({"kind": "themes", "reason": "theme backup skipped: %s" % ex})
                    added = []
                for seg in added:
                    r["segments"].append(seg)
                r["segments"].sort(key=lambda s: s["start"])
            with open(os.path.join(details, r["episode"] + ".json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(r, f, indent=1, ensure_ascii=False)
            if r["segments"]:
                times["s"].setdefault(str(season), {})[str(e["episode"])] = [formats.times_entry(s, r["duration"]) for s in r["segments"]]
            write_sidecars(outdir, r, e["spec"], which)
            print("%s  (%s)" % (r["episode"], clock(r["duration"])))
            for s in r["segments"]:
                print("  %-8s %8s - %8s" % (s["type"], clock(s["start"]), clock(s["end"])))
            if not r["segments"]:
                print("  nothing certain enough to report")
    if "json" in which:
        with open(os.path.join(outdir, "times.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(times, f, separators=(",", ":"))
    for season, eps in groups.items():
        if season not in usable:
            print("skipped season %d: one episode is not enough to compare (%s)" % (season, eps[0]["name"]))
    print("\n%d episode(s) in %.0f s. Output: %s" % (sum(len(v) for v in usable.values()), time.time() - t0, outdir))
    if not a.keep_cache and not a.cache:
        shutil.rmtree(base_cache, ignore_errors=True)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog=CLI_NAME, description="%s: find the skippable parts of TV episodes." % DISPLAY_NAME)
    ap.add_argument("--version", action="version", version="%s %s" % (CLI_NAME, __version__))
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="scan a folder of episodes (or files, or HTTP(S) URLs) and report segment times")
    p.add_argument("inputs", nargs="+", metavar="FOLDER_OR_FILE", help="a folder of episodes, or two or more files or URLs")
    p.add_argument("--out", help="output folder (default: skip-times inside the scanned folder)")
    p.add_argument("--format", default="json", help="comma separated: json, edl, mpv, chapters (default: json)")
    p.add_argument("--ocr", action="store_true", help="also read on-screen text where no credits were found (needs the ocr extra)")
    p.add_argument("--themes", metavar="SLUG",
                   help="fill gaps with official anime opening and ending themes from AnimeThemes.moe "
                        "(GraphQL API, at most 90 requests per minute, cached locally; only this show is fetched, "
                        "never a bulk download). SLUG is the AnimeThemes anime slug for the season. "
                        "A theme result is used only for intro or credits the main pass did not find, "
                        "trimmed 2 s at each end. Anime only.")
    p.add_argument("--recap", action="store_true", help="also look for recaps: a Previously card (needs the ocr extra, skipped cleanly without it) and replayed audio from whole earlier episodes of the same season")
    p.add_argument("--cache", help="keep decoded windows in this folder, for faster repeat runs")
    p.add_argument("--keep-cache", action="store_true", help="do not delete the default cache folder at the end")
    p.add_argument("--config", help="JSON object overriding detection settings (see pipeline.CFG)")
    p.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
    p.set_defaults(run=scan)
    return ap


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = build_parser().parse_args(argv)
    return a.run(a)


if __name__ == "__main__":
    sys.exit(main())
