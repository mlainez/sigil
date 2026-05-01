#!/usr/bin/env python3
"""Generate ~200 verified examples covering the new prelude functions and
canonical names that are currently under-represented in the corpus.

Each example is verified by running it through vm.exe and matching expected
output exactly. Only verified examples are emitted.

Targets:
  tokens       50 examples
  find_all     50 examples
  line_count   30 examples
  squeeze      30 examples
  split_blocks 30 examples
  argv_int     20 examples
  string_at    20 examples
  map_kv       15 examples

Run:
  python3 benchmark/refresh_seeds.py
Outputs:
  benchmark/refresh_seeds.jsonl
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO / "interpreter" / "_build" / "default" / "vm.exe")
OUT = REPO / "benchmark" / "refresh_seeds.jsonl"

SYSTEM = ("You write Sigil programs. Sigil is an S-expression language designed for "
          "minimal tokens. Programs may use (module name ...) wrapping or top-level "
          "script mode. CLI args: $0 is the first user arg as a string, #0 is the first "
          "as an int. Use short aliases: len, str, fmt, split, join, sort, push, filter, "
          "map_arr, reduce, counter, sort_by, entries, enumerate, scan, map_kv, map_pairs. "
          "Prefer functional pipelines over for-each+accumulator. Empty collections: [] "
          "and {}. Output ONLY raw Sigil code.")


def verify(code: str, args: list[str], expected: str) -> bool:
    """Run code through vm.exe with args, compare stdout to expected exactly."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False)
    f.write(code); f.close()
    try:
        r = subprocess.run([SIGIL_BIN, f.name] + args,
                          capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and r.stdout == expected
    except Exception:
        return False
    finally:
        os.unlink(f.name)


# ============================================================================
# Generators per function
# ============================================================================

def gen_tokens():
    """50 tokens-using examples covering common shapes."""
    inputs_basic = [
        "the quick brown fox", "hello world", "a b c d e f g",
        "single", "  leading and trailing  ",
        "many   spaces  between", "tab\tseparated\twords",
        "mixed  \t\tspaces tabs", "one two three four",
        "alpha beta gamma delta epsilon", "x y", "java python rust go",
    ]
    cases = []
    # 1. count tokens
    for s in inputs_basic[:8]:
        n = len(s.split())
        cases.append({
            "user": f"Read a string in arg0 and print the count of whitespace-separated tokens.",
            "code": "(println (len (tokens $0)))",
            "args": [s], "expected": f"{n}\n",
        })
    # 2. print each token on its own line
    for s in inputs_basic[:6]:
        toks = s.split()
        if not toks: continue
        cases.append({
            "user": f"Read a string in arg0 and print each whitespace-separated word on its own line.",
            "code": "(for-each w (tokens $0)\n  (println w))",
            "args": [s], "expected": "\n".join(toks) + "\n",
        })
    # 3. longest token
    for s in inputs_basic[:6]:
        toks = s.split()
        if not toks: continue
        longest = max(toks, key=len)
        cases.append({
            "user": "Read a string in arg0 and print the longest whitespace-separated token.",
            "code": "(println (reduce (tokens $0) (\\(a b) (if (gt (len a) (len b)) a b)) \"\"))",
            "args": [s], "expected": f"{longest}\n",
        })
    # 4. join uppercased
    for s in inputs_basic[:5]:
        toks = s.split()
        if not toks: continue
        out = " ".join(t.upper() for t in toks)
        cases.append({
            "user": "Read a string in arg0 and print all whitespace-separated tokens uppercased, joined by single spaces.",
            "code": "(println (join (map_arr (tokens $0) upper) \" \"))",
            "args": [s], "expected": f"{out}\n",
        })
    # 5. count tokens of length > N
    for s in ["the quick brown fox", "a bb ccc dddd eeeee", "x y z"]:
        for n in [2, 3]:
            count = sum(1 for t in s.split() if len(t) > n)
            cases.append({
                "user": f"Read a string in arg0 and print the count of whitespace-separated tokens whose length is strictly greater than {n}.",
                "code": f"(println (len (filter (tokens $0) (\\t (gt (len t) {n})))))",
                "args": [s], "expected": f"{count}\n",
            })
    # 6. nth token
    for s, idx in [("alpha beta gamma delta", 0), ("alpha beta gamma delta", 2),
                    ("one two three four", 3), ("a b c d e", 1)]:
        toks = s.split()
        if idx < len(toks):
            cases.append({
                "user": f"Read a string in arg0 and print the {['first','second','third','fourth','fifth'][idx]} whitespace-separated token.",
                "code": f"(println (get (tokens $0) {idx}))",
                "args": [s], "expected": f"{toks[idx]}\n",
            })
    # 7. count distinct tokens
    for s in ["a a b b c", "the the quick fox the", "x y x y z y"]:
        n = len(set(s.split()))
        cases.append({
            "user": "Read a string in arg0 and print the count of DISTINCT whitespace-separated tokens.",
            "code": "(let s {})\n(for-each t (tokens $0)\n  (set s (map_set s t true)))\n(println (len (map_keys s)))",
            "args": [s], "expected": f"{n}\n",
        })
    return cases


def gen_find_all():
    """50 find_all examples covering common regex shapes."""
    cases = []
    # 1. extract integers
    inputs_int = [
        ("foo 123 bar 456", "123\n456\n"),
        ("a1 b22 c333", "1\n22\n333\n"),
        ("price 99 quantity 7", "99\n7\n"),
        ("no numbers here", ""),
        ("42", "42\n"),
        ("13 lines and 17 columns", "13\n17\n"),
    ]
    for s, exp in inputs_int:
        cases.append({
            "user": "Read a string in arg0 and print every contiguous run of digits, one per line, in order.",
            "code": "(for-each m (find_all \"[0-9]+\" $0)\n  (println m))",
            "args": [s], "expected": exp,
        })
    # 2. sum extracted integers
    for s in ["a 10 b 20 c 30", "5 6 7 8", "1 2 3 4 5"]:
        ints = [int(x) for x in s.split() if x.isdigit()]
        total = sum(ints)
        cases.append({
            "user": "Read a string in arg0 and print the sum of all contiguous digit-runs.",
            "code": "(println (sum (map_arr (find_all \"[0-9]+\" $0) parse_int)))",
            "args": [s], "expected": f"{total}\n",
        })
    # 3. count matches
    for s in ["aaa bbb aaa", "abc def abc abc"]:
        cases.append({
            "user": "Read a string in arg0 and arg1 (a substring); print the count of occurrences.",
            "code": "(println (len (find_all $1 $0)))",
            "args": [s, "aaa" if "aaa" in s else "abc"],
            "expected": f"{s.count('aaa' if 'aaa' in s else 'abc')}\n",
        })
    # 4. extract words (simple)
    for s, exp in [
        ("hello, world!", "hello\nworld\n"),
        ("foo-bar baz", "foo\nbar\nbaz\n"),
    ]:
        cases.append({
            "user": "Read a string in arg0 and print every contiguous run of word characters [a-zA-Z]+, one per line.",
            "code": "(for-each w (find_all \"[a-zA-Z]+\" $0)\n  (println w))",
            "args": [s], "expected": exp,
        })
    # 5. extract dates YYYY-MM-DD
    for s, exp in [
        ("on 2024-01-15 and 2025-03-20", "2024-01-15\n2025-03-20\n"),
        ("no dates", ""),
        ("2026-12-31", "2026-12-31\n"),
    ]:
        cases.append({
            "user": "Read a string in arg0 and print every ISO-format date (YYYY-MM-DD), one per line.",
            "code": "(for-each d (find_all \"[0-9]{4}-[0-9]{2}-[0-9]{2}\" $0)\n  (println d))",
            "args": [s], "expected": exp,
        })
    # 6. find max integer
    for s in ["a 10 b 200 c 30", "5 50 500 5000 50000", "1 2 3"]:
        ints = [int(x) for x in s.split() if x.isdigit()]
        if not ints: continue
        cases.append({
            "user": "Read a string in arg0 and print the largest contiguous digit-run as an integer.",
            "code": "(println (reduce (map_arr (find_all \"[0-9]+\" $0) parse_int) (\\(a b) (if (gt a b) a b)) 0))",
            "args": [s], "expected": f"{max(ints)}\n",
        })
    # 7. extract URLs
    for s, exp in [
        ("see http://a.com and https://b.io", "http://a.com\nhttps://b.io\n"),
        ("https://x.y/path here", "https://x.y/path\n"),
    ]:
        cases.append({
            "user": "Read a string in arg0 and print every http:// or https:// URL (run of non-whitespace), one per line.",
            "code": "(for-each u (find_all \"https?://[^ \\n]+\" $0)\n  (println u))",
            "args": [s], "expected": exp,
        })
    return cases


def gen_line_count():
    cases = []
    # line_count returns line count handling trailing newline
    for s, n in [
        ("a\nb\nc", 3), ("a\nb\nc\n", 3), ("single", 1),
        ("", 0), ("a\nb", 2), ("\n", 1),
        ("one\ntwo\nthree\nfour", 4), ("x\ny\nz\n", 3),
    ]:
        cases.append({
            "user": "Read a multi-line string in arg0 and print the number of lines (a final trailing newline does NOT add a line).",
            "code": "(println (line_count $0))",
            "args": [s], "expected": f"{n}\n",
        })
    # count newlines (wc -l semantics)
    for s, n in [
        ("a\nb\nc", 2), ("a\nb\nc\n", 3), ("", 0),
        ("\n", 1), ("\n\n\n", 3),
        ("hello\nworld\nfoo", 2),
    ]:
        cases.append({
            "user": "Read a string in arg0 and print the count of newline characters.",
            "code": "(println (count $0 \"\\n\"))",
            "args": [s], "expected": f"{n}\n",
        })
    # count non-empty lines
    for s, n in [
        ("a\nb\n\nc", 3), ("a\n\n\nb", 2), ("\n\n\n", 0),
        ("alpha\n\nbeta\ngamma\n", 3),
    ]:
        cases.append({
            "user": "Read a multi-line string in arg0 and print the count of non-empty lines.",
            "code": "(println (len (filter (split $0 \"\\n\") (\\l (gt (len l) 0)))))",
            "args": [s], "expected": f"{n}\n",
        })
    return cases


def gen_squeeze():
    cases = []
    for s, exp in [
        ("  hello   world  foo ", " hello world foo "),
        ("a    b", "a b"),
        ("normal text", "normal text"),
        ("\t\thi\t\tthere", " hi there"),
        ("trailing   ", "trailing "),
        ("   leading", " leading"),
        ("", ""),
    ]:
        cases.append({
            "user": "Read a string in arg0 and print it with runs of spaces/tabs collapsed to a single space (preserve leading/trailing whitespace).",
            "code": "(println (squeeze $0))",
            "args": [s], "expected": f"{exp}\n",
        })
    # squeeze + count length
    for s in ["  hello   world  ", "a    b   c"]:
        sq = " ".join(s.split())
        # squeeze preserves leading/trailing
        # actually len of squeezed depends on shape
        n = len("".join((" " if x==" " or x=="\t" else x) for x in
                       (s.replace("\t", " "))).replace("  ", " ").replace("  ", " "))
        # simpler: use Python's "manual squeeze"
        result = []
        prev_ws = False
        for c in s:
            is_ws = c == " " or c == "\t"
            if is_ws:
                if not prev_ws:
                    result.append(" ")
                prev_ws = True
            else:
                result.append(c)
                prev_ws = False
        sqs = "".join(result)
        cases.append({
            "user": "Read a string in arg0, collapse all runs of spaces/tabs to a single space (preserving leading/trailing), then print the resulting LENGTH.",
            "code": "(println (len (squeeze $0)))",
            "args": [s], "expected": f"{len(sqs)}\n",
        })
    return cases


def gen_split_blocks():
    cases = []
    for s, blocks in [
        ("hello\nworld\n\nfoo\nbar\n\nlast", 3),
        ("p1\n\np2", 2),
        ("p1\n\n\np2", 2),
        ("only one paragraph", 1),
        ("\n\n\n", 0),
        ("a\nb", 1),
    ]:
        cases.append({
            "user": "Read a multi-line string in arg0 and print the count of paragraphs (blocks separated by one or more blank lines).",
            "code": "(println (len (split_blocks $0)))",
            "args": [s], "expected": f"{blocks}\n",
        })
    # split_blocks then print each as joined
    for s, exp in [
        ("hello\nworld\n\nfoo\nbar\nbaz\n\nlast",
         "hello world\n---\nfoo bar baz\n---\nlast\n"),
        ("a\nb\n\nc\nd",
         "a b\n---\nc d\n"),
    ]:
        cases.append({
            "user": "Read a multi-line string in arg0. Paragraphs are separated by blank lines. Print each paragraph as one line (newlines inside replaced by spaces), with '---' between paragraphs and no trailing separator.",
            "code": ("(let bs (split_blocks $0))\n(let n (len bs))\n(for i 0 n\n"
                    "  (println (join (split (get bs i) \"\\n\") \" \"))\n"
                    "  (if (lt i (sub n 1))\n    (println \"---\")))"),
            "args": [s], "expected": exp,
        })
    return cases


def gen_argv_int():
    """argv_int gets a CLI arg (by index) parsed as int."""
    cases = []
    # take an int from arg N, do something simple
    for index in [0, 1]:
        for n in [3, 5, 10]:
            args = [str(n)] if index == 0 else ["dummy", str(n)]
            cases.append({
                "user": f"Read an integer from CLI arg index {index}. Print it doubled.",
                "code": f"(println (mul (argv_int {index}) 2))",
                "args": args, "expected": f"{n*2}\n",
            })
    # use argv_int to control loop count
    for n in [3, 5, 7]:
        cases.append({
            "user": "Read an integer N from CLI arg 0. Print integers from 0 to N-1, one per line.",
            "code": "(for i 0 (argv_int 0)\n  (println i))",
            "args": [str(n)], "expected": "".join(f"{i}\n" for i in range(n)),
        })
    # use argv_int in arithmetic
    for a, b in [(10, 3), (7, 2), (100, 25)]:
        cases.append({
            "user": "Read two integers from CLI args 0 and 1. Print their sum.",
            "code": "(println (add (argv_int 0) (argv_int 1)))",
            "args": [str(a), str(b)], "expected": f"{a+b}\n",
        })
    return cases


def gen_string_at():
    cases = []
    for s, idx in [("abc", 0), ("abc", 1), ("abc", 2), ("hello", 0), ("xyz", 2)]:
        cases.append({
            "user": f"Read a string in arg0. Print the character at index {idx} (as a 1-character string).",
            "code": f"(println (string_at $0 {idx}))",
            "args": [s], "expected": f"{s[idx]}\n",
        })
    # check first char equality
    for s, ch in [("apple", "a"), ("banana", "b"), ("cherry", "c"), ("not", "n")]:
        cases.append({
            "user": f"Read a string in arg0. Print 'yes' if the first character is '{ch}', else 'no'.",
            "code": f"(if (eq (string_at $0 0) \"{ch}\")\n  (println \"yes\")\n  (println \"no\"))",
            "args": [s], "expected": ("yes\n" if s[0] == ch else "no\n"),
        })
    return cases


def gen_map_kv():
    cases = []
    # build map, transform with map_kv
    # (map_kv m fn) -> array, fn takes (k, v)
    for entries, fmt_fn, expected_fn in [
        ([("a", 1), ("b", 2), ("c", 3)], "fmt \"{}={}\" k v", lambda k, v: f"{k}={v}"),
        ([("x", 10), ("y", 20)], "fmt \"{}->{}\" k v", lambda k, v: f"{k}->{v}"),
    ]:
        # Build the map literal as Sigil source
        m_init = ""
        for k, v in entries:
            m_init += f"(set m (map_set m \"{k}\" {v}))\n"
        # Sort keys alphabetically for deterministic output
        sorted_pairs = sorted(entries)
        exp = " ".join(expected_fn(k, v) for k, v in sorted_pairs) + "\n"
        cases.append({
            "user": "Build a small map and print key=value entries sorted alphabetically by key, space-separated.",
            "code": (
                "(let m {})\n" + m_init.strip() + "\n"
                "(println (join (sort (map_kv m (\\(k v) (" + fmt_fn + ")))) \" \"))"
            ),
            "args": [], "expected": exp,
        })
    return cases


GENERATORS = [
    ("tokens", gen_tokens),
    ("find_all", gen_find_all),
    ("line_count", gen_line_count),
    ("squeeze", gen_squeeze),
    ("split_blocks", gen_split_blocks),
    ("argv_int", gen_argv_int),
    ("string_at", gen_string_at),
    ("map_kv", gen_map_kv),
]


def main():
    out_lines = []
    summary = {}
    for name, gen in GENERATORS:
        cases = gen()
        ok = 0
        fail = 0
        for c in cases:
            if verify(c["code"], c["args"], c["expected"]):
                rec = {"messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": c["user"]},
                    {"role": "assistant", "content": c["code"]},
                ]}
                out_lines.append(json.dumps(rec, ensure_ascii=False))
                ok += 1
            else:
                fail += 1
        summary[name] = (ok, fail)
        print(f"  {name:14s} {ok:3d} verified, {fail:3d} failed")
    OUT.write_text("\n".join(out_lines) + "\n")
    print(f"\nTotal verified: {sum(s[0] for s in summary.values())}")
    print(f"Total failed:   {sum(s[1] for s in summary.values())}")
    print(f"Output: {OUT}")


if __name__ == "__main__":
    main()
