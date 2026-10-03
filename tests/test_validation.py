"""Offline tests: no IBM call, no key needed. Run: python -m tests.test_validation"""
import json
from src.analysis import analyze

CASE = "CASE-0001"
GOOD = {"caseId": CASE, "severity": "low", "summary": "A neutral test message.", "categories": ["other"]}


def run(name, model_output, expect_status, expect_code=None, expect_warning=None):
    def fake(_messages):
        return model_output if isinstance(model_output, str) else json.dumps(model_output)

    out = analyze(CASE, "some transcript", {"sourceType": "synthetic"}, _chat_fn=fake)
    ok = out["status"] == expect_status
    if expect_code:
        ok = ok and out.get("error", {}).get("code") == expect_code
    if expect_warning:
        ok = ok and any(expect_warning in w for w in out.get("warnings", []))
    print(("PASS" if ok else "FAIL"), "-", name)
    return ok, out


results = []
results.append(run("valid output accepted", GOOD, "ok")[0])
ok, out = run("advisory flags set by code", GOOD, "ok")
results.append(ok and out["result"]["advisory"] is True and out["result"]["requiresHumanReview"] is True)
results.append(run("prose instead of JSON detected", "I think this is fine.", "error", "MALFORMED_OUTPUT")[0])
results.append(run("truncated JSON detected", '{"caseId": "CASE-0001", "sever', "error", "MALFORMED_OUTPUT")[0])
results.append(run("JSON in code fence tolerated + flagged", "```json\n" + json.dumps(GOOD) + "\n```", "ok", expect_warning="code_fence")[0])
results.append(run("wrong caseId rejected", {**GOOD, "caseId": "CASE-9999"}, "error", "INVALID_OUTPUT")[0])
results.append(run("bad severity rejected", {**GOOD, "severity": "extreme"}, "error", "INVALID_OUTPUT")[0])
results.append(run("empty summary rejected", {**GOOD, "summary": "  "}, "error", "INVALID_OUTPUT")[0])
results.append(run("unknown category rejected", {**GOOD, "categories": ["made_up"]}, "error", "INVALID_OUTPUT")[0])
results.append(run("missing categories rejected", {k: v for k, v in GOOD.items() if k != "categories"}, "error", "INVALID_OUTPUT")[0])
ok, out = run("decision field stripped", {**GOOD, "decision": "remove content"}, "ok", expect_warning="stripped_decision_field")
results.append(ok and "decision" not in out["result"])
results.append(run("extra field dropped", {**GOOD, "confidenceNote": "x"}, "ok", expect_warning="dropped_unexpected_field")[0])

ok, out = run("concerningSegments kept", {**GOOD, "concerningSegments": [2]}, "ok")
results.append(ok and out["result"]["concerningSegments"] == [2])
results.append(run("concerningSegments must be integers", {**GOOD, "concerningSegments": ["two"]}, "error", "INVALID_OUTPUT")[0])
results.append(run("concerningSegments must be a list", {**GOOD, "concerningSegments": 2}, "error", "INVALID_OUTPUT")[0])
ok, out = run("concerningSegments defaults to empty", GOOD, "ok")
results.append(ok and out["result"]["concerningSegments"] == [])

# D4 (Sprint 2 Week 3 stabilisation): a category needs evidenceSegments pointing at a real
# transcript segment, or it is dropped. Only applies to a segment-aware call.
SEGMENTS_3 = [{"text": "a"}, {"text": "b"}, {"text": "c"}]


def run_seg(name, model_output, expect_status, expect_code=None, expect_warning=None, segments=SEGMENTS_3):
    def fake(_messages):
        return model_output if isinstance(model_output, str) else json.dumps(model_output)

    out = analyze(CASE, "some transcript", {"sourceType": "synthetic"}, segments=segments, _chat_fn=fake)
    ok = out["status"] == expect_status
    if expect_code:
        ok = ok and out.get("error", {}).get("code") == expect_code
    if expect_warning:
        ok = ok and any(expect_warning in w for w in out.get("warnings", []))
    print(("PASS" if ok else "FAIL"), "-", name)
    return ok, out


ok, out = run_seg("D4: category with valid evidenceSegments is kept",
                   {**GOOD, "categories": ["harassment", "violence"], "evidenceSegments": {"harassment": [1], "violence": [2]}}, "ok")
results.append(ok and out["result"]["categories"] == ["harassment", "violence"]
               and out["result"]["evidenceSegments"] == {"harassment": [1], "violence": [2]})
ok, out = run_seg("D4: category with no evidenceSegments entry is dropped with a warning",
                   {**GOOD, "categories": ["harassment", "violence"], "evidenceSegments": {"harassment": [1]}}, "ok",
                   expect_warning="category_dropped_no_evidence:violence")
results.append(ok and out["result"]["categories"] == ["harassment"])
ok, out = run_seg("D4: evidence pointing outside the transcript is not valid evidence",
                   {**GOOD, "categories": ["harassment"], "evidenceSegments": {"harassment": [99]}}, "ok",
                   expect_warning="category_dropped_no_evidence:harassment")
results.append(ok and out["result"]["categories"] == [])
ok, out = run_seg("D4: evidenceSegments missing entirely drops every category",
                   {**GOOD, "categories": ["harassment", "violence"]}, "ok")
results.append(ok and out["result"]["categories"] == []
               and sum(1 for w in out["warnings"] if w.startswith("category_dropped_no_evidence:")) == 2)
ok, out = run_seg("D4: evidenceSegments of the wrong type is treated as missing, not a crash",
                   {**GOOD, "categories": ["harassment"], "evidenceSegments": ["harassment"]}, "ok",
                   expect_warning="category_dropped_no_evidence:harassment")
results.append(ok and out["result"]["categories"] == [])
ok, out = run_seg("D4: duplicate and out-of-range segment numbers are cleaned, the valid one kept",
                   {**GOOD, "categories": ["harassment"], "evidenceSegments": {"harassment": [2, 2, 99]}}, "ok")
results.append(ok and out["result"]["categories"] == ["harassment"] and out["result"]["evidenceSegments"] == {"harassment": [2]})
ok, out = run("D4: a legacy call with no segments keeps categories regardless of evidenceSegments", GOOD, "ok")
results.append(ok and out["result"]["categories"] == ["other"] and out["result"]["evidenceSegments"] == {})

seen = {}


def spy(messages):
    seen["m"] = messages
    return json.dumps(GOOD)


analyze(CASE, "t", {}, segments=[{"text": "hello"}, {"text": "bye"}], _chat_fn=spy)
system_p, user_p = seen["m"][0]["content"], seen["m"][1]["content"]
results.append("[1] hello" in user_p and "[2] bye" in user_p and "concerningSegments" in system_p)
print("PASS" if results[-1] else "FAIL", "- segments are numbered in the prompt when provided")
results.append("evidenceSegments" in system_p and "self_harm" in system_p and "THEMSELVES" in system_p)
print("PASS" if results[-1] else "FAIL", "- category definitions and the evidenceSegments instruction are in the prompt when segments are given (D4)")
analyze(CASE, "t", {}, _chat_fn=spy)
results.append("concerningSegments" not in seen["m"][0]["content"])
print("PASS" if results[-1] else "FAIL", "- no segment instruction when no segments are given")
results.append("evidenceSegments" not in seen["m"][0]["content"] and "self_harm" in seen["m"][0]["content"])
print("PASS" if results[-1] else "FAIL", "- category definitions are always in the prompt, but not the evidenceSegments instruction without segments (D4)")

r = analyze("", "text", {}, _chat_fn=lambda m: "{}")
results.append(r["error"]["code"] == "MISSING_INPUT"); print("PASS" if results[-1] else "FAIL", "- missing caseId handled")
r = analyze(CASE, "   ", {}, _chat_fn=lambda m: "{}")
results.append(r["error"]["code"] == "MISSING_INPUT"); print("PASS" if results[-1] else "FAIL", "- missing transcript handled")

seq = iter(["not json", json.dumps(GOOD)])
r = analyze(CASE, "t", {}, _chat_fn=lambda m: next(seq))
results.append(r["status"] == "ok" and "succeeded_on_retry" in r["warnings"]); print("PASS" if results[-1] else "FAIL", "- retry recovers from one bad output")

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
