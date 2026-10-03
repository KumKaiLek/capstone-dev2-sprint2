"""Runs an already stored case N times and reports whether severity, categories, timestamps and
summary wording matched on every run. Speech to Text and watsonx.ai can both vary between calls
on unchanged input even at temperature 0, so this is for checking how stable a given case
actually is before trusting a single run of it.
Usage: python run_repeat.py <caseId> N
The case must already exist at cases/<caseId>/ (see run_pipeline.py / seed_synthetic_case.py).
Each run overwrites that case's stored transcript.json and analysis.json with its own result, so
after this finishes the store holds whatever the LAST run produced, not necessarily the first.

Summary rule checks (Card 1, "summary output behaviour checked") are best effort, not a proof of
correctness: sentence count and length are exact, the other two are heuristics printed as flags
for a human to glance at, not a pass/fail.
  - 1 to 3 sentences, and under the schema's MAX_SUMMARY_CHARS: exact checks.
  - neutral wording: flagged if the summary contains a recommendation/decision style phrase
    (the system prompt already asks for neutral, descriptive wording; this is a check, not a fix).
  - describes only what is in the transcript: flagged if the summary names a capitalised word
    that does not appear anywhere in the transcript. A flag is not proof of a fabricated detail,
    and no flag is not proof there isn't one; a human still has to read the summary to be sure.
Severity, categories and timestamps are still compared with exact equality, unchanged from
before. Summary wording is reported separately: identical wording across runs is reported as
that; different wording is reported honestly as different wording, not as a mismatch, and is
only described as "likely the same content, differently worded" when severity and categories
(already an exact match check) agree on every run, since that is the one thing here that is
actually verified rather than guessed."""
import json
import re
import sys

from src.config import ConfigError
from src.pipeline import run_case
from src.schemas import MAX_SUMMARY_CHARS
from src.store import default_store

NON_NEUTRAL_PHRASES = [
    "should be removed", "should be deleted", "should be banned", "should be blocked",
    "should be suspended", "should be reported", "must be removed", "must be deleted",
    "must be banned", "needs to be removed", "needs to be deleted", "i recommend",
    "we recommend", "recommend that", "take down", "taken down", "ban this", "delete this",
    "remove this", "report this user", "action required", "this user should",
]
STOPWORDS = {"the", "a", "an", "this", "that", "it", "and", "or", "of", "in", "on", "to", "is", "was"}


def count_sentences(text):
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()])


def neutral_wording_flags(summary):
    low = summary.lower()
    return [p for p in NON_NEUTRAL_PHRASES if p in low]


def unverified_detail_flags(summary, transcript):
    """Capitalised words in the summary that are not sentence-initial and do not appear anywhere
    in the transcript. A heuristic nudge to read the summary, not a verdict."""
    transcript_low = (transcript or "").lower()
    sentence_starts = {s.strip().split()[0] for s in re.split(r"(?<=[.!?])\s+", summary.strip()) if s.strip().split()}
    flags = []
    for word in re.findall(r"\b[A-Z][a-zA-Z]+\b", summary):
        if word in sentence_starts or word.lower() in transcript_low:
            continue
        flags.append(word)
    return sorted(set(flags))


def check_summary_rules(summary, transcript):
    sentences = count_sentences(summary)
    return {
        "sentenceCount": sentences,
        "sentenceCountOk": 1 <= sentences <= 3,
        "length": len(summary),
        "lengthOk": len(summary) <= MAX_SUMMARY_CHARS,
        "neutralWordingFlags": neutral_wording_flags(summary),
        "possibleUnverifiedDetails": unverified_detail_flags(summary, transcript),
    }


def word_overlap(a, b):
    """Rough, approximate similarity: the fraction of a's non-trivial words that also appear in
    b. Supporting evidence only, not a semantic equivalence check."""
    wa = {w for w in re.findall(r"[a-z']+", a.lower()) if w not in STOPWORDS}
    wb = {w for w in re.findall(r"[a-z']+", b.lower()) if w not in STOPWORDS}
    if not wa:
        return 1.0
    return len(wa & wb) / len(wa)


def summarise(analysis_doc):
    return {"severity": analysis_doc.get("severity"), "categories": analysis_doc.get("categories"),
            "timestamps": analysis_doc.get("timestamps")}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python run_repeat.py <caseId> N")
    case_id, n_arg = sys.argv[1], sys.argv[2]
    if not n_arg.isdigit() or int(n_arg) < 1:
        raise SystemExit(f"N must be a whole number of 1 or more, not {n_arg!r}")
    n = int(n_arg)

    try:
        store = default_store()
    except ConfigError as e:
        raise SystemExit(f"Setting problem, {e}")

    runs, summaries = [], []
    for i in range(1, n + 1):
        result = run_case(case_id, store)
        if result["status"] == "error":
            raise SystemExit(f"run {i}: could not run the case, {result['error']['code']} {result['error']['message']}")
        key_fields = summarise(result["analysis"])
        runs.append(key_fields)
        summary_text = result["analysis"].get("summary") or ""
        transcript_text = result["transcript"].get("transcript") or ""
        summaries.append(summary_text)
        rules = check_summary_rules(summary_text, transcript_text)
        print(f"run {i}: status={result['status']} severity={key_fields['severity']} "
              f"categories={key_fields['categories']} timestamps={key_fields['timestamps']}")
        print(f"  summary: {summary_text!r}")
        print(f"  summary rules: sentences={rules['sentenceCount']} "
              f"({'ok' if rules['sentenceCountOk'] else 'OUT OF 1-3 RANGE'}), "
              f"length={rules['length']}/{MAX_SUMMARY_CHARS} "
              f"({'ok' if rules['lengthOk'] else 'OVER LIMIT'}), "
              f"neutral wording flags={rules['neutralWordingFlags'] or 'none'}, "
              f"possible unverified details={rules['possibleUnverifiedDetails'] or 'none'}")

    matched = all(r == runs[0] for r in runs)
    distinct = {json.dumps(r, sort_keys=True) for r in runs}
    print()
    if matched:
        print(f"All {n} runs of {case_id} matched exactly on severity, categories and timestamps.")
    else:
        print(f"{case_id} did NOT match on every run: {len(distinct)} distinct results out of {n} runs.")
        for i, r in enumerate(runs, 1):
            print(f"  run {i}: {json.dumps(r, sort_keys=True)}")

    distinct_summaries = set(summaries)
    print()
    if len(distinct_summaries) == 1:
        print(f"Summary wording was identical across all {n} runs.")
    else:
        overlaps = [round(100 * word_overlap(s, summaries[0])) for s in summaries[1:]]
        print(f"Summary wording differed across runs: {len(distinct_summaries)} distinct wordings out of {n} runs "
              f"(not treated as a mismatch on its own, wording is not required to be identical).")
        print(f"  word overlap with run 1's summary (approximate, not a semantic check): {overlaps}%")
        if matched:
            print("  severity and categories matched exactly on every run (the part of this that is actually "
                  "verified, not guessed), so these summaries most likely describe the same content, just worded "
                  "differently. Still worth a human skim, this is not proof.")
        else:
            print("  severity and/or categories did NOT match on every run either, so the differently worded "
                  "summaries cannot be assumed to describe the same content without reading them.")

    raise SystemExit(0 if matched else 1)
