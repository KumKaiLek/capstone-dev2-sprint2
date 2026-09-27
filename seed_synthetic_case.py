"""Creates synthetic cases under cases/ (a stand in for Dev1's case.json plus media), runs the pipeline on
each scenario and saves the output of each one under outputs/pipeline/.
Usage: python seed_synthetic_case.py           simulated Speech to Text and watsonx.ai, no keys needed
       python seed_synthetic_case.py --live    CASE-001 uses the real IBM services
CASE-001 uses samples/synthetic_concerning_video.mp4 and ffmpeg when they are available.
Only case folders whose case.json is marked synthetic are touched."""
import json
import shutil
import sys
from pathlib import Path
from tests.simulated import SCENARIOS, run_scenario

CLIP = Path("samples/synthetic_concerning_video.mp4")
OUT = Path("outputs/pipeline")

if __name__ == "__main__":
    live = "--live" in sys.argv[1:]
    real_media = CLIP.is_file() and shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    OUT.mkdir(parents=True, exist_ok=True)
    for name in SCENARIOS:
        out = run_scenario(name, ".", "outputs/media", clip=CLIP if CLIP.is_file() else None,
                           real_media=real_media, live=live)
        out.pop("original_case_json")
        (OUT / f"{name}.json").write_text(json.dumps(out, indent=2))
        analysis = out["files"].get("analysis.json", {})
        print(f"{out['caseId']} {name}: {out['resultStatus']} {analysis.get('processingStatus', '')}")
    print(f"\nSaved {len(SCENARIOS)} scenario outputs to {OUT}/")
