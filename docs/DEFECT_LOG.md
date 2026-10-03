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
