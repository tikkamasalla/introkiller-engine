"""A few tests that prove the command line runs. Detection itself is scored on real episodes, see the README."""
import hashlib
import json
import shutil
import subprocess
import sys

import pytest

from introkiller import __version__, cli, formats

FFMPEG = shutil.which("ffmpeg")
SEGMENTS = [{"type": "intro", "start": 10.0, "end": 40.0}, {"type": "credits", "start": 100.0, "end": 130.0},
            {"type": "preview", "start": 130.0, "end": 150.0}]


def run(*args):
    return subprocess.run([sys.executable, "-m", "introkiller.cli", *args], capture_output=True, text=True)


def test_version():
    r = run("--version")
    assert r.returncode == 0 and __version__ in r.stdout


@pytest.mark.parametrize("name,want", [("Show S02E05 Title", (2, 5)), ("Show.s1e12", (1, 12)), ("Show 3x07", (3, 7)),
                                       ("Pioneer One E04", (None, 4)), ("Show Ep.6 War", (None, 6)), ("Movie 1080p", (None, None))])
def test_episode_numbers(name, want):
    assert cli.parse_number(name) == want


def test_one_file_is_refused(tmp_path):
    (tmp_path / "only.mp4").write_bytes(b"x")
    r = run("scan", str(tmp_path))
    assert r.returncode != 0 and "at least two episodes" in r.stderr


def test_kodi_edl_leaves_previews_to_the_viewer():
    assert formats.kodi_edl(SEGMENTS) == "10.000\t40.000\t3\n100.000\t130.000\t3\n130.000\t130.000\t2\n"


def test_mpv_edl_keeps_story_and_preview():
    text = formats.mpv_edl("ep,1.mkv", SEGMENTS, 150.0).splitlines()
    assert text == ["# mpv EDL v0", "%8%ep,1.mkv,0.000,10.000", "%8%ep,1.mkv,40.000,60.000", "%8%ep,1.mkv,130.000,20.000"]


def test_chapters_cover_the_whole_file():
    text = formats.ffmeta(SEGMENTS, 160.0)
    assert text.startswith(";FFMETADATA1") and text.count("[CHAPTER]") == 6 and "title=Story" in text and "END=160000" in text


def episode(path, seed):
    """Two minutes of synthetic video: a unique cold open, a shared 40 s title, unique story, shared 30 s credits."""
    src = [("cellauto=rule=30:s=320x180:r=12:seed=%d" % (seed + 1), "anoisesrc=color=pink:r=48000:seed=%d" % (seed + 1), 5 + 2 * seed),
           ("testsrc2=s=320x180:r=12", "anoisesrc=color=pink:r=48000:seed=7", 40),
           ("cellauto=rule=110:s=320x180:r=12:seed=%d" % (seed + 50), "anoisesrc=color=white:r=48000:seed=%d" % (seed + 50), 50),
           ("testsrc=s=320x180:r=12", "anoisesrc=color=brown:r=48000:seed=9", 30)]
    cmd = [FFMPEG, "-v", "error", "-y"]
    for v, a, d in src:
        cmd += ["-f", "lavfi", "-t", str(d), "-i", v, "-f", "lavfi", "-t", str(d), "-i", a]
    pairs = "".join("[%d:v]format=yuv420p,setsar=1[pic%d];[%d:a]aformat=sample_rates=48000:channel_layouts=mono[snd%d];" % (2 * i, i, 2 * i + 1, i) for i in range(4))
    joined = "".join("[pic%d][snd%d]" % (i, i) for i in range(4))
    cmd += ["-filter_complex", pairs + joined + "concat=n=4:v=1:a=1[pic][snd]",
            "-map", "[pic]", "-map", "[snd]", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)]
    subprocess.run(cmd, check=True)


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_scan_end_to_end(tmp_path):
    for i in range(1, 5):
        episode(tmp_path / ("Test Show S01E0%d.mkv" % i), i)
    out = tmp_path / "out"
    fingerprint = lambda: sorted(hashlib.sha1(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.mkv"))
    before = fingerprint()
    r = run("scan", str(tmp_path), "--out", str(out), "--format", "json,edl,mpv,chapters", "--quiet")
    assert r.returncode == 0, r.stderr
    assert before == fingerprint()      # the videos are never touched
    times = json.loads((out / "times.json").read_text())
    assert times["v"] == 1 and set(times["s"]["1"]) == {"1", "2", "3", "4"}
    first = times["s"]["1"]["1"]
    intro = [s for s in first if s["t"] == "intro"][0]
    assert abs(intro["a"] - 7000) < 1500 and abs(intro["b"] - 47000) < 1500
    assert intro["d"] > 100000
    assert (out / "Test Show S01E01.edl").exists() and (out / "Test Show S01E01.ffmeta").exists()
    assert not (out / "cache").exists()
