"""Case store. The files of a case live under cases/<caseId>/, the same layout as Dev1's COS bucket:
  case.json         Dev1's metadata for the case (names the media in mediaObject). Read only, never written here.
  <media file>      the audio or video that mediaObject points at
  transcript.json   written by us (Speech to Text)
  analysis.json     written by us (watsonx.ai)

CaseStore is the interface. LocalCaseStore keeps the files on disk. CosCaseStore is a stub for later.
save and load never raise. They return {"status": "ok", ...} or {"status": "error", "error": {...}}.
"""
import json
import os
import re
from pathlib import Path

from .config import ConfigError

CASE_ID_PATTERN = re.compile(r"^CASE-[A-Za-z0-9-]{3,64}$")
READ_ONLY_FILES = {"case.json"}
MAX_FILENAME_LENGTH = 150
CONTROL_CHARS = frozenset(chr(c) for c in list(range(0x20)) + [0x7F])


def valid_case_id(case_id):
    return isinstance(case_id, str) and bool(CASE_ID_PATTERN.match(case_id))


def valid_filename(filename):
    """A plain file name: spaces and normal punctuation are fine, since original file names from
    Dev1 can have both (D3, Sprint 2 Week 3 stabilisation). Still blocked: path separators, ..
    anywhere in the name, and control characters."""
    if not isinstance(filename, str) or not filename or filename.isspace():
        return False
    if len(filename) > MAX_FILENAME_LENGTH:
        return False
    if "/" in filename or "\\" in filename or ".." in filename:
        return False
    return not any(ch in CONTROL_CHARS for ch in filename)


def _error(code, message):
    return {"status": "error", "error": {"code": code, "message": message}}


class CaseStore:
    """Interface. filename is a plain file name inside the case folder, never a path."""

    def save(self, case_id, filename, data):
        raise NotImplementedError

    def load(self, case_id, filename):
        raise NotImplementedError

    def exists(self, case_id, filename):
        raise NotImplementedError

    def path(self, case_id, filename):
        """A local file path for the file (for ffmpeg and Speech to Text), or None if it is not there."""
        raise NotImplementedError


class LocalCaseStore(CaseStore):
    def __init__(self, base_dir="."):
        self.base = Path(base_dir).resolve()

    def _file(self, case_id, filename):
        if not valid_case_id(case_id) or not valid_filename(filename):
            return None
        return self.base / "cases" / case_id / filename

    def exists(self, case_id, filename):
        f = self._file(case_id, filename)
        return f is not None and f.is_file()

    def path(self, case_id, filename):
        return str(self._file(case_id, filename)) if self.exists(case_id, filename) else None

    def save(self, case_id, filename, data):
        if not valid_case_id(case_id):
            return _error("INVALID_CASE_ID", "caseId must look like CASE-001 or CASE-<uuid>, letters, digits and hyphens only")
        if not valid_filename(filename):
            return _error("INVALID_FILENAME", "filename must be a plain file name")
        if filename in READ_ONLY_FILES:
            return _error("READ_ONLY_FILE", f"{filename} belongs to Dev1 and is never written here")
        if isinstance(data, (dict, list)):
            if isinstance(data, dict) and "caseId" in data and data["caseId"] != case_id:
                return _error("INVALID_DOCUMENT", f"The document caseId does not match {case_id}")
            try:
                payload = json.dumps(data, indent=2).encode("utf-8")
            except (TypeError, ValueError):
                return _error("INVALID_DOCUMENT", "The document could not be turned into JSON")
        elif isinstance(data, str):
            payload = data.encode("utf-8")
        elif isinstance(data, bytes):
            payload = data
        else:
            return _error("INVALID_DOCUMENT", "data must be a dict, list, str or bytes")
        target = self._file(case_id, filename)
        tmp = target.with_name(target.name + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(payload)
            os.replace(tmp, target)
        except OSError as e:
            return _error("STORE_WRITE_FAILED", f"Could not write {filename} ({type(e).__name__})")
        return {"status": "ok", "caseId": case_id, "key": f"cases/{case_id}/{filename}"}

    def load(self, case_id, filename):
        if not valid_case_id(case_id):
            return _error("INVALID_CASE_ID", "caseId must look like CASE-001 or CASE-<uuid>, letters, digits and hyphens only")
        if not valid_filename(filename):
            return _error("INVALID_FILENAME", "filename must be a plain file name")
        target = self._file(case_id, filename)
        if not target.is_file():
            return _error("FILE_NOT_FOUND", f"cases/{case_id}/{filename} does not exist")
        try:
            raw = target.read_bytes()
        except OSError as e:
            return _error("STORE_READ_FAILED", f"Could not read {filename} ({type(e).__name__})")
        if filename.endswith(".json"):
            try:
                data = json.loads(raw.decode("utf-8"))
            except ValueError:
                return _error("CASE_DATA_INVALID", f"{filename} is not valid JSON")
        else:
            data = raw
        return {"status": "ok", "caseId": case_id, "filename": filename, "data": data}


class CosCaseStore(CaseStore):
    """TODO: read and write cases/<caseId>/<filename> in the COS bucket once Dev1 gives the
    credentials and confirms the layout. Not built. Every call returns NOT_IMPLEMENTED."""

    def _todo(self):
        return _error("NOT_IMPLEMENTED", "The COS store is not built yet, use CASE_STORE=local")

    def save(self, case_id, filename, data):
        return self._todo()

    def load(self, case_id, filename):
        return self._todo()

    def exists(self, case_id, filename):
        return False

    def path(self, case_id, filename):
        return None


def default_store():
    """CASE_STORE picks local (default) or cos. CASE_STORE_DIR is the folder that holds cases/."""
    kind = (os.getenv("CASE_STORE") or "local").strip().lower()
    if kind == "local":
        return LocalCaseStore(os.getenv("CASE_STORE_DIR") or ".")
    if kind == "cos":
        return CosCaseStore()
    raise ConfigError(f"CASE_STORE must be local or cos, not {kind}")
