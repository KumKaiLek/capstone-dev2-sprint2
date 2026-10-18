# Refinement log, Sprint 3: Harden Category / Timestamp Consistency

Branch `sprint3-ai-hardening`, built on `sprint2-week3-stabilisation`. Every number below comes from
the files in `outputs/sprint3/before/` (taken before any code change) and `outputs/sprint3/after/`
(taken after). Both sets were run live against IBM Speech to Text and watsonx.ai
(`ibm/granite-4-h-small`, temperature 0). The AI output stays advisory only; a human Auditor decides.

## Changes

| # | Change | Where | Why |
|---|---|---|---|
| R1 | Contract test: fails if `SEVERITIES`, `CATEGORIES`, the analysis.json or transcript.json field names, the `errors` entry shape, the `processingStatus` stages or the error envelope `{status, error: {code, message}}` change | `tests/test_contract.py` (new) | The schema is shared with Dev1, so a change has to be agreed first, not slip in during prompt work |
| R2 | The `other` definition now ends "NOT mild frustration, complaints, criticism or swearing that targets no person or group; return no category for those" | `src/schemas.py` `CATEGORY_DEFINITIONS` | V4 (CASE-104, frustration at a plan, nobody targeted) was labelled `other` in the Week 3 validation and in 4 of 5 baseline repeat runs |
| R3 | One prompt line under `summary`: "Describe only what is said. Do not assess the speaker's intent, motive or state of mind" | `src/analysis.py` `build_system_prompt` | 3 of 5 baseline CASE-001 summaries said "The threatening language and intent to cause harm are clear", which judges intent instead of describing content |
| R4 | Unusable Speech to Text word timings (not numbers, too short, negative, or end before start) now give `startSec`/`endSec` null, `timestampStatus` "unavailable" and a reason | `src/stt.py` `_segment_times` | Before this, `float()` or an index error raised out of `transcribe()`, which is documented as never raising, and would have crashed `run_case`. Shown by running the new tests against the old code: `ValueError: could not convert string to float: 'x'`, exit 1 |

Not changed, already correct and covered by existing tests: a category with no valid
`evidenceSegments` is dropped (D4); a flagged segment number outside the transcript, or a segment
with no timing, gives an `unavailable` timestamp with null start and end, never a guessed one
(`tests/test_pipeline.py`, "no timestamps" and "invalid segment index"). Temperature stays 0; a new
test in `tests/test_validation.py` checks the watsonx.ai request body still sends `temperature: 0`.

New tests: `tests/test_contract.py` 10 checks; `tests/test_validation.py` +4 (other definition,
describe-not-judge line, both lines without segments, temperature 0); `tests/test_stt.py` +4
(non-numeric, too short, end before start, negative start).

## Before / after, V1 to V6 (one live run each, `python run_validation.py`)

| Case | Before: severity, categories, timestamp | After: severity, categories, timestamp | Status before → after |
|---|---|---|---|
| V1 CASE-101 harmless | low, [], none | low, [], none | ok → ok |
| V2 CASE-102 harassment/threat | high, [harassment, violence], 3.64-9.7s | high, **[violence]**, 3.64-9.7s | ok → ok |
| V3 CASE-103 one concerning line | medium, [harassment], 0.0-11.54s | medium, [harassment], 0.0-11.54s | ok → ok |
| V4 CASE-104 mild frustration | low, **[other]**, 0.02-4.28s | low, **[]**, none | ok → ok |
| V5 CASE-105 silence | null, [], none (EMPTY_TRANSCRIPT) | null, [], none (EMPTY_TRANSCRIPT) | partial → partial |
| V6 CASE-106 missing media | null, [], none (MEDIA_NOT_FOUND) | null, [], none (MEDIA_NOT_FOUND) | failed → failed |

## Before / after, repeat runs (`python run_repeat.py <case> 5`)

| Case | Before | After |
|---|---|---|
| CASE-001 (same clip as V2) | 5/5 identical: high, [harassment, violence], 3.64-9.7s. 4 distinct summary wordings, 3 of 5 contain "intent to cause harm are clear" | 5/5 identical: high, [harassment, violence], 3.64-9.7s. 1 summary wording, 0 of 5 mention intent |
| CASE-104 (V4) | **did not match**, 2 distinct results: [other] with 0.02-4.28s on runs 1, 3, 4, 5; [] with no timestamp on run 2 | 5/5 identical: low, [], no timestamp |
| CASE-102 (V2) | not repeated before the change (single runs only: Week 3 and Phase 0 baseline both gave [harassment, violence]) | 5/5 identical: high, **[violence]**, 3.64-9.7s |

## Results

- **V4 fixed in these runs.** `other` is gone on the single validation run and on all 5 repeats,
  and V4 is now stable where it was not before (2 distinct results out of 5 → 1).
- **Intent judging gone in these runs.** 0 of 5 CASE-001 summaries mention intent (3 of 5 before).
- **V2 regressed.** After the change CASE-102 returns only `violence` on 6 of 6 live runs (1
  validation + 5 repeats). No `category_dropped_no_evidence` warning was raised, so the model
  itself stopped returning `harassment`; the evidence check did not remove it. The test plan
  expects [harassment, violence].
- **The model output depends on the caseId text.** CASE-001 and CASE-102 are the same clip
  (`cmp` reports the files identical), give identical transcript segments, and send identical media
  context; only the caseId in the prompt differs. CASE-001 gives [harassment, violence] 5/5 and
  CASE-102 gives [violence] 5/5. So a stable result on one case ID is not proof the same content
  gets the same categories under another.

## Remaining edge cases

| Edge case | Status |
|---|---|
| V2 loses `harassment` after R2/R3, and CASE-001 vs CASE-102 differ only by caseId | Open. Not fixed in this round; any further prompt change needs re-running V1 to V6 and the repeats again |
| V3: Speech to Text returned the whole 11.54s clip as one segment, so the timestamp is 0.0-11.54s | Open, a Speech to Text limit, not a pipeline defect. The timestamp is the real measured time of the only segment STT gave; nothing is papered over |
| Summaries can add details not in the transcript: after-run CASE-001 says "death threat", CASE-102 says "regret their existence"; the transcript has neither "death" nor "existence" | Open. `run_repeat.py`'s unverified-detail check only looks at capitalised words, so it did not flag these. A human still needs to read the summary |
| V4 summary still says the speaker "expresses frustration" | Accepted: frustration is what the words say ("this is so frustrating"), not an inferred motive |
