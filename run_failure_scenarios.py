"""Runs every simulated failure scenario (tests/simulated.py) through the real pipeline code with a
fake network, and saves each result to outputs/sprint3/failure/simulated/<scenario>.json. No IBM
call and no key needed. Case folders are built in a temporary directory, not under cases/.
Usage: python run_failure_scenarios.py
For real failures against IBM, force a timeout instead, for example
  STT_TIMEOUT=0.001 python run_pipeline.py CASE-001
  IAM_TIMEOUT=60 WATSONX_TIMEOUT=0.001 python run_pipeline.py CASE-001"""
import json
import tempfile
from pathlib import Path

from tests.simulated import run_scenario

FAILURES = ["stt_server_error", "stt_timeout", "watsonx_timeout", "iam_timeout", "watsonx_service_error",
            "truncated_output", "truncated_but_parseable", "malformed_watsonx_output", "malformed_json",
            "incomplete_json", "missing_values", "empty_values"]
OUT = Path("outputs/sprint3/failure/simulated")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp())
    for name in FAILURES:
        out = run_scenario(name, base, base / "work")
        out.pop("original_case_json")
        (OUT / f"{name}.json").write_text(json.dumps(out, indent=2))
        a = out["files"]["analysis.json"]
        codes = ", ".join(f"{e['stage']}:{e['code']}" for e in a["errors"])
        print(f"{out['caseId']} {name}: {out['resultStatus']} {codes} severity={a['severity']} "
              f"categories={a['categories']} timestamps={a['timestamps']}")
    print(f"\nSaved {len(FAILURES)} scenario outputs to {OUT}/")
