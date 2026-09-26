"""Runs one stored video through media analysis, Speech to Text and watsonx.ai.
Usage: python run_pipeline.py <video> <caseId>     (caseId looks like CASE-001)
Saves outputs/pipeline_<caseId>.json with the transcript and case documents."""
import json
import sys
from pathlib import Path
from src.pipeline import run_case

if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python run_pipeline.py <video> <caseId>")
    out = run_case(sys.argv[2], sys.argv[1])
    text = json.dumps(out, indent=2)
    print(text)
    if out["status"] == "error":
        raise SystemExit(1)
    Path("outputs").mkdir(exist_ok=True)
    path = Path(f"outputs/pipeline_{out['caseId']}.json")
    path.write_text(text)
    print(f"\nSaved to {path}")
