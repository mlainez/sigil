#!/usr/bin/env python3
"""Bucket the A/B failures, then propose corpus additions per bucket.

Reads benchmark/rag_ab_results.json (output of rag_ab.py) and produces:
  1. A failure-class histogram (parse / type / runtime / wrong-output)
  2. Per-task short-form: what bug, which idiom looks missing
  3. A proposed-tasks list (json) with new specs targeted at gaps

The proposed tasks are NOT yet validated — feed them into corpus_extender.py
so the existing python-ref check + sigil-validation catches bad ones."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
RESULTS = BENCH / "rag_ab_results.json"
PROPOSALS = BENCH / "rag_ab_proposals.json"


def classify(stderr: str, stdout: str, expected: str) -> str:
    s = (stderr or "").lower()
    if "parse error" in s:
        return "parse_error"
    if "undefined variable" in s or "unbound" in s:
        return "undefined_var"
    if any(p in s for p in ["type error", "takes (", "requires", "expected ", "cannot", "invalid"]):
        return "type_error"
    if "runtime error" in s:
        return "runtime_other"
    if not (stdout or "").strip():
        return "empty_output"
    if stdout != expected:
        return "wrong_output"
    return "unknown"


# Task-level idiom-gap hypothesis. Keyed on (task_id, bucket) -> note.
# These are hypotheses, not certainties — the proposed tasks are designed
# to exercise the suspected gap and let the validator confirm.
TASK_HINTS = {
    "alternating_case": "char-indexed iteration: enumerate or index walk over a string with per-position transform",
    "rle_encode": "compress consecutive runs: stateful loop that tracks (current char, count) and emits on change",
    "rotate_left": "join an array of any kind into a space-separated string; map_arr arr str if ints",
    "digital_root": "while-loop on int with digit decomposition (chars + parse_int per char)",
    "count_words_starting_with": "filter words by a predicate over the first character",
    "kth_largest": "sort-descending then index, or sort-ascending and index from len-k",
    "sum_squares_to_n": "sum over a range with map; (sum (map_arr (range 1 (+ n 1)) (\\x (* x x))))",
    "first_unique_char": "two-pass: build counter map, then index walk emitting the first unique",
    "max_paren_depth": "running max while folding over a string; track depth as int",
    "csv_column_sum": "csv parsing: split rows, split first row as header to find column index, sum int column across rest",
}


def short_err(stderr: str) -> str:
    if not stderr:
        return ""
    line = stderr.strip().splitlines()[0]
    return line[:120]


def main():
    if not RESULTS.exists():
        print(f"missing {RESULTS}; run rag_ab.py first", file=sys.stderr)
        sys.exit(1)

    data = json.loads(RESULTS.read_text())
    rows = data["tasks"]

    print(f"=== A/B summary ===")
    print(f"  A pass: {data['a_pass']}/{len(rows)}")
    print(f"  B pass: {data['b_pass']}/{len(rows)}")
    print(f"  flips A->B: {data['flips_a_to_b']}")
    print(f"  flips B->A (regressions): {data['flips_b_to_a']}")
    print()

    # Per-pass bucket
    a_buckets: dict[str, list[str]] = {}
    b_buckets: dict[str, list[str]] = {}
    for r in rows:
        # We don't store expected per row, but rag_ab.py records stdout; we
        # know it failed so just use the existence of a parse-error / type
        # error / empty-output signature.
        a_b = classify(r["a_stderr"], r["a_stdout"], "")
        b_b = classify(r["b_stderr"], r["b_stdout"], "")
        if not r["a_pass"]:
            a_buckets.setdefault(a_b, []).append(r["id"])
        if not r["b_pass"]:
            b_buckets.setdefault(b_b, []).append(r["id"])

    print("=== Failure buckets ===")
    print("A (no RAG):")
    for k, v in sorted(a_buckets.items()):
        print(f"  {k:18s} {len(v):2d}  {', '.join(v)}")
    print("B (with RAG):")
    for k, v in sorted(b_buckets.items()):
        print(f"  {k:18s} {len(v):2d}  {', '.join(v)}")
    print()

    print("=== Per-task diagnosis (failures only) ===")
    proposals: list[dict] = []
    for r in rows:
        if r["a_pass"] and r["b_pass"]:
            continue
        idiom = TASK_HINTS.get(r["id"], "(no idiom hint)")
        a_err = short_err(r["a_stderr"]) or (r["a_stdout"] or "")[:80]
        b_err = short_err(r["b_stderr"]) or (r["b_stdout"] or "")[:80]
        a_b = classify(r["a_stderr"], r["a_stdout"], "")
        b_b = classify(r["b_stderr"], r["b_stdout"], "")
        a_status = "PASS" if r["a_pass"] else f"FAIL/{a_b}"
        b_status = "PASS" if r["b_pass"] else f"FAIL/{b_b}"
        print(f"  {r['id']:28s} A:{a_status:18s}  B:{b_status:18s}")
        print(f"     idiom: {idiom}")
        if not r["a_pass"]:
            print(f"     A err: {a_err}")
        if not r["b_pass"]:
            print(f"     B err: {b_err}")

        # Propose 2 new task specs around the same idiom but distinct shapes.
        # Empty list if we don't yet have a generator for this idiom — manual
        # follow-up for those cases.
        proposals.append({
            "source_task_id": r["id"],
            "a_bucket": a_b if not r["a_pass"] else None,
            "b_bucket": b_b if not r["b_pass"] else None,
            "idiom_hypothesis": idiom,
            "suggested_pattern_to_seed": _seed_for(r["id"]),
        })

    PROPOSALS.write_text(json.dumps(proposals, indent=2))
    print(f"\nProposals saved to {PROPOSALS}")


def _seed_for(task_id: str) -> list[dict] | None:
    """Hand-curated companion task specs that exercise the same idiom from
    a different angle. Each spec needs id, desc, args, expected, python — the
    same shape corpus_extender.py expects. Returning None means we don't yet
    have a curated set for that gap."""
    seeds = {
        "alternating_case": [
            {"id": "char_idx_swap_pairs",
             "desc": "Take a string in arg0 and print it with each pair of adjacent characters swapped. If the length is odd, leave the last char in place.",
             "args": ["abcdef"], "expected": "badcfe\n",
             "python": ("import sys\ns = sys.argv[1]\n"
                        "out = []\n"
                        "i = 0\n"
                        "while i+1 < len(s):\n    out.append(s[i+1] + s[i])\n    i += 2\n"
                        "if i < len(s): out.append(s[i])\n"
                        "print(''.join(out))")},
            {"id": "char_idx_double_vowels",
             "desc": "Take a string in arg0 and print it with every vowel (aeiouAEIOU) doubled.",
             "args": ["hello"], "expected": "heelloo\n",
             "python": ("import sys\ns=sys.argv[1]\n"
                        "print(''.join(c*2 if c in 'aeiouAEIOU' else c for c in s))")},
        ],
        "rle_encode": [
            {"id": "stateful_run_max",
             "desc": "Take a string in arg0 and print the length of the longest run of identical adjacent characters.",
             "args": ["aaabbbbccda"], "expected": "4\n",
             "python": ("import sys\ns=sys.argv[1]\n"
                        "best=cur=1\n"
                        "for i in range(1,len(s)):\n"
                        "    if s[i]==s[i-1]: cur+=1; \n    else: cur=1\n"
                        "    if cur>best: best=cur\n"
                        "print(best)")},
        ],
        "rotate_left": [
            {"id": "join_int_array_space",
             "desc": "Take a comma-separated list of integers in arg0, sort them ascending, and print them space-separated.",
             "args": ["3,1,4,1,5"], "expected": "1 1 3 4 5\n",
             "python": ("import sys\n"
                        "xs=sorted(int(x) for x in sys.argv[1].split(','))\n"
                        "print(' '.join(str(x) for x in xs))")},
        ],
        "kth_largest": [
            {"id": "median_of_ints",
             "desc": "Take an odd-length space-separated list of integers in arg0 and print the median.",
             "args": ["7 1 3 9 5"], "expected": "5\n",
             "python": ("import sys\n"
                        "xs=sorted(int(x) for x in sys.argv[1].split())\n"
                        "print(xs[len(xs)//2])")},
        ],
        "first_unique_char": [
            {"id": "first_repeat_char",
             "desc": "Take a string in arg0 and print the first character that appears more than once. Print empty if all characters are unique.",
             "args": ["abcbd"], "expected": "b\n",
             "python": ("import sys\n"
                        "s=sys.argv[1]; seen=set()\n"
                        "for c in s:\n    if c in seen: print(c); break\n    seen.add(c)\n"
                        "else: print('')")},
        ],
        "max_paren_depth": [
            {"id": "balanced_or_not",
             "desc": "Take a string of parentheses in arg0 and print 'yes' if balanced, otherwise 'no'.",
             "args": ["(()())"], "expected": "yes\n",
             "python": ("import sys\n"
                        "s=sys.argv[1]; d=0; ok=True\n"
                        "for c in s:\n    d += 1 if c=='(' else -1\n    if d<0: ok=False; break\n"
                        "print('yes' if ok and d==0 else 'no')")},
        ],
        "csv_column_sum": [
            {"id": "csv_column_max",
             "desc": "Take a CSV with header in arg0 and a column name in arg1. Print the maximum integer value in that column.",
             "args": ["name,score\nalice,30\nbob,80\ncarol,55", "score"], "expected": "80\n",
             "python": ("import sys\n"
                        "rows=sys.argv[1].split('\\n')\n"
                        "h=rows[0].split(','); idx=h.index(sys.argv[2])\n"
                        "print(max(int(r.split(',')[idx]) for r in rows[1:]))")},
        ],
    }
    return seeds.get(task_id)


if __name__ == "__main__":
    main()
