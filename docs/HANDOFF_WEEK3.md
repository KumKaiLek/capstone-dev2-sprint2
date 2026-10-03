# AI pipeline handoff for Sprint 2 Week 3 testing

Written at the end of Sprint 2 Week 2. This covers the result contract, how to run the pipeline and its known limitations. The AI is advisory only. The human Auditor is always the final decision maker.

## What the pipeline does

```
cases/<caseId>/case.json  ->  find the media it names  ->  Speech to Text  ->  watsonx.ai  ->  transcript.json + analysis.json
```

- **Audio** named in case.json goes straight to Watson Speech to Text.
- **Video** goes through media analysis first (ffmpeg extracts the audio, takes frames and finds scene cuts), then Speech to Text.
- watsonx.ai (`ibm/granite-4-h-small`) reads the numbered transcript segments and returns severity, summary, categories (each backed by the segment numbers that support it) and the numbers of the segments it thinks are concerning. A category with no real supporting segment is dropped before the result is saved.
- A failure in one stage is recorded and the other stages still run when they can. The result is partial, never a crash.

## Case folder

The files of a case live under `cases/<caseId>/`, the same layout as Dev1's COS bucket. A case ID looks like `CASE-001` or `CASE-<uuid>` (`^CASE-[A-Za-z0-9-]{3,64}$`, so no `/` and no `..`), matching the id style Dev1's backend actually issues.

| File | Written by | Notes |
|---|---|---|
| `case.json` | Dev1 | Read only. We never write it. Names the media file |
| the media file | Dev1 | Audio or video, its name given in `case.json` |
| `transcript.json` | us | Speech to Text result |
| `analysis.json` | us | watsonx.ai result, timestamps and processing status |

`case.json` is Dev1's own file, in his backend's shape: `caseId`, `fileName`, `contentType` (`"video"` or `"audio"`), `mediaMimeType`, `mediaObjectKey` (a COS key, `cases/<caseId>/<originalname>`), `submittedBy`, `submittedAt`, `status`, `severity`, `isTestCase`, `exposureMinutes`. We use two things from it. `caseId` must equal the folder name, otherwise the run is refused and nothing is written. The media file is found in this order:
1. `mediaObjectKey`, with its `cases/<caseId>/` prefix stripped. A key naming a different case folder is refused with `MEDIA_KEY_WRONG_CASE`, never read.
2. `fileName`, used as given if there is no `mediaObjectKey`.
3. `mediaObject`, an older shape (a plain file name, or an object with a name under `key`/`objectKey`/`fileName`/`filename`/`name`/`path`/`file` and a type under `contentType`/`mimeType`/`mediaType`/`type`) kept only for backward compatibility, used when neither of the above is present.

The media type comes from `contentType` (Dev1's own `"video"`/`"audio"`) first, then `mediaMimeType`, then the file extension.

Supported media: audio `.wav`, `.mp3`, `.flac`, `.ogg`, `.webm`, and video `.mp4`, `.mov`, `.mkv`, `.webm`. A `.webm` counts as video unless the type says audio. A file name can have spaces and normal punctuation; only path separators, `..` and control characters are rejected.

## transcript.json

Dev1's `transcript` and `confidence` are kept. Everything else was added.

| Field | Meaning |
|---|---|
| caseId | The case ID |
| transcript | Full text, or `null` |
| confidence | Average confidence from Speech to Text, or `null` |
| status | `ok`, `failed` or `unavailable` (the same as `processingStatus.stt`) |
| error | `null`, or `{code, message}` |
| segments | List of `{startSec, endSec, text, confidence, timestampStatus, timestampReason}` |
| source, model, durationSeconds | The audio file, the Speech to Text model and the length in seconds |

Example from the synthetic case `CASE-001`:

```json
{
  "caseId": "CASE-001",
  "transcript": "this is a synthetic test recording synthetic test script you are worthless and everyone hates you i know where you live and i will make you regret it",
  "confidence": 0.95,
  "status": "ok",
  "error": null,
  "segments": [
    {"startSec": 0.02, "endSec": 1.9, "text": "this is a synthetic test recording", "confidence": 0.96,
     "timestampStatus": "available", "timestampReason": null},
    {"startSec": 3.64, "endSec": 9.7, "text": "synthetic test script you are worthless and everyone hates you i know where you live and i will make you regret it",
     "confidence": 0.94, "timestampStatus": "available", "timestampReason": null}
  ],
  "source": "video_audio.wav",
  "model": "en-US_Multimedia",
  "durationSeconds": 9.7
}
```

## analysis.json

Dev1's fields `caseId`, `severity`, `summary`, `categories` and `timestamps` are kept. Everything else was added.

| Field | Meaning |
|---|---|
| severity | `low`, `medium` or `high`, or `null` if watsonx.ai gave no result |
| summary | 1 to 3 neutral sentences, or `null` |
| categories | From `hate_speech`, `harassment`, `violence`, `self_harm`, `sexual_content`, `misinformation`, `other`, always in that fixed order regardless of the order watsonx.ai used. A category the model named with no real supporting segment is dropped before this is built. Empty list if none |
| timestamps | List of `{start, end, reason, timestampStatus}` in seconds (see the rules below) |
| processingStatus | `{stt, mediaAnalysis, watsonx}`, each `ok`, `failed` or `unavailable` |
| advisory | Always `true`, set by code |
| requiresHumanReview | Always `true`, set by code |
| model | The watsonx.ai model, or `null` |
| mediaType, mediaFile | `video` or `audio`, and the file name. `null` if the media could not be identified |
| media | For video: `{fileName, durationSeconds, hasAudio, frameCount, sceneChanges}`, otherwise `null` |
| sceneSegments | Visual scene cuts with `segmentId`, `startSec`, `endSec`, `label`, `frameFiles`, `transcriptText`. No severity. Not evidence of an incident |
| errors | List of `{stage, code, message}` for every failed stage |
| warnings | Notes such as `audio_only_no_media_analysis`, `output_wrapped_in_code_fence` or `category_dropped_no_evidence:<category>` (the model named that category but gave no segment that actually supports it) |

`mediaAnalysis` is `unavailable` for an audio case because there is no video to analyse. That is not a failure.

Example from `CASE-001` (frame lists shortened):

```json
{
  "caseId": "CASE-001",
  "severity": "high",
  "summary": "The content contains a synthetic voice making threats of violence and stating that the target is hated and worthless. It also includes a threat to physically harm the target.",
  "categories": ["harassment", "violence"],
  "timestamps": [
    {"start": 3.64, "end": 9.7, "reason": "segment 2 flagged by watsonx.ai (harassment, violence)", "timestampStatus": "available"}
  ],
  "processingStatus": {"stt": "ok", "mediaAnalysis": "ok", "watsonx": "ok"},
  "advisory": true,
  "requiresHumanReview": true,
  "model": "ibm/granite-4-h-small",
  "mediaType": "video",
  "mediaFile": "video.mp4",
  "media": {"fileName": "video.mp4", "durationSeconds": 9.77, "hasAudio": true, "frameCount": 5, "sceneChanges": [5.0]},
  "sceneSegments": [
    {"segmentId": 1, "startSec": 0.0, "endSec": 5.0, "label": "scene 1", "frameFiles": ["frame_001.jpg"], "transcriptText": "this is a synthetic test recording ..."},
    {"segmentId": 2, "startSec": 5.0, "endSec": 9.77, "label": "scene 2", "frameFiles": ["frame_004.jpg"], "transcriptText": "synthetic test script you are worthless ..."}
  ],
  "errors": [],
  "warnings": []
}
```

Example of a segment that could not be timed (from the `no_timestamps` scenario):

```json
{"start": null, "end": null, "timestampStatus": "unavailable",
 "reason": "segment 1 was flagged but Speech to Text gave no timing for it"}
```

## Timestamp rules

- Incident timestamps come only from Speech to Text segment times. watsonx.ai returns the numbers of the segments it flags (numbered from 1) and the code looks up the measured start and end. The model never supplies a time.
- If a timestamp cannot be given, `start` and `end` are `null`, `timestampStatus` is `unavailable` and `reason` says why. It is never 0 and never estimated.
- That happens when the model names a segment that does not exist, when the segment has no timing, and when severity is `medium` or `high` but no segment was named.
- A transcript segment without timing has `startSec` and `endSec` of `null`, `timestampStatus` `unavailable` and a `timestampReason`.
- A timestamp covers a whole Speech to Text segment (one stretch of speech between pauses), not the exact words.
- `low` severity with nothing flagged gives an empty `timestamps` list.

## Failures

`errors` in `analysis.json` holds one entry per failed stage. The overall result of a run is `ok`, `partial` or `failed`. It is returned by the pipeline and is not stored in the files, so it can be worked out from `processingStatus`.

- **Run refused, nothing written:** `INVALID_CASE_ID`, `CASE_NOT_FOUND`, `CASE_DATA_INVALID`, `CASE_ID_MISMATCH`
- **mediaAnalysis:** `MEDIA_REFERENCE_MISSING`, `MEDIA_KEY_WRONG_CASE`, `INVALID_MEDIA_TYPE`, `MEDIA_NOT_FOUND`, `MEDIA_UNREADABLE`, `TOOL_MISSING`, `AUDIO_EXTRACTION_FAILED`, `FRAME_EXTRACTION_FAILED`, `SCENE_DETECTION_FAILED`, `PROCESSING_TIMEOUT`, `INVALID_INPUT`, `FILE_NOT_FOUND`
- **stt:** `NO_AUDIO_TRACK`, `CONFIG_ERROR`, `NETWORK_ERROR`, `AUTH_FAILED`, `INVALID_INPUT`, `STT_SERVICE_ERROR`, `MALFORMED_RESPONSE`, `EMPTY_TRANSCRIPT`
- **watsonx:** `CONFIG_ERROR`, `MISSING_INPUT`, `NETWORK_ERROR`, `AUTH_FAILED`, `AUTH_OR_PROJECT_ACCESS`, `SERVICE_ERROR`, `MALFORMED_OUTPUT`, `INVALID_OUTPUT`
- **store:** `INVALID_FILENAME`, `READ_ONLY_FILE`, `INVALID_DOCUMENT`, `STORE_WRITE_FAILED`, `STORE_READ_FAILED`, `NOT_IMPLEMENTED`

If video analysis fails but the audio can still be extracted, Speech to Text and watsonx.ai still run and the warning `audio_recovered_after_media_analysis_failed` is added.

## How to run it

Settings are in `.env` (see `.env.example`). Keys are never printed.

```
python seed_synthetic_case.py            create the synthetic cases under cases/ and save every scenario to outputs/pipeline/ (simulated services, no keys needed)
python seed_synthetic_case.py --live     the same, but CASE-001 uses the real Speech to Text and watsonx.ai
python run_pipeline.py CASE-001          run one case that already has a case.json and its media in cases/CASE-001/
python run_load.py CASE-001              load the stored analysis.json and transcript.json, as an Auditor screen would
python run_repeat.py CASE-001 N          run an already stored case N times, report whether severity, categories and timestamps matched every run
```

Offline tests, which need no keys and no internet:

```
python -m tests.test_pipeline
python -m tests.test_store
python -m tests.test_validation
python -m tests.test_media
python -m tests.test_stt
```

`CASE_STORE=local` (the default) keeps the case files on disk. `CASE_STORE_DIR` sets the folder that holds `cases/`.

## Test evidence (synthetic data only)

Each scenario has its output in `outputs/pipeline/<scenario>.json`, showing the files as they were saved and that Dev1's `case.json` was left unchanged.

| Scenario | Case | Result |
|---|---|---|
| `happy_path` | CASE-001 | ok, real Speech to Text and watsonx.ai, flagged segment with a measured timestamp |
| `missing_media` | CASE-002 | failed, `MEDIA_NOT_FOUND`, failure recorded |
| `invalid_media_type` | CASE-003 | failed, `INVALID_MEDIA_TYPE` |
| `stt_server_error` | CASE-004 | partial, `STT_SERVICE_ERROR`, scene cuts kept |
| `malformed_watsonx_output` | CASE-005 | partial, `MALFORMED_OUTPUT`, transcript kept |
| `no_timestamps` | CASE-006 | ok, timestamps recorded as unavailable |
| `invalid_segment_index` | CASE-007 | ok, timestamp recorded as unavailable |
| `case_id_mismatch` | CASE-008 | refused, `CASE_ID_MISMATCH`, nothing written |
| `audio_only` | CASE-009 | ok, straight to Speech to Text |
| `media_analysis_failed_audio_recovered` | CASE-010 | partial, the rest still ran |
| `no_media_reference` | CASE-011 | failed, `MEDIA_REFERENCE_MISSING` |
| `media_key_wrong_case` | CASE-012 | failed, `MEDIA_KEY_WRONG_CASE`, the real file sitting next to it is never read |
| `filename_with_spaces` | CASE-013 | ok, file name `My Clip (Final v2).mp4` resolves correctly |
| `legacy_media_object` | CASE-014 | ok, the older `mediaObject` field still resolves |
| `uuid_case_id` | CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab | ok, a `CASE-<uuid>` style id works end to end |

Only `happy_path` uses the real IBM services. The other scenarios use simulated ones so that failures such as an HTTP 500 can be triggered, and the file says which services were used.

## Known limitations

Not built or not confirmed:
- **Local store instead of COS.** The COS store is a stub that returns `NOT_IMPLEMENTED`. Nothing has been run against a real bucket.
- **No Auditor retrieval endpoint yet.** Results can only be read with `run_load.py` or the store. Nothing is connected to Dev1's backend.
- **Some of this is still unconfirmed by Dev1.** `case.json`'s fields now match what his backend's prototype actually produces, but he has not formally signed off on them. `transcript.json` and `analysis.json`, including their file names, are our own choice, not something he specified.
- **English synthetic audio only.** Speech to Text uses the English model `en-US_Multimedia`, there is no speaker separation, and the samples are text to speech, not real recordings. The concerning sample video was made with text to speech from a synthetic script.

Scope:
- Analysis is based on the transcript. Frames are extracted but not classified visually, so a video with no speech gets no meaningful severity.
- Scene segments are visual cuts only. Their `transcriptText` is matched by time overlap, so speech that crosses a cut can appear in two scenes.
- The code trusts the model to pick the concerning segments. It only checks that the numbers are valid and looks up their times.
- A category needs at least one watsonx.ai-cited transcript segment to survive; one with none is silently dropped and only shows up as a `category_dropped_no_evidence:<category>` warning, not an error.
- Severity values (`low`/`medium`/`high`) follow the `severity` field already in Dev1's own case.json. The category list, and the one-line definition behind each category in the watsonx.ai prompt, was defined on our side and has not been confirmed with Dev1 or checked against an official specification.

Behaviour:
- watsonx.ai output that is malformed or invalid is retried once. Rate limits and server errors are not retried and there is no backoff.
- Limits: video 200 MB, audio 100 MB, one media file per case.
- A run is synchronous. Each step has a timeout and there is no queue.
- The two output files are written one after the other. A reader loading during a save could see a new transcript with an old analysis. Running a case again replaces both files.
