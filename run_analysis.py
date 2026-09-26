"""Runs a synthetic sample through watsonx.ai and saves the result.
Usage: python run_analysis.py [harmless|concerning]"""
import json
import sys
from pathlib import Path
from src.analysis import analyze

SAMPLES = {
    "harmless": {
        "caseId": "CASE-0001",
        "transcript": "this is a test message describing a synthetic scenario for the proof of concept",
        "media_context": {
            "sourceType": "synthetic_audio",
            "durationSeconds": 6.2,
            "sceneSegments": [{"startSec": 0.0, "endSec": 6.2, "label": "full clip"}],
        },
    },
    "concerning": {
        "caseId": "CASE-0002",
        "transcript": "synthetic test script: you are worthless and everyone hates you, I know where you live and I will make you regret it",
        "media_context": {
            "sourceType": "synthetic_audio",
            "durationSeconds": 7.0,
            "sceneSegments": [{"startSec": 0.0, "endSec": 7.0, "label": "full clip"}],
        },
    },
}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "harmless"
    if name not in SAMPLES:
        raise SystemExit(f"Unknown sample '{name}'. Choose: {', '.join(SAMPLES)}")
    s = SAMPLES[name]
    out = analyze(s["caseId"], s["transcript"], s["media_context"])
    print(json.dumps(out, indent=2))
    Path("outputs").mkdir(exist_ok=True)
    path = Path(f"outputs/sample_{name}.json")
    path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved to {path}")