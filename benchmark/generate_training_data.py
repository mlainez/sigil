#!/usr/bin/env python3
"""Generate comprehensive Sigil training data for fine-tuning.

Sources:
  1. All 142 test files — converted to standalone programs
  2. All 17 stdlib modules — as examples of idiomatic Sigil
  3. Example programs (chat server, todo app, hello world)
  4. Synthetic examples covering every builtin and pattern
  5. Grammar-teaching examples (explain what constructs do)

Target: 300-500 high-quality examples.
"""

import json
import os
import re
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent.parent

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


def make_example(task: str, code: str, system: str = SYSTEM_PROMPT) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
            {"role": "assistant", "content": f"```sigil\n{code.strip()}\n```"},
        ]
    }


# ---------------------------------------------------------------------------
# Source 1: Extract from test files
# ---------------------------------------------------------------------------

def extract_from_tests() -> list[dict]:
    """Convert test files into training examples."""
    examples = []
    test_dir = REPO_ROOT / "tests"

    for f in sorted(test_dir.glob("test_*.sigil")):
        code = f.read_text().strip()
        if not code:
            continue

        # Extract meta-note for description
        note = ""
        m = re.search(r'\(meta-note\s+"([^"]+)"\)', code)
        if m:
            note = m.group(1)

        # Extract function names and test cases for description
        fn_names = re.findall(r'\(fn\s+(\w+)', code)
        fn_names = [n for n in fn_names if n != "main"]

        if not fn_names:
            continue

        # Build description from test file
        test_name = f.stem.replace("test_", "").replace("_", " ")
        desc = f"Write a Sigil module that implements and tests: {test_name}."
        if note:
            desc += f" {note}"
        if fn_names:
            desc += f" Functions: {', '.join(fn_names[:5])}."
        desc += " Use the test-spec framework with case/input/expect."

        examples.append(make_example(desc, code))

    return examples


# ---------------------------------------------------------------------------
# Source 2: Extract from stdlib modules
# ---------------------------------------------------------------------------

def extract_from_stdlib() -> list[dict]:
    """Use stdlib modules as examples of idiomatic Sigil."""
    examples = []
    stdlib_dir = REPO_ROOT / "stdlib"

    for f in sorted(stdlib_dir.rglob("*.sigil")):
        code = f.read_text().strip()
        if not code:
            continue

        # Extract module name
        m = re.search(r'\(module\s+(\w+)', code)
        mod_name = m.group(1) if m else f.stem

        # Extract function names
        fn_names = re.findall(r'\(fn\s+(\w+)', code)

        # Extract meta-note
        note = ""
        m = re.search(r'\(meta-note\s+"([^"]*)"', code, re.DOTALL)
        if m:
            note = m.group(1).split("\n")[0]

        # Build description
        subdir = f.parent.name
        desc = f"Write a Sigil stdlib module '{mod_name}' (category: {subdir}) with functions: {', '.join(fn_names[:10])}."
        if note:
            desc += f" {note}"
        desc += " Write it in pure Sigil with no external dependencies."

        examples.append(make_example(desc, code))

    return examples


# ---------------------------------------------------------------------------
# Source 3: Example programs
# ---------------------------------------------------------------------------

def extract_from_examples() -> list[dict]:
    """Use example programs as training data."""
    examples = []

    # Hello world
    hw = (REPO_ROOT / "examples" / "hello_world.sigil").read_text().strip()
    examples.append(make_example("Write a simple Sigil program that prints 'Hello from Sigil!'", hw))

    # Chat server
    cs = (REPO_ROOT / "examples" / "chat_app" / "chat_server.sigil").read_text().strip()
    examples.append(make_example(
        "Write a WebSocket chat server in Sigil that listens on port 8080, "
        "accepts WebSocket connections, and broadcasts messages to all connected clients. "
        "Use socket_select for non-blocking I/O.",
        cs
    ))

    # Chat client
    cc = (REPO_ROOT / "examples" / "chat_app" / "chat_client.sigil").read_text().strip()
    examples.append(make_example(
        "Write a WebSocket chat client in Sigil with an HTTP interface. "
        "It connects to a WebSocket chat server and provides HTTP endpoints for "
        "sending messages and polling for new messages. Serves an HTML chat UI.",
        cc
    ))

    # Todo app
    ta = (REPO_ROOT / "examples" / "todo_app" / "todo_app.sigil").read_text().strip()
    examples.append(make_example(
        "Write a TODO web application in Sigil with SQLite backend. "
        "HTTP server on port 8080 with REST API: GET / serves HTML, "
        "GET /api/add?text=... adds todos, GET /api/toggle?id=... toggles done state, "
        "GET /api/delete?id=... deletes. Use socket_select for non-blocking I/O.",
        ta
    ))

    return examples


# ---------------------------------------------------------------------------
# Source 4: Synthetic examples — systematic builtin coverage
# ---------------------------------------------------------------------------

def generate_arithmetic_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that takes two integers and prints their sum, difference, product, and quotient, each on a separate line.",
        dedent("""\
        (module arith
          (fn main -> int
            (set a int (string_to_int (array_get (argv) 0)))
            (set b int (string_to_int (array_get (argv) 1)))
            (println (add a b))
            (println (sub a b))
            (println (mul a b))
            (println (div a b))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes a float and prints its floor, ceiling, and rounded value.",
        dedent("""\
        (module rounding
          (fn main -> int
            (set f float (string_to_float (array_get (argv) 0)))
            (println (floor f))
            (println (ceil f))
            (println (round f))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that computes the absolute value, negation, min and max of two integers.",
        dedent("""\
        (module math_ops
          (fn main -> int
            (set a int (string_to_int (array_get (argv) 0)))
            (set b int (string_to_int (array_get (argv) 1)))
            (println (abs a))
            (println (neg a))
            (println (min a b))
            (println (max a b))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes a base and exponent (floats) and prints the result of pow, then the square root of the base.",
        dedent("""\
        (module pow_sqrt
          (fn main -> int
            (set base float (string_to_float (array_get (argv) 0)))
            (set exp float (string_to_float (array_get (argv) 1)))
            (println (pow base exp))
            (println (sqrt base))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that demonstrates decimal precision: add 0.1 and 0.2 using both float and decimal types, printing both results.",
        dedent("""\
        (module decimal_demo
          (fn main -> int
            (set f_result float (add 0.1 0.2))
            (set d_result decimal (add 0.1d 0.2d))
            (println f_result)
            (println d_result)
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that computes modulo and checks if a number is even or odd.",
        dedent("""\
        (module mod_check
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (set remainder int (mod n 2))
            (if (eq remainder 0)
              (println "even")
              (else
                (println "odd")))
            (ret 0)))""")
    ))

    return examples


def generate_string_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that takes a string and prints its length, uppercase version, and lowercase version.",
        dedent("""\
        (module str_ops
          (fn main -> int
            (set s string (array_get (argv) 0))
            (println (string_length s))
            (println (string_to_upper s))
            (println (string_to_lower s))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes a string and prints it trimmed, then reversed character by character.",
        dedent("""\
        (module str_trim_rev
          (fn main -> int
            (set s string (string_trim (array_get (argv) 0)))
            (println s)
            (set len int (string_length s))
            (set rev string "")
            (set i int (sub len 1))
            (while (ge i 0)
              (set rev (string_concat rev (string_slice s i 1)))
              (set i (sub i 1)))
            (println rev)
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that splits a CSV line by commas and prints each field on its own line.",
        dedent("""\
        (module csv_split
          (fn main -> int
            (set line string (array_get (argv) 0))
            (set fields array (string_split line ","))
            (set len int (array_length fields))
            (for i 0 len
              (println (string_trim (array_get fields i))))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes a string and a search term, and prints whether the string contains the search term, starts with it, and ends with it.",
        dedent("""\
        (module str_search
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set term string (array_get (argv) 1))
            (println (string_contains s term))
            (println (string_starts_with s term))
            (println (string_ends_with s term))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses string_format to build a greeting from a name and age.",
        dedent("""\
        (module greeting
          (fn main -> int
            (set name string (array_get (argv) 0))
            (set age string (array_get (argv) 1))
            (println (string_format "Hello, {}! You are {} years old." name age))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes a string and replaces all occurrences of 'old' with 'new', then prints the result.",
        dedent("""\
        (module str_replace
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set old_str string (array_get (argv) 1))
            (set new_str string (array_get (argv) 2))
            (println (string_replace s old_str new_str))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes a string and an index, prints the character code at that index, then converts it back to a character.",
        dedent("""\
        (module char_ops
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set idx int (string_to_int (array_get (argv) 1)))
            (set code int (string_get s idx))
            (println code)
            (println (char_from_code code))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that joins an array of words with a separator.",
        dedent("""\
        (module str_join
          (fn main -> int
            (set words array (string_split (array_get (argv) 0) " "))
            (set sep string (array_get (argv) 1))
            (println (string_join words sep))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that finds the position of a substring in a string, printing -1 if not found.",
        dedent("""\
        (module str_find
          (fn main -> int
            (set haystack string (array_get (argv) 0))
            (set needle string (array_get (argv) 1))
            (println (string_find haystack needle))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes a string, a start position, and a length, and prints the substring.",
        dedent("""\
        (module substr
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set start int (string_to_int (array_get (argv) 1)))
            (set len int (string_to_int (array_get (argv) 2)))
            (println (string_slice s start len))
            (ret 0)))""")
    ))

    return examples


def generate_array_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that creates an array, pushes 5 numbers, then prints the array length and each element.",
        dedent("""\
        (module array_ops
          (fn main -> int
            (set arr array (array_new))
            (for i 1 6
              (array_push arr (mul i 10)))
            (println (array_length arr))
            (for i 0 (array_length arr)
              (println (array_get arr i)))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes space-separated integers, sorts them, and prints the sorted array.",
        dedent("""\
        (module sort_nums
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set nums array (array_new))
            (for i 0 (array_length parts)
              (array_push nums (string_to_int (array_get parts i))))
            (array_sort nums)
            (for i 0 (array_length nums)
              (if (gt i 0) (print " "))
              (print (array_get nums i)))
            (println "")
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that reverses an array and prints it.",
        dedent("""\
        (module rev_array
          (fn main -> int
            (set arr array [5 4 3 2 1])
            (array_reverse arr)
            (for i 0 (array_length arr)
              (if (gt i 0) (print " "))
              (print (array_get arr i)))
            (println "")
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that takes space-separated numbers and prints the sum, min, and max.",
        dedent("""\
        (module array_stats
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set len int (array_length parts))
            (set sum int 0)
            (set min_val int (string_to_int (array_get parts 0)))
            (set max_val int min_val)
            (for i 0 len
              (set v int (string_to_int (array_get parts i)))
              (set sum (add sum v))
              (if (lt v min_val) (set min_val v))
              (if (gt v max_val) (set max_val v)))
            (println (string_format "sum={} min={} max={}" (string_from_int sum) (string_from_int min_val) (string_from_int max_val)))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses array literals and demonstrates array_contains and array_index_of.",
        dedent("""\
        (module array_search
          (fn main -> int
            (set fruits array ["apple" "banana" "cherry" "date"])
            (set target string (array_get (argv) 0))
            (println (array_contains fruits target))
            (println (array_index_of fruits target))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that slices an array and concatenates two arrays.",
        dedent("""\
        (module array_slice_concat
          (fn main -> int
            (set a array [1 2 3 4 5])
            (set b array [6 7 8])
            (set sliced array (array_slice a 1 3))
            (set combined array (array_concat sliced b))
            (for i 0 (array_length combined)
              (println (array_get combined i)))
            (ret 0)))""")
    ))

    return examples


def generate_map_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that creates a map with name, age, and city, then prints each key-value pair.",
        dedent("""\
        (module map_demo
          (fn main -> int
            (set person map {"name" "Alice" "age" "30" "city" "Paris"})
            (set keys array (map_keys person))
            (for i 0 (array_length keys)
              (set k string (array_get keys i))
              (println (string_format "{}={}" k (map_get person k))))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that counts character frequencies using a map.",
        dedent("""\
        (module char_freq
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set freq map (map_new))
            (for i 0 (string_length s)
              (set ch string (string_slice s i 1))
              (if (map_has freq ch)
                (set cur int (map_get freq ch))
                (map_set freq ch (add cur 1))
                (else
                  (map_set freq ch 1))))
            (set keys array (map_keys freq))
            (array_sort keys)
            (for i 0 (array_length keys)
              (set k string (array_get keys i))
              (println (string_format "{} {}" k (string_from_int (map_get freq k)))))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that demonstrates map operations: has, get, set, delete, length.",
        dedent("""\
        (module map_ops
          (fn main -> int
            (set m map (map_new))
            (map_set m "x" 10)
            (map_set m "y" 20)
            (println (map_length m))
            (println (map_has m "x"))
            (println (map_get m "x"))
            (map_delete m "x")
            (println (map_has m "x"))
            (println (map_length m))
            (ret 0)))""")
    ))

    return examples


def generate_control_flow_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that uses a for loop to compute the sum of integers from 1 to n.",
        dedent("""\
        (module sum_to_n
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (set total int 0)
            (for i 1 (add n 1)
              (set total (add total i)))
            (println total)
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses while loop to find the first power of 2 greater than n.",
        dedent("""\
        (module next_pow2
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (set p int 1)
            (while (le p n)
              (set p (mul p 2)))
            (println p)
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses break to find the first negative number in a list.",
        dedent("""\
        (module first_negative
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set found int -1)
            (for i 0 (array_length parts)
              (set v int (string_to_int (array_get parts i)))
              (if (lt v 0)
                (set found v)
                (break)))
            (println found)
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses continue to skip odd numbers and sum only even numbers from 1 to n.",
        dedent("""\
        (module sum_evens
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (set total int 0)
            (for i 1 (add n 1)
              (if (eq (mod i 2) 1)
                (continue))
              (set total (add total i)))
            (println total)
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses cond to classify a temperature as cold, mild, warm, or hot.",
        dedent("""\
        (module temp_class
          (fn main -> int
            (set temp int (string_to_int (array_get (argv) 0)))
            (cond
              ((lt temp 0) (println "freezing"))
              ((lt temp 15) (println "cold"))
              ((lt temp 25) (println "mild"))
              ((lt temp 35) (println "warm"))
              (true (println "hot")))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses if-else to determine the sign of a number.",
        dedent("""\
        (module sign
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (if (gt n 0)
              (println "positive")
              (else
                (if (lt n 0)
                  (println "negative")
                  (else
                    (println "zero")))))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses nested for loops to print a multiplication table.",
        dedent("""\
        (module mult_table
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (for i 1 (add n 1)
              (set line string "")
              (for j 1 (add n 1)
                (if (gt j 1)
                  (set line (string_concat line "\t")))
                (set line (string_concat line (string_from_int (mul i j)))))
              (println line))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses for-each to iterate over an array and print each element doubled.",
        dedent("""\
        (module foreach_demo
          (fn main -> int
            (set nums array [10 20 30 40 50])
            (for-each val int nums
              (println (mul val 2)))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses loop with break to implement a simple REPL that echoes input until 'quit'.",
        dedent("""\
        (module repl
          (fn main -> int
            (loop
              (print "> ")
              (set line string (read_line))
              (if (string_equals line "quit")
                (break))
              (println (string_format "echo: {}" line)))
            (ret 0)))""")
    ))

    return examples


def generate_function_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program with a recursive factorial function.",
        dedent("""\
        (module factorial
          (fn factorial n int -> int
            (if (le n 1) (ret 1))
            (ret (mul n (factorial (sub n 1)))))
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (println (factorial n))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program with a recursive fibonacci function.",
        dedent("""\
        (module fib
          (fn fib n int -> int
            (if (le n 1) (ret n))
            (ret (add (fib (sub n 1)) (fib (sub n 2)))))
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (println (fib n))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program with a helper function that checks if a number is prime.",
        dedent("""\
        (module is_prime
          (fn is_prime n int -> bool
            (if (lt n 2) (ret false))
            (set i int 2)
            (while (le (mul i i) n)
              (if (eq (mod n i) 0)
                (ret false))
              (set i (add i 1)))
            (ret true))
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (if (is_prime n)
              (println "prime")
              (else
                (println "not prime")))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program with a GCD function using Euclid's algorithm.",
        dedent("""\
        (module gcd
          (fn gcd a int b int -> int
            (while (ne b 0)
              (set temp int b)
              (set b (mod a b))
              (set a temp))
            (ret a))
          (fn main -> int
            (set a int (string_to_int (array_get (argv) 0)))
            (set b int (string_to_int (array_get (argv) 1)))
            (println (gcd a b))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program with a binary search function.",
        dedent("""\
        (module bsearch
          (fn binary_search arr array target int -> int
            (set lo int 0)
            (set hi int (sub (array_length arr) 1))
            (while (le lo hi)
              (set mid int (div (add lo hi) 2))
              (set val int (array_get arr mid))
              (cond
                ((eq val target) (ret mid))
                ((lt val target) (set lo (add mid 1)))
                (true (set hi (sub mid 1)))))
            (ret -1))
          (fn main -> int
            (set arr array [1 3 5 7 9 11 13])
            (set target int (string_to_int (array_get (argv) 0)))
            (println (binary_search arr target))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program with multiple helper functions to validate a password (length >= 8, has digit, has uppercase).",
        dedent("""\
        (module password
          (fn has_digit s string -> bool
            (for i 0 (string_length s)
              (set c int (string_get s i))
              (if (and (ge c 48) (le c 57))
                (ret true)))
            (ret false))
          (fn has_upper s string -> bool
            (for i 0 (string_length s)
              (set c int (string_get s i))
              (if (and (ge c 65) (le c 90))
                (ret true)))
            (ret false))
          (fn validate pw string -> string
            (if (lt (string_length pw) 8)
              (ret "too short"))
            (if (not (has_digit pw))
              (ret "needs digit"))
            (if (not (has_upper pw))
              (ret "needs uppercase"))
            (ret "valid"))
          (fn main -> int
            (println (validate (array_get (argv) 0)))
            (ret 0)))""")
    ))

    return examples


def generate_type_conversion_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that demonstrates all type conversions between int, float, and string.",
        dedent("""\
        (module conversions
          (fn main -> int
            (set i int 42)
            (set f float (cast_int_float i))
            (set s string (string_from_int i))
            (set f2 float 3.14)
            (set i2 int (cast_float_int f2))
            (set s2 string (string_from_float f2))
            (println (string_format "int {} -> float {} -> string {}" (string_from_int i) (string_from_float f) s))
            (println (string_format "float {} -> int {} -> string {}" (string_from_float f2) (string_from_int i2) s2))
            (println (type_of i))
            (println (type_of f))
            (println (type_of s))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that reads a string, converts it to int and float, and prints the types.",
        dedent("""\
        (module parse_types
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set i int (string_to_int s))
            (set f float (string_to_float s))
            (println (string_format "string: {} int: {} float: {}" s (string_from_int i) (string_from_float f)))
            (ret 0)))""")
    ))

    return examples


def generate_error_handling_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that uses try/catch to handle division by zero.",
        dedent("""\
        (module safe_div
          (fn main -> int
            (set a int (string_to_int (array_get (argv) 0)))
            (set b int (string_to_int (array_get (argv) 1)))
            (try
              (println (div a b))
              (catch err string
                (println (string_format "error: {}" err))))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses try/catch to safely parse user input.",
        dedent("""\
        (module safe_parse
          (fn main -> int
            (set input string (array_get (argv) 0))
            (try
              (set n int (string_to_int input))
              (println (string_format "parsed: {}" (string_from_int n)))
              (catch err string
                (println "invalid number")))
            (ret 0)))""")
    ))

    return examples


def generate_bitwise_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that demonstrates bitwise operations: AND, OR, XOR, NOT, shift left, shift right.",
        dedent("""\
        (module bitwise
          (fn main -> int
            (set a int (string_to_int (array_get (argv) 0)))
            (set b int (string_to_int (array_get (argv) 1)))
            (println (string_format "AND: {}" (string_from_int (bit_and a b))))
            (println (string_format "OR: {}" (string_from_int (bit_or a b))))
            (println (string_format "XOR: {}" (string_from_int (bit_xor a b))))
            (println (string_format "NOT a: {}" (string_from_int (bit_not a))))
            (println (string_format "a << 2: {}" (string_from_int (bit_shift_left a 2))))
            (println (string_format "a >> 1: {}" (string_from_int (bit_shift_right a 1))))
            (ret 0)))""")
    ))

    return examples


def generate_comparison_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that compares two values using all comparison operators and prints the results.",
        dedent("""\
        (module compare
          (fn main -> int
            (set a int (string_to_int (array_get (argv) 0)))
            (set b int (string_to_int (array_get (argv) 1)))
            (println (eq a b))
            (println (ne a b))
            (println (lt a b))
            (println (gt a b))
            (println (le a b))
            (println (ge a b))
            (ret 0)))""")
    ))

    return examples


def generate_algorithm_examples() -> list[dict]:
    """Medium and hard algorithm problems in Sigil."""
    examples = []

    examples.append(make_example(
        "Write a program that implements bubble sort on a space-separated list of integers.",
        dedent("""\
        (module bubble_sort
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set arr array (array_new))
            (for i 0 (array_length parts)
              (array_push arr (string_to_int (array_get parts i))))
            (set n int (array_length arr))
            (for i 0 n
              (for j 0 (sub (sub n i) 1)
                (if (gt (array_get arr j) (array_get arr (add j 1)))
                  (set temp int (array_get arr j))
                  (array_set arr j (array_get arr (add j 1)))
                  (array_set arr (add j 1) temp))))
            (for i 0 n
              (if (gt i 0) (print " "))
              (print (array_get arr i)))
            (println "")
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that generates the first n prime numbers.",
        dedent("""\
        (module primes
          (fn is_prime n int -> bool
            (if (lt n 2) (ret false))
            (set i int 2)
            (while (le (mul i i) n)
              (if (eq (mod n i) 0)
                (ret false))
              (set i (add i 1)))
            (ret true))
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (set count int 0)
            (set candidate int 2)
            (while (lt count n)
              (if (is_prime candidate)
                (if (gt count 0) (print " "))
                (print candidate)
                (set count (add count 1)))
              (set candidate (add candidate 1)))
            (println "")
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that converts a decimal number to any base (2-16).",
        dedent("""\
        (module base_convert
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (set base int (string_to_int (array_get (argv) 1)))
            (set digits string "0123456789ABCDEF")
            (if (eq n 0)
              (println "0")
              (else
                (set result array (array_new))
                (while (gt n 0)
                  (array_push result (string_slice digits (mod n base) 1))
                  (set n (div n base)))
                (set out string "")
                (set i int (sub (array_length result) 1))
                (while (ge i 0)
                  (set out (string_concat out (array_get result i)))
                  (set i (sub i 1)))
                (println out)))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that checks if a string is a valid palindrome (ignoring case and non-alpha characters).",
        dedent("""\
        (module palindrome
          (fn is_alpha c int -> bool
            (ret (or (and (ge c 97) (le c 122)) (and (ge c 65) (le c 90)))))
          (fn to_lower c int -> int
            (if (and (ge c 65) (le c 90))
              (ret (add c 32)))
            (ret c))
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set clean string "")
            (for i 0 (string_length s)
              (set c int (string_get s i))
              (if (is_alpha c)
                (set clean (string_concat clean (char_from_code (to_lower c))))))
            (set len int (string_length clean))
            (set is_palindrome bool true)
            (for i 0 (div len 2)
              (if (ne (string_get clean i) (string_get clean (sub (sub len 1) i)))
                (set is_palindrome false)
                (break)))
            (println is_palindrome)
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that implements a simple stack using an array, supporting push, pop, and peek operations.",
        dedent("""\
        (module stack
          (fn main -> int
            (set stack array (array_new))
            (set parts array (string_split (array_get (argv) 0) " "))
            (for i 0 (array_length parts)
              (set cmd string (array_get parts i))
              (cond
                ((string_equals cmd "peek")
                  (if (gt (array_length stack) 0)
                    (println (array_get stack (sub (array_length stack) 1)))
                    (else
                      (println "empty"))))
                ((string_equals cmd "pop")
                  (if (gt (array_length stack) 0)
                    (println (array_pop stack))
                    (else
                      (println "empty"))))
                (true
                  (array_push stack (string_to_int cmd)))))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that computes the Collatz sequence length for a given number.",
        dedent("""\
        (module collatz
          (fn collatz_length n int -> int
            (set steps int 0)
            (while (ne n 1)
              (if (eq (mod n 2) 0)
                (set n (div n 2))
                (else
                  (set n (add (mul 3 n) 1))))
              (set steps (add steps 1)))
            (ret steps))
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (println (collatz_length n))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that implements insertion sort.",
        dedent("""\
        (module insertion_sort
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set arr array (array_new))
            (for i 0 (array_length parts)
              (array_push arr (string_to_int (array_get parts i))))
            (set n int (array_length arr))
            (for i 1 n
              (set key int (array_get arr i))
              (set j int (sub i 1))
              (while (and (ge j 0) (gt (array_get arr j) key))
                (array_set arr (add j 1) (array_get arr j))
                (set j (sub j 1)))
              (array_set arr (add j 1) key))
            (for i 0 n
              (if (gt i 0) (print " "))
              (print (array_get arr i)))
            (println "")
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that converts a Roman numeral string to an integer.",
        dedent("""\
        (module roman
          (fn roman_val ch string -> int
            (cond
              ((string_equals ch "I") (ret 1))
              ((string_equals ch "V") (ret 5))
              ((string_equals ch "X") (ret 10))
              ((string_equals ch "L") (ret 50))
              ((string_equals ch "C") (ret 100))
              ((string_equals ch "D") (ret 500))
              ((string_equals ch "M") (ret 1000))
              (true (ret 0))))
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set total int 0)
            (set len int (string_length s))
            (for i 0 len
              (set cur int (roman_val (string_slice s i 1)))
              (set next_val int 0)
              (if (lt i (sub len 1))
                (set next_val (roman_val (string_slice s (add i 1) 1))))
              (if (lt cur next_val)
                (set total (sub total cur))
                (else
                  (set total (add total cur)))))
            (println total)
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that implements matrix transposition. Input: rows separated by semicolons, values by commas.",
        dedent("""\
        (module transpose
          (fn main -> int
            (set input string (array_get (argv) 0))
            (set rows array (string_split input ";"))
            (set num_rows int (array_length rows))
            (set first_row array (string_split (array_get rows 0) ","))
            (set num_cols int (array_length first_row))
            (for c 0 num_cols
              (set line string "")
              (for r 0 num_rows
                (set row array (string_split (array_get rows r) ","))
                (if (gt r 0)
                  (set line (string_concat line ",")))
                (set line (string_concat line (string_trim (array_get row c)))))
              (println line))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that implements a simple RPN calculator supporting +, -, *, /.",
        dedent("""\
        (module rpn
          (fn main -> int
            (set tokens array (string_split (array_get (argv) 0) " "))
            (set stack array (array_new))
            (for i 0 (array_length tokens)
              (set tok string (array_get tokens i))
              (cond
                ((or (string_equals tok "+") (or (string_equals tok "-") (or (string_equals tok "*") (string_equals tok "/"))))
                  (set b int (array_pop stack))
                  (set a int (array_pop stack))
                  (cond
                    ((string_equals tok "+") (array_push stack (add a b)))
                    ((string_equals tok "-") (array_push stack (sub a b)))
                    ((string_equals tok "*") (array_push stack (mul a b)))
                    ((string_equals tok "/") (array_push stack (div a b)))))
                (true
                  (array_push stack (string_to_int tok)))))
            (println (array_get stack 0))
            (ret 0)))""")
    ))

    return examples


def generate_io_file_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that reads a file, counts its lines, and prints the count.",
        dedent("""\
        (module line_count
          (fn main -> int
            (set path string (array_get (argv) 0))
            (if (not (file_exists path))
              (println "file not found")
              (else
                (set content string (file_read path))
                (set lines array (string_split content "\\n"))
                (println (array_length lines))))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that writes text to a file and reads it back.",
        dedent("""\
        (module file_io
          (fn main -> int
            (set path string (array_get (argv) 0))
            (set text string (array_get (argv) 1))
            (file_write path text)
            (set readback string (file_read path))
            (println readback)
            (file_delete path)
            (ret 0)))""")
    ))

    return examples


def generate_json_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that creates a JSON object, adds fields, and prints it as a string.",
        dedent("""\
        (module json_demo
          (fn main -> int
            (set obj json (json_new_object))
            (json_set obj "name" "Alice")
            (json_set obj "age" 30)
            (json_set obj "active" true)
            (println (json_stringify obj))
            (println (json_get obj "name"))
            (println (json_has obj "email"))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that parses a JSON string and extracts values.",
        dedent("""\
        (module json_parse
          (fn main -> int
            (set input string (array_get (argv) 0))
            (set data json (json_parse input))
            (println (json_type data))
            (println (json_stringify data))
            (ret 0)))""")
    ))

    return examples


def generate_regex_examples() -> list[dict]:
    examples = []

    examples.append(make_example(
        "Write a program that uses regex to find all numbers in a string.",
        dedent("""\
        (module regex_demo
          (fn main -> int
            (set text string (array_get (argv) 0))
            (set pattern regex (regex_compile "[0-9]+"))
            (set matches array (regex_find_all pattern text))
            (for-each m string matches
              (println m))
            (ret 0)))""")
    ))

    examples.append(make_example(
        "Write a program that uses regex to validate an email-like pattern.",
        dedent("""\
        (module email_check
          (fn main -> int
            (set email string (array_get (argv) 0))
            (set pattern regex (regex_compile "^[a-zA-Z0-9]+@[a-zA-Z0-9]+\\\\.[a-zA-Z]+$"))
            (if (regex_match pattern email)
              (println "valid")
              (else
                (println "invalid")))
            (ret 0)))""")
    ))

    return examples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Sigil fine-tuning data")
    parser.add_argument("--output", default="benchmark/training_data.jsonl")
    args = parser.parse_args()

    all_examples = []

    # Source 1: Test files
    test_examples = extract_from_tests()
    print(f"From tests: {len(test_examples)} examples")
    all_examples.extend(test_examples)

    # Source 2: Stdlib
    stdlib_examples = extract_from_stdlib()
    print(f"From stdlib: {len(stdlib_examples)} examples")
    all_examples.extend(stdlib_examples)

    # Source 3: Example programs
    example_examples = extract_from_examples()
    print(f"From examples: {len(example_examples)} examples")
    all_examples.extend(example_examples)

    # Source 4: Synthetic — systematic builtin coverage
    synth = []
    synth.extend(generate_arithmetic_examples())
    synth.extend(generate_string_examples())
    synth.extend(generate_array_examples())
    synth.extend(generate_map_examples())
    synth.extend(generate_control_flow_examples())
    synth.extend(generate_function_examples())
    synth.extend(generate_type_conversion_examples())
    synth.extend(generate_error_handling_examples())
    synth.extend(generate_bitwise_examples())
    synth.extend(generate_comparison_examples())
    synth.extend(generate_algorithm_examples())
    synth.extend(generate_io_file_examples())
    synth.extend(generate_json_examples())
    synth.extend(generate_regex_examples())
    print(f"Synthetic: {len(synth)} examples")
    all_examples.extend(synth)

    print(f"\nTotal: {len(all_examples)} examples")

    # Write
    outpath = Path(args.output)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")

    # Stats
    total_tokens_est = sum(
        len(json.dumps(ex).split()) for ex in all_examples
    )
    print(f"Written to: {outpath}")
    print(f"File size: {outpath.stat().st_size / 1024:.1f} KB")
    print(f"Estimated tokens: ~{total_tokens_est}")


if __name__ == "__main__":
    main()
