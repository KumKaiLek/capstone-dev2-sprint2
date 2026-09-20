"""Speech-to-Text processing and transcript contract (IBM Watson Speech to Text).

Sends approved synthetic/staged audio to IBM Speech to Text and normalises the result into
one transcript contract for the later backend and AI (watsonx.ai) integration.

Settings come from .env (never hardcoded, never printed):
  STT_API_KEY  the Speech to Text API key
  STT_URL      the service URL including the instance, e.g.
               https://api.<region>.speech-to-text.watson.cloud.ibm.com/instances/<id>
  STT_MODEL    optional, defaults to en-US_Multimedia
"""
from pathlib import Path
import requests

from .config import get_setting, ConfigError

ALLOWED_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}
MAX_MB = 100  # Watson STT limit per request
TIMEOUT = 120
DEFAULT_MODEL = "en-US_Multimedia"


class SttError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _error(code, message):
    return {"status": "error", "error": {"code": code, "message": message}}


def stt_settings():
    return {
        "api_key": get_setting("STT_API_KEY"),
        "url": get_setting("STT_URL").rstrip("/"),
        "model": get_setting("STT_MODEL", DEFAULT_MODEL),
    }


def validate_audio(path):
    if path is None or not str(path).strip():
        raise SttError("MISSING_INPUT", "No audio path was provided")
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise SttError("FILE_NOT_FOUND", f"File not found: {p.name}")
    if p.suffix.lower() not in ALLOWED_TYPES:
        raise SttError("INVALID_INPUT", f"Unsupported audio type {p.suffix or '(none)'}; allowed: {sorted(ALLOWED_TYPES)}")
    size = p.stat().st_size
    if size == 0:
        raise SttError("INVALID_INPUT", "Audio file is empty")
    if size > MAX_MB * 1024 * 1024:
        raise SttError("INVALID_INPUT", f"Audio file is larger than {MAX_MB} MB")
    return p


def _default_post(url, params, headers, data, auth):
    return requests.post(url, params=params, headers=headers, data=data, auth=auth, timeout=TIMEOUT)


def normalise(raw, model, source_name):
    """Turn a Watson STT response into the transcript contract."""
    try:
        results = raw["results"]
    except (KeyError, TypeError):
        raise SttError("MALFORMED_RESPONSE", "STT response had no results field")
    if not isinstance(results, list):
        raise SttError("MALFORMED_RESPONSE", "STT results was not a list")
    if not results:
        raise SttError("EMPTY_TRANSCRIPT", "STT returned no speech for this audio")

    segments, confidences = [], []
    for r in results:
        try:
            alt = r["alternatives"][0]
            text = alt["transcript"].strip()
        except (KeyError, IndexError, TypeError, AttributeError):
            raise SttError("MALFORMED_RESPONSE", "STT result had no usable alternative")
        if not text:
            continue
        stamps = alt.get("timestamps") or []
        start = round(float(stamps[0][1]), 2) if stamps else None
        end = round(float(stamps[-1][2]), 2) if stamps else None
        conf = alt.get("confidence")
        if conf is not None:
            confidences.append(float(conf))
        segments.append({"startSec": start, "endSec": end, "text": text,
                         "confidence": round(float(conf), 2) if conf is not None else None})

    if not segments:
        raise SttError("EMPTY_TRANSCRIPT", "STT returned only empty text")

    ends = [s["endSec"] for s in segments if s["endSec"] is not None]
    return {
        "source": source_name,
        "model": model,
        "text": " ".join(s["text"] for s in segments),
        "confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
        "durationSeconds": max(ends) if ends else None,
        "segments": segments,
    }


def transcribe(path, _settings=None, _post_fn=None):
    """Never raises. Returns {"status": "ok", "transcript": {...}} or {"status": "error", ...}.
    _settings and _post_fn let the tests run without IBM."""
    try:
        p = validate_audio(path)
        s = _settings if _settings is not None else stt_settings()
        post = _post_fn or _default_post
        try:
            with open(p, "rb") as f:
                resp = post(
                    f"{s['url']}/v1/recognize",
                    {"model": s["model"], "timestamps": "true"},
                    {"Content-Type": ALLOWED_TYPES[p.suffix.lower()]},
                    f,
                    ("apikey", s["api_key"]),
                )
        except requests.RequestException as e:
            raise SttError("NETWORK_ERROR", f"Could not reach Speech to Text: {type(e).__name__}")

        if resp.status_code in (401, 403):
            raise SttError("AUTH_FAILED", f"Speech to Text returned HTTP {resp.status_code} (check STT_API_KEY and STT_URL)")
        if resp.status_code == 400:
            raise SttError("INVALID_INPUT", "Speech to Text rejected the audio (HTTP 400, check the format)")
        if resp.status_code != 200:
            raise SttError("STT_SERVICE_ERROR", f"Speech to Text returned HTTP {resp.status_code}")
        try:
            raw = resp.json()
        except ValueError:
            raise SttError("MALFORMED_RESPONSE", "STT response was not valid JSON")
        return {"status": "ok", "transcript": normalise(raw, s["model"], p.name)}
    except ConfigError as e:
        return _error("CONFIG_ERROR", str(e))
    except SttError as e:
        return _error(e.code, e.message)
