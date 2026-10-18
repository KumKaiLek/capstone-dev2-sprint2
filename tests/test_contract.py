"""Offline contract test: fails if the shared schema with Dev1 changes. No IBM call, no key needed.
Run: python -m tests.test_contract
If one of these checks fails, the contract changed. Agree the change with Dev1 first, then update
this file in the same commit, never just to make it pass."""
import tempfile
from pathlib import Path

from src.analysis import analyze
from src.pipeline import build_analysis_doc, build_transcript_doc, run_case
from src.schemas import CATEGORIES, SEVERITIES
from src.store import LocalCaseStore
from tests.simulated import run_scenario

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


check("SEVERITIES unchanged", SEVERITIES == ["low", "medium", "high"])
check("CATEGORIES unchanged, same values in the same order", CATEGORIES == [
    "hate_speech", "harassment", "violence", "self_harm", "sexual_content", "misinformation", "other"])

ANALYSIS_FIELDS = ["caseId", "severity", "summary", "categories", "evidenceSegments", "timestamps",
                   "processingStatus", "advisory", "requiresHumanReview", "model", "mediaType", "mediaFile",
                   "media", "sceneSegments", "errors", "warnings"]
TRANSCRIPT_FIELDS = ["caseId", "transcript", "confidence", "status", "error", "segments", "source", "model",
                     "durationSeconds"]
SEGMENT_FIELDS = ["startSec", "endSec", "text", "confidence", "timestampStatus", "timestampReason"]
TIMESTAMP_FIELDS = {"start", "end", "reason", "timestampStatus"}
STAGES = {"stt", "mediaAnalysis", "watsonx"}

a = build_analysis_doc("CASE-001", {"stt": "ok", "mediaAnalysis": "ok", "watsonx": "ok"}, None, [], None,
                       "video", "video.mp4", [], [])
check("analysis.json field names unchanged, same order", list(a) == ANALYSIS_FIELDS)
t = build_transcript_doc("CASE-001", "ok", {"text": "x", "segments": [
    {"startSec": 0.0, "endSec": 1.0, "text": "x", "confidence": 0.9, "timestampStatus": "available",
     "timestampReason": None}]}, None)
check("transcript.json field names unchanged, same order", list(t) == TRANSCRIPT_FIELDS)
check("transcript.json segment field names unchanged", list(t["segments"][0]) == SEGMENT_FIELDS)

r = analyze("", "text", {}, _chat_fn=lambda m: "{}")
check("error envelope is {status: error, error: {code, message}}",
      set(r) == {"status", "error"} and r["status"] == "error" and set(r["error"]) == {"code", "message"})

r = run_case("bad id", LocalCaseStore("/nonexistent"))
check("run_case error envelope is {status: error, error: {code, message}}",
      set(r) == {"status", "error"} and set(r["error"]) == {"code", "message"})

# A real pipeline run (simulated services) for the processingStatus, errors and timestamps shapes
base = Path(tempfile.mkdtemp())
happy = run_scenario("happy_path", base, base / "work")["files"]["analysis.json"]
check("processingStatus has exactly the stages stt, mediaAnalysis, watsonx", set(happy["processingStatus"]) == STAGES)
check("each timestamp entry has exactly start, end, reason, timestampStatus",
      happy["timestamps"] and all(set(ts) == TIMESTAMP_FIELDS for ts in happy["timestamps"]))
failed = run_scenario("stt_server_error", base, base / "work")["files"]["analysis.json"]
check("each errors entry has exactly stage, code, message",
      failed["errors"] and all(set(e) == {"stage", "code", "message"} for e in failed["errors"]))

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
