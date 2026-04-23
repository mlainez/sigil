#!/usr/bin/env python3
"""Generate Sigil training data and launch fine-tuning jobs on together.ai.

Usage:
  # Generate training data only
  python finetune.py generate --output training_data.jsonl

  # Generate + upload + launch fine-tuning on selected models
  python finetune.py launch --models qwen3-8b gemma-4b llama-8b

  # Check status of running jobs
  python finetune.py status

  # List available fine-tuned models
  python finetune.py list
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from textwrap import dedent

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Model configs — together.ai model IDs for fine-tuning
# ---------------------------------------------------------------------------

FINETUNE_MODELS = {
    "qwen3-8b": {
        "id": "Qwen/Qwen3-8B",
        "description": "Qwen3 8B — strong small general model",
        "lora": True,
        "learning_rate": 1e-5,
        "n_epochs": 3,
    },
    "qwen3-coder-30b": {
        "id": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
        "description": "Qwen3 Coder 30B MoE (3B active) — code-specialized",
        "lora": True,
        "learning_rate": 1e-5,
        "n_epochs": 3,
    },
    "gemma-4b": {
        "id": "google/gemma-3-4b-it",
        "description": "Gemma 3 4B — very small, tests max uplift",
        "lora": True,
        "learning_rate": 1e-5,
        "n_epochs": 4,
    },
    "llama-8b": {
        "id": "meta-llama/Meta-Llama-3.1-8B-Instruct-Reference",
        "description": "Llama 3.1 8B Instruct — classic baseline",
        "lora": True,
        "learning_rate": 1e-5,
        "n_epochs": 3,
    },
    "qwen2.5-7b": {
        "id": "Qwen/Qwen2.5-7B-Instruct",
        "description": "Qwen 2.5 7B Instruct — widely used local model",
        "lora": True,
        "learning_rate": 1e-5,
        "n_epochs": 3,
    },
    "qwen3-4b": {
        "id": "Qwen/Qwen3-4B",
        "description": "Qwen3 4B — smallest Qwen3, extreme test",
        "lora": True,
        "learning_rate": 1e-5,
        "n_epochs": 4,
    },
}

# ---------------------------------------------------------------------------
# Training data generation
# ---------------------------------------------------------------------------

def make_example(task_description: str, sigil_code: str) -> dict:
    """Create a single training example in together.ai chat format."""
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write Sigil programs. Sigil is an S-expression language "
                    "with (module ...) (fn name params -> type body...) syntax. "
                    "Programs use (fn main -> int ...) as entry point, (argv) for CLI args, "
                    "(print)/(println) for output, and (ret 0) to exit."
                ),
            },
            {"role": "user", "content": task_description},
            {"role": "assistant", "content": f"```sigil\n{sigil_code}\n```"},
        ]
    }


def generate_training_data() -> list[dict]:
    """Generate training examples from hand-crafted tasks. NOT from benchmark tasks (to avoid contamination)."""
    examples = []

    # --- Basic I/O and arithmetic ---

    examples.append(make_example(
        "Write a program that prints 'Hello, World!'",
        dedent("""\
        (module hello
          (fn main -> int
            (println "Hello, World!")
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes two integers as arguments and prints their sum.",
        dedent("""\
        (module add_two
          (fn main -> int
            (set a int (string_to_int (array_get (argv) 0)))
            (set b int (string_to_int (array_get (argv) 1)))
            (println (add a b))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes an integer n and prints whether it is even or odd.",
        dedent("""\
        (module even_odd
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (if (eq (mod n 2) 0)
              (println "even")
              (else
                (println "odd")))
            (ret 0)))"""),
    ))

    # --- Loops and iteration ---

    examples.append(make_example(
        "Write a program that takes n and prints the numbers from 1 to n, one per line.",
        dedent("""\
        (module count_up
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (for i 1 (add n 1)
              (println i))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes n and computes the factorial of n, printing the result.",
        dedent("""\
        (module factorial
          (fn factorial n int -> int
            (if (le n 1) (ret 1))
            (ret (mul n (factorial (sub n 1)))))
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (println (factorial n))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes n and prints the first n Fibonacci numbers, one per line.",
        dedent("""\
        (module fibonacci
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (set a int 0)
            (set b int 1)
            (for i 0 n
              (println a)
              (set temp int b)
              (set b (add a b))
              (set a temp))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a space-separated list of integers and prints their sum.",
        dedent("""\
        (module sum_list
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set total int 0)
            (set len int (array_length parts))
            (for i 0 len
              (set total (add total (string_to_int (array_get parts i)))))
            (println total)
            (ret 0)))"""),
    ))

    # --- String operations ---

    examples.append(make_example(
        "Write a program that takes a string and prints it reversed.",
        dedent("""\
        (module reverse_str
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set len int (string_length s))
            (set result string "")
            (set i int (sub len 1))
            (while (ge i 0)
              (set result (string_concat result (string_slice s i 1)))
              (set i (sub i 1)))
            (println result)
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a string and prints the number of vowels in it.",
        dedent("""\
        (module count_vowels
          (fn main -> int
            (set s string (string_to_lower (array_get (argv) 0)))
            (set count int 0)
            (set len int (string_length s))
            (for i 0 len
              (set ch string (string_slice s i 1))
              (if (or (string_equals ch "a") (or (string_equals ch "e") (or (string_equals ch "i") (or (string_equals ch "o") (string_equals ch "u")))))
                (set count (add count 1))))
            (println count)
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a string and prints it with each word capitalized (first letter uppercase).",
        dedent("""\
        (module capitalize
          (fn main -> int
            (set words array (string_split (array_get (argv) 0) " "))
            (set len int (array_length words))
            (set result string "")
            (for i 0 len
              (set word string (array_get words i))
              (if (gt (string_length word) 0)
                (set first int (string_get word 0))
                (if (and (ge first 97) (le first 122))
                  (set first (sub first 32)))
                (set cap string (string_concat (char_from_code first) (string_slice word 1 (sub (string_length word) 1))))
                (if (gt i 0)
                  (set result (string_concat result " ")))
                (set result (string_concat result cap))))
            (println result)
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a string and a substring, and counts how many times the substring appears.",
        dedent("""\
        (module count_substring
          (fn main -> int
            (set text string (array_get (argv) 0))
            (set sub string (array_get (argv) 1))
            (set count int 0)
            (set text_len int (string_length text))
            (set sub_len int (string_length sub))
            (set max_pos int (sub text_len sub_len))
            (set i int 0)
            (while (le i max_pos)
              (if (string_equals (string_slice text i sub_len) sub)
                (set count (add count 1)))
              (set i (add i 1)))
            (println count)
            (ret 0)))"""),
    ))

    # --- Array operations ---

    examples.append(make_example(
        "Write a program that takes a space-separated list of integers and prints them sorted in ascending order.",
        dedent("""\
        (module sort_ints
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set nums array (array_new))
            (set len int (array_length parts))
            (for i 0 len
              (array_push nums (string_to_int (array_get parts i))))
            (array_sort nums)
            (set result string "")
            (set slen int (array_length nums))
            (for i 0 slen
              (if (gt i 0)
                (set result (string_concat result " ")))
              (set result (string_concat result (string_from_int (array_get nums i)))))
            (println result)
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a space-separated list of integers and prints the maximum value.",
        dedent("""\
        (module find_max
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set max_val int (string_to_int (array_get parts 0)))
            (set len int (array_length parts))
            (for i 1 len
              (set val int (string_to_int (array_get parts i)))
              (if (gt val max_val)
                (set max_val val)))
            (println max_val)
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a list of integers and removes all duplicates, printing the unique values in order.",
        dedent("""\
        (module unique
          (fn main -> int
            (set parts array (string_split (array_get (argv) 0) " "))
            (set seen array (array_new))
            (set len int (array_length parts))
            (for i 0 len
              (set val string (array_get parts i))
              (if (not (array_contains seen val))
                (array_push seen val)))
            (set result string "")
            (set slen int (array_length seen))
            (for i 0 slen
              (if (gt i 0)
                (set result (string_concat result " ")))
              (set result (string_concat result (array_get seen i))))
            (println result)
            (ret 0)))"""),
    ))

    # --- Maps and data structures ---

    examples.append(make_example(
        "Write a program that takes a string of characters and prints each character with its frequency, one per line as 'char count'.",
        dedent("""\
        (module char_freq
          (fn main -> int
            (set s string (array_get (argv) 0))
            (set freq map (map_new))
            (set order array (array_new))
            (set len int (string_length s))
            (for i 0 len
              (set ch string (string_slice s i 1))
              (if (not (map_has freq ch))
                (map_set freq ch 0)
                (array_push order ch))
              (set cur int (map_get freq ch))
              (map_set freq ch (add cur 1)))
            (set olen int (array_length order))
            (for i 0 olen
              (set ch string (array_get order i))
              (set c int (map_get freq ch))
              (println (string_format "{} {}" ch (string_from_int c))))
            (ret 0)))"""),
    ))

    # --- Conditionals and control flow ---

    examples.append(make_example(
        "Write a program that takes a year as argument and prints whether it is a leap year.",
        dedent("""\
        (module leap_year
          (fn main -> int
            (set y int (string_to_int (array_get (argv) 0)))
            (set is_leap bool false)
            (if (eq (mod y 400) 0)
              (set is_leap true)
              (else
                (if (eq (mod y 100) 0)
                  (set is_leap false)
                  (else
                    (if (eq (mod y 4) 0)
                      (set is_leap true))))))
            (if is_leap
              (println "true")
              (else
                (println "false")))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a number and prints all its prime factors, space-separated.",
        dedent("""\
        (module prime_factors
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (set result string "")
            (set d int 2)
            (while (le (mul d d) n)
              (while (eq (mod n d) 0)
                (if (gt (string_length result) 0)
                  (set result (string_concat result " ")))
                (set result (string_concat result (string_from_int d)))
                (set n (div n d)))
              (set d (add d 1)))
            (if (gt n 1)
              (if (gt (string_length result) 0)
                (set result (string_concat result " ")))
              (set result (string_concat result (string_from_int n))))
            (println result)
            (ret 0)))"""),
    ))

    # --- Pattern matching with cond ---

    examples.append(make_example(
        "Write a program that takes a month number (1-12) and prints the month name.",
        dedent("""\
        (module month_name
          (fn main -> int
            (set m int (string_to_int (array_get (argv) 0)))
            (set names array ["January" "February" "March" "April" "May" "June" "July" "August" "September" "October" "November" "December"])
            (if (and (ge m 1) (le m 12))
              (println (array_get names (sub m 1)))
              (else
                (println "invalid")))
            (ret 0)))"""),
    ))

    # --- String building with string_format ---

    examples.append(make_example(
        "Write a program that takes a name and age and prints a greeting like 'Hello, Alice! You are 30 years old.'",
        dedent("""\
        (module greet
          (fn main -> int
            (set name string (array_get (argv) 0))
            (set age string (array_get (argv) 1))
            (println (string_format "Hello, {}! You are {} years old." name age))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes rows and cols as arguments and prints an ASCII grid of that size using + for corners, - for horizontal edges, and | for vertical edges.",
        dedent("""\
        (module grid
          (fn main -> int
            (set rows int (string_to_int (array_get (argv) 0)))
            (set cols int (string_to_int (array_get (argv) 1)))
            (for r 0 (add rows 1)
              (set line string "")
              (for c 0 (add cols 1)
                (cond
                  ((and (or (eq r 0) (eq r rows)) (or (eq c 0) (eq c cols)))
                    (set line (string_concat line "+")))
                  ((or (eq r 0) (eq r rows))
                    (set line (string_concat line "-")))
                  ((or (eq c 0) (eq c cols))
                    (set line (string_concat line "|")))
                  (true
                    (set line (string_concat line " ")))))
              (println line))
            (ret 0)))"""),
    ))

    # --- Error handling ---

    examples.append(make_example(
        "Write a program that takes a number and prints its reciprocal. If the number is 0, print 'error: division by zero'.",
        dedent("""\
        (module reciprocal
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (if (eq n 0)
              (println "error: division by zero")
              (else
                (set r float (div 1.0 (cast_int_float n)))
                (println r)))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes two integers and safely divides them. Use try/catch to handle division by zero and print 'error' on failure.",
        dedent("""\
        (module safe_div
          (fn main -> int
            (set a int (string_to_int (array_get (argv) 0)))
            (set b int (string_to_int (array_get (argv) 1)))
            (try
              (println (div a b))
              (catch err string
                (println "error")))
            (ret 0)))"""),
    ))

    # --- for-each iteration ---

    examples.append(make_example(
        "Write a program that takes a comma-separated list and prints each item on its own line, trimmed of whitespace.",
        dedent("""\
        (module split_print
          (fn main -> int
            (set items array (string_split (array_get (argv) 0) ","))
            (for-each item string items
              (println (string_trim item)))
            (ret 0)))"""),
    ))

    # --- Combining features ---

    examples.append(make_example(
        "Write a program that takes a string and checks if it's a palindrome (ignoring case). Print true or false.",
        dedent("""\
        (module palindrome
          (fn main -> int
            (set s string (string_to_lower (array_get (argv) 0)))
            (set len int (string_length s))
            (set is_palindrome bool true)
            (for i 0 (div len 2)
              (set left string (string_slice s i 1))
              (set right string (string_slice s (sub (sub len 1) i) 1))
              (if (not (string_equals left right))
                (set is_palindrome false)
                (break)))
            (if is_palindrome
              (println "true")
              (else
                (println "false")))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a positive integer and prints its binary representation.",
        dedent("""\
        (module to_binary
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (if (eq n 0)
              (println "0")
              (else
                (set bits array (array_new))
                (while (gt n 0)
                  (array_push bits (string_from_int (mod n 2)))
                  (set n (div n 2)))
                (set result string "")
                (set i int (sub (array_length bits) 1))
                (while (ge i 0)
                  (set result (string_concat result (array_get bits i)))
                  (set i (sub i 1)))
                (println result)))
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a Roman numeral string and prints its integer value.",
        dedent("""\
        (module roman_to_int
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
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a mathematical expression with + and - only (no spaces, integers only) and evaluates it. Example: '10+20-5' prints 25.",
        dedent("""\
        (module simple_expr
          (fn main -> int
            (set expr string (array_get (argv) 0))
            (set len int (string_length expr))
            (set result int 0)
            (set current string "")
            (set op int 1)
            (for i 0 len
              (set ch int (string_get expr i))
              (cond
                ((eq ch 43)
                  (set result (add result (mul op (string_to_int current))))
                  (set current "")
                  (set op 1))
                ((eq ch 45)
                  (set result (add result (mul op (string_to_int current))))
                  (set current "")
                  (set op -1))
                (true
                  (set current (string_concat current (char_from_code ch))))))
            (set result (add result (mul op (string_to_int current))))
            (println result)
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that takes a list of words and prints the longest one. If there's a tie, print the first one.",
        dedent("""\
        (module longest_word
          (fn main -> int
            (set words array (string_split (array_get (argv) 0) " "))
            (set best string (array_get words 0))
            (set best_len int (string_length best))
            (set len int (array_length words))
            (for i 1 len
              (set word string (array_get words i))
              (set wlen int (string_length word))
              (if (gt wlen best_len)
                (set best word)
                (set best_len wlen)))
            (println best)
            (ret 0)))"""),
    ))

    examples.append(make_example(
        "Write a program that generates a multiplication table up to n (given as argument) and prints it formatted as 'a x b = c' one per line.",
        dedent("""\
        (module mult_table
          (fn main -> int
            (set n int (string_to_int (array_get (argv) 0)))
            (for i 1 (add n 1)
              (for j 1 (add n 1)
                (println (string_format "{} x {} = {}" (string_from_int i) (string_from_int j) (string_from_int (mul i j))))))
            (ret 0)))"""),
    ))

    return examples


# ---------------------------------------------------------------------------
# Together.ai operations
# ---------------------------------------------------------------------------

def get_client():
    """Get together.ai client."""
    from together import Together
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        print("Error: TOGETHER_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return Together(api_key=api_key)


def upload_training_data(client, filepath: str) -> str:
    """Upload training data file and return the file ID."""
    print(f"Uploading {filepath}...")
    resp = client.files.upload(filepath, purpose="fine-tune", check=True)
    print(f"  File ID: {resp.id}")
    return resp.id


def launch_finetune(client, model_config: dict, file_id: str, suffix: str) -> str:
    """Launch a fine-tuning job and return the job ID."""
    model_id = model_config["id"]
    print(f"Launching fine-tuning: {model_id} (suffix: {suffix})")

    resp = client.fine_tuning.create(
        training_file=file_id,
        model=model_id,
        lora=model_config.get("lora", True),
        n_epochs=model_config.get("n_epochs", 3),
        n_checkpoints=1,
        learning_rate=model_config.get("learning_rate", 1e-5),
        warmup_ratio=0.1,
        train_on_inputs="auto",
        suffix=suffix,
    )
    print(f"  Job ID: {resp.id}")
    print(f"  Status: {resp.status}")
    return resp.id


def check_status(client, job_id: str = None):
    """Check status of fine-tuning jobs."""
    jobs = client.fine_tuning.list()
    for job in jobs.data:
        if job_id and job.id != job_id:
            continue
        model_name = getattr(job, "output_name", None) or getattr(job, "model", "?")
        print(f"  Job {job.id}: status={job.status} model={model_name}")


def list_finetuned_models(client):
    """List all fine-tuned models."""
    jobs = client.fine_tuning.list()
    completed = [j for j in jobs.data if j.status == "completed"]
    if not completed:
        print("No completed fine-tuning jobs found.")
        return
    print(f"Completed fine-tuning jobs ({len(completed)}):\n")
    for job in completed:
        output = getattr(job, "output_name", None) or "?"
        print(f"  {output}")
        print(f"    Job ID: {job.id}")
        print(f"    Base model: {job.model}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sigil Fine-Tuning on together.ai")
    sub = parser.add_subparsers(dest="command", required=True)

    # generate
    gen = sub.add_parser("generate", help="Generate training data JSONL file")
    gen.add_argument("--output", default="benchmark/training_data.jsonl",
                     help="Output JSONL file path")

    # launch
    launch = sub.add_parser("launch", help="Generate data, upload, and launch fine-tuning")
    launch.add_argument("--models", nargs="+", default=["qwen3-8b"],
                        choices=list(FINETUNE_MODELS.keys()),
                        help="Models to fine-tune")
    launch.add_argument("--suffix", default="sigil-v1",
                        help="Suffix for fine-tuned model name")
    launch.add_argument("--data", default=None,
                        help="Path to existing training data JSONL (skips generation)")

    # status
    sub.add_parser("status", help="Check fine-tuning job status")

    # list
    sub.add_parser("list", help="List completed fine-tuned models")

    args = parser.parse_args()

    if args.command == "generate":
        examples = generate_training_data()
        outpath = Path(args.output)
        outpath.parent.mkdir(parents=True, exist_ok=True)
        with open(outpath, "w") as f:
            for ex in examples:
                f.write(json.dumps(ex) + "\n")
        print(f"Generated {len(examples)} training examples → {outpath}")

    elif args.command == "launch":
        # Generate training data if not provided
        if args.data:
            data_path = args.data
        else:
            data_path = "benchmark/training_data.jsonl"
            print(f"Generating training data with generate_training_data.py...")
            import subprocess
            subprocess.run([sys.executable, "benchmark/generate_training_data.py", "--output", data_path], check=True)
            print()

        client = get_client()
        file_id = upload_training_data(client, data_path)
        print()

        job_ids = []
        for model_key in args.models:
            config = FINETUNE_MODELS[model_key]
            print(f"\n--- {config['description']} ---")
            job_id = launch_finetune(client, config, file_id, args.suffix)
            job_ids.append((model_key, job_id))

        print(f"\n{'=' * 60}")
        print(f"Launched {len(job_ids)} fine-tuning jobs:")
        for model_key, job_id in job_ids:
            print(f"  {model_key}: {job_id}")
        print(f"\nCheck status with: python finetune.py status")
        print(f"Use in benchmark with:")
        for model_key, job_id in job_ids:
            print(f"  python harness.py --model <output_model_name> --provider together --finetuned --languages sigil python")

    elif args.command == "status":
        client = get_client()
        check_status(client)

    elif args.command == "list":
        client = get_client()
        list_finetuned_models(client)


if __name__ == "__main__":
    main()
