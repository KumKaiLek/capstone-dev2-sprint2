"""Runs the video/media adapter and (optionally) watsonx.ai on a synthetic video.
Usage: python run_media.py <video> <caseId> ["transcript text"]
Without a transcript, the analysis step is skipped and the payload reports it as missing."""
import json
import sys
from pathlib import Path
from src.media import analyse_media, media_context_for_ai, build_backend_payload
from src.analysis import analyze

if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit('Usage: python run_media.py <video> <caseId> ["transcript text"]')
    video, case_id = sys.argv[1], sys.argv[2]
    transcript = sys.argv[3] if len(sys.argv) > 3 else None

    media_result = analyse_media(video)
    analysis_result = None
    if transcript and media_result["status"] == "ok":
        ctx = media_context_for_ai(media_result["media"])
        analysis_result = analyze(case_id, transcript, ctx)

    payload = build_backend_payload(case_id, media_result, analysis_result)
    text = json.dumps(payload, indent=2)
    print(text)
    Path("outputs").mkdir(exist_ok=True)
    out = Path(f"outputs/media_payload_{case_id}.json")
    out.write_text(text)
    print(f"\nSaved to {out}")
