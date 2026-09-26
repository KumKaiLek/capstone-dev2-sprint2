"""Runs one case through media analysis, Speech to Text and watsonx.ai, then saves the two
case documents through the case store (local by default).
Usage: python run_pipeline.py <caseId>            fetches the stored video for the case
       python run_pipeline.py <video> <caseId>    uses a video file you give it
The caseId looks like CASE-001. Also saves outputs/pipeline_<caseId>.json as test evidence."""
import json
import sys
from pathlib import Path
from src.config import ConfigError
from src.media_source import default_media_source
from src.pipeline import run_case
from src.store import default_store

if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) not in (1, 2):
        raise SystemExit("Usage: python run_pipeline.py <caseId>   or   python run_pipeline.py <video> <caseId>")
    try:
        if len(args) == 1:
            out = run_case(args[0], source=default_media_source())
        else:
            out = run_case(args[1], media_path=args[0])
    except ConfigError as e:
        raise SystemExit(f"Setting problem, {e}")
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
