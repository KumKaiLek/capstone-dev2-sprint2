"""Runs one case through media analysis, Speech to Text and watsonx.ai.
Usage: python run_pipeline.py <caseId>       (caseId looks like CASE-001)
Reads cases/<caseId>/case.json (Dev1's file, never changed), finds the media it names, and writes
cases/<caseId>/transcript.json and cases/<caseId>/analysis.json. CASE_STORE=local is the default."""
import json
import sys
from src.config import ConfigError
from src.pipeline import run_case
from src.store import default_store

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python run_pipeline.py <caseId>")
    try:
        out = run_case(sys.argv[1], default_store())
    except ConfigError as e:
        raise SystemExit(f"Setting problem, {e}")
    print(json.dumps(out, indent=2))
    raise SystemExit(1 if out["status"] == "error" else 0)
