#!/usr/bin/env python3
"""Measure how much of each second of an episode is shared with the other episodes of its season.

Uses the engine's own audio alignment, nothing else. For every pair of episodes it finds the matching
stretches (correlation 0.85 or better), then counts, for each second, how many other episodes share it.
The result is the raw material of the heat strip in the README.

    python tools/build_heat.py FOLDER --title "My Show S1" --out data/heat_myshow.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

from introkiller import align, media
from introkiller.cli import collect

WINDOW = 300.0
NCC_MIN = 0.85


def shared_seconds(signals):
    """signals: list of prepped mono arrays. Returns, per episode, the count of other episodes sharing each second."""
    n = len(signals)
    size = max(len(x) for x in signals)
    nfft = 1 << int(np.ceil(np.log2(2 * size)))
    specs = [align.Spec(x, nfft) for x in signals]
    counts = [np.zeros(int(len(x) / media.SR) + 1, np.int32) for x in signals]
    for i in range(n):
        for j in range(i + 1, n):
            mark_i = np.zeros_like(counts[i], bool)
            mark_j = np.zeros_like(counts[j], bool)
            for lag, _peak, _noise in align.top_lags(specs[i], specs[j], k=3):
                for st in align.stretches(signals[i], signals[j], lag):
                    if st["ncc"] < NCC_MIN:
                        continue
                    mark_i[int(st["start"]):int(np.ceil(st["end"]))] = True
                    a, b = st["start"] - lag / media.SR, st["end"] - lag / media.SR
                    mark_j[max(0, int(a)):int(np.ceil(b))] = True
            counts[i] += mark_i
            counts[j] += mark_j
    return counts


def to_digits(count, others):
    """One digit per second: 0 = nobody shares it, 9 = every other episode does."""
    return "".join(str(int(round(9 * c / others))) for c in count)


def build(title, labels, heads, tails, durations):
    head = shared_seconds([align.prep(x) for x in heads])
    tail = shared_seconds([align.prep(x) for x in tails])
    others = len(labels) - 1
    rows = [{"label": lab, "duration": d, "head": to_digits(h, others), "tail": to_digits(t, others)}
            for lab, d, h, t in zip(labels, durations, head, tail)]
    return {"title": title, "window_s": WINDOW, "others": others, "rows": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder")
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="heat-cache")
    a = ap.parse_args()
    media.lowprio()
    labels, heads, tails, durs = [], [], [], []
    for e in collect([a.folder]):
        src = media.Source(e["spec"], e["name"], a.cache)
        d = src.duration
        labels.append("E%d" % e["episode"] if e["episode"] else e["name"])
        durs.append(round(d, 3))
        heads.append(src.audio(0.0, WINDOW))
        tails.append(src.audio(d - WINDOW, d))
    if len(labels) < 2:
        sys.exit("need at least two episodes")
    Path(a.out).write_text(json.dumps(build(a.title, labels, heads, tails, durs)) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
