"""Download theme ogg files politely, decode to 8 kHz mono f32, trim silence."""
import json
import os
import subprocess
import time
import urllib.request

import numpy as np

from .settings import API_DELAY_S, SILENCE_DB, SR, UA


def fetch(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())


def to_f32(ogg, f32):
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", ogg, "-ac", "1", "-ar", str(SR),
           "-f", "f32le", f32]
    subprocess.run(cmd, check=True)


def trim_silence(x, db=SILENCE_DB):
    thr = 10.0 ** (db / 20.0)
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return 0, len(x), x
    a, b = int(idx[0]), int(idx[-1]) + 1
    return a, b, x[a:b]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dir", required=True)
    a = ap.parse_args()
    os.makedirs(a.dir, exist_ok=True)
    man = json.load(open(a.manifest, encoding="utf-8"))
    items = [(s, t) for s, v in man.items() for t in v["themes"]]
    print("themes=%d" % len(items))
    total = 0
    for i, (slug, t) in enumerate(items):
        base = "%s-%s" % (slug, t["slug"])
        ogg = os.path.join(a.dir, base + ".ogg")
        f32 = os.path.join(a.dir, base + ".f32")
        meta = os.path.join(a.dir, base + ".json")
        if i:
            time.sleep(API_DELAY_S)
        if not os.path.exists(ogg):
            fetch(t["audio"], ogg)
        if not os.path.exists(f32):
            to_f32(ogg, f32)
        x = np.fromfile(f32, "<f4")
        la, lb, core = trim_silence(x)
        np.save(os.path.join(a.dir, base + ".npy"), core)
        m = {"ogg": os.path.basename(ogg), "ogg_bytes": os.path.getsize(ogg),
             "sr": SR, "total": len(x), "lead": la, "trail": len(x) - lb,
             "core": len(core), "audio": t["audio"]}
        json.dump(m, open(meta, "w", encoding="utf-8"), indent=1)
        total += m["ogg_bytes"]
        print("%d/%d %s core=%.1fs ogg=%d" % (i + 1, len(items), base, len(core) / SR, m["ogg_bytes"]))
    print("ogg_bytes_total=%d" % total)


if __name__ == "__main__":
    main()
