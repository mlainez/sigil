#!/usr/bin/env python3
"""V3: Use all new features — top-level scripts, $N/#N argv, short builtins, fmt, in."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")

import tiktoken
enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(code: str) -> int:
    return len(enc.encode(code))


def run_sigil(code, args):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name] + args, capture_output=True, text=True, timeout=5)
            return r.returncode == 0, r.stdout
        finally:
            os.unlink(f.name)


def run_python(code, args):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([sys.executable, f.name] + args, capture_output=True, text=True, timeout=5)
            return r.returncode == 0, r.stdout
        finally:
            os.unlink(f.name)


# V3: maximally concise Sigil using ALL new features
CONSTRUCTS = []

CONSTRUCTS.append((
    "01_hello_world", [], "Hello, World!\n",
    '(println "Hello, World!")',
    'print("Hello, World!")',
))

CONSTRUCTS.append((
    "02_cli_int_echo", ["42"], "42\n",
    '(println #0)',
    'import sys\nprint(int(sys.argv[1]))',
))

CONSTRUCTS.append((
    "03_indexed_loop", ["5"], "1\n2\n3\n4\n5\n",
    '(for i 1 (add #0 1) (println i))',
    'import sys\nn = int(sys.argv[1])\nfor i in range(1, n+1):\n    print(i)',
))

CONSTRUCTS.append((
    "04_array_sum", ["1 2 3 4 5"], "15\n",
    '(println (sum (parse_ints $0)))',
    'import sys\ntotal = sum(int(x) for x in sys.argv[1].split())\nprint(total)',
))

CONSTRUCTS.append((
    "05_string_vowel_count", ["hello world"], "3\n",
    '(println (count_in (lower $0) "aeiou"))',
    'import sys\ns = sys.argv[1].lower()\nprint(sum(1 for c in s if c in "aeiou"))',
))

CONSTRUCTS.append((
    "06_filter_evens", ["1 2 3 4 5 6"], "2 4 6\n",
    '(set r (array_new)) (for-each p (split $0 " ") (if (eq (mod (int p) 2) 0) (push r p))) (println (join r " "))',
    'import sys\nnums = sys.argv[1].split()\nevens = [n for n in nums if int(n) % 2 == 0]\nprint(" ".join(evens))',
))

CONSTRUCTS.append((
    "07_word_frequency", ["the cat sat on the mat"], "cat 1\nmat 1\non 1\nsat 1\nthe 2\n",
    '(set c (map_new)) (for-each w (split $0 " ") (map_inc c w)) (for-each k (sort (map_keys c)) (println k (map_get c k)))',
    'import sys\nfrom collections import Counter\nwords = sys.argv[1].split()\nfor k in sorted(Counter(words)):\n    print(f"{k} {Counter(words)[k]}")',
))

CONSTRUCTS.append((
    "08_string_build", ["Alice", "30"], "Hello, Alice! You are 30 years old.\n",
    '(set name $0) (set age $1) (println (fmt "Hello, {name}! You are {age} years old."))',
    'import sys\nprint(f"Hello, {sys.argv[1]}! You are {sys.argv[2]} years old.")',
))

CONSTRUCTS.append((
    "09_safe_divide", ["10", "0"], "error\n",
    '(try (println (div #0 #1)) (catch err string (println "error")))',
    'import sys\ntry:\n    a, b = int(sys.argv[1]), int(sys.argv[2])\n    print(a // b)\nexcept Exception:\n    print("error")',
))

CONSTRUCTS.append((
    "10_factorial_recursive", ["5"], "120\n",
    '(fn factorial n int -> int (if (le n 1) (ret 1)) (ret (mul n (factorial (sub n 1))))) (println (factorial #0))',
    'import sys\ndef factorial(n):\n    return 1 if n <= 1 else n * factorial(n-1)\nprint(factorial(int(sys.argv[1])))',
))

CONSTRUCTS.append((
    "11_substring_find", ["hello world", "world"], "6\n",
    '(println (string_find $0 $1))',
    'import sys\nprint(sys.argv[1].find(sys.argv[2]))',
))

CONSTRUCTS.append((
    "12_sort_ints", ["5 2 8 1 9 3"], "1 2 3 5 8 9\n",
    '(set nums (parse_ints $0)) (sort nums) (println (join nums " "))',
    'import sys\nnums = sorted(int(x) for x in sys.argv[1].split())\nprint(" ".join(str(n) for n in nums))',
))

CONSTRUCTS.append((
    "13_cond_dispatch", ["3"], "March\n",
    '(set names ["January" "February" "March" "April" "May" "June" "July" "August" "September" "October" "November" "December"]) (println (get_or names (sub #0 1) "invalid"))',
    'import sys\nnames = ["January","February","March","April","May","June","July","August","September","October","November","December"]\nm = int(sys.argv[1])\nprint(names[m-1] if 1 <= m <= 12 else "invalid")',
))

CONSTRUCTS.append((
    "14_json_assemble", ["Alice", "30"], '{"name":"Alice","age":30}\n',
    '(set name $0) (set age #1) (println (fmt "{{\\"name\\":\\"{name}\\",\\"age\\":{age}}}"))',
    'import sys, json\nprint(json.dumps({"name": sys.argv[1], "age": int(sys.argv[2])}, separators=(",",":")))',
))

CONSTRUCTS.append((
    "15_http_response", ["200", "OK"], "HTTP/1.1 200 OK\n",
    '(println "HTTP/1.1" $0 $1)',
    'import sys\nprint(f"HTTP/1.1 {sys.argv[1]} {sys.argv[2]}")',
))


def main():
    results = []
    print(f"{'Construct':<30} {'Sigil':>8} {'Python':>8} {'Ratio':>8} {'Status':<30}")
    print("-" * 85)

    for name, args, expected, sigil_code, python_code in CONSTRUCTS:
        ok_s, out_s = run_sigil(sigil_code, args)
        ok_p, out_p = run_python(python_code, args)
        sigil_correct = ok_s and out_s == expected
        python_correct = ok_p and out_p == expected

        sigil_tokens = count_tokens(sigil_code)
        python_tokens = count_tokens(python_code)
        ratio = sigil_tokens / python_tokens if python_tokens else 0

        status = "OK"
        if not sigil_correct: status = f"SIGIL({out_s[:20]!r})"
        if not python_correct: status += f" PY({out_p[:20]!r})"

        print(f"{name:<30} {sigil_tokens:>8} {python_tokens:>8} {ratio:>8.2f} {status:<30}")
        results.append((name, sigil_tokens, python_tokens, ratio, status))

    total_sigil = sum(r[1] for r in results if r[4] == "OK")
    total_python = sum(r[2] for r in results if r[4] == "OK")
    ok = sum(1 for r in results if r[4] == "OK")
    print()
    print(f"Valid: {ok}/{len(results)}  Sigil: {total_sigil}  Python: {total_python}")
    if total_python:
        print(f"Overall: {total_sigil/total_python:.2f}x  ({(total_sigil/total_python - 1)*100:+.1f}% vs Python)")

    print("\nSigil WINS (ratio < 1.0):")
    wins = 0
    for r in results:
        if r[4] == "OK" and r[3] < 1.0:
            wins += 1
            print(f"  {r[0]}: {r[3]:.2f}x ({r[1]} vs {r[2]})")
    print(f"\nTotal wins: {wins}")

    print("\nStill losing (ratio > 1.3):")
    for r in results:
        if r[4] == "OK" and r[3] > 1.3:
            print(f"  {r[0]}: {r[3]:.2f}x ({r[1]} vs {r[2]})")


if __name__ == "__main__":
    main()
