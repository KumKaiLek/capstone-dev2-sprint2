"""Finds the stored video for a case and makes it available as a local file.

Dev1 keeps one .mp4 per case at cases/<caseId>/<file> in COS. The local source reads the same
layout from disk. The COS source has not been run against a real bucket yet (no credentials).

fetch never raises. It returns {"status": "ok", "path": ...} or {"status": "error", "error": {...}}.
"""
from pathlib import Path

from .media import ALLOWED_EXT, MAX_MB
from .pipeline import valid_case_id
from .store import cos_client, local_dir, store_kind


def _error(code, message):
    return {"status": "error", "error": {"code": code, "message": message}}


def _pick(case_id, names):
    videos = sorted(n for n in names if Path(n).suffix.lower() in ALLOWED_EXT)
    if not videos:
        return None, _error("MEDIA_NOT_FOUND", f"No video is stored for {case_id}")
    if len(videos) > 1:
        return None, _error("MEDIA_AMBIGUOUS", f"More than one video is stored for {case_id}: {videos}")
    return videos[0], None


class LocalMediaSource:
    def __init__(self, base_dir="."):
        self.base = Path(base_dir)

    def fetch(self, case_id, dest_dir):
        if not valid_case_id(case_id):
            return _error("INVALID_CASE_ID", "caseId must look like CASE-001")
        folder = self.base / "cases" / case_id
        if not folder.is_dir():
            return _error("MEDIA_NOT_FOUND", f"No video is stored for {case_id}")
        name, err = _pick(case_id, [p.name for p in folder.iterdir() if p.is_file()])
        if err:
            return err
        return {"status": "ok", "path": str(folder / name), "source": "local"}


class CosMediaSource:
    """client is an S3 style client (ibm_boto3), passed in so tests can use a fake."""

    def __init__(self, bucket, client):
        self.bucket = bucket
        self.client = client

    def fetch(self, case_id, dest_dir):
        if not valid_case_id(case_id):
            return _error("INVALID_CASE_ID", "caseId must look like CASE-001")
        prefix = f"cases/{case_id}/"
        try:
            listing = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            sizes = {o["Key"][len(prefix):]: o.get("Size", 0) for o in listing.get("Contents", [])
                     if "/" not in o["Key"][len(prefix):]}
            name, err = _pick(case_id, sizes)
            if err:
                return err
            if sizes[name] > MAX_MB * 1024 * 1024:
                return _error("MEDIA_TOO_LARGE", f"The stored video is larger than {MAX_MB} MB")
            dest = Path(dest_dir)
            dest.mkdir(parents=True, exist_ok=True)
            out = dest / name
            body = self.client.get_object(Bucket=self.bucket, Key=prefix + name)["Body"]
            with open(out, "wb") as f:
                while True:
                    chunk = body.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception as e:
            return _error("MEDIA_READ_FAILED", f"Could not read the stored video ({type(e).__name__})")
        return {"status": "ok", "path": str(out), "source": "cos"}


def default_media_source():
    """Same CASE_STORE setting as the case store. Raises ConfigError for a bad or incomplete setting."""
    if store_kind() == "local":
        return LocalMediaSource(local_dir())
    client, bucket = cos_client()
    return CosMediaSource(bucket, client)
