#!/usr/bin/env python3
"""Download the six Pioneer One episodes from archive.org for the demo.

Plain HTTPS, standard library only, resumes partial files, and stops at a hard
byte limit so a surprise on the server side cannot fill a disk.

    python tools/fetch_demo.py DEST_FOLDER
"""
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BYTE_LIMIT = 5 * 1000 ** 3
BASE = "https://archive.org/download/"
EPISODES = [
    ("pioneer-one-ep.-1-earthfall-pilot", "PIONEER ONE Ep.1 Earthfall-Pilot.mp4", "Pioneer One E01.mp4"),
    ("pioneer-one-ep.-2-the-man-from-mars_202608", "PIONEER ONE Ep.2 The Man From Mars.mp4", "Pioneer One E02.mp4"),
    ("pioneer-one-ep.-3-alone-in-the-night", "PIONEER ONE Ep.3 Alone in the Night.mp4", "Pioneer One E03.mp4"),
    ("pioneer-one-ep.-4-triangular-diploma", "PIONEER ONE Ep.4 Triangular Diploma.mp4", "Pioneer One E04.mp4"),
    ("pioneer-one-ep.-5-sea-change", "PIONEER ONE Ep.5 Sea Change.mp4", "Pioneer One E05.mp4"),
    ("pioneer-one-ep.-6-war-of-the-world-3mp-4_202608", "PIONEER ONE Ep.6 War of the World3mp4.mp4", "Pioneer One E06.mp4"),
]


def fetch(url, path, spent):
    """Download url to path, resuming a partial file. Returns the bytes used by this call."""
    have = path.stat().st_size if path.exists() else 0
    req = urllib.request.Request(url, headers={"Range": "bytes=%d-" % have} if have else {})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as err:
        if err.code == 416:        # already complete
            return 0
        raise
    used = 0
    with resp, open(path, "ab" if have and resp.status == 206 else "wb") as out:
        while True:
            block = resp.read(1 << 20)
            if not block:
                return used
            if spent + used + len(block) > BYTE_LIMIT:
                raise SystemExit("byte limit reached after %d bytes, stopping" % (spent + used))
            out.write(block)
            used += len(block)


def main():
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "pioneer-one")
    dest.mkdir(parents=True, exist_ok=True)
    spent = 0
    for item, remote, local in EPISODES:
        url = BASE + urllib.parse.quote(item) + "/" + urllib.parse.quote(remote)
        spent += fetch(url, dest / local, spent)
        print("%-24s %6.1f MB   total this run %.2f GB" % (local, (dest / local).stat().st_size / 1e6, spent / 1e9), flush=True)


if __name__ == "__main__":
    main()
