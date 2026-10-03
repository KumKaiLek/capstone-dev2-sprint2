# Defect log, Sprint 2 Week 3 stabilisation

Each entry is one commit on `sprint2-week3-stabilisation`. Format: defect, cause, fix, before/after test.

## D1: Case ID only accepted CASE-001 style

**Defect.** `valid_case_id` in `src/store.py` only matched `CASE-` followed by digits. Dev1's backend now issues case IDs as `CASE-<uuid>`, for example `CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab`. Every one of those would have been refused with `INVALID_CASE_ID`.

**Cause.** `CASE_ID_PATTERN = re.compile(r"^CASE-[0-9]{3,}$")` assumed the only format we had seen (the test fixtures).

**Fix.** Pattern widened to `^CASE-[A-Za-z0-9-]{3,64}$`, so letters and hyphens are accepted alongside digits. The character class still has no `/` or `.`, so a case ID with a path separator or `..` is still rejected, the same as before. The error message now mentions both formats.

**Before/after test.** `tests/test_store.py`, "valid case ids: CASE-\<uuid\> style (D1)" and "bad case ids rejected ... including / and .. in a uuid-style id (D1)". Before the fix, `valid_case_id("CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab")` was `False`; after, `True`. `valid_case_id("CASE-abc/def")` and `valid_case_id("CASE-abc..def")` are `False` both before and after.

## D2: Media reference only read the old mediaObject field

**Defect.** `run_case` only ever read `meta.get("mediaObject")`, the shape the pipeline invented before Dev1's real backend existed. Dev1's backend now writes `mediaObjectKey` (a COS key, `cases/<caseId>/<originalname>`) and `fileName`, and no longer writes `mediaObject` at all, so every real case would have failed with `MEDIA_REFERENCE_MISSING`. There was also no check that a key actually belonged to the case being processed, so a wrong or tampered key could have pulled in another case's video.

**Cause.** `src/pipeline.py` was written against an assumed contract before the real one was confirmed, and nothing in it was updated when Dev1's format changed.

**Fix.** Added `resolve_media_reference(meta, case_id)`, checked in order: `mediaObjectKey` (its `cases/<caseId>/` prefix is stripped and compared against the caseId being run; a mismatch is refused with `MEDIA_KEY_WRONG_CASE`, not silently used), then `fileName`, then the old `mediaObject` for backward compatibility. The media type comes from `contentType` (Dev1's coarse `"video"`/`"audio"`) first, then `mediaMimeType`, then the file extension, so `media_kind` now trusts Dev1's own classification instead of only guessing from the extension.

**Before/after test.** `tests/test_pipeline.py`, the D2 section. Before the fix, `resolve_media_reference` did not exist, and a case.json with `mediaObjectKey` but no `mediaObject` resolved to no media reference at all. After, `resolve_media_reference({"mediaObjectKey": "cases/CASE-001/My Clip.mp4", "contentType": "video"}, "CASE-001")` returns `("My Clip.mp4", "video", None)`, and the same key under a different caseId returns a `MEDIA_KEY_WRONG_CASE` error instead of being read.

## D3: File names rejected spaces and normal punctuation

**Defect.** `valid_filename` in `src/store.py` required the first character to be a letter or digit and only allowed `._-` after that. An original file name such as `My Clip (Final v2).mp4` or `résumé.mp4`, both ordinary names a person could give a file before uploading it, would be rejected as `INVALID_FILENAME`, so the case's own media file could never be read even though it really was in the case folder (`store.exists` returns `False` for an invalid name before it even checks the disk).

**Cause.** `FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")` was written as a narrow safe list instead of a block list, so it rejected most real file names, not just dangerous ones.

**Fix.** Replaced the pattern with explicit checks: empty or whitespace-only is rejected, over 150 characters is rejected, and so is a name containing `/`, `\`, `..` anywhere, or a control character (0x00 to 0x1F, 0x7F). Anything else, including spaces, parentheses, apostrophes, commas and accented letters, is allowed.

**Before/after test.** `tests/test_store.py`, "spaces and normal punctuation in a file name are now allowed (D3)" and "bad file names rejected ... (D3)". Before the fix, `valid_filename("My Clip (Final v2).mp4")` was `False`; after, `True`. `valid_filename("a/../b.json")`, a null byte and a newline in a name are `False` both before and after.

## D4: Categories were taken on the model's word, with no definitions

**Defect.** The prompt listed the category names with no explanation of what each one meant, so the model had to guess the boundary between, say, `harassment` and `violence`, or between `self_harm` and `violence` aimed at someone else. `validate_result` then accepted whatever category list came back as long as every name was a known one, with nothing checking that the model could actually point at content supporting it.

**Cause.** The category list in `src/schemas.py` was written as plain names for a first pass, and the review step after it only checked the names were spelled correctly, not that they were justified.

**Fix.** Added `CATEGORY_DEFINITIONS`, one line per category in `src/schemas.py`, included in the system prompt. For a segment-aware call, the prompt now also asks for `evidenceSegments`, an object mapping each returned category to the transcript segment numbers that support it. `validate_result` takes a new `segment_count` argument: when it is given (there were numbered segments), a category with no `evidenceSegments` entry, or only out-of-range segment numbers, is dropped from the result and a `category_dropped_no_evidence:<category>` warning is added, instead of being trusted outright. A call with no numbered transcript (`segment_count=None`) is unaffected, so this only applies where there is something to check evidence against. Schema validation (`caseId`, `severity`, `summary`, category names, duplicates) is unchanged, and `temperature` stays `0`.

**Before/after test.** `tests/test_validation.py`, the D4 section. Before the fix, `validate_result` had no `segment_count` parameter and returned every category the model named, evidence or not. After, a category with `evidenceSegments` pointing only at segment 99 of a 3-segment transcript is dropped with `category_dropped_no_evidence:<category>` in `warnings`, and `evidenceSegments` entirely missing from the model's output drops every category. `tests/simulated.py`'s fake watsonx response was updated to include `evidenceSegments` so the existing pipeline scenarios keep their categories; the `invalid_segment_index` scenario (which flags a segment that does not exist) now also loses its categories, since a model that hallucinates a segment number would plausibly cite the same number as its own evidence.

## D5: Tests and the seed script still simulated the old case.json

**Defect.** `tests/simulated.py`'s `dev1_case_json` built the pipeline's own older, invented shape (`title`, `status: "submitted"`, `mediaObject`) rather than the one Dev1's backend actually sends (`fileName`, `contentType`, `mediaMimeType`, `mediaObjectKey`, `submittedBy`, `submittedAt`, `status: "Queued"`, `isTestCase`, `exposureMinutes`). Every scenario `seed_synthetic_case.py` and `tests/test_pipeline.py` ran was therefore testing a case.json shape Dev1 does not produce, so passing tests here gave no assurance D2 through D4 actually work against his backend, and D1's CASE-\<uuid\> ids and D2's `mediaObjectKey` resolution had no end-to-end coverage at all.

**Cause.** The simulated layer was written before Dev1's backend existed and nothing had gone back to update it as the real contract arrived (the same root cause as D2).

**Fix.** `dev1_case_json` now builds Dev1's current shape by default, with a `legacy=True` option that still builds the old `mediaObject` shape for the one backward-compatibility scenario D2 is meant to keep working. Added four scenarios that only make sense against the new contract: `media_key_wrong_case` (a `mediaObjectKey` naming a different case, must be refused), `filename_with_spaces` (a real file name with spaces and punctuation, D3), `legacy_media_object` (the kept backward-compatibility case, D2), and `uuid_case_id` (a `CASE-<uuid>` style id end to end, D1). `seed_synthetic_case.py` needed no code change, since it only calls `tests.simulated`'s `SCENARIOS`/`run_scenario`, but its evidence under `outputs/pipeline/` was regenerated so it reflects the new format rather than the old one.

**Before/after test.** `tests/test_pipeline.py`, the four checks referencing D1/D2/D3/D5 right after the `no_media_reference` check. Before the fix, none of these scenarios or case.json shapes existed in the simulated layer, so running the full pipeline against a `CASE-<uuid>` id, a `mediaObjectKey`-only case, a spaced file name, or a key from another case was never exercised. `python seed_synthetic_case.py --live` now produces `outputs/pipeline/uuid_case_id.json`, `media_key_wrong_case.json`, `filename_with_spaces.json` and `legacy_media_object.json` alongside the original eleven.

## D6: Category order was not normalised

**Defect.** Found by running `python run_repeat.py CASE-001 3` against the real services: severity, categories (as a set) and timestamps matched on all three runs, but the second run returned `categories` as `["violence", "harassment"]` instead of `["harassment", "violence"]`. Nothing downstream orders categories, so the same real-world content could produce a differently ordered, textually different `analysis.json` from one run to the next, and `build_timestamps` in `src/pipeline.py` builds its reason text straight from that list (`", ".join(analysis["categories"])`), so the timestamp reason wording moved with it.

**Cause.** `validate_result` in `src/analysis.py` passed `obj["categories"]` straight through (filtered by D4's evidence check, but never reordered). watsonx.ai does not promise a stable order for a JSON array, so nothing enforced one.

**Fix.** After the evidence filter, `categories = sorted(categories, key=CATEGORIES.index)`, so the result always comes back in the fixed order of `CATEGORIES` in `src/schemas.py` (`hate_speech, harassment, violence, self_harm, sexual_content, misinformation, other`), regardless of what order the model used. This runs for both a segment-aware call and a legacy call with no segments. `build_timestamps` needed no change, since it reads the now-sorted `analysis["categories"]` directly, so its reason text follows the same order automatically. `run_repeat.py` was deliberately left doing exact equality on the full summary, including the `categories` list, rather than switched to a set comparison, so it still proves the stored output is byte-for-byte identical across runs, not just equivalent.

**Before/after test.** `tests/test_validation.py`, the D6 section. Before the fix, `analyze` returning `{"categories": ["violence", "harassment"], ...}` (plus matching `evidenceSegments`) gave back `["violence", "harassment"]` unchanged. After, it gives back `["harassment", "violence"]`, and a model returning all seven categories in reverse gives back `CATEGORIES` in its original order, for both a segment-aware call and a legacy call with no segments.
