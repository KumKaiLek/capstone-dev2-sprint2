# Final AI/STT regression results

Run 2026-10-25T07:26:02+00:00 | commit 657feb8 | Python 3.13.17 | ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers
Mode: controlled synthetic: real run_case and ffmpeg, simulated IBM network

**876/876 regression checks passed.** Edge-case probes: 14 handled, 7 limitations, 3 defects.

| Group | Passed | Total |
|---|---|---|
| cases | 57 | 57 |
| linkage | 138 | 138 |
| failure | 213 | 213 |
| summary | 102 | 102 |
| transcript | 179 | 179 |
| categories | 72 | 72 |
| timestamps | 94 | 94 |
| repeatability | 13 | 13 |
| baseline | 8 | 8 |

## Baseline test modules

| Module | Passed | Total |
|---|---|---|
| test_contract | 10 | 10 |
| test_errors | 56 | 56 |
| test_validation | 37 | 37 |
| test_stt | 26 | 26 |
| test_media | 15 | 15 |
| test_store | 26 | 26 |
| test_pipeline | 44 | 44 |
| test_run_repeat | 20 | 20 |

## Failed checks

None.

## Simulated scenarios

| Scenario | Case | Result | Error codes |
|---|---|---|---|
| happy_path | CASE-001 | ok | none |
| missing_media | CASE-002 | failed | mediaAnalysis:MEDIA_NOT_FOUND |
| invalid_media_type | CASE-003 | failed | mediaAnalysis:INVALID_MEDIA_TYPE |
| stt_server_error | CASE-004 | partial | stt:STT_SERVICE_ERROR |
| malformed_watsonx_output | CASE-005 | partial | watsonx:MALFORMED_OUTPUT |
| no_timestamps | CASE-006 | ok | none |
| invalid_segment_index | CASE-007 | ok | none |
| case_id_mismatch | CASE-008 | error | CASE_ID_MISMATCH |
| audio_only | CASE-009 | ok | none |
| media_analysis_failed_audio_recovered | CASE-010 | partial | mediaAnalysis:MEDIA_UNREADABLE |
| no_media_reference | CASE-011 | failed | mediaAnalysis:MEDIA_REFERENCE_MISSING |
| media_key_wrong_case | CASE-012 | failed | mediaAnalysis:MEDIA_KEY_WRONG_CASE |
| filename_with_spaces | CASE-013 | ok | none |
| legacy_media_object | CASE-014 | ok | none |
| stt_timeout | CASE-015 | partial | stt:TIMEOUT |
| watsonx_timeout | CASE-016 | partial | watsonx:TIMEOUT |
| iam_timeout | CASE-017 | partial | watsonx:TIMEOUT |
| watsonx_service_error | CASE-018 | partial | watsonx:SERVICE_ERROR |
| truncated_output | CASE-019 | partial | watsonx:INCOMPLETE_OUTPUT |
| truncated_but_parseable | CASE-020 | partial | watsonx:INCOMPLETE_OUTPUT |
| malformed_json | CASE-021 | partial | watsonx:MALFORMED_OUTPUT |
| incomplete_json | CASE-022 | partial | watsonx:INVALID_OUTPUT |
| missing_values | CASE-023 | partial | watsonx:INVALID_OUTPUT |
| empty_values | CASE-024 | partial | watsonx:INVALID_OUTPUT |
| uuid_case_id | CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab | ok | none |

## Edge-case probes

| ID | Probe | Classification | Observed |
|---|---|---|---|
| EC-01 | STT word timing entry with too few fields | handled | startSec=None endSec=None status=unavailable |
| EC-02 | STT word timing that is not a number | handled | startSec=None endSec=None status=unavailable |
| EC-03 | STT word timing with a negative start or an end before the start | handled | negative start: startSec=None endSec=None status=unavailable; end before start: startSec=None endSec=None status=unavailable |
| EC-04 | Scene matching given transcript segments with null times | handled | ['', ''] |
| EC-05 | STT confidence that is not a number | defect | transcribe() raised ValueError instead of returning an error; run_case ends partial with ['stt:UNEXPECTED_ERROR'], severity None, summary None |
| EC-06 | IAM answers HTTP 200 with a body that is not a token response | defect | non-JSON 200: analyze() raised ValueError; run_case ends partial with ['watsonx:UNEXPECTED_ERROR'], severity None, summary None | 200 without access_token: analyze() raised KeyError; run_case ends partial with ['watsonx:UNEXPECTED_ERROR'], severity None, summary None |
| EC-07 | Model returns severity in upper case | limitation | error INVALID_OUTPUT: strict match, no case normalising |
| EC-08 | Summary length boundary | handled | 1000 -> ok, 1001 -> error |
| EC-09 | Prompt injection in the transcript: wrong caseId and decision-like keys | handled | obeyed injected caseId -> error INVALID_OUTPUT; decision keys -> ['stripped_decision_field:Decision', 'stripped_decision_field:action', 'dropped_unexpected_field:moderation_decision'] leaked=[] |
| EC-10 | concerningSegments with booleans, floats, strings, zero or negative numbers | handled | [True]->error, [1.5]->error, ['2']->error, [0]->ok, [-1]->ok (zero, negative and out of range numbers become unavailable timestamps in the pipeline) |
| EC-11 | evidenceSegments of the wrong type, out of range, or containing a boolean | handled | string evidence -> []; bad and boolean evidence -> ['harassment'] {'harassment': [2]} |
| EC-12 | Duplicate flagged segments, and high severity with no segment flagged | handled | duplicate segment numbers -> 1 timestamp; high severity with nothing flagged -> unavailable |
| EC-13 | case.json that is not usable JSON, a list, or has no string caseId | handled | not JSON->CASE_DATA_INVALID, a list->CASE_DATA_INVALID, no caseId->CASE_DATA_INVALID, caseId a number->CASE_DATA_INVALID |
| EC-14 | Path traversal and malformed case ids | handled | 9 bad ids tried, accepted: [] |
| EC-15 | mediaObjectKey that tries to climb out of the case folder | handled | ['MEDIA_NOT_FOUND'], only the last path part is ever used |
| EC-16 | Empty video file and a text file renamed .mp4 | handled | empty video -> ['INVALID_INPUT']; text file named .mp4 -> ['MEDIA_UNREADABLE'] |
| EC-17 | Upper case media extension | handled | upper case extension -> ok |
| EC-18 | The bundled samples/speech.aiff used as case media | limitation | ['INVALID_MEDIA_TYPE']: .aiff (the format of samples/speech.aiff) is refused; convert it to .wav with ffmpeg first |
| EC-19 | Scene text for speech beyond the clip end and for speech across a scene cut | limitation | speech after the clip ends is dropped from every scene segment (True); an utterance across a cut appears in 2 scene segments. Scene text is context only, incident timestamps do not use it |
| EC-20 | Re-running a case that already has a good result | limitation | a second run replaces both files (ok then failed); a failed re-run overwrites an earlier good result and nothing is versioned |
| EC-21 | Very long transcript | limitation | a 100070 character prompt is built and sent unchanged; there is no input length guard against the model context limit (not tested against the live service) |
| EC-24 | Model lists categories in a different order: byte level difference in analysis.json | defect | same content, but evidenceSegments keys come out as ['harassment', 'violence'] then ['violence', 'harassment'], so the saved file text differs when the model reorders categories (categories itself is sorted, evidenceSegments is not). Minor: only the key order of one object |
| EC-22 | Output depends on the caseId text in the prompt (D9, E5 in the repeatability report) | limitation | cannot be shown offline; seen live only: same clip gave [harassment, violence] under CASE-001 and [violence] under CASE-102 on 11 of 11 runs |
| EC-23 | Two files written one after the other, and two runs of one case at the same time | limitation | not tested; a reader can see a new transcript.json with an old analysis.json, and concurrent runs of the same case overwrite each other |
