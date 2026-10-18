# Repeatability report, Sprint 3: Run Repeatability Tests & Integration Handoff

`python run_repeatability.py 5` was run live against IBM Speech to Text and watsonx.ai
(`ibm/granite-4-h-small`, temperature 0) on branch `sprint3-ai-hardening`, after the Phase 1
refinement and Phase 2 error handling. It made 35 runs (7 cases × 5) in 72 seconds and exited 0.
Raw output for every run is in `outputs/sprint3/repeatability/<case>/run<i>.json`, the per-case
results in `results.json`, and the printed report in `run_repeatability_stdout.txt`.

## What is checked, per case, across all 5 runs

| Check | How |
|---|---|
| Severity identical | exact equality |
| Categories identical | exact equality, order included |
| Timestamps identical | exact equality of start, end, reason and timestampStatus |
| Status and error codes identical | exact equality of the overall result and every `stage:code` |
| Summary rules | `run_repeat.py`'s `check_summary_rules` on every run: 1 to 3 sentences, at most 1000 characters, no decision or recommendation phrase. A failed stage must have no summary at all |
| Case ID linkage | `caseId` in `case.json`, `transcript.json`, `analysis.json` and the returned result all equal the case being run, read back from the store after every run |

## Results

| Case | Result on every run | Severity | Categories | Timestamps | Status / errors | Summary | caseId linked |
|---|---|---|---|---|---|---|---|
| V1 CASE-101 harmless | low, [], none, ok | identical | identical | identical | identical | rules passed 5/5, 1 wording | 5/5 |
| V2 CASE-102 harassment/threat | high, **[violence]**, 3.64-9.7s, ok | identical | identical | identical | identical | rules passed 5/5, 2 wordings | 5/5 |
| V3 CASE-103 one concerning line | medium, [harassment], 0.0-11.54s, ok | identical | identical | identical | identical | rules passed 5/5, 1 wording | 5/5 |
| V4 CASE-104 mild frustration | low, [], none, ok | identical | identical | identical | identical | rules passed 5/5, 1 wording | 5/5 |
| V5 CASE-105 no speech | null, [], none, partial, `stt:EMPTY_TRANSCRIPT` | identical | identical | identical | identical | no summary on any run | 5/5 |
| V6 CASE-106 missing media | null, [], none, failed, `mediaAnalysis:MEDIA_NOT_FOUND` | identical | identical | identical | identical | no summary on any run | 5/5 |
| Forced failure: CASE-101 with `STT_TIMEOUT=0.001` | null, [], none, partial, `stt:TIMEOUT` | identical | identical | identical | identical | no summary on any run | 5/5 |

All 7 cases were stable on every exact-equality check, and the caseId matched in all three files
on all 35 runs. Stable is not the same as correct: V2 is stable on a result that misses
`harassment` (D9 in `docs/DEFECT_LOG.md`).

## Comparison with the Week 3 single run

Week 3 values are from the committed `outputs/validation/CASE-10x.json` (one live run each, before
Sprint 3).

| Case | Week 3 single run | Sprint 3, 5 runs | Change |
|---|---|---|---|
| V1 | low, [], none | low, [], none, 5/5 | same, now shown stable |
| V2 | high, [harassment, violence], 3.64-9.7s | high, [violence], 3.64-9.7s, 5/5 | **worse**: harassment lost (D9) |
| V3 | medium, [harassment], 0.0-11.54s | medium, [harassment], 0.0-11.54s, 5/5 | same, now shown stable |
| V4 | low, [other], 0.02-4.28s | low, [], none, 5/5 | **fixed**: other gone, and stable where the baseline repeat gave 2 distinct results in 5 |
| V5 | partial, EMPTY_TRANSCRIPT | partial, EMPTY_TRANSCRIPT, 5/5 | same |
| V6 | failed, MEDIA_NOT_FOUND | failed, MEDIA_NOT_FOUND, 5/5 | same |
| Forced STT timeout | not possible in Week 3 (timeouts reported as NETWORK_ERROR, no override) | partial, `stt:TIMEOUT`, 5/5 | new |

## Remaining edge cases

| # | Edge case | Seen in | Status |
|---|---|---|---|
| E1 | V2 misses `harassment`; the same clip under caseId CASE-001 does not | 11/11 live V2 runs after the refinement | Open, D9. The Auditor reads the transcript and may add it |
| E2 | V3 timestamp is the whole clip, 0.0-11.54s, because Speech to Text returned one segment | every V3 run, Week 3 and Sprint 3 | Open, a Speech to Text limit, not a pipeline defect. The time is real, never invented |
| E3 | V2 summaries add a detail not in the transcript: "regret their existence" (transcript: "i will make you regret it") | 4 of 5 repeatability runs | Open. The summary rules check only flags capitalised words, so it passed. A human must read the summary |
| E4 | One V2 summary still judges intent: "targets a specific person with the intent to cause harm" | 1 of 5 repeatability runs | Open. The prompt line reduced this (CASE-001 baseline 3/5 → 0/5) but did not remove it |
| E5 | Output depends on the caseId text (E1), so a stable result on one case ID is not proof of the same result for the same content under another | CASE-001 vs CASE-102 | Open |
| E6 | A truncated reply (`finish_reason: "length"`) has not happened live | none at max_tokens 800 | Covered by simulated scenarios through the real code only |
| E7 | After the forced-failure case, the stored `cases/CASE-101/transcript.json` and `analysis.json` hold the timeout result, since every run overwrites them | last run of the script | Expected. Run `python run_pipeline.py CASE-101` to restore a normal result |
