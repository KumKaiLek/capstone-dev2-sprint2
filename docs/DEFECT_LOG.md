# Defect log, Sprint 2 Week 3 stabilisation

Each entry is one commit on `sprint2-week3-stabilisation`. Format: defect, cause, fix, before/after test.

## D1: Case ID only accepted CASE-001 style

**Defect.** `valid_case_id` in `src/store.py` only matched `CASE-` followed by digits. Dev1's backend now issues case IDs as `CASE-<uuid>`, for example `CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab`. Every one of those would have been refused with `INVALID_CASE_ID`.

**Cause.** `CASE_ID_PATTERN = re.compile(r"^CASE-[0-9]{3,}$")` assumed the only format we had seen (the test fixtures).

**Fix.** Pattern widened to `^CASE-[A-Za-z0-9-]{3,64}$`, so letters and hyphens are accepted alongside digits. The character class still has no `/` or `.`, so a case ID with a path separator or `..` is still rejected, the same as before. The error message now mentions both formats.

**Before/after test.** `tests/test_store.py`, "valid case ids: CASE-\<uuid\> style (D1)" and "bad case ids rejected ... including / and .. in a uuid-style id (D1)". Before the fix, `valid_case_id("CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab")` was `False`; after, `True`. `valid_case_id("CASE-abc/def")` and `valid_case_id("CASE-abc..def")` are `False` both before and after.
