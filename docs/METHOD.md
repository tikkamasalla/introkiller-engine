# How the engine decides

This page lists the rules the engine uses to decide what to report, so you can check or change them. The [README](../README.md) has the short version. Each value is a key in `CFG` at the top of `src/introkiller/pipeline.py`, or a constant in the module named. To override `CFG` from the command line, use `--config '{"ncc_min": 0.9}'`.

One rule comes before all the others: if the engine is not sure, it reports nothing. It records the reason under `rejected` in `details/<episode>.json`.

## 1. Windows

The engine reads only the start and end of each file, so a remote HTTP(S) file is not downloaded in full.

The head window is the first 300 s of an episode and the tail window is the last 300 s. If nothing is found, a second try covers 720 s and 600 s. Audio is decoded to mono at 8 kHz, and the Japanese track is preferred when a file has one.

## 2. Audio alignment (`align.py`)

The engine finds the parts of the audio that two episodes share.

The signal is limited to 80 to 1500 Hz and gain-normalised over 1 s. Lossy codecs rebuild high frequencies differently in each file, so only the low band identifies a recording reliably. A pre-emphasised full band scored 0.58 on two AAC copies of the same opening, and the band-limited signal scored 0.98. Gain normalisation lets a quiet theme count as much as loud dialogue.

FFT cross-correlation (a score for how well two signals line up) against up to 5 other episodes gives the top 3 time offsets. At each offset, a 0.1 s sliding correlation marks the stretches where both episodes carry the same recording. The threshold is 0.5, gaps up to 0.6 s are bridged, and stretches of 4 s or more are kept.

## 3. Clustering and gates (`pipeline.py`)

The engine reports a segment only when several episodes agree on it.

Stretches from different episodes form a group when their starts and ends agree within 3 s. If every supporter is within 0.2 s, the edges are the median. Otherwise the edges are the inner intersection, never wider than any supporter, and confidence drops by 0.10. A group becomes a candidate only if it passes all of these gates:

- Every supporting stretch has a correlation of at least 0.85.
- At least 2 other episodes agree. A season of exactly 2 episodes uses a stricter pair rule: correlation of at least 0.95, picture share of at least 0.8, and an opening or ending position in both episodes.
- A stretch cut off by its window or file limit says nothing about that edge. Each edge comes only from supporters that saw it, and if fewer than 2 saw an edge, the candidate is refused as clipped.
- Length is 5 to 240 s for intros and 15 to 700 s for credits. Intros under 20 s need both edges verified on the picture.
- Head candidates start before 60% of the episode, and tail candidates start after 50%.

Credits have one extra route. Credits seen by only one other episode count when both sit at the same distance from the end (within 3 s) and near the end (within 90 s). They also need a correlation of at least 0.95, a picture share of at least 0.8, and both edges on a confirmed transition.

## 4. Edges to the exact frame (`edges.py`)

The engine moves each edge to the exact frame where the shared part begins or ends.

Starting at the audio edge, it walks outward for at most 1 s while the frame is near-black or its perceptual hash (a short fingerprint of a frame) matches the same moment in at least 2 other episodes. The first frame that is neither is story, and the engine never takes it. The edge must land on a real transition: a hard cut, the end of black, or the start of the file. Otherwise the audio edge stays.

If the audio edge is already story, it moves inward by up to 6 s to the nearest transition into shared picture. Black frames at either end are trimmed. An edge that is still unverified is cut back to the last hard cut within 2.5 s for intros. For credits with something after them, it goes to the first black run or last hard cut within 8 s. Frame times are the file's real timestamps, including on variable-frame-rate files.

## 5. Picture share

A song can play over story, so audio alone is not enough.

The engine measures each segment on three chunks of up to 15 s. The share of frames that match another episode's picture, or are black, must be at least 0.60. If the shared picture ends inside the segment, the segment is cut there. The same applies to a lead-in with no shared picture at the start. Black frames count toward the share, but they never show where shared picture starts or ends.

## 6. Split segments

Some openings contain a section that differs in each episode, and the engine can join the halves.

Two segments of one type with a gap of up to 25 s merge in either of two cases. In the first, every gap frame is near-black or matches at least 2 other episodes. In the second, the gap has the same duration in at least 2 other episodes, at least 40% of its frames are shared, and its first and last second are shared. The second case covers the Detective Conan opening, where 14 s of episode-specific clips sit between two identical halves.

## 7. Picture-only fallback (`visual.py`)

When the audio finds no intro in a set of at least 3 episodes, the engine compares the first 300 s by picture alone.

A run counts at one constant offset, lasts at least 8 s, and has at least 85% of its frames matched and pixel-identical (median difference at most 5, 90th percentile at most 12). The references must agree within 1 s, and both edges must sit on a visual transition. Confidence is capped at 0.75. Red Dwarf's title music scores 0.81, below the audio gate, so this route finds it.

## 8. Previews (`preview.py`)

A next-episode preview has new footage each time, so the engine matches its shape.

A segment from the end of the credits to the end of the file is reported only if all of these hold:

- Its length agrees within 1.5 s with at least 2 other episodes, and the whole group spreads no more than 3 s.
- It runs 10 to 75 s.
- It shares a card or a jingle with at least 2 of them in its first or last 3 s.

The start uses the shortest length in the group, so credits do not leak in. Black and silence are not evidence.

Treat previews as a button, never as an automatic skip. A synthetic test can make this stage report 27 s of story as a preview when only the end of the segment carries shared evidence, and 14 of the 29 scored previews we examined rely on that end-only evidence. Our output formats leave previews out of anything that skips automatically.

## 9. Recaps (`recap.py`, off by default, `--recap`)

The engine matches audio fingerprints from the head region against the full audio of earlier episodes. A recap is a run of at least 8 s made of 2 s buckets, each from one earlier episode. Narrated or re-mixed recaps are invisible to this method. It decodes every episode in full, and it scored 1 of 3.

## 10. On-screen text credits (`ocr_credits.py`, optional, `--ocr`)

This stage finds credits that matching missed, by reading the text on screen.

It runs only on episodes where matching found no credits. Keyframes from the last 450 s (900 s for long files) go through a text detector at 320 by 180. Dialogue subtitles, lower-thirds, static overlays and prose cards are filtered out. A segment is kept only if it reaches the end of the file within 1 s. Text runs that stop earlier were wrong too often: one Detective Conan episode produced a 51 s false credits segment in the middle of the story.

## What the engine does not do

It never reads container chapters, online databases or subtitle files, and it never writes to a video file.
