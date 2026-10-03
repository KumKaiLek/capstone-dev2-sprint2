# AI validation test plan (Card 2)

Written and committed before `run_validation.py` is run, so the expected values below are a prediction, not a result read back from the pipeline. All media is synthetic (text to speech via macOS `say`, plus ffmpeg for video), reusing `samples/synthetic_concerning_video.mp4` for V2. Case folders are `cases/CASE-10{1..6}/`, built in Dev1's real `case.json` shape.

Severity and categories are watsonx.ai's judgement, so "expected" for those is our prediction of a reasonable, defensible call, not a guarantee of what the model will say. Timestamps are not a prediction in the same sense: the pipeline only ever reports a timestamp window that is the real measured Speech to Text time of the segment watsonx.ai points at, so the expected window below is simply where the concerning line of text actually sits in the recording.

## V1 — harmless video, CASE-101

**Script:** "This is a routine status update for the weekly team meeting. Everyone please review the agenda before Friday."

**Expected**
- transcript gist: a routine status update about a weekly team meeting and an agenda
- severity: `low`
- categories: `[]`
- timestamps: `[]` (low severity, nothing flagged)
- status: `ok`

## V2 — harassment/threat video, CASE-102

Reuses `samples/synthetic_concerning_video.mp4`. **Script:** "This is a synthetic test recording." (pause) "Synthetic test script: you are worthless and everyone hates you, I know where you live and I will make you regret it."

**Expected**
- transcript gist: an opening neutral line, then a direct threat and insult
- severity: `high`
- categories: `harassment`, `violence`
- timestamps: one window covering the second line only (roughly 3.6 to 9.7 seconds, based on this same clip's measured timing in earlier runs), not the first line
- status: `ok`

## V3 — longer video, one concerning line in the middle, CASE-103

**Script**, three segments concatenated with a short pause between each: (1) "Good morning everyone, thanks for joining today's call." (2) "If you do not finish this by tonight, I will make sure you regret it." (3) "Let's move on to the next item on the agenda, the quarterly budget review."

**Expected**
- transcript gist: a neutral opening, one threatening line, a neutral close
- severity: `medium` or `high` (a direct, if brief, threat; we are not asserting which exact level the model will pick, only that it should not be `low`)
- categories: should include `violence` and/or `harassment`
- timestamps: one window matching segment 2 only, not segment 1 or segment 3 — this is the actual point of this test case, proving the timestamp tracks the real concerning segment and not the whole clip
- status: `ok`

## V4 — audio-only, mild language, CASE-104

**Script:** "This is so frustrating, this whole plan is stupid and I am sick of dealing with it."

**Expected**
- transcript gist: frustration about a plan, directed at the plan, not at a person
- severity: `low`
- categories: `[]` (nothing here targets a person or threatens harm)
- timestamps: `[]`
- status: `ok`, `mediaType` is `audio`, `mediaAnalysis` is `unavailable` not `failed` (no video to analyse)

## V5 — silence, no speech, CASE-105

A video with a real (silent) audio track, not an audio-free video, so this exercises Speech to Text actually finding no speech rather than there being no audio to send it.

**Expected**
- transcript: `null`, `status: "unavailable"` is wrong for this one; Speech to Text should return a result with no usable speech, so we expect `status: "failed"` with an `EMPTY_TRANSCRIPT` style error, not `NO_AUDIO_TRACK`
- severity: `null` (watsonx.ai never runs, there is no transcript to send it)
- categories: `[]`
- timestamps: `[]`
- status: `failed` (stt failed, mediaAnalysis ok, watsonx unavailable)

## V6 — failure case, missing media, CASE-106

`case.json` names `missing.mp4`, which is never actually placed in the case folder.

**Expected**
- transcript: `null`, `status: "unavailable"`
- severity: `null`
- status: `failed`, `mediaAnalysis` failed with `MEDIA_NOT_FOUND`, `stt` and `watsonx` both `unavailable`
- nothing invented: no timestamps, no categories, no summary

## What "correct" means here

A field is **correct** if it matches the expected value above, or for severity/categories on V2 and V3, if it is a defensible reading of the script even if not the exact value predicted. It is **incorrect** if it clearly contradicts the script (for example, flagging V1 or V4 as concerning, or missing the threat in V2 or V3). It is **uncertain** if the field is technically accurate but goes beyond what the transcript itself supports, for example a severity judgement or wording that implies something the words alone do not establish; this does not count against the pipeline's correctness, since the model is explicitly allowed to make a severity judgement, but it is recorded so a human reviewer knows where a judgement call, not a fact, is being reported as advisory output.

This is a correctness check, not an accuracy benchmark. No percentage or pass rate is reported, since no accuracy threshold has been confirmed with the client.
