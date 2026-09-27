"""Loads the stored results of a case, the way an Auditor screen would.
Usage: python run_load.py <caseId>"""
import json
import sys
from src.config import ConfigError
from src.store import default_store

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python run_load.py <caseId>")
    try:
        store = default_store()
    except ConfigError as e:
        raise SystemExit(f"Setting problem, {e}")
    out = {name: store.load(sys.argv[1], f"{name}.json") for name in ("analysis", "transcript")}
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if out["analysis"]["status"] == "ok" else 1)
