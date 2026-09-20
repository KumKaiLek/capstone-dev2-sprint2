"""Result contract for the watsonx structured analysis.

NOTE: SEVERITIES and CATEGORIES are placeholders. Replace them with the exact
values from the Task 9 contract so Dev1's Auditor console matches.
"""

SEVERITIES = ["low", "medium", "high", "critical"]
CATEGORIES = [
    "hate_speech",
    "harassment",
    "violence",
    "self_harm",
    "sexual_content",
    "misinformation",
    "other",
]

# Fields the model is allowed to return
ALLOWED_MODEL_FIELDS = {"caseId", "severity", "summary", "categories"}

# Anything that looks like a moderation decision is stripped and flagged
FORBIDDEN_KEYS = {
    "decision", "moderationdecision", "finaldecision", "action", "verdict",
    "remove", "takedown", "ban", "enforcement", "outcome",
}

MAX_SUMMARY_CHARS = 1000

# Documented contract (this is what goes in the Master Document and to Dev1)
RESULT_CONTRACT = {
    "status": "ok | error",
    "result": {
        "caseId": "string, must equal the caseId sent in",
        "severity": f"one of {SEVERITIES}",
        "summary": f"non-empty string, max {MAX_SUMMARY_CHARS} chars",
        "categories": f"list, may be empty when nothing applies, unique values from {CATEGORIES}",
        "advisory": "always true, set by code, not the model",
        "requiresHumanReview": "always true, set by code, not the model",
        "model": "model id used",
    },
    "warnings": "list of strings, e.g. stripped decision fields",
    "error": {"code": "string", "message": "string"},
}
