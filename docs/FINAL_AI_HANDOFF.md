# Final AI/STT integration documentation and Dev2 technical handoff

For PM and Dev1. Written at the end of Sprint 3 on branch `sprint3-ai-hardening` (code at commit `657feb8`).
This is the one document to read to run, integrate or continue the AI pipeline. It keeps the detail that
`docs/HANDOFF_WEEK3.md` (field lists, case folder) and `docs/HANDOFF_SPRINT3.md` (what changed in Sprint 3) hold, and adds the
final regression results. The AI is advisory only. The human Auditor is always the final decision maker.

## Status in one view

| | |
|---|---|
| Contract | Frozen. `tests/test_contract.py` fails if severities, categories, field names, error shapes or processing stages change. Dev1's retrieval endpoint needs no change |
| Final regression | 876 of 876 checks pass (`docs/REGRESSION_REPORT.md`): 10 synthetic cases, 25 failure and edge scenarios, repeatability, the full failure matrix, plus the 8 existing test modules (234 checks) |
| Live evidence | 18 October, 35 live runs, 7 cases, all stable (`docs/REPEATABILITY_REPORT.md`). No source file has changed since. The final regression itself used simulated IBM services |
| Open items | D9 (V2 loses `harassment`, live only), D10 to D12 (minor, mitigated), the limitations in this document. Nothing blocks integration |
| Not built | COS store (`CASE_STORE=cos` returns `NOT_IMPLEMENTED`); cases are read from a local `cases/` folder |

## 1. Current AI flow

```
cases/<caseId>/case.json  ->  find the media it names  ->  Speech to Text  ->  watsonx.ai  ->  transcript.json + analysis.json
```

`run_case(caseId, store)` in `src/pipeline.py` runs the whole flow, never raises, and returns `ok`, `partial` or `failed` (or an error envelope
when the case cannot be run at all). `case.json` is read, never written.

| Step | What happens | Code |
|---|---|---|
| 1. Read the case | `case.json` must exist, be a JSON object, and its `caseId` must equal the folder name, otherwise the run is refused and nothing is written | `src/pipeline.py`, `src/store.py` |
| 2. Find the media | `mediaObjectKey` (prefix `cases/<caseId>/` must match this case), else `fileName`, else the older `mediaObject`. Type from `contentType`, then `mediaMimeType`, then the file extension | `resolve_media_reference`, `media_kind` |
| 3a. Audio | Goes straight to Speech to Text. `mediaAnalysis` is `unavailable` (not a failure) | |
| 3b. Video | ffmpeg: probe, extract audio (mono, 16 kHz wav), frames every 2 s, scene cuts (threshold 0.3). If this fails but the audio can still be extracted, the rest still runs | `src/media.py` |
| 4. Speech to Text | Watson STT, English model, word timings. Result becomes numbered segments | `src/stt.py` |
| 5. watsonx.ai | Reads the numbered segments, returns severity, summary, categories with evidence segment numbers, and the numbers of the concerning segments. Output is validated before anything is kept | `src/analysis.py` |
| 6. Timestamps | Built by code from the measured Speech to Text time of each flagged segment. The model never supplies a time | `build_timestamps` |
| 7. Save | `transcript.json` then `analysis.json`, each written atomically | `src/store.py` |

A failure in one stage is recorded and the other stages still run when they can. A stage that raises is recorded as `UNEXPECTED_ERROR`.
Frames are extracted but not classified: analysis is based on the transcript, so a video with no speech gets no meaningful severity.

## 2. Speech to Text integration

| | |
|---|---|
| Service | IBM Watson Speech to Text, `POST <STT_URL>/v1/recognize?model=<model>&timestamps=true` |
| Authentication | HTTP basic, user `apikey`, password `STT_API_KEY`. The key is never in the URL, a header or any output |
| Model | `STT_MODEL`, default `en-US_Multimedia`. English only, no speaker separation |
| Audio types | `.wav`, `.mp3`, `.flac`, `.ogg`, `.webm`. Maximum 100 MB. Empty files and other types are refused before any call |
| Video | Maximum 200 MB, `.mp4`, `.mov`, `.mkv`, `.webm`. `.aiff` is not supported anywhere; convert to `.wav` first |
| Timeout | `STT_TIMEOUT`, default 120 s, reported as `TIMEOUT` |
| Segments | One segment per Watson result (one stretch of speech between pauses). `startSec` and `endSec` are the first word's start and the last word's end |
| Unusable timing | Missing, not a number, too short, negative or ending before it starts gives `startSec` and `endSec` `null`, `timestampStatus` `unavailable` and a reason. Never guessed or repaired |
| Confidence | Mean of the segment confidences, or `null` |

`transcript.json` fields: `caseId`, `transcript`, `confidence`, `status` (`ok`, `failed`, `unavailable`), `error` (`null` or `{code, message}`),
`segments` (`startSec`, `endSec`, `text`, `confidence`, `timestampStatus`, `timestampReason`), `source`, `model`, `durationSeconds`.
When Speech to Text did not succeed, `transcript` is `null`, `segments` is `[]` and `error` says why. A recording that Speech to Text returns as one
segment can only be given one whole-clip timestamp (V3).

## 3. watsonx.ai integration

| | |
|---|---|
| Service | IBM watsonx.ai chat, `POST <WATSONX_URL>/ml/v1/text/chat?version=2025-02-11`, after an IBM IAM token call (`https://iam.cloud.ibm.com/identity/token`) |
| Model | `WATSONX_MODEL_ID`, default `ibm/granite-4-h-small`, `temperature` 0, `max_tokens` 800 |
| Authentication | The API key goes only to the IAM call. The chat call carries the bearer token and `project_id`. The key and token never appear in any output |
| Timeouts | `WATSONX_TIMEOUT` (default 60 s) for the IAM call and the chat call; `IAM_TIMEOUT` overrides the IAM call only. Reported as `TIMEOUT` |
| Prompt | System prompt: advisory role, exact severity and category lists, one-line definition of each category (`CATEGORY_DEFINITIONS`), describe only what is said and not the speaker's intent, return one JSON object. User message: the `caseId`, the numbered segments `[1] ...`, and a media context (type, duration, audio present, scene cuts) |
| Retry | One retry for `MALFORMED_OUTPUT`, `INVALID_OUTPUT` and `INCOMPLETE_OUTPUT`. Nothing else is retried and there is no backoff. HTTP 429 is not retried |

Validation of every reply (`validate_result`), in this order:

1. JSON is extracted (a code fence or surrounding prose is tolerated and flagged in `warnings`). Anything else is `MALFORMED_OUTPUT`.
2. A reply cut off at the token limit (`finish_reason: length`) is `INCOMPLETE_OUTPUT`, even when the text happens to parse.
3. Keys that look like a decision (`decision`, `action`, `verdict`, `remove`, `ban`, `takedown`, `enforcement`, `outcome`, `moderationdecision`, `finaldecision`) are stripped and flagged.
4. The `caseId` must equal the one sent, `severity` must be `low`, `medium` or `high`, `summary` a non-empty string of at most 1000 characters, `categories` a list of unique
   known values, `concerningSegments` a list of integers. Any problem is `INVALID_OUTPUT`, with every problem listed.
5. A category with no valid `evidenceSegments` entry (segment numbers inside the transcript) is dropped with the warning `category_dropped_no_evidence:<category>`.
6. `categories` is sorted into the fixed order of `CATEGORIES`.
7. `advisory` and `requiresHumanReview` are set to `true` by code. Unknown fields are dropped and flagged.

`analysis.json` fields: `caseId`, `severity`, `summary`, `categories`, `evidenceSegments`, `timestamps` (`start`, `end`, `reason`, `timestampStatus`),
`processingStatus` (`stt`, `mediaAnalysis`, `watsonx`, each `ok`, `failed` or `unavailable`), `advisory`, `requiresHumanReview`, `model`, `mediaType`, `mediaFile`,
`media`, `sceneSegments`, `errors` (`{stage, code, message}`), `warnings`. Scene segments are visual cuts only and are not evidence of an incident.

Timestamp rules: a flagged segment gives that segment's measured start and end (`available`). A segment number that does not exist, a segment with no timing, or `medium`
or `high` severity with nothing flagged gives `start` and `end` `null`, `unavailable` and a reason. `low` severity with nothing flagged gives `[]`. A time is never 0 and never estimated.

## 4. Shared Case ID schema

The same `caseId` ties every file and every stage together.

| Rule | Where it is enforced |
|---|---|
| A case ID looks like `CASE-001` or `CASE-<uuid>`: `^CASE-[A-Za-z0-9-]{3,64}$`. No `/`, no `..` | `valid_case_id`, checked before any file is touched. Otherwise `INVALID_CASE_ID` |
| Folder `cases/<caseId>/`, the same layout as Dev1's COS bucket | `src/store.py` |
| `case.json` `caseId` must equal the folder name | `CASE_ID_MISMATCH`, nothing written |
| `case.json` is Dev1's file and is read only | `READ_ONLY_FILE`; regression checks it is byte for byte unchanged |
| `mediaObjectKey` must name this case's folder | `MEDIA_KEY_WRONG_CASE`; another case's file is never read |
| A saved document's `caseId` must equal the folder | `INVALID_DOCUMENT` |
| The model must echo the `caseId` exactly | `INVALID_OUTPUT` otherwise, even if a transcript tries to change it (prompt injection probe EC-09) |
| `transcript.json` and `analysis.json` both carry the `caseId` | checked on every case in the regression (138 linkage checks) and on 35 live runs |

Files of a case:

| File | Written by | Fields the pipeline uses or writes |
|---|---|---|
| `case.json` | Dev1 | Used: `caseId`, `mediaObjectKey`, `fileName`, `contentType`, `mediaMimeType`; older `mediaObject` still accepted |
| the media file | Dev1 | Audio or video named in `case.json`. A name may have spaces and normal punctuation; path separators, `..` and control characters are refused |
| `transcript.json` | this pipeline | See section 2 |
| `analysis.json` | this pipeline | See section 3 |

The `caseId` text is part of the prompt, and live runs showed the model's categories can depend on it (D9). A stable result for one case ID is
not proof of the same result for the same content under another case ID.

## 5. Required environment and configuration

Python 3.9 or newer with `requests` and `python-dotenv` (`requirements.txt`), and `ffmpeg` and `ffprobe` on the PATH for video. The tests and the regression need no key.
Settings come from a `.env` file copied from `.env.example`. `.env` is git-ignored. **No credential is in this repository or in these documents**: `.env.example` holds placeholders
only, and a scan of every tracked and new text file for key-shaped strings found none.

| Variable | Required | Default | Used for |
|---|---|---|---|
| `WATSONX_API_KEY` | live | none | IBM IAM token call |
| `WATSONX_PROJECT_ID` | live | none | watsonx.ai project. The key's user must be a collaborator, else `AUTH_OR_PROJECT_ACCESS` |
| `WATSONX_URL` | live | none (`.env.example` shows the `us-south` host) | watsonx.ai host |
| `WATSONX_MODEL_ID` | no | `ibm/granite-4-h-small` | model |
| `STT_API_KEY` | live | none | Speech to Text key |
| `STT_URL` | live | none | Speech to Text URL including the instance id |
| `STT_MODEL` | no | `en-US_Multimedia` | Speech to Text model |
| `STT_TIMEOUT` | no | 120 | seconds for Speech to Text |
| `WATSONX_TIMEOUT` | no | 60 | seconds for the IAM and chat calls |
| `IAM_TIMEOUT` | no | `WATSONX_TIMEOUT` | seconds for the IAM call only |
| `CASE_STORE` | no | `local` | `local`, or `cos` (not built) |
| `CASE_STORE_DIR` | no | `.` | folder that holds `cases/` |

A missing key or URL, or a timeout that is not a number above 0, gives `CONFIG_ERROR` for that stage and no call is made.

### Steps to run or continue the pipeline

1. Clone the repository, check out `sprint3-ai-hardening`, create a virtual environment and `pip install -r requirements.txt`.
2. Install ffmpeg (video only) and check `ffmpeg -version` and `ffprobe -version`.
3. Copy `.env.example` to `.env` and fill in the six live settings with your own IBM credentials. Never commit `.env`.
4. Run the offline tests and the regression (below). They need no key.
5. Put a case under `cases/<caseId>/` (`case.json` plus the media file), or create synthetic ones with `python seed_synthetic_case.py`.
6. Run `python run_pipeline.py <caseId>`, then read the result with `python run_load.py <caseId>`.

| What | Command |
|---|---|
| Final regression (no key, needs ffmpeg) | `PYTHONPATH=. python -m tests.test_regression` writes `outputs/sprint3/regression/` |
| The 8 module tests, one at a time (pytest skips `test_media.py`) | `PYTHONPATH=. python -m tests.<module>` for `test_contract`, `test_errors`, `test_validation`, `test_stt`, `test_media`, `test_store`, `test_pipeline`, `test_run_repeat` |
| One case, live | `python run_pipeline.py CASE-001` |
| V1 to V6, live, expected against actual | `python run_validation.py` |
| One case N times, live | `python run_repeat.py CASE-104 5` |
| Repeatability of V1 to V6 plus a forced timeout, live | `python run_repeatability.py 5` |
| Simulated failure scenarios, no key | `python run_failure_scenarios.py` |
| A real timeout on demand | `STT_TIMEOUT=0.001 python run_pipeline.py CASE-001`, or `IAM_TIMEOUT=60 WATSONX_TIMEOUT=0.001 python run_pipeline.py CASE-001` for the chat call |
| Synthetic cases | `python seed_synthetic_case.py` (add `--live` for real IBM on CASE-001) |

## 6. Failure behaviour

Every failure ends in a defined state, and `run_case` never raises. The full table with the fallback for each failure is in `docs/ERROR_HANDLING.md`.

**The rule for every failure:** `severity` and `summary` are `null`, and `categories` `[]`, `evidenceSegments` `{}` and `timestamps` `[]`. They are never filled in, estimated or carried over.
`advisory` and `requiresHumanReview` stay `true`. Messages never contain a key, a token or a service URL. Show the case as needing review, with the stage and code from `errors`.

| Where | Error codes | Overall result |
|---|---|---|
| Run refused, nothing written | `INVALID_CASE_ID`, `CASE_NOT_FOUND`, `CASE_DATA_INVALID`, `CASE_ID_MISMATCH` | error envelope `{"status": "error", "error": {code, message}}` |
| `mediaAnalysis` | `MEDIA_REFERENCE_MISSING`, `MEDIA_KEY_WRONG_CASE`, `INVALID_MEDIA_TYPE`, `MEDIA_NOT_FOUND`, `MEDIA_UNREADABLE`, `TOOL_MISSING`, `AUDIO_EXTRACTION_FAILED`, `FRAME_EXTRACTION_FAILED`, `SCENE_DETECTION_FAILED`, `PROCESSING_TIMEOUT`, `INVALID_INPUT` | `failed`, or `partial` if the audio was recovered |
| `stt` | `TIMEOUT`, `STT_SERVICE_ERROR`, `AUTH_FAILED`, `INVALID_INPUT`, `NETWORK_ERROR`, `MALFORMED_RESPONSE`, `EMPTY_TRANSCRIPT`, `NO_AUDIO_TRACK`, `CONFIG_ERROR` | `partial` (video, scene cuts kept) or `failed` (audio) |
| `watsonx` | `TIMEOUT`, `INCOMPLETE_OUTPUT`, `SERVICE_ERROR`, `AUTH_OR_PROJECT_ACCESS`, `AUTH_FAILED`, `NETWORK_ERROR`, `MALFORMED_OUTPUT`, `INVALID_OUTPUT`, `CONFIG_ERROR`, `MISSING_INPUT` | `partial`, the real transcript is kept |
| any stage | `UNEXPECTED_ERROR` (a stage raised; only the exception type is recorded) | `partial` or `failed` |
| store | `INVALID_FILENAME`, `READ_ONLY_FILE`, `INVALID_DOCUMENT`, `STORE_WRITE_FAILED`, `STORE_READ_FAILED`, `NOT_IMPLEMENTED` | an `ok` run becomes `partial` if a save fails |

The overall result is `ok` when every stage that applies is `ok`, `failed` when none is, and `partial` otherwise. It is returned by the pipeline and is not stored in the files, so it can be
worked out from `processingStatus`. Retries: one for malformed, invalid or truncated model output; none for timeouts, HTTP errors or authentication, and none for Speech to Text.
Each of these states, and the retry counts, is checked by the final regression at unit, HTTP and pipeline level.

## 7. Known limitations

- **V2 misses `harassment` (D9, open).** The same clip returns `[violence]` under CASE-102 and `[harassment, violence]` under CASE-001, on every live run, so the output depends on the caseId text. Two prompt fixes were tried and rejected (`docs/REFINEMENT_LOG.md`). The Auditor reads the transcript and may add the category.
- **Whole-clip timestamps (V3).** If Speech to Text returns one segment, the timestamp is the whole clip. It is a real time, never invented. The regression (R103) shows a single line gets its own window when the clip is split.
- **Summaries can still add or judge.** For example "regret their existence" in 4 of 5 live V2 runs. The automatic check only flags capitalised words, so a human must read the summary.
- **Stable is not correct.** Temperature 0 gave identical results on 5 live runs of every case, but the rejected prompt attempts showed results can still vary at temperature 0.
- **Offline repeatability is by construction.** The regression's stub model is deterministic, so it shows the pipeline adds no variation. Model consistency is only shown by the live runs of 18 October.
- **Synthetic English audio only.** Text-to-speech samples, one language, no speaker separation. Frames are not classified visually.
- **Scene text is context.** Scene `transcriptText` repeats speech that crosses a cut and drops speech after the clip ends. Incident timestamps never use it.
- **No input length guard.** A very long transcript is sent unchanged; the model's context limit is untested. Limits are 100 MB audio and 200 MB video, one media file per case, untested at the boundary.
- **Results are overwritten.** Running a case again replaces both files, a failed re-run replaces an earlier good result, and the two files are written one after the other, so a reader can briefly see a new transcript with an old analysis. Concurrent runs of one case are untested.
- **Truncation is tested by simulation only.** No live reply has hit the 800 token limit.
- **COS store not built.** Dev1 has agreed his `GET /api/cases/:caseId` will read `transcript.json` and `analysis.json` from the case folder; that endpoint change was not built at the time of the last handoff.

## 8. Remaining edge cases and defects

The complete log is in `docs/REGRESSION_REPORT.md` (24 probes: 14 handled, 7 limitations, 3 defects) and `docs/DEFECT_LOG.md` (D1 to D12).

| ID | What | Status |
|---|---|---|
| D9 / E1 / EC-22 | V2 loses `harassment`; output depends on the caseId text | Open, live only |
| D10 | `evidenceSegments` key order follows the model's category order (content identical) | Open, minor. Fix: rebuild the object in the sorted order |
| D11 | A Speech to Text confidence that is not a number makes `transcribe()` raise | Open, minor. Guarded: `stt:UNEXPECTED_ERROR`, `partial`, nothing filled in |
| D12 | An IAM answer that is not a token response makes `analyze()` raise | Open, minor. Guarded: `watsonx:UNEXPECTED_ERROR`, `partial`, nothing filled in |
| E2 | V3 timestamp is the whole clip | Open, a Speech to Text limit |
| E3 / E4 | Summaries that add a detail or judge intent | Open. A human reads the summary |
| EC-07, EC-18 to EC-21, EC-23 | Strict severity case, `.aiff` refused, scene text edge cases, overwrite on re-run, no length guard, concurrency | Open limitations, see the report |

## 9. What each reader needs to do

- **Dev1:** nothing changes in the contract. The pipeline reads `cases/<caseId>/case.json` and the media, and writes `transcript.json` and `analysis.json` beside them. Keep `caseId` equal to the folder name, keep `mediaObjectKey` under `cases/<caseId>/`, and show a case with `processingStatus` `failed` or `partial` as needing review with the stage and code from `errors`.
  Until the COS store is built, the case folder has to be reachable by the process that runs `run_case`.
- **PM:** the AI pipeline is complete for Sprint 3 and the final regression passes. The open items above are known and none blocks integration. Live evidence is from 18 October; a fresh live run needs the team's IBM credentials.
- **Whoever continues:** apply the three one-line fixes for D10 to D12 with a test each, decide whether D9 needs a different approach than prompt wording (for example evidence based category checks or a larger model), and run `python run_repeatability.py 5` after any prompt or model change.
