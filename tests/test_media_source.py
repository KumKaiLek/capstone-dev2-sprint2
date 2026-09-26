"""Offline tests for fetching the stored video of a case. No COS, no IBM call, no key needed.
Run: python -m tests.test_media_source"""
import io
import os
import tempfile
from pathlib import Path
from src.config import ConfigError
from src.media_source import LocalMediaSource, CosMediaSource, default_media_source

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


CASE = "CASE-001"

# local source
tmp = Path(tempfile.mkdtemp())
folder = tmp / "cases" / CASE
folder.mkdir(parents=True)
(folder / "clip.mp4").write_bytes(b"video")
(folder / "case.json").write_text("{}")
(folder / "transcript.json").write_text("{}")
src = LocalMediaSource(tmp)
r = src.fetch(CASE, tmp / "work")
check("local source finds the video next to the case documents", r["status"] == "ok" and r["path"].endswith("cases/CASE-001/clip.mp4"))
check("no folder for the case gives MEDIA_NOT_FOUND", src.fetch("CASE-404", tmp / "work")["error"]["code"] == "MEDIA_NOT_FOUND")
(tmp / "cases" / "CASE-002").mkdir()
(tmp / "cases" / "CASE-002" / "case.json").write_text("{}")
check("case documents alone are not a video (MEDIA_NOT_FOUND)", src.fetch("CASE-002", tmp / "work")["error"]["code"] == "MEDIA_NOT_FOUND")
(tmp / "cases" / "CASE-003").mkdir()
(tmp / "cases" / "CASE-003" / "a.mp4").write_bytes(b"1")
(tmp / "cases" / "CASE-003" / "b.mov").write_bytes(b"2")
check("two videos for one case gives MEDIA_AMBIGUOUS", src.fetch("CASE-003", tmp / "work")["error"]["code"] == "MEDIA_AMBIGUOUS")
check("bad case id rejected", all(src.fetch(x, tmp)["error"]["code"] == "INVALID_CASE_ID" for x in [None, "", "../x", "CASE-1", "CASE-001/../.."]))


# COS source with a fake client
class FakeCos:
    def __init__(self, objects):
        self.objects, self.gets, self.fail_get = objects, [], False

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k, "Size": len(v) if isinstance(v, bytes) else v}
                             for k, v in self.objects.items() if k.startswith(Prefix)]}

    def get_object(self, Bucket, Key):
        self.gets.append(Key)
        if self.fail_get:
            raise RuntimeError("down")
        return {"Body": io.BytesIO(self.objects[Key])}


big = b"x" * (2 * 1024 * 1024 + 5)
fake = FakeCos({
    "cases/CASE-001/video.mp4": big,
    "cases/CASE-001/case.json": b"{}",
    "cases/CASE-001/sub/other.mp4": b"nested",
    "cases/CASE-0011/video.mp4": b"another case",
})
cos = CosMediaSource("test-bucket", fake)
work = tmp / "cos_work"
r = cos.fetch(CASE, work)
check("COS video is downloaded whole into the work folder",
      r["status"] == "ok" and Path(r["path"]).read_bytes() == big and Path(r["path"]).parent == work)
check("only that case's video is used (not nested files or a similar case id)", fake.gets == ["cases/CASE-001/video.mp4"])
check("COS case with no video gives MEDIA_NOT_FOUND", cos.fetch("CASE-404", work)["error"]["code"] == "MEDIA_NOT_FOUND")
check("COS bad case id rejected", cos.fetch("../x", work)["error"]["code"] == "INVALID_CASE_ID")

huge = FakeCos({"cases/CASE-001/video.mp4": 500 * 1024 * 1024})
r = CosMediaSource("b", huge).fetch(CASE, work)
check("video over the size limit gives MEDIA_TOO_LARGE without downloading", r["error"]["code"] == "MEDIA_TOO_LARGE" and huge.gets == [])
fake.gets.clear(); fake.fail_get = True
check("COS read problem gives MEDIA_READ_FAILED and does not raise", cos.fetch(CASE, work)["error"]["code"] == "MEDIA_READ_FAILED")

# source choice from the environment
keep = {k: os.environ.pop(k, None) for k in ("CASE_STORE", "CASE_STORE_DIR", "COS_API_KEY", "COS_INSTANCE_CRN", "COS_ENDPOINT", "COS_BUCKET")}
try:
    check("local source is the default", isinstance(default_media_source(), LocalMediaSource))
    os.environ["CASE_STORE"] = "cos"
    try:
        default_media_source(); ok = False
    except ConfigError as e:
        ok = "COS_API_KEY" in str(e)
    check("cos without its settings gives a config error", ok)
finally:
    for k, v in keep.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
