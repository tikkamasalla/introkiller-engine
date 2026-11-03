# Details

This is the long version of the [README](../README.md): the full scores, the Pioneer One test, the comparison with other tools, the mistakes we fixed, and ways to use the results.

## Anatomy of an episode

The intro rarely starts at zero, and a preview can start on the frame right after the credits. No single episode in our results has all four parts, so the chart shows two real rows.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/anatomy-dark.svg">
  <img src="../assets/anatomy-light.svg" width="900" alt="Two episode timelines. Record of Ragnarok season 3 episode 11: recap 0:17 to 0:45, intro 1:30 to 2:57, credits 22:11 to 24:59. Blood-C episode 1: intro 1:12 to 2:41, credits 22:08 to 23:38, preview 23:38 to 24:09.">
</picture>

## The scoreboard

The table shows how often the engine found, missed or wrongly reported each kind of segment. In the chart, "old" is the previous version of the engine on the same episodes. It had no preview stage, so its preview score is zero.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/scoreboard-dark.svg">
  <img src="../assets/scoreboard-light.svg" width="900" alt="Paired bars of found against missed. Intro 103 of 114, old and new. Credits 68 of 105 old, 85 of 105 now. Preview 0 of 57 old, 33 of 57 now. Recap 1 of 3, old and new.">
</picture>

| On 123 episodes | Found | Missed | False | Flagged | Ate story, after checking frames |
|---|---:|---:|---:|---:|---:|
| Intro | 103 | 11 | 0 | 13 | 0 |
| Credits | 85 | 20 | 3 | 15 | 0 |
| Preview | 33 | 24 | 3 | 3 | 0 |
| Recap | 1 | 2 | 0 | 0 | 0 |

The reference is the set of times we treat as correct. The 123 episodes come in 23 sets chosen to be awkward, including 3 films. For 86 episodes the reference is the named chapter marks in the file, which the engine never reads. For 9 it is unnamed chapters we checked on frames, and for 28 it was written from the frames.

"Found" means the engine returned a segment where the reference has one. "False" means it returned one where the reference has none. "Flagged" means more than 1.0 s of a returned segment lies outside the reference, the strict test for a wrong skip.

We judged all 31 flagged segments on frames, and none eats story or preview. Most are chapter marks about a second off the real boundary. The 3 false credits are real credit rolls on Samurai Jack, where the reference lists only the intro. The 3 false previews are 10.5 s of studio logos.

We tuned the engine on these same episodes, so this is a development score and not a blind test. "Found" also counts a partial segment, so the next table shows how close the found ones came.

| Found segments | Median start error | Median end error | Median share of the reference covered | Covered less than 90% |
|---|---:|---:|---:|---:|
| Intro | 0.79 s | 0.09 s | 98.5% | 9 of 103 |
| Credits | 0.17 s | 0.96 s | 98.9% | 7 of 85 |
| Preview | 0.29 s | 0.00 s | 99.1% | 0 of 33 |
| Recap | 12.05 s | 33.44 s | 37.6% | 1 of 1 |

With `--ocr`, credits rise from 85 to 99 of 105. It also adds 7 credit rolls on episodes whose reference lists no credits. They are real on frames, though the rules score them as false. Text starts run late, up to about two minutes on *The Glory*, which errs on the safe side.

### Recaps on 43 episodes

The scoreboard above uses 3 recaps. We measured the recap rule separately on 43 recaps with 40 negatives. The previous rule found 4 of 12 recaps when given whole earlier episodes, with 1 false result and overruns of up to 139.9 s. The new rule with `--recap` combines a "Previously on" card method and a method that matches replayed audio against whole earlier episodes. It finds montage-style recaps and "Previously on" cards. It misses narrated recaps and single-scene replays. The replay method needs whole earlier episodes of the same season. The card method needs the OCR extra and is skipped cleanly when it is missing.

| Rule | Recaps tested | Found | False results | Worst overrun past the true end |
|---|---:|---:|---:|---:|
| Previous rule, given whole earlier episodes | 12 | 4 | 1 | 139.9 s |
| New: "Previously on" card | 43 | 10 | 0 | 0.0 s |
| New: replay of whole earlier episodes | 12 | 4 | 0 | 0.0 s |
| New: both combined, with `--recap` | 43 | 13 | 0 | 0.0 s |

The replay method ran on 12 of the 43 recaps because it needs whole episodes, so the combined figure may rise with a fuller test.

It covers a median 98 percent of each recap it finds. The rival tables below show the previous rule on their own episodes. The new rule was not rerun there, so those figures are unchanged.

When a season has too few episodes for the main pipeline, pass --themes SLUG with the AnimeThemes slug. The engine fetches only that show from AnimeThemes.moe over GraphQL, caches the songs, and tries openings where intro is missing and endings where credits are missing. A result is kept only if it passes a correlation check, which produced no real false matches across 2,200 pairs from different shows and 648 regions within the same shows. It is then trimmed 2 seconds at each end. It never replaces a main result. On 123 episodes the main pass finds 103 of 114 intros and 85 of 105 credits. With themes it finds 109 intros and 85 credits, adding 8 segments. Blood+ intros go from 0 of 5 to 5 of 5. The 2 added credits are real endings missing from the reference. Alone it finds 82 intros and 80 credits with no real wrong results. It is anime-only, needs network and local cache, handles one show per run, and finds less alone than the main pipeline.

<details>
<summary>Every set, including the zeros</summary>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/shows-dark.svg">
  <img src="../assets/shows-light.svg" width="900" alt="A table of 23 test sets with found out of reference counts. Zeros include Fawlty Towers and Blood+ intros, and Ideon, The Glory, Drive to Survive and film credits.">
</picture>
A dash means the reference has none of that type, and +3f means three false results. The numbers are in <a href="../data/scoreboard.json">data/scoreboard.json</a>.
</details>

## Time given back

Across the 117 episodes with published times, the engine finds 5.4 of 51.0 hours that you have already seen or will not miss.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/hours-dark.svg">
  <img src="../assets/hours-light.svg" width="900" alt="5.4 hours out of 51.0 hours of runtime, 10.6 percent, across 117 episodes of 22 shows. Share per show runs from 16.6 percent for Record of Ragnarok to 1.7 percent for Fawlty Towers.">
</picture>

The 245 published segments are 2.71 hours of credits, 2.46 of intros, 0.22 of previews and one 27-second recap. The median intro runs 88 s and the median credits 89 s. A low share can mean a show has less to skip, or that the engine missed it: Fawlty Towers has a title sequence, and our score for it is 0 of 4.

## Mistakes we found and fixed

Each of these happened, and each left a rule behind.

- Some credit windows that volunteers entered online ran 277 to 326 s and included real mid-credits scenes. Windows that survived ran about 100 s, and our own 108 credits have a median of 89 s and a 90th percentile of 104 s. Rule: a player using our times shows a button, never an automatic skip, for any online credits window over 180 s.
- An earlier version found a 19 s scrap of Blood+'s 94 s opening, and the scorer counted 5 hits. Rule: short pieces need verified edges. The score went from 108 to 103 on purpose.
- The text stage called 51 s in the middle of a Detective Conan episode "credits", and got 4 of 26 wrong at first. Rule: text results count only if they run to the end of the file, and only where matching found nothing.
- A streamed decode silently lost its first 5.12 s on one episode. Rule: a decode that comes back short is refused unless the audio ends there.
- A black frame hashes to all zeros, so black always matched black. Rule: black counts toward the share, never as evidence of where a segment starts or ends.
- Seven series ids in our first draft were wrong. *Planetes* pointed at *Movies for Guys Who Like Movies*, and *Mobile Suit Gundam* at *Billy*. Rule: every id is checked by name and by whether the episode exists.
- The old recap rule made false reports and ran past the true end. The new rule finds montage replays and "Previously on" cards with no overrun.

## The demo: Pioneer One

Our scored episodes cannot ship with this repository, so this test is one you can repeat. [Pioneer One](https://en.wikipedia.org/wiki/Pioneer_One) is a six-episode series created by Josh Bernhard and Bracey Smith. A card in the episodes states a Creative Commons Attribution-NonCommercial-ShareAlike licence, and the [copies on archive.org](https://archive.org/details/pioneer-one-ep.-1-earthfall-pilot) list CC BY-SA 4.0. We go by the card.

```sh
python tools/fetch_demo.py pioneer        # 3.39 GB over HTTPS, with a hard stop at 5 GB
introkiller scan pioneer --recap --ocr
```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/demo-dark.svg">
  <img src="../assets/demo-light.svg" width="900" alt="Six timelines of Pioneer One. Recaps found on episodes 2, 3 and 5, intros on episodes 3, 4, 5 and 6, no credits on any.">
</picture>

| Episode | Recap found | Intro found | Title sequence by eye | Result |
|---|---|---|---|---|
| 1 | | | none separate | correct silence |
| 2 | 0:36 to 1:01 | | ends about 6:45 | intro missed, picture share 0.56 against the 0.60 gate |
| 3 | 0:07 to 0:26 | 4:30.0 to 4:59.2 | about 4:27 to 5:04 | 3 s late, 5 s short |
| 4 | | 4:40.4 to 5:00.0 | about 4:38 to 5:15 | 2 s late, 15 s short, stopped at the 5-minute window; recap missed |
| 5 | 0:04 to 0:35 | 3:07.6 to 3:40.9 | about 3:05 to 3:41 | 3 s late, end on the mark |
| 6 | | 3:53.0 to 4:26.6 | about 3:50 to 4:27 | 3 s late, end on the mark; recap missed |

We compared every result with the frames. The engine found 4 of 5 title sequences and 3 of 5 "previously on" recaps, and nothing ate story. It found 0 of 6 credits. Matching refused them because the name cards differ in every episode, and the picture share stayed between 0.00 and 0.45. The text stage found a text run in all six but refused them too, because each run stops before the file ends. That rule protects other shows from a false skip, and here it costs every credits result.

<p align="center">
  <img src="../assets/demo-title.jpg" width="400" alt="Pioneer One title sequence: line art of a seated figure on aged paper, at 3:35 of episode 5, inside the found intro.">
  <img src="../assets/demo-credits.jpg" width="400" alt="Pioneer One credits at 31:00 of episode 3, a column of names on black with orange boxes around the 12 text regions the detector saw.">
  <br><sub>Left: inside the found intro, episode 5. Right: what the text stage sees in episode 3's credits, with its 12 boxes drawn on. From Pioneer One, CC BY-NC-SA.</sub>
</p>

## Comparison with other tools

Matching theme audio across a season is a common method, and [Media Preview Generator](https://github.com/stevezau/media_preview_generator) is the closest to ours. Among 26 detection projects and 4 community databases, we found no published per-show score on real episodes that covers next-episode previews, with misses and false results in view. The nearest is the [thesis](https://github.com/nielstenboom/masterthesis/raw/master/main.pdf) behind recurring-content-detector, which charts previews and other classes on 80 files, but not per show. This says what has been measured, and nothing about who had the idea first.

| Project | Needs a server | Intro | Credits | Next-episode preview | Recap | Uses the picture | Reads on-screen text | Score on real episodes |
|---|---|---|---|---|---|---|---|---|
| IntroKiller Engine | no | yes | yes | yes, 33 of 57 | weak, 1 of 3 | yes | optional | yes, per show |
| Plex ([intros](https://support.plex.tv/articles/skip-content/), [credits](https://support.plex.tv/articles/credits-detection/)) | yes, plus Plex Pass | yes | yes | not listed | not listed | yes, [for credits](https://www.mactrast.com/2023/02/plex-now-allows-viewers-to-skip-the-credits-at-the-end-of-shows-and-movies-with-a-click-of-the-remote/) | yes, for credits | credits only, per [staff](https://forums.plex.tv/t/credit-detection-making-mistakes/831210), set not described |
| [Emby](https://emby.media/support/articles/Intro-Skip.html) | yes, plus Premiere | yes | [plugins only](https://emby.media/community/topic/145091-plugin-embycredits-detect-end-credits-and-add-auto-skip/) | not listed | not listed | not published | not listed | not published |
| [Jellyfin Intro Skipper](https://github.com/intro-skipper/intro-skipper) | yes | yes | yes | partial: [chapters, subtitles, credits end](https://github.com/intro-skipper/intro-skipper/blob/12.0/docs/analysis.md) | yes | yes | partial | not published |
| [Media Preview Generator](https://github.com/stevezau/media_preview_generator) | yes, Docker | yes | yes | from chapters or online databases | same | partial | yes | yes, totals; ours below |
| [skipmark](https://github.com/Rakshit-gen/skipmark) | no | yes | yes | yes | yes | no, audio series | no | its own [synthetic shows](https://github.com/Rakshit-gen/skipmark#limits); ours below |
| [SkipForge](https://github.com/jamieelliston/skipforge) | Docker web app | partial: start to a marker image | yes, marker image | no | no | yes | no | not published |
| [recurring-content-detector](https://github.com/nielstenboom/recurring-content-detector) | no | yes | yes | yes | yes | yes, picture only | no | yes, totals on 80 files |
| Streaming services' own marking | no | yes | yes | yes | yes | a person | a person | not published |
| Community databases: [AniSkip](https://github.com/lexesjan/typescript-aniskip-extension), [TheIntroDB](https://theintrodb.org/), [IntroDB.app](https://introdb.app/), [SkipDB](https://skipdb.tv/docs) | no, online | yes | yes | some sites | some sites | people submit | people submit | not published |

Other tools win in several places. Plex and Emby are built in with little or no setup, so use them if you want a button in your app. Intro Skipper lives inside Jellyfin, is far more widely used and has a real recap stage. We have nothing that puts a button on your TV. Media Preview Generator writes markers into Plex, Emby and Jellyfin at once, reads on-screen credits on single files and movies, merges online sources and runs on arrival from Sonarr or Radarr. skipmark finds ads as well as recaps, and anyone can rerun its benchmark, which we cannot offer because our test episodes cannot ship. SkipForge has a review queue. recurring-content-detector and [ScenePass](https://github.com/lynxstrike/ScenePass.repo) go after recaps, with pictures and with speech recognition, which is where we are weakest. Community databases answer instantly whenever someone has already done the work.

Users describe gaps that this project targets. One Plex user found that [the skip button goes missing](https://forums.plex.tv/t/intro-credit-skip-problems-and-a-feature-request/835342) when a preview follows the credits. [Another reported](https://forums.plex.tv/t/credit-detection-making-mistakes/831210) that on animated shows the credit markers were wrong in "easily more than half the episodes", in the thread where Plex staff put credits at around 93% on their own test set. Neither measures Plex on our episodes, which we do not have.

### Two tools, tested on our episodes

We ran two tools on our test episodes with our scorer unchanged and online sources off. Both tests favour us, because we tuned on these episodes and the other tools never saw them, so treat the margins as an upper limit. The numbers are in [data/head_to_head.json](../data/head_to_head.json).

skipmark ran on all 123 episodes. It is built for audio series, and here it heard only the first and last 5 minutes or so of each file.

| | skipmark | IntroKiller Engine |
|---|---:|---:|
| Intros returned, of 114 | 112 | 103 |
| Intros covering at least half the reference | 105 | 103 |
| Same, with no wrong skip | 74 | 90 |
| Credits returned, of 105 | 105 | 85, or 99 with `--ocr` |
| Credits covering at least half the reference | 77 | 82 |
| Same, with no wrong skip | 40 | 70 |
| Previews, of 57 | 3 | 33 |
| Recaps, of 3 | 0, plus 9 false | 1 |
| Segments more than 1.0 s outside the reference | 115 | 31 |
| Median and 90th percentile edge error | 1.07 s, 62.07 s | 0.34 s, 2.32 s |

skipmark also returned 69 "ads", and 26 of them were really intros, credits or previews under the wrong name. It beat our default run on Fawlty Towers intros, 3 of 4 against our 0, and on Blood+ intros, 5 of 5 against our 0, though most of those run past the real edges. With `--themes` we now find all 5 Blood+ intros. It also returns something for credits on sets where we return nothing.

Media Preview Generator ran on 31 episodes with its own test harness, without chapters or online sources, so this tests its detectors alone. Its High tier publishes nothing without a second source, so the table shows its Medium tier. It saw 3 or 4 episodes per show, while some of our results come from runs with more episodes of the same show.

| | Media Preview Generator | IntroKiller Engine |
|---|---:|---:|
| Intros found, of 27 | 20 | 27 |
| Intros wrong by more than 1.0 s, after known reference errors | 7 | 0 |
| Intro median start error | 1.01 s | 0.79 s |
| Credits found, of 26 | 18 | 16, or 25 with `--ocr` |
| Credits wrong by more than 1.0 s, after known reference errors | 5 | 0 |
| Credits median start error | 19.0 s | 0.13 s |
| Previews and recaps | not a feature | 5 of 9, 1 of 3 |

On our default run, Media Preview Generator won credits coverage, including all 3 episodes each of *The Glory*, *Drive to Survive* and *Ideon*, where matching found nothing. `--ocr` closes the gap: it finds the same 9 episodes, for 25 of 26 against its 18. Those 9 start up to 124 s late, which errs on the safe side. The error rows are for the default run only. Media Preview Generator also found 5 real credit rolls that our reference leaves out, on *Red Dwarf* and *Detective Conan*. We counted those for it. `--ocr` finds 2 of them, and our default run finds none. Its own [evaluation notes](https://github.com/stevezau/media_preview_generator/blob/dev/tools/markers_eval/README.md) report 91 useful, 12 wrong and 15 missed intros on 118 episodes, and 59 of 80 credits within 10 s. Those use different episodes and looser rules, so they do not compare with our table.

ScenePass v0.9.5, closed-source, ran on the same 31 episodes as Media Preview Generator. By default it applies nothing; finds wait as held-for-review for confirmation. The table shows defaults and held-for-review. With held it finds 25 of 27 intros to our 27, with 1 wrong skip to our 0 and median start 1.02 s to our 0.79 s. Recaps are its win, 3 of 3 to our 1 of 3, with 5 false and 8 wrong to our 0. Only 3 recaps were in the test, a small sample. We tuned here and it did not, so this favours us.

| | ScenePass defaults | ScenePass held | IntroKiller Engine |
|---|---|---|---|
| Intros, of 27 | 0 | 25 | 27 |
| Intros wrong after known errors | 0 | 1 | 0 |
| Median start error | not measured | 1.02 s | 0.79 s |
| Recaps, of 3 | 0 | 3 | 1 |
| Recaps false / wrong | 0 / 0 | 5 / 8 | 0 / 0 |

The other projects we looked at: [needle](https://github.com/aksiksi/needle), [Skiptro](https://github.com/MikeSiLVO/skiptro-releases), [AniChapters](https://github.com/56cla/AniChapters), [iina-skip-intro](https://github.com/pparanoiidd/iina-skip-intro), [ScenePass](https://github.com/lynxstrike/ScenePass.repo), [EmbyCredits](https://github.com/yocksers/EmbyCredits), [Kodi Intro Skipper](https://github.com/CvH/kodi-intro-skipper), [Skip-emby](https://github.com/dandan658/Skip-emby), [intro-skipper-node](https://github.com/GOvEy1nw/intro-skipper-node), [Mydia](https://github.com/getmydia/mydia), [analyzer](https://github.com/zaentrum/analyzer), [contentDetectron](https://github.com/fertlopus/contentDetectron), [end-credits-detection](https://github.com/thiago-franco/end-credits-detection), [Credit Scout](https://github.com/PatrickKalkman/credit-scout), [credroll](https://github.com/debrup416/credroll), [Content-Seperator](https://github.com/dhruv7539/Content-Seperator), [series-player](https://github.com/althropic/series-player), [plex-credits-detect](https://github.com/cjmanca/plex-credits-detect) (retired) and [Jellyfin Media Analyzer](https://github.com/endrl/jellyfin-plugin-media-analyzer) (archived).

## What you can do with the results

- Fill gaps in a media server. Run `introkiller scan Season1 --format chapters`, then `ffmpeg -i ep.mkv -i ep.ffmeta -map_metadata 1 -map_chapters 1 -map 0 -c copy ep-chapters.mkv` to make a copy with named chapters. Tools that read chapter names, such as Intro Skipper, can use them.
- Skip in Kodi or mpv with no plugin. `--format edl,mpv` writes edit decision list (EDL) files, which name the parts of a video to skip. Put `ep.edl` next to `ep.mkv` and [Kodi](https://kodi.wiki/view/Edit_decision_list) skips each marked part once. In mpv, open `ep.mpv.edl` and the marked parts are removed: on one Pioneer One episode, a 37:44 file plays as 37:10. `mpv --chapters-file=ep.ffmeta ep.mkv` also works. Both lists leave previews out on purpose.
- Build it into a player or addon. Read `times.json` and seek. These results already power the "own times" source in [stremio-morphe-patches](https://github.com/tikkamasalla/stremio-morphe-patches), and [the published files](https://github.com/tikkamasalla/stremio-morphe-patches/tree/skip-data/times) show the format at scale.
- Contribute to a community database. Scan a season nobody has covered, check the edges, and submit what holds up. The `d` field lets a database match your times to the right cut.
- Catalogue a collection. `details/<episode>.json` records every segment with its evidence, and every refused candidate with the reason. The engine runs offline.

## Credits

GPL-3.0, see [LICENSE](../LICENSE). Built on [FFmpeg](https://ffmpeg.org), [NumPy](https://numpy.org), [OpenCV](https://opencv.org), and for `--ocr`, [RapidOCR](https://github.com/RapidAI/RapidOCR). Charts rebuild from `data/` with `python tools/build_charts.py`.

The two Pioneer One frames in `assets/` come from *Pioneer One*, created by Josh Bernhard and Bracey Smith, and stay under the licence its makers state in the episodes: Creative Commons Attribution-NonCommercial-ShareAlike. Show names in the charts identify what was measured, and no frames from those shows are included.
