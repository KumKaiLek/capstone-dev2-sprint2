"""Runs an already stored case N times and reports whether severity, categories and timestamps
matched on every run. Speech to Text and watsonx.ai can both vary between calls on unchanged
input even at temperature 0, so this is for checking how stable a given case actually is before
trusting a single run of it.
Usage: python run_repeat.py <caseId> N
The case must already exist at cases/<caseId>/ (see run_pipeline.py / seed_synthetic_case.py).
Each run overwrites that case's stored transcript.json and analysis.json with its own result, so
after this finishes the store holds whatever the LAST run produced, not necessarily the first."""
import json
import sys

from src.config import ConfigError
from src.pipeline import run_case
from src.store import default_store


def summarise(analysis_doc):
    return {"severity": analysis_doc.get("severity"), "categories": analysis_doc.get("categories"),
            "timestamps": analysis_doc.get("timestamps")}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python run_repeat.py <caseId> N")
    case_id, n_arg = sys.argv[1], sys.argv[2]
    if not n_arg.isdigit() or int(n_arg) < 1:
        raise SystemExit(f"N must be a whole number of 1 or more, not {n_arg!r}")
    n = int(n_arg)

    try:
        store = default_store()
    except ConfigError as e:
        raise SystemExit(f"Setting problem, {e}")

    runs = []
    for i in range(1, n + 1):
        result = run_case(case_id, store)
        if result["status"] == "error":
            raise SystemExit(f"run {i}: could not run the case, {result['error']['code']} {result['error']['message']}")
        summary = summarise(result["analysis"])
        runs.append(summary)
        print(f"run {i}: status={result['status']} severity={summary['severity']} "
              f"categories={summary['categories']} timestamps={summary['timestamps']}")

    matched = all(r == runs[0] for r in runs)
    distinct = {json.dumps(r, sort_keys=True) for r in runs}
    print()
    if matched:
        print(f"All {n} runs of {case_id} matched exactly on severity, categories and timestamps.")
    else:
        print(f"{case_id} did NOT match on every run: {len(distinct)} distinct results out of {n} runs.")
        for i, r in enumerate(runs, 1):
            print(f"  run {i}: {json.dumps(r, sort_keys=True)}")
    raise SystemExit(0 if matched else 1)
