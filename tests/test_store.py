"""Offline tests for the case store. No COS, no IBM call, no key needed.
Run: python -m tests.test_store"""
import json
import os
import tempfile
from pathlib import Path
from src.config import ConfigError
from src.store import CaseStore, LocalBackend, CosBackend, default_store

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


CASE = "CASE-001"
TRANSCRIPT = {"caseId": CASE, "transcript": "hello", "confidence": 0.9, "status": "ok", "error": None,
              "segments": [{"startSec": 0.5, "endSec": 2.0, "text": "hello", "confidence": 0.9}]}
CASE_DOC = {"caseId": CASE, "severity": "low", "summary": "A summary.", "categories": [],
            "timestamps": [{"start": None, "end": None, "reason": "none", "timestampStatus": "unavailable"}],
            "processingStatus": {"stt": "ok", "mediaAnalysis": "ok", "watsonx": "ok"}}


def new_store():
    tmp = Path(tempfile.mkdtemp())
    return tmp, CaseStore(LocalBackend(tmp))


# local backend
tmp, store = new_store()
saved = store.save(CASE, TRANSCRIPT, CASE_DOC)
check("save works and reports the COS style keys", saved["status"] == "ok" and saved["keys"] == [
    "cases/CASE-001/transcript.json", "cases/CASE-001/case.json"])
check("files are written in the cases/<caseId>/ layout",
      (tmp / "cases/CASE-001/case.json").is_file() and (tmp / "cases/CASE-001/transcript.json").is_file())
loaded = store.load(CASE)
check("load returns exactly what was saved", loaded["status"] == "ok" and loaded["case"] == CASE_DOC
      and loaded["transcript"] == TRANSCRIPT)
check("no temp files are left behind", not list((tmp / "cases").rglob("*.tmp")))
CASE_DOC2 = {**CASE_DOC, "severity": "high"}
store.save(CASE, TRANSCRIPT, CASE_DOC2)
check("saving again replaces the stored case", store.load(CASE)["case"]["severity"] == "high")

# case id handling
for bad in [None, "", "CASE-1", "../CASE-001", "CASE-001/../../x", "case-001"]:
    r1, r2 = store.save(bad, TRANSCRIPT, CASE_DOC), store.load(bad)
    if not (r1["error"]["code"] == "INVALID_CASE_ID" and r2["error"]["code"] == "INVALID_CASE_ID"):
        check(f"bad case id rejected {bad!r}", False)
        break
else:
    check("bad case ids rejected by save and load", True)
check("a bad case id wrote nothing outside the cases folder", sorted(p.name for p in tmp.iterdir()) == ["cases"])
r = store.save("CASE-002", TRANSCRIPT, CASE_DOC)
check("document caseId must match the caseId given", r["error"]["code"] == "INVALID_DOCUMENT" and not (tmp / "cases/CASE-002").exists())
check("non object document rejected", store.save(CASE, "text", CASE_DOC)["error"]["code"] == "INVALID_DOCUMENT")
r = store.save("CASE-003", {"caseId": "CASE-003", "x": {1, 2}}, {"caseId": "CASE-003"})
check("document that is not JSON is rejected before anything is written",
      r["error"]["code"] == "INVALID_DOCUMENT" and not (tmp / "cases/CASE-003").exists())

# load problems
check("missing case gives CASE_NOT_FOUND", store.load("CASE-404")["error"]["code"] == "CASE_NOT_FOUND")
(tmp / "cases/CASE-005").mkdir()
(tmp / "cases/CASE-005/case.json").write_text("{not json")
check("corrupt case.json gives CASE_DATA_INVALID", store.load("CASE-005")["error"]["code"] == "CASE_DATA_INVALID")
(tmp / "cases/CASE-006").mkdir()
(tmp / "cases/CASE-006/case.json").write_text(json.dumps({"caseId": "CASE-999"}))
check("case.json for a different case is rejected", store.load("CASE-006")["error"]["code"] == "CASE_DATA_INVALID")
(tmp / "cases/CASE-007").mkdir()
(tmp / "cases/CASE-007/case.json").write_text(json.dumps({"caseId": "CASE-007", "severity": "low"}))
r = store.load("CASE-007")
check("transcript.json is optional when loading", r["status"] == "ok" and r["transcript"] is None and r["case"]["severity"] == "low")
blocker = tmp / "blocker"; blocker.write_text("a file, not a folder")
r = CaseStore(LocalBackend(blocker)).save(CASE, TRANSCRIPT, CASE_DOC)
check("write problem gives STORE_WRITE_FAILED and does not raise", r["error"]["code"] == "STORE_WRITE_FAILED")


# COS backend with a fake client
class ClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeCos:
    def __init__(self):
        self.objects, self.fail_put, self.get_error = {}, False, None

    def put_object(self, Bucket, Key, Body, ContentType):
        if self.fail_put:
            raise RuntimeError("down")
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if self.get_error:
            raise ClientError(self.get_error)
        if (Bucket, Key) not in self.objects:
            raise ClientError("NoSuchKey")

        class Body:
            def read(_):
                return self.objects[(Bucket, Key)]
        return {"Body": Body()}


fake = FakeCos()
cos = CaseStore(CosBackend("test-bucket", fake))
check("COS save writes both keys to the bucket", cos.save(CASE, TRANSCRIPT, CASE_DOC)["status"] == "ok" and
      set(fake.objects) == {("test-bucket", "cases/CASE-001/transcript.json"), ("test-bucket", "cases/CASE-001/case.json")})
check("COS load returns what was saved", cos.load(CASE)["case"] == CASE_DOC)
check("COS missing key gives CASE_NOT_FOUND", cos.load("CASE-404")["error"]["code"] == "CASE_NOT_FOUND")
fake.get_error = "AccessDenied"
check("COS read error gives STORE_READ_FAILED", cos.load(CASE)["error"]["code"] == "STORE_READ_FAILED")
fake.fail_put = True
check("COS write error gives STORE_WRITE_FAILED", cos.save("CASE-009", {"caseId": "CASE-009"}, {"caseId": "CASE-009"})["error"]["code"] == "STORE_WRITE_FAILED")

# backend choice from the environment
keep = {k: os.environ.pop(k, None) for k in ("CASE_STORE", "CASE_STORE_DIR", "COS_API_KEY", "COS_INSTANCE_CRN", "COS_ENDPOINT", "COS_BUCKET")}
try:
    check("local backend is the default", isinstance(default_store().backend, LocalBackend))
    os.environ["CASE_STORE"] = "cos"
    try:
        default_store(); ok = False
    except ConfigError as e:
        ok = "COS_API_KEY" in str(e)
    check("cos without its settings gives a config error", ok)
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
