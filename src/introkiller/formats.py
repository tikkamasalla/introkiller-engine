"""Output formats: times JSON, Kodi EDL, mpv EDL and FFmpeg chapter metadata."""
LABEL = {"recap": "Recap", "intro": "Intro", "credits": "Credits", "preview": "Preview"}
NEVER_AUTO = {"preview"}            # a preview is a choice: formats that can only auto-skip leave it alone


def times_entry(seg, duration):
    return {"t": seg["type"], "a": round(seg["start"] * 1000), "b": round(seg["end"] * 1000), "d": round(duration * 1000)}


def kodi_edl(segments):
    """One line per segment: start, end, action. 3 = commercial break (skipped once), 2 = scene marker (a jump point at its end time)."""
    lines = []
    for s in segments:
        auto = s["type"] not in NEVER_AUTO
        lines.append("%.3f\t%.3f\t%d\n" % (s["start"], s["end"] if auto else s["start"], 3 if auto else 2))
    return "".join(lines)


def _keep_spans(segments, duration):
    """The stretches left once every auto-skippable segment is cut out."""
    spans, t = [], 0.0
    for s in sorted(segments, key=lambda s: s["start"]):
        if s["type"] not in NEVER_AUTO:
            if s["start"] > t:
                spans.append((t, s["start"]))
            t = max(t, s["end"])
    if duration > t:
        spans.append((t, duration))
    return spans


def mpv_edl(path, segments, duration):
    """A playlist of the keep-spans of one file. Open it with mpv and the skipped parts are simply not there."""
    name = "%%%d%%%s" % (len(path.encode("utf-8")), path)
    lines = ["%s,%.3f,%.3f" % (name, a, b - a) for a, b in _keep_spans(segments, duration)]
    return "# mpv EDL v0\n" + "\n".join(lines) + "\n"


def ffmeta(segments, duration):
    """Chapters for the whole file, with "Story" between the named parts."""
    marks, t = [], 0.0
    for s in sorted(segments, key=lambda s: s["start"]):
        if s["start"] > t:
            marks.append((t, s["start"], "Story"))
        marks.append((s["start"], s["end"], LABEL.get(s["type"], s["type"].title())))
        t = max(t, s["end"])
    if duration > t:
        marks.append((t, duration, "Story"))
    body = "".join("\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=%d\nEND=%d\ntitle=%s\n" % (round(a * 1000), round(b * 1000), n)
                   for a, b, n in marks)
    return ";FFMETADATA1\n" + body
