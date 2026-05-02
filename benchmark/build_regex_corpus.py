#!/usr/bin/env python3
"""Generate a large, verified regex-focused training corpus for Sigil.

Each example is constructed as:
  - a task description (natural English)
  - canonical input args
  - expected stdout
  - a Sigil program that produces exactly the expected output

The Sigil program is RUN against the args; only examples whose stdout
matches expected verbatim are kept.

Output: JSONL with the same {"messages":[system,user,assistant]} shape
as training_corpus.jsonl, suitable for both RAG indexing and SFT.
"""
import json, subprocess, tempfile, os, sys
from pathlib import Path

REPO = Path(__file__).parent.parent
VM = str(REPO / "interpreter" / "_build" / "default" / "vm.exe")

SYSTEM = (
    "You write Sigil programs. Sigil is an S-expression language designed for minimal tokens. "
    "Programs may use (module name ...) wrapping or top-level script mode. "
    "CLI args: $0 is the first user arg as a string, #0 is the first as an int. "
    "Use short aliases: len, str, fmt, split, join, sort, push, filter, map_arr, reduce, "
    "counter, sort_by, entries, enumerate, scan, map_kv, map_pairs, find_all, regex_find, "
    "regex_match, regex_replace. Prefer functional pipelines over for-each+accumulator. "
    "Empty collections: [] and {}. Output ONLY raw Sigil code."
)


def run_sigil(code: str, args: list[str], timeout: float = 5.0) -> tuple[bool, str, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".sigil", delete=False) as f:
        f.write(code); fp = f.name
    try:
        r = subprocess.run([VM, fp] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout, r.stderr
    finally:
        os.unlink(fp)


def example(desc: str, args: list[str], expected: str, code: str) -> dict:
    return {
        "_desc": desc, "_args": args, "_expected": expected, "_code": code,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": desc},
            {"role": "assistant", "content": code},
        ],
    }


# ============================================================
# Family 1: extract-all via find_all (canonical)
# ============================================================
EXTRACT_ALL = [
    # (desc, args, expected, code)
    ("Take a string in arg0. Print all http:// and https:// URLs (run of non-whitespace), one per line in order.",
     ["See https://example.com and http://foo.io for docs, plus https://x.y/path"],
     "https://example.com\nhttp://foo.io\nhttps://x.y/path\n",
     '(for-each u (find_all "https?://\\S+" $0) (println u))'),

    ("Take a multi-line text in arg0. Print all ISO dates (YYYY-MM-DD) found, one per line in order.",
     ["log on 2024-01-15: ok\nlog on 2024-02-30: weird\nno date here\n2025-12-01 done"],
     "2024-01-15\n2024-02-30\n2025-12-01\n",
     '(for-each d (find_all "\\d{4}-\\d{2}-\\d{2}" $0) (println d))'),

    ("Take a string in arg0. Print all email addresses found, one per line in order.",
     ["contact alice@example.com or bob@foo.io; also c@d.org"],
     "alice@example.com\nbob@foo.io\nc@d.org\n",
     '(for-each e (find_all "[\\w.+-]+@[\\w-]+\\.[\\w.-]+" $0) (println e))'),

    ("Take a string in arg0. Print all positive integers found, one per line.",
     ["item 42 cost 9 took 1284 ms"],
     "42\n9\n1284\n",
     '(for-each n (find_all "\\d+" $0) (println n))'),

    ("Take a string in arg0. Print the SUM of all positive integers found.",
     ["item 42 cost 9 took 1284 ms"],
     "1335\n",
     '(println (sum (map_arr (find_all "\\d+" $0) parse_int)))'),

    ("Take a string in arg0. Print all hex color codes (# followed by 3 or 6 hex digits), one per line.",
     ["bg=#ffeedd accent=#abc gradient via #123456 or #fff"],
     "#ffeedd\n#abc\n#123456\n#fff\n",
     '(for-each h (find_all "#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}" $0) (println h))'),

    ("Take a string in arg0. Print all hashtags (# followed by 1+ word chars), one per line.",
     ["went hiking #outdoors #wellness today, also #fun-times"],
     "#outdoors\n#wellness\n#fun\n",
     '(for-each h (find_all "#\\w+" $0) (println h))'),

    ("Take a string in arg0. Print all @-mentions (@ followed by 1+ word chars), one per line.",
     ["thanks @alice and @bob_42 plus @c"],
     "@alice\n@bob_42\n@c\n",
     '(for-each m (find_all "@\\w+" $0) (println m))'),

    ("Take a string in arg0. Print all dotted-quad IPv4 addresses, one per line.",
     ["from 10.0.0.1 to 192.168.1.42 via 8.8.8.8"],
     "10.0.0.1\n192.168.1.42\n8.8.8.8\n",
     '(for-each ip (find_all "\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}" $0) (println ip))'),

    ("Take a string in arg0. Print all UUIDs (8-4-4-4-12 hex), one per line.",
     ["ids: 550e8400-e29b-41d4-a716-446655440000 and 6ba7b810-9dad-11d1-80b4-00c04fd430c8"],
     "550e8400-e29b-41d4-a716-446655440000\n6ba7b810-9dad-11d1-80b4-00c04fd430c8\n",
     '(for-each u (find_all "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" $0) (println u))'),

    ("Take a string in arg0. Print all words (runs of letters), one per line.",
     ["hello, world! 42 cats."],
     "hello\nworld\ncats\n",
     '(for-each w (find_all "[a-zA-Z]+" $0) (println w))'),

    ("Take a string in arg0. Print all decimal numbers (with optional decimal point), one per line.",
     ["price 19.99 quantity 3 weight 0.5kg"],
     "19.99\n3\n0.5\n",
     '(for-each n (find_all "\\d+\\.?\\d*" $0) (println n))'),

    ("Take a string in arg0. Print all dollar amounts ($ followed by digits with optional decimals), one per line.",
     ["totals: $100, $42.50, and $1.99 today"],
     "$100\n$42.50\n$1.99\n",
     '(for-each d (find_all "\\$\\d+(\\.\\d+)?" $0) (println d))'),

    ("Take a string in arg0. Print all percentages (digits followed by %), one per line.",
     ["growth 25% on sale 10%, premium tier hit 99%"],
     "25%\n10%\n99%\n",
     '(for-each p (find_all "\\d+%" $0) (println p))'),

    ("Take a string in arg0. Print all 24h HH:MM time stamps, one per line.",
     ["start 09:15, lunch 12:30, end 17:45"],
     "09:15\n12:30\n17:45\n",
     '(for-each t (find_all "\\d{2}:\\d{2}" $0) (println t))'),

    ("Take a string in arg0. Print all words ending with 'ing', one per line.",
     ["running jumping skipping while singing"],
     "running\njumping\nskipping\nsinging\n",
     '(for-each w (find_all "\\w+ing" $0) (println w))'),

    ("Take a string in arg0. Print all all-caps acronyms (2+ uppercase letters), one per line.",
     ["the API and SDK are different from CLI tools"],
     "API\nSDK\nCLI\n",
     '(for-each a (find_all "[A-Z]{2,}" $0) (println a))'),

    ("Take a string in arg0. Print all semver-shaped versions (X.Y.Z), one per line.",
     ["upgrade from 1.2.3 to 2.0.1 (was 1.0.0 before)"],
     "1.2.3\n2.0.1\n1.0.0\n",
     '(for-each v (find_all "\\d+\\.\\d+\\.\\d+" $0) (println v))'),

    ("Take a string in arg0. Print the COUNT of integers found.",
     ["a 1 b 2 c 3 d 4 e 5"],
     "5\n",
     '(println (len (find_all "\\d+" $0)))'),

    ("Take a string in arg0. Print the COUNT of words.",
     ["the quick brown fox"],
     "4\n",
     '(println (len (find_all "\\w+" $0)))'),
]

# ============================================================
# Family 2: validate via regex_match (returns bool, used in if)
# ============================================================
VALIDATE = [
    ("Take a string in arg0. Print 'yes' if it matches a US phone number ###-###-####, else 'no'.",
     ["555-123-4567"], "yes\n",
     '(println (if (regex_match "^\\d{3}-\\d{3}-\\d{4}$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it matches a US phone number ###-###-####, else 'no'.",
     ["abc-def-ghij"], "no\n",
     '(println (if (regex_match "^\\d{3}-\\d{3}-\\d{4}$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it looks like an email address, else 'no'.",
     ["alice@example.com"], "yes\n",
     '(println (if (regex_match "^[\\w.+-]+@[\\w-]+\\.[\\w.-]+$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it looks like an email address, else 'no'.",
     ["not an email"], "no\n",
     '(println (if (regex_match "^[\\w.+-]+@[\\w-]+\\.[\\w.-]+$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it is exactly 1+ digits, else 'no'.",
     ["12345"], "yes\n",
     '(println (if (regex_match "^\\d+$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it is exactly 1+ digits, else 'no'.",
     ["12a45"], "no\n",
     '(println (if (regex_match "^\\d+$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it matches an ISO date YYYY-MM-DD exactly, else 'no'.",
     ["2024-01-15"], "yes\n",
     '(println (if (regex_match "^\\d{4}-\\d{2}-\\d{2}$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it matches an ISO date YYYY-MM-DD exactly, else 'no'.",
     ["2024-1-15"], "no\n",
     '(println (if (regex_match "^\\d{4}-\\d{2}-\\d{2}$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it matches a hex color #RRGGBB exactly, else 'no'.",
     ["#ffeedd"], "yes\n",
     '(println (if (regex_match "^#[0-9a-fA-F]{6}$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it matches a hex color #RRGGBB exactly, else 'no'.",
     ["#xyz"], "no\n",
     '(println (if (regex_match "^#[0-9a-fA-F]{6}$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it matches semver X.Y.Z exactly, else 'no'.",
     ["1.2.3"], "yes\n",
     '(println (if (regex_match "^\\d+\\.\\d+\\.\\d+$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it matches semver X.Y.Z exactly, else 'no'.",
     ["1.2"], "no\n",
     '(println (if (regex_match "^\\d+\\.\\d+\\.\\d+$" $0) "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it is a valid IPv4 dotted quad (no leading zeros except 0, each octet 0-255), else 'no'.",
     ["192.168.1.1"], "yes\n",
     '(set parts (split $0 "."))\n(set ok (eq (len parts) 4))\n(if ok\n  (for-each p parts\n    (if (not (regex_match "^(0|[1-9]\\d{0,2})$" p))\n      (set ok false)\n      (if (gt (parse_int p) 255) (set ok false) (set _ 0)))))\n(println (if ok "yes" "no"))'),

    ("Take a string in arg0. Print 'yes' if it is a valid IPv4 dotted quad (no leading zeros except 0, each octet 0-255), else 'no'.",
     ["256.1.1.1"], "no\n",
     '(set parts (split $0 "."))\n(set ok (eq (len parts) 4))\n(if ok\n  (for-each p parts\n    (if (not (regex_match "^(0|[1-9]\\d{0,2})$" p))\n      (set ok false)\n      (if (gt (parse_int p) 255) (set ok false) (set _ 0)))))\n(println (if ok "yes" "no"))'),
]

# ============================================================
# Family 3: filter lines by regex_match
# ============================================================
FILTER = [
    ("Take a multi-line text in arg0. Print only lines containing the word ERROR.",
     ["INFO ok\nERROR boom\nINFO ok\nERROR oops"],
     "ERROR boom\nERROR oops\n",
     '(for-each l (split $0 "\\n") (if (regex_match "ERROR" l) (println l)))'),

    ("Take a multi-line text in arg0. Print only lines that start with a digit.",
     ["1 first\nalpha\n2 second\nbeta"],
     "1 first\n2 second\n",
     '(for-each l (split $0 "\\n") (if (regex_match "^\\d" l) (println l)))'),

    ("Take a multi-line text in arg0. Print only lines that contain a 4-digit year (19xx or 20xx).",
     ["born 1985 in town\nno year here\nfounded 2003 inc"],
     "born 1985 in town\nfounded 2003 inc\n",
     '(for-each l (split $0 "\\n") (if (regex_match "(19|20)\\d{2}" l) (println l)))'),

    ("Take a multi-line text in arg0. Print only lines that DO NOT contain a digit.",
     ["alpha\nbeta 2\ngamma\ndelta 4"],
     "alpha\ngamma\n",
     '(for-each l (split $0 "\\n") (if (not (regex_match "\\d" l)) (println l)))'),

    ("Take a multi-line text in arg0. Print only lines whose first non-whitespace character is #.",
     ["#comment\n  indented\n# another\nplain"],
     "#comment\n# another\n",
     '(for-each l (split $0 "\\n") (if (regex_match "^\\s*#" l) (println l)))'),

    ("Take a multi-line text in arg0. Print the count of blank or whitespace-only lines.",
     ["a\n\nb\n   \nc"],
     "2\n",
     '(println (len (filter (split $0 "\\n") (\\l (regex_match "^\\s*$" l)))))'),

    ("Take a multi-line text in arg0. Print only NON-blank lines (skip blank or whitespace-only).",
     ["a\n\nb\n   \nc"],
     "a\nb\nc\n",
     '(for-each l (split $0 "\\n") (if (not (regex_match "^\\s*$" l)) (println l)))'),

    ("Take a multi-line text in arg0. Print the count of lines containing the word TODO.",
     ["TODO fix\nok\nTODO test\nTODO ship\nfine"],
     "3\n",
     '(println (len (filter (split $0 "\\n") (\\l (regex_match "TODO" l)))))'),
]

# ============================================================
# Family 4: replace via regex_replace
# ============================================================
REPLACE = [
    ("Replace runs of whitespace in arg0 with a single space; print result.",
     ["hello   world\t\tfoo  bar"],
     "hello world foo bar\n",
     '(println (regex_replace "\\s+" $0 " "))'),

    ("Remove all digits from arg0; print result.",
     ["abc123def456"],
     "abcdef\n",
     '(println (regex_replace "\\d+" $0 ""))'),

    ("Replace all occurrences of one or more 'a' in arg0 with 'X'; print result.",
     ["banana aardvark"],
     "bXnXnX XrdvXrk\n",
     '(println (regex_replace "a+" $0 "X"))'),

    ("Redact all email addresses in arg0 (replace each with [EMAIL]); print result.",
     ["mail alice@example.com or bob@foo.io now"],
     "mail [EMAIL] or [EMAIL] now\n",
     '(println (regex_replace "[\\w.+-]+@[\\w-]+\\.[\\w.-]+" $0 "[EMAIL]"))'),

    ("Redact every 4-digit year in arg0 (replace with YEAR); print result.",
     ["born 1985 founded 2003"],
     "born YEAR founded YEAR\n",
     '(println (regex_replace "\\d{4}" $0 "YEAR"))'),

    ("Strip ANSI color escape sequences (ESC [ ... m) from arg0; print result.",
     ["[31mred[0m and [32mgreen[0m"],
     "red and green\n",
     '(println (regex_replace "\\x1b\\[[0-9;]*m" $0 ""))'),

    ("Collapse repeated dashes in arg0 to a single dash; print result.",
     ["a---b----c-d"],
     "a-b-c-d\n",
     '(println (regex_replace "-+" $0 "-"))'),

    ("Remove every leading whitespace from each line in arg0; print result joined by newlines.",
     ["   one\n  two\n     three"],
     "one\ntwo\nthree\n",
     '(println (join (map_arr (split $0 "\\n") (\\l (regex_replace "^\\s+" l ""))) "\\n"))'),
]

# ============================================================
# Family 5: line-by-line regex_find + slice/extract
# (capture-group simulation since Re.all returns whole matches)
# ============================================================
LINE_EXTRACT = [
    ("Take a Python source string in arg0. Print top-level (no leading whitespace) `def NAME(` definition NAMES, one per line.",
     ["def foo():\n    pass\n\nclass Bar:\n    def baz(self): pass\n\ndef main():\n    pass\n"],
     "foo\nmain\n",
     '(for-each line (split $0 "\\n")\n  (set m (regex_find "^def \\w+\\(" line))\n  (if (ne m "") (println (string_slice m 4 (sub (len m) 5)))))'),

    ("Take a multi-line text in arg0. For each line containing an integer, print the FIRST integer found on that line.",
     ["a 1 b\nno digits\nx 22 33\nq"],
     "1\n22\n",
     '(for-each line (split $0 "\\n")\n  (set m (regex_find "\\d+" line))\n  (if (ne m "") (println m)))'),

    ("Take a multi-line text in arg0. For every line of the form 'KEY=VALUE', print KEY (only the part before =).",
     ["FOO=1\nbar baz\nBAR=hello\nNAME=alice"],
     "FOO\nBAR\nNAME\n",
     '(for-each line (split $0 "\\n")\n  (set m (regex_find "^[A-Za-z_][A-Za-z0-9_]*=" line))\n  (if (ne m "") (println (string_slice m 0 (sub (len m) 1)))))'),

    ("Take a multi-line text in arg0. For lines of form '[LEVEL] msg', print the LEVEL (without brackets).",
     ["[INFO] start\n[ERROR] bad\nplain line\n[WARN] hmm"],
     "INFO\nERROR\nWARN\n",
     '(for-each line (split $0 "\\n")\n  (set m (regex_find "^\\[[A-Z]+\\]" line))\n  (if (ne m "") (println (string_slice m 1 (sub (len m) 2)))))'),
]

# ============================================================
# Family 6: count occurrences (regex-based)
# ============================================================
COUNT = [
    ("Print the count of times the substring in arg1 appears in arg0 (overlap NOT allowed).",
     ["banana", "an"], "2\n",
     '(println (sub (len (split $0 $1)) 1))'),

    ("Print the count of digits in arg0.",
     ["abc123def456"], "6\n",
     '(println (sum (map_arr (find_all "\\d" $0) (\\_ 1))))'),

    ("Print the count of vowels (a, e, i, o, u, lowercase) in arg0.",
     ["education"], "5\n",
     '(println (len (find_all "[aeiou]" $0)))'),

    ("Print the count of words (runs of letters) in arg0.",
     ["the quick brown fox jumps"], "5\n",
     '(println (len (find_all "[a-zA-Z]+" $0)))'),
]

ALL = EXTRACT_ALL + VALIDATE + FILTER + REPLACE + LINE_EXTRACT + COUNT


def main(out_path: str):
    print(f"Verifying {len(ALL)} regex examples against the interpreter...")
    kept, dropped = [], []
    for i, (desc, args, expected, code) in enumerate(ALL, 1):
        ok, stdout, stderr = run_sigil(code, args)
        if ok and stdout == expected:
            kept.append(example(desc, args, expected, code))
            print(f"  [{i:3}] OK")
        else:
            dropped.append((i, desc, expected, stdout, stderr))
            print(f"  [{i:3}] DROP — got {stdout!r} stderr={stderr[:80]!r}")
    print(f"\nKept {len(kept)} / dropped {len(dropped)}")
    with open(out_path, "w") as f:
        for ex in kept:
            # Strip the meta fields before writing — keep messages only
            clean = {"messages": ex["messages"]}
            f.write(json.dumps(clean) + "\n")
    print(f"Wrote {out_path}")
    if dropped:
        print("\nDropped detail:")
        for i, desc, exp, got, err in dropped:
            print(f"  [{i}] {desc[:60]}")
            print(f"      expected={exp!r}\n      got={got!r}\n      err={err[:120]!r}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(REPO / "benchmark" / "regex_corpus.jsonl")
    main(out)
