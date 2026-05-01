#!/usr/bin/env python3
"""A/B test: ollama-only vs ollama+RAG correctness on 10 moderately-novel tasks.

Both passes use the SAME ollama model (qwen2.5-coder:32b) with the SAME
PROMPT and SAME deterministic temperature. The only difference is whether
the prompt includes a few-shot block of K most-similar prior solutions
fetched from rag_index.json.

For each task we:
  1. Verify the Python reference produces the expected output.
  2. Run pass A (no RAG): one attempt at temperature 0.
  3. Run pass B (with RAG, k=5): one attempt at temperature 0.
  4. Validate each output via the Sigil interpreter against the expected
     stdout for the given args.

Single attempt per pass — the goal is to compare base vs RAG-augmented
correctness rate, not to measure how many retries it takes to land.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag
from corpus_extender import (
    GRAMMAR, PROMPT, SLIM_HEADER, gen_sigil_ollama, run_python, run_sigil,
)

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:32b"
RAG_K = 5
RAG_MIN_SCORE = 0.0
RAG_MMR_LAMBDA = 1.0

# 10 hand-crafted tasks — picked to be slightly novel (rare in the corpus
# in EXACTLY this form) but solvable with patterns the corpus contains, so
# RAG retrieval should plausibly help. Each task has a Python reference we
# verify before asking the model to write Sigil.
TASKS = [
    {
        "id": "alternating_case",
        "desc": "Take a string and print it with letters alternating UPPER, lower, UPPER, lower, ... starting with UPPER. Non-letters keep their case but still consume a position.",
        "args": ["hello"],
        "expected": "HeLlO\n",
        "python": ("import sys\n"
                   "s = sys.argv[1]\n"
                   "print(''.join(c.upper() if i%2==0 else c.lower() for i,c in enumerate(s)))"),
    },
    {
        "id": "rle_encode",
        "desc": "Run-length encode the string in arg0. For each maximal run of identical chars print the char followed by the count, no separators.",
        "args": ["aaabbc"],
        "expected": "a3b2c1\n",
        "python": ("import sys\n"
                   "s = sys.argv[1]\n"
                   "out = []\n"
                   "i = 0\n"
                   "while i < len(s):\n"
                   "    j = i\n"
                   "    while j < len(s) and s[j] == s[i]:\n"
                   "        j += 1\n"
                   "    out.append(s[i] + str(j - i))\n"
                   "    i = j\n"
                   "print(''.join(out))"),
    },
    {
        "id": "rotate_left",
        "desc": "Take a space-separated list of integers in arg0 and a non-negative integer k in arg1. Print the list rotated left by k positions, space-separated.",
        "args": ["1 2 3 4 5", "2"],
        "expected": "3 4 5 1 2\n",
        "python": ("import sys\n"
                   "xs = sys.argv[1].split()\n"
                   "k = int(sys.argv[2]) % len(xs)\n"
                   "print(' '.join(xs[k:] + xs[:k]))"),
    },
    {
        "id": "digital_root",
        "desc": "Take an integer in arg0 and print its digital root: repeatedly sum the decimal digits until a single digit remains.",
        "args": ["38"],
        "expected": "2\n",
        "python": ("import sys\n"
                   "n = int(sys.argv[1])\n"
                   "while n >= 10:\n"
                   "    n = sum(int(c) for c in str(n))\n"
                   "print(n)"),
    },
    {
        "id": "count_words_starting_with",
        "desc": "Take a sentence in arg0 and a single letter in arg1. Print how many whitespace-separated words in arg0 start with arg1 (case-sensitive).",
        "args": ["hi hello world hat", "h"],
        "expected": "3\n",
        "python": ("import sys\n"
                   "words = sys.argv[1].split()\n"
                   "c = sys.argv[2]\n"
                   "print(sum(1 for w in words if w.startswith(c)))"),
    },
    {
        "id": "kth_largest",
        "desc": "Take a space-separated list of integers in arg0 and a 1-based index k in arg1. Print the k-th largest value.",
        "args": ["5 1 9 3 7", "2"],
        "expected": "7\n",
        "python": ("import sys\n"
                   "xs = sorted([int(x) for x in sys.argv[1].split()], reverse=True)\n"
                   "print(xs[int(sys.argv[2]) - 1])"),
    },
    {
        "id": "sum_squares_to_n",
        "desc": "Take a positive integer n in arg0 and print 1^2 + 2^2 + ... + n^2.",
        "args": ["5"],
        "expected": "55\n",
        "python": ("import sys\n"
                   "n = int(sys.argv[1])\n"
                   "print(sum(i*i for i in range(1, n+1)))"),
    },
    {
        "id": "first_unique_char",
        "desc": "Take a string in arg0 and print the 0-based index of the first character that appears exactly once in the whole string. If no such character exists, print -1.",
        "args": ["swiss"],
        "expected": "1\n",
        "python": ("import sys\n"
                   "from collections import Counter\n"
                   "s = sys.argv[1]\n"
                   "c = Counter(s)\n"
                   "for i, ch in enumerate(s):\n"
                   "    if c[ch] == 1:\n"
                   "        print(i); break\n"
                   "else:\n"
                   "    print(-1)"),
    },
    {
        "id": "max_paren_depth",
        "desc": "Take a string of parentheses in arg0 (only '(' and ')') and print the maximum nesting depth.",
        "args": ["(()(()))"],
        "expected": "3\n",
        "python": ("import sys\n"
                   "s = sys.argv[1]\n"
                   "d = 0; m = 0\n"
                   "for c in s:\n"
                   "    if c == '(':\n"
                   "        d += 1\n"
                   "        if d > m: m = d\n"
                   "    elif c == ')':\n"
                   "        d -= 1\n"
                   "print(m)"),
    },
    {
        "id": "csv_column_sum",
        "desc": "Take a CSV string in arg0 (rows separated by '\\n', fields by ','). The first row is a header. Sum the integer values of the column named arg1 and print the total.",
        "args": ["name,age\nalice,30\nbob,25\ncarol,40", "age"],
        "expected": "95\n",
        "python": ("import sys\n"
                   "rows = sys.argv[1].split('\\n')\n"
                   "header = rows[0].split(',')\n"
                   "idx = header.index(sys.argv[2])\n"
                   "print(sum(int(r.split(',')[idx]) for r in rows[1:]))"),
    },
]


def gen_no_rag(task):
    return gen_sigil_ollama(task, OLLAMA_MODEL, OLLAMA_URL,
                            temperature=0.0, slim=False, rag_block="")


def gen_with_rag(task, index, k=RAG_K, min_score=RAG_MIN_SCORE,
                 mmr_lambda=RAG_MMR_LAMBDA):
    hits = rag.query(task["desc"], k=k, index=index,
                     min_score=min_score, mmr_lambda=mmr_lambda)
    block = rag.format_examples(hits) if hits else ""
    return gen_sigil_ollama(task, OLLAMA_MODEL, OLLAMA_URL,
                            temperature=0.0, slim=False, rag_block=block), hits


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", type=int, default=RAG_K)
    ap.add_argument("--min-score", type=float, default=RAG_MIN_SCORE)
    ap.add_argument("--mmr-lambda", type=float, default=RAG_MMR_LAMBDA)
    ap.add_argument("--label", type=str, default="",
                    help="Suffix for the output file (rag_ab_results_<label>.json)")
    args = ap.parse_args()

    print("Verifying Python references...")
    for t in TASKS:
        ok, out = run_python(t["python"], t["args"])
        if not ok or out != t["expected"]:
            print(f"  BAD SPEC {t['id']}: ok={ok} out={out!r} expected={t['expected']!r}")
            sys.exit(1)
    print(f"  all {len(TASKS)} Python refs verified")

    print("\nLoading RAG index...")
    index = rag.load_index()
    print(f"  loaded {index['count']} entries, dim={index['dim']}")

    rows = []
    a_pass = 0
    b_pass = 0
    flips_a_to_b = 0
    flips_b_to_a = 0

    print(f"\nRunning A (no RAG) vs B (RAG, k={args.k}, "
          f"min_score={args.min_score}, mmr_lambda={args.mmr_lambda})...\n")
    for i, t in enumerate(TASKS, 1):
        # Pass A
        t0 = time.time()
        code_a = gen_no_rag(t)
        ta = time.time() - t0
        a_ok, a_out, a_err = (False, "", "no code")
        if code_a:
            a_ok, a_out, a_err = run_sigil(code_a, t["args"])
        a_good = a_ok and a_out == t["expected"]

        # Pass B
        t0 = time.time()
        code_b, hits = gen_with_rag(t, index, k=args.k,
                                    min_score=args.min_score,
                                    mmr_lambda=args.mmr_lambda)
        tb = time.time() - t0
        b_ok, b_out, b_err = (False, "", "no code")
        if code_b:
            b_ok, b_out, b_err = run_sigil(code_b, t["args"])
        b_good = b_ok and b_out == t["expected"]

        a_pass += int(a_good)
        b_pass += int(b_good)
        if (not a_good) and b_good:
            flips_a_to_b += 1
        if a_good and (not b_good):
            flips_b_to_a += 1

        a_mark = "PASS" if a_good else "FAIL"
        b_mark = "PASS" if b_good else "FAIL"
        diff = "  "
        if a_good and not b_good: diff = "B-"
        if b_good and not a_good: diff = "B+"
        if a_good and b_good: diff = "= "
        if not a_good and not b_good: diff = ".."

        top_score = hits[0]["score"] if hits else 0.0
        print(f"  [{i:2}/{len(TASKS)}] {diff} {t['id']:28s}  A:{a_mark} ({ta:5.1f}s)  "
              f"B:{b_mark} ({tb:5.1f}s)  top_sim={top_score:.2f}")
        if not a_good:
            short = a_err.strip().splitlines()[0][:70] if a_err else (a_out or "no out")[:70]
            print(f"        A err: {short}")
        if not b_good:
            short = b_err.strip().splitlines()[0][:70] if b_err else (b_out or "no out")[:70]
            print(f"        B err: {short}")

        rows.append({
            "id": t["id"],
            "a_pass": a_good, "b_pass": b_good,
            "a_seconds": round(ta, 1), "b_seconds": round(tb, 1),
            "a_code": code_a, "b_code": code_b,
            "a_stdout": a_out, "b_stdout": b_out,
            "a_stderr": a_err, "b_stderr": b_err,
            "rag_top_sim": top_score,
            "rag_hits": [{"score": h["score"], "desc": h["desc"][:120]} for h in hits],
        })

    print(f"\n=== SUMMARY ===")
    print(f"  A (no RAG):  {a_pass}/{len(TASKS)} pass")
    print(f"  B (RAG k={RAG_K}): {b_pass}/{len(TASKS)} pass")
    print(f"  RAG flipped A-fail -> B-pass: {flips_a_to_b}")
    print(f"  RAG flipped A-pass -> B-fail (regression): {flips_b_to_a}")
    print(f"  Net delta: {b_pass - a_pass:+d}")

    suffix = f"_{args.label}" if args.label else ""
    out_path = Path(__file__).resolve().parent / f"rag_ab_results{suffix}.json"
    out_path.write_text(json.dumps({
        "model": OLLAMA_MODEL, "k": args.k,
        "min_score": args.min_score, "mmr_lambda": args.mmr_lambda,
        "tasks": rows,
        "a_pass": a_pass, "b_pass": b_pass,
        "flips_a_to_b": flips_a_to_b, "flips_b_to_a": flips_b_to_a,
    }, indent=2))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
