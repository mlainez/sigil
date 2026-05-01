#!/usr/bin/env python3
"""Meta-generate task specs via Opus, at scale.

For each Opus call: ask for a batch of N (default 20) task specs with
{id, desc, args, expected, python}. Validate each by running Python and
comparing to expected. Keep the valid ones.

Two modes, chosen by category:
  - 'short': 1-5 line programs (avg ~80-150 tokens in Sigil)
  - 'long':  substantial programs (multiple functions, 200-500 tokens)

Output: appends validated specs to generated_tasks.jsonl. The extender
loads this alongside the hand-crafted task_bank.py.

Usage:
    python meta_gen_tasks.py --batches 20 --batch-size 20       # ~400 tasks
    python meta_gen_tasks.py --mode long --batches 10           # longer programs
    python meta_gen_tasks.py --workers 4
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "benchmark" / "generated_tasks.jsonl"


CATEGORIES_SHORT = """
- str_ (string manipulation: split, join, replace, search, predicate)
- num_ (integer or float arithmetic, comparisons, rounding)
- arr_ (array ops on space-separated numbers or words: sum, filter, sort, slice)
- map_ (key-value pairs parsed from "k=v,k=v" strings)
- parse_ (CSV/TSV row extraction, URL query, env-var, email, path components)
- valid_ (predicates returning yes/no or true/false)
- hof_ (higher-order: map+filter+reduce combinations)
- fmt_ (output formatting: padding, decimals, percent, thousands separator)
- ctrl_ (conditional dispatch: grading, categorizing, mapping to labels)
- algo_ (small classic algorithms: counting, searching, hashing)
""".strip()

CATEGORIES_LONG = """
- Complete CLI tools that read args, parse, transform, and print multi-line output.
- Mini data-processing pipelines: parse → filter → aggregate → format.
- Multi-step algorithms with helper functions (not one-liners).
- Small state machines: balanced-brackets checker, simple RPN calc, tokenizer.
- Mini apps: tiny CSV query engine, simple JSON reshaper, grep-like tool.
- Recursive algorithms with multiple base cases.
""".strip()

CATEGORIES_AGENT = """
Coding-agent operations on FILE-LIKE TEXT BLOBS (passed via argv as strings,
no real filesystem ops). The model has these Sigil builtins available:
  split, join, len, str, fmt, push, sort, sort_by, filter, map_arr, reduce,
  first, last, rev, uniq, counter, slice, range, in, has, get_or, sum,
  parse_ints, chars, char_from_code, string_get, string_replace, string_find,
  string_contains, string_starts_with, string_ends_with, regex_compile,
  regex_match, regex_find_all, regex_replace, json_parse, json_get (with
  array-of-keys for deep access), json_has, json_stringify, json_type,
  is_object, is_array, upper, lower, swapcase, title, trim.

Focus categories (mix tasks across all of these):
- file_lines: count/grep/head/tail lines from a file-content string ($0)
- file_match: filter lines matching/not-matching a pattern in $1
- file_replace: substitute substring/regex matches across all lines
- file_numbered: prefix lines with line numbers in various formats
- path_ops: extract basename, dirname, extension from a path string
- code_metric: count function defs, imports, comment lines, blank lines
- code_extract: pull out function names, import names, TODO comments
- log_filter: select log lines by level (INFO/WARN/ERROR), timestamp range
- log_extract: pull error messages, request IDs, status codes from log lines
- diff_lines: report which lines added/removed between two file blobs
- diff_count: count added/removed lines, or character-level changes
- json_select: pick fields from a JSON object/array using paths
- json_filter: keep only objects matching a predicate, sort/limit results
- csv_pipe: select columns by index/name, filter rows, project to TSV
- ini_kv: parse INI/.env/key=value pairs, look up values, list keys
- markdown_ops: extract headers, links, code blocks from MD content
- shell_emulate: simulate cut/awk/sort-like one-liner pipelines on text
- text_indent: re-indent code blocks, dedent, change indent width
- yaml_like: parse simple `key: value` blocks (no nested), extract values
- url_parts: extract scheme/host/path/query from URL strings

Each task is realistic — what an agent might do when reading a file, parsing
config, scanning logs, or processing source. Inputs are small (10-30 lines max).
Avoid tasks requiring real file I/O or network — only string manipulation.
""".strip()


PROMPT_SHORT = """You are a task-bank generator. Produce a JSON array of exactly {batch_size} programming task specs, suitable for testing small CLI programs.

Each spec is an object with these EXACT keys:
- "id": short snake_case unique identifier with category prefix
- "desc": natural-language description of what the program does (one sentence)
- "args": array of string CLI args the program receives (e.g. ["hello"], ["1 2 3"], ["a=1,b=2", "b"])
- "expected": exact stdout (string, INCLUDING trailing \\n if the program ends with print)
- "python": a self-contained Python reference implementation that reads sys.argv and prints to stdout

The Python code MUST produce EXACTLY the expected output when run with the given args. Be rigorous — if expected is "42\\n", Python must produce exactly that.

Cover these categories, spreading tasks across them:
{categories}

AVOID duplicates of common tasks like "hello world", "factorial", "reverse string", "count vowels", "is palindrome". Focus on less-obvious transformations.

Output ONLY the JSON array. No markdown fences. No prose.

Example element:
{{"id": "str_word_count", "desc": "Count words (whitespace-separated) in arg1.", "args": ["the quick brown fox"], "expected": "4\\n", "python": "import sys\\nprint(len(sys.argv[1].split()))"}}"""


PROMPT_LONG = """You are a task-bank generator. Produce a JSON array of exactly {batch_size} SUBSTANTIAL programming task specs suitable for testing larger CLI programs.

Each spec must describe a task requiring 10-30 lines of Python (multiple statements, helper functions, multi-step processing). Keep the I/O format simple (CLI args in, stdout out) but the computation should be non-trivial.

Each spec is an object with these EXACT keys:
- "id": short snake_case unique identifier
- "desc": natural-language description (one sentence) — MUST be specific enough that the expected output is unambiguous
- "args": array of string CLI args
- "expected": exact stdout including trailing newline
- "python": self-contained Python reference (10-30 lines ideal)

The Python MUST produce EXACTLY the expected output. Be meticulous about edge cases (trailing newlines, empty lines, ordering).

Categories:
{categories}

Output ONLY the JSON array. No markdown fences. No prose."""


def load_existing_ids() -> set:
    """Scan task_bank.py + generated_tasks.jsonl to avoid duplicate IDs."""
    ids = set()
    # Hand-crafted bank
    sys.path.insert(0, str(REPO_ROOT / "benchmark"))
    try:
        from task_bank import TASKS
        ids.update(t["id"] for t in TASKS)
    except Exception:
        pass
    # Generated
    if OUT_PATH.exists():
        with OUT_PATH.open() as f:
            for line in f:
                try:
                    ids.add(json.loads(line)["id"])
                except Exception:
                    pass
    return ids


def run_python(code: str, args: list) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([sys.executable, f.name] + list(args),
                             capture_output=True, text=True, timeout=10)
            return r.returncode == 0, r.stdout
        finally:
            os.unlink(f.name)


def validate_spec(spec: dict) -> tuple[bool, str]:
    """Return (ok, reason). A valid spec has all fields and Python matches."""
    for k in ("id", "desc", "args", "expected", "python"):
        if k not in spec:
            return False, f"missing key {k}"
    if not isinstance(spec["args"], list):
        return False, "args must be list"
    ok, out = run_python(spec["python"], [str(a) for a in spec["args"]])
    if not ok:
        return False, "python failed"
    if out != spec["expected"]:
        return False, f"python_out={out!r} != expected={spec['expected']!r}"
    return True, ""


def extract_json_array(raw: str) -> list | None:
    """Try to pull a JSON array out of a model response. Models sometimes
    add stray prose before/after; we hunt for the outermost [...]."""
    s = raw.strip()
    for fence in ["```json", "```"]:
        if s.startswith(fence):
            s = s[len(fence):].lstrip()
    if s.endswith("```"):
        s = s[:-3].rstrip()
    # Find first [ and last ]
    start = s.find("[")
    end = s.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(s[start:end+1])
    except json.JSONDecodeError:
        return None


def _categories_for(mode: str) -> str:
    if mode == "long": return CATEGORIES_LONG
    if mode == "agent": return CATEGORIES_AGENT
    return CATEGORIES_SHORT


def _prompt_for(mode: str, batch_size: int) -> str:
    cats = _categories_for(mode)
    # Use the LONG prompt template for "agent" too — both want substantial code.
    tpl = PROMPT_LONG if mode in ("long", "agent") else PROMPT_SHORT
    return tpl.format(batch_size=batch_size, categories=cats)


def gen_batch_ollama(batch_size: int, mode: str, existing_ids: set,
                     model: str, url: str = "http://127.0.0.1:11434",
                     timeout: int = 300) -> list[dict]:
    """Ask local ollama for a batch of specs. Free; uses big context for hits."""
    import urllib.request
    prompt = _prompt_for(mode, batch_size)
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        # Big num_predict — JSON arrays of 20 specs need ~3-5K tokens out.
        "options": {"temperature": 0.3, "num_predict": 8192, "top_p": 0.9},
    }).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        raw = data.get("response", "")
    except Exception:
        return []
    arr = extract_json_array(raw)
    if not arr:
        return []
    return _validate_specs(arr, existing_ids)


def gen_batch(batch_size: int, mode: str, existing_ids: set,
             model: str = "claude-opus-4-7") -> list[dict]:
    """Ask Opus for a batch of specs. Return validated ones with unique IDs."""
    prompt = _prompt_for(mode, batch_size)

    try:
        r = subprocess.run(
            ["claude", "--print", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=600, cwd="/tmp",
        )
        raw = r.stdout
    except Exception as e:
        return []

    # Rate-limit / error detection
    if "out of extra usage" in raw.lower() or "rate limit" in raw.lower():
        return []

    arr = extract_json_array(raw)
    if not arr:
        return []

    return _validate_specs(arr, existing_ids)


REJECTED_PATH = Path(__file__).resolve().parent / "rejected_tasks.jsonl"
_rejected_lock = threading.Lock()


def _append_rejected(spec: dict, reason: str) -> None:
    """Save rejected specs to a sidecar so Sonnet can patch them later."""
    record = {**spec, "_reject_reason": reason}
    with _rejected_lock:
        with REJECTED_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")


def _validate_specs(arr: list, existing_ids: set) -> list[dict]:
    kept = []
    for spec in arr:
        if not isinstance(spec, dict):
            continue
        base_id = spec.get("id", f"gen_{uuid.uuid4().hex[:6]}")
        tid = base_id
        suffix = 0
        while tid in existing_ids:
            suffix += 1
            tid = f"{base_id}_{suffix}"
        spec["id"] = tid
        existing_ids.add(tid)

        ok, reason = validate_spec(spec)
        if ok:
            kept.append(spec)
        else:
            _append_rejected(spec, reason)
    return kept


def append_specs(specs: list[dict]):
    with OUT_PATH.open("a") as f:
        for s in specs:
            f.write(json.dumps(s) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=int, default=20,
                    help="Number of Opus calls to make")
    ap.add_argument("--batch-size", type=int, default=20,
                    help="Tasks per batch")
    ap.add_argument("--workers", type=int, default=3,
                    help="Parallel Opus calls")
    ap.add_argument("--mode", choices=["short", "long", "mix", "agent"], default="short")
    ap.add_argument("--model", type=str, default="claude-sonnet-4-6",
                    help="Claude model for meta-gen (Sonnet by default)")
    ap.add_argument("--ollama-url", type=str, default=None,
                    help="If set, generate via local ollama (free) instead of Claude.")
    ap.add_argument("--ollama-model", type=str, default=None,
                    help="Ollama model tag, e.g. qwen2.5-coder:32b")
    args = ap.parse_args()
    if args.ollama_url and not args.ollama_model:
        ap.error("--ollama-url requires --ollama-model")

    existing = load_existing_ids()
    print(f"Existing IDs: {len(existing)}")
    print(f"Generating {args.batches} batches of {args.batch_size} ({args.mode} mode)")
    start = time.time()

    total_kept = 0
    total_validated = 0
    lock = []  # not thread-safe but fine for append-only

    def work(i):
        mode = args.mode
        if mode == "mix":
            mode = "long" if i % 3 == 0 else "short"
        if args.ollama_url:
            specs = gen_batch_ollama(args.batch_size, mode, existing,
                                     args.ollama_model, args.ollama_url)
        else:
            specs = gen_batch(args.batch_size, mode, existing, model=args.model)
        return i, mode, specs

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(work, i): i for i in range(args.batches)}
        for fut in as_completed(futs):
            i, mode, specs = fut.result()
            kept = len(specs)
            total_kept += kept
            # Append immediately so partial progress is saved
            if specs:
                append_specs(specs)
            print(f"  batch {i+1} ({mode}): {kept} valid specs")

    elapsed = time.time() - start
    print(f"\n=== DONE in {elapsed:.1f}s ===")
    print(f"Total validated new specs: {total_kept}")
    print(f"Saved to: {OUT_PATH}")


if __name__ == "__main__":
    main()
