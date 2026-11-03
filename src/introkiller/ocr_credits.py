"""On-screen text credits detector (optional stage, needs the "ocr" extra).

Finds an end-credits roll from the text boxes on screen, for episodes where
audio matching across references fails (music changes every episode, a single
reference, credits over near-silence).  Detection only (PP-OCRv4 boxes via
RapidOCR/ONNX); recognition is used at most once, for the prose-card guard.

Hard rule, inherited from the pipeline: NEVER a wrong skip.  A returned
segment may start late or be absent, but its start is never placed before the
first frame that itself shows a credit-like text layout.  Uncertain -> None.

How it works
------------
1. Coarse pass: keyframes only (-skip_frame nokey) at 320x180 gray over the
   tail window (last 450 s, 900 s for files over 65 min) plus 90 s of story
   lead before it.  Exact PTS via -copyts/-fps_mode passthrough/showinfo --
   the same variable-frame-rate care as media.Source.grab; frame i is times[i], always.
2. Pure row logic (find_run) on rows (t, boxes, mean_luma):
   static-overlay removal, subtitle/lower-third filter (all frames, row
   clusters), wide-prose dark-card rejection, credit-frame classification
   (dark: any text; lit: >=3 aligned boxes spanning rows), runs joined
   across <=12 s gaps that hold no sustained text-free lit story,
   story-wide text/caption vetoes, positional gates, static head-card skip.
3. Refine pass: native-rate 320x180 decode around each edge, detector run on
   a 1 fps subsample (chosen by PTS, not by frame index).  Start walks back
   only over consecutive credit seconds whose text band overlaps the run's,
   then pins forward to the first non-black native frame on a hard cut or
   a black->picture transition at/after that second.  End is the end of
   text, not the end of file, when a scene/preview follows.  No 640x360
   retry is skipped silently: it runs once when the 320 pass finds nothing.

Credits over story pictures: only dense, aligned, multi-row layout counts
on lit frames, and the start is the first such second, so story under the
early sparse cards is never skipped; the price is a late start there.

Public entry point (one function):

    detect_credits(source, duration=None, name="ep", cache_dir=None,
                   cfg=None, detector=None) -> dict | None

source is a local path, an http(s) URL, or any object with .path() and
.duration (e.g. media.Source).  Returns
{"type": "credits", "start": s, "end": s, "method": "ocr_credits",
 "detail": {...gates, counts, cpu_s, est_bytes...}} or None (no segment;
detail of the rejection is in detect_credits.last_detail for logging).
Only ffmpeg/ffprobe + numpy are needed at import; RapidOCR loads lazily.
"""
import json
import os
import re
import subprocess
import time

import numpy as np

NOWIN = (0x08000000 | 0x4000) if os.name == "nt" else 0   # Windows: CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS
DET_W, DET_H = 320, 180
CFG = {
    "tail_s": 450.0,          # tail scanned for files <= 65 min
    "tail_long_s": 900.0,     # ... and for longer files / films
    "long_file_s": 3900.0,
    "story_lead_s": 90.0,     # extra story decoded before the tail (overlay + veto stats)
    "min_story_before_s": 30.0,
    "gap_s": 12.0,            # max gap joined inside a run (24 s was too loose here)
    "min_run_s": 15.0,
    "max_run_s": 700.0,
    "min_credit_frames": 5,
    "min_mean_boxes": 2.0,
    "dark_luma": 32.0,
    "lit_min_boxes": 3,
    "max_after_s": 120.0,     # credits are terminal: >120 s after the last credit text means mid-episode scene text (previews measured <=32 s)
    "text_all_share": 0.40,   # story-wide text veto
    "captions_share": 0.25,   # caption-chain veto (with the run-shape conditions)
    "retry_640": True,
    "dense_rescan_s": 240.0,  # 1 fps rescan of the last minutes when keyframes are too sparse to form a run
    "prose_check": True,      # one recognition call on a static dark head card, if a recogniser is available
    "ffmpeg_timeout_s": 900,
}


# --------------------------------------------------------------------------
# Box helpers (boxes are (x0, y0, x1, y1) in 320x180 coordinates)
# --------------------------------------------------------------------------
def _row_clusters(boxes, tol=6):
    """Group boxes into text rows by vertical centre (within tol px of the row mean)."""
    rows = []                                   # [boxes, centre_sum]
    for b in sorted(boxes, key=lambda b: ((b[1] + b[3]) / 2.0, b[0])):
        c = (b[1] + b[3]) / 2.0
        if rows and abs(c - rows[-1][1] / len(rows[-1][0])) <= tol:
            rows[-1][0].append(b)
            rows[-1][1] += c
        else:
            rows.append([[b], c])
    return [r[0] for r in rows]


def _subtitle_only(boxes):
    """True when the frame's text is 1-2 bottom rows: dialogue subtitle or lower-third.

    Runs on dark frames too (a night scene's subtitles are the classic way to
    glue story onto a black roll).  A bottom card with two separated columns
    in some row (role | name) is not a subtitle and survives."""
    if not boxes or any(b[1] < 0.72 * DET_H for b in boxes):
        return False
    rows = _row_clusters(boxes)
    if len(rows) > 2:
        return False
    two_col = lambda row: len(row) >= 2 and max(b[0] for b in row) - min(b[2] for b in row) >= 0.12 * DET_W
    if len(rows) >= 2 and all(two_col(r) for r in rows):
        return False                         # bottom credit card: role|name on every row
    return True


def _aligned(boxes):
    """At least 3 boxes take part in a shared left-edge or centre column (tol 8/10 px).

    Credit layouts are typeset: left-aligned, centre-aligned, or two columns.
    Signs, screens and scenery text on one frame almost never share an axis."""
    def participants(vals, tol):
        ok = [False] * len(vals)
        for i, v in enumerate(vals):
            if any(j != i and abs(vals[j] - v) <= tol for j in range(len(vals))):
                ok[i] = True
        return sum(ok)
    lefts = [float(b[0]) for b in boxes]
    centres = [(b[0] + b[2]) / 2.0 for b in boxes]
    return participants(lefts, 8) >= 3 or participants(centres, 10) >= 3


def _wide_prose_shape(boxes):
    """Full-width single-column lines: the shape of an epilogue paragraph card.

    Credit cards are narrower or two-column.  Static-ness is checked by the
    caller against the neighbouring frames (a scroll moves, prose sits)."""
    if not boxes or len(boxes) > 6 or len(_row_clusters(boxes)) != len(boxes):
        return False
    widths = sorted(b[2] - b[0] for b in boxes)
    return widths[len(widths) // 2] >= 0.48 * DET_W


def _same_card(a, b):
    """Same static card: equal count, each box matched within a few px."""
    if not a or len(a) != len(b):
        return False
    return all(abs(x[0] - y[0]) <= 4 and abs(x[1] - y[1]) <= 3 and abs(x[2] - y[2]) <= 4
               for x, y in zip(sorted(a), sorted(b)))


def _overlay_keys(story_rows):
    """Box positions that sit still across the story lead: bugs, tickers, timecodes."""
    if len(story_rows) < 4:
        return set()
    hits = {}
    for _t, boxes, _m in story_rows:
        seen = {(b[0] // 8, b[1] // 8, b[2] // 8, b[3] // 8) for b in boxes}
        for k in seen:
            hits[k] = hits.get(k, 0) + 1
    return {k for k, n in hits.items() if n >= 4 and n >= 0.25 * len(story_rows)}


def _drop_overlays(boxes, keys):
    if not keys:
        return boxes
    return tuple(b for b in boxes if (b[0] // 8, b[1] // 8, b[2] // 8, b[3] // 8) not in keys)


def _is_credit_frame(mean, boxes, cfg):
    if not boxes:
        return False
    if mean < cfg["dark_luma"]:
        return True                          # any real text on a dark card/roll
    if len(boxes) < cfg["lit_min_boxes"]:
        return False
    span = max(b[3] for b in boxes) - min(b[1] for b in boxes)
    return (span >= 0.18 * DET_H or len(_row_clusters(boxes)) >= 2) and _aligned(boxes)


# --------------------------------------------------------------------------
# Pure row logic: rows -> coarse segment (unit-tested without video or OCR)
# --------------------------------------------------------------------------
def find_run(rows, duration, cfg=None):
    """rows: [(t, boxes, mean_luma)] sorted by t, covering story lead + tail.

    Returns {"start","end","detail"} for the last acceptable credit run, or
    None.  detail["reject"] names the gate when a run existed but was refused."""
    cfg = {**CFG, **(cfg or {})}
    rows = sorted(rows, key=lambda r: r[0])   # emission order is not PTS order on some encodes
    detail = {"rows": len(rows)}
    if len(rows) < 10 or duration <= 0:
        detail["reject"] = "too_few_rows"
        return None
    tail_s = cfg["tail_long_s"] if duration > cfg["long_file_s"] else cfg["tail_s"]
    tail_start = max(0.0, duration - tail_s)
    keys = _overlay_keys([r for r in rows if r[0] < tail_start])
    detail["overlay_boxes"] = len(keys)
    # clean: drop overlays, drop subtitle-only frames' boxes, drop static wide-prose
    # cards.  share_boxes keeps overlays: the story-wide veto must see raw text
    # (a static sign removed as "overlay" must not make a captioned show look clean).
    stage, share_boxes = [], []
    for t, boxes, mean in rows:
        raw = () if _subtitle_only(tuple(boxes)) else tuple(boxes)
        share_boxes.append(raw)
        stage.append(_drop_overlays(raw, keys))
    clean = []
    for i, (t, _boxes, mean) in enumerate(rows):
        b = stage[i]
        if b and mean < cfg["dark_luma"] and _wide_prose_shape(b):
            neigh = [stage[j] for j in (i - 1, i + 1) if 0 <= j < len(stage)]
            if any(_same_card(b, n) for n in neigh):
                b = ()
        clean.append((t, b, mean))
    credit = [_is_credit_frame(m, b, cfg) for _t, b, m in clean]
    detail["credit_frames"] = int(sum(credit))
    # runs: join credit frames across gaps <= gap_s with no sustained text-free lit story
    runs, cur = [], []
    for i, (t, b, m) in enumerate(clean):
        if not credit[i]:
            continue
        if cur:
            j = cur[-1]
            gap = t - clean[j][0]
            between = [k for k in range(j + 1, i) if not credit[k]]
            lit_free = [k for k in between if clean[k][2] >= cfg["dark_luma"] and not clean[k][1]]
            # A lit text-free stretch of >=4 s (first such frame to the next credit
            # frame) is story and breaks the run; a shorter one is a card fade.
            # Measured in seconds, not frames: keyframe spacing is encoder-chosen.
            sustained = bool(lit_free) and t - clean[lit_free[0]][0] >= 4.0
            if gap > cfg["gap_s"] or sustained:
                runs.append(cur)
                cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    detail["runs"] = len(runs)
    passing = []                             # (run, start_i) for every run passing all gates
    best = None
    for run in runs:                         # keep the LAST run that passes every gate
        t0, t1 = clean[run[0]][0], clean[run[-1]][0]
        span = t1 - t0
        mean_boxes = float(np.mean([len(clean[i][1]) for i in run])) if run else 0.0
        if len(run) < cfg["min_credit_frames"] or span < cfg["min_run_s"] or mean_boxes < cfg["min_mean_boxes"]:
            detail.setdefault("reject", "run_too_weak")
            continue
        if t0 < max(0.5 * duration, tail_start) or span > cfg["max_run_s"]:
            detail.setdefault("reject", "positional")
            continue
        if duration - t1 > cfg["max_after_s"]:
            detail.setdefault("reject", "story_after")
            continue
        pre = [i for i in range(run[0]) if clean[i][0] < t0]
        if not pre or t0 - clean[pre[0]][0] < cfg["min_story_before_s"]:
            detail.setdefault("reject", "no_story_before")
            continue
        share = float(np.mean([1.0 if share_boxes[i] else 0.0 for i in pre])) if pre else 0.0
        dark_in_run = any(clean[i][2] < cfg["dark_luma"] for i in run)
        if share >= cfg["text_all_share"]:
            detail["reject"] = "text_all_through"
            continue
        if share >= cfg["captions_share"] and not dark_in_run and mean_boxes < 3.5:
            detail["reject"] = "captions_all_through"
            continue
        # Typeset credits keep side margins; lit scene text touching BOTH frame
        # edges (signs, tickers, edge-cropped graphics) is never a roll.  Lit
        # only: a dark roll is unambiguous whatever its width.  Fail-safe cost:
        # a wide lit roll with an edge artifact is missed, never mislabelled.
        boxes_run = [b for i in run for b in clean[i][1]]
        if (not dark_in_run and boxes_run and min(b[0] for b in boxes_run) <= 12
                and max(b[2] for b in boxes_run) >= DET_W - 12):
            detail["reject"] = "edge_to_edge_text"
            continue
        # static head cards (epilogue line glued to the roll): skip at most 2,
        # only while what remains is still a full run -- a late start, never early.
        start_i = 0
        for _ in range(2):
            head = [run[start_i]]
            while (start_i + len(head) < len(run)
                   and _same_card(clean[run[start_i + len(head)]][1], clean[head[0]][1])):
                head.append(run[start_i + len(head)])
            nxt = start_i + len(head)
            if nxt >= len(run):
                break
            head_span = clean[head[-1]][0] - clean[head[0]][0]
            head_gap = clean[run[nxt]][0] - clean[head[-1]][0]
            rest_span = t1 - clean[run[nxt]][0]
            lone = len(head) == 1 and head_gap >= 4.0 and len(clean[run[nxt]][1]) >= 3
            if (len(clean[head[0]][1]) <= 2 and (head_span >= 3.0 or lone) and head_gap >= 1.0
                    and rest_span >= cfg["min_run_s"] and clean[head[0]][2] < cfg["dark_luma"]):
                start_i = nxt
            else:
                break
        xs = [b for i in run for b in clean[i][1]]
        passing.append((run, start_i))
        best = {"start": clean[run[start_i]][0], "end": t1,
                "detail": {**detail, "run_frames": len(run), "mean_boxes": round(mean_boxes, 2),
                           "pre_text_share": round(share, 3), "head_cards_skipped": start_i,
                           "band": [int(min(b[0] for b in xs)), int(max(b[2] for b in xs))] if xs else [0, DET_W],
                           "dark_in_run": bool(dark_in_run), "reject": None}}
    # Same-roll merge: a main crawl and later dubbing slates are one roll when
    # only black / credit cards / a logo flash separate them (<=45 s, and no
    # sustained text-free lit story in between).  Never merges across story.
    if best is not None and len(passing) >= 2:
        merged = 0
        cur_start = best["start"]
        for run, start_i in reversed(passing[:-1]):
            prev_end_i = run[-1]
            gap = cur_start - clean[prev_end_i][0]
            if gap > 45.0:
                break
            between = [k for k in range(prev_end_i + 1, len(clean)) if clean[k][0] < cur_start]
            lit_free = [k for k in between if clean[k][2] >= cfg["dark_luma"] and not clean[k][1]]
            sustained = bool(lit_free) and cur_start - clean[lit_free[0]][0] >= 4.0
            if sustained:
                break
            cur_start = clean[run[start_i]][0]
            merged += 1
        if merged:
            best["start"] = cur_start
            best["detail"]["merged_runs"] = merged
            xs = [b for run, _si in passing[-(merged + 1):] for i in run for b in clean[i][1]]
            if xs:
                best["detail"]["band"] = [int(min(b[0] for b in xs)), int(max(b[2] for b in xs))]
    if best is None:
        find_run.last_detail = detail
    return best


def is_prose_text(lines):
    """Recognised lines of a static dark card: True for epilogue prose.

    A sentence ending in '.' with >=4 words (>=3 words/line), or any line of
    >=7 words mostly lowercase.  Initialisms (p.g.a., U.S.) are not sentences."""
    words_per = []
    for ln in lines:
        w = ln.split()
        words_per.append(len(w))
        if len(w) >= 7 and sum(1 for x in w if x[:1].islower()) > 0.5 * len(w):
            return True
    joined = " ".join(lines)
    for sent in re.split(r"\.\s+", joined):
        s = sent.strip()
        if not s or re.fullmatch(r"(?:[^\W\d_]{1,2}\.){2,}", s.replace(" ", "")):
            continue
        if s.endswith(".") or "." in s:
            n = len(s.split())
            if n >= 4 and (not words_per or n / max(1, len(lines)) >= 3.0):
                return True
    return False


# --------------------------------------------------------------------------
# Decoding (exact PTS: -copyts + passthrough + showinfo)
# --------------------------------------------------------------------------
def _probe(path, timeout=180):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
                        "-of", "json", path], capture_output=True, creationflags=NOWIN, timeout=timeout)
    j = json.loads(p.stdout.decode("utf-8", "replace") or "{}").get("format") or {}
    return float(j.get("duration") or 0), float(j.get("size") or 0)


def decode_frames(path, a, b, w=DET_W, h=DET_H, keyframes_only=False, timeout=900):
    """(times, frames[n,h,w] uint8 gray) for a <= pts <= b.  Never by frame index."""
    vf = "scale=%d:%d:flags=neighbor,format=gray,showinfo" % (w, h)
    cmd = ["ffmpeg", "-hide_banner", "-nostdin"]
    if keyframes_only:
        cmd += ["-skip_frame", "nokey"]
    cmd += ["-copyts", "-ss", "%.3f" % a, "-i", path, "-to", "%.3f" % b, "-an", "-sn",
            "-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=NOWIN, timeout=timeout)
    raw = np.frombuffer(p.stdout, np.uint8)
    n = len(raw) // (w * h)
    if n == 0:
        return np.zeros(0), np.zeros((0, h, w), np.uint8)
    fr = raw[:n * w * h].reshape(n, h, w)
    ts = np.array([float(m) for m in re.findall(r"pts_time:\s*(-?[\d.]+)",
                                                 p.stderr.decode(errors="replace"))][:n])
    fr = fr[:len(ts)]
    keep = (ts >= a - 1e-6) & (ts <= b + 1e-6)
    ts, fr = ts[keep], fr[keep]
    order = np.argsort(ts, kind="stable")   # decoder may emit keyframe pairs out of PTS order
    return ts[order], fr[order]


def _is_black(fr):
    return (fr.mean(axis=(1, 2)) <= 22.0) & (np.percentile(fr, 99, axis=(1, 2)) <= 40.0)


def _cut_diff(fr):
    if len(fr) < 2:
        return np.zeros(len(fr))
    small = fr[:, ::5, ::5].astype(np.int16)          # 64x36-equivalent mean abs diff
    return np.concatenate([[0.0], np.abs(small[1:] - small[:-1]).mean(axis=(1, 2))])


class RapidDet:
    """PP-OCRv4 box detector (RapidOCR/ONNX).  Boxes in the frame's own pixels.

    det_limit_side_len=640/'max' is load-bearing: the default upscales the
    short side to 736 and costs ~550 ms/frame at 320x180; capped, ~26 ms
    (measured on one 8-thread desktop CPU)."""
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self._eng = RapidOCR(det_limit_side_len=640, det_limit_type="max")
        self.calls = 0
        self.cpu_s = 0.0

    def boxes(self, gray):
        t0 = time.perf_counter()
        res, _el = self._eng(gray, use_det=True, use_cls=False, use_rec=False)
        self.cpu_s += time.perf_counter() - t0
        self.calls += 1
        out = []
        for poly in res or []:
            xs = [int(round(p[0])) for p in poly]
            ys = [int(round(p[1])) for p in poly]
            out.append((min(xs), min(ys), max(xs), max(ys)))
        return tuple(out)

    def recognize(self, gray):
        res, _el = self._eng(gray, use_det=True, use_cls=False, use_rec=True)
        return [r[1] for r in res or []]


def rows_from_frames(ts, fr, detector, scale=1):
    rows = []
    for i in range(len(ts)):
        b = detector.boxes(fr[i])
        if scale != 1:
            b = tuple((x0 // scale, y0 // scale, x1 // scale, y1 // scale) for x0, y0, x1, y1 in b)
        rows.append((float(ts[i]), b, float(fr[i].mean())))
    return rows


def _subsample_1fps(ts):
    """Indices of the first frame in each whole second (by PTS)."""
    idx, seen = [], -1
    for i, t in enumerate(ts):
        if int(t) != seen:
            seen = int(t)
            idx.append(i)
    return idx


def _frame_credit(fr_i, boxes, cfg, band=None):
    if _subtitle_only(boxes):
        return False
    if not _is_credit_frame(float(fr_i.mean()), boxes, cfg):
        return False
    if band is not None and boxes:
        lo, hi = min(x[0] for x in boxes), max(x[2] for x in boxes)
        overlap = max(0, min(hi, band[1]) - max(lo, band[0]))
        return overlap >= 0.5 * max(1, hi - lo)
    return True


def refine_start(path, coarse, band, detector, cfg, span=27.0):
    """First credit second at 1 fps, pinned forward on exact native frames.

    Never returns a time before the first verified credit-layout second; the
    walk back stops at the first non-credit second or when the text leaves
    the run's horizontal band."""
    a, b = max(0.0, coarse - span + 2.0), coarse + 3.0
    ts, fr = decode_frames(path, a, b, timeout=cfg["ffmpeg_timeout_s"])
    if len(ts) == 0:
        return coarse, "coarse_only"
    credit_at = {}
    for i in _subsample_1fps(ts):
        credit_at[float(ts[i])] = _frame_credit(fr[i], detector.boxes(fr[i]), cfg, band)
    secs = sorted(credit_at)
    near = [s for s in secs if s <= coarse + 1.0 and credit_at[s]]
    anchor = max(near) if near else next((s for s in secs if credit_at[s]), None)
    if anchor is None:
        return coarse, "coarse_only"
    first = anchor
    for s in sorted((x for x in secs if x < anchor), reverse=True):
        if credit_at[s] and first - s <= 1.6:
            first = s
        else:
            break
    blk, diff = _is_black(fr), _cut_diff(fr)
    for i in range(len(ts)):
        if ts[i] < first - 1e-6 or ts[i] > coarse + 2.0 or blk[i]:
            continue
        if i == 0 or diff[i] >= 18.0 or blk[i - 1] or ts[i] >= coarse:
            return float(ts[i]), "cut" if diff[i] >= 18.0 else "black_end"
    return float(first), "first_text_second"


def _scan_last(samples, cfg):
    """Last credit second in [(t, is_credit, mean_luma)] at ~1 fps, plus whether
    sustained lit story followed it.  The scan STOPs at the first sustained
    text-free lit stretch (>=4 s, the find_run story rule) or at a >gap_s jump
    between credit seconds: text after story (preview, next-episode card,
    subtitled scene) must never move the end.  The old scan kept the LAST
    credit-like frame in the whole 200 s window, so one preview card 30 s
    after the roll moved the end to EOF / last_text+1s past the true end."""
    last, story_after, lit_since = None, False, None
    for t, is_credit, mean in samples:
        if is_credit:
            if last is not None and t - last > cfg["gap_s"]:
                story_after = True
                break
            last, lit_since = t, None
        elif last is not None and mean >= cfg["dark_luma"]:
            lit_since = t if lit_since is None else lit_since
            if t - lit_since >= 3.0:     # ~4 consecutive lit text-free seconds
                story_after = True
                break
    return last, story_after


def refine_end(path, last_credit, duration, detector, cfg, band=None):
    """End of text: EOF only when no lit scene follows the last credit second."""
    a = max(0.0, last_credit - 3.0)
    b = min(duration, a + 200.0)
    ts, fr = decode_frames(path, a, b, timeout=cfg["ffmpeg_timeout_s"])
    if len(ts) == 0:
        return duration, "eof_no_frames"
    samples = [(float(ts[i]), _frame_credit(fr[i], detector.boxes(fr[i]), cfg, band),
                float(fr[i].mean())) for i in _subsample_1fps(ts)]
    last, story_after = _scan_last(samples, cfg)
    if last is None:
        return min(duration, last_credit + 1.0), "coarse_fallback"
    if samples and samples[-1][0] - last >= 4.0:
        story_after = True          # anything (even dark story) after the text is not credits
    if not story_after and duration - last <= 30.0:
        return duration, "eof"
    blk, diff = _is_black(fr), _cut_diff(fr)
    run_start = None
    for i in range(len(ts)):
        if ts[i] < last - 1e-6 or ts[i] > last + 2.5:
            continue
        if diff[i] >= 18.0:
            return float(ts[i]), "cut"
        if blk[i]:
            run_start = ts[i] if run_start is None else run_start
            if ts[i] - run_start >= 0.25:
                return float(run_start), "black"
        else:
            run_start = None
    return min(duration, last + 1.0), "last_text_plus_1s"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def detect_credits(source, duration=None, name="ep", cache_dir=None, cfg=None, detector=None):
    cfg = {**CFG, **(cfg or {})}
    t_wall = time.perf_counter()
    path = source.path() if hasattr(source, "path") else str(source)
    if duration is None and hasattr(source, "duration"):
        duration = float(source.duration)
    size = 0.0
    try:
        d2, size = _probe(path)
        duration = duration or d2
    except Exception:
        pass
    if not duration:
        detect_credits.last_detail = {"reject": "no_duration"}
        return None
    det = detector or RapidDet()
    tail_s = cfg["tail_long_s"] if duration > cfg["long_file_s"] else cfg["tail_s"]
    win_a = max(0.0, duration - tail_s - cfg["story_lead_s"])
    decoded_s, rows, scale, found = 0.0, None, 1, None
    cache_fn = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_fn = os.path.join(cache_dir, "%s_ocr_rows.json" % name)
        if os.path.exists(cache_fn):
            rows = [(float(t), tuple(tuple(x) for x in bx), float(m))
                    for t, bx, m in json.load(open(cache_fn))]
    for sc in ((1, 2) if cfg["retry_640"] else (1,)):
        scale = sc
        if rows is None or sc > 1:
            ts, fr = decode_frames(path, win_a, duration, w=DET_W * sc, h=DET_H * sc,
                                   keyframes_only=True, timeout=cfg["ffmpeg_timeout_s"])
            decoded_s += duration - win_a
            rows = rows_from_frames(ts, fr, det, scale=sc)
            if sc == 1 and cache_fn:
                json.dump(rows, open(cache_fn, "w"))
        found = find_run(rows, duration, cfg)
        if found:
            break
    if not found and getattr(find_run, "last_detail", {}).get("credit_frames", 0) >= 3:
        # Keyframe cadence is an encoder choice, not a property of the credits:
        # a 10 s GOP fragments any run.  Rescan the last minutes at 1 fps by PTS.
        dense_a = max(win_a, duration - cfg["dense_rescan_s"])
        ts, fr = decode_frames(path, dense_a, duration, timeout=cfg["ffmpeg_timeout_s"])
        decoded_s += duration - dense_a
        if len(ts):
            idx = _subsample_1fps(ts)
            dense = rows_from_frames(ts[idx], fr[idx], det)
            rows = [r for r in rows if r[0] < dense_a] + dense
            found = find_run(rows, duration, cfg)
            if found:
                found["detail"]["dense_rescan"] = True
    if not found:
        detect_credits.last_detail = getattr(find_run, "last_detail", {})
        return None
    detail = dict(found["detail"])
    detail["scale"] = scale
    start, how_s = refine_start(path, found["start"], detail["band"], det, cfg)
    decoded_s += 30.0
    if start < found["start"] - 27.0 or start > found["start"] + 3.0:
        start, how_s = found["start"], "coarse_clamped"
    if cfg["prose_check"] and hasattr(det, "recognize"):
        try:
            ts1, fr1 = decode_frames(path, start, start + 2.0, w=640, h=360,
                                     timeout=cfg["ffmpeg_timeout_s"])
            decoded_s += 2.0
            if len(ts1) and float(fr1[0].mean()) < cfg["dark_luma"]:
                lines = det.recognize(fr1[len(fr1) // 2])
                detail["head_card_text"] = lines[:8]
                if lines and is_prose_text(lines):
                    detail["prose_head"] = True
                    nxt, _h = refine_start(path, start + 12.0, detail["band"], det, cfg, span=13.0)
                    if start < nxt <= start + 30.0:
                        start, how_s = nxt, "past_prose"
                    else:
                        detect_credits.last_detail = {**detail, "reject": "prose_only"}
                        return None
        except Exception as exc:                # recognition is a guard layer, never required
            detail["prose_check_error"] = type(exc).__name__
    end, how_e = refine_end(path, found["end"], duration, det, cfg, band=detail.get("band"))
    decoded_s += min(200.0, duration - max(0.0, found["end"] - 3.0))
    if end <= start + 1.0 or end - start > cfg["max_run_s"]:
        detect_credits.last_detail = {**detail, "reject": "bad_refined_span"}
        return None
    detail.update({"start_how": how_s, "end_how": how_e, "coarse_start": found["start"],
                   "coarse_end": found["end"], "det_calls": getattr(det, "calls", None),
                   "det_cpu_s": round(getattr(det, "cpu_s", 0.0), 2),
                   "wall_s": round(time.perf_counter() - t_wall, 2),
                   "decoded_window_s": round(decoded_s, 1),
                   "est_bytes": int(size / duration * decoded_s) if size else None,
                   "duration": duration})
    return {"type": "credits", "start": round(float(start), 3), "end": round(float(end), 3),
            "method": "ocr_credits", "detail": detail}
