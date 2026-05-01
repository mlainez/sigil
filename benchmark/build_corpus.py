#!/usr/bin/env python3
"""Build a fine-tune corpus from the modernized Sigil sources.

Output: one JSONL file in together.ai chat format, one line per example:
    {"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}

Sources:
  - examples/corpus/*.sigil  (task-shaped programs)
  - tests/*.sigil            (test specs — teach the test-spec form)

stdlib is excluded — those are library modules, not instruction-shaped.

Task descriptions are derived from filename + a curated hint map for well-known
names. Names we don't recognize get a generic fallback ("Implement X in Sigil.").

Extended corpus (from feedback-loop tier tasks) is merged in with its exact
description — the desc we used to generate the Sigil in the first place.

Usage:
    python build_corpus.py                              # writes training_corpus.jsonl
    python build_corpus.py --output /tmp/x.jsonl
    python build_corpus.py --dedupe                     # skip numbered dupes if base exists
    python build_corpus.py --include-opus-extensions    # also pull from extensions/
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")
GRAMMAR = (REPO_ROOT / ".sigil.grammar").read_text()


# ---------------------------------------------------------------------------
# Task-description heuristics
# ---------------------------------------------------------------------------

# Curated descriptions for common corpus filenames. Keyed on filename stem with
# numbered suffix stripped. Missing keys fall back to the generic template.
#
# Keep these short and task-shaped — they become the user message in the
# training pair, so they should match the kinds of prompts a real user types.
HINTS = {
    "hello_world": "Print 'Hello, World!'.",
    "hello": "Print 'Hello, World!'.",
    "absolute_value": "Read an integer from the first CLI arg and print its absolute value.",
    "abs_manual": "Read an integer from the first CLI arg and print its absolute value without using a builtin.",
    "alpha_check": "Read a string from the first CLI arg and print whether every character is a letter.",
    "anagram_finder": "Read a space-separated list of words from the first CLI arg and group anagrams together.",
    "armstrong": "Read an integer from the first CLI arg and print whether it is an Armstrong number (narcissistic).",
    "armstrong_numbers": "Read an integer N and print all Armstrong numbers from 1 to N.",
    "average_float": "Read a space-separated list of numbers and print their mean as a float.",
    "balanced_parens": "Read a string and print 'yes' if brackets ()[]{} are balanced, 'no' otherwise.",
    "binary_search": "Binary-search a sorted space-separated int array (arg1) for a target (arg2). Print the 0-based index or -1.",
    "binary_to_decimal": "Read a binary string and print its decimal value.",
    "bubble_sort": "Bubble-sort space-separated integers and print them space-separated.",
    "caesar_cipher": "Apply a Caesar shift (arg2) to string (arg1).",
    "capitalize_words": "Title-case each word in a sentence.",
    "case_insensitive_compare": "Read two strings and print 'equal' if they match case-insensitively, else 'different'.",
    "celsius_to_fahrenheit": "Read a Celsius temperature and print the Fahrenheit equivalent.",
    "char_counter": "Count occurrences of a character (arg2) in a string (arg1).",
    "char_freq": "Print character frequency of a string, one 'char count' pair per line.",
    "char_histogram": "Print a histogram of character frequencies in a string.",
    "circle_area": "Read a radius and print the area of a circle.",
    "circle_calculator": "Read a radius and print the circumference and area of a circle.",
    "closer_to_zero": "Read two integers and print the one closer to zero.",
    "collatz": "Read an integer n and print the Collatz sequence until it reaches 1.",
    "comma_sort": "Read comma-separated integers, sort them, and print them comma-separated.",
    "concat_strings": "Read two strings and print them concatenated.",
    "count_above_avg": "Count how many numbers in a list are above the mean.",
    "count_digits": "Read an integer and print its number of digits.",
    "count_vowels": "Count vowels in a string (case-insensitive).",
    "dedupe": "Remove duplicate words from a space-separated list, preserving order.",
    "dedup_integers": "Remove duplicate integers from a space-separated list, preserving order.",
    "digit_sum": "Sum the digits of a non-negative integer.",
    "factorial": "Compute the factorial of N.",
    "fibonacci": "Print the first N Fibonacci numbers, one per line.",
    "fizzbuzz": "Print the FizzBuzz sequence from 1 to N.",
    "gcd": "Print the greatest common divisor of two integers.",
    "group_by_first_letter": "Group words by their first letter.",
    "is_palindrome": "Print 'yes' if the input string reads the same forwards and backwards (case-insensitive), else 'no'.",
    "is_prime": "Print 'yes' if N is prime, else 'no'.",
    "lcm": "Print the least common multiple of two integers.",
    "longest_word": "Print the longest word in a sentence (first one wins on ties).",
    "max_of_three": "Read three integers and print the largest.",
    "min_max": "Read space-separated integers and print the minimum and maximum.",
    "palindrome": "Read a string and print whether it is a palindrome (case-insensitive).",
    "phone_book": "Implement a small phonebook: parse 'name=number' pairs, then look up a name.",
    "power_of_two": "Print whether N is a power of two.",
    "prime_factors": "Print the prime factors of N, space-separated.",
    "prime_sieve": "Print all primes up to N, space-separated.",
    "remove_digits": "Read a string and print it with all digits removed.",
    "reverse_integer": "Read an integer and print its digits reversed.",
    "reverse_string": "Read a string and print it reversed.",
    "reverse_words": "Reverse the order of words in a sentence.",
    "roman_numerals": "Read an integer 1..3999 and print its Roman numeral form.",
    "roman_to_int": "Read a Roman numeral and print its integer value.",
    "rot13": "Apply ROT13 to the input string.",
    "selection_sort": "Selection-sort space-separated integers.",
    "sieve_primes": "Print all primes up to N using the Sieve of Eratosthenes.",
    "spaces_to_underscores": "Replace every space in the input string with an underscore.",
    "string_rotate": "Rotate a string by N positions.",
    "sum_of_digits": "Sum the digits of a non-negative integer.",
    "tax_calculator": "Read a pre-tax amount and a tax rate (percent), print the total.",
    "title_case": "Title-case each word in a sentence.",
    "url_parser": "Parse a URL query string into key=value pairs, sorted by key.",
    "vowel_counter": "Count vowels in a string.",
    "word_counter": "Count words in a sentence.",
    "word_frequency": "Count word frequencies in a sentence and print them sorted by word.",
    "word_length_histogram": "Print a histogram of word lengths.",
    "word_wrap": "Wrap a sentence at width N (arg2), preserving word boundaries.",
}


def describe(stem: str) -> str:
    """Derive a task description from a filename stem."""
    # Strip numbered suffixes: sort_ints_0027 -> sort_ints
    base = re.sub(r"_\d{4}$", "", stem)
    base = re.sub(r"_main$", "", base)
    if base in HINTS:
        return HINTS[base]
    # Generic fallback — readable but somewhat dry.
    pretty = base.replace("_", " ")
    return f"Write a Sigil program that implements {pretty}."


# ---------------------------------------------------------------------------
# Test-spec descriptions: the first test-spec's first case has a docstring.
# ---------------------------------------------------------------------------

TEST_SPEC_RE = re.compile(
    r'\(test-spec\s+(\w+)\s*\(case\s+"([^"]+)"',
    re.DOTALL,
)


def describe_test(code: str, stem: str) -> str:
    """Testfiles have (test-spec name (case "docstring" ...)). Use the first
    case docstring if we can find it; otherwise fall back to the filename."""
    m = TEST_SPEC_RE.search(code)
    if m:
        return f"Write a Sigil test that verifies: {m.group(2)}."
    return f"Write a Sigil test for {stem.replace('test_', '').replace('_', ' ')}."


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_generated_descs() -> dict[str, str]:
    """Map task id -> rich `desc` from generated_tasks.jsonl. The
    corpus_extender writes id.sigil for each spec; we want to keep the
    spec's natural-language description rather than re-deriving a generic
    one from the filename, since these descriptions are what the RAG
    layer embeds and matches against incoming queries."""
    p = REPO_ROOT / "benchmark" / "generated_tasks.jsonl"
    if not p.exists():
        return {}
    out = {}
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in d and "desc" in d:
                out[d["id"]] = d["desc"]
    return out


_GENERATED_DESCS_CACHE: dict[str, str] | None = None


def load_files(root: Path, describer) -> list[dict]:
    global _GENERATED_DESCS_CACHE
    if _GENERATED_DESCS_CACHE is None:
        _GENERATED_DESCS_CACHE = _load_generated_descs()
    gen_descs = _GENERATED_DESCS_CACHE

    out = []
    for p in sorted(root.rglob("*.sigil")):
        stem = p.stem
        code = p.read_text().rstrip() + "\n"
        # Prefer the rich generated_tasks.jsonl desc when present (these
        # are the corpus_extender outputs). Fall back to the filename
        # heuristic for everything else.
        if stem in gen_descs:
            task = gen_descs[stem]
        elif describer.__name__ == "describe_test":
            task = describer(code, stem)
        else:
            task = describer(stem)
        out.append({"stem": stem, "path": str(p.relative_to(REPO_ROOT)), "task": task, "code": code})
    return out


def dedupe_numbered(items: list[dict]) -> list[dict]:
    """If base_name and base_name_0012 both exist, keep only one (prefer base)."""
    bases = {re.sub(r"_\d{4}$", "", it["stem"]) for it in items}
    keep = []
    seen = set()
    for it in items:
        stem = it["stem"]
        base = re.sub(r"_\d{4}$", "", stem)
        if stem == base:  # base name, keep
            if base in seen:
                continue
            keep.append(it); seen.add(base)
        else:  # numbered variant
            if base in {i["stem"] for i in keep}:
                continue  # base exists, skip
            if base in seen:
                continue
            keep.append(it); seen.add(base)
    return keep


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def parses_clean(code: str) -> bool:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name],
                               capture_output=True, text=True, timeout=5)
            return "Parse error" not in r.stderr
        except subprocess.TimeoutExpired:
            return True
        finally:
            import os; os.unlink(f.name)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You write Sigil programs. Sigil is an S-expression language designed for "
    "minimal tokens. Programs may use (module name ...) wrapping or top-level "
    "script mode. CLI args: $0 is the first user arg as a string, #0 is the "
    "first as an int. Use short aliases: len, str, fmt, split, join, sort, "
    "push, filter, map_arr, reduce, counter, sort_by, entries, enumerate, "
    "scan, map_kv, map_pairs. Prefer functional pipelines over for-each+"
    "accumulator. Empty collections: [] and {}. Output ONLY raw Sigil code."
)


def to_message(item: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": item["task"]},
            {"role": "assistant", "content": item["code"].rstrip()},
        ]
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(REPO_ROOT / "benchmark" / "training_corpus.jsonl"))
    ap.add_argument("--dedupe", action="store_true",
                    help="Skip numbered variants if a base-name file exists")
    ap.add_argument("--include-opus-extensions", action="store_true",
                    help="Also load examples/corpus_extensions/*.sigil (from Opus generator)")
    ap.add_argument("--validate", action="store_true",
                    help="Parse each file with the interpreter; skip ones with parse errors")
    args = ap.parse_args()

    items = []
    items += load_files(REPO_ROOT / "examples" / "corpus", describe)
    items += load_files(REPO_ROOT / "tests", describe_test)
    if args.include_opus_extensions:
        ext = REPO_ROOT / "examples" / "corpus_extensions"
        if ext.exists():
            items += load_files(ext, describe)

    if args.dedupe:
        before = len(items)
        items = dedupe_numbered(items)
        print(f"dedupe: {before} -> {len(items)}")

    if args.validate:
        before = len(items)
        items = [it for it in items if parses_clean(it["code"])]
        print(f"validate: {before} -> {len(items)} after dropping parse errors")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for it in items:
            f.write(json.dumps(to_message(it)) + "\n")

    # Stats
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        total_tokens = sum(len(enc.encode(it["code"])) for it in items)
        print(f"\n{len(items)} examples -> {out_path}")
        print(f"Total code tokens: {total_tokens:,}")
        print(f"Avg tokens/example: {total_tokens / max(len(items), 1):.0f}")
    except ImportError:
        # Fallback: rough char/3.5 estimate
        total_chars = sum(len(it["code"]) for it in items)
        est = total_chars // 4
        print(f"\n{len(items)} examples -> {out_path}")
        print(f"Total chars: {total_chars:,}  (est ~{est:,} tokens)")
        print(f"Avg chars/example: {total_chars / max(len(items), 1):.0f}")


if __name__ == "__main__":
    main()
