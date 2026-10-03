"""Simulated services and scenarios, shared by tests/test_pipeline.py and seed_synthetic_case.py.
Speech to Text and watsonx.ai run through the real modules with a fake network layer, so parsing,
validation and error handling are the real code. No IBM call and no key needed."""
import json
from functools import partial
from pathlib import Path

from src.analysis import analyze
from src.media import build_segments
from src.pipeline import run_case
from src.store import LocalCaseStore
from src.stt import transcribe

STT_SETTINGS = {"api_key": "simulated-key", "url": "https://stt.example.test/instances/simulated",
                "model": "en-US_Multimedia"}
SEGMENTS = [
    ("this is a synthetic test recording", 0.02, 1.9),
    ("synthetic test script you are worthless and everyone hates you i know where you live and i will make you regret it", 3.64, 9.7),
]
GENERATED = ("transcript.json", "analysis.json")


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def watson_body(timestamps=True):
    results = []
    for text, start, end in SEGMENTS:
        alt = {"transcript": text + " ", "confidence": 0.93}
        if timestamps:
            words = text.split()
            alt["timestamps"] = [[words[0], start, start + 0.4], [words[-1], end - 0.4, end]]
        results.append({"final": True, "alternatives": [alt]})
    return {"result_index": 0, "results": results}


def stt_service(kind):
    def post(*args, **kwargs):
        if kind == "server_error":
            return Resp(500, {})
        return Resp(200, watson_body(timestamps=(kind != "no_timestamps")))
    return partial(transcribe, _settings=STT_SETTINGS, _post_fn=post)


def chat_service(kind):
    flagged = {"concerning": [2], "invalid_index": [9], "no_timestamps": [1]}

    def chat(messages):
        case_id = messages[1]["content"].split("\n")[0].split(": ", 1)[1]
        if kind == "malformed":
            return "I think this content is fine."
        # evidenceSegments points at the same numbers as concerningSegments (D4), so a scenario that
        # deliberately flags an index outside the transcript (invalid_index) also drops its categories,
        # the way a model that hallucinates a segment number would hallucinate the same one as evidence.
        return json.dumps({"caseId": case_id, "severity": "high", "summary": "A neutral summary of the recording.",
                           "categories": ["harassment", "violence"], "concerningSegments": flagged[kind],
                           "evidenceSegments": {"harassment": flagged[kind], "violence": flagged[kind]}})
    return partial(analyze, _chat_fn=chat)


def media_service(has_audio=True):
    def fn(path, work_dir=None):
        out = Path(work_dir)
        out.mkdir(parents=True, exist_ok=True)
        audio = out / "video_audio.wav"
        audio.write_bytes(b"RIFF....WAVEfmt ")
        return {"status": "ok", "media": {
            "sourceType": "synthetic_video", "fileName": Path(path).name, "durationSeconds": 10.0,
            "hasAudio": has_audio, "audioFile": str(audio) if has_audio else None, "frameCount": 5, "frames": [],
            "sceneChanges": [5.0], "sceneSegments": build_segments(10.0, [5.0], [], None)}}
    return fn


def media_failure(path, work_dir=None):
    return {"status": "error", "error": {"code": "MEDIA_UNREADABLE", "message": "ffprobe could not read the file"}}


def extract_service(path, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    audio = out / "recovered_audio.wav"
    audio.write_bytes(b"RIFF....WAVEfmt ")
    return str(audio)


def dev1_case_json(case_id, filename=None, content_type=None, media_mime_type=None, media_object_key=None,
                   case_id_inside=None, legacy=False, legacy_media_object=None):
    """A stand in for Dev1's case.json. D5, Sprint 2 Week 3 stabilisation: this now matches the shape
    his backend actually sends: {caseId, fileName, contentType: "video"|"audio", mediaMimeType,
    mediaObjectKey: "cases/<caseId>/<originalname>", submittedBy, submittedAt, status, severity,
    isTestCase, exposureMinutes}. legacy=True builds the older shape this pipeline used before that
    was confirmed, kept for the one backward-compatibility scenario."""
    if legacy:
        doc = {"caseId": case_id_inside or case_id, "title": "Synthetic test case", "status": "submitted",
               "severity": None, "summary": None, "categories": [], "timestamps": [], "synthetic": True}
        if legacy_media_object is not None:
            doc["mediaObject"] = legacy_media_object
        return doc
    doc = {
        "caseId": case_id_inside or case_id,
        "submittedBy": "synthetic-seed",
        "submittedAt": "2026-10-03T00:00:00Z",
        "status": "Queued",
        "severity": None,
        "isTestCase": True,
        "exposureMinutes": 0,
        "synthetic": True,
    }
    if filename is not None:
        doc["fileName"] = filename
        doc["mediaObjectKey"] = media_object_key if media_object_key is not None else f"cases/{case_id}/{filename}"
    if content_type is not None:
        doc["contentType"] = content_type
    if media_mime_type is not None:
        doc["mediaMimeType"] = media_mime_type
    return doc


# name -> what the case folder holds and which services answer
SCENARIOS = {
    "happy_path": dict(case_id="CASE-001", description="Video case, every stage works",
                       filename="video.mp4", content_type="video", media_mime_type="video/mp4",
                       files=["video.mp4"], stt="ok", chat="concerning"),
    "missing_media": dict(case_id="CASE-002", description="case.json names a video that is not in the folder",
                          filename="video.mp4", content_type="video", media_mime_type="video/mp4",
                          files=[], stt="ok", chat="concerning"),
    "invalid_media_type": dict(case_id="CASE-003", description="The case file is a type Speech to Text and media analysis cannot use",
                               filename="notes.txt", media_mime_type="text/plain",
                               files=["notes.txt"], stt="ok", chat="concerning"),
    "stt_server_error": dict(case_id="CASE-004", description="Speech to Text answers HTTP 500",
                             filename="video.mp4", content_type="video", media_mime_type="video/mp4",
                             files=["video.mp4"], stt="server_error", chat="concerning"),
    "malformed_watsonx_output": dict(case_id="CASE-005", description="watsonx.ai answers with prose instead of JSON",
                                     filename="video.mp4", content_type="video", media_mime_type="video/mp4",
                                     files=["video.mp4"], stt="ok", chat="malformed"),
    "no_timestamps": dict(case_id="CASE-006", description="Speech to Text gives no timing for its segments",
                          filename="video.mp4", content_type="video", media_mime_type="video/mp4",
                          files=["video.mp4"], stt="no_timestamps", chat="no_timestamps"),
    "invalid_segment_index": dict(case_id="CASE-007", description="watsonx.ai names a segment that does not exist",
                                  filename="video.mp4", content_type="video", media_mime_type="video/mp4",
                                  files=["video.mp4"], stt="ok", chat="invalid_index"),
    "case_id_mismatch": dict(case_id="CASE-008", description="case.json says CASE-999 but the folder is CASE-008",
                             filename="video.mp4", content_type="video", media_mime_type="video/mp4",
                             files=["video.mp4"], stt="ok", chat="concerning", case_id_inside="CASE-999"),
    "audio_only": dict(case_id="CASE-009", description="The case media is audio, so it goes straight to Speech to Text",
                       filename="speech.wav", content_type="audio", media_mime_type="audio/wav",
                       files=["speech.wav"], stt="ok", chat="concerning"),
    "media_analysis_failed_audio_recovered": dict(
        case_id="CASE-010", description="Video analysis fails but the audio can still be extracted, so the rest runs",
        filename="video.mp4", content_type="video", media_mime_type="video/mp4",
        files=["video.mp4"], stt="ok", chat="concerning", media_fails=True),
    "no_media_reference": dict(case_id="CASE-011", description="case.json has no fileName, mediaObjectKey or mediaObject",
                               files=[], stt="ok", chat="concerning"),
    "media_key_wrong_case": dict(
        case_id="CASE-012", description="mediaObjectKey points at a different case folder, D2 must refuse it, never use it",
        filename="video.mp4", content_type="video", media_mime_type="video/mp4",
        media_object_key="cases/CASE-999/video.mp4", files=["video.mp4"], stt="ok", chat="concerning"),
    "filename_with_spaces": dict(
        case_id="CASE-013", description="A file name with spaces and punctuation resolves and loads correctly (D3)",
        filename="My Clip (Final v2).mp4", content_type="video", media_mime_type="video/mp4",
        files=["My Clip (Final v2).mp4"], stt="ok", chat="concerning"),
    "legacy_media_object": dict(
        case_id="CASE-014", description="The older mediaObject field still works, kept for backward compatibility (D5)",
        legacy=True, legacy_media_object={"key": "cases/CASE-014/video.mp4", "contentType": "video/mp4"},
        files=["video.mp4"], stt="ok", chat="concerning"),
    "uuid_case_id": dict(
        case_id="CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab",
        description="A Dev1 style CASE-<uuid> id works end to end, not just CASE-001 style (D1)",
        filename="video.mp4", content_type="video", media_mime_type="video/mp4",
        files=["video.mp4"], stt="ok", chat="concerning"),
}


def run_scenario(name, base_dir, work_dir, clip=None, real_media=False, live=False):
    """Builds the case folder for a scenario under base_dir/cases, runs the pipeline and returns everything.
    clip is a real video to copy in. real_media uses ffmpeg. live uses the real IBM services (happy_path only)."""
    s = SCENARIOS[name]
    folder = Path(base_dir) / "cases" / s["case_id"]
    existing = folder / "case.json"
    if existing.is_file():
        try:
            synthetic = json.loads(existing.read_text()).get("synthetic") is True
        except ValueError:
            synthetic = False
        if not synthetic:
            raise RuntimeError(f"{existing} is not a synthetic case, not touching it")
    folder.mkdir(parents=True, exist_ok=True)
    for generated in GENERATED:
        (folder / generated).unlink(missing_ok=True)
    case_doc = dev1_case_json(
        s["case_id"], filename=s.get("filename"), content_type=s.get("content_type"),
        media_mime_type=s.get("media_mime_type"), media_object_key=s.get("media_object_key"),
        case_id_inside=s.get("case_id_inside"), legacy=s.get("legacy", False),
        legacy_media_object=s.get("legacy_media_object"))
    existing.write_text(json.dumps(case_doc, indent=2))
    for fname in s["files"]:
        if clip is not None and fname.endswith(".mp4") and name == "happy_path":
            (folder / fname).write_bytes(Path(clip).read_bytes())
        else:
            (folder / fname).write_bytes(b"simulated file")

    use_live = live and name == "happy_path"
    real = real_media and name == "happy_path" and clip is not None
    media_fn = None if real else (media_failure if s.get("media_fails") else media_service())
    result = run_case(
        s["case_id"], LocalCaseStore(base_dir), work_dir=str(work_dir),
        _media_fn=media_fn,
        _stt_fn=None if use_live else stt_service(s["stt"]),
        _analyze_fn=None if use_live else chat_service(s["chat"]),
        _extract_audio_fn=extract_service)
    files = {n: json.loads((folder / n).read_text()) for n in ("case.json",) + GENERATED if (folder / n).is_file()}
    return {"scenario": name, "description": s["description"], "caseId": s["case_id"],
            "services": {"mediaAnalysis": "ffmpeg" if real else "simulated",
                         "speechToText": "IBM live" if use_live else "simulated",
                         "watsonx": "IBM live" if use_live else "simulated"},
            "resultStatus": result["status"], "error": result.get("error"), "saved": result.get("saved"),
            "files": files, "original_case_json": case_doc}
