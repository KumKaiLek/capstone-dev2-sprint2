"""Result contract for the watsonx structured analysis.

Severity and category values are the agreed contract shared with Dev1.
If the Auditor console needs different values, change them here and re-run the tests.
"""

SEVERITIES = ["low", "medium", "high"]
CATEGORIES = [
    "hate_speech",
    "harassment",
    "violence",
    "self_harm",
    "sexual_content",
    "misinformation",
    "other",
]

# One line per category, given to watsonx.ai in the prompt so it classifies consistently (D4,
# Sprint 2 Week 3 stabilisation). Keep these short and behavioural, not examples.
CATEGORY_DEFINITIONS = {
    "hate_speech": "the speaker expresses hatred, contempt or dehumanisation toward a person or group "
                   "based on a trait such as race, religion, gender or sexual orientation",
    "harassment": "the speaker targets a specific person with abuse, insults, threats or unwanted aggressive contact",
    "violence": "the speaker describes, threatens or encourages physical harm against a person",
    "self_harm": "the speaker describes or encourages harming THEMSELVES",
    "sexual_content": "the speaker describes explicit sexual acts or sexualises a person",
    "misinformation": "the speaker states something false or misleading as if it were a verified fact",
    "other": "concerning content that does not fit any category above",
}

# Fields the model is allowed to return
ALLOWED_MODEL_FIELDS = {"caseId", "severity", "summary", "categories", "concerningSegments", "evidenceSegments"}

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
        "categories": f"list, may be empty when nothing applies, unique values from {CATEGORIES}. A category "
                      "the model returned with no valid evidenceSegments is dropped before this result is built",
        "concerningSegments": "list of 1-based STT segment numbers the model flagged, [] if none. "
                              "Never trusted as a time: code looks up the real start/end from STT",
        "evidenceSegments": "object mapping each category that survived into categories to the list of "
                            "1-based STT segment numbers that justify it",
        "advisory": "always true, set by code, not the model",
        "requiresHumanReview": "always true, set by code, not the model",
        "model": "model id used",
    },
    "warnings": "list of strings, e.g. stripped decision fields",
    "error": {"code": "string", "message": "string"},
}
