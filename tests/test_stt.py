"""Offline tests for the STT component. No IBM call, no key needed.
Run: python -m tests.test_stt"""
import json
import os
import tempfile
from pathlib import Path
import requests
from src.stt import transcribe, stt_settings

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


class Resp:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code = status
        self._body = body
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._body


SECRET = "SUPER-SECRET-KEY-123"
SETTINGS = {"api_key": SECRET, "url": "https://stt.example.test/instances/abc", "model": "en-US_Multimedia"}
GOOD = {"result_index": 0, "results": [{"final": True, "alternatives": [{
    "transcript": "this is a test message ", "confidence": 0.97,
    "timestamps": [["this", 0.4, 0.6], ["is", 0.6, 0.7], ["a", 0.7, 0.8], ["test", 0.8, 1.1], ["message", 1.1, 1.6]]}]}]}

tmp = Path(tempfile.mkdtemp())
wav = tmp / "sample.wav"; wav.write_bytes(b"RIFF....WAVEfmt ")


def run(post_fn, path=None):
    return transcribe(str(path or wav), _settings=SETTINGS, _post_fn=post_fn)


# input handling
check("missing input handled", transcribe(None)["error"]["code"] == "MISSING_INPUT")
check("missing file handled", transcribe(str(tmp / "nope.wav"))["error"]["code"] == "FILE_NOT_FOUND")
txt = tmp / "notes.txt"; txt.write_text("hi")
check("wrong file type rejected", transcribe(str(txt))["error"]["code"] == "INVALID_INPUT")
empty = tmp / "empty.wav"; empty.write_bytes(b"")
check("empty audio rejected", transcribe(str(empty))["error"]["code"] == "INVALID_INPUT")

# good result and normalisation
out = run(lambda *a, **k: Resp(200, GOOD))
t = out.get("transcript", {})
check("transcript returned", out["status"] == "ok" and t.get("text") == "this is a test message")
check("confidence returned", t.get("confidence") == 0.97)
check("timestamps normalised into segments", t.get("segments") == [{"startSec": 0.4, "endSec": 1.6, "text": "this is a test message", "confidence": 0.97}])
check("duration and source recorded", t.get("durationSeconds") == 1.6 and t.get("source") == "sample.wav")

no_conf = {"results": [{"alternatives": [{"transcript": "hello there", "timestamps": [["hello", 0.0, 0.5], ["there", 0.5, 1.0]]}]}]}
out = run(lambda *a, **k: Resp(200, no_conf))
check("missing confidence handled (null)", out["status"] == "ok" and out["transcript"]["confidence"] is None)

two = {"results": [
    {"alternatives": [{"transcript": "first part ", "confidence": 0.9, "timestamps": [["first", 0, 1], ["part", 1, 2]]}]},
    {"alternatives": [{"transcript": "second part ", "confidence": 0.8, "timestamps": [["second", 3, 4], ["part", 4, 5]]}]}]}
out = run(lambda *a, **k: Resp(200, two))
check("multiple utterances become segments", len(out["transcript"]["segments"]) == 2 and out["transcript"]["confidence"] == 0.85)

# service failures
check("auth failure handled (401)", run(lambda *a, **k: Resp(401, {}))["error"]["code"] == "AUTH_FAILED")
check("service failure handled (500)", run(lambda *a, **k: Resp(500, {}))["error"]["code"] == "STT_SERVICE_ERROR")
check("bad audio handled (400)", run(lambda *a, **k: Resp(400, {}))["error"]["code"] == "INVALID_INPUT")


def boom(*a, **k):
    raise requests.ConnectionError("down")


check("network failure handled", run(boom)["error"]["code"] == "NETWORK_ERROR")
check("malformed response handled", run(lambda *a, **k: Resp(200, {"oops": 1}))["error"]["code"] == "MALFORMED_RESPONSE")
check("invalid JSON handled", run(lambda *a, **k: Resp(200, bad_json=True))["error"]["code"] == "MALFORMED_RESPONSE")
check("no speech handled", run(lambda *a, **k: Resp(200, {"results": []}))["error"]["code"] == "EMPTY_TRANSCRIPT")

# authentication handled securely
seen = {}


def spy(url, params, headers, data, auth):
    seen["auth"] = auth
    seen["headers"] = headers
    return Resp(200, GOOD)


ok = run(spy)
check("key sent as basic auth, not in URL or headers", seen["auth"] == ("apikey", SECRET) and SECRET not in json.dumps(seen["headers"]))
check("key never appears in any output", SECRET not in json.dumps(ok) and SECRET not in json.dumps(run(lambda *a, **k: Resp(401, {}))) and SECRET not in json.dumps(run(boom)))
check("instance URL never appears in errors", "example.test" not in json.dumps(run(boom)) and "example.test" not in json.dumps(run(lambda *a, **k: Resp(500, {}))))

# config
old = os.environ.get("STT_API_KEY")
os.environ["STT_API_KEY"] = ""
r = transcribe(str(wav))
check("missing key handled (config error)", r["error"]["code"] == "CONFIG_ERROR")
if old is None:
    del os.environ["STT_API_KEY"]
else:
    os.environ["STT_API_KEY"] = old

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
