"""Offline tests for the case pipeline. Speech to Text, watsonx.ai and ffmpeg are simulated,
no IBM call and no key needed. Run: python -m tests.test_pipeline"""
import tempfile
from pathlib import Path
from src.pipeline import media_kind, read_media_object, resolve_media_reference, run_case
from src.store import LocalCaseStore
from tests.simulated import SCENARIOS, media_service, run_scenario, stt_service, chat_service

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


base = Path(tempfile.mkdtemp())
work = base / "work"
out = {name: run_scenario(name, base, work) for name in SCENARIOS}


def files(name):
    return out[name]["files"]


def status(name):
    return files(name)["analysis.json"]["processingStatus"]


def errors(name):
    return files(name)["analysis.json"]["errors"]


def dev1_untouched(name):
    return files(name)["case.json"] == out[name]["original_case_json"]


# 1 happy path
h = files("happy_path")
check("happy path: every stage ok", out["happy_path"]["resultStatus"] == "ok"
      and status("happy_path") == {"stt": "ok", "mediaAnalysis": "ok", "watsonx": "ok"})
check("happy path: transcript.json and analysis.json written, both saved ok",
      "transcript.json" in h and "analysis.json" in h and all(s["status"] == "ok" for s in out["happy_path"]["saved"].values()))
check("happy path: Dev1's case.json is left exactly as it was", dev1_untouched("happy_path"))
check("happy path: transcript text, confidence and timed segments", h["transcript.json"]["status"] == "ok"
      and h["transcript.json"]["confidence"] == 0.93 and len(h["transcript.json"]["segments"]) == 2
      and all(s["timestampStatus"] == "available" for s in h["transcript.json"]["segments"]))
check("happy path: incident timestamp is the measured STT time of the flagged segment",
      h["analysis.json"]["timestamps"] == [{"start": 3.64, "end": 9.7, "timestampStatus": "available",
                                            "reason": "segment 2 flagged by watsonx.ai (harassment, violence)"}])
check("happy path: Dev1's fields and advisory flags in analysis.json", h["analysis.json"]["severity"] == "high"
      and h["analysis.json"]["categories"] == ["harassment", "violence"] and h["analysis.json"]["summary"]
      and h["analysis.json"]["advisory"] is True and h["analysis.json"]["requiresHumanReview"] is True)
scenes = h["analysis.json"]["sceneSegments"]
check("happy path: scene cuts kept as sceneSegments with no severity", len(scenes) == 2
      and all("severity" not in s for s in scenes) and "sceneSegments" in h["analysis.json"])

# 2 missing media
check("missing media: recorded as failed, later stages unavailable, no crash",
      out["missing_media"]["resultStatus"] == "failed"
      and status("missing_media") == {"stt": "unavailable", "mediaAnalysis": "failed", "watsonx": "unavailable"}
      and errors("missing_media")[0]["code"] == "MEDIA_NOT_FOUND")
check("missing media: both files still written with the failure state",
      files("missing_media")["transcript.json"]["status"] == "unavailable"
      and files("missing_media")["transcript.json"]["transcript"] is None
      and files("missing_media")["analysis.json"]["severity"] is None and dev1_untouched("missing_media"))

# 3 invalid media type
check("invalid media type: rejected and recorded", out["invalid_media_type"]["resultStatus"] == "failed"
      and status("invalid_media_type")["mediaAnalysis"] == "failed" and errors("invalid_media_type")[0]["code"] == "INVALID_MEDIA_TYPE"
      and status("invalid_media_type")["stt"] == "unavailable" and dev1_untouched("invalid_media_type"))

# 4 STT 500
check("STT 500: stt failed, the rest recorded, result is partial", out["stt_server_error"]["resultStatus"] == "partial"
      and status("stt_server_error") == {"stt": "failed", "mediaAnalysis": "ok", "watsonx": "unavailable"}
      and errors("stt_server_error")[0]["code"] == "STT_SERVICE_ERROR")
check("STT 500: failure kept in transcript.json, scene cuts still there, nothing invented",
      files("stt_server_error")["transcript.json"]["status"] == "failed"
      and files("stt_server_error")["transcript.json"]["error"]["code"] == "STT_SERVICE_ERROR"
      and len(files("stt_server_error")["analysis.json"]["sceneSegments"]) == 2
      and files("stt_server_error")["analysis.json"]["severity"] is None and files("stt_server_error")["analysis.json"]["timestamps"] == [])

# 5 malformed watsonx output
check("malformed watsonx output: watsonx failed, transcript kept, result is partial",
      out["malformed_watsonx_output"]["resultStatus"] == "partial"
      and status("malformed_watsonx_output") == {"stt": "ok", "mediaAnalysis": "ok", "watsonx": "failed"}
      and errors("malformed_watsonx_output")[0]["code"] == "MALFORMED_OUTPUT"
      and files("malformed_watsonx_output")["transcript.json"]["transcript"]
      and files("malformed_watsonx_output")["analysis.json"]["severity"] is None
      and files("malformed_watsonx_output")["analysis.json"]["timestamps"] == [])

# 6 no timestamps
nt = files("no_timestamps")
check("no timestamps: does not crash and the run still finishes ok", out["no_timestamps"]["resultStatus"] == "ok")
check("no timestamps: segments have null times, unavailable status and a reason, never 0",
      all(s["startSec"] is None and s["endSec"] is None and s["timestampStatus"] == "unavailable" and s["timestampReason"]
          for s in nt["transcript.json"]["segments"]))
t = nt["analysis.json"]["timestamps"][0]
check("no timestamps: the incident timestamp is null, unavailable, with a reason (not estimated)",
      len(nt["analysis.json"]["timestamps"]) == 1 and t["start"] is None and t["end"] is None
      and t["timestampStatus"] == "unavailable" and "no timing" in t["reason"])

# 7 invalid segment index
t = files("invalid_segment_index")["analysis.json"]["timestamps"]
check("invalid segment index: recorded as unavailable with a reason, run still ok", out["invalid_segment_index"]["resultStatus"] == "ok"
      and len(t) == 1 and t[0]["start"] is None and t[0]["end"] is None and t[0]["timestampStatus"] == "unavailable"
      and "segment 9" in t[0]["reason"])

# 8 case id mismatch
cm = out["case_id_mismatch"]
check("case id mismatch: refused with CASE_ID_MISMATCH", cm["resultStatus"] == "error" and cm["error"]["code"] == "CASE_ID_MISMATCH")
check("case id mismatch: nothing written and case.json untouched", set(cm["files"]) == {"case.json"} and dev1_untouched("case_id_mismatch"))

# more cases beyond the eight
ao = files("audio_only")["analysis.json"]
check("audio case goes straight to STT, media analysis is unavailable, result ok", out["audio_only"]["resultStatus"] == "ok"
      and ao["mediaType"] == "audio" and ao["processingStatus"] == {"stt": "ok", "mediaAnalysis": "unavailable", "watsonx": "ok"}
      and ao["timestamps"][0]["timestampStatus"] == "available" and "audio_only_no_media_analysis" in ao["warnings"])
rc = files("media_analysis_failed_audio_recovered")["analysis.json"]
check("media analysis failure still lets STT and watsonx run on the recovered audio",
      out["media_analysis_failed_audio_recovered"]["resultStatus"] == "partial"
      and rc["processingStatus"] == {"stt": "ok", "mediaAnalysis": "failed", "watsonx": "ok"} and rc["severity"] == "high"
      and rc["errors"][0]["code"] == "MEDIA_UNREADABLE" and "audio_recovered_after_media_analysis_failed" in rc["warnings"])
check("case.json without mediaObject is recorded as a failed media stage", out["no_media_reference"]["resultStatus"] == "failed"
      and errors("no_media_reference")[0]["code"] == "MEDIA_REFERENCE_MISSING")

# D1, D2, D3, D5: end to end through the real pipeline, not just the pure functions above
check("a mediaObjectKey for a different case is refused end to end, the real file next to it is never read (D2)",
      out["media_key_wrong_case"]["resultStatus"] == "failed"
      and status("media_key_wrong_case") == {"stt": "unavailable", "mediaAnalysis": "failed", "watsonx": "unavailable"}
      and errors("media_key_wrong_case")[0]["code"] == "MEDIA_KEY_WRONG_CASE" and dev1_untouched("media_key_wrong_case"))
fs = files("filename_with_spaces")["analysis.json"]
check("a file name with spaces and punctuation resolves through the real store end to end (D3)",
      out["filename_with_spaces"]["resultStatus"] == "ok" and fs["severity"] == "high" and fs["mediaFile"] == "My Clip (Final v2).mp4")
lg = files("legacy_media_object")["analysis.json"]
check("the older mediaObject field still resolves a case end to end (D5, kept for backward compatibility)",
      out["legacy_media_object"]["resultStatus"] == "ok" and lg["mediaFile"] == "video.mp4" and lg["severity"] == "high")
uid = "CASE-3b9a4f2e-1c3d-4b5a-8f2e-1234567890ab"
ud = files("uuid_case_id")["analysis.json"]
check("a CASE-<uuid> style case id runs end to end and round trips through transcript.json and analysis.json (D1)",
      out["uuid_case_id"]["resultStatus"] == "ok" and ud["caseId"] == uid
      and files("uuid_case_id")["transcript.json"]["caseId"] == uid and ud["severity"] == "high")

store = LocalCaseStore(base)
check("bad case id refused", run_case("../x", store)["error"]["code"] == "INVALID_CASE_ID")
check("no case.json gives CASE_NOT_FOUND and writes nothing", run_case("CASE-404", store)["error"]["code"] == "CASE_NOT_FOUND"
      and not (base / "cases/CASE-404").exists())
(base / "cases/CASE-099").mkdir()
(base / "cases/CASE-099/case.json").write_text('{"title": "no id"}')
check("case.json without a caseId is refused", run_case("CASE-099", store)["error"]["code"] == "CASE_DATA_INVALID")


class NoWriteStore(LocalCaseStore):
    def save(self, case_id, filename, data):
        return {"status": "error", "error": {"code": "STORE_WRITE_FAILED", "message": "disk full"}}


r = run_case("CASE-001", NoWriteStore(base), work_dir=str(work), _media_fn=media_service(),
             _stt_fn=stt_service("ok"), _analyze_fn=chat_service("concerning"))
check("a save failure downgrades an ok run to partial and is reported", r["status"] == "partial"
      and r["saved"]["analysis"]["error"]["code"] == "STORE_WRITE_FAILED")

# mediaObject shapes and types
check("mediaObject as a string or an object with a key path", read_media_object("cases/CASE-001/clip.mp4") == ("clip.mp4", None)
      and read_media_object({"key": "cases/CASE-001/clip.mp4", "contentType": "video/mp4"}) == ("clip.mp4", "video/mp4")
      and read_media_object({"fileName": "a.wav"}) == ("a.wav", None))
check("mediaObject with nothing usable gives none", read_media_object(None) == (None, None)
      and read_media_object({}) == (None, None) and read_media_object("  ") == (None, None) and read_media_object(5) == (None, None))
check("media kinds", media_kind("a.mp4") == "video" and media_kind("a.wav") == "audio" and media_kind("a.mp3") == "audio"
      and media_kind("a.txt") is None and media_kind("a") is None and media_kind("a.webm") == "video"
      and media_kind("a.webm", "audio/webm") == "audio")
check("media kind trusts Dev1's coarse contentType directly, even over the extension (D2)",
      media_kind("anything", "video") == "video" and media_kind("anything", "audio") == "audio"
      and media_kind("a.mp4", "audio") == "audio")

# D2: resolve_media_reference, checked in order mediaObjectKey, fileName, the older mediaObject
CASE = "CASE-001"
check("mediaObjectKey is read first and its cases/<caseId>/ prefix is stripped (D2)",
      resolve_media_reference({"mediaObjectKey": "cases/CASE-001/My Clip.mp4", "contentType": "video"}, CASE)
      == ("My Clip.mp4", "video", None))
check("a mediaObjectKey naming a different case is refused, not silently used (D2)",
      resolve_media_reference({"mediaObjectKey": "cases/CASE-002/video.mp4", "contentType": "video"}, CASE)
      == (None, None, {"code": "MEDIA_KEY_WRONG_CASE", "message": "mediaObjectKey points at 'CASE-002', not CASE-001"}))
check("a mediaObjectKey with no cases/<id>/ prefix falls back to its basename (D2)",
      resolve_media_reference({"mediaObjectKey": "video.mp4", "contentType": "video"}, CASE) == ("video.mp4", "video", None))
check("fileName is used when there is no mediaObjectKey (D2)",
      resolve_media_reference({"fileName": "clip.mov", "contentType": "video"}, CASE) == ("clip.mov", "video", None))
check("the older mediaObject is used when neither mediaObjectKey nor fileName is present (D2)",
      resolve_media_reference({"mediaObject": {"key": "cases/CASE-001/old.mp4", "contentType": "video/mp4"}}, CASE)
      == ("old.mp4", "video/mp4", None))
check("contentType wins over mediaMimeType for the type hint (D2)",
      resolve_media_reference({"fileName": "a.mp4", "contentType": "video", "mediaMimeType": "video/mp4"}, CASE)[1] == "video")
check("mediaMimeType is used when there is no contentType (D2)",
      resolve_media_reference({"fileName": "a.mp4", "mediaMimeType": "video/mp4"}, CASE)[1] == "video/mp4")
check("nothing usable in case.json gives no reference and no error (D2)",
      resolve_media_reference({}, CASE) == (None, None, None)
      and resolve_media_reference({"mediaObjectKey": "  ", "fileName": "  "}, CASE) == (None, None, None))

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
