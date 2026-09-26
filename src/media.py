"""Video/media analysis and scene segment adapter.

Selected approach (MVP): ffmpeg based. For an approved synthetic or staged video we
  1. validate the input,
  2. probe duration and streams,
  3. extract audio (ready for the STT component),
  4. extract frames every few seconds (ready for a future vision model),
  5. detect scene changes and turn them into scene segments with start/end times,
  6. build a backend ready payload that also carries the watsonx.ai result.
Scene segments are visual cuts only and are never treated as incident evidence. Incident
timestamps come from measured STT segment times (see src/pipeline.py).
Visual classification of the frames is out of scope for this MVP. The media signals
(duration, scene changes, segments) are passed to watsonx.ai as media context so they can
contribute to severity, summary and categories.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm"}
MAX_MB = 200
FRAME_EVERY_SEC = 2
SCENE_THRESHOLD = 0.3
TIMEOUT = 120


class MediaError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _error(code, message):
    return {"status": "error", "error": {"code": code, "message": message}}


def check_tools():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise MediaError("TOOL_MISSING", f"{tool} is not installed or not on PATH")


def validate_input(path):
    if path is None or not str(path).strip():
        raise MediaError("MISSING_INPUT", "No video path was provided")
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise MediaError("FILE_NOT_FOUND", f"File not found: {p.name}")
    if p.suffix.lower() not in ALLOWED_EXT:
        raise MediaError("INVALID_INPUT", f"Unsupported file type {p.suffix or '(none)'}; allowed: {sorted(ALLOWED_EXT)}")
    size = p.stat().st_size
    if size == 0:
        raise MediaError("INVALID_INPUT", "File is empty")
    if size > MAX_MB * 1024 * 1024:
        raise MediaError("INVALID_INPUT", f"File is larger than {MAX_MB} MB")
    return p


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise MediaError("PROCESSING_TIMEOUT", "ffmpeg took too long")


def probe(p):
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
              "-of", "json", str(p)])
    if r.returncode != 0:
        raise MediaError("MEDIA_UNREADABLE", "ffprobe could not read the file (corrupt or not a video)")
    try:
        info = json.loads(r.stdout)
        duration = float(info["format"]["duration"])
        kinds = [s.get("codec_type") for s in info.get("streams", [])]
    except (KeyError, ValueError, json.JSONDecodeError):
        raise MediaError("MEDIA_UNREADABLE", "Could not read duration or streams")
    if "video" not in kinds:
        raise MediaError("MEDIA_UNREADABLE", "File has no video stream")
    return {"durationSeconds": round(duration, 2), "hasVideo": True, "hasAudio": "audio" in kinds}


def extract_audio(p, out_dir):
    out = Path(out_dir) / (p.stem + "_audio.wav")
    r = _run(["ffmpeg", "-y", "-i", str(p), "-vn", "-ac", "1", "-ar", "16000", str(out)])
    if r.returncode != 0 or not out.exists():
        raise MediaError("AUDIO_EXTRACTION_FAILED", "Could not extract the audio track")
    return str(out)


def extract_frames(p, out_dir, every=FRAME_EVERY_SEC):
    frames_dir = Path(out_dir) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("frame_*.jpg"):
        old.unlink()
    r = _run(["ffmpeg", "-y", "-i", str(p), "-vf", f"fps=1/{every}", "-q:v", "3",
              str(frames_dir / "frame_%03d.jpg")])
    if r.returncode != 0:
        raise MediaError("FRAME_EXTRACTION_FAILED", "Could not extract frames")
    files = sorted(frames_dir.glob("frame_*.jpg"))
    return [{"file": f.name, "timeSec": float(i * every)} for i, f in enumerate(files)]


def detect_scene_changes(p, threshold=SCENE_THRESHOLD):
    r = _run(["ffmpeg", "-i", str(p), "-vf", f"select='gt(scene,{threshold})',showinfo",
              "-an", "-f", "null", "-"])
    if r.returncode != 0:
        raise MediaError("SCENE_DETECTION_FAILED", "Scene detection failed")
    times = [round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    return sorted(set(times))


def build_segments(duration, scene_times, frames=None, transcript_segments=None):
    """Turn scene change times into scene segments with start and end seconds.
    These are visual cuts only, not evidence of an incident. Transcript segments without
    timing are left out of the time matching instead of being given a guessed time."""
    cuts = [0.0] + [t for t in scene_times if 0 < t < duration] + [round(duration, 2)]
    cuts = sorted(set(cuts))
    timed = [t for t in (transcript_segments or [])
             if t.get("startSec") is not None and t.get("endSec") is not None]
    segments = []
    for i in range(len(cuts) - 1):
        start, end = cuts[i], cuts[i + 1]
        seg = {"segmentId": i + 1, "startSec": start, "endSec": end, "label": f"scene {i + 1}",
               "frameFiles": [f["file"] for f in (frames or []) if start <= f["timeSec"] < end]}
        if transcript_segments:
            texts = [t["text"] for t in timed if t["startSec"] < end and t["endSec"] > start]
            seg["transcriptText"] = " ".join(texts)
        segments.append(seg)
    return segments


def analyse_media(path, work_dir="outputs/media", transcript_segments=None):
    """Never raises. Returns {"status": "ok", "media": {...}} or {"status": "error", ...}."""
    try:
        check_tools()
        p = validate_input(path)
        info = probe(p)
        out_dir = Path(work_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio = extract_audio(p, out_dir) if info["hasAudio"] else None
        frames = extract_frames(p, out_dir)
        scenes = detect_scene_changes(p)
        segments = build_segments(info["durationSeconds"], scenes, frames, transcript_segments)
        media = {
            "sourceType": "synthetic_video",
            "fileName": p.name,
            "durationSeconds": info["durationSeconds"],
            "hasAudio": info["hasAudio"],
            "audioFile": audio,
            "frameCount": len(frames),
            "frames": frames,
            "sceneChanges": scenes,
            "sceneSegments": segments,
        }
        return {"status": "ok", "media": media}
    except MediaError as e:
        return _error(e.code, e.message)


def media_context_for_ai(media):
    """Compact media signals that are passed to watsonx.ai as media context."""
    return {
        "sourceType": media["sourceType"],
        "durationSeconds": media["durationSeconds"],
        "hasAudio": media["hasAudio"],
        "sceneChangeCount": len(media["sceneChanges"]),
        "sceneSegments": [
            {"startSec": s["startSec"], "endSec": s["endSec"], "label": s["label"]}
            for s in media["sceneSegments"]
        ],
    }


def build_backend_payload(case_id, media_result, analysis_result):
    """Normalised, backend ready payload that combines media output and the watsonx.ai result.
    Handles a missing or failed analysis result without crashing."""
    payload = {
        "caseId": case_id,
        "advisory": True,
        "requiresHumanReview": True,
        "media": None,
        "sceneSegments": [],
        "analysisStatus": "missing",
        "analysis": None,
        "errors": [],
    }
    if not media_result or media_result.get("status") != "ok":
        err = (media_result or {}).get("error", {"code": "MEDIA_MISSING", "message": "No media result"})
        payload["errors"].append({"stage": "media", **err})
    else:
        m = media_result["media"]
        payload["media"] = {k: m[k] for k in ("sourceType", "fileName", "durationSeconds",
                                              "hasAudio", "frameCount", "sceneChanges")}
        payload["sceneSegments"] = m["sceneSegments"]

    if analysis_result is None:
        payload["analysisStatus"] = "missing"
        payload["errors"].append({"stage": "analysis", "code": "ANALYSIS_MISSING",
                                  "message": "No watsonx.ai result was provided"})
    elif analysis_result.get("status") == "ok":
        payload["analysisStatus"] = "ok"
        payload["analysis"] = analysis_result["result"]
    else:
        payload["analysisStatus"] = "failed"
        payload["errors"].append({"stage": "analysis", **analysis_result.get("error", {})})
    return payload
