"""Offline tests for the case store. No COS, no IBM call, no key needed.
Run: python -m tests.test_store"""
import json
import os
import tempfile
from pathlib import Path
from src.config import ConfigError
from src.store import CosCaseStore, LocalCaseStore, default_store, valid_case_id

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


CASE = "CASE-001"
DOC = {"caseId": CASE, "severity": "low", "timestamps": [{"start": None, "end": None, "timestampStatus": "unavailable"}]}


def new_store():
    tmp = Path(tempfile.mkdtemp())
    return tmp, LocalCaseStore(tmp)


tmp, store = new_store()
saved = store.save(CASE, "analysis.json", DOC)
check("save works and reports the COS style key", saved["status"] == "ok" and saved["key"] == "cases/CASE-001/analysis.json")
check("file is written in the cases/<caseId>/ layout", (tmp / "cases/CASE-001/analysis.json").is_file())
loaded = store.load(CASE, "analysis.json")
check("load returns exactly what was saved", loaded["status"] == "ok" and loaded["data"] == DOC)
check("exists is true for a saved file and false for another", store.exists(CASE, "analysis.json") and not store.exists(CASE, "nope.json"))
store.save(CASE, "analysis.json", {**DOC, "severity": "high"})
check("saving again replaces the file", store.load(CASE, "analysis.json")["data"]["severity"] == "high")
check("no temp files are left behind", not list((tmp / "cases").rglob("*.tmp")))

r = store.save(CASE, "video.mp4", b"\x00\x01binary")
check("binary files can be saved and read back", r["status"] == "ok" and store.load(CASE, "video.mp4")["data"] == b"\x00\x01binary")
check("path gives the local file, or None when missing",
      store.path(CASE, "video.mp4") == str(tmp.resolve() / "cases/CASE-001/video.mp4") and store.path(CASE, "nope.mp4") is None)

# Dev1's case.json is read only
(tmp / "cases/CASE-001/case.json").write_text('{"caseId": "CASE-001", "mine": true}')
r = store.save(CASE, "case.json", {"caseId": CASE, "overwritten": True})
check("case.json is never written", r["error"]["code"] == "READ_ONLY_FILE"
      and json.loads((tmp / "cases/CASE-001/case.json").read_text()) == {"caseId": "CASE-001", "mine": True})
check("case.json can be read", store.load(CASE, "case.json")["data"]["mine"] is True)

# ids and names
check("valid case ids: CASE-001 style", valid_case_id("CASE-001") and valid_case_id("CASE-0001"))
check("valid case ids: CASE-<uuid> style (D1)", valid_case_id("CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab")
      and valid_case_id("CASE-abc123"))
bad_ids = [None, "", "CASE-1", "case-001", "../CASE-001", "CASE-001/../x", 5,
           "CASE-abc/def", "CASE-abc..def", "CASE-../../etc", "CASE-" + "a" * 65]
check("bad case ids rejected by save, load, exists and path, including / and .. in a uuid-style id (D1)", all(
    store.save(b, "analysis.json", DOC)["status"] == "error" and store.load(b, "analysis.json")["status"] == "error"
    and not store.exists(b, "analysis.json") and store.path(b, "analysis.json") is None for b in bad_ids))
bad_names = ["", "   ", "../x.json", "sub/x.json", "a/../b.json", "a\\b.json", None, "x" * 151,
             "control\x00char.json", "a\nb.json", "a\x7fb.json"]
check("bad file names rejected: path separators, .., control characters, empty (D3)", all(
    store.save(CASE, n, DOC)["error"]["code"] == "INVALID_FILENAME"
    and store.load(CASE, n)["error"]["code"] == "INVALID_FILENAME" and not store.exists(CASE, n) for n in bad_names))
good_names = ["My Clip (Final v2).mp4", "notes, v2 - draft.txt", "O'Brien's report.json", "résumé.mp4", ".hidden.json"]
check("spaces and normal punctuation in a file name are now allowed (D3)", all(
    store.save(CASE, n, DOC)["status"] == "ok" and store.load(CASE, n)["status"] == "ok" and store.exists(CASE, n)
    for n in good_names))
check("nothing was written outside the cases folder", sorted(p.name for p in tmp.iterdir()) == ["cases"])

# documents
r = store.save("CASE-002", "analysis.json", DOC)
check("document caseId must match the caseId given", r["error"]["code"] == "INVALID_DOCUMENT" and not (tmp / "cases/CASE-002").exists())
r = store.save("CASE-003", "analysis.json", {"caseId": "CASE-003", "x": {1, 2}})
check("document that is not JSON is rejected and nothing is written", r["error"]["code"] == "INVALID_DOCUMENT" and not (tmp / "cases/CASE-003").exists())
check("unsupported data type rejected", store.save(CASE, "analysis.json", 42)["error"]["code"] == "INVALID_DOCUMENT")

# load problems
check("missing file gives FILE_NOT_FOUND", store.load("CASE-404", "case.json")["error"]["code"] == "FILE_NOT_FOUND")
(tmp / "cases/CASE-005").mkdir()
(tmp / "cases/CASE-005/transcript.json").write_text("{not json")
check("corrupt JSON gives CASE_DATA_INVALID", store.load("CASE-005", "transcript.json")["error"]["code"] == "CASE_DATA_INVALID")
blocker = tmp / "blocker"; blocker.write_text("a file, not a folder")
r = LocalCaseStore(blocker).save(CASE, "analysis.json", DOC)
check("write problem gives STORE_WRITE_FAILED and does not raise", r["error"]["code"] == "STORE_WRITE_FAILED")

# COS stub
cos = CosCaseStore()
check("COS stub says NOT_IMPLEMENTED and never raises",
      cos.save(CASE, "analysis.json", DOC)["error"]["code"] == "NOT_IMPLEMENTED"
      and cos.load(CASE, "analysis.json")["error"]["code"] == "NOT_IMPLEMENTED"
      and cos.exists(CASE, "analysis.json") is False and cos.path(CASE, "video.mp4") is None)

# backend choice from the environment
keep = {k: os.environ.pop(k, None) for k in ("CASE_STORE", "CASE_STORE_DIR")}
try:
    check("local store is the default", isinstance(default_store(), LocalCaseStore))
    os.environ["CASE_STORE"] = "cos"
    check("CASE_STORE=cos gives the COS stub", isinstance(default_store(), CosCaseStore))
    os.environ["CASE_STORE"] = "database"
    try:
        default_store(); ok = False
    except ConfigError:
        ok = True
    check("unknown store type gives a config error", ok)
finally:
    for k, v in keep.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
