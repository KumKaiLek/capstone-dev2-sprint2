"""Card 3, AI validation. Runs each case N times through the real pipeline (real Speech to Text and
watsonx.ai) and reports, per case, whether severity, categories and timestamps were identical on
every run (exact equality), whether the summary passed the summary rules from run_repeat.py on
every run, and whether caseId matched in case.json, transcript.json and analysis.json on every run.
Usage: python run_repeatability.py [N]      N defaults to 5
Cases are V1 to V6 from docs/TEST_PLAN.md, already stored under cases/, plus one forced failure:
CASE-101 again with STT_TIMEOUT=0.001, so Speech to Text times out for real on every run.
Raw output of every run goes to outputs/sprint3/repeatability/<label>/run<i>.json, and the per case
results to outputs/sprint3/repeatability/results.json. Exit code 0 only if every case was stable."""
import json
import os
import sys
from pathlib import Path

from run_repeat import check_summary_rules
from src.config import ConfigError
from src.pipeline import run_case
from src.store import default_store

CASES = [
    # (label, caseId, environment overrides for this case only)
    ("V1_CASE-101", "CASE-101", {}),
    ("V2_CASE-102", "CASE-102", {}),
    ("V3_CASE-103", "CASE-103", {}),
    ("V4_CASE-104", "CASE-104", {}),
    ("V5_CASE-105_no_speech", "CASE-105", {}),
    ("V6_CASE-106_missing_media", "CASE-106", {}),
    ("FORCED_stt_timeout_CASE-101", "CASE-101", {"STT_TIMEOUT": "0.001"}),
]
OUT = Path("outputs/sprint3/repeatability")


def with_env(overrides, fn):
    old = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        return fn()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def case_id_linkage(store, case_id, result):
    """caseId as stored in case.json, transcript.json and analysis.json, and in the returned result."""
    ids = {"result": result.get("caseId")}
    for name in ("case.json", "transcript.json", "analysis.json"):
        loaded = store.load(case_id, name)
        ids[name] = loaded["data"].get("caseId") if loaded["status"] == "ok" else f"<{loaded['error']['code']}>"
    return ids, all(v == case_id for v in ids.values())


def summary_ok(summary, transcript):
    """run_repeat.py's summary rules. A failed run must have no summary at all."""
    if summary is None:
        return None
    rules = check_summary_rules(summary, transcript or "")
    rules["passed"] = rules["sentenceCountOk"] and rules["lengthOk"] and not rules["neutralWordingFlags"]
    return rules


def run_one(store, label, case_id, overrides, n):
    folder = OUT / label
    folder.mkdir(parents=True, exist_ok=True)
    runs = []
    for i in range(1, n + 1):
        result = with_env(overrides, lambda: run_case(case_id, store))
        if result["status"] == "error":
            record = {"status": "error", "error": result["error"], "caseIds": {}, "caseIdLinked": False}
        else:
            a, t = result["analysis"], result["transcript"]
            ids, linked = case_id_linkage(store, case_id, result)
            record = {"status": result["status"], "severity": a["severity"], "categories": a["categories"],
                      "timestamps": a["timestamps"], "summary": a["summary"],
                      "summaryRules": summary_ok(a["summary"], t.get("transcript")),
                      "processingStatus": a["processingStatus"],
                      "errorCodes": [f"{e['stage']}:{e['code']}" for e in a["errors"]],
                      "caseIds": ids, "caseIdLinked": linked}
        (folder / f"run{i}.json").write_text(json.dumps({"overrides": overrides, "record": record,
                                                          "result": result}, indent=2))
        runs.append(record)

    def same(key):
        return all(r.get(key) == runs[0].get(key) for r in runs)

    rules = [r.get("summaryRules") for r in runs]
    if all(x is None for x in rules):
        summary_check = "no summary on any run (correct for a failed stage)"
        summary_pass = all(r.get("summary") is None for r in runs)
    else:
        summary_pass = all(x is not None and x["passed"] for x in rules)
        summary_check = "rules passed on every run" if summary_pass else "rules NOT passed on every run"
    return {
        "label": label, "caseId": case_id, "overrides": overrides, "runs": n,
        "severityIdentical": same("severity"), "categoriesIdentical": same("categories"),
        "timestampsIdentical": same("timestamps"), "statusIdentical": same("status") and same("errorCodes"),
        "summaryRulesPassed": summary_pass, "summaryCheck": summary_check,
        "distinctSummaryWordings": len({r.get("summary") for r in runs}),
        "caseIdLinkedEveryRun": all(r["caseIdLinked"] for r in runs),
        "values": [{k: r.get(k) for k in ("status", "severity", "categories", "timestamps", "errorCodes")} for r in runs],
    }


if __name__ == "__main__":
    n_arg = sys.argv[1] if len(sys.argv) > 1 else "5"
    if not n_arg.isdigit() or int(n_arg) < 1:
        raise SystemExit(f"N must be a whole number of 1 or more, not {n_arg!r}")
    n = int(n_arg)
    try:
        store = default_store()
    except ConfigError as e:
        raise SystemExit(f"Setting problem, {e}")

    OUT.mkdir(parents=True, exist_ok=True)
    report = [run_one(store, label, case_id, overrides, n) for label, case_id, overrides in CASES]
    (OUT / "results.json").write_text(json.dumps(report, indent=2))

    stable = True
    for r in report:
        flags = {k: r[k] for k in ("severityIdentical", "categoriesIdentical", "timestampsIdentical",
                                   "statusIdentical", "summaryRulesPassed", "caseIdLinkedEveryRun")}
        ok = all(flags.values())
        stable = stable and ok
        v = r["values"][0]
        print(f"{r['label']}: {'STABLE' if ok else 'NOT STABLE'} over {r['runs']} runs")
        print(f"  severity identical={r['severityIdentical']} categories identical={r['categoriesIdentical']} "
              f"timestamps identical={r['timestampsIdentical']} status and error codes identical={r['statusIdentical']}")
        print(f"  summary: {r['summaryCheck']}, {r['distinctSummaryWordings']} distinct wording(s); "
              f"caseId linked in case.json, transcript.json, analysis.json on every run={r['caseIdLinkedEveryRun']}")
        print(f"  run 1: status={v['status']} severity={v['severity']} categories={v['categories']} "
              f"timestamps={[(t['start'], t['end'], t['timestampStatus']) for t in v['timestamps'] or []]} "
              f"errors={v['errorCodes']}")
        if not ok:
            for i, x in enumerate(r["values"], 1):
                print(f"  run {i}: {json.dumps(x, sort_keys=True)}")
    print(f"\nSaved raw runs and results.json to {OUT}/")
    raise SystemExit(0 if stable else 1)
