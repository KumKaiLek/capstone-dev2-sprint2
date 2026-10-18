# AI pipeline handoff, Sprint 3

For PM, BA and Dev1. Written at the end of Sprint 3 on branch `sprint3-ai-hardening`, which builds
on `sprint2-week3-stabilisation`. `docs/HANDOFF_WEEK3.md` still describes the case folder, the
media lookup and the full field list; this note covers what changed. The AI is advisory only. The
human Auditor is always the final decision maker.

## The contract did not change

Same `SEVERITIES` (`low`, `medium`, `high`), same `CATEGORIES`, the same field names in
`transcript.json` and `analysis.json`, and the same error shapes:
`{"status": "error", "error": {"code", "message"}}` for a case that cannot run, and `errors` entries
`{"stage", "code", "message"}` in `analysis.json`. `tests/test_contract.py` now fails if any of
these change. Dev1's retrieval endpoint needs no change.

## What changed

| Area | Change | Detail |
|---|---|---|
| Categories | `other` no longer covers mild frustration or criticism that targets nobody | V4 now gets no category on 11/11 live runs (it got `other` in Week 3) |
| Summaries | The prompt tells the model to describe what is said, not the speaker's intent or state of mind | Reduced, not removed, see Known limits |
| Timestamps | Unusable Speech to Text word timings give an `unavailable` timestamp instead of crashing | D8 |
| Timeouts | New error code `TIMEOUT` for Speech to Text, the IAM token call and the watsonx.ai chat call, which used to be reported as `NETWORK_ERROR` | `STT_TIMEOUT` (default 120s), `WATSONX_TIMEOUT` (default 60s), `IAM_TIMEOUT` (token call only) |
| Truncated output | A reply cut off at the token limit gets `INCOMPLETE_OUTPUT`, is retried once and is never accepted | |
| Unexpected crashes | A stage that raises is recorded as `UNEXPECTED_ERROR`; the case still ends in a defined state | |
| Repeatability | `run_repeatability.py` runs cases N times and checks severity, categories, timestamps, summary rules and caseId linkage | All 7 cases stable over 5 runs, see `docs/REPEATABILITY_REPORT.md` |

## Failure states the application can now receive

On any failure, `severity` and `summary` are `null`, and `categories` `[]`, `evidenceSegments` `{}`
and `timestamps` `[]`. They are never filled in. Show the case as needing review, with the stage
and code from `errors`.

| `errors[].stage` | `errors[].code` | `processingStatus` | Overall result |
|---|---|---|---|
| `stt` | `TIMEOUT` **(new)** | `stt: failed`, `watsonx: unavailable` | `partial` (video), `failed` (audio) |
| `watsonx` | `TIMEOUT` **(new)** | `watsonx: failed` | `partial`, transcript kept |
| `watsonx` | `INCOMPLETE_OUTPUT` **(new)** | `watsonx: failed` | `partial`, transcript kept |
| any | `UNEXPECTED_ERROR` **(new)** | that stage `failed` | `partial` or `failed` |
| `watsonx` | `SERVICE_ERROR`, `AUTH_OR_PROJECT_ACCESS`, `AUTH_FAILED`, `NETWORK_ERROR`, `MALFORMED_OUTPUT`, `INVALID_OUTPUT`, `CONFIG_ERROR` | `watsonx: failed` | `partial` |
| `stt` | `STT_SERVICE_ERROR`, `AUTH_FAILED`, `INVALID_INPUT`, `NETWORK_ERROR`, `MALFORMED_RESPONSE`, `EMPTY_TRANSCRIPT`, `NO_AUDIO_TRACK`, `CONFIG_ERROR` | `stt: failed` (`unavailable` for `NO_AUDIO_TRACK`) | `partial` or `failed` |
| `mediaAnalysis` | `MEDIA_NOT_FOUND`, `MEDIA_REFERENCE_MISSING`, `INVALID_MEDIA_TYPE`, `MEDIA_KEY_WRONG_CASE`, ffmpeg codes | `mediaAnalysis: failed` | `failed`, or `partial` if audio was recovered |

The full table with the fallback for each is in `docs/ERROR_HANDLING.md`.

## How to run everything

Python 3.9 with the packages in `requirements.txt`, ffmpeg on the PATH for video, and `.env` from
`.env.example` for the live commands. The tests need no key.

| What | Command |
|---|---|
| All offline tests, one module at a time (pytest skips `test_media.py`, so run them directly) | `PYTHONPATH=. python -m tests.<module>` for `test_contract`, `test_errors`, `test_validation`, `test_stt`, `test_media`, `test_store`, `test_pipeline`, `test_run_repeat` |
| One case, live | `python run_pipeline.py CASE-001` |
| V1 to V6, live, expected vs actual | `python run_validation.py` (writes `outputs/validation/`) |
| One case N times, live | `python run_repeat.py CASE-104 5` |
| Repeatability of V1 to V6 plus a forced STT timeout, live | `python run_repeatability.py 5` (writes `outputs/sprint3/repeatability/`) |
| Simulated failure scenarios, no key | `python run_failure_scenarios.py` (writes `outputs/sprint3/failure/simulated/`) |
| A real timeout on demand | `STT_TIMEOUT=0.001 python run_pipeline.py CASE-001`, or `IAM_TIMEOUT=60 WATSONX_TIMEOUT=0.001 python run_pipeline.py CASE-001` for the chat call |
| Seed the synthetic cases | `python seed_synthetic_case.py` (add `--live` for real IBM on CASE-001) |

## Known limits

- **V2 misses `harassment` (D9, open).** CASE-102 returns `[violence]` on every live run since the
  refinement, while the identical clip under CASE-001 returns `[harassment, violence]`. The output
  depends on the caseId text, so one stable case is not proof for the same content under another ID.
  Two prompt fixes were tried and rejected (`docs/REFINEMENT_LOG.md`).
- **Whole-clip timestamps (V3).** When Speech to Text returns one segment, the timestamp is the whole
  clip. It is a real time, never invented, but it cannot point within the clip.
- **Summaries can still add or judge.** For example "regret their existence" (4/5 V2 runs) and "with
  the intent to cause harm" (1/5 V2 runs). The automatic summary check does not catch these; a
  human must read the summary.
- **Truncation is tested by simulation only.** No live reply has hit the 800-token limit.
- **Stable is not correct.** Temperature 0 gave identical results on 5 runs for every case here, but
  the rejected prompt attempts showed results can still vary run to run at temperature 0.
- **COS store not built.** `CASE_STORE=cos` still returns `NOT_IMPLEMENTED`; cases are read from the
  local `cases/` folder.
