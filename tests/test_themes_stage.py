"""The --themes backup stage: off means untouched, on means gaps only, always trimmed."""
import json

import pytest

from introkiller import cli, themes_stage
from introkiller.themes import theme_matcher


def test_option_defaults_off():
    a = cli.build_parser().parse_args(["scan", "some/folder"])
    assert a.themes is None


def test_help_names_theme_source():
    a = cli.build_parser().parse_args(["scan", "--themes", "blood", "some/folder"])
    assert a.themes == "blood"
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            cli.build_parser().parse_args(["scan", "--help"])
        except SystemExit:
            pass
    assert "AnimeThemes" in buf.getvalue()


def test_ep_in_range_open_ended():
    assert themes_stage.ep_in_range("1203-", 1206) is True
    assert themes_stage.ep_in_range("1203-", 1190) is False
    assert themes_stage.ep_in_range("1-30", 5) is True
    assert themes_stage.ep_in_range(None, 5) is None
    assert themes_stage.ep_in_range("", 5) is None
    assert themes_stage.ep_in_range("45", 45) is True


def test_rank_prefers_in_range_theme():
    themes = [{"type": "ED", "sequence": 1, "slug": "ED1", "episodes": "1-26"},
              {"type": "ED", "sequence": 75, "slug": "ED75", "episodes": "1203-"}]
    assert [t["slug"] for t in themes_stage.rank(themes, 1206, "ED")] == ["ED75", "ED1"]


def test_trim_needs_positive_length():
    assert themes_stage.trimmed({"start_s": 10.0, "end_s": 90.0}) == (12.0, 88.0)
    assert themes_stage.trimmed({"start_s": 10.0, "end_s": 13.0}) is None


def _fake_match(start_s, end_s):
    return {"theme": "slug-ED1", "match": True, "start_s": start_s, "end_s": end_s,
            "median_corr": 0.99, "lag_ncc": 0.99, "hi_n": 30}


def test_gap_only_and_trim(monkeypatch, tmp_path):
    man = {"themes": [{"type": "OP", "sequence": 1, "slug": "OP1", "episodes": "1-30"},
                       {"type": "ED", "sequence": 1, "slug": "ED1", "episodes": "1-30"}]}
    monkeypatch.setattr(themes_stage, "ensure_show", lambda slug, d: man)

    class Src:
        def __init__(self, spec, name, cache):
            pass

        @property
        def duration(self):
            return 1400.0

        def audio(self, a, b):
            import numpy as np
            return np.zeros(max(1, int(round((b - a) * 8000))), dtype=np.float32)

    monkeypatch.setattr(themes_stage.media, "Source", Src)
    calls = []
    fake = {"intro": _fake_match(60.0, 150.0), "credits": _fake_match(1300.0, 1380.0)}

    def match_epx(epx, off, meta, core, kind, name, base, loose=False):
        calls.append(kind)
        import numpy as np  # noqa: F401
        if kind == "OP":
            return dict(fake["intro"], kind=kind)
        return dict(fake["credits"], kind=kind)

    monkeypatch.setattr(theme_matcher, "match_epx", match_epx)
    import numpy as np
    for t in man["themes"]:
        base = "show-%s" % t["slug"]
        json.dump({"lead": 0, "trail": 0}, open(tmp_path / (base + ".json"), "w"))
        np.save(tmp_path / (base + ".npy"), np.zeros(8000, dtype=np.float32))

    segs = [{"type": "intro", "start": 60.0, "end": 150.0}]
    added = themes_stage.fill_gaps("spec", "show_e05", 5, "show", segs, str(tmp_path), str(tmp_path))
    assert calls == ["ED"]                      # the existing intro is never re-matched
    assert added and added[0]["type"] == "credits"
    assert (added[0]["start"], added[0]["end"]) == (1302.0, 1378.0)
    assert added[0]["gates"]["gate"] == "strict" and added[0]["method"] == "theme-match"

    calls.clear()
    both = segs + added
    assert themes_stage.fill_gaps("spec", "show_e05", 5, "show", both, str(tmp_path), str(tmp_path)) == []
    assert calls == []                          # nothing missing, matcher never runs


def test_short_theme_result_dropped_after_trim(monkeypatch, tmp_path):
    man = {"themes": [{"type": "ED", "sequence": 1, "slug": "ED1", "episodes": None}]}
    monkeypatch.setattr(themes_stage, "ensure_show", lambda slug, d: man)

    class Src:
        def __init__(self, spec, name, cache):
            pass

        @property
        def duration(self):
            return 1400.0

        def audio(self, a, b):
            import numpy as np
            return np.zeros(max(1, int(round((b - a) * 8000))), dtype=np.float32)

    monkeypatch.setattr(themes_stage.media, "Source", Src)
    monkeypatch.setattr(theme_matcher, "match_epx",
                        lambda *a, **k: dict(_fake_match(10.0, 13.0), kind="ED"))
    import numpy as np
    json.dump({"lead": 0, "trail": 0}, open(tmp_path / "show-ED1.json", "w"))
    np.save(tmp_path / "show-ED1.npy", np.zeros(8000, dtype=np.float32))
    assert themes_stage.fill_gaps("s", "show_e05", 5, "show", [], str(tmp_path), str(tmp_path)) == []
