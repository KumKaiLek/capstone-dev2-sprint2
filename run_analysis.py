"""Runs one synthetic sample through watsonx.ai and saves the result."""
import json
from pathlib import Path
from src.analysis import analyze

SAMPLE = {
    "caseId": "CASE-0001",
    "transcript": "this is a test message describing a synthetic scenario for the proof of concept",
    "media_context": {
        "sourceType": "synthetic_audio",
        "durationSeconds": 6.2,
        "incidentSegments": [{"startSec": 0.0, "endSec": 6.2, "label": "full clip"}],
    },
}

if __name__ == "__main__":
    out = analyze(SAMPLE["caseId"], SAMPLE["transcript"], SAMPLE["media_context"])
    print(json.dumps(out, indent=2))
    Path("outputs").mkdir(exist_ok=True)
    Path("outputs/sample_result.json").write_text(json.dumps(out, indent=2))
    print("\nSaved to outputs/sample_result.json")
