#!/usr/bin/env python3
"""Analyze the corpus to identify stdlib gaps and language optimization opportunities."""

import re
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "examples" / "corpus"
STDLIB = REPO_ROOT / "stdlib"
TESTS = REPO_ROOT / "tests"

def analyze():
    all_code = []
    for f in sorted(CORPUS.glob("*.sigil")):
        all_code.append(("corpus", f.name, f.read_text()))
    for f in sorted(TESTS.glob("*.sigil")):
        all_code.append(("test", f.name, f.read_text()))
    for f in sorted(STDLIB.rglob("*.sigil")):
        all_code.append(("stdlib", f.name, f.read_text()))

    print(f"Analyzing {len(all_code)} files ({sum(len(c) for _, _, c in all_code)} chars)\n")

    # --- 1. Most called builtins ---
    builtin_calls = Counter()
    for _, _, code in all_code:
        # Match (builtin_name ...)
        for m in re.finditer(r'\((\w+)\s', code):
            name = m.group(1)
            if name not in {"module", "fn", "set", "if", "else", "while", "for", "for-each",
                           "loop", "break", "continue", "ret", "cond", "and", "or", "not",
                           "try", "catch", "label", "goto", "ifnot", "import", "test-spec",
                           "case", "meta-note", "input", "expect"}:
                builtin_calls[name] += 1

    print("=" * 70)
    print("TOP 30 MOST CALLED OPERATIONS")
    print("=" * 70)
    for name, count in builtin_calls.most_common(30):
        print(f"  {count:>5}  {name}")

    # --- 2. Verbose patterns (token waste) ---
    print(f"\n{'=' * 70}")
    print("VERBOSE PATTERNS (token waste)")
    print("=" * 70)

    patterns = {
        "argv->int parsing": r"string_to_int \(array_get \(argv\)",
        "argv->float parsing": r"string_to_float \(array_get \(argv\)",
        "argv->string": r"array_get \(argv\)",
        "string_from_int for output": r"string_from_int",
        "string_concat accumulation": r"set \w+ \(string_concat \w+",
        "manual char iteration": r"string_get \w+ \w+\).*string_slice",
        "manual is_alpha check": r"and \(ge \w+ 6[57]\) \(le \w+ [0-9]+\)",
        "manual is_digit check": r"and \(ge \w+ 48\) \(le \w+ 57\)",
        "println string_from_int": r"println \(string_from_int",
        "cast_int_float": r"cast_int_float",
        "cast_float_int": r"cast_float_int",
        "array_length in for bound": r"for \w+ 0 \(array_length",
    }

    for desc, pattern in patterns.items():
        count = sum(len(re.findall(pattern, code)) for _, _, code in all_code)
        print(f"  {count:>5}  {desc}")

    # --- 3. Reimplemented functions ---
    print(f"\n{'=' * 70}")
    print("REIMPLEMENTED FUNCTIONS (should be stdlib)")
    print("=" * 70)

    fn_defs = Counter()
    for src, fname, code in all_code:
        if src == "stdlib":
            continue  # skip stdlib itself
        for m in re.finditer(r'\(fn\s+(\w+)', code):
            name = m.group(1)
            if name != "main":
                fn_defs[name] += 1

    # Show functions defined more than once
    for name, count in fn_defs.most_common(40):
        if count >= 2:
            print(f"  {count:>3}x  {name}")

    # --- 4. Missing stdlib modules (inferred from patterns) ---
    print(f"\n{'=' * 70}")
    print("RECOMMENDED STDLIB ADDITIONS")
    print("=" * 70)

    recommendations = []

    # Check for number theory patterns
    number_theory = sum(1 for _, _, c in all_code if "is_prime" in c or "fn gcd" in c or "fn lcm" in c or "fn factorial" in c)
    if number_theory > 0:
        recommendations.append(("stdlib/core/number_theory.sigil",
            f"is_prime, gcd, lcm, factorial, fibonacci — reimplemented in {number_theory} files"))

    # Check for char utils
    char_utils = sum(1 for _, _, c in all_code if re.search(r"ge \w+ 65.*le \w+ 90|ge \w+ 97.*le \w+ 122|ge \w+ 48.*le \w+ 57", c))
    if char_utils > 0:
        recommendations.append(("stdlib/core/char_utils.sigil",
            f"is_digit, is_alpha, is_upper, is_lower, is_whitespace — manual checks in {char_utils} files"))

    # Check for encoding
    encoding = sum(1 for _, _, c in all_code if "to_hex" in c or "to_binary" in c or "base_convert" in c or "hex_byte" in c)
    if encoding > 0:
        recommendations.append(("stdlib/core/encoding.sigil",
            f"int_to_hex, hex_to_int, int_to_binary, binary_to_int — in {encoding} files"))

    for path, reason in recommendations:
        print(f"  {path}")
        print(f"    {reason}")
        print()

    # --- 5. Recommended builtins (interpreter-level) ---
    print(f"{'=' * 70}")
    print("RECOMMENDED INTERPRETER BUILTINS")
    print("=" * 70)

    argv_int = sum(len(re.findall(r"string_to_int \(array_get \(argv\)", c)) for _, _, c in all_code)
    argv_str = sum(len(re.findall(r"array_get \(argv\)", c)) for _, _, c in all_code)
    print(f"\n  arg_int(n) / arg_str(n) / arg_float(n)")
    print(f"    Replaces: (string_to_int (array_get (argv) n))")
    print(f"    Occurrences: {argv_int} int + {argv_str} total argv access")
    print(f"    Token savings: ~5 tokens per call")

    strlen_for = sum(len(re.findall(r"for \w+ 0 \(string_length", c)) for _, _, c in all_code)
    arrlen_for = sum(len(re.findall(r"for \w+ 0 \(array_length", c)) for _, _, c in all_code)
    print(f"\n  len(x) — polymorphic length")
    print(f"    Replaces: (string_length x) and (array_length x)")
    print(f"    Occurrences: {strlen_for} string + {arrlen_for} array in for-bounds alone")
    print(f"    Token savings: ~1 token per call (shorter name)")

    str_chars = sum(len(re.findall(r"string_slice \w+ \w+ 1\)", c)) for _, _, c in all_code)
    print(f"\n  string_chars(s) -> array of single-char strings")
    print(f"    Replaces: manual (for i 0 (string_length s) (string_slice s i 1))")
    print(f"    Occurrences: ~{str_chars} single-char slices")
    print(f"    Enables: (for-each ch string (string_chars s) ...)")

    sfmt = sum(len(re.findall(r"string_from_int", c)) for _, _, c in all_code)
    print(f"\n  Polymorphic string conversion: str(x)")
    print(f"    Replaces: string_from_int, string_from_float, string_from_bool")
    print(f"    Occurrences: {sfmt} string_from_int calls")
    print(f"    Token savings: ~2 tokens per call")

    concat_chains = sum(len(re.findall(r"string_concat", c)) for _, _, c in all_code)
    print(f"\n  String interpolation or builder")
    print(f"    string_concat calls: {concat_chains}")
    print(f"    string_format already exists but underused")


if __name__ == "__main__":
    analyze()
