#!/usr/bin/env python3
"""Feedback loop: generate corpus at increasing complexity, measure vs Python/JS,
identify language/stdlib gaps, report recommendations.

Architecture:
  TIER_TASKS[N] = list of task specs (desc, args, expected_stdout, py_code)
  For each task:
    1. Use Claude to generate Sigil (with latest grammar)
    2. Validate Sigil output matches expected
    3. Measure tokens for both Sigil and Python
    4. If Sigil loses: analyze why
  After tier complete: summary of wins/losses + recommendations

Usage:
  python feedback_loop.py --tier 2
  python feedback_loop.py --tier 2 --limit 5     # quick smoke test
  python feedback_loop.py --all                   # run all tiers
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import tiktoken

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")
GRAMMAR = (REPO_ROOT / ".sigil.grammar").read_text()
CORPUS_DIR = REPO_ROOT / "examples" / "corpus"
ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(s: str) -> int:
    return len(ENC.encode(s))


def run_sigil(code: str, args: list) -> tuple[bool, str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name] + args,
                             capture_output=True, text=True, timeout=10)
            return r.returncode == 0, r.stdout, r.stderr
        finally:
            os.unlink(f.name)


def run_python(code: str, args: list) -> tuple[bool, str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([sys.executable, f.name] + args,
                             capture_output=True, text=True, timeout=10)
            return r.returncode == 0, r.stdout, r.stderr
        finally:
            os.unlink(f.name)


def generate_sigil(desc: str, example_args: list, example_output: str, model: str = "claude-sonnet-4-6") -> str:
    """Use Claude to write Sigil code for a task. Returns just the code."""
    prompt = f"""{GRAMMAR}

Write a Sigil program that does exactly this:

TASK: {desc}

Example: when called with args {example_args}, output must be exactly:
{example_output!r}

Rules — follow STRICTLY for minimum tokens:
1. Use script mode, NO (module ...) wrapper, NO (fn main ...), top-level only
2. CLI args are zero-indexed from the FIRST user arg:
   - $0 = first user arg as string, $1 = second, etc.
   - #0 = first user arg as int, #1 = second as int
   (Python's sys.argv[1] == Sigil $0; Python's sys.argv[2] == Sigil $1)
3. OMIT type annotations on (set ...) and (for-each ...) — they are optional
4. PREFER functional pipelines over for-each+set accumulator:
   (sum (map_arr arr (\\x ...)))  is better than  (for-each ... (set tot ...))
5. Use lambdas: (\\x expr) for 1 arg, (\\(x y) expr) for multi
6. Higher-order arg order:  (filter arr pred),  (map_arr arr fn),
   (reduce arr fn init) — array FIRST, function SECOND
7. Short aliases always: len, str, fmt, split, join, sort, push, chars,
   int, float, lower, upper, trim, first, last, filter, map_arr, reduce,
   parse_ints, sum, count, count_in, map_inc, get_or, rev, swapcase, title,
   uniq, max_by, min_by, digits, counter, sort_by, group_by, transpose
8. Empty collections: use [] and {{}} — NEVER (array_new) or (map_new)
9. (push arr v), (map_set m k v), (sort arr), (rev arr) MUTATE in place.
   Call them directly, do NOT wrap in (set arr ...).
10. String ops:
    - (add s1 s2) concatenates strings
    - (mul s n) repeats s n times
    - (rev s) reverses a string
    - (swapcase s) swaps letter case
    - (title s) capitalizes first letter of each word
    - (uniq arr) dedupes preserving order
    - (parse_pairs s outer inner) parses "a=1,b=2" to a map
    - (count haystack needle) counts occurrences (string or array)
    - (max_by arr key-fn) / (min_by arr key-fn) pick element by key
    - (digits n) int|string → array of digit ints (skips non-digits in string)
    - (counter arr) frequency map: each element mapped to its count (Python Counter)
    - (sort_by arr key-fn) stable ascending sort by key; desc via (neg (key x))
    - (group_by arr key-fn) → map from key to array (Python defaultdict)
    - (transpose rows) matrix transpose — array of arrays to array of arrays
11. Variadic println prints space-separated: (println a b c)
12. Index with (array_get a i) — supports negatives like Python
13. Comparisons are prefix: (gt a b), (lt a b), (eq a b)

Output ONLY the raw Sigil code. No markdown fences. No explanations. No (module)."""

    try:
        r = subprocess.run(
            ["claude", "--print", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=90, cwd="/tmp",
        )
        code = r.stdout.strip()
        for fence in ["```sigil", "```lisp", "```scheme", "```"]:
            if code.startswith(fence):
                code = code[len(fence):].strip()
                break
        if code.endswith("```"):
            code = code[:-3].strip()
        return code
    except Exception as e:
        return ""


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

TIER_2 = [
    # Medium complexity: data transformations, string processing, simple parsers
    {
        "id": "csv_sum_col",
        "desc": "Parse a CSV string (rows separated by ';', fields by ','). Sum the second column (integers) and print the total.",
        "args": ["1,10;2,20;3,30;4,40"],
        "expected": "100\n",
        "python": '''import sys
rows = sys.argv[1].split(";")
total = sum(int(r.split(",")[1]) for r in rows)
print(total)''',
    },
    {
        "id": "word_longer_than",
        "desc": "Given a sentence (first arg) and an int N (second arg), print all words longer than N chars, space-separated.",
        "args": ["the quick brown fox jumped over", "3"],
        "expected": "quick brown jumped over\n",
        "python": '''import sys
n = int(sys.argv[2])
print(" ".join(w for w in sys.argv[1].split() if len(w) > n))''',
    },
    {
        "id": "reverse_each_word",
        "desc": "Reverse each word in a sentence, preserving word order.",
        "args": ["hello world foo"],
        "expected": "olleh dlrow oof\n",
        "python": '''import sys
print(" ".join(w[::-1] for w in sys.argv[1].split()))''',
    },
    {
        "id": "count_char",
        "desc": "Count occurrences of a specific character in a string. First arg is string, second arg is single char.",
        "args": ["mississippi", "s"],
        "expected": "4\n",
        "python": '''import sys
print(sys.argv[1].count(sys.argv[2]))''',
    },
    {
        "id": "dedupe_preserve_order",
        "desc": "Remove duplicate words from a space-separated list, preserving order of first occurrence.",
        "args": ["a b a c b d a"],
        "expected": "a b c d\n",
        "python": '''import sys
seen = set()
result = []
for w in sys.argv[1].split():
    if w not in seen:
        seen.add(w)
        result.append(w)
print(" ".join(result))''',
    },
    {
        "id": "average_int",
        "desc": "Compute the integer average (floor division) of space-separated numbers.",
        "args": ["10 20 30 40"],
        "expected": "25\n",
        "python": '''import sys
nums = [int(x) for x in sys.argv[1].split()]
print(sum(nums) // len(nums))''',
    },
    {
        "id": "repeat_string",
        "desc": "Repeat a string N times. First arg is the string, second is count.",
        "args": ["ab", "3"],
        "expected": "ababab\n",
        "python": '''import sys
print(sys.argv[1] * int(sys.argv[2]))''',
    },
    {
        "id": "kv_pair_lookup",
        "desc": "Given key=value pairs separated by commas, look up a key and print its value. First arg is pairs, second is key.",
        "args": ["name=alice,age=30,city=paris", "age"],
        "expected": "30\n",
        "python": '''import sys
pairs = dict(kv.split("=") for kv in sys.argv[1].split(","))
print(pairs[sys.argv[2]])''',
    },
    {
        "id": "swap_case",
        "desc": "Swap the case of each letter in a string (upper->lower, lower->upper).",
        "args": ["Hello World"],
        "expected": "hELLO wORLD\n",
        "python": '''import sys
print(sys.argv[1].swapcase())''',
    },
    {
        "id": "longest_word",
        "desc": "Print the longest word in a sentence. If tied, print the first.",
        "args": ["the quick brown fox"],
        "expected": "quick\n",
        "python": '''import sys
words = sys.argv[1].split()
best = words[0]
for w in words[1:]:
    if len(w) > len(best):
        best = w
print(best)''',
    },
    {
        "id": "is_sorted",
        "desc": "Print 'yes' if space-separated integers are sorted ascending, 'no' otherwise.",
        "args": ["1 2 3 4 5"],
        "expected": "yes\n",
        "python": '''import sys
nums = [int(x) for x in sys.argv[1].split()]
print("yes" if nums == sorted(nums) else "no")''',
    },
    {
        "id": "sum_digits",
        "desc": "Sum the digits of a non-negative integer.",
        "args": ["12345"],
        "expected": "15\n",
        "python": '''import sys
print(sum(int(d) for d in sys.argv[1]))''',
    },
    {
        "id": "caesar_shift",
        "desc": "Caesar cipher: shift each lowercase letter by N positions (wrap around). First arg text, second arg shift.",
        "args": ["hello", "3"],
        "expected": "khoor\n",
        "python": '''import sys
text = sys.argv[1]
shift = int(sys.argv[2])
result = []
for c in text:
    if "a" <= c <= "z":
        result.append(chr((ord(c) - ord("a") + shift) % 26 + ord("a")))
    else:
        result.append(c)
print("".join(result))''',
    },
    {
        "id": "title_case",
        "desc": "Capitalize the first letter of each word in a sentence.",
        "args": ["hello world from sigil"],
        "expected": "Hello World From Sigil\n",
        "python": '''import sys
print(" ".join(w.capitalize() for w in sys.argv[1].split()))''',
    },
    {
        "id": "max_subarray_len",
        "desc": "Given space-separated integers and a target sum, find the longest contiguous subarray whose sum is <= target. Print its length.",
        "args": ["1 2 3 4 5", "7"],
        "expected": "3\n",
        "python": '''import sys
nums = [int(x) for x in sys.argv[1].split()]
target = int(sys.argv[2])
best = 0
for i in range(len(nums)):
    total = 0
    for j in range(i, len(nums)):
        total += nums[j]
        if total <= target:
            best = max(best, j - i + 1)
        else:
            break
print(best)''',
    },
]

TIER_3 = [
    # Harder: hashmaps, nested structures, multi-step algorithms
    {
        "id": "word_frequency_top",
        "desc": "Count word frequencies in a sentence and print them as 'word:count' pairs sorted by count desc (ties by word asc), comma-separated.",
        "args": ["the cat and the dog and the cat"],
        "expected": "the:3,and:2,cat:2,dog:1\n",
        "python": '''import sys
from collections import Counter
c = Counter(sys.argv[1].split())
items = sorted(c.items(), key=lambda x: (-x[1], x[0]))
print(",".join(f"{k}:{v}" for k, v in items))''',
    },
    {
        "id": "group_anagrams",
        "desc": "Group words that are anagrams of each other. Output groups separated by ';', words within group space-separated and sorted, groups sorted by first word.",
        "args": ["eat tea tan ate nat bat"],
        "expected": "ate eat tea;bat;nat tan\n",
        "python": '''import sys
from collections import defaultdict
g = defaultdict(list)
for w in sys.argv[1].split():
    g["".join(sorted(w))].append(w)
groups = [sorted(v) for v in g.values()]
groups.sort(key=lambda v: v[0])
print(";".join(" ".join(g) for g in groups))''',
    },
    {
        "id": "balanced_parens",
        "desc": "Check if parentheses/brackets/braces in a string are balanced. Print 'yes' or 'no'.",
        "args": ["({[]})[]"],
        "expected": "yes\n",
        "python": '''import sys
s = sys.argv[1]
stack = []
pairs = {")": "(", "]": "[", "}": "{"}
ok = True
for c in s:
    if c in "([{":
        stack.append(c)
    elif c in ")]}":
        if not stack or stack.pop() != pairs[c]:
            ok = False; break
print("yes" if ok and not stack else "no")''',
    },
    {
        "id": "matrix_transpose",
        "desc": "Transpose a matrix given as rows separated by ';' and integers by ','. Output same format.",
        "args": ["1,2,3;4,5,6"],
        "expected": "1,4;2,5;3,6\n",
        "python": '''import sys
rows = [r.split(",") for r in sys.argv[1].split(";")]
cols = list(zip(*rows))
print(";".join(",".join(c) for c in cols))''',
    },
    {
        "id": "flatten_nested",
        "desc": "Flatten a nested list given as '[1,2,[3,4,[5]],6]' into a single comma-separated list.",
        "args": ["[1,2,[3,4,[5]],6]"],
        "expected": "1,2,3,4,5,6\n",
        "python": '''import sys, re
# Simple: strip brackets, keep digits + commas, dedupe commas
s = re.sub(r"[\\[\\]]", "", sys.argv[1])
s = re.sub(r",+", ",", s).strip(",")
print(s)''',
    },
    {
        "id": "running_average",
        "desc": "Compute running averages (as floats with 1 decimal) for space-separated ints. Output space-separated.",
        "args": ["10 20 30 40"],
        "expected": "10.0 15.0 20.0 25.0\n",
        "python": '''import sys
nums = [int(x) for x in sys.argv[1].split()]
out = []
for i in range(1, len(nums) + 1):
    out.append(f"{sum(nums[:i])/i:.1f}")
print(" ".join(out))''',
    },
    {
        "id": "interval_merge",
        "desc": "Merge overlapping intervals. Input: intervals as 'a-b' separated by ','. Output merged intervals in same format, sorted by start.",
        "args": ["1-3,2-6,8-10,15-18"],
        "expected": "1-6,8-10,15-18\n",
        "python": '''import sys
ivs = sorted(tuple(map(int, p.split("-"))) for p in sys.argv[1].split(","))
out = [list(ivs[0])]
for a, b in ivs[1:]:
    if a <= out[-1][1]:
        out[-1][1] = max(out[-1][1], b)
    else:
        out.append([a, b])
print(",".join(f"{a}-{b}" for a, b in out))''',
    },
    {
        "id": "kv_update",
        "desc": "Parse 'k=v,k=v' pairs (first arg), then apply updates in 'k=v,k=v' form (second arg, new or overwrite). Output merged as 'k=v' pairs sorted by key, comma-separated.",
        "args": ["a=1,b=2,c=3", "b=20,d=4"],
        "expected": "a=1,b=20,c=3,d=4\n",
        "python": '''import sys
def parse(s): return dict(kv.split("=") for kv in s.split(","))
d = parse(sys.argv[1])
d.update(parse(sys.argv[2]))
print(",".join(f"{k}={v}" for k, v in sorted(d.items())))''',
    },
    {
        "id": "prime_sieve",
        "desc": "Print all primes up to N (inclusive), space-separated.",
        "args": ["30"],
        "expected": "2 3 5 7 11 13 17 19 23 29\n",
        "python": '''import sys
n = int(sys.argv[1])
sieve = [True] * (n + 1)
sieve[0] = sieve[1] = False
for i in range(2, int(n**0.5) + 1):
    if sieve[i]:
        for j in range(i*i, n+1, i):
            sieve[j] = False
print(" ".join(str(i) for i in range(n+1) if sieve[i]))''',
    },
    {
        "id": "two_sum",
        "desc": "Find two indices in an int array that sum to target. Print them as 'i,j' (0-indexed, smaller first). Assume exactly one solution.",
        "args": ["2 7 11 15", "9"],
        "expected": "0,1\n",
        "python": '''import sys
nums = [int(x) for x in sys.argv[1].split()]
target = int(sys.argv[2])
seen = {}
for i, n in enumerate(nums):
    if target - n in seen:
        print(f"{seen[target-n]},{i}")
        break
    seen[n] = i''',
    },
    {
        "id": "rle_encode",
        "desc": "Run-length encode a string. Output char followed by count, e.g. 'aaabbc' -> 'a3b2c1'.",
        "args": ["aaabbc"],
        "expected": "a3b2c1\n",
        "python": '''import sys
s = sys.argv[1]
if not s:
    print("")
else:
    out = []
    prev = s[0]; cnt = 1
    for c in s[1:]:
        if c == prev: cnt += 1
        else: out.append(f"{prev}{cnt}"); prev, cnt = c, 1
    out.append(f"{prev}{cnt}")
    print("".join(out))''',
    },
    {
        "id": "diff_sets",
        "desc": "Given two space-separated lists of words, print words in first but not in second, sorted alphabetically, space-separated.",
        "args": ["apple banana cherry date", "banana date fig"],
        "expected": "apple cherry\n",
        "python": '''import sys
a = set(sys.argv[1].split())
b = set(sys.argv[2].split())
print(" ".join(sorted(a - b)))''',
    },
    {
        "id": "fib_memo",
        "desc": "Compute the Nth Fibonacci number (0-indexed, fib(0)=0, fib(1)=1).",
        "args": ["20"],
        "expected": "6765\n",
        "python": '''import sys
n = int(sys.argv[1])
a, b = 0, 1
for _ in range(n):
    a, b = b, a + b
print(a)''',
    },
    {
        "id": "query_string_parse",
        "desc": "Parse a URL query string ('k=v&k=v&...') and print values in key-sorted order, one 'k=v' per line.",
        "args": ["name=alice&age=30&city=paris"],
        "expected": "age=30\ncity=paris\nname=alice\n",
        "python": '''import sys
pairs = dict(kv.split("=") for kv in sys.argv[1].split("&"))
for k in sorted(pairs):
    print(f"{k}={pairs[k]}")''',
    },
    {
        "id": "stack_calc",
        "desc": "Evaluate a postfix (RPN) expression. Tokens are space-separated ints or the operators + - * /. Integer math.",
        "args": ["3 4 + 2 *"],
        "expected": "14\n",
        "python": '''import sys
stack = []
for tok in sys.argv[1].split():
    if tok in "+-*/":
        b = stack.pop(); a = stack.pop()
        if tok == "+": stack.append(a + b)
        elif tok == "-": stack.append(a - b)
        elif tok == "*": stack.append(a * b)
        elif tok == "/": stack.append(a // b)
    else:
        stack.append(int(tok))
print(stack[0])''',
    },
]

TIERS = {2: TIER_2, 3: TIER_3}


def run_task(task: dict) -> dict:
    """Run one task: generate, validate, measure. Returns result dict."""
    result = {
        "id": task["id"],
        "desc": task["desc"],
    }

    # Measure Python first (baseline)
    py_code = task["python"]
    ok_p, out_p, err_p = run_python(py_code, task["args"])
    if not ok_p or out_p != task["expected"]:
        result["status"] = "python-broken"
        result["note"] = f"python out={out_p!r} expected={task['expected']!r}"
        return result

    result["python_tokens"] = count_tokens(py_code)

    # Try Sigil up to 3 times
    for attempt in range(3):
        sigil_code = generate_sigil(task["desc"], task["args"], task["expected"])
        if not sigil_code:
            continue
        ok_s, out_s, err_s = run_sigil(sigil_code, task["args"])
        if ok_s and out_s == task["expected"]:
            result["sigil_code"] = sigil_code
            result["sigil_tokens"] = count_tokens(sigil_code)
            result["attempts"] = attempt + 1
            result["status"] = "ok"
            result["ratio"] = result["sigil_tokens"] / result["python_tokens"]
            return result

    # Sigil failed
    result["status"] = "sigil-failed"
    result["note"] = f"last_sigil={sigil_code[:100]!r} out={out_s[:60]!r} err={err_s[:60]!r}"
    return result


def analyze_results(results: list[dict]) -> dict:
    """Summarize wins/losses and identify patterns needing improvement."""
    ok = [r for r in results if r.get("status") == "ok"]
    sigil_failed = [r for r in results if r.get("status") == "sigil-failed"]
    py_broken = [r for r in results if r.get("status") == "python-broken"]

    wins = [r for r in ok if r["ratio"] < 1.0]
    ties = [r for r in ok if 1.0 <= r["ratio"] <= 1.1]
    losses = [r for r in ok if r["ratio"] > 1.1]

    total_sigil = sum(r["sigil_tokens"] for r in ok)
    total_python = sum(r["python_tokens"] for r in ok)

    return {
        "total": len(results),
        "ok": len(ok),
        "sigil_failed": len(sigil_failed),
        "python_broken": len(py_broken),
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "total_sigil": total_sigil,
        "total_python": total_python,
        "overall_ratio": total_sigil / total_python if total_python else 0,
    }


def print_summary(summary: dict):
    print()
    print("=" * 75)
    print(f"RESULTS: {summary['ok']}/{summary['total']} valid")
    if summary['sigil_failed']:
        print(f"  Sigil failed to produce correct code: {summary['sigil_failed']}")
    if summary['python_broken']:
        print(f"  Python ref broken (fix needed): {summary['python_broken']}")
    print()
    print(f"Wins  (Sigil < 1.0x Python): {len(summary['wins'])}")
    print(f"Ties  (1.0-1.1x): {len(summary['ties'])}")
    print(f"LOSSES (>1.1x):   {len(summary['losses'])}")
    print()
    print(f"Overall Sigil/Python ratio: {summary['overall_ratio']:.2f}x")
    print()

    if summary['losses']:
        print("=" * 75)
        print("LOSSES — investigate for language/stdlib improvements:")
        print("=" * 75)
        for r in sorted(summary['losses'], key=lambda x: -x['ratio']):
            print(f"\n[{r['ratio']:.2f}x] {r['id']}: {r['desc'][:60]}")
            print(f"  Sigil ({r['sigil_tokens']} tok):")
            for line in r['sigil_code'].split("\n"):
                print(f"    {line}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--save-corpus", action="store_true",
                       help="Save successful Sigil programs to examples/corpus/")
    args = parser.parse_args()

    tasks = TIERS.get(args.tier, [])
    if not tasks:
        print(f"No tasks for tier {args.tier}")
        sys.exit(1)

    if args.limit:
        tasks = tasks[:args.limit]

    print(f"=== TIER {args.tier}: {len(tasks)} tasks ===\n")

    results = []
    for i, task in enumerate(tasks):
        print(f"[{i+1}/{len(tasks)}] {task['id']}: {task['desc'][:60]}...")
        r = run_task(task)
        if r['status'] == 'ok':
            marker = '✓' if r['ratio'] < 1.0 else ('~' if r['ratio'] <= 1.1 else '✗')
            print(f"  {marker} {r['ratio']:.2f}x (Sigil {r['sigil_tokens']} / Python {r['python_tokens']})")
        else:
            print(f"  ✗ {r['status']}: {r.get('note', '')[:80]}")
        results.append(r)

        # Save to corpus if successful
        if args.save_corpus and r['status'] == 'ok':
            CORPUS_DIR.mkdir(parents=True, exist_ok=True)
            fpath = CORPUS_DIR / f"t{args.tier}_{r['id']}.sigil"
            fpath.write_text(r['sigil_code'].strip() + "\n")

    summary = analyze_results(results)
    print_summary(summary)

    out_path = REPO_ROOT / "benchmark" / f"tier{args.tier}_results.json"
    out_path.write_text(json.dumps({"results": results, "summary": {
        "total": summary["total"], "ok": summary["ok"],
        "sigil_failed": summary["sigil_failed"], "python_broken": summary["python_broken"],
        "wins": len(summary["wins"]), "ties": len(summary["ties"]), "losses": len(summary["losses"]),
        "overall_ratio": summary["overall_ratio"],
    }}, indent=2))
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    main()
