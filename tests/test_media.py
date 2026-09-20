"""Offline tests for the media adapter. No IBM call, no key needed.
Run: python -m tests.test_media"""
import shutil
import tempfile
from pathlib import Path
from src.media import analyse_media, build_segments, build_backend_payload

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


tmp = Path(tempfile.mkdtemp())

# input handling
check("missing input handled", analyse_media(None)["error"]["code"] == "MISSING_INPUT")
check("missing file handled", analyse_media(str(tmp / "nope.mp4"))["error"]["code"] == "FILE_NOT_FOUND")

txt = tmp / "notes.txt"; txt.write_text("hello")
check("wrong file type rejected", analyse_media(str(txt))["error"]["code"] == "INVALID_INPUT")

empty = tmp / "empty.mp4"; empty.write_bytes(b"")
check("empty file rejected", analyse_media(str(empty))["error"]["code"] == "INVALID_INPUT")

if shutil.which("ffprobe"):
    fake = tmp / "fake.mp4"; fake.write_text("this is not a video")
    check("corrupt video handled", analyse_media(str(fake))["error"]["code"] == "MEDIA_UNREADABLE")

# segments
segs = build_segments(8.0, [4.0], frames=[{"file": "f1.jpg", "timeSec": 0.0}, {"file": "f2.jpg", "timeSec": 4.0}])
check("scene change makes two segments", len(segs) == 2 and segs[0]["endSec"] == 4.0 and segs[1]["startSec"] == 4.0)
check("frames attached to segments", segs[0]["frameFiles"] == ["f1.jpg"] and segs[1]["frameFiles"] == ["f2.jpg"])
check("no scene change gives one full segment", len(build_segments(6.0, [])) == 1)
tseg = build_segments(8.0, [4.0], transcript_segments=[{"startSec": 0.5, "endSec": 3.0, "text": "hello"}])
check("transcript text attached by time", tseg[0]["transcriptText"] == "hello" and tseg[1]["transcriptText"] == "")

# payload states
ok_media = {"status": "ok", "media": {"sourceType": "synthetic_video", "fileName": "a.mp4", "durationSeconds": 8.0,
            "hasAudio": True, "frameCount": 4, "sceneChanges": [4.0], "incidentSegments": segs}}
good = {"status": "ok", "result": {"caseId": "C1", "severity": "low", "summary": "x", "categories": [],
        "advisory": True, "requiresHumanReview": True, "model": "m"}}
p = build_backend_payload("C1", ok_media, good)
check("payload built with analysis", p["analysisStatus"] == "ok" and p["analysis"]["severity"] == "low" and len(p["incidentSegments"]) == 2)
p = build_backend_payload("C1", ok_media, None)
check("missing analysis result handled", p["analysisStatus"] == "missing" and p["errors"][0]["code"] == "ANALYSIS_MISSING")
p = build_backend_payload("C1", ok_media, {"status": "error", "error": {"code": "AUTH_OR_PROJECT_ACCESS", "message": "403"}})
check("failed analysis state handled", p["analysisStatus"] == "failed" and p["errors"][0]["code"] == "AUTH_OR_PROJECT_ACCESS")
p = build_backend_payload("C1", {"status": "error", "error": {"code": "MEDIA_UNREADABLE", "message": "bad"}}, good)
check("failed media result handled", p["media"] is None and p["errors"][0]["stage"] == "media" and p["analysisStatus"] == "ok")
check("advisory flags always true", p["advisory"] is True and p["requiresHumanReview"] is True)

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
