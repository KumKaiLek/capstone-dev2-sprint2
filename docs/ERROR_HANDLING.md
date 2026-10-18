# Error handling, Sprint 3: Timeout / Failure / Malformed Output

Every failure ends in a defined state. `run_case` never raises: either the case cannot be run at all
and the caller gets the error envelope `{"status": "error", "error": {"code", "message"}}` with
nothing written, or `transcript.json` and `analysis.json` are written with the failed stage marked
in `processingStatus` and one entry per failure in `errors` (`{"stage", "code", "message"}`).

**The rule for every failure:** `severity` and `summary` are `null`, and `categories` `[]`,
`evidenceSegments` `{}` and `timestamps` `[]`. They are never filled in, estimated or carried over
from an earlier run. `advisory` and `requiresHumanReview` are always `true`. Messages never contain
an API key, a token or the service URL.

`processingStatus` has three stages, `stt`, `mediaAnalysis` and `watsonx`, each `ok`, `failed` or
`unavailable` (did not run because an earlier stage gave it nothing). The overall result is `ok`
(every stage that applies is ok), `partial` (some ok) or `failed` (none ok).

## Failure table

| Failure | Error code | Stage status set | What the application receives | Fallback behaviour |
|---|---|---|---|---|
| Speech to Text does not answer in time **(new)** | `TIMEOUT` | `stt: failed`, `watsonx: unavailable` | Result `partial` for a video (media analysis ok), `failed` for audio. transcript.json `status: failed`, `transcript: null`, `segments: []` | No retry. Scene cuts from media analysis are still saved. `STT_TIMEOUT` (default 120s) |
| IAM token call does not answer in time **(new)** | `TIMEOUT` | `watsonx: failed` | `partial`; the real transcript is kept | No retry, chat is never called. `IAM_TIMEOUT`, else `WATSONX_TIMEOUT` (default 60s) |
| watsonx.ai chat does not answer in time **(new)** | `TIMEOUT` | `watsonx: failed` | `partial`; the real transcript is kept | No retry. `WATSONX_TIMEOUT` (default 60s) |
| Reply cut off at the token limit, `finish_reason: "length"` **(new)** | `INCOMPLETE_OUTPUT` | `watsonx: failed` (if the retry is also cut off) | `partial`; the real transcript is kept | One retry. A truncated reply is never accepted, even when the text happens to parse as JSON. A complete retry succeeds with warning `succeeded_on_retry` |
| A stage raises instead of returning an error (a code bug) **(new)** | `UNEXPECTED_ERROR` | that stage `failed` | `partial` or `failed`; message names only the exception type | No retry. The case still ends in a recorded state |
| watsonx.ai answers HTTP 5xx or another non-200 | `SERVICE_ERROR` | `watsonx: failed` | `partial` | No retry |
| watsonx.ai HTTP 401 / 403 | `AUTH_OR_PROJECT_ACCESS` | `watsonx: failed` | `partial` | No retry; check key, project ID, collaborator access |
| IAM rejects the key | `AUTH_FAILED` | `watsonx: failed` | `partial` | No retry |
| Network error other than a timeout (watsonx or IAM) | `NETWORK_ERROR` | `watsonx: failed` | `partial` | No retry |
| Reply is not JSON, or broken JSON | `MALFORMED_OUTPUT` | `watsonx: failed` | `partial` | One retry. JSON in a code fence or inside prose is extracted and flagged in `warnings` |
| JSON missing keys (incomplete), `null` values (missing) or empty values, wrong caseId, unknown severity or category | `INVALID_OUTPUT` | `watsonx: failed` | `partial`; message lists every problem | One retry |
| Category with no valid evidenceSegments | none, not a failure | `watsonx: ok` | The category is dropped, warning `category_dropped_no_evidence:<category>` | — |
| Flagged segment does not exist, or has no STT timing | none, not a failure | `watsonx: ok` | Timestamp `start: null, end: null, timestampStatus: "unavailable"` with a reason | Never a guessed time |
| STT word timing unusable (not numbers, end before start) **(new)** | none, not a failure | `stt: ok` | Segment `startSec/endSec: null`, `timestampStatus: "unavailable"`, reason | Before Sprint 3 this crashed `transcribe()` |
| Speech to Text HTTP 5xx | `STT_SERVICE_ERROR` | `stt: failed`, `watsonx: unavailable` | `partial` (video) / `failed` (audio) | No retry |
| Speech to Text HTTP 401 / 403 | `AUTH_FAILED` | `stt: failed` | as above | No retry |
| Speech to Text HTTP 400, unsupported or empty audio | `INVALID_INPUT` | `stt: failed` | as above | No retry |
| Speech to Text network error | `NETWORK_ERROR` | `stt: failed` | as above | No retry |
| Speech to Text response unreadable | `MALFORMED_RESPONSE` | `stt: failed` | as above | No retry |
| No speech in the audio (V5) | `EMPTY_TRANSCRIPT` | `stt: failed`, `watsonx: unavailable` | as above | watsonx.ai is not called with an empty transcript |
| Video has no audio track | `NO_AUDIO_TRACK` | `stt: unavailable`, `watsonx: unavailable` | `partial` | Scene cuts still saved |
| Media file named in case.json is not in the folder (V6) | `MEDIA_NOT_FOUND` | `mediaAnalysis: failed`, others `unavailable` | `failed`; both files still written | — |
| case.json has no media reference / unsupported type / key from another case | `MEDIA_REFERENCE_MISSING` / `INVALID_MEDIA_TYPE` / `MEDIA_KEY_WRONG_CASE` | `mediaAnalysis: failed` | `failed` | The other case's file is never read |
| ffmpeg / ffprobe failure | `MEDIA_UNREADABLE`, `TOOL_MISSING`, `PROCESSING_TIMEOUT`, `AUDIO_EXTRACTION_FAILED`, `FRAME_EXTRACTION_FAILED`, `SCENE_DETECTION_FAILED` | `mediaAnalysis: failed` | `partial` if audio could still be recovered, else `failed` | Audio extraction is tried on its own, warning `audio_recovered_after_media_analysis_failed` |
| A timeout setting is not a positive number | `CONFIG_ERROR` | stage that needs it `failed` | `partial` / `failed` | No call is made with a bad timeout |
| Missing key or URL in .env | `CONFIG_ERROR` | stage `failed` | `partial` / `failed` | — |
| Bad caseId, no case.json, case.json without caseId, caseId mismatch | `INVALID_CASE_ID`, `CASE_NOT_FOUND`, `CASE_DATA_INVALID`, `CASE_ID_MISMATCH` | none | Error envelope, nothing written | — |
| Saving transcript.json or analysis.json fails | `STORE_WRITE_FAILED` (in `saved`) | unchanged | An ok run becomes `partial` | — |

## Settings

| Variable | Default | Applies to |
|---|---|---|
| `STT_TIMEOUT` | 120 | Speech to Text recognize call |
| `WATSONX_TIMEOUT` | 60 | IAM token call and watsonx.ai chat call |
| `IAM_TIMEOUT` | value of `WATSONX_TIMEOUT` | IAM token call only, so the chat call alone can be timed out |

Temperature stays 0 and `max_tokens` stays 800.

## Evidence

**Live, real IBM services** (`outputs/sprint3/failure/`), CASE-001:

| File | Command | Result |
|---|---|---|
| `live_stt_timeout_CASE-001.json` | `STT_TIMEOUT=0.001 python run_pipeline.py CASE-001` | `partial`, `stt: failed` `TIMEOUT` "Speech to Text did not answer in time", `watsonx: unavailable`, nothing filled in |
| `live_iam_timeout_CASE-001.json` | `WATSONX_TIMEOUT=0.001 python run_pipeline.py CASE-001` | `partial`, `watsonx: failed` `TIMEOUT` "IBM IAM did not answer in time"; the real transcript is kept, nothing filled in |
| `live_watsonx_chat_timeout_CASE-001.json` | `IAM_TIMEOUT=60 WATSONX_TIMEOUT=0.001 python run_pipeline.py CASE-001` | `partial`, `watsonx: failed` `TIMEOUT` "watsonx.ai did not answer in time"; the real transcript is kept, nothing filled in |

A live truncated reply was not produced: no live run in this sprint ended with `INCOMPLETE_OUTPUT`
at `max_tokens` 800, and lowering `max_tokens` to force one would change the production request. Truncation is covered
by the simulated scenarios below, which go through the real `call_chat` code.

**Simulated** (`outputs/sprint3/failure/simulated/`, `python run_failure_scenarios.py`): the real
stt, analysis and pipeline code with a fake network, one file per scenario: `stt_server_error`,
`stt_timeout`, `watsonx_timeout`, `iam_timeout`, `watsonx_service_error`, `truncated_output`,
`truncated_but_parseable`, `malformed_watsonx_output`, `malformed_json`, `incomplete_json`,
`missing_values`, `empty_values`.

**Tests**: `tests/test_errors.py` checks, for each scenario, the stage, the code, the overall
result and that nothing is filled in; the retry counts (2 chat calls for truncated and malformed
output, 1 for a timeout or service error, 0 after an IAM timeout); that the timeout variables
reach the real calls; and that bad timeout values give `CONFIG_ERROR`.
