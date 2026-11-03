# The method, gate by gate

The README gives the short version. This page lists the actual rules, for anyone who wants to argue with them. Every value below is a key in `CFG` at the top of `src/introkiller/pipeline.py` or a constant in the module named, and `--config '{"ncc_min": 0.9}'` overrides `CFG` from the command line.

The rule behind all of it: if the engine is not sure, it reports nothing, and it writes down why in `details/<episode>.json` under `rejected`.

## 1. Windows

The head window is the first 300 s of every episode. The tail window is the last 300 s. Episodes that found nothing get a second try over 720 s and 600 s. Audio is decoded to mono at 8 kHz, and the Japanese track is preferred when a file has one. Only these windows are read, so a remote file over HTTP(S) is not downloaded whole.

## 2. Audio alignment (`align.py`)

The signal is band-limited to 80 to 1500 Hz and gain-normalised over 1 s. Lossy codecs rebuild the high frequencies differently per file, so only the low band is a reliable fingerprint of one recording: a pre-emphasised full band scored 0.58 on two AAC copies of the same opening, the band-limited signal 0.98. Gain control lets a quiet theme weigh as much as loud dialogue.

FFT cross-correlation against up to 5 other episodes gives the top 3 time offsets. At each offset a 0.1 s sliding correlation marks the stretches where both episodes carry the same recording (threshold 0.5, gaps up to 0.6 s bridged, stretches of 4 s or more kept).

## 3. Clustering and gates (`pipeline.py`)

Stretches from different episodes are grouped when their starts and ends agree within 3 s. When every supporter is within 0.2 s the edges are the median. Otherwise they are the inner intersection, never wider than any supporter, and confidence drops by 0.10. A group becomes a candidate only if all of these hold:

- Every supporting stretch has correlation of at least 0.85.
- At least 2 other episodes agree. A season of exactly 2 episodes has a stricter pair rule: correlation of at least 0.95, picture share of at least 0.8, and the segment must sit at an opening or ending position in both episodes.
- A stretch cut by its own window or file limit says nothing about that edge, so each edge is taken only from supporters that saw it. If fewer than 2 saw an edge, the candidate is refused as clipped.
- Length: intro 5 to 240 s, credits 15 to 700 s. Intros under 20 s need both edges visually verified.
- Position: head candidates start before 60% of the episode, tail candidates after 50%.

One extra route exists for credits: credits seen by only one other episode count when both sit at the same distance from the end (within 3 s), near the end (within 90 s), with correlation of at least 0.95, picture share of at least 0.8, and both edges on a confirmed transition.

## 4. Edges to the exact frame (`edges.py`)

Starting from the audio edge, the engine walks outward at most 1 s while the frame is near-black or its perceptual hash matches the same moment in at least 2 other episodes. The first frame that is neither is story and is never taken. The edge must land on a real transition: a hard cut, the end of black, or the start of the file. Otherwise the audio edge stays.

If the audio edge is already story, the edge moves inward up to 6 s to the nearest transition into shared picture. Black frames at either end are trimmed. An edge still unverified is cut back to the last hard cut within 2.5 s for intros, or to the first black run or last hard cut within 8 s for credits with something after them. Frame times are the file's real timestamps, also on variable-frame-rate files.

## 5. Picture share

Audio alone is not enough, since a song can play over story. Each segment is measured on three chunks of up to 15 s: the share of frames that match another episode's picture or are black must be at least 0.60. If the shared picture ends inside the segment, the segment is cut there, and the same goes for a lead-in with no shared picture at the start. Black frames count toward the share but are never evidence of where shared picture starts or ends.

## 6. Split segments

Two segments of one type with a gap of up to 25 s merge only if every gap frame is near-black or matches at least 2 other episodes, or if the gap has the same duration in at least 2 other episodes with at least 40% of its frames shared and its first and last second shared. The second rule is the Detective Conan opening, where 14 s of episode-specific clips sit between two identical halves.

## 7. Picture-only fallback (`visual.py`)

When audio finds no intro in a set of at least 3 episodes, the first 300 s are compared by picture alone. A run counts at one constant offset, at least 8 s long, with at least 85% of frames matched and pixel-identical (median difference at most 5, 90th percentile at most 12). The references must agree within 1 s and both edges must sit on a visual transition. Confidence is capped at 0.75. Red Dwarf's title music scores 0.81, below the audio gate, and is found this way.

## 8. Previews (`preview.py`)

A next-episode preview does not repeat, but its shape does. A segment from the credits end to the file end is reported only if its length agrees within 1.5 s with at least 2 other episodes, the whole group spreads no more than 3 s, it runs 10 to 75 s, and it shares a card or a jingle with at least 2 of them in its first or last 3 s. The start uses the shortest length in the group, so credits do not leak in. Black and silence are not evidence.

Treat previews as a button, never an auto-skip. A synthetic test can make this stage report 27 s of story as a preview when only the end of the segment carries the shared evidence, and 14 of the 29 scored previews we examined rely on that end-only evidence. Our own output formats leave previews out of anything that would skip them automatically.

## 9. Recaps (`recap.py`, off by default, `--recap`)

Audio landmark fingerprints of the head region are matched against the whole audio of earlier episodes. A recap is a run of at least 8 s of 2 s buckets, each from one earlier episode. Narrated or re-mixed recaps are invisible to this. It decodes every episode in full, and it scored 1 of 3.

## 10. On-screen text credits (`ocr_credits.py`, optional, `--ocr`)

Only for episodes where matching found no credits. Keyframes of the last 450 s (900 s for long files) go through a text detector at 320 by 180, and dialogue subtitles, lower-thirds, static overlays and prose cards are filtered out. A segment is kept only if it reaches the end of the file within 1 s. Text runs that stop earlier were wrong too often: one Detective Conan episode produced a 51 s false credits segment in the middle of the story.

## What it does not do

It never reads container chapters, online databases or subtitle files. It never writes to a video file.
