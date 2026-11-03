#!/usr/bin/env python3
"""Build the Pioneer One demo assets from a finished scan: the timeline data and two small real frames.

    python tools/fetch_demo.py pioneer-one
    introkiller scan pioneer-one --recap --ocr --out pioneer-out
    python tools/build_demo_assets.py pioneer-one pioneer-out

Needs the ocr extra, because the credits frame shows the text boxes the detector saw.
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from introkiller.ocr_credits import RapidDet

ROOT = Path(__file__).resolve().parent.parent
TITLE_FRAME = ("Pioneer One E05.mp4", 215.0)
CREDITS_FRAME = ("Pioneer One E03.mp4", 1860.0)


def grab(video, t, width):
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % t, "-i", str(video), "-frames:v", "1",
           "-vf", "scale=%d:-2" % width, "-f", "image2pipe", "-vcodec", "png", "-"]
    data = subprocess.run(cmd, capture_output=True, check=True).stdout
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def main():
    videos, scan = Path(sys.argv[1]), Path(sys.argv[2])
    episodes = []
    for f in sorted((scan / "details").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        episodes.append({"label": "E" + f.stem[-2:].lstrip("0"), "duration": d["duration"],
                         "segments": [{"type": s["type"], "start": s["start"], "end": s["end"]} for s in d["segments"]]})
    demo = {"caption": "Six episodes of Pioneer One, drawn to scale.", "episodes": episodes}
    (ROOT / "data" / "demo_pioneer_one.json").write_text(json.dumps(demo, indent=1) + "\n", encoding="utf-8", newline="\n")

    name, t = TITLE_FRAME
    cv2.imwrite(str(ROOT / "assets" / "demo-title.jpg"), grab(videos / name, t, 480), [cv2.IMWRITE_JPEG_QUALITY, 80])
    name, t = CREDITS_FRAME
    det = RapidDet()
    small = cv2.cvtColor(grab(videos / name, t, 320), cv2.COLOR_BGR2GRAY)
    frame = grab(videos / name, t, 480)
    k = frame.shape[1] / small.shape[1]
    boxes = det.boxes(small)
    for x0, y0, x1, y1 in boxes:
        cv2.rectangle(frame, (int(x0 * k) - 2, int(y0 * k) - 2), (int(x1 * k) + 2, int(y1 * k) + 2), (40, 150, 240), 1, cv2.LINE_AA)
    cv2.imwrite(str(ROOT / "assets" / "demo-credits.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    print("text boxes on the credits frame:", len(boxes))


if __name__ == "__main__":
    main()
