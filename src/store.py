"""Case store: saves and loads the two case documents.

The keys match Dev1's COS layout so switching backends changes nothing else:
  cases/<caseId>/transcript.json
  cases/<caseId>/case.json

CASE_STORE=local (default) keeps them on disk under CASE_STORE_DIR (default: the project folder).
CASE_STORE=cos writes them to the COS bucket. That backend needs ibm-cos-sdk and the COS_* settings,
and it has not been run against a real bucket yet because the COS credentials are not available.

save and load never raise. They return {"status": "ok", ...} or {"status": "error", "error": {...}}.
"""
import json
import os
from pathlib import Path

from .config import get_setting, ConfigError
from .pipeline import valid_case_id

TRANSCRIPT_FILE = "transcript.json"
CASE_FILE = "case.json"


class NotFound(Exception):
    pass


def _error(code, message):
    return {"status": "error", "error": {"code": code, "message": message}}


def _key(case_id, name):
    return f"cases/{case_id}/{name}"


class LocalBackend:
    def __init__(self, base_dir="."):
        self.base = Path(base_dir).resolve()

    def _path(self, key):
        path = (self.base / key).resolve()
        if self.base not in path.parents:
            raise ValueError("key is outside the store folder")
        return path

    def put(self, key, text):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    def get(self, key):
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        return path.read_text(encoding="utf-8")


class CosBackend:
    """client is an S3 style client (ibm_boto3), passed in so tests can use a fake."""

    def __init__(self, bucket, client):
        self.bucket = bucket
        self.client = client

    def put(self, key, text):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=text.encode("utf-8"),
                               ContentType="application/json")

    def get(self, key):
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise NotFound(key)
            raise
        return obj["Body"].read().decode("utf-8")


class CaseStore:
    def __init__(self, backend):
        self.backend = backend

    def save(self, case_id, transcript_doc, case_doc):
        if not valid_case_id(case_id):
            return _error("INVALID_CASE_ID", "caseId must look like CASE-001")
        for name, doc in (("transcript", transcript_doc), ("case", case_doc)):
            if not isinstance(doc, dict):
                return _error("INVALID_DOCUMENT", f"The {name} document must be a JSON object")
            if doc.get("caseId") != case_id:
                return _error("INVALID_DOCUMENT", f"The {name} document caseId does not match {case_id}")
        try:
            texts = {TRANSCRIPT_FILE: json.dumps(transcript_doc, indent=2),
                     CASE_FILE: json.dumps(case_doc, indent=2)}
        except (TypeError, ValueError):
            return _error("INVALID_DOCUMENT", "A document could not be turned into JSON")
        keys = []
        try:
            for name, text in texts.items():
                self.backend.put(_key(case_id, name), text)
                keys.append(_key(case_id, name))
        except Exception as e:
            return _error("STORE_WRITE_FAILED", f"Could not write the case ({type(e).__name__}), saved so far: {keys or 'nothing'}")
        return {"status": "ok", "caseId": case_id, "keys": keys}

    def load(self, case_id):
        if not valid_case_id(case_id):
            return _error("INVALID_CASE_ID", "caseId must look like CASE-001")
        docs = {}
        for name in (CASE_FILE, TRANSCRIPT_FILE):
            try:
                text = self.backend.get(_key(case_id, name))
            except NotFound:
                if name == CASE_FILE:
                    return _error("CASE_NOT_FOUND", f"No stored case for {case_id}")
                docs[name] = None
                continue
            except Exception as e:
                return _error("STORE_READ_FAILED", f"Could not read the case ({type(e).__name__})")
            try:
                doc = json.loads(text)
            except ValueError:
                return _error("CASE_DATA_INVALID", f"{name} for {case_id} is not valid JSON")
            if not isinstance(doc, dict) or doc.get("caseId") != case_id:
                return _error("CASE_DATA_INVALID", f"{name} does not belong to {case_id}")
            docs[name] = doc
        return {"status": "ok", "caseId": case_id, "case": docs[CASE_FILE], "transcript": docs[TRANSCRIPT_FILE]}


def store_kind():
    """CASE_STORE picks local or cos. Raises ConfigError for anything else."""
    kind = (os.getenv("CASE_STORE") or "local").strip().lower()
    if kind not in ("local", "cos"):
        raise ConfigError(f"CASE_STORE must be local or cos, not {kind}")
    return kind


def local_dir():
    return os.getenv("CASE_STORE_DIR") or "."


def cos_client():
    """Returns (client, bucket) from the COS_* settings. Raises ConfigError if incomplete."""
    api_key = get_setting("COS_API_KEY")
    instance = get_setting("COS_INSTANCE_CRN")
    endpoint = get_setting("COS_ENDPOINT")
    bucket = get_setting("COS_BUCKET")
    try:
        import ibm_boto3
        from ibm_botocore.client import Config
    except ImportError:
        raise ConfigError("CASE_STORE=cos needs the ibm-cos-sdk package (pip install ibm-cos-sdk)")
    client = ibm_boto3.client("s3", ibm_api_key_id=api_key, ibm_service_instance_id=instance,
                              config=Config(signature_version="oauth"), endpoint_url=endpoint)
    return client, bucket


def default_store():
    """Backend chosen by CASE_STORE. Raises ConfigError for a bad or incomplete setting."""
    if store_kind() == "local":
        return CaseStore(LocalBackend(local_dir()))
    client, bucket = cos_client()
    return CaseStore(CosBackend(bucket, client))
