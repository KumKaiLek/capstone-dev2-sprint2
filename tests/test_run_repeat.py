"""Offline tests for run_repeat.py's summary rule checks (Card 1, "summary output behaviour
checked"). No IBM call, no key needed. Run: python -m tests.test_run_repeat"""
from run_repeat import check_summary_rules, count_sentences, neutral_wording_flags, unverified_detail_flags, word_overlap

results = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), "-", name)
    results.append(bool(ok))


T = ("this is a synthetic test recording synthetic test script you are worthless and everyone "
     "hates you i know where you live and i will make you regret it")

check("one sentence counted as one", count_sentences("A single neutral sentence.") == 1)
check("three sentences counted as three", count_sentences("One. Two. Three.") == 3)
check("four sentences counted as four, not clamped", count_sentences("One. Two. Three. Four.") == 4)

check("neutral summary has no wording flags", neutral_wording_flags("The content describes a threat of violence.") == [])
check("a removal recommendation is flagged", "should be removed" in neutral_wording_flags("This content should be removed immediately."))
check("a takedown recommendation is flagged", "take down" in neutral_wording_flags("The team should take down this post."))

check("a summary built only from transcript words has no detail flags",
      unverified_detail_flags("The speaker describes the recording as a test.", T) == [])
check("a name and place not in the transcript are flagged",
      unverified_detail_flags("The speaker Bob threatens violence in Paris.", T) == ["Bob", "Paris"])
check("a sentence-initial capital is not flagged on its own",
      unverified_detail_flags("Synthetic test recording described.", T) == [])

r = check_summary_rules("The content describes a worthless and hated target, with a threat to cause harm.", T)
check("check_summary_rules reports sentence count, length and both flag lists",
      r["sentenceCount"] == 1 and r["sentenceCountOk"] is True and r["length"] > 0 and r["lengthOk"] is True
      and r["neutralWordingFlags"] == [] and r["possibleUnverifiedDetails"] == [])
r = check_summary_rules("One. Two. Three. Four. This should be removed, says Bob from Mars.", T)
check("check_summary_rules catches an out of range sentence count, a flagged phrase and unverified names together",
      r["sentenceCountOk"] is False and r["neutralWordingFlags"] == ["should be removed"]
      and set(r["possibleUnverifiedDetails"]) >= {"Bob", "Mars"})

check("identical text has full word overlap", word_overlap("hello world", "hello world") == 1.0)
check("unrelated text has no word overlap", word_overlap("hello world", "completely different text") == 0.0)
check("partial overlap is between 0 and 1", 0 < word_overlap("the hello world test", "hello there") < 1)

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
