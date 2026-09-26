"""Offline tests for the case pipeline. No ffmpeg, no IBM call, no key needed.
Run: python -m tests.test_pipeline"""
import json
from src.pipeline import run_case, valid_case_id

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


CASE = "CASE-001"
SEGS = [
    {"startSec": 0.5, "endSec": 3.0, "text": "hello there", "confidence": 0.95},
    {"startSec": 5.0, "endSec": 7.5, "text": "I will hurt you", "confidence": 0.9},
]


def media_ok(has_audio=True):
    m = {"sourceType": "synthetic_video", "fileName": "clip.mp4", "durationSeconds": 8.0, "hasAudio": has_audio,
         "audioFile": "clip_audio.wav" if has_audio else None, "frameCount": 4, "frames": [],
         "sceneChanges": [4.0],
         "sceneSegments": [{"segmentId": 1, "startSec": 0.0, "endSec": 4.0, "label": "scene 1", "frameFiles": []},
                           {"segmentId": 2, "startSec": 4.0, "endSec": 8.0, "label": "scene 2", "frameFiles": []}]}
    return lambda path, work_dir=None: {"status": "ok", "media": m}


def media_fail(path, work_dir=None):
    return {"status": "error", "error": {"code": "MEDIA_UNREADABLE", "message": "corrupt"}}


def stt_ok(segments=SEGS):
    t = {"source": "clip_audio.wav", "model": "en-US_Multimedia", "text": " ".join(s["text"] for s in segments),
         "confidence": 0.92, "durationSeconds": 7.5, "segments": segments}
    return lambda path: {"status": "ok", "transcript": t}


def stt_fail(path):
    return {"status": "error", "error": {"code": "STT_SERVICE_ERROR", "message": "Speech to Text returned HTTP 500"}}


def ai(severity="high", categories=("violence",), flagged=(2,)):
    calls = []

    def fn(case_id, transcript, media_context, segments=None):
        calls.append({"caseId": case_id, "transcript": transcript, "segments": segments, "ctx": media_context})
        return {"status": "ok", "warnings": [], "result": {
            "caseId": case_id, "severity": severity, "summary": "A summary.", "categories": list(categories),
            "concerningSegments": list(flagged), "advisory": True, "requiresHumanReview": True, "model": "test-model"}}
    fn.calls = calls
    return fn


def ai_fail(case_id, transcript, media_context, segments=None):
    return {"status": "error", "error": {"code": "SERVICE_ERROR", "message": "watsonx.ai returned HTTP 500"}}


def run(media=None, stt=None, analyze_fn=None, case_id=CASE):
    return run_case(case_id, "clip.mp4", _media_fn=media or media_ok(), _stt_fn=stt or stt_ok(),
                    _analyze_fn=analyze_fn or ai())


# case id handling (the id ends up in file paths later)
check("valid case ids accepted", valid_case_id("CASE-001") and valid_case_id("CASE-0001"))
check("bad case ids rejected", not any(valid_case_id(x) for x in
                                       [None, "", "CASE-1", "case-001", "../CASE-001", "CASE-001/../x", "CASE-00a", 5]))
bad = run_case("../etc", "clip.mp4", _media_fn=media_ok(), _stt_fn=stt_ok(), _analyze_fn=ai())
check("run_case rejects a bad case id", bad["status"] == "error" and bad["error"]["code"] == "INVALID_CASE_ID")

# happy path
spy = ai()
out = run(analyze_fn=spy)
case, tr = out["case"], out["transcript"]
check("all three stages ok", out["status"] == "ok" and case["processingStatus"] == {
    "stt": "ok", "mediaAnalysis": "ok", "watsonx": "ok"})
check("case.json keeps Dev1's fields", all(k in case for k in ("caseId", "severity", "summary", "categories", "timestamps"))
      and case["caseId"] == CASE and case["severity"] == "high" and case["categories"] == ["violence"])
check("transcript.json keeps Dev1's fields", tr["transcript"] == "hello there I will hurt you"
      and tr["confidence"] == 0.92 and tr["caseId"] == CASE and tr["status"] == "ok" and tr["error"] is None)
check("transcript segments carried", tr["segments"] == SEGS)
check("watsonx got the case id and numbered segments", spy.calls[0]["caseId"] == CASE and spy.calls[0]["segments"] == SEGS)
check("incident timestamp is the measured STT time of the flagged segment", case["timestamps"] == [
    {"start": 5.0, "end": 7.5, "reason": "segment 2 flagged by watsonx.ai (violence)", "timestampStatus": "available"}])
check("advisory flags set by code", case["advisory"] is True and case["requiresHumanReview"] is True)
check("scene segments carry no severity and get transcript text by time",
      all("severity" not in s for s in case["sceneSegments"])
      and case["sceneSegments"][0]["transcriptText"] == "hello there"
      and case["sceneSegments"][1]["transcriptText"] == "I will hurt you")
check("output is JSON serialisable", bool(json.dumps(out)))

# timestamps: nothing invented
o = run(analyze_fn=ai(flagged=(7,)))
t = o["case"]["timestamps"][0]
check("segment that does not exist gives unavailable, not 0",
      t["start"] is None and t["end"] is None and t["timestampStatus"] == "unavailable" and "segment 7" in t["reason"])
o = run(analyze_fn=ai(flagged=(0,)))
check("segment number 0 is invalid (numbering starts at 1)", o["case"]["timestamps"][0]["timestampStatus"] == "unavailable")
untimed = [{"startSec": None, "endSec": None, "text": "no timing here", "confidence": None}, SEGS[1]]
o = run(stt=stt_ok(untimed), analyze_fn=ai(flagged=(1,)))
t = o["case"]["timestamps"][0]
check("STT segment without timing gives unavailable (and does not crash)",
      o["status"] == "ok" and t["start"] is None and t["timestampStatus"] == "unavailable")
o = run(analyze_fn=ai(flagged=(2, 2)))
check("duplicate segment numbers give one timestamp", len(o["case"]["timestamps"]) == 1)
o = run(analyze_fn=ai(severity="high", flagged=()))
check("high severity with no segment named is recorded as unavailable",
      len(o["case"]["timestamps"]) == 1 and o["case"]["timestamps"][0]["timestampStatus"] == "unavailable")
o = run(analyze_fn=ai(severity="low", categories=(), flagged=()))
check("low severity with nothing flagged has no timestamps", o["case"]["timestamps"] == [])

# failures are recorded, never crash
spy = ai()
o = run(stt=stt_fail, analyze_fn=spy)
check("STT failure recorded as a failure state", o["case"]["processingStatus"] == {
    "stt": "failed", "mediaAnalysis": "ok", "watsonx": "unavailable"} and o["status"] == "partial")
check("STT failure: error kept in transcript and case, watsonx not called",
      o["transcript"]["status"] == "failed" and o["transcript"]["error"]["code"] == "STT_SERVICE_ERROR"
      and o["transcript"]["transcript"] is None and o["case"]["errors"][0]["stage"] == "stt" and spy.calls == [])
check("STT failure: no severity or timestamps invented", o["case"]["severity"] is None and o["case"]["timestamps"] == [])

spy_stt_calls = []
o = run(media=media_fail, stt=lambda p: spy_stt_calls.append(p), analyze_fn=ai())
check("media failure: only mediaAnalysis marked failed, STT never called", o["status"] == "failed"
      and o["case"]["processingStatus"] == {"stt": "unavailable", "mediaAnalysis": "failed", "watsonx": "unavailable"}
      and spy_stt_calls == [] and o["case"]["media"] is None and o["case"]["sceneSegments"] == [])
check("media failure error recorded", o["case"]["errors"][0] == {"stage": "mediaAnalysis", "code": "MEDIA_UNREADABLE", "message": "corrupt"})

o = run(media=media_ok(has_audio=False))
check("video without audio: stt unavailable with a reason, no transcript",
      o["case"]["processingStatus"]["stt"] == "unavailable" and o["case"]["errors"][0]["code"] == "NO_AUDIO_TRACK"
      and o["transcript"]["transcript"] is None and o["case"]["processingStatus"]["watsonx"] == "unavailable")

o = run(analyze_fn=ai_fail)
check("watsonx failure recorded, transcript kept", o["status"] == "partial" and o["case"]["processingStatus"] == {
    "stt": "ok", "mediaAnalysis": "ok", "watsonx": "failed"} and o["transcript"]["transcript"] is not None
      and o["case"]["severity"] is None and o["case"]["timestamps"] == [] and o["case"]["errors"][0]["stage"] == "watsonx")

# stored video fetched through a source
class FakeSource:
    def __init__(self, result):
        self.result, self.calls = result, []

    def fetch(self, case_id, dest_dir):
        self.calls.append((case_id, dest_dir))
        return self.result


seen = []


def media_spy(path, work_dir=None):
    seen.append(path)
    return media_ok()(path, work_dir)


src = FakeSource({"status": "ok", "path": "cases/CASE-001/video.mp4"})
o = run_case(CASE, source=src, _media_fn=media_spy, _stt_fn=stt_ok(), _analyze_fn=ai())
check("stored video is fetched for the case and then analysed",
      o["status"] == "ok" and seen == ["cases/CASE-001/video.mp4"] and src.calls[0][0] == CASE)

src = FakeSource({"status": "error", "error": {"code": "MEDIA_NOT_FOUND", "message": "No video is stored for CASE-001"}})
stt_calls = []
o = run_case(CASE, source=src, _media_fn=lambda *a, **k: 1 / 0, _stt_fn=lambda p: stt_calls.append(p), _analyze_fn=ai())
check("missing stored video is recorded as a media failure and nothing else runs",
      o["status"] == "failed" and o["case"]["processingStatus"]["mediaAnalysis"] == "failed"
      and o["case"]["errors"][0] == {"stage": "mediaAnalysis", "code": "MEDIA_NOT_FOUND", "message": "No video is stored for CASE-001"}
      and stt_calls == [])

seen.clear()
src = FakeSource({"status": "ok", "path": "should/not/be/used.mp4"})
run_case(CASE, media_path="given.mp4", source=src, _media_fn=media_spy, _stt_fn=stt_ok(), _analyze_fn=ai())
check("a video path you give wins over the source", seen == ["given.mp4"] and src.calls == [])

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
