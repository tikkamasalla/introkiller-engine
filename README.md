<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/hero-dark.svg">
  <img src="assets/hero-light.svg" width="900" alt="IntroKiller Engine. Also kills credits, previews and recaps. Never touches your files.">
</picture>

Point this at a season of a show and it tells you where the intros, credits and next-episode previews are.

Despite the name, it doesn't cut anything. It only writes out the times, and your player decides what to do with them. If it isn't sure, it stays quiet, because a missed intro costs you a minute and a bad skip costs you the plot.

## Try it

You need Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html) 5.1+.

```sh
git clone https://github.com/tikkamasalla/introkiller-engine
cd introkiller-engine
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install .
introkiller scan "path/to/Show/Season 1"
```

Here it is on [Pioneer One](https://en.wikipedia.org/wiki/Pioneer_One), a Creative Commons series you can grab with `python tools/fetch_demo.py pioneer`:

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

The times also land in a `skip-times` folder as JSON. Add `--format edl,mpv,chapters` for files that mpv or Kodi can use, `--ocr` to read on-screen credits (after `pip install ".[ocr]"`), and `--recap` to look for recaps.

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/heat-dark.svg">
  <img src="assets/heat-light.svg" width="900" alt="Twelve episodes stacked. A bright band marks audio shared with the other episodes. The intro band moves from episode to episode, between 0:01 and 2:39. The credits band sits at the same distance from the end in all twelve.">
</picture>

Each row is an episode of *Legend of the Galactic Heroes: Die Neue These*. A second lights up when the other episodes have the same audio. Nobody told it where the intro was. It's just the one part all twelve agree on, wherever a cold open pushed it, which is why "skip 0:00 to 1:30" doesn't work here.

Once the audio lines up, it checks the picture too, so a song playing over a new scene doesn't count. The exact rules are in [docs/METHOD.md](docs/METHOD.md).

## How good is it?

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/scoreboard-dark.svg">
  <img src="assets/scoreboard-light.svg" width="900" alt="Paired bars of found against missed. Intro 103 of 114, old and new. Credits 68 of 105 old, 85 of 105 now. Preview 0 of 57 old, 33 of 57 now. Recap 1 of 3, old and new.">
</picture>

We tested it on 123 episodes picked to be awkward. It found 103 of 114 intros, 85 of 105 credits (99 with `--ocr`), 33 of 57 previews and 1 of 3 recaps. Recaps are the weak spot.

It got 31 results off by more than a second. We checked each one on the video and none cut into the story. Most were reference times that were slightly off themselves.

One catch: we tuned it on these same episodes, so expect lower scores on shows it hasn't seen.

Across the 117 episodes we've published times for, it gives you back 5.4 of 51 hours.

## Against the others

We ran two rivals on our episodes with the same scoring. Both tests lean our way, since we tuned on these episodes and they'd never seen them.

**skipmark, 123 episodes.** It found 112 of 114 intros to our 103, and 105 of 105 credits to our 85 (99 with `--ocr`). But 115 of its results were off by more than a second, against our 31, because it often overshoots. It's built for audio series and only heard the first and last few minutes of each file, so this isn't its home turf.

**Media Preview Generator, 31 episodes.** It found 20 of 27 intros to our 27, and 18 of 26 credits to our 16 (25 with `--ocr`). 24 of its results were off by more than a second, against our 10. It ran without the chapters and online sources it normally leans on.

If you use Plex, Emby or Jellyfin, start there. Plex and Emby have this built in, and [Intro Skipper](https://github.com/intro-skipper/intro-skipper) and [Media Preview Generator](https://github.com/stevezau/media_preview_generator) put a skip button right on your server. We don't.

This one is for when you want the times themselves: to use in mpv or Kodi, to build into a player, or to fill a gap in a database. The [Stremio patches](https://github.com/tikkamasalla/stremio-morphe-patches) already use them.

## Things that went wrong

- Seven series ids in our first results were wrong. *Planetes* pointed at *Movies for Guys Who Like Movies*. Every id gets checked now.
- A black frame looks like every other black frame, so fades kept "matching". Black no longer counts as evidence.
- A second recap method found all three recaps, then ate a second of story on one. We dropped it.

## Limits

It needs at least two episodes of a season, and three is better. Credits with different music every episode get missed without `--ocr`. Long intros that cross the 5-minute mark get cut short. Films mostly don't work. We haven't tried the EDL files in Kodi itself, or run anything on macOS.

The full scoreboard, the Pioneer One test, every rival we looked at and more mistakes are in [docs/DETAILS.md](docs/DETAILS.md).

## Licence

GPL-3.0. The two Pioneer One frames in `assets/` stay under the licence stated in the episodes, CC BY-NC-SA, and belong to creators Josh Bernhard and Bracey Smith.
