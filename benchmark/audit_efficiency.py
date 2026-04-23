#!/usr/bin/env python3
"""Audit tests/corpus for opportunities to use more token-efficient constructs.

Finds patterns that could be shortened with newer features:
- Manual filter/map loops -> filter/map_arr with closure
- (string_format ...) -> (fmt ...)
- (array_get arr (sub (len arr) 1)) -> (last arr) or (array_get arr -1)
- (array_get (argv) N) -> $N
- Verbose argv aliasing
- Explicit (ret 0) at end of main
- Explicit type on declarations where inferable
- Verbose for-each with type
"""

import re
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parent.parent

PATTERNS = {
    "(string_to_int (array_get (argv) ...)) — use #N": r'\(string_to_int\s+\(array_get\s+\(argv\)\s+\d+\)\)',
    "(array_get (argv) N) — use $N": r'\(array_get\s+\(argv\)\s+\d+\)',
    "(string_length x) — use (len x)": r'\(string_length\s',
    "(array_length x) — use (len x)": r'\(array_length\s',
    "(map_length x) — use (len x)": r'\(map_length\s',
    "(string_from_int x) — use (str x)": r'\(string_from_int\s',
    "(string_from_float x) — use (str x)": r'\(string_from_float\s',
    "(array_get arr (sub (len arr) 1)) — use (last arr) or (array_get arr -1)":
        r'\(array_get\s+\w+\s+\(sub\s+\(len\s+\w+\)\s+1\)\)',
    "(if cond then) (else else) wrapper — could merge with cond?": None,
    "Manual filter loop (for-each ... if push) — use (filter arr (\\x ...))":
        r'\(for-each\s+\w+(?:\s+\w+)?\s+\([^)]+\)\s*\(if\s+[^)]+\(push',
    "Manual map loop — use (map_arr arr (\\x ...))": None,
    "Manual sum loop (set total 0) (for-each ... add) — use (sum arr)":
        r'\(set\s+\w+\s+(?:int\s+)?0\)\s*\(for-each\s+\w+(?:\s+\w+)?\s+\([^)]+\)\s*\(set\s+\w+\s*\(add',
    "(set len int (len ...)) variable shadowing builtin": r'\(set\s+len\s+int',
    "Explicit (set ARGS array (argv)) — use $N or (argv) directly": r'\(set\s+\w+\s+array\s+\(argv\)\)',
    "Trailing (ret 0) in main — implicit now": r'\(fn\s+main[^)]*\)[\s\S]*?\(ret\s+0\)\s*\)\s*\)?',
    "(string_format) — use (fmt) for named interpolation": r'\(string_format\s',
    "Verbose nested or for membership — use (in x coll)": r'\(or\s+\(eq\s+\w+\s+"[^"]*"\)\s+\(or',
    "(set x int 0) where 0 makes type obvious — drop type": r'\(set\s+\w+\s+int\s+\d+\)',
}


def main():
    targets = []
    for d in [REPO_ROOT / "examples" / "corpus", REPO_ROOT / "tests"]:
        if d.exists():
            targets.extend(sorted(d.glob("*.sigil")))

    # Count pattern occurrences across all files
    pattern_counts = Counter()
    file_examples = {}  # pattern_name -> [(file, snippet)]

    for f in targets:
        code = f.read_text()
        for desc, pat in PATTERNS.items():
            if pat is None:
                continue
            matches = list(re.finditer(pat, code))
            if matches:
                pattern_counts[desc] += len(matches)
                file_examples.setdefault(desc, []).append((f.name, matches[0].group()[:80]))

    # Report
    print(f"Audited {len(targets)} files\n")
    print(f"{'Opportunity':<70} {'Count':>8}")
    print("-" * 80)
    for desc, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"{desc[:70]:<70} {count:>8}")

    # Show samples
    print("\n\nFirst example of each:")
    for desc, count in sorted(pattern_counts.items(), key=lambda x: -x[1])[:5]:
        examples = file_examples[desc]
        if examples:
            f, snippet = examples[0]
            print(f"\n{desc}")
            print(f"  In {f}: {snippet}")


if __name__ == "__main__":
    main()
