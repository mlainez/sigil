#!/usr/bin/env python3
"""Translate Python programs to Sigil using Claude.

Pipeline:
  1. Read a Python program with associated test cases
  2. Ask Claude to write the Sigil equivalent
  3. Run both through their interpreters with the same inputs
  4. Keep only pairs where outputs match exactly
  5. Write the Sigil version as a new corpus file

Usage:
  python translate_python.py --input tasks.jsonl --output corpus_translated/
  python translate_python.py --batch-size 50 --max 500
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")
GRAMMAR = (REPO_ROOT / ".sigil.grammar").read_text()

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


def translate_one(python_code: str, task_desc: str, model: str = "claude-sonnet-4-6") -> str:
    """Ask Claude to translate Python to Sigil. Returns Sigil code or empty string."""
    prompt = f"""{GRAMMAR}

You are translating Python to Sigil. Sigil is a token-efficient S-expression language.

Task: {task_desc}

Python implementation:
```python
{python_code}
```

Translate to idiomatic Sigil using the new concise features:
- `$N` for argv string access, `#N` for int access
- `fmt` for interpolation with named {{var}} placeholders
- `in` for membership, `map_inc` for counters, `parse_ints` for batch int parsing
- Variadic `println a b c` for space-separated output
- Script mode (no module wrapper) when it's a single-purpose program
- Top-level `(fn ...)` definitions are allowed in script mode

Output ONLY the Sigil code, no markdown fences, no explanations."""

    try:
        r = subprocess.run(
            ["claude", "--print", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=90, cwd="/tmp",
        )
        code = r.stdout.strip()
        for fence in ["```sigil", "```lisp", "```scheme", "```"]:
            if code.startswith(fence):
                code = code[len(fence):].strip()
                break
        if code.endswith("```"):
            code = code[:-3].strip()
        return code
    except Exception:
        return ""


def run_sigil(code: str, args: list) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name] + args,
                             capture_output=True, text=True, timeout=5)
            return r.returncode == 0, r.stdout
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
        finally:
            os.unlink(f.name)


def validate(sigil_code: str, python_code: str, test_cases: list) -> tuple[bool, str]:
    """Return (all_match, reason_if_not)."""
    for i, tc in enumerate(test_cases):
        args = tc.get("args", [])
        ok_p, out_p = run_python(python_code, args)
        if not ok_p:
            return False, f"python failed on case {i}"

        ok_s, out_s = run_sigil(sigil_code, args)
        if not ok_s:
            return False, f"sigil failed on case {i}: {out_s[:60]}"

        if out_s != out_p:
            return False, f"mismatch case {i}: sigil={out_s!r} python={out_p!r}"
    return True, ""


def process_task(task: dict, model: str) -> dict:
    """Translate one task. Returns result dict."""
    desc = task["description"]
    py = task["python"]
    tests = task["tests"]

    # Up to 3 attempts with retry-on-error feedback
    for attempt in range(3):
        sigil = translate_one(py, desc, model)
        if not sigil:
            continue
        ok, reason = validate(sigil, py, tests)
        if ok:
            return {**task, "sigil": sigil, "status": "ok", "attempts": attempt + 1}

    return {**task, "sigil": "", "status": "failed", "attempts": 3, "last_reason": reason}


def generate_seed_tasks() -> list[dict]:
    """Generate ~50 seed tasks with Python implementations for initial validation."""
    tasks = []

    tasks.append({
        "id": "hello_name",
        "description": "Print 'Hello, NAME!' where NAME is the first argument",
        "python": 'import sys\nprint(f"Hello, {sys.argv[1]}!")',
        "tests": [
            {"args": ["Alice"]},
            {"args": ["Bob"]},
        ],
    })

    tasks.append({
        "id": "abs_diff",
        "description": "Print absolute difference of two integers",
        "python": 'import sys\na, b = int(sys.argv[1]), int(sys.argv[2])\nprint(abs(a - b))',
        "tests": [
            {"args": ["10", "3"]},
            {"args": ["5", "20"]},
            {"args": ["0", "0"]},
        ],
    })

    tasks.append({
        "id": "triple_largest",
        "description": "Print largest of three integers",
        "python": 'import sys\nvals = [int(x) for x in sys.argv[1:4]]\nprint(max(vals))',
        "tests": [
            {"args": ["5", "10", "3"]},
            {"args": ["100", "1", "50"]},
        ],
    })

    tasks.append({
        "id": "sum_to_n",
        "description": "Sum of integers 1 to n",
        "python": 'import sys\nn = int(sys.argv[1])\nprint(sum(range(1, n+1)))',
        "tests": [
            {"args": ["10"]},
            {"args": ["100"]},
            {"args": ["1"]},
        ],
    })

    tasks.append({
        "id": "reverse_string",
        "description": "Reverse a string",
        "python": 'import sys\nprint(sys.argv[1][::-1])',
        "tests": [
            {"args": ["hello"]},
            {"args": ["a"]},
            {"args": ["Palindrome"]},
        ],
    })

    tasks.append({
        "id": "count_words",
        "description": "Count space-separated words",
        "python": 'import sys\nprint(len(sys.argv[1].split()))',
        "tests": [
            {"args": ["hello world"]},
            {"args": ["a b c d e"]},
            {"args": ["one"]},
        ],
    })

    tasks.append({
        "id": "is_even",
        "description": "Print 'even' or 'odd' based on integer",
        "python": 'import sys\nprint("even" if int(sys.argv[1]) % 2 == 0 else "odd")',
        "tests": [
            {"args": ["4"]},
            {"args": ["7"]},
            {"args": ["0"]},
        ],
    })

    tasks.append({
        "id": "fizz_only",
        "description": "Print Fizz for multiples of 3 from 1 to n, else the number",
        "python": '''import sys
n = int(sys.argv[1])
for i in range(1, n+1):
    print("Fizz" if i % 3 == 0 else i)''',
        "tests": [
            {"args": ["5"]},
            {"args": ["9"]},
        ],
    })

    tasks.append({
        "id": "square_numbers",
        "description": "Print squares of 1 to n, one per line",
        "python": '''import sys
n = int(sys.argv[1])
for i in range(1, n+1):
    print(i * i)''',
        "tests": [
            {"args": ["5"]},
            {"args": ["3"]},
        ],
    })

    tasks.append({
        "id": "uppercase",
        "description": "Uppercase a string",
        "python": 'import sys\nprint(sys.argv[1].upper())',
        "tests": [
            {"args": ["hello"]},
            {"args": ["mIxEd"]},
        ],
    })

    return tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default=None,
                       help="JSONL file with tasks (uses seed tasks if absent)")
    parser.add_argument("--output-dir", type=str, default="examples/corpus/translated")
    parser.add_argument("--output-jsonl", type=str, default="benchmark/translated.jsonl")
    parser.add_argument("--max", type=int, default=None, help="Max tasks to process")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-6")
    args = parser.parse_args()

    if args.input:
        tasks = [json.loads(line) for line in Path(args.input).read_text().splitlines() if line.strip()]
    else:
        tasks = generate_seed_tasks()

    if args.max:
        tasks = tasks[:args.max]

    print(f"Processing {len(tasks)} tasks with {args.workers} workers...")
    t0 = time.time()

    results = []
    # Sequential to be safe with Claude CLI rate limits
    for i, task in enumerate(tasks):
        result = process_task(task, args.model)
        results.append(result)
        status = "OK" if result["status"] == "ok" else "FAIL"
        print(f"  [{i+1}/{len(tasks)}] {status} (att {result['attempts']}): {task['description'][:60]}")

    elapsed = time.time() - t0
    ok_count = sum(1 for r in results if r["status"] == "ok")
    print(f"\nResults: {ok_count}/{len(results)} OK in {elapsed:.0f}s ({ok_count/len(results)*100:.0f}%)")

    # Write outputs
    out_dir = REPO_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for r in results:
        if r["status"] == "ok":
            path = out_dir / f"{r['id']}.sigil"
            path.write_text(r["sigil"].strip() + "\n")
            written += 1

    jsonl_path = REPO_ROOT / args.output_jsonl
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"Wrote {written} .sigil files to {out_dir}/")
    print(f"Wrote {len(results)} result entries to {jsonl_path}")


if __name__ == "__main__":
    main()
