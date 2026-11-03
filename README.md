<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/hero-dark.svg">
  <img src="assets/hero-light.svg" width="900" alt="IntroKiller Engine. Also kills credits, previews and recaps. Never touches your files.">
</picture>

IntroKiller Engine finds the intros, credits and next-episode previews in a season of a show, and writes down when each one starts and ends.

Despite the name, the engine never cuts a video. It only writes out times, and your player decides what to do with them. When the engine is not sure, it reports nothing. A missed intro costs you a minute, and a wrong skip can cost you part of the plot.

## Try it

You need Python 3.10 or later and [FFmpeg](https://ffmpeg.org/download.html) 5.1 or later.

```sh
git clone https://github.com/tikkamasalla/introkiller-engine
cd introkiller-engine
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install .
introkiller scan "path/to/Show/Season 1"
```

To try it on a real series, download [Pioneer One](https://en.wikipedia.org/wiki/Pioneer_One), a Creative Commons series, with `python tools/fetch_demo.py pioneer`. The engine prints this:

```text
Pioneer One E01  (31:36.4)
  nothing certain enough to report
Pioneer One E02  (38:42.0)
  nothing certain enough to report
Pioneer One E03  (31:14.7)
  intro      4:30.0 -   4:59.2
Pioneer One E04  (33:46.7)
  intro      4:40.4 -   5:00.0
Pioneer One E05  (37:44.0)
  intro      3:07.6 -   3:40.9
Pioneer One E06  (44:00.3)
  intro      3:53.0 -   4:26.6
```

The times are also saved as JSON in a `skip-times` folder. Add `--format edl,mpv,chapters` for files that mpv or Kodi can read, `--ocr` to read on-screen credits (after `pip install ".[ocr]"`), and `--recap` to look for recaps.

## How it works

The engine compares the audio of the episodes in a season and looks for the part they all share. You do not tell it where the intro is.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/heat-dark.svg">
  <img src="assets/heat-light.svg" width="900" alt="Twelve episodes stacked. A bright band marks audio shared with the other episodes. The intro band moves from episode to episode, between 0:01 and 2:39. The credits band sits at the same distance from the end in all twelve.">
</picture>

Each row is an episode of *Legend of the Galactic Heroes: Die Neue These*, and a bright band marks audio shared with the other episodes. A cold open (a scene before the title sequence) moves the intro from episode to episode, so a fixed rule such as "skip 0:00 to 1:30" would fail here. The engine finds the intro wherever it sits.

The engine then checks the picture too, so a song that plays over a new scene does not count. The exact rules are in [docs/METHOD.md](docs/METHOD.md).

## How well it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/scoreboard-dark.svg">
  <img src="assets/scoreboard-light.svg" width="900" alt="Paired bars of found against missed. Intro 103 of 114, old and new. Credits 68 of 105 old, 85 of 105 now. Preview 0 of 57 old, 33 of 57 now. Recap 1 of 3, old and new.">
</picture>

We tested the engine on 123 episodes chosen because they are hard. It found 103 of 114 intros, 85 of 105 credits (99 with `--ocr`), 33 of 57 previews and 1 of 3 recaps on that set. A partial segment counts as found.

### Recaps

We measured recaps separately on 43 recaps. The new rule finds montage-style recaps and "Previously on" cards. It misses narrated recaps and single-scene replays. The replay method needs whole earlier episodes. The card method needs the OCR extra and is skipped cleanly without it. It covers a median 98 percent of each recap it finds.

| Rule | Recaps tested | Found | False results | Worst overrun past the true end |
|---|---:|---:|---:|---:|
| Previous rule, given whole earlier episodes | 12 | 4 | 1 | 139.9 s |
| New: "Previously on" card | 43 | 10 | 0 | 0.0 s |
| New: replay of whole earlier episodes | 12 | 4 | 0 | 0.0 s |
| New: both combined, with `--recap` | 43 | 13 | 0 | 0.0 s |

The replay method ran on 12 of the 43 recaps because it needs whole episodes, so the combined figure may rise with a fuller test.

The rival tables below show the previous rule, which was not rerun, so those figures are unchanged.

Of the results, 31 were off by more than a second. We checked each against the video, and none cut into the story. Most were reference times (the correct times we score against) that were slightly off themselves.

We tuned the engine on these same episodes, so expect lower scores on shows it has not seen. Across the 117 episodes with published times, it gives back 5.4 of 51 hours.

## Comparison with other tools

We tested three similar tools on our episodes with the same scoring. Every test favours us, because we tuned on these episodes and the other tools had never seen them.

### skipmark, 123 episodes

| | skipmark | IntroKiller Engine |
|---|---:|---:|
| Intros skipped correctly, of 114 | 74 | **90** |
| Credits skipped correctly, of 105 | 40 | **70** |
| Previews found, of 57 | 3 | **33** |
| Results off by more than 1 s | 115 | **31** |
| Intros touched, of 114 | **112** | 103, or 109 with `--themes` |
| Credits touched, of 105 | **105** | 85, or 99 with `--ocr` |

A correct skip covers at least half of the real segment and is never off by more than a second. skipmark touches more segments but often overshoots into the episode. It is built for audio series and heard only the first and last few minutes of each file.

### Media Preview Generator, 31 episodes

| | Media Preview Generator | IntroKiller Engine |
|---|---:|---:|
| Intros found, of 27 | 20 | **27** |
| Credits found, of 26 | 18 | 16, or **25** with `--ocr` |
| Results off by more than 1 s | 24 | **10** |
| Median error at the start of credits | 19 s | **0.13 s** |

It ran without the chapters and online sources it normally uses. The error rows are for our default run, without `--ocr`.

### ScenePass v0.9.5, 31 episodes

| | ScenePass, default settings | ScenePass, counting results held for review | IntroKiller Engine |
|---|---:|---:|---:|
| Intros found, of 27 | 0 | 25 | **27** |
| Wrong intro skips | 0 | 1 | 0 |
| Recaps found, of 3 | 0 | **3** | 1 |
| False recaps | 0 | 5 | 0 |
| Wrong recap results | 0 | 8 | 0 |

ScenePass is closed source. By default it holds every result for your review and applies none, so the middle column shows what it would do if you accepted them all. Its recap win comes from only 3 recaps, which is a small sample.

If you use Plex, Emby or Jellyfin, start with the tools built for them. Plex and Emby include this feature, and [Intro Skipper](https://github.com/intro-skipper/intro-skipper) and [Media Preview Generator](https://github.com/stevezau/media_preview_generator) add a skip button to your server. This engine does not. Use it when you want the times themselves, for mpv, Kodi, your own player or a database. The [Stremio patches](https://github.com/tikkamasalla/stremio-morphe-patches) already use them.

## Mistakes we found and fixed

- Seven series ids in our first results were wrong. *Planetes* pointed at *Movies for Guys Who Like Movies*. The engine now checks every id.
- Every black frame looks like every other black frame, so fades kept matching. Black no longer counts as evidence.
- The old recap rule reported recaps that ran past the true end and made false reports. The new rule reports only montage replays and "Previously on" cards with no overrun.

## Limits

The engine needs at least two episodes of a season, and three is better. Without `--ocr`, it misses credits with different music in every episode. It cuts short intros that cross the 5-minute mark, and it mostly fails on films. We have not tested the EDL files in Kodi itself, or run the engine on macOS.

When a show has too few episodes for the main pipeline, use --themes SLUG to try its official songs. The engine fetches that show only from AnimeThemes.moe, fills only types the main pass missed, and trims 2 seconds from each end. On 123 episodes it adds 8 segments. The main pipeline finds 103 of 114 intros and 85 of 105 credits. With themes it finds 109 intros and 85 credits. It covers anime only, needs network and local cache, handles one show per run, and finds less alone than the main pipeline.

[docs/DETAILS.md](docs/DETAILS.md) has the full scoreboard, the Pioneer One test, the other tools we looked at and more mistakes.

## Licence

GPL-3.0. The two Pioneer One frames in `assets/` stay under the licence stated in the episodes, CC BY-NC-SA, and belong to creators Josh Bernhard and Bracey Smith.
