#!/usr/bin/env python3
"""V2: Measure token cost using the NEW builtins (fmt, in, optional types, implicit ret 0)."""

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


def run_sigil(code: str, args: list) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name] + args,
                             capture_output=True, text=True, timeout=5)
            return r.returncode == 0, r.stdout
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT"
        finally:
            os.unlink(f.name)


def run_python(code: str, args: list) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            r = subprocess.run([sys.executable, f.name] + args,
                             capture_output=True, text=True, timeout=5)
            return r.returncode == 0, r.stdout
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT"
        finally:
            os.unlink(f.name)


# V2 Sigil: using new features — fmt, in, optional types, implicit ret 0
CONSTRUCTS = []

CONSTRUCTS.append((
    "01_hello_world", [], "Hello, World!\n",
    '''(module hello (fn main -> int (println "Hello, World!")))''',
    '''print("Hello, World!")''',
))

CONSTRUCTS.append((
    "02_cli_int_echo", ["42"], "42\n",
    '''(module echo (fn main -> int (println (arg_int 0))))''',
    '''import sys
print(int(sys.argv[1]))''',
))

CONSTRUCTS.append((
    "03_indexed_loop", ["5"], "1\n2\n3\n4\n5\n",
    '''(module loop (fn main -> int (set n (arg_int 0)) (for i 1 (add n 1) (println i))))''',
    '''import sys
n = int(sys.argv[1])
for i in range(1, n+1):
    print(i)''',
))

CONSTRUCTS.append((
    "04_array_sum", ["1 2 3 4 5"], "15\n",
    '''(module sum
  (fn main -> int
    (set total 0)
    (for-each p string (string_split (arg_str 0) " ")
      (set total (add total (string_to_int p))))
    (println total)))''',
    '''import sys
total = sum(int(x) for x in sys.argv[1].split())
print(total)''',
))

CONSTRUCTS.append((
    "05_string_vowel_count", ["hello world"], "3\n",
    '''(module vowels
  (fn main -> int
    (set count 0)
    (for-each ch string (string_chars (string_to_lower (arg_str 0)))
      (if (in ch "aeiou") (set count (add count 1))))
    (println count)))''',
    '''import sys
s = sys.argv[1].lower()
print(sum(1 for c in s if c in "aeiou"))''',
))

CONSTRUCTS.append((
    "06_filter_evens", ["1 2 3 4 5 6"], "2 4 6\n",
    '''(module evens
  (fn main -> int
    (set result (array_new))
    (for-each p string (string_split (arg_str 0) " ")
      (if (eq (mod (string_to_int p) 2) 0) (array_push result p)))
    (println (string_join result " "))))''',
    '''import sys
nums = sys.argv[1].split()
evens = [n for n in nums if int(n) % 2 == 0]
print(" ".join(evens))''',
))

CONSTRUCTS.append((
    "07_word_frequency", ["the cat sat on the mat"], "cat 1\nmat 1\non 1\nsat 1\nthe 2\n",
    '''(module freq
  (fn main -> int
    (set counts (map_new))
    (for-each w string (string_split (arg_str 0) " ")
      (if (in w counts)
        (map_set counts w (add (map_get counts w) 1))
        (else (map_set counts w 1))))
    (set keys (map_keys counts))
    (array_sort keys)
    (for-each k string keys
      (println (fmt "{k} {}" (map_get counts k))))))''',
    '''import sys
from collections import Counter
words = sys.argv[1].split()
for k in sorted(Counter(words)):
    print(f"{k} {Counter(words)[k]}")''',
))

CONSTRUCTS.append((
    "08_string_build", ["Alice", "30"], "Hello, Alice! You are 30 years old.\n",
    '''(module greet
  (fn main -> int
    (set name (arg_str 0))
    (set age (arg_str 1))
    (println (fmt "Hello, {name}! You are {age} years old."))))''',
    '''import sys
print(f"Hello, {sys.argv[1]}! You are {sys.argv[2]} years old.")''',
))

CONSTRUCTS.append((
    "09_safe_divide", ["10", "0"], "error\n",
    '''(module safediv
  (fn main -> int
    (try
      (println (div (arg_int 0) (arg_int 1)))
      (catch err string (println "error")))))''',
    '''import sys
try:
    a, b = int(sys.argv[1]), int(sys.argv[2])
    print(a // b)
except Exception:
    print("error")''',
))

CONSTRUCTS.append((
    "10_factorial_recursive", ["5"], "120\n",
    '''(module fact
  (fn factorial n int -> int
    (if (le n 1) (ret 1))
    (ret (mul n (factorial (sub n 1)))))
  (fn main -> int (println (factorial (arg_int 0)))))''',
    '''import sys
def factorial(n):
    return 1 if n <= 1 else n * factorial(n-1)
print(factorial(int(sys.argv[1])))''',
))

CONSTRUCTS.append((
    "11_substring_find", ["hello world", "world"], "6\n",
    '''(module find (fn main -> int (println (string_find (arg_str 0) (arg_str 1)))))''',
    '''import sys
print(sys.argv[1].find(sys.argv[2]))''',
))

CONSTRUCTS.append((
    "12_sort_ints", ["5 2 8 1 9 3"], "1 2 3 5 8 9\n",
    '''(module sortnum
  (fn main -> int
    (set nums (array_new))
    (for-each p string (string_split (arg_str 0) " ")
      (array_push nums (string_to_int p)))
    (array_sort nums)
    (set result (array_new))
    (for-each n int nums
      (array_push result (str n)))
    (println (string_join result " "))))''',
    '''import sys
nums = sorted(int(x) for x in sys.argv[1].split())
print(" ".join(str(n) for n in nums))''',
))

CONSTRUCTS.append((
    "13_cond_dispatch", ["3"], "March\n",
    '''(module month
  (fn main -> int
    (set m (arg_int 0))
    (set names array ["January" "February" "March" "April" "May" "June" "July" "August" "September" "October" "November" "December"])
    (if (and (ge m 1) (le m 12))
      (println (array_get names (sub m 1)))
      (else (println "invalid")))))''',
    '''import sys
names = ["January","February","March","April","May","June","July","August","September","October","November","December"]
m = int(sys.argv[1])
print(names[m-1] if 1 <= m <= 12 else "invalid")''',
))

CONSTRUCTS.append((
    "14_json_assemble", ["Alice", "30"], '{"name":"Alice","age":30}\n',
    '''(module jsonf
  (fn main -> int
    (set name (arg_str 0))
    (set age (arg_int 1))
    (println (fmt "{{\\"name\\":\\"{name}\\",\\"age\\":{age}}}"))))''',
    '''import sys, json
print(json.dumps({"name": sys.argv[1], "age": int(sys.argv[2])}, separators=(",",":")))''',
))

CONSTRUCTS.append((
    "15_http_response", ["200", "OK"], "HTTP/1.1 200 OK\n",
    '''(module httpr
  (fn main -> int
    (set code (arg_str 0))
    (set text (arg_str 1))
    (println (fmt "HTTP/1.1 {code} {text}"))))''',
    '''import sys
print(f"HTTP/1.1 {sys.argv[1]} {sys.argv[2]}")''',
))


def main():
    results = []
    print(f"{'Construct':<30} {'Sigil':>8} {'Python':>8} {'Ratio':>8} {'Status':<20}")
    print("-" * 80)

    for name, args, expected, sigil_code, python_code in CONSTRUCTS:
        ok_s, out_s = run_sigil(sigil_code, args)
        ok_p, out_p = run_python(python_code, args)
        sigil_correct = ok_s and out_s == expected
        python_correct = ok_p and out_p == expected

        sigil_tokens = count_tokens(sigil_code)
        python_tokens = count_tokens(python_code)
        ratio = sigil_tokens / python_tokens if python_tokens else 0

        status = ""
        if not sigil_correct:
            status += f"SIGIL-BROKEN ({out_s[:40]!r}) "
        if not python_correct:
            status += f"PY-BROKEN ({out_p[:40]!r})"
        if not status:
            status = "OK"

        print(f"{name:<30} {sigil_tokens:>8} {python_tokens:>8} {ratio:>8.2f} {status:<20}")
        results.append((name, sigil_tokens, python_tokens, ratio, status))

    print()
    total_sigil = sum(r[1] for r in results if r[4] == "OK")
    total_python = sum(r[2] for r in results if r[4] == "OK")
    ok_count = sum(1 for r in results if r[4] == "OK")
    print(f"Valid: {ok_count}/{len(results)}  Sigil: {total_sigil}  Python: {total_python}")
    if total_python:
        print(f"Overall: {total_sigil/total_python:.2f}x  ({(total_sigil/total_python - 1)*100:+.1f}% vs Python)")

    print("\nSigil WINS (ratio < 1.0):")
    for r in results:
        if r[4] == "OK" and r[3] < 1.0:
            print(f"  {r[0]}: {r[3]:.2f}x ({r[1]} vs {r[2]})")
    print("\nCLOSE (1.0-1.3):")
    for r in results:
        if r[4] == "OK" and 1.0 <= r[3] <= 1.3:
            print(f"  {r[0]}: {r[3]:.2f}x ({r[1]} vs {r[2]})")
    print("\nSigil LOSES (ratio > 1.5):")
    for r in results:
        if r[4] == "OK" and r[3] > 1.5:
            print(f"  {r[0]}: {r[3]:.2f}x ({r[1]} vs {r[2]})")


if __name__ == "__main__":
    main()
