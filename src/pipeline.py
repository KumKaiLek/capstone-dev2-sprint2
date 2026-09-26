"""Case pipeline: stored video -> media analysis -> Speech to Text -> watsonx.ai.

Produces the two documents Dev1's COS layout uses (transcript.json and case.json). Dev1's
fields are kept as they are and only new fields are added. Saving them is done by the
CaseStore, not here.

Incident timestamps are never invented: watsonx.ai refers to numbered STT segments and the
code looks up the measured start/end of that segment. A missing, invalid or untimed segment
gives start/end = null and timestampStatus "unavailable" with a reason.
"""
import re
from pathlib import Path

from .media import analyse_media, build_segments, media_context_for_ai
from .stt import transcribe
from .analysis import analyze

CASE_ID_PATTERN = re.compile(r"^CASE-[0-9]{3,}$")


def valid_case_id(case_id):
    return isinstance(case_id, str) and bool(CASE_ID_PATTERN.match(case_id))


def _stage_error(stage, err):
    err = err or {}
    return {"stage": stage, "code": err.get("code", "UNKNOWN"), "message": err.get("message", "")}


def _unavailable(reason):
    return {"start": None, "end": None, "reason": reason, "timestampStatus": "unavailable"}


def build_timestamps(analysis, segments):
    """Incident timestamps from the STT segments that watsonx.ai pointed at."""
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
        out.append({"start": seg["startSec"], "end": seg["endSec"], "reason": reason,
                    "timestampStatus": "available"})
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
                      "confidence": s["confidence"]} for s in t.get("segments", [])],
        "source": t.get("source"),
        "model": t.get("model"),
        "durationSeconds": t.get("durationSeconds"),
    }


def build_case_doc(case_id, status, analysis, timestamps, media, errors, warnings):
    a = analysis or {}
    return {
        "caseId": case_id,
        "severity": a.get("severity"),
        "summary": a.get("summary"),
        "categories": a.get("categories", []),
        "timestamps": timestamps,
        "processingStatus": status,
        "advisory": True,
        "requiresHumanReview": True,
        "model": a.get("model"),
        "media": None if media is None else {k: media[k] for k in (
            "fileName", "durationSeconds", "hasAudio", "frameCount", "sceneChanges")},
        "sceneSegments": [] if media is None else media["sceneSegments"],
        "errors": errors,
        "warnings": warnings,
    }


def run_case(case_id, media_path, work_dir="outputs/media", _media_fn=None, _stt_fn=None, _analyze_fn=None):
    """Never raises. Returns {"status": "error", ...} for a bad caseId, otherwise
    {"status": "ok" | "partial" | "failed", "caseId", "transcript": {...}, "case": {...}}.
    The _fn arguments let the tests run without ffmpeg or IBM."""
    if not valid_case_id(case_id):
        return {"status": "error", "error": {"code": "INVALID_CASE_ID",
                                             "message": "caseId must look like CASE-001"}}
    media_fn = _media_fn or analyse_media
    stt_fn = _stt_fn or transcribe
    analyze_fn = _analyze_fn or analyze

    status = {"stt": "unavailable", "mediaAnalysis": "unavailable", "watsonx": "unavailable"}
    errors, warnings = [], []
    media = transcript = analysis = None
    stt_error = None

    media_result = media_fn(media_path, work_dir=str(Path(work_dir) / case_id))
    if media_result.get("status") == "ok":
        status["mediaAnalysis"] = "ok"
        media = media_result["media"]
    else:
        status["mediaAnalysis"] = "failed"
        errors.append(_stage_error("mediaAnalysis", media_result.get("error")))

    if media is not None:
        if not media["hasAudio"]:
            stt_error = {"code": "NO_AUDIO_TRACK", "message": "The video has no audio track, so there is nothing to transcribe"}
            errors.append({"stage": "stt", **stt_error})
        else:
            stt_result = stt_fn(media["audioFile"])
            if stt_result.get("status") == "ok":
                status["stt"] = "ok"
                transcript = stt_result["transcript"]
                media["sceneSegments"] = build_segments(
                    media["durationSeconds"], media["sceneChanges"], media["frames"], transcript["segments"])
            else:
                status["stt"] = "failed"
                stt_error = stt_result.get("error")
                errors.append(_stage_error("stt", stt_error))

    timestamps = []
    if transcript is not None:
        result = analyze_fn(case_id, transcript["text"], media_context_for_ai(media),
                            segments=transcript["segments"])
        if result.get("status") == "ok":
            status["watsonx"] = "ok"
            analysis = result["result"]
            warnings = list(result.get("warnings", []))
            timestamps = build_timestamps(analysis, transcript["segments"])
        else:
            status["watsonx"] = "failed"
            errors.append(_stage_error("watsonx", result.get("error")))

    oks = [v == "ok" for v in status.values()]
    overall = "ok" if all(oks) else ("failed" if not any(oks) else "partial")
    return {
        "status": overall,
        "caseId": case_id,
        "transcript": build_transcript_doc(case_id, status["stt"], transcript, stt_error),
        "case": build_case_doc(case_id, status, analysis, timestamps, media, errors, warnings),
    }
