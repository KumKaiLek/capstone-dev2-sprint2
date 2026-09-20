"""watsonx.ai structured analysis: transcript + media context -> validated,
advisory-only result. Uses the supported /ml/v1/text/chat endpoint."""
import json
import re
import requests

from .config import watsonx_settings, ConfigError
from .schemas import (
    SEVERITIES, CATEGORIES, ALLOWED_MODEL_FIELDS, FORBIDDEN_KEYS, MAX_SUMMARY_CHARS,
)

IAM_URL = "https://iam.cloud.ibm.com/identity/token"
API_VERSION = "2025-02-11"
TIMEOUT = 60

SYSTEM_PROMPT = f"""You are an assistant that helps a human content-safety auditor.
You do NOT make moderation decisions. You only describe and classify.
Return ONLY one JSON object, no prose, no code fences, with exactly these keys:
  "caseId": copy the caseId you are given, unchanged
  "severity": one of {SEVERITIES}
  "summary": 1 to 3 neutral sentences describing what the content contains
  "categories": a list with values only from {CATEGORIES}
Never include keys such as decision, action, verdict, remove or ban."""


class AnalysisError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def get_token(api_key):
    try:
        r = requests.post(
            IAM_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise AnalysisError("NETWORK_ERROR", f"Could not reach IBM IAM: {type(e).__name__}")
    if r.status_code != 200:
        raise AnalysisError("AUTH_FAILED", f"IAM token request failed with HTTP {r.status_code}")
    return r.json()["access_token"]


def build_messages(case_id, transcript, media_context):
    user = (
        f"caseId: {case_id}\n"
        f"transcript: {transcript}\n"
        f"media_context: {json.dumps(media_context)}\n"
        "Return the JSON object now."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def call_chat(settings, token, messages):
    url = f"{settings['url']}/ml/v1/text/chat?version={API_VERSION}"
    body = {
        "model_id": settings["model_id"],
        "project_id": settings["project_id"],
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0,
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise AnalysisError("NETWORK_ERROR", f"Could not reach watsonx.ai: {type(e).__name__}")
    if r.status_code in (401, 403):
        raise AnalysisError("AUTH_OR_PROJECT_ACCESS", f"watsonx.ai returned HTTP {r.status_code} (check key, project ID, collaborator access)")
    if r.status_code != 200:
        raise AnalysisError("SERVICE_ERROR", f"watsonx.ai returned HTTP {r.status_code}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise AnalysisError("MALFORMED_OUTPUT", "watsonx.ai response had no message content")


def extract_json(text):
    """Returns (object, warnings). Raises MALFORMED_OUTPUT if no JSON object found."""
    warnings = []
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
        warnings.append("output_wrapped_in_code_fence")
    try:
        return json.loads(text), warnings
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            warnings.append("json_extracted_from_surrounding_text")
            return obj, warnings
        except json.JSONDecodeError:
            pass
    raise AnalysisError("MALFORMED_OUTPUT", "Model output was not valid JSON")


def validate_result(obj, case_id, model_id="unknown"):
    """Returns (clean_result, warnings). Raises INVALID_OUTPUT with all problems listed."""
    warnings = []
    if not isinstance(obj, dict):
        raise AnalysisError("INVALID_OUTPUT", "Result is not a JSON object")

    # Strip anything that looks like a moderation decision
    for key in list(obj.keys()):
        if key.lower() in FORBIDDEN_KEYS:
            del obj[key]
            warnings.append(f"stripped_decision_field:{key}")

    problems = []
    if obj.get("caseId") != case_id:
        problems.append("caseId missing or does not match the input caseId")

    if obj.get("severity") not in SEVERITIES:
        problems.append(f"severity must be one of {SEVERITIES}")

    summary = obj.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("summary must be a non-empty string")
    elif len(summary) > MAX_SUMMARY_CHARS:
        problems.append(f"summary longer than {MAX_SUMMARY_CHARS} chars")

    cats = obj.get("categories")
    if not isinstance(cats, list):
        problems.append("categories must be a list (empty if nothing applies)")
    else:
        bad = [c for c in cats if c not in CATEGORIES]
        if bad:
            problems.append(f"categories contain unknown values: {bad}")
        if len(set(map(str, cats))) != len(cats):
            problems.append("categories contain duplicates")

    if problems:
        raise AnalysisError("INVALID_OUTPUT", "; ".join(problems))

    for key in obj:
        if key not in ALLOWED_MODEL_FIELDS:
            warnings.append(f"dropped_unexpected_field:{key}")

    clean = {
        "caseId": obj["caseId"],
        "severity": obj["severity"],
        "summary": obj["summary"].strip(),
        "categories": obj["categories"],
        # Set by code, never trusted from the model
        "advisory": True,
        "requiresHumanReview": True,
        "model": model_id,
    }
    return clean, warnings


def analyze(case_id, transcript, media_context, _chat_fn=None):
    """Never raises. Returns {"status": "ok", ...} or {"status": "error", ...}.
    _chat_fn lets tests inject a fake model response without calling IBM."""
    if not case_id or not isinstance(case_id, str):
        return {"status": "error", "error": {"code": "MISSING_INPUT", "message": "caseId is required"}}
    if not transcript or not str(transcript).strip():
        return {"status": "error", "error": {"code": "MISSING_INPUT", "message": "transcript is required"}}
    media_context = media_context or {}

    try:
        settings = watsonx_settings() if _chat_fn is None else {"model_id": "test-model"}
        messages = build_messages(case_id, transcript, media_context)
        if _chat_fn is None:
            token = get_token(settings["api_key"])
            chat = lambda: call_chat(settings, token, messages)
        else:
            chat = lambda: _chat_fn(messages)

        last_error = None
        for attempt in (1, 2):  # one retry on malformed or invalid output
            try:
                raw = chat()
                obj, warnings = extract_json(raw)
                clean, more = validate_result(obj, case_id, settings["model_id"])
                warnings += more
                if attempt == 2:
                    warnings.append("succeeded_on_retry")
                return {"status": "ok", "result": clean, "warnings": warnings}
            except AnalysisError as e:
                last_error = e
                if e.code not in ("MALFORMED_OUTPUT", "INVALID_OUTPUT"):
                    raise
        raise last_error
    except ConfigError as e:
        return {"status": "error", "error": {"code": "CONFIG_ERROR", "message": str(e)}}
    except AnalysisError as e:
        return {"status": "error", "error": {"code": e.code, "message": e.message}}
