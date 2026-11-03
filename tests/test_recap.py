"""Recap combined rule: card lane plus full-replay lane."""
import json
import shutil
import subprocess

import pytest

from introkiller import pipeline, recap_lanes

FFMPEG = shutil.which("ffmpeg")


class FakeSrc:
    def __init__(self, name, duration=200.0):
        self.name, self.duration = name, duration

    def path(self):
        return self.name

    def audio(self, a, b):
        import numpy as np
        return np.zeros(max(0, int(round((b - a) * 8000))), dtype=np.float32)


def test_replay_needs_earlier():
    t = FakeSrc("e02")
    assert recap_lanes.lane6_full_replay(t, []) is None
    assert recap_lanes.lane6_full_replay(t, None) is None


def test_card_skips_cleanly_without_ocr(monkeypatch):
    monkeypatch.setattr(recap_lanes._CardOCR, "__init__", lambda s: (_ for _ in ()).throw(ImportError("no ocr")))
    t = FakeSrc("e02")
    assert recap_lanes.lane5_text_card(t, 60.0) is None
    assert recap_lanes.combined_recap(t, [], 60.0) is None


def test_combined_prefers_audio(monkeypatch):
    t, audio = FakeSrc("e02"), {"start": 6.0, "end": 74.0, "lane": "full-replay"}
    card = {"start": 0.0, "end": 83.0, "lane": "card"}
    monkeypatch.setattr(recap_lanes, "lane6_full_replay", lambda *a, **k: dict(audio))
    monkeypatch.setattr(recap_lanes, "lane5_text_card", lambda *a, **k: dict(card))
    out = recap_lanes.combined_recap(t, [FakeSrc("e01")], 84.0)
    assert (out["start"], out["end"], out["lanes"]) == (6.0, 74.0, ["full-replay", "card"])
    monkeypatch.setattr(recap_lanes, "lane6_full_replay", lambda *a, **k: None)
    out2 = recap_lanes.combined_recap(t, [FakeSrc("e01")], 84.0)
    assert (out2["start"], out2["lanes"]) == (0.0, ["card"])


def tiny_episode(path, seed):
    src = [("cellauto=rule=30:s=320x180:r=12:seed=%d" % (seed + 1), "anoisesrc=color=pink:r=48000:seed=%d" % (seed + 1), 5 + 2 * seed),
           ("testsrc2=s=320x180:r=12", "anoisesrc=color=pink:r=48000:seed=7", 20),
           ("cellauto=rule=110:s=320x180:r=12:seed=%d" % (seed + 50), "anoisesrc=color=white:r=48000:seed=%d" % (seed + 50), 20),
           ("testsrc=s=320x180:r=12", "anoisesrc=color=brown:r=48000:seed=9", 15)]
    cmd = [FFMPEG, "-v", "error", "-y"]
    for v, a, d in src:
        cmd += ["-f", "lavfi", "-t", str(d), "-i", v, "-f", "lavfi", "-t", str(d), "-i", a]
    cmd += ["-filter_complex", "".join("[%d:v]format=yuv420p,setsar=1[pic%d];[%d:a]aformat=sample_rates=48000:channel_layouts=mono[snd%d];" % (2 * i, i, 2 * i + 1, i) for i in range(4)) + "".join("[pic%d][snd%d]" % (i, i) for i in range(4)) + "concat=n=4:v=1:a=1[pic][snd]", "-map", "[pic]", "-map", "[snd]", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)]
    subprocess.run(cmd, check=True)


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_no_flag_is_byte_identical(tmp_path):
    a, b = tmp_path / "S01E01.mkv", tmp_path / "S01E02.mkv"
    tiny_episode(a, 1)
    tiny_episode(b, 2)
    cache = str(tmp_path / "cache")
    r1 = pipeline.run_season([str(a), str(b)], ["S01E01", "S01E02"], cache, None, {"recap": False})
    r2 = pipeline.run_season([str(a), str(b)], ["S01E01", "S01E02"], cache, None, {"recap": False})
    scrub = lambda rs: json.dumps([{"episode": r["episode"], "duration": r["duration"], "segments": r["segments"], "rejected": r["rejected"]} for r in rs], sort_keys=True)
    assert scrub(r1) == scrub(r2)
    assert all(s["type"] != "recap" for r in r1 for s in r["segments"])
    r3 = pipeline.run_season([str(a), str(b)], ["S01E01", "S01E02"], cache, None, {"recap": True})
    for p, q in zip(r1, r3):
        assert [s for s in p["segments"] if s["type"] != "recap"] == [s for s in q["segments"] if s["type"] != "recap"]
        assert p["rejected"] == q["rejected"]
