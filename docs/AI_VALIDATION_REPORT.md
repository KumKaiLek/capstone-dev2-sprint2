# AI validation report (Card 2)

Expected values are from `docs/TEST_PLAN.md`, written and committed before `run_validation.py` was run. Results are from a single live run of each case against the real Speech to Text and watsonx.ai services, saved under `outputs/validation/`. This is a correctness check against six synthetic test cases, not an accuracy benchmark: no percentage or pass rate is given, since no accuracy threshold has been confirmed with the client.

## Comparison table

| Case | Transcript (actual, shortened) | Severity exp → act | Summary (actual) | Categories exp → act | Timestamps (actual) | Status exp → act |
|---|---|---|---|---|---|---|
| V1 CASE-101 | "this is a routine status update for the weekly team meeting everyone please review the agenda before friday" | low → low | "The content is a brief, neutral status update for a team meeting, instructing attendees to review the agenda by Friday." | [] → [] | [] | ok → ok |
| V2 CASE-102 | "this is a synthetic test recording synthetic test script you are worthless and everyone hates you i know where you live and i will make you regret it" | high → high | "The speaker makes a hateful statement about the target, threatens them with violence, and claims to know their location." | [harassment, violence] → [harassment, violence] | 3.64-9.7s, segment 2 | ok → ok |
| V3 CASE-103 | "good morning everyone thanks for joining today's call if you do not finish this by tonight i will make sure you regret it let's move on to the next item on the agenda the quarterly budget review" | medium/high → medium | "The speaker issues a vague threat to punish someone if they do not complete a task by a deadline, then transitions to discussing a quarterly budget review." | violence and/or harassment → [harassment] | 0.0-11.54s, segment 1 (the whole clip) | ok → ok |
| V4 CASE-104 | "this is so frustrating this whole plan is stupid and i am sick of dealing with it" | low → low | "The speaker expresses frustration and dissatisfaction with a plan, using strong language to convey their annoyance." | [] → [other] | 0.02-4.28s, segment 1 | ok → ok |
| V5 CASE-105 | null | null → null | null | [] → [] | [] | failed → partial |
| V6 CASE-106 | null | null → null | null | [] → [] | [] | failed → failed |

## Verdicts

| Case | Field | Verdict | Reason |
|---|---|---|---|
| V1 | transcript, severity, summary, categories, timestamps, status | correct | Matches the test plan exactly; a neutral update gets low severity, no categories, no timestamps |
| V2 | transcript, severity, summary, categories, timestamps, status | correct | Matches the test plan exactly; the timestamp (3.64-9.7s) is the real measured time of the threat, not the whole clip |
| V3 | severity, categories, status | correct | medium severity and harassment both fall inside the test plan's hedged prediction (medium or high; violence and/or harassment) |
| V3 | timestamps | uncertain, test design limitation, not a pipeline defect | Speech to Text returned the whole 11.54s clip as a single segment instead of three, so the pipeline correctly reports the real segment it was given, but that segment spans the neutral lines too. The half-second pause inserted between the three spoken clips was not long enough for Speech to Text to treat them as separate results. This is the test case's construction, not a bug: the rule that a timestamp is only ever a real measured Speech to Text time, never invented, held exactly as designed |
| V4 | severity | correct | Mild frustration about a plan, not a threat or a targeted insult, correctly stayed low |
| V4 | categories | incorrect | Test plan expected no category for this content; the model added `other` anyway, backed by `evidenceSegments: {"other": [1]}` pointing at the whole clip. `other` is meant for concerning content that doesn't fit the named categories, and this content is not concerning. This is the clearest output-quality finding in this round |
| V5 | status (partial vs failed) | correct, test plan prediction was wrong | The test plan predicted `failed`; the actual result is `partial`, because media analysis genuinely succeeded (it's a real, readable video) and only Speech to Text failed to find speech. `partial` is the documented, correct behaviour for one failed stage among others that succeeded. The mistake was in the prediction, not the pipeline |
| V5 | transcript, severity, categories, timestamps | correct | All null/empty, exactly as expected, no severity or categories invented for an empty transcript |
| V5 | STT failure code | correct | `EMPTY_TRANSCRIPT`, distinct from `NO_AUDIO_TRACK`, which is the right distinction since this video has a real, silent audio track rather than no audio track at all |
| V6 | transcript, severity, categories, timestamps, status | correct | Case refused cleanly with `MEDIA_NOT_FOUND`, nothing invented, `stt` and `watsonx` both correctly `unavailable` |

**Counts** (one count per row in the verdicts table above, not per individual table cell, since several rows bundle multiple fields that all got the same verdict for the same reason): **8 correct, 1 incorrect, 1 uncertain** across V1-V6, plus **1 further uncertain** item below that sits outside V1-V6. Total: **8 correct, 1 incorrect, 2 uncertain**.

**Additional uncertain item, outside V1-V6:** the summary already saved for `CASE-001` (the stabilisation branch's concerning sample, see `outputs/pipeline/happy_path.json`) reads: "The synthetic video contains a short segment where the speaker verbally abuses a target, making threats and stating that others hate the target. **The threatening language and intent to cause harm are clear.**" The bolded clause is a judgement about the speaker's intent, not a description of what the transcript literally says. It is not necessarily wrong, but it goes beyond the transcript the way a `summary` is meant to stay neutral and descriptive, so it is recorded here as **uncertain**, not incorrect: a human Auditor reading it should know that "intent is clear" is the model's own inference, not a quoted fact.

## Failure behaviour

Both designed failure cases (V5 Speech to Text finding no speech, V6 a missing media file) behaved exactly as the rest of this pipeline has been built to: the run never crashes, the specific failing stage is recorded with a real error code, nothing downstream is invented (no severity, no categories, no timestamp), and `processingStatus` correctly distinguishes a stage that is `unavailable` because an earlier stage blocked it from one that actually `failed`.

## Sprint 3 AI refinement handoff

- **Over-flagging mild content into `other` (V4).** The clearest finding here. Worth a prompt change, for example tightening the `other` definition in `src/schemas.py`'s `CATEGORY_DEFINITIONS` to explicitly exclude mild frustration with no target, or adding a worked example to the system prompt. Not fixed in this round, since Card 2 was scoped to validate and report, not to change the prompt.
- **Single-segment transcripts lose within-clip timestamp resolution (V3).** Not a defect in this pipeline (D1-D7 already guarantee a timestamp is only ever a real Speech to Text time, never invented), but worth knowing for Sprint 3: if Speech to Text treats a recording as one segment, the incident timestamp can only ever be "the whole clip," even when the concerning content is a small part of it. If finer timestamp resolution turns out to matter for real cases, the fix is on the Speech to Text side (a different acoustic model, or VAD-based segmentation before sending audio to Speech to Text), not in how this pipeline reads the result it's given.
- **Judgement language in summaries (CASE-001).** Worth one line in the system prompt asking the model to describe the content, not assess the speaker's state of mind, if "intent is clear" style phrasing turns out to be common across more cases than this one.
