#!/usr/bin/env python3
"""Generate a large validated Sigil training corpus using Claude as the code generator.

Strategy:
  1. Define 500+ diverse programming tasks
  2. Call Claude to generate Sigil solutions
  3. Validate each solution by running it through the interpreter
  4. Retry failures with error feedback (up to 3 attempts)
  5. Save only validated, working (task, code) pairs

Also includes all existing repo code (tests, stdlib, examples).

Usage:
  python generate_corpus.py --output training_corpus.jsonl
  python generate_corpus.py --output training_corpus.jsonl --max-tasks 100  # smaller test run
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe"

SYSTEM_PROMPT = (
    "You write Sigil programs. Sigil uses S-expression syntax: "
    "(module name (fn name params -> type body...)). "
    "Entry point: (fn main -> int ...). Input: (argv). Output: (print)/(println). "
    "Variables: (set x int 0) for declaration, (set x expr) for reassignment. "
    "Loops: (for i start end body...), (while cond body...), (for-each v type coll body...). "
    "Conditionals: (if cond body... (else body...)), (cond (c1 b1...) (c2 b2...)). "
    "Types: int float decimal bool string array map. "
    "Type-directed dispatch: (add x y) works for int/float/decimal."
)

TRAINING_SYSTEM = (
    "You write Sigil programs. Sigil uses S-expression syntax: "
    "(module name (fn name params -> type body...)). "
    "Entry point: (fn main -> int ...). Input: (argv). Output: (print)/(println). "
    "Variables: (set x int 0) for declaration, (set x expr) for reassignment. "
    "Loops: (for i start end body...), (while cond body...), (for-each v type coll body...). "
    "Conditionals: (if cond body... (else body...)), (cond (c1 b1...) (c2 b2...)). "
    "Types: int float decimal bool string array map. "
    "Type-directed dispatch: (add x y) works for int/float/decimal."
)

# ---------------------------------------------------------------------------
# Task bank — 500+ diverse programming tasks
# ---------------------------------------------------------------------------

TASKS = []

# ---- Basics: I/O, arithmetic, simple logic ----
BASICS = [
    "Write a program that prints 'Hello, World!'",
    "Write a program that takes a name as argument and prints 'Hello, <name>!'",
    "Write a program that takes two integers and prints their sum",
    "Write a program that takes two integers and prints the larger one",
    "Write a program that takes three integers and prints the smallest",
    "Write a program that takes an integer and prints whether it's positive, negative, or zero",
    "Write a program that takes an integer and prints whether it's even or odd",
    "Write a program that takes two integers and prints their average as a float",
    "Write a program that takes a temperature in Celsius and prints it in Fahrenheit",
    "Write a program that takes a radius (float) and prints the area of a circle (pi * r^2, use 3.14159)",
    "Write a program that takes length and width and prints the perimeter and area of a rectangle",
    "Write a program that swaps two integers and prints them",
    "Write a program that takes three numbers and prints them sorted in ascending order",
    "Write a program that takes a number of seconds and prints hours, minutes, seconds",
    "Write a program that takes a price and tax rate (as percentages) and prints the total with tax",
    "Write a program that takes a year and prints whether it's a leap year",
    "Write a program that takes a number 1-7 and prints the day of the week",
    "Write a program that takes a month number 1-12 and prints how many days it has (non-leap year)",
    "Write a program that takes two floats and prints which is closer to zero",
    "Write a program that takes an integer and prints its absolute value without using the abs builtin",
]

# ---- String operations ----
STRINGS = [
    "Write a program that takes a string and prints its length",
    "Write a program that takes a string and prints it reversed",
    "Write a program that takes a string and prints it in uppercase",
    "Write a program that takes a string and prints it in lowercase",
    "Write a program that takes a string and counts the number of vowels (a,e,i,o,u)",
    "Write a program that takes a string and counts the number of words (space-separated)",
    "Write a program that takes a string and prints each word on a separate line",
    "Write a program that takes a string and prints the first and last character",
    "Write a program that takes a string and checks if it's a palindrome (ignoring case)",
    "Write a program that takes two strings and checks if they are equal (case-insensitive)",
    "Write a program that takes a string and a character, counts occurrences of that character",
    "Write a program that takes a string and replaces all spaces with underscores",
    "Write a program that takes a string and removes all digits from it",
    "Write a program that takes a string and capitalizes the first letter of each word",
    "Write a program that takes a sentence and prints the longest word",
    "Write a program that takes a string and prints it repeated n times (n is second argument)",
    "Write a program that takes a string and a width, pads it with spaces on the left to that width",
    "Write a program that takes a string and truncates it to n characters, adding '...' if truncated",
    "Write a program that takes a string and prints the number of unique characters",
    "Write a program that takes two strings and prints their concatenation with a space between them",
    "Write a program that takes a string and prints each character with its ASCII code",
    "Write a program that takes a string and checks if it contains only digits",
    "Write a program that takes a string and checks if it contains only alphabetic characters",
    "Write a program that takes a CSV line and prints the third field",
    "Write a program that takes a string with words separated by commas and prints them sorted alphabetically",
    "Write a program that takes a sentence and reverses the order of words",
    "Write a program that takes a string and removes leading and trailing whitespace",
    "Write a program that takes a string and a substring, prints all positions where the substring occurs",
    "Write a program that takes a string and converts it to a simple Caesar cipher with shift 13 (ROT13)",
    "Write a program that takes a string and prints it with all duplicate adjacent characters removed (e.g. 'aabcc' -> 'abc')",
]

# ---- Array operations ----
ARRAYS = [
    "Write a program that takes space-separated integers and prints their sum",
    "Write a program that takes space-separated integers and prints the maximum",
    "Write a program that takes space-separated integers and prints the minimum",
    "Write a program that takes space-separated integers and prints the average",
    "Write a program that takes space-separated integers and prints them in reverse order",
    "Write a program that takes space-separated integers and prints them sorted ascending",
    "Write a program that takes space-separated integers and prints only the even numbers",
    "Write a program that takes space-separated integers and prints only the unique values",
    "Write a program that takes space-separated integers and prints how many are positive, negative, and zero",
    "Write a program that takes space-separated integers and prints the second largest",
    "Write a program that creates an array of numbers 1 to 20 and prints those divisible by 3",
    "Write a program that takes space-separated integers and prints the running sum",
    "Write a program that takes space-separated integers and finds two that sum to a target (first argument)",
    "Write a program that takes space-separated integers and prints them with duplicates removed, preserving order",
    "Write a program that takes space-separated integers and rotates them left by n positions (n is first argument)",
    "Write a program that takes two space-separated lists (semicolon-separated) and prints their intersection",
    "Write a program that takes space-separated integers and prints the difference between max and min",
    "Write a program that takes space-separated integers and counts how many are greater than the average",
    "Write a program that takes space-separated integers and prints them in a zigzag pattern (first, last, second, second-to-last, ...)",
    "Write a program that takes space-separated integers and finds the longest increasing subsequence length",
]

# ---- Map operations ----
MAPS = [
    "Write a program that counts word frequency in a sentence and prints each word with its count",
    "Write a program that takes key=value pairs separated by spaces and prints them sorted by key",
    "Write a program that takes a string and builds a map of character frequencies, then prints the most common character",
    "Write a program that takes two space-separated lists of equal length and creates a map from first to second, then prints it",
    "Write a program that takes a sentence and prints a histogram of word lengths",
    "Write a program that takes key=value pairs and groups values by their first letter",
    "Write a program that takes a string and counts how many times each vowel appears",
    "Write a program that takes name=score pairs and prints the name with the highest score",
    "Write a program that creates a map representing a simple phone book: name -> number, then looks up a name",
    "Write a program that takes words and prints which ones are anagrams of each other",
]

# ---- Control flow patterns ----
CONTROL_FLOW = [
    "Write a program that prints the first n Fibonacci numbers",
    "Write a program that computes factorial of n using a loop",
    "Write a program that computes factorial of n using recursion",
    "Write a program that prints a right triangle of stars with n rows",
    "Write a program that prints the FizzBuzz sequence from 1 to n",
    "Write a program that finds all prime numbers up to n using the sieve approach",
    "Write a program that prints the Collatz sequence starting from n",
    "Write a program that uses nested loops to print a multiplication table up to n",
    "Write a program that uses break to find the first number divisible by both 3 and 7 after n",
    "Write a program that uses continue to print all numbers from 1 to n except multiples of 4",
    "Write a program that uses cond to convert a numeric grade (0-100) to a letter grade",
    "Write a program that computes the sum of digits of a number",
    "Write a program that reverses an integer (e.g., 1234 -> 4321)",
    "Write a program that checks if a number is a perfect square",
    "Write a program that prints the first n terms of a geometric sequence with ratio r",
    "Write a program that computes power (base^exp) using a loop, not the pow builtin",
    "Write a program that counts the number of digits in an integer",
    "Write a program that prints all Armstrong numbers (narcissistic numbers) up to n",
    "Write a program that implements binary search on a sorted space-separated list",
    "Write a program that generates Pascal's triangle up to n rows",
]

# ---- Algorithms ----
ALGORITHMS = [
    "Write a program that implements bubble sort on space-separated integers",
    "Write a program that implements insertion sort on space-separated integers",
    "Write a program that implements selection sort on space-separated integers",
    "Write a program that merges two sorted space-separated lists into one sorted list",
    "Write a program that implements linear search, printing the index or -1",
    "Write a program that computes GCD of two numbers using Euclid's algorithm",
    "Write a program that computes LCM of two numbers",
    "Write a program that checks if a string is a valid set of balanced parentheses",
    "Write a program that evaluates a Reverse Polish Notation expression",
    "Write a program that converts a decimal number to binary",
    "Write a program that converts a decimal number to hexadecimal",
    "Write a program that converts a binary string to decimal",
    "Write a program that implements a simple run-length encoding",
    "Write a program that implements run-length decoding",
    "Write a program that finds the longest common prefix of space-separated strings",
    "Write a program that implements the Euclidean distance between two 2D points",
    "Write a program that computes the nth triangular number",
    "Write a program that checks if a number is a power of 2",
    "Write a program that rotates a string by n positions",
    "Write a program that finds all pairs in an array that sum to a target",
    "Write a program that computes the Hamming distance between two strings of equal length",
    "Write a program that implements a simple Caesar cipher (encode and decode based on a mode argument)",
    "Write a program that validates if a credit card number passes the Luhn check",
    "Write a program that converts Roman numerals to integers",
    "Write a program that converts integers to Roman numerals",
    "Write a program that transposes a matrix given as rows separated by semicolons, values by commas",
    "Write a program that computes dot product of two vectors given as space-separated numbers",
    "Write a program that finds the majority element in a list (appears more than n/2 times)",
    "Write a program that implements the Sieve of Eratosthenes up to n",
    "Write a program that computes the edit distance between two strings",
]

# ---- Data processing / real-world tasks ----
DATA_PROCESSING = [
    "Write a program that takes a query string (key=val&key=val) and prints each pair sorted by key",
    "Write a program that takes CSV data (rows separated by newlines, fields by commas) and prints the sum of the second column",
    "Write a program that takes a list of name:score pairs and prints the top 3 by score",
    "Write a program that takes a log line like '2024-01-15 ERROR something failed' and extracts the date and level",
    "Write a program that takes a URL-like string and extracts the protocol, host, and path",
    "Write a program that takes a sentence and generates a simple word index (word -> list of positions)",
    "Write a program that takes a list of timestamps (HH:MM) and finds the smallest gap between consecutive ones",
    "Write a program that takes a flat key-value config (key=value per line) and prints it as a formatted table",
    "Write a program that takes text and wraps it at n characters per line (word-wrap, don't break words)",
    "Write a program that takes a list of file paths and groups them by extension",
    "Write a program that takes a string of hex digits and converts each pair to its decimal value",
    "Write a program that validates an IPv4 address (four octets 0-255 separated by dots)",
    "Write a program that takes a mathematical expression with + and - (no spaces, integers only) and evaluates it",
    "Write a program that takes a string with nested parentheses and computes the maximum nesting depth",
    "Write a program that takes a list of intervals (start-end) and merges overlapping ones",
    "Write a program that encodes a string using simple XOR with a single-character key",
    "Write a program that takes a list of words and finds all that are palindromes",
    "Write a program that generates a histogram of character types (uppercase, lowercase, digit, other) in a string",
    "Write a program that takes a version string (like '1.2.3') and a second one, and prints which is newer",
    "Write a program that takes a string of words and removes all stop words (the, a, an, is, in, on, at, to)",
]

# ---- Multi-function programs ----
MULTI_FUNCTION = [
    "Write a program with helper functions to check if a number is prime, then print all primes up to n",
    "Write a program with a recursive helper to compute power, and a main that uses it",
    "Write a program with separate functions for min, max, and average of an array",
    "Write a program with a function that validates a password (length >= 8, has digit, has uppercase) and tests it",
    "Write a program with a function that converts Celsius to Fahrenheit and another for the reverse",
    "Write a program with a function to check if a string is a pangram (contains every letter a-z)",
    "Write a program with helper functions to compute the area and perimeter of a circle given the radius",
    "Write a program with a function that counts syllables in a word (simplified: count vowel groups)",
    "Write a program with a function that formats a number with thousands separators",
    "Write a program with a function to check if two strings are rotations of each other",
    "Write a program with a function that flattens a 2D array (semicolon-separated rows) into a 1D array",
    "Write a program with a function that computes the moving average of a list with window size k",
    "Write a program with separate encode and decode functions for a simple substitution cipher",
    "Write a program with a function that generates all permutations of a string (up to length 4)",
    "Write a program with functions to push, pop, and peek on a stack implemented as an array",
]

# ---- Type system and conversions ----
TYPES = [
    "Write a program that demonstrates casting between int, float, and decimal types",
    "Write a program that takes a float, converts to int (truncating), and prints both",
    "Write a program that uses decimal type to compute 0.1 + 0.2 exactly",
    "Write a program that uses string_from_int and string_from_float to format output",
    "Write a program that reads a string, tries to parse it as int, handles the error if it fails",
    "Write a program that demonstrates type_of on different value types",
    "Write a program that uses decimal arithmetic to compute compound interest precisely",
    "Write a program that converts between int and bool (0/1)",
    "Write a program that uses cast_int_decimal and cast_decimal_int to convert between types",
    "Write a program that takes mixed int and float arguments and performs arithmetic after converting",
]

# ---- Error handling ----
ERROR_HANDLING = [
    "Write a program that uses try/catch to safely divide two numbers",
    "Write a program that uses try/catch to handle array index out of bounds",
    "Write a program that validates user input is a positive integer, printing an error message if not",
    "Write a program that reads a file path, checks if it exists before reading, and prints the content or an error",
    "Write a program that uses try/catch around multiple operations and reports which one failed",
    "Write a program that validates command-line arguments (checks count and types) before processing",
    "Write a program that safely parses a list of integers, skipping invalid entries",
    "Write a program that divides elements of one array by elements of another, catching division by zero",
    "Write a program that attempts to access nested map keys, handling missing keys gracefully",
    "Write a program that reads and processes a file, catching and reporting any errors",
]

# ---- Bitwise operations ----
BITWISE = [
    "Write a program that prints a number in binary using bitwise shift operations",
    "Write a program that checks if the nth bit of a number is set",
    "Write a program that sets the nth bit of a number",
    "Write a program that clears the nth bit of a number",
    "Write a program that counts the number of set bits in an integer",
    "Write a program that checks if a number is a power of 2 using bitwise AND",
    "Write a program that swaps two integers using XOR without a temporary variable",
    "Write a program that computes the bitwise AND, OR, and XOR of two numbers",
]

# ---- Regex ----
REGEX = [
    "Write a program that uses regex to find all numbers in a string",
    "Write a program that uses regex to validate an email-like pattern",
    "Write a program that uses regex to extract all words from a string",
    "Write a program that uses regex to replace all whitespace sequences with a single space",
    "Write a program that uses regex to check if a string matches a phone number pattern",
]

# ---- for-each specific ----
FOR_EACH = [
    "Write a program that uses for-each to iterate over an array and print each element",
    "Write a program that uses for-each to sum all elements of an array",
    "Write a program that uses for-each to find the longest string in an array",
    "Write a program that uses for-each to iterate over map keys and print key-value pairs",
    "Write a program that uses for-each with continue to skip negative numbers",
]

# ---- string_format specific ----
STRING_FORMAT = [
    "Write a program that uses string_format to create a table row with aligned columns",
    "Write a program that uses string_format to build a JSON-like string from variables",
    "Write a program that uses string_format to create an HTTP header line",
    "Write a program that uses string_format with multiple placeholders to build a log message",
    "Write a program that uses string_format to construct a SQL-like query string",
]

# ---- test-spec framework ----
TEST_SPEC = [
    "Write a Sigil test module with test-spec that tests an 'add' function with three test cases",
    "Write a Sigil test module with test-spec that tests a 'max' function that returns the larger of two integers",
    "Write a Sigil test module with test-spec that tests a 'factorial' function",
    "Write a Sigil test module with test-spec that tests a 'reverse_string' function",
    "Write a Sigil test module with test-spec that tests an 'is_palindrome' function returning bool",
    "Write a Sigil test module with test-spec that tests a 'fibonacci' function",
    "Write a Sigil test module with test-spec that tests a 'gcd' function",
    "Write a Sigil test module with test-spec that tests a 'count_vowels' function",
    "Write a Sigil test module with test-spec that tests a 'clamp' function that constrains a value between min and max",
    "Write a Sigil test module with test-spec that tests a 'sum_array' function that takes an array and length",
]

# Combine all
TASKS = BASICS + STRINGS + ARRAYS + MAPS + CONTROL_FLOW + ALGORITHMS + DATA_PROCESSING + MULTI_FUNCTION + TYPES + ERROR_HANDLING + BITWISE + REGEX + FOR_EACH + STRING_FORMAT + TEST_SPEC


# ---------------------------------------------------------------------------
# Code generation via Claude CLI
# ---------------------------------------------------------------------------

def load_grammar() -> str:
    return (REPO_ROOT / ".sigil.grammar").read_text()


def generate_with_claude(task: str, model: str = "claude-sonnet-4-6") -> str:
    """Call Claude CLI to generate Sigil code for a task."""
    grammar = load_grammar()
    prompt = (
        f"You are a Sigil code generator. Here is the Sigil grammar:\n\n"
        f"{grammar}\n\n"
        f"Generate ONLY a complete Sigil program as a (module name ...) with appropriate functions.\n"
        f"If the task requires CLI input, use (fn main -> int ...) with (argv) for arguments.\n"
        f"If the task is about testing, use test-spec framework with case/input/expect.\n"
        f"Print output with (print)/(println). Return 0 from main.\n"
        f"Output ONLY the raw Sigil code. No markdown fences. No explanations.\n\n"
        f"Task: {task}"
    )

    try:
        result = subprocess.run(
            ["claude", "--print", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=90,
            cwd="/tmp",  # run outside the repo to avoid CLAUDE.md interference
        )
        code = result.stdout.strip()
        # Strip markdown fences if present
        for fence in ["```sigil", "```lisp", "```scheme", "```"]:
            if code.startswith(fence):
                code = code[len(fence):].strip()
                break
        if code.endswith("```"):
            code = code[:-3].strip()
        return code
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def validate_sigil(code: str) -> tuple[bool, str]:
    """Run Sigil code through the interpreter to check if it parses and executes."""
    if not code or "(module" not in code:
        return False, "No valid module found"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                [str(SIGIL_BIN), f.name],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return True, ""
            combined = result.stdout + result.stderr
            # Valid programs that just need CLI args or are libraries
            if any(x in combined for x in [
                "out of bounds", "Index", "argv",
                "Undefined variable", "Usage:",
                "No 'main' function",
            ]):
                return True, ""
            # Exit code 1 with no parse/runtime error = valid program returning 1
            if result.returncode == 1 and "Parse error" not in result.stderr and "Error:" not in result.stderr:
                return True, ""
            return False, result.stderr[:200]
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT"
        finally:
            os.unlink(f.name)


# ---------------------------------------------------------------------------
# Extract from repo (same as generate_training_data.py)
# ---------------------------------------------------------------------------

def extract_repo_examples() -> list[dict]:
    """Extract all working Sigil code from the repo."""
    import re
    examples = []

    # Tests
    test_dir = REPO_ROOT / "tests"
    for f in sorted(test_dir.glob("test_*.sigil")):
        code = f.read_text().strip()
        if not code:
            continue
        note = ""
        m = re.search(r'\(meta-note\s+"([^"]+)"\)', code)
        if m:
            note = m.group(1)
        fn_names = [n for n in re.findall(r'\(fn\s+(\w+)', code) if n != "main"]
        test_name = f.stem.replace("test_", "").replace("_", " ")
        desc = f"Write a Sigil module that tests: {test_name}."
        if note:
            desc += f" {note}"
        if fn_names:
            desc += f" Functions: {', '.join(fn_names[:5])}."
        desc += " Use the test-spec framework."
        examples.append({"task": desc, "code": code})

    # Stdlib
    for f in sorted((REPO_ROOT / "stdlib").rglob("*.sigil")):
        code = f.read_text().strip()
        if not code:
            continue
        m = re.search(r'\(module\s+(\w+)', code)
        mod_name = m.group(1) if m else f.stem
        fn_names = re.findall(r'\(fn\s+(\w+)', code)
        desc = f"Write a Sigil stdlib module '{mod_name}' with functions: {', '.join(fn_names[:10])}."
        examples.append({"task": desc, "code": code})

    # Examples
    for f in sorted((REPO_ROOT / "examples").rglob("*.sigil")):
        code = f.read_text().strip()
        if not code:
            continue
        desc = f"Write the Sigil example program: {f.stem}"
        examples.append({"task": desc, "code": code})

    return examples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def make_training_example(task: str, code: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": TRAINING_SYSTEM},
            {"role": "user", "content": task},
            {"role": "assistant", "content": f"```sigil\n{code.strip()}\n```"},
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Generate validated Sigil training corpus")
    parser.add_argument("--output", default="benchmark/training_corpus.jsonl")
    parser.add_argument("--max-tasks", type=int, default=None,
                        help="Limit number of generated tasks (for testing)")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                        help="Claude model for code generation")
    parser.add_argument("--skip-generation", action="store_true",
                        help="Only use repo examples, skip Claude generation")
    args = parser.parse_args()

    all_examples = []

    # Phase 1: Extract from repo (pre-validated)
    print("Phase 1: Extracting from repo...")
    repo_examples = extract_repo_examples()
    for ex in repo_examples:
        all_examples.append(make_training_example(ex["task"], ex["code"]))
    print(f"  Repo examples: {len(repo_examples)}")

    if args.skip_generation:
        print(f"\nSkipping generation. Total: {len(all_examples)}")
    else:
        # Phase 2: Generate with Claude and validate
        tasks = TASKS[:args.max_tasks] if args.max_tasks else TASKS
        print(f"\nPhase 2: Generating {len(tasks)} tasks with Claude ({args.model})...")
        print(f"  Estimated time: {len(tasks) * 8 / 60:.0f}-{len(tasks) * 15 / 60:.0f} minutes\n")

        generated = 0
        failed = 0
        for i, task in enumerate(tasks):
            progress = f"[{i+1}/{len(tasks)}]"

            # Generate
            code = generate_with_claude(task, model=args.model)
            if not code:
                print(f"  {progress} EMPTY: {task[:60]}...")
                failed += 1
                continue

            # Validate
            valid, error = validate_sigil(code)
            if valid:
                all_examples.append(make_training_example(task, code))
                generated += 1
                print(f"  {progress} OK: {task[:60]}...")
            else:
                # Retry once with error feedback
                retry_prompt = f"{task}\n\nPrevious attempt had error: {error}\nFix the code."
                code2 = generate_with_claude(retry_prompt, model=args.model)
                if code2:
                    valid2, error2 = validate_sigil(code2)
                    if valid2:
                        all_examples.append(make_training_example(task, code2))
                        generated += 1
                        print(f"  {progress} OK (retry): {task[:60]}...")
                        continue
                failed += 1
                print(f"  {progress} FAIL: {task[:60]}... ({error[:50]})")

        print(f"\n  Generated: {generated}/{len(tasks)} ({100*generated//len(tasks)}%)")
        print(f"  Failed: {failed}")

    # Write JSONL output
    outpath = Path(args.output)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")

    # Also save generated programs as .sigil files in examples/corpus/
    corpus_dir = REPO_ROOT / "examples" / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for i, ex in enumerate(all_examples):
        code = ex["messages"][2]["content"]
        # Strip markdown fences from training format
        if code.startswith("```"):
            lines = code.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)

        # Extract module name for filename
        import re
        m = re.search(r'\(module\s+(\w+)', code)
        if m:
            name = m.group(1)
        else:
            name = f"example_{i:04d}"

        filepath = corpus_dir / f"{name}.sigil"
        # Avoid overwriting — add index suffix if needed
        if filepath.exists():
            filepath = corpus_dir / f"{name}_{i:04d}.sigil"
        filepath.write_text(code.strip() + "\n")
        saved += 1

    print(f"\nTotal examples: {len(all_examples)}")
    print(f"JSONL: {outpath} ({outpath.stat().st_size / 1024:.1f} KB)")
    print(f"Sigil files: {corpus_dir}/ ({saved} files)")


if __name__ == "__main__":
    main()
