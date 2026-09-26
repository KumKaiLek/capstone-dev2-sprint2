"""Loads a stored case back from the case store, the way an Auditor screen would.
Usage: python run_load.py <caseId>"""
import json
import sys
from src.config import ConfigError
from src.store import default_store

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python run_load.py <caseId>")
    try:
        out = default_store().load(sys.argv[1])
    except ConfigError as e:
        out = {"status": "error", "error": {"code": "CONFIG_ERROR", "message": str(e)}}
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if out["status"] == "ok" else 1)
