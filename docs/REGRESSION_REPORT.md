# Final AI regression report, Sprint 3 (final week)

Final controlled synthetic regression of the AI/STT pipeline on branch `sprint3-ai-hardening`, commit
`657feb8`. The AI output stays advisory only; the human Auditor is the final decision maker.

**Result: 876 of 876 regression checks passed.** The edge-case probes found 14 handled cases, 7 limitations
and 3 defects (D10 to D12, all minor and all caught by the `UNEXPECTED_ERROR` guard, see below).

## What was run, and what was not

| | |
|---|---|
| Command | `PYTHONPATH=. python -m tests.test_regression` (needs ffmpeg, no key) |
| Code under test | The real `run_case`, case store, media adapter, Speech to Text normalisation, and watsonx.ai request, validation and retry code |
| Real | ffmpeg and ffprobe on generated synthetic videos and audio; every line of `src/` |
| Simulated | Only the IBM network layer. Speech to Text answers with a canned Watson response. watsonx.ai is a rule based stub reached through the real IAM and chat code, so a reply goes through the real `call_chat`, `extract_json` and `validate_result` |
| Not run | **Live IBM services.** This suite proves the plumbing, contract and failure behaviour. It says nothing about model quality |
| Evidence pack | `outputs/sprint3/regression/`: `regression_results.md`, `regression_results.json` (every check with its detail), `run_regression_stdout.txt` and the saved `transcript.json` and `analysis.json` of each case in `cases/` |

**Live evidence is from 18 October, not re-run for this report.** `docs/REPEATABILITY_REPORT.md` holds a live run of
35 runs (7 cases × 5) at commit `afe4c85`. No file under `src/`, `tests/` or the `run_*.py` scripts has changed since
that run, so it still describes the current code. A fresh live run needs credentials: `python run_repeatability.py 5`
and `python run_validation.py` (see `docs/FINAL_AI_HANDOFF.md`).

## Results by checklist item

| Checklist item | Checks | Passed | What was checked |
|---|---|---|---|
| Representative synthetic cases tested | 57 | 57 | 10 new cases R101 to R110 plus all 25 scenarios in `tests/simulated.py` ended in the expected state with the expected error codes |
| Case ID linkage | 138 | 138 | `caseId` identical in `case.json`, `transcript.json` and `analysis.json`; `case.json` byte for byte unchanged; a refused run writes nothing; no other case's ID appears in the saved files; a `CASE-<uuid>` ID works end to end |
| Transcript | 179 | 179 | Text equals the spoken source, one segment per utterance with the measured times, mean confidence, `durationSeconds`, segments carry the full contract, null transcript and no segments when Speech to Text did not succeed |
| Summary | 102 | 102 | 1 to 3 sentences, within 1000 characters, no decision wording, `null` on every failed stage, `advisory` and `requiresHumanReview` always true, no decision-like key anywhere |
| Category output | 72 | 72 | Values from the contract, unique, in the fixed `CATEGORIES` order even when the model lists them in reverse, every kept category has evidence segments inside the transcript, empty on failure |
| Timestamp behaviour | 94 | 94 | Every incident timestamp equals a measured Speech to Text segment time inside the clip, or is `null` with a reason; scene segments contiguous from 0 to the clip length |
| Repeatability | 13 | 13 | Each R case 5 times and each scenario 3 times, interleaved, in a fresh case store each time: identical status, `transcript.json` and `analysis.json` content |
| Failure handling | 213 | 213 | Every defined failure state at three levels (below), nothing filled in, no key, token, URL or project ID in any saved file |
| Baseline | 8 | 8 | The 8 existing test modules, 234 checks in all, all passing |

### The R cases

| Case | What it proves | Result |
|---|---|---|
| R101 harmless video | Neutral content gives `low`, no categories, no timestamps | ok |
| R102 harassment and threat video | `high`, `[harassment, violence]`, timestamp is the flagged segment only (4.5 to 7.6 s), scene cut at 4.0 s found by real ffmpeg | ok |
| R103 one threatening line between two neutral ones | Three scenes and three segments; the timestamp (4.6 to 7.6 s) is the middle line only, not the whole 12 s clip, and each scene holds the line spoken in it | ok |
| R104 audio only, mild language | `low`, no categories, `mediaType` audio, `mediaAnalysis` `unavailable` (not failed) | ok |
| R105 silent audio track | `EMPTY_TRANSCRIPT`, watsonx.ai never called, nothing invented | partial |
| R106 media file missing | `MEDIA_NOT_FOUND`, neither Speech to Text nor watsonx.ai called | failed |
| R107 video with no audio track | `NO_AUDIO_TRACK`, Speech to Text not called, scene cuts kept | partial |
| R108 `CASE-<uuid>` ID, file name `My Clip (Final v2).mp4` | Dev1 style ID and a spaced file name work end to end | ok |
| R109 unusable Speech to Text timing | Segment times `null`, timestamp `unavailable` with a reason, nothing guessed | ok |
| R110 Speech to Text times out | `TIMEOUT`, watsonx.ai never called | partial |

### The three failure levels

1. **Speech to Text** through the real `transcribe`: HTTP 401, 403, 400, 429, 500, 503; timeout, read timeout, connect
   timeout; connection and TLS errors; missing results, results not a list, result without alternatives, body that is not JSON,
   no speech, whitespace only; empty and wrong-type files; missing path and file. 37 checks, and each error is also checked for secrets.
2. **watsonx.ai** through the real IAM and chat code with a counted fake network: IAM 401, 500, timeout, connection error (chat never called);
   chat 401, 403, 429, 500, 503, timeout, connection error (one call, no retry); no choices, prose, broken JSON, cut off at the token limit, cut off but
   parseable (two calls, then an error); recovery on the second call; invalid severity, wrong caseId, null and empty values, missing keys; empty input;
   missing key, bad timeout values (`0`, `-5`, `soon`) giving `CONFIG_ERROR` with no call; `IAM_TIMEOUT` and `WATSONX_TIMEOUT` reaching the right call;
   request is temperature 0, `max_tokens` 800, bearer token only.
3. **Pipeline**: all 25 scenarios plus a stage that raises, for both Speech to Text and watsonx.ai, ending in `UNEXPECTED_ERROR` with `severity` and
   `summary` `null` and the exception message not copied into the file.

### Does the suite catch a regression?

Six deliberate breaks were applied to copies of the code, one at a time. Each made the suite fail:

| Break | Regression checks that failed | Existing test module that also failed |
|---|---|---|
| caseId check removed from `validate_result` | 1 (the wrong-caseId check) | `test_validation` 36/37 |
| `unavailable` timestamp given `0.0` to `0.0` instead of `null` | 4 (R109 twice, `no_timestamps`, `invalid_segment_index`) | `test_pipeline` 42/44 |
| category sorting removed | 8 (6 category checks, 2 repeatability checks) | `test_validation` 34/37 |
| Speech to Text timeout reported as `NETWORK_ERROR` | 5 (R110, `stt_timeout`, three timeout variants in the HTTP matrix) | `test_errors` 52/56 |
| a failed run given a default severity of `low` | 26 (R105, R106, R107, R110 and 16 failure scenarios) | `test_errors` 44/56, `test_pipeline` 41/44 |
| truncated reply accepted | 5 (`truncated_output`, `truncated_but_parseable`, three checks in the HTTP matrix) | `test_errors` 53/56 |

The new suite caught every break, and so did at least one of the existing test modules each time. So the regression suite is a second, wider net
(the same fault seen from the saved files of ten cases and 25 scenarios, plus repeatability), not the only detector.

## Remaining AI edge-case and defect log

Defects found by this regression carry on from `docs/DEFECT_LOG.md` (D1 to D9). None was fixed in this pass: the
task is to run and record, and a source change after the live run would make the 18 October evidence describe different code. Each has a
one-line fix that can be applied and tested in the next change.

### New defects (all minor, all mitigated)

| ID | Defect | Seen as | Mitigation in place | Proposed fix |
|---|---|---|---|---|
| D10 | `evidenceSegments` keeps the model's category order, while `categories` is sorted into the fixed order (D6) | EC-24. The same content saved with the model's categories in two orders gives two `analysis.json` files with the same content but different key order in `evidenceSegments` | Content is identical, and `run_repeat.py` and `run_repeatability.py` compare severity, categories, timestamps and status, not that object's key order | After the sort in `validate_result`, rebuild `evidence_out` as `{c: evidence_out[c] for c in categories}` |
| D11 | `normalise` in `src/stt.py` calls `float(conf)` on the confidence with no guard, so a confidence that is not a number makes `transcribe()` raise instead of returning an error | EC-05, `ValueError: could not convert string to float: 'high'` | `run_case` records the stage as `UNEXPECTED_ERROR`, the case ends `partial`, `severity` and `summary` stay `null` | Treat an unusable confidence as `None`, the way D8 treats unusable timing |
| D12 | `get_token` in `src/analysis.py` reads `r.json()["access_token"]` with no guard, so an IAM HTTP 200 with a body that is not JSON, or has no `access_token`, makes `analyze()` raise | EC-06, `ValueError` and `KeyError` | Same guard: `watsonx:UNEXPECTED_ERROR`, `partial`, nothing filled in | Catch `ValueError` and `KeyError` there and raise `AnalysisError("AUTH_FAILED", ...)` |

D11 and D12 are the same class as D8: a function documented as never raising that can. The guard added in Sprint 3
turns each into a recorded state, which the regression confirms by running `run_case` with exactly those inputs.

### Edge cases that are handled

EC-01 to EC-03 and EC-04 (unusable or missing Speech to Text timing, in `src/stt.py` and in scene matching),
EC-08 (summary length boundary), EC-09 (prompt injection in a transcript cannot change the `caseId`, and decision-like keys such as `Decision`,
`action` and `moderation_decision` never reach the result), EC-10 and EC-11 (bad `concerningSegments` and `evidenceSegments` types),
EC-12 (duplicate flagged segments; high severity with nothing flagged gives one `unavailable` timestamp), EC-13 (unusable `case.json`), EC-14 and EC-15
(path traversal in a case ID or media key), EC-16 (empty video, text file named `.mp4`), EC-17 (upper case extension).

### Limitations (open, not defects in the code)

| ID | Edge case | Status |
|---|---|---|
| EC-07 | Severity must match exactly (`high`, not `HIGH`); the model's reply is rejected with `INVALID_OUTPUT` after one retry | By design. The prompt gives the exact values |
| EC-18 | `samples/speech.aiff` cannot be used as case media: `.aiff` is refused with `INVALID_MEDIA_TYPE` | Convert to `.wav` with ffmpeg first |
| EC-19 | Scene `transcriptText` drops speech after the clip ends and repeats speech that crosses a scene cut | Scene text is context only; incident timestamps never use it |
| EC-20 | Running a case again replaces both output files, so a failed re-run overwrites an earlier good result and nothing is versioned | Expected today. Copy results out first if they matter |
| EC-21 | No input length guard: a very long transcript is sent unchanged (about 100,000 characters in the probe) | Not tested against the live service |
| EC-22 | The output depends on the caseId text in the prompt | **Open, D9.** Live only, cannot be reproduced offline |
| EC-23 | The two output files are written one after the other, and two runs of the same case at the same time overwrite each other | Not tested |

### Carried over from the live report (`docs/REPEATABILITY_REPORT.md`), still open

| # | Edge case | Status |
|---|---|---|
| E1 / D9 | V2 misses `harassment` on 11 of 11 live runs; the same clip under CASE-001 does not | Open. Two prompt fixes tried and rejected (`docs/REFINEMENT_LOG.md`). The Auditor reads the transcript and may add it |
| E2 | V3 timestamp is the whole clip because Speech to Text returned one segment | Open, a Speech to Text limit. The time is real, never invented. R103 shows the pipeline gives the single line's window when Speech to Text does split the clip |
| E3 | V2 summaries add a detail not in the transcript ("regret their existence") | Open. The automatic summary check only flags capitalised words, so a human must read the summary |
| E4 | One V2 summary still judged intent | Open. Reduced from 3 of 5 to 1 of 5 |
| E5 | Output depends on caseId text (same as EC-22) | Open |
| E6 | A reply truncated at the token limit has not happened live | Covered by simulated scenarios and 4 regression checks through the real code |
| E7 | After the forced-failure repeat, the stored `CASE-101` files hold the timeout result | Expected. Run `python run_pipeline.py CASE-101` to restore |

### Not covered by this regression

- **Model quality and consistency** (live only). The stub is deterministic by construction, so offline repeatability proves the pipeline adds no variation, not that the model gives none.
- **Real recordings, other languages, several speakers.** All media is synthetic and English.
- **Limits at the boundary** (100 MB audio, 200 MB video) and ffmpeg timeouts.
- **A real COS bucket.** `CASE_STORE=cos` still returns `NOT_IMPLEMENTED`.
- **Concurrent runs** and **a live truncated reply** (EC-23, E6).
