# AI pipeline handoff for Sprint 2 Week 3 testing

Written at the end of Sprint 2 Week 2. This covers the result contract and the known limitations of the Dev2 AI pipeline. The AI is advisory only. The human Auditor is always the final decision maker.

## What the pipeline does

```
stored video  ->  media analysis (ffmpeg)  ->  Speech to Text  ->  watsonx.ai  ->  two case documents  ->  case store
```

1. The media source finds the one video stored for the case (`cases/<caseId>/<video>`).
2. Media analysis probes the video, extracts the audio and frames, and finds scene cuts.
3. Watson Speech to Text turns the audio into a transcript with timed segments.
4. watsonx.ai (`ibm/granite-4-h-small`) reads the numbered transcript segments and returns severity, summary, categories and the segment numbers it thinks are concerning.
5. Code builds `transcript.json` and `case.json` and the case store saves them next to the video.

Every stage can fail without stopping the run. A failed stage is recorded, later stages that depend on it are marked unavailable, and the documents are still saved.

## Where things are stored

Same layout as Dev1's COS bucket. The local store uses the same paths under the project folder.

```
cases/<caseId>/video.mp4
cases/<caseId>/transcript.json
cases/<caseId>/case.json
```

Case IDs look like `CASE-001` (`CASE-` followed by 3 or more digits). Anything else is rejected.

## case.json

Dev1's fields are kept as they are. Everything else was added.

| Field | Meaning |
|---|---|
| caseId | The case ID |
| severity | `low`, `medium` or `high`, or `null` if watsonx.ai did not produce a result |
| summary | 1 to 3 neutral sentences, or `null` |
| categories | List from `hate_speech`, `harassment`, `violence`, `self_harm`, `sexual_content`, `misinformation`, `other`. Empty list if none |
| timestamps | List of `{start, end, reason, timestampStatus}`. Times are in seconds (see the rules below) |
| processingStatus | `{stt, mediaAnalysis, watsonx}`. Each is `ok`, `failed` or `unavailable` |
| advisory | Always `true`, set by code |
| requiresHumanReview | Always `true`, set by code |
| model | The watsonx.ai model id, or `null` |
| media | `{fileName, durationSeconds, hasAudio, frameCount, sceneChanges}`, or `null` if media analysis failed |
| sceneSegments | Visual scene cuts with `segmentId`, `startSec`, `endSec`, `label`, `frameFiles` and `transcriptText`. No severity. Not evidence of an incident |
| errors | List of `{stage, code, message}` for every failed or unavailable stage |
| warnings | Notes from validating the model output, for example `output_wrapped_in_code_fence` |

## transcript.json

Dev1's `transcript` and `confidence` are kept. Everything else was added.

| Field | Meaning |
|---|---|
| caseId | The case ID |
| transcript | Full text, or `null` |
| confidence | Average confidence from Speech to Text, or `null` |
| status | `ok`, `failed` or `unavailable` (the same value as `processingStatus.stt`) |
| error | `null`, or `{code, message}` |
| segments | List of `{startSec, endSec, text, confidence}`. Times can be `null` if Speech to Text gave none |
| source, model, durationSeconds | The audio file name, the Speech to Text model, and the length in seconds |

## Timestamp rules

- Incident timestamps come only from Speech to Text segment times. watsonx.ai returns the numbers of the segments it flags (1 based) and the code looks up the measured start and end. The model never supplies a time.
- If a timestamp cannot be given, `start` and `end` are `null`, `timestampStatus` is `unavailable` and `reason` says why. It is never 0 and never estimated.
- This happens when the model names a segment that does not exist, when the segment has no timing, and when severity is `medium` or `high` but no segment was named.
- A timestamp covers the whole Speech to Text segment (one stretch of speech between pauses), not the exact words.
- `low` severity with nothing flagged gives an empty `timestamps` list.

## Failure states

`errors` holds one entry per problem. Codes by stage:

- mediaAnalysis: `MEDIA_NOT_FOUND`, `MEDIA_AMBIGUOUS`, `MEDIA_TOO_LARGE`, `MEDIA_READ_FAILED`, `MISSING_INPUT`, `FILE_NOT_FOUND`, `INVALID_INPUT`, `MEDIA_UNREADABLE`, `TOOL_MISSING`, `AUDIO_EXTRACTION_FAILED`, `FRAME_EXTRACTION_FAILED`, `SCENE_DETECTION_FAILED`, `PROCESSING_TIMEOUT`
- stt: `NO_AUDIO_TRACK`, `CONFIG_ERROR`, `NETWORK_ERROR`, `AUTH_FAILED`, `INVALID_INPUT`, `STT_SERVICE_ERROR`, `MALFORMED_RESPONSE`, `EMPTY_TRANSCRIPT`
- watsonx: `CONFIG_ERROR`, `MISSING_INPUT`, `NETWORK_ERROR`, `AUTH_FAILED`, `AUTH_OR_PROJECT_ACCESS`, `SERVICE_ERROR`, `MALFORMED_OUTPUT`, `INVALID_OUTPUT`

The case store returns its own errors when loading or saving: `INVALID_CASE_ID`, `INVALID_DOCUMENT`, `STORE_WRITE_FAILED`, `STORE_READ_FAILED`, `CASE_NOT_FOUND`, `CASE_DATA_INVALID`.

## How to run it

Settings are in `.env` (see `.env.example`). Keys are never printed.

```
python run_pipeline.py CASE-001                       fetch the stored video for the case, run everything, save the case
python run_pipeline.py samples/synthetic_video.mp4 CASE-001   use a video file directly
python run_load.py CASE-001                           load the stored case back, as an Auditor screen would
```

Offline tests, which need no keys and no internet:

```
python -m tests.test_pipeline
python -m tests.test_store
python -m tests.test_media_source
python -m tests.test_validation
python -m tests.test_media
python -m tests.test_stt
```

`CASE_STORE` chooses the backend. `local` is the default. `cos` needs `COS_API_KEY`, `COS_INSTANCE_CRN`, `COS_ENDPOINT`, `COS_BUCKET` and the `ibm-cos-sdk` package.

## Test evidence (synthetic samples only)

- `outputs/pipeline_CASE-001.json`: harmless sample, all stages ok, low severity.
- `outputs/pipeline_CASE-002.json`: synthetic concerning sample, high severity, one flagged segment with a measured timestamp.
- `outputs/pipeline_CASE-404.json`: no video stored, media stage failed, the rest unavailable, failure recorded.
- `outputs/transcript_*.json`: Speech to Text output for the sample audio.

## Known limitations and open items

Needs Dev1 to confirm:
- The timestamp and segment format, the persistence approach and the media reference. All of these were built to Dev1's prototype and have not been confirmed.
- How the Auditor console retrieves a case. The local `load` works, but Dev1's real retrieval path has not been tried.

Not verified:
- The COS backends have only been tested against a fake client. They have never run against a real bucket. The `COS_*` setting names are proposals, and `ibm-cos-sdk` is not installed or listed in `requirements.txt`.
- The CASE-002 sample video is made with text to speech from a synthetic script, not a real recording. The team chose to keep it as the concerning test sample.

Scope:
- Analysis is based on the transcript. Frames are extracted but not classified visually, so a video with no speech gets no meaningful severity.
- Scene segments are visual cuts only. Their `transcriptText` is matched by time overlap, so speech that crosses a cut can appear in two scenes.
- The code trusts the model to pick the concerning segments. It only checks that the numbers are valid and looks up their times.
- Severity levels and categories were agreed with Dev1 and have not been checked against an official specification.

Behaviour:
- watsonx.ai output that is malformed or invalid is retried once. Rate limits and server errors are not retried and there is no backoff.
- Speech to Text uses the English model `en-US_Multimedia`. There is no speaker separation.
- Limits: video 200 MB, audio 100 MB, one video per case, video types `.mp4`, `.mov`, `.mkv`, `.webm`.
- A run is synchronous. Each step has a timeout and there is no queue.
- The two documents are written one after the other (transcript first). A reader loading during a save could see a new transcript with an old case. Saving the same case twice replaces it.
