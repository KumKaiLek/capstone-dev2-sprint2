"""Offline tests for Sprint 3 error handling: timeouts, service errors, truncated, malformed,
incomplete, missing and empty model output. No IBM call, no key needed: the network is faked and
the real stt, analysis and pipeline code runs. Run: python -m tests.test_errors"""
import json
import os
import tempfile
from pathlib import Path

import requests

import src.analysis as analysis_mod
import src.stt as stt_mod
from src.analysis import analyze
from src.config import get_timeout
from src.pipeline import run_case
from src.store import LocalCaseStore
from tests.simulated import WATSONX_SETTINGS, Resp, run_scenario, watsonx_network_service

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


def nothing_filled_in(a):
    """The rule for every failure: no severity, summary, categories, evidence or timestamps."""
    return (a["severity"] is None and a["summary"] is None and a["categories"] == []
            and a["evidenceSegments"] == {} and a["timestamps"] == [] and a["advisory"] is True
            and a["requiresHumanReview"] is True)


base = Path(tempfile.mkdtemp())
EXPECT = {
    # scenario: (stage that failed, code, overall result)
    "stt_timeout": ("stt", "TIMEOUT", "partial"),
    "watsonx_timeout": ("watsonx", "TIMEOUT", "partial"),
    "iam_timeout": ("watsonx", "TIMEOUT", "partial"),
    "watsonx_service_error": ("watsonx", "SERVICE_ERROR", "partial"),
    "truncated_output": ("watsonx", "INCOMPLETE_OUTPUT", "partial"),
    "truncated_but_parseable": ("watsonx", "INCOMPLETE_OUTPUT", "partial"),
    "malformed_json": ("watsonx", "MALFORMED_OUTPUT", "partial"),
    "incomplete_json": ("watsonx", "INVALID_OUTPUT", "partial"),
    "missing_values": ("watsonx", "INVALID_OUTPUT", "partial"),
    "empty_values": ("watsonx", "INVALID_OUTPUT", "partial"),
}
for name, (stage, code, overall) in EXPECT.items():
    out = run_scenario(name, base, base / "work")
    a, t = out["files"]["analysis.json"], out["files"]["transcript.json"]
    other_stage = "watsonx" if stage == "stt" else "stt"
    check(f"{name}: {stage} failed with {code}, result {overall}",
          out["resultStatus"] == overall and a["processingStatus"][stage] == "failed"
          and a["errors"] == [{"stage": stage, "code": code, "message": a["errors"][0]["message"]}]
          and a["errors"][0]["message"])
    check(f"{name}: nothing fabricated, severity summary categories evidence and timestamps empty",
          nothing_filled_in(a))
    if stage == "stt":
        check(f"{name}: transcript.json records the failure with no text or segments, watsonx never ran",
              t["status"] == "failed" and t["error"]["code"] == code and t["transcript"] is None
              and t["segments"] == [] and a["processingStatus"][other_stage] == "unavailable")
    else:
        check(f"{name}: the real transcript is kept, only the watsonx stage failed",
              t["status"] == "ok" and t["transcript"] and a["processingStatus"]["stt"] == "ok")


# the single retry: once for truncated or bad output, never for a timeout or service error
def chat_calls(kind):
    calls = []
    watsonx_network_service(kind, calls)("CASE-001", "some transcript", {}, segments=[{"text": "a"}])
    return len(calls)


check("truncated output is retried once, then fails (2 chat calls)", chat_calls("wx_truncated") == 2)
check("malformed JSON is retried once, then fails (2 chat calls)", chat_calls("wx_malformed_json") == 2)
check("a watsonx timeout is not retried (1 chat call)", chat_calls("wx_timeout") == 1)
check("a watsonx service error is not retried (1 chat call)", chat_calls("wx_service_error") == 1)
check("an IAM timeout never reaches the chat call (0 chat calls)", chat_calls("iam_timeout") == 0)

GOOD = json.dumps({"caseId": "CASE-001", "severity": "low", "summary": "A neutral summary.", "categories": [],
                   "concerningSegments": [], "evidenceSegments": {}})
replies = iter([("{\"caseId\": \"CASE-001\", \"sev", "length"), (GOOD, "stop")])


def truncated_then_good(url, **kwargs):
    if "iam" in url:
        return Resp(200, {"access_token": "t"})
    content, finish = next(replies)
    return Resp(200, {"choices": [{"message": {"content": content}, "finish_reason": finish}]})


r = analyze("CASE-001", "t", {}, segments=[{"text": "a"}], _settings=WATSONX_SETTINGS, _post_fn=truncated_then_good)
check("a truncated reply followed by a complete one succeeds on the retry, flagged succeeded_on_retry",
      r["status"] == "ok" and "succeeded_on_retry" in r["warnings"] and r["result"]["severity"] == "low")


def ok_with_finish(finish):
    def post(url, **kwargs):
        if "iam" in url:
            return Resp(200, {"access_token": "t"})
        return Resp(200, {"choices": [{"message": {"content": GOOD}, **({} if finish is None else {"finish_reason": finish})}]})
    return post


check("finish_reason stop is accepted", analyze("CASE-001", "t", {}, _settings=WATSONX_SETTINGS,
                                                _post_fn=ok_with_finish("stop"))["status"] == "ok")
check("no finish_reason at all is accepted, only length is treated as incomplete",
      analyze("CASE-001", "t", {}, _settings=WATSONX_SETTINGS, _post_fn=ok_with_finish(None))["status"] == "ok")


# timeouts come from the environment, defaults unchanged
def with_env(name, value, fn):
    old = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


check("STT_TIMEOUT default is still 120 seconds", with_env("STT_TIMEOUT", None, lambda: get_timeout("STT_TIMEOUT", stt_mod.TIMEOUT)) == 120.0)
check("WATSONX_TIMEOUT default is still 60 seconds",
      with_env("WATSONX_TIMEOUT", None, lambda: get_timeout("WATSONX_TIMEOUT", analysis_mod.TIMEOUT)) == 60.0)
check("WATSONX_TIMEOUT=0.001 is read as 0.001 seconds", with_env("WATSONX_TIMEOUT", "0.001", lambda: get_timeout("WATSONX_TIMEOUT", 60)) == 0.001)

seen = {}


def capture(url, **kwargs):
    seen.setdefault("timeouts", []).append(kwargs["timeout"])
    if "iam" in url:
        return Resp(200, {"access_token": "t"})
    return Resp(200, {"choices": [{"message": {"content": GOOD}, "finish_reason": "stop"}]})


with_env("WATSONX_TIMEOUT", "7.5", lambda: analyze("CASE-001", "t", {}, _settings=WATSONX_SETTINGS, _post_fn=capture))
check("WATSONX_TIMEOUT is passed to both the IAM call and the chat call", seen["timeouts"] == [7.5, 7.5])

real_post = stt_mod.requests.post
stt_mod.requests.post = lambda *a, **k: seen.update(stt_timeout=k["timeout"]) or Resp(200, {"results": []})
try:
    with_env("STT_TIMEOUT", "3", lambda: stt_mod._default_post("u", {}, {}, b"", ("apikey", "k")))
finally:
    stt_mod.requests.post = real_post
check("STT_TIMEOUT is passed to the Speech to Text call", seen.get("stt_timeout") == 3.0)

for bad in ("abc", "0", "-1"):
    r = with_env("WATSONX_TIMEOUT", bad, lambda: analyze("CASE-001", "t", {}, _settings=WATSONX_SETTINGS, _post_fn=capture))
    check(f"WATSONX_TIMEOUT={bad} gives CONFIG_ERROR, not a call with a bad timeout", r["error"]["code"] == "CONFIG_ERROR")
wav = base / "a.wav"
wav.write_bytes(b"RIFF....WAVEfmt ")
r = with_env("STT_TIMEOUT", "abc", lambda: stt_mod.transcribe(str(wav), _settings={"api_key": "k", "url": "u", "model": "m"}))
check("STT_TIMEOUT=abc gives CONFIG_ERROR from transcribe, not a crash", r["status"] == "error" and r["error"]["code"] == "CONFIG_ERROR")


# a timeout is TIMEOUT, other network failures are still NETWORK_ERROR
def raises(exc):
    def post(*a, **k):
        raise exc
    return post


stt = lambda post: stt_mod.transcribe(str(wav), _settings={"api_key": "k", "url": "u", "model": "m"}, _post_fn=post)
check("STT read timeout gives TIMEOUT", stt(raises(requests.ReadTimeout()))["error"]["code"] == "TIMEOUT")
check("STT connect timeout gives TIMEOUT", stt(raises(requests.ConnectTimeout()))["error"]["code"] == "TIMEOUT")
check("STT connection error is still NETWORK_ERROR", stt(raises(requests.ConnectionError()))["error"]["code"] == "NETWORK_ERROR")
wx = lambda post: analyze("CASE-001", "t", {}, _settings=WATSONX_SETTINGS, _post_fn=post)["error"]["code"]
check("watsonx connect timeout gives TIMEOUT", wx(raises(requests.ConnectTimeout())) == "TIMEOUT")
check("watsonx connection error is still NETWORK_ERROR", wx(raises(requests.ConnectionError())) == "NETWORK_ERROR")
timeout_out = json.dumps([analyze("CASE-001", "t", {}, _settings=WATSONX_SETTINGS, _post_fn=raises(requests.Timeout())),
                          stt(raises(requests.Timeout()))])
check("TIMEOUT results never contain the key or the service URL",
      "TIMEOUT" in timeout_out and "simulated-key" not in timeout_out and "example.test" not in timeout_out
      and '"u"' not in timeout_out)


# a stage that raises instead of returning an error still ends in a recorded state
folder = base / "cases" / "CASE-030"
folder.mkdir(parents=True)
(folder / "case.json").write_text(json.dumps({"caseId": "CASE-030", "fileName": "a.wav", "contentType": "audio",
                                              "mediaObjectKey": "cases/CASE-030/a.wav"}))
(folder / "a.wav").write_bytes(b"RIFF....WAVEfmt ")


def stt_bug(path):
    raise ValueError("bug")


r = run_case("CASE-030", LocalCaseStore(base), work_dir=str(base / "work"), _stt_fn=stt_bug)
a = r["analysis"]
check("a stage that raises becomes UNEXPECTED_ERROR in errors, not a crash",
      r["status"] == "failed" and a["processingStatus"]["stt"] == "failed"
      and a["errors"][0]["code"] == "UNEXPECTED_ERROR" and nothing_filled_in(a))


def analyze_bug(*a, **k):
    raise KeyError("bug")


r = run_case("CASE-030", LocalCaseStore(base), work_dir=str(base / "work"),
             _stt_fn=lambda p: {"status": "ok", "transcript": {"text": "hi", "segments": [
                 {"startSec": 0.0, "endSec": 1.0, "text": "hi", "confidence": 0.9}], "durationSeconds": 1.0}},
             _analyze_fn=analyze_bug)
a = r["analysis"]
check("a watsonx stage that raises is UNEXPECTED_ERROR, the real transcript is kept, nothing invented",
      r["status"] == "partial" and a["processingStatus"]["watsonx"] == "failed"
      and a["errors"][0]["code"] == "UNEXPECTED_ERROR" and nothing_filled_in(a)
      and r["transcript"]["transcript"] == "hi")

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
