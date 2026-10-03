"""Case pipeline. Reads Dev1's case.json, gets the media it references, runs Speech to Text
and watsonx.ai, and writes transcript.json and analysis.json next to it. case.json is never written.

  audio  -> straight to Speech to Text
  video  -> media analysis (ffmpeg) extracts the audio and finds scene cuts, then Speech to Text

A failure in one stage is recorded in processingStatus and errors and the other stages still run when they can.
The result is partial, never a crash. Incident timestamps are never invented: watsonx.ai refers to numbered
Speech to Text segments and the code looks up the measured start and end of that segment. A segment number that
does not exist, or a segment with no timing, gives start/end = null and timestampStatus "unavailable".

Media reference (D2, Sprint 2 Week 3 stabilisation): case.json is checked in this order,
  1. mediaObjectKey, Dev1's current field, shaped "cases/<caseId>/<originalname>"
  2. fileName, a plain name alongside mediaObjectKey
  3. mediaObject, the older shape this pipeline used before (kept for backward compatibility)
A mediaObjectKey that names a different case folder is refused, never silently used.
"""
import re
from pathlib import Path

from .analysis import analyze
from .media import (ALLOWED_EXT as VIDEO_EXT, MediaError, analyse_media, build_segments, check_tools,
                    extract_audio, media_context_for_ai, validate_input)
from .stt import ALLOWED_TYPES as STT_TYPES, transcribe
from .store import valid_case_id

AUDIO_EXT = set(STT_TYPES)
# The exact shape of mediaObject, the older field, is not confirmed. A plain string or an object is accepted.
MEDIA_NAME_KEYS = ("key", "objectKey", "fileName", "filename", "name", "path", "file")
MEDIA_TYPE_KEYS = ("contentType", "mimeType", "mediaType", "type")
KEY_PREFIX_PATTERN = re.compile(r"^cases/([^/]+)/")


def read_media_object(obj):
    """(file name, content type) from the older mediaObject field, or (None, None) if nothing is usable."""
    content_type = None
    if isinstance(obj, dict):
        ref = next((obj[k] for k in MEDIA_NAME_KEYS if isinstance(obj.get(k), str) and obj[k].strip()), None)
        content_type = next((obj[k] for k in MEDIA_TYPE_KEYS if isinstance(obj.get(k), str)), None)
    else:
        ref = obj if isinstance(obj, str) and obj.strip() else None
    if ref is None:
        return None, None
    return ref.strip().replace("\\", "/").split("/")[-1], content_type


def _type_hint(meta):
    """contentType first (Dev1's coarse "video"/"audio"), then mediaMimeType (a full mime type)."""
    for key in ("contentType", "mediaMimeType"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_media_reference(meta, case_id):
    """(file name, content type, error) from case.json, checked in the order in the module docstring.
    error is only set when mediaObjectKey names a different case; any other unusable field is just
    skipped in favour of the next one, not treated as an error."""
    key = meta.get("mediaObjectKey")
    if isinstance(key, str) and key.strip():
        key = key.strip().replace("\\", "/")
        match = KEY_PREFIX_PATTERN.match(key)
        if match:
            if match.group(1) != case_id:
                return None, None, {"code": "MEDIA_KEY_WRONG_CASE",
                                    "message": f"mediaObjectKey points at {match.group(1)!r}, not {case_id}"}
            rest = key[match.end():].split("/")[-1].strip()
        else:
            rest = key.split("/")[-1].strip()
        if rest:
            return rest, _type_hint(meta), None

    name = meta.get("fileName")
    if isinstance(name, str) and name.strip():
        return name.strip().split("/")[-1], _type_hint(meta), None

    legacy_name, legacy_type = read_media_object(meta.get("mediaObject"))
    if legacy_name:
        return legacy_name, legacy_type or _type_hint(meta), None

    return None, None, None


def media_kind(filename, content_type=None):
    """"audio", "video" or None when the type cannot be worked out. A coarse content_type of
    "audio" or "video" (Dev1's contentType field) is trusted directly. Otherwise a full mime type
    ("video/mp4") is used if it matches the extension, then the extension alone. .webm with no
    audio/video hint counts as video."""
    ct = (content_type or "").lower().strip()
    if ct in ("audio", "video"):
        return ct
    ext = Path(filename).suffix.lower()
    if ct.startswith("audio/") and ext in AUDIO_EXT:
        return "audio"
    if ct.startswith("video/") and ext in VIDEO_EXT:
        return "video"
    if ext == ".webm":
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    return None


def _unavailable(reason):
    return {"start": None, "end": None, "reason": reason, "timestampStatus": "unavailable"}


def build_timestamps(analysis, segments):
    """Incident timestamps from the Speech to Text segments that watsonx.ai pointed at (1 based numbers)."""
    cats = ", ".join(analysis["categories"])
    out = []
    for n in sorted(set(analysis.get("concerningSegments", []))):
        if not 1 <= n <= len(segments):
            out.append(_unavailable(f"watsonx.ai referred to segment {n}, which is not in the transcript"))
            continue
        seg = segments[n - 1]
        if seg.get("startSec") is None or seg.get("endSec") is None:
            out.append(_unavailable(f"segment {n} was flagged but Speech to Text gave no timing for it"))
            continue
        reason = f"segment {n} flagged by watsonx.ai" + (f" ({cats})" if cats else "")
        out.append({"start": seg["startSec"], "end": seg["endSec"], "reason": reason, "timestampStatus": "available"})
    if not out and analysis["severity"] != "low":
        out.append(_unavailable(
            f"watsonx.ai rated {analysis['severity']} severity but did not point to a specific transcript segment"))
    return out


def build_transcript_doc(case_id, stt_status, transcript, error):
    t = transcript or {}
    return {
        "caseId": case_id,
        "transcript": t.get("text"),
        "confidence": t.get("confidence"),
        "status": stt_status,
        "error": error,
        "segments": [{"startSec": s["startSec"], "endSec": s["endSec"], "text": s["text"],
                      "confidence": s["confidence"], "timestampStatus": s.get("timestampStatus"),
                      "timestampReason": s.get("timestampReason")} for s in t.get("segments", [])],
        "source": t.get("source"),
        "model": t.get("model"),
        "durationSeconds": t.get("durationSeconds"),
    }


def build_analysis_doc(case_id, status, analysis, timestamps, media, media_type, media_file, errors, warnings):
    a = analysis or {}
    return {
        "caseId": case_id,
        "severity": a.get("severity"),
        "summary": a.get("summary"),
        "categories": a.get("categories", []),
        "evidenceSegments": a.get("evidenceSegments", {}),
        "timestamps": timestamps,
        "processingStatus": status,
        "advisory": True,
        "requiresHumanReview": True,
        "model": a.get("model"),
        "mediaType": media_type,
        "mediaFile": media_file,
        "media": None if media is None else {k: media[k] for k in (
            "fileName", "durationSeconds", "hasAudio", "frameCount", "sceneChanges")},
        "sceneSegments": [] if media is None else media["sceneSegments"],
        "errors": errors,
        "warnings": warnings,
    }


def _extract_audio(media_path, out_dir):
    """Audio from a video whose full media analysis failed, or None."""
    try:
        check_tools()
        p = validate_input(media_path)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        return extract_audio(p, out_dir)
    except MediaError:
        return None


def run_case(case_id, store, work_dir="outputs/media", _media_fn=None, _stt_fn=None, _analyze_fn=None,
             _extract_audio_fn=None):
    """Never raises. Returns {"status": "error", "error": {...}} when the case cannot be run at all
    (bad caseId, no case.json, caseId mismatch). Otherwise returns
    {"status": "ok" | "partial" | "failed", "caseId", "mediaType", "transcript": {...}, "analysis": {...}, "saved": {...}}
    and has written transcript.json and analysis.json. The _fn arguments let the tests run without ffmpeg or IBM."""
    if not valid_case_id(case_id):
        return {"status": "error", "error": {"code": "INVALID_CASE_ID", "message": "caseId must look like CASE-001 or CASE-<uuid>, letters, digits and hyphens only"}}
    media_fn = _media_fn or analyse_media
    stt_fn = _stt_fn or transcribe
    analyze_fn = _analyze_fn or analyze
    extract_fn = _extract_audio_fn or _extract_audio

    loaded = store.load(case_id, "case.json")
    if loaded["status"] != "ok":
        err = loaded["error"]
        if err["code"] == "FILE_NOT_FOUND":
            err = {"code": "CASE_NOT_FOUND", "message": f"There is no case.json for {case_id}"}
        return {"status": "error", "error": err}
    meta = loaded["data"]
    if not isinstance(meta, dict) or not isinstance(meta.get("caseId"), str):
        return {"status": "error", "error": {"code": "CASE_DATA_INVALID", "message": "case.json has no caseId"}}
    if meta["caseId"] != case_id:
        return {"status": "error", "error": {
            "code": "CASE_ID_MISMATCH",
            "message": f"case.json says {meta['caseId']} but the case folder is {case_id}, nothing was written"}}

    status = {"stt": "unavailable", "mediaAnalysis": "unavailable", "watsonx": "unavailable"}
    errors, warnings = [], []
    media = transcript = analysis = audio_path = stt_error = None
    case_dir = str(Path(work_dir) / case_id)

    def fail(stage, code, message):
        status[stage] = "failed"
        errors.append({"stage": stage, "code": code, "message": message})
        return {"code": code, "message": message}

    media_file, content_type, media_error = resolve_media_reference(meta, case_id)
    kind = media_kind(media_file, content_type) if media_file else None
    if media_error is not None:
        fail("mediaAnalysis", media_error["code"], media_error["message"])
    elif media_file is None:
        fail("mediaAnalysis", "MEDIA_REFERENCE_MISSING",
             "case.json has no usable mediaObjectKey, fileName or mediaObject")
    elif kind is None:
        ext = Path(media_file).suffix.lower() or "(none)"
        fail("mediaAnalysis", "INVALID_MEDIA_TYPE",
             f"Unsupported media type {ext}; audio {sorted(AUDIO_EXT)} or video {sorted(VIDEO_EXT)} is expected")
    elif not store.exists(case_id, media_file):
        fail("mediaAnalysis", "MEDIA_NOT_FOUND", f"The media file {media_file} is not in the case folder")
    else:
        media_path = store.path(case_id, media_file)
        if kind == "audio":
            audio_path = media_path
            warnings.append("audio_only_no_media_analysis")
        else:
            media_result = media_fn(media_path, work_dir=case_dir)
            if media_result.get("status") == "ok":
                status["mediaAnalysis"] = "ok"
                media = media_result["media"]
                if media["hasAudio"]:
                    audio_path = media["audioFile"]
                else:
                    stt_error = {"code": "NO_AUDIO_TRACK", "message": "The video has no audio track, so there is nothing to transcribe"}
                    errors.append({"stage": "stt", **stt_error})
            else:
                err = media_result.get("error") or {}
                fail("mediaAnalysis", err.get("code", "UNKNOWN"), err.get("message", ""))
                audio_path = extract_fn(media_path, case_dir)
                if audio_path:
                    warnings.append("audio_recovered_after_media_analysis_failed")

    if audio_path:
        stt_result = stt_fn(audio_path)
        if stt_result.get("status") == "ok":
            status["stt"] = "ok"
            transcript = stt_result["transcript"]
            if media is not None:
                media["sceneSegments"] = build_segments(
                    media["durationSeconds"], media["sceneChanges"], media["frames"], transcript["segments"])
        else:
            err = stt_result.get("error") or {}
            stt_error = fail("stt", err.get("code", "UNKNOWN"), err.get("message", ""))

    timestamps = []
    if transcript is not None:
        context = media_context_for_ai(media) if media is not None else {
            "sourceType": kind or "unknown", "durationSeconds": transcript.get("durationSeconds")}
        result = analyze_fn(case_id, transcript["text"], context, segments=transcript["segments"])
        if result.get("status") == "ok":
            status["watsonx"] = "ok"
            analysis = result["result"]
            warnings += list(result.get("warnings", []))
            timestamps = build_timestamps(analysis, transcript["segments"])
        else:
            err = result.get("error") or {}
            fail("watsonx", err.get("code", "UNKNOWN"), err.get("message", ""))

    stages = [status["stt"], status["watsonx"]]
    if not (kind == "audio" and status["mediaAnalysis"] == "unavailable"):
        stages.append(status["mediaAnalysis"])
    overall = "ok" if all(s == "ok" for s in stages) else ("failed" if not any(s == "ok" for s in stages) else "partial")

    transcript_doc = build_transcript_doc(case_id, status["stt"], transcript, stt_error)
    analysis_doc = build_analysis_doc(case_id, status, analysis, timestamps, media, kind, media_file, errors, warnings)
    saved = {"transcript": store.save(case_id, "transcript.json", transcript_doc),
             "analysis": store.save(case_id, "analysis.json", analysis_doc)}
    if overall == "ok" and any(s["status"] != "ok" for s in saved.values()):
        overall = "partial"
    return {"status": overall, "caseId": case_id, "mediaType": kind,
            "transcript": transcript_doc, "analysis": analysis_doc, "saved": saved}
