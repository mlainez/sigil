#!/usr/bin/env python3
"""Generalization test: 10 fresh tasks (different from rag_ab.py) to confirm
the RAG improvements generalize beyond the tuning set.

Same harness shape as rag_ab.py — single attempt per pass, temp=0.0,
qwen2.5-coder:32b, default RAG knobs (k=5, min_score=0.65, mmr_lambda=1.0).
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
RAG_MIN_SCORE = 0.65
RAG_MMR_LAMBDA = 1.0

# 10 fresh tasks — different domains and shapes from rag_ab.py.
TASKS = [
    {"id": "rotate_right",
     "desc": "Take a space-separated list of integers in arg0 and a non-negative integer k in arg1. Print the list rotated right by k positions, space-separated.",
     "args": ["1 2 3 4 5", "2"], "expected": "4 5 1 2 3\n",
     "python": ("import sys\n"
                "xs=sys.argv[1].split()\n"
                "k=int(sys.argv[2])%len(xs)\n"
                "print(' '.join(xs[-k:]+xs[:-k] if k else xs))")},
    {"id": "count_uppercase",
     "desc": "Take a string in arg0 and print how many uppercase ASCII letters it contains.",
     "args": ["Hello World ABC"], "expected": "5\n",
     "python": ("import sys\n"
                "print(sum(1 for c in sys.argv[1] if c.isupper() and c.isascii()))")},
    {"id": "second_largest_distinct",
     "desc": "Take a space-separated list of integers in arg0. Print the second-largest distinct value. If fewer than two distinct values exist, print -1.",
     "args": ["3 1 9 9 5 7 7"], "expected": "7\n",
     "python": ("import sys\n"
                "vs=sorted(set(int(x) for x in sys.argv[1].split()), reverse=True)\n"
                "print(vs[1] if len(vs)>=2 else -1)")},
    {"id": "string_set_diff",
     "desc": "Take two strings in arg0 and arg1. Print the characters that appear in arg0 but not in arg1, in their original order from arg0, with duplicates kept.",
     "args": ["abracadabra", "br"], "expected": "aacadaa\n",
     "python": ("import sys\n"
                "a,b=sys.argv[1],sys.argv[2]; bs=set(b)\n"
                "print(''.join(c for c in a if c not in bs))")},
    {"id": "product_of_digits",
     "desc": "Take a non-negative integer in arg0 and print the product of its decimal digits.",
     "args": ["234"], "expected": "24\n",
     "python": ("import sys\n"
                "p=1\n"
                "for c in sys.argv[1]:\n    p*=int(c)\n"
                "print(p)")},
    {"id": "zero_pad_left",
     "desc": "Take a string in arg0 and a positive integer n in arg1. Print arg0 padded on the LEFT with '0' characters until its length is n. If arg0 is already at least n long, print it unchanged.",
     "args": ["42", "5"], "expected": "00042\n",
     "python": ("import sys\n"
                "s=sys.argv[1]; n=int(sys.argv[2])\n"
                "print(s if len(s)>=n else '0'*(n-len(s))+s)")},
    {"id": "acronym",
     "desc": "Take a sentence in arg0. Print the uppercase acronym formed from the first letter of each whitespace-separated word.",
     "args": ["self contained underwater breathing apparatus"], "expected": "SCUBA\n",
     "python": ("import sys\n"
                "print(''.join(w[0].upper() for w in sys.argv[1].split()))")},
    {"id": "max_word_length",
     "desc": "Take a sentence in arg0. Print the length of the longest whitespace-separated word.",
     "args": ["the quick brown fox jumps"], "expected": "5\n",
     "python": ("import sys\n"
                "print(max(len(w) for w in sys.argv[1].split()))")},
    {"id": "fizzbuzz_n",
     "desc": "Take a positive integer n in arg0. Print FizzBuzz from 1 to n, one value per line: 'Fizz' for multiples of 3, 'Buzz' for multiples of 5, 'FizzBuzz' for multiples of 15, otherwise the number.",
     "args": ["5"], "expected": "1\n2\nFizz\n4\nBuzz\n",
     "python": ("import sys\n"
                "for i in range(1, int(sys.argv[1])+1):\n"
                "    if i%15==0: print('FizzBuzz')\n"
                "    elif i%3==0: print('Fizz')\n"
                "    elif i%5==0: print('Buzz')\n"
                "    else: print(i)")},
    {"id": "caesar_decrypt",
     "desc": "Take a string in arg0 (uppercase letters only) and a positive shift k in arg1. Print arg0 decrypted by shifting each letter BACKWARDS by k positions in the alphabet (A wraps to Z).",
     "args": ["KHOOR", "3"], "expected": "HELLO\n",
     "python": ("import sys\n"
                "s=sys.argv[1]; k=int(sys.argv[2])%26\n"
                "print(''.join(chr((ord(c)-65-k)%26+65) for c in s))")},
]


def gen_no_rag(task):
    return gen_sigil_ollama(task, OLLAMA_MODEL, OLLAMA_URL,
                            temperature=0.0, slim=False, rag_block="")


def gen_with_rag(task, index):
    hits = rag.query(task["desc"], k=RAG_K, index=index,
                     min_score=RAG_MIN_SCORE, mmr_lambda=RAG_MMR_LAMBDA)
    block = rag.format_examples(hits) if hits else ""
    return gen_sigil_ollama(task, OLLAMA_MODEL, OLLAMA_URL,
                            temperature=0.0, slim=False, rag_block=block), hits


def main():
    print("Verifying Python references...")
    for t in TASKS:
        ok, out = run_python(t["python"], t["args"])
        if not ok or out != t["expected"]:
            print(f"  BAD {t['id']}: out={out!r} expected={t['expected']!r}")
            sys.exit(1)
    print(f"  all {len(TASKS)} verified")

    print("\nLoading RAG index...")
    index = rag.load_index()
    print(f"  {index['count']} entries, dim={index['dim']}")

    rows = []
    a_pass = b_pass = flips_a_to_b = flips_b_to_a = 0

    print(f"\nRunning A (no RAG) vs B (RAG, k={RAG_K}, min_score={RAG_MIN_SCORE}, mmr={RAG_MMR_LAMBDA})...\n")
    for i, t in enumerate(TASKS, 1):
        t0 = time.time()
        code_a = gen_no_rag(t)
        ta = time.time() - t0
        a_ok, a_out, a_err = (False, "", "no code")
        if code_a:
            a_ok, a_out, a_err = run_sigil(code_a, t["args"])
        a_good = a_ok and a_out == t["expected"]

        t0 = time.time()
        code_b, hits = gen_with_rag(t, index)
        tb = time.time() - t0
        b_ok, b_out, b_err = (False, "", "no code")
        if code_b:
            b_ok, b_out, b_err = run_sigil(code_b, t["args"])
        b_good = b_ok and b_out == t["expected"]

        a_pass += int(a_good); b_pass += int(b_good)
        if (not a_good) and b_good: flips_a_to_b += 1
        if a_good and (not b_good): flips_b_to_a += 1

        a_mark = "PASS" if a_good else "FAIL"
        b_mark = "PASS" if b_good else "FAIL"
        diff = "  "
        if a_good and not b_good: diff = "B-"
        elif b_good and not a_good: diff = "B+"
        elif a_good and b_good: diff = "= "
        else: diff = ".."

        top_score = hits[0]["score"] if hits else 0.0
        print(f"  [{i:2}/{len(TASKS)}] {diff} {t['id']:28s}  A:{a_mark} ({ta:5.1f}s)  "
              f"B:{b_mark} ({tb:5.1f}s)  top_sim={top_score:.2f}")
        if not a_good:
            short = a_err.strip().splitlines()[0][:80] if a_err else (a_out or "no out")[:80]
            print(f"        A err: {short}")
        if not b_good:
            short = b_err.strip().splitlines()[0][:80] if b_err else (b_out or "no out")[:80]
            print(f"        B err: {short}")

        rows.append({
            "id": t["id"], "a_pass": a_good, "b_pass": b_good,
            "a_seconds": round(ta, 1), "b_seconds": round(tb, 1),
            "a_code": code_a, "b_code": code_b,
            "a_stdout": a_out, "b_stdout": b_out,
            "a_stderr": a_err, "b_stderr": b_err,
            "rag_top_sim": top_score,
            "rag_hits": [{"score": h["score"], "desc": h["desc"][:120]} for h in hits],
        })

    print(f"\n=== SUMMARY (fresh task set) ===")
    print(f"  A (no RAG):  {a_pass}/{len(TASKS)} pass")
    print(f"  B (RAG):     {b_pass}/{len(TASKS)} pass")
    print(f"  Flips A->B+: {flips_a_to_b}")
    print(f"  Flips B->A-: {flips_b_to_a}")
    print(f"  Net delta: {b_pass - a_pass:+d}")

    out_path = Path(__file__).resolve().parent / "rag_ab_v2_results.json"
    out_path.write_text(json.dumps({
        "model": OLLAMA_MODEL, "k": RAG_K, "min_score": RAG_MIN_SCORE,
        "mmr_lambda": RAG_MMR_LAMBDA, "tasks": rows,
        "a_pass": a_pass, "b_pass": b_pass,
        "flips_a_to_b": flips_a_to_b, "flips_b_to_a": flips_b_to_a,
    }, indent=2))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
