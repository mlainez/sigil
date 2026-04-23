#!/usr/bin/env python3
"""Audit how different tokenizers handle Sigil syntax.

Goal: identify syntax elements that fragment badly across tokenizers,
which would waste context window and make learning harder.
"""

import tiktoken
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Tokenizers to test (tiktoken encodings that stand in for common tokenizers)
ENCODERS = {
    "cl100k_base (GPT-4)": tiktoken.get_encoding("cl100k_base"),
    "o200k_base (GPT-4o)": tiktoken.get_encoding("o200k_base"),
    "p50k_base (older)": tiktoken.get_encoding("p50k_base"),
}


def tokenize(s: str, enc) -> list[str]:
    """Return the list of decoded tokens for a string."""
    ids = enc.encode(s)
    return [enc.decode([i]) for i in ids]


def audit_elements():
    """Check how specific Sigil syntax elements tokenize."""

    targets = {
        # Sigil-specific syntax
        "$0": "argv access (str)",
        "$1": "argv access (str)",
        "#0": "argv access (int)",
        "#1": "argv access (int)",
        "$10": "argv index >9",

        # Builtins we added
        "arg_int": "arg_int builtin",
        "arg_str": "arg_str builtin",
        "fmt": "fmt builtin",
        "string_chars": "string_chars",
        "string_to_int": "string_to_int",
        "array_push": "array_push",
        "array_get": "array_get",
        "map_inc": "map_inc",
        "get_or": "get_or",
        "count_in": "count_in",
        "parse_ints": "parse_ints",
        "to_lower_char": "to_lower_char",
        "to_upper_char": "to_upper_char",

        # Short aliases
        "split": "split",
        "join": "join",
        "push": "push",
        "chars": "chars",
        "sort": "sort",
        "len": "len",
        "str": "str",
        "lower": "lower",
        "upper": "upper",
        "trim": "trim",
        "sum": "sum",

        # Basic words
        "module": "module keyword",
        "set": "set keyword",
        "for": "for keyword",
        "for-each": "for-each keyword",
        "println": "println",
        "print": "print",

        # Arithmetic
        "add": "add",
        "sub": "sub",
        "mul": "mul",
        "div": "div",
        "mod": "mod",

        # Comparisons
        "eq": "eq",
        "ne": "ne",
        "lt": "lt",
        "gt": "gt",
        "le": "le",
        "ge": "ge",

        # Structural tokens
        "(set x int 0)": "typical binding",
        "(set x 0)": "type-inferred binding",
        "(arg_int 0)": "verbose argv",
        "#0": "short argv",
        '(fmt "hello {name}")': "fmt call",
        "(for-each p arr body)": "for-each",
        "(println a b c)": "variadic println",
    }

    for enc_name, enc in ENCODERS.items():
        print(f"\n{'=' * 70}")
        print(f"Tokenizer: {enc_name}")
        print(f"{'=' * 70}")
        print(f"{'Element':<30} {'Count':<8} {'Tokens':<40} {'Note'}")
        print("-" * 100)

        bad = []
        for elem, desc in targets.items():
            tokens = tokenize(elem, enc)
            count = len(tokens)
            token_strs = [repr(t) for t in tokens]
            # Flag if a single identifier splits into many tokens
            is_single_word = elem.replace("_", "").replace("-", "").isalnum()
            flag = ""
            if is_single_word and count > 1:
                flag = "⚠ FRAGMENTED"
                bad.append(elem)
            print(f"{elem!r:<30} {count:<8} {' '.join(token_strs)[:40]:<40} {flag}")

        print(f"\n{'Fragmented single-word tokens: ' + str(len(bad)) if bad else 'No single-word fragmentation'}")
        if bad:
            print(f"  Fragmented: {', '.join(bad)}")


def audit_real_code():
    """Compare tokenization of real Sigil programs."""
    print(f"\n{'=' * 70}")
    print("REAL CODE SAMPLES")
    print(f"{'=' * 70}")

    samples = {
        "fizzbuzz (script mode)": '''(set n #0)
(for i 1 (add n 1)
  (cond
    ((eq (mod i 15) 0) (println "FizzBuzz"))
    ((eq (mod i 3) 0) (println "Fizz"))
    ((eq (mod i 5) 0) (println "Buzz"))
    (true (println i))))''',

        "word_freq (modernized)": '''(set c (map_new))
(for-each w (split $0 " ") (map_inc c w))
(for-each k (sort (map_keys c)) (println k (map_get c k)))''',

        "old-style verbose": '''(module freq
  (fn main -> int
    (set args array (argv))
    (set s string (array_get args 0))
    (set c map (map_new))
    (set words array (string_split s " "))
    (set n int (array_length words))
    (for i 0 n
      (set w string (array_get words i))
      (if (map_has c w)
        (set cur int (map_get c w))
        (map_set c w (add cur 1))
        (else
          (map_set c w 1))))
    (ret 0)))''',
    }

    enc = tiktoken.get_encoding("cl100k_base")
    for name, code in samples.items():
        tokens = enc.encode(code)
        chars = len(code)
        print(f"\n{name}:")
        print(f"  Chars: {chars}, Tokens: {len(tokens)}, Chars/token: {chars/len(tokens):.1f}")
        print(f"  Code:")
        for line in code.split("\n"):
            print(f"    {line}")


if __name__ == "__main__":
    audit_elements()
    audit_real_code()
