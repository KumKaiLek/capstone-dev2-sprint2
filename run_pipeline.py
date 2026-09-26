"""Runs one stored video through media analysis, Speech to Text and watsonx.ai,
then saves the two case documents through the case store (local by default).
Usage: python run_pipeline.py <video> <caseId>     (caseId looks like CASE-001)
Also saves outputs/pipeline_<caseId>.json as test evidence."""
import json
import sys
from pathlib import Path
from src.config import ConfigError
from src.pipeline import run_case
from src.store import default_store

if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python run_pipeline.py <video> <caseId>")
    out = run_case(sys.argv[2], sys.argv[1])
    text = json.dumps(out, indent=2)
    print(text)
    if out["status"] == "error":
        raise SystemExit(1)

    try:
        saved = default_store().save(out["caseId"], out["transcript"], out["case"])
    except ConfigError as e:
        saved = {"status": "error", "error": {"code": "CONFIG_ERROR", "message": str(e)}}
    print("\nStore result:", json.dumps(saved))

    Path("outputs").mkdir(exist_ok=True)
    path = Path(f"outputs/pipeline_{out['caseId']}.json")
    path.write_text(text)
    print(f"Saved to {path}")
