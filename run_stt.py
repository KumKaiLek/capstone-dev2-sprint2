"""Runs Speech to Text on an approved synthetic audio file and saves the transcript contract.
Usage: python run_stt.py <audio file>"""
import json
import sys
from pathlib import Path
from src.stt import transcribe

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python run_stt.py <audio file>")
    out = transcribe(sys.argv[1])
    text = json.dumps(out, indent=2)
    print(text)
    Path("outputs").mkdir(exist_ok=True)
    path = Path(f"outputs/transcript_{Path(sys.argv[1]).stem}.json")
    path.write_text(text)
    print(f"\nSaved to {path}")
