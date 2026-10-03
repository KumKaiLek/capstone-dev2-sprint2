"""Card 2, AI validation. Runs the V1-V6 cases from docs/TEST_PLAN.md live through the real
Speech to Text and watsonx.ai, saves each result to outputs/validation/<caseId>.json, and prints
a comparison table of expected (from the test plan) against actual. The expected values are
copied in from docs/TEST_PLAN.md, not computed, so changing an expectation means changing both
files. This only runs and records results; docs/AI_VALIDATION_REPORT.md is where each field gets
a correct/incorrect/uncertain verdict.
Usage: python run_validation.py"""
import json
from pathlib import Path

from src.config import ConfigError
from src.pipeline import run_case
from src.store import default_store

CASES = {
    "CASE-101": {"name": "V1 harmless", "expectSeverity": "low", "expectCategories": []},
    "CASE-102": {"name": "V2 harassment/threat", "expectSeverity": "high", "expectCategories": ["harassment", "violence"]},
    "CASE-103": {"name": "V3 one concerning line", "expectSeverity": "medium or high", "expectCategories": ["violence or harassment"]},
    "CASE-104": {"name": "V4 audio mild language", "expectSeverity": "low", "expectCategories": []},
    "CASE-105": {"name": "V5 silence, no speech", "expectSeverity": None, "expectCategories": []},
    "CASE-106": {"name": "V6 missing media", "expectSeverity": None, "expectCategories": []},
}

OUT = Path("outputs/validation")

if __name__ == "__main__":
    try:
        store = default_store()
    except ConfigError as e:
        raise SystemExit(f"Setting problem, {e}")

    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for case_id, info in CASES.items():
        result = run_case(case_id, store)
        (OUT / f"{case_id}.json").write_text(json.dumps(result, indent=2))
        if result["status"] == "error":
            actual = {"status": "error", "severity": None, "categories": None,
                      "transcript": None, "timestamps": None, "error": result["error"]}
        else:
            a, t = result["analysis"], result["transcript"]
            actual = {"status": result["status"], "severity": a["severity"], "categories": a["categories"],
                      "transcript": t.get("transcript"), "timestamps": a["timestamps"],
                      "processingStatus": a["processingStatus"], "errors": a["errors"]}
        rows.append((case_id, info, actual))
        print(f"{case_id} ({info['name']})")
        print(f"  expected severity={info['expectSeverity']!r} categories={info['expectCategories']!r}")
        print(f"  actual   severity={actual['severity']!r} categories={actual['categories']!r} status={actual['status']!r}")
        print(f"  transcript: {actual['transcript']!r}")
        print(f"  timestamps: {actual.get('timestamps')}")
        if actual["status"] in ("error", "failed", "partial"):
            print(f"  errors: {actual.get('errors') or actual.get('error')}")
        print()

    print(f"Saved {len(rows)} results to {OUT}/. See docs/TEST_PLAN.md for the full expected values "
          f"and docs/AI_VALIDATION_REPORT.md for the verdicts.")
