"""Media access: local files or streamed HTTP(S) sources.

A Source never downloads a whole file.  It decodes only the windows it is asked for
(ffmpeg -ss/-t on the path or URL) and caches the decoded windows on disk:
  * audio : mono 8 kHz float32, per (start, end) window  -> <cache>/<name>_a_<a>_<b>.npy
  * video : 64x36 gray frames with exact pts, per window -> <cache>/<name>_v_<a>_<b>.npz

Source specs:
  "shows/ep01.mkv"         local file
  "https://..."            direct URL
"""
import json
import os
import re
import subprocess
import time

import numpy as np

SR = 8000
LEN_TOL = SR // 4      # samples a decode may fall short by (0.25 s: last partial packets, priming)
W, H = 64, 36
NOWIN = (0x08000000 | 0x4000) if os.name == "nt" else 0    # Windows: CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS


def lowprio():
    """Run this process (and the ffmpeg children it starts) at below-normal priority."""
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        else:
            os.nice(5)
    except Exception:
        pass


class Source:
    def __init__(self, spec, name, cache_dir):
        self.spec, self.name, self.cache_dir = spec, name, cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._info = None
        self._vmem = {}
        self._short = {}

    # -- resolution ---------------------------------------------------------------
    def path(self):
        s = self.spec
        if not s.startswith("http") and not os.path.exists(s):
            raise FileNotFoundError("media file missing (window not in the cache): %s" % s)
        return s

    def info(self):
        """duration (s) and the preferred audio stream index (Japanese if present, else first)."""
        if self._info is None:
            fn = os.path.join(self.cache_dir, self.name + "_info.json")
            if os.path.exists(fn):
                self._info = json.load(open(fn))
            else:
                p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "format=duration:stream=index,codec_type:stream_tags=language",
                                    "-of", "json", self.path()], capture_output=True, creationflags=NOWIN, timeout=180)
                j = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
                aud = [s for s in j.get("streams", []) if s.get("codec_type") == "audio"]
                ai = 0
                for i, s in enumerate(aud):
                    if (s.get("tags") or {}).get("language", "") in ("jpn", "ja"):
                        ai = i
                        break
                self._info = {"duration": float((j.get("format") or {}).get("duration") or 0), "aidx": ai,
                              "n_audio": len(aud)}
                json.dump(self._info, open(fn, "w"))
        return self._info

    @property
    def duration(self):
        return self.info()["duration"]

    # -- audio --------------------------------------------------------------------
    def _audio_after(self, t):
        """Is there audio after time t?  True / False, None when the read itself failed."""
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % t, "-t", "1.500", "-i", self.path(),
               "-map", "0:a:%d" % self.info()["aidx"], "-vn", "-sn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NOWIN, timeout=300)
        if len(p.stdout) >= 4:
            return True
        return False if p.returncode == 0 else None

    def _short_ok(self, a, x):
        """A decode shorter than asked is fine only when the audio stream really stops where the decode stopped."""
        key = (round(a, 1), len(x))
        if key not in self._short:
            self._short[key] = self._audio_after(a + len(x) / SR + 0.3) is False
        return self._short[key]

    def audio(self, a, b):
        """Mono 8 kHz float32 samples of [a, b) seconds (clipped to the file).

        Sample k is taken to be time a + k/SR, so a decode that silently loses samples shifts every time in the window (LOGH S1E02:
        a streamed decode lost its first 5.12 s and still passed a 90 % length bar).  A decode short by more than LEN_TOL is therefore
        accepted only if there is no audio after the point it stopped at, wherever the window lies; anything else is retried, then
        refused, never cached.  The same test is applied to a cached window."""
        a = max(0.0, a)
        b = min(b, self.duration)
        fn = os.path.join(self.cache_dir, "%s_a_%.1f_%.1f.npy" % (self.name, a, b))
        exp = int(round((b - a) * SR))
        if os.path.exists(fn):
            x = np.load(fn)
            if len(x) >= exp - LEN_TOL or self._short_ok(a, x):
                return x[:exp]
        for attempt in range(4):
            cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % a, "-t", "%.3f" % (b - a), "-i", self.path(),
                   "-map", "0:a:%d" % self.info()["aidx"], "-vn", "-sn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NOWIN, timeout=900)
            x = np.frombuffer(p.stdout, dtype=np.float32).copy()
            if len(x) >= exp - LEN_TOL or self._short_ok(a, x):
                x = x[:exp]
                np.save(fn, x)
                return x
            time.sleep(2 + 3 * attempt)
        raise RuntimeError("audio decode of %s [%.1f, %.1f) stays short: %.3f s of %.3f s, and the stream continues"
                           % (self.name, a, b, len(x) / SR, b - a))

    # -- video frames -------------------------------------------------------------
    def grab(self, t0, t1):
        """(times, frames[n,H,W] uint8 gray) for t0 <= pts <= t1, exact pts (full frame rate)."""
        t0 = max(0.0, t0)
        key = (round(t0, 3), round(t1, 3))
        if key in self._vmem:
            return self._vmem[key]
        for (a, b), (ts, fr) in self._vmem.items():          # a cached window that already contains the request
            if a <= t0 + 1e-6 and b >= t1 - 1e-6 and len(ts):
                m = (ts >= t0 - 1e-6) & (ts <= t1 + 1e-6)
                return ts[m], fr[m]
        fn = os.path.join(self.cache_dir, "%s_vp_%.3f_%.3f.npz" % (self.name, key[0], key[1]))
        if os.path.exists(fn):
            z = np.load(fn)
            self._vmem[key] = (z["ts"], z["fr"])
            return self._vmem[key]
        for attempt in range(2):
            cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-copyts", "-ss", "%.3f" % t0, "-i", self.path(),
                   "-to", "%.3f" % t1, "-an", "-sn", "-vf", "scale=%d:%d:flags=area,format=gray,showinfo" % (W, H),
                   "-fps_mode", "passthrough",       # without it a variable-frame-rate file gets frames duplicated/dropped at the
                   "-f", "rawvideo", "-"]            # output, so frame i no longer belongs to pts i (Texhnolyze: up to 1.2 s off)
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NOWIN, timeout=900)
            raw = np.frombuffer(p.stdout, np.uint8)
            n = len(raw) // (W * H)
            if n > 0:
                break
            time.sleep(2)
        fr = raw[:n * W * H].reshape(n, H, W)
        ts = np.array([float(m) for m in re.findall(r"pts_time:\s*(-?[\d.]+)", p.stderr.decode(errors="replace"))][:n])
        fr = fr[:len(ts)]
        keep = (ts >= t0 - 1e-6) & (ts <= t1 + 1e-6)
        res = (ts[keep], fr[keep])
        np.savez(fn, ts=res[0], fr=res[1])
        self._vmem[key] = res
        return res
