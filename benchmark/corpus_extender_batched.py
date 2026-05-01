#!/usr/bin/env python3
"""Batched Sigil corpus extender.

Compared to corpus_extender.py:
  - Asks for N programs per call (default 25). Grammar is sent once,
    so per-task input cost is ~30x lower.
  - Sonnet 4.6 by default, falls back to Opus 4.7 only on per-task
    failure (after batch attempt).
  - Returns JSON array, one entry per task id.

Pipeline per task:
  1. Verify Python reference produces expected output (catches bad specs).
  2. Group todo tasks into batches of B; ask Sonnet for JSON array.
  3. For each task in the batch reply: run Sigil, compare stdout.
  4. Collect failures; retry with Opus single-shot.
  5. Save successful programs.

Usage:
    python corpus_extender_batched.py --batch 25 --workers 2
    python corpus_extender_batched.py --ids id1,id2 --batch 5
    python corpus_extender_batched.py --limit 100 --no-fallback
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_bank import TASKS as HAND_TASKS

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")
GRAMMAR = (REPO_ROOT / ".sigil.grammar").read_text()
OUT_DIR = REPO_ROOT / "examples" / "corpus_extensions"


def _load_generated():
    p = Path(__file__).resolve().parent / "generated_tasks.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


TASKS = HAND_TASKS + _load_generated()


SLIM_HEADER = """Sigil is a Lisp-shaped scripting language. Here are 6 worked examples:

# Uppercase the first arg
(println (upper $0))

# Sum all space-separated ints in arg
(println (sum (parse_ints $0)))

# Word count of arg
(println (len (split $0 " ")))

# Sum of squares of evens in arg (functional pipeline)
(println (sum (map_arr (filter (parse_ints $0) (\\x (eq (mod x 2) 0))) (\\x (mul x x)))))

# CSV row → "Alice,30,NYC" filter where city == "NYC"; uses for-each
(set rows (split $0 "\\n"))
(for-each row rows
  (set fields (split row ","))
  (if (eq (last fields) $1)
    (println row)))

# Caesar cipher shift on alpha
(fn shift c int n int -> int
  (cond
    ((and (ge c 65) (le c 90)) (ret (add 65 (mod (add (sub c 65) n) 26))))
    ((and (ge c 97) (le c 122)) (ret (add 97 (mod (add (sub c 97) n) 26))))
    (true (ret c))))
(println (join (map_arr (chars $1) (\\c (char_from_code (shift (string_get c 0) #0)))) ""))

Key builtins: len, str, fmt, split, join, sort, push, filter, map_arr, reduce,
first, last, rev, swapcase, title, uniq, counter, sort_by, entries, enumerate,
scan, slice, merge, range, sum, parse_ints, chars, char_from_code, string_get,
string_replace, string_find, string_contains, string_starts_with, mod, add, sub,
mul, div, eq, ne, lt, gt, le, ge, neg, abs, in, has, get_or, regex_compile,
regex_match, regex_find_all, regex_replace.
Aliases: map=map_arr, head=first, tail=rest, contains=in, size/length=len,
upcase=upper, downcase=lower, let=set, def=fn. + - * / % < > <= >= = work.
HOFs accept either (map fn arr) or (map arr fn).
Empty: [] {{}}. Lambdas (\\x ...) or (\\(x y) ...). (println x) auto-newlines.
"""

BATCH_PROMPT = """{grammar}

You will write Sigil programs for a batch of tasks. Each task gives you:
  id, desc (what the program does), args (CLI args it receives),
  expected (exact stdout — match this byte-for-byte).

Rules — follow STRICTLY for correct, minimal code:
1. Top-level script mode (no (module ...) wrapper) unless multiple fns are needed.
2. CLI args: $0 is first user arg as string, #0 is first as int. $1, #1, etc.
3. Omit type annotations on (set ...) and (for-each ...).
4. PREFER functional pipelines: (sum (map_arr arr (\\x ...))) over for-each loops.
5. Short aliases available: len, str, fmt, split, join, sort, push, filter,
   map_arr, reduce, first, last, rev, swapcase, title, uniq, counter, sort_by,
   entries, enumerate, scan, map_kv, map_pairs, diff, inter, union, slice,
   merge, range.
6. Alt-names accepted: map=map_arr, head/car=first, tail/cdr=rest,
   contains/has=in, size/length=len, upcase=upper, downcase=lower, let=set,
   def=fn. Operators + - * / % < > <= >= = work as builtins.
7. HOFs accept either argument order.
8. Empty collections: [] and {{}}. NEVER (array_new) or (map_new).
9. Lambdas: (\\x expr) for 1 arg, (\\(x y) expr) for multi.
10. (println x) auto-adds newline.
11. Comparisons are prefix: (eq a b), (lt a b), (gt a b), etc.

TASKS (JSON array):
{tasks_json}

Return ONLY a JSON array of objects, one per input task, in the SAME ORDER:
  [{{"id": "<task id>", "code": "<raw Sigil program, no fences>"}}]

The "code" string must be the complete Sigil program — no markdown fences,
no prose, just valid Sigil. Do not include comments. JSON-escape newlines as \\n
and quotes as \\". Output ONLY the JSON array."""


SINGLE_PROMPT = """{grammar}

Write a Sigil program that does exactly this:

TASK: {desc}

When called with CLI args {args}, output must be EXACTLY:
{expected!r}

Rules: top-level script; $0/$1 string args, #0/#1 int args; short aliases ok
(len, fmt, split, map, filter, reduce, first, last, rev, sort, push, range, slice);
empty collections [] {{}}; lambdas (\\x ...); (println x) auto-newlines.

Output ONLY the raw Sigil code. No fences. No prose."""


RATE_LIMIT_MARKERS = [
    "out of extra usage",
    "rate limit",
    "usage limit",
    # "resets " removed — too aggressive; matched valid code with "reset" in identifiers
]


def is_rate_limit_msg(text: str) -> bool:
    low = text.lower()[:500]
    return any(m in low for m in RATE_LIMIT_MARKERS)


def run_python(code: str, args: list) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([sys.executable, f.name] + [str(a) for a in args],
                             capture_output=True, text=True, timeout=10)
            return r.returncode == 0, r.stdout
        finally:
            os.unlink(f.name)


def run_sigil(code: str, args: list) -> tuple[bool, str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name] + [str(a) for a in args],
                             capture_output=True, text=True, timeout=10)
            return r.returncode == 0, r.stdout, r.stderr
        finally:
            os.unlink(f.name)


def strip_fences(code: str) -> str:
    s = code.strip()
    for fence in ["```sigil", "```lisp", "```scheme", "```json", "```"]:
        if s.startswith(fence):
            s = s[len(fence):].lstrip()
            break
    if s.endswith("```"):
        s = s[:-3].rstrip()
    return s


def call_claude(prompt: str, model: str, timeout: int = 600) -> str:
    """Invoke claude --print. Returns raw stdout, or '' on rate-limit/error."""
    try:
        r = subprocess.run(
            ["claude", "--print", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=timeout, cwd="/tmp",
        )
        if is_rate_limit_msg(r.stdout):
            return ""
        return r.stdout
    except Exception:
        return ""


def extract_json_array(raw: str) -> list | None:
    """Pull a JSON array from response text; tolerant of stray prose / fences."""
    s = strip_fences(raw)
    # Find outermost [...]
    start = s.find("[")
    end = s.rfind("]")
    if start < 0 or end <= start:
        return None
    candidate = s[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Try fixing common issues: trailing commas, single quotes
        fixed = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None


def gen_batch(tasks: list[dict], model: str, slim: bool = True) -> dict[str, str]:
    """Ask the model for code for each task. Returns {id -> code} (may be partial)."""
    # Compact JSON to keep prompt small
    tasks_json = json.dumps([
        {"id": t["id"], "desc": t["desc"], "args": t["args"], "expected": t["expected"]}
        for t in tasks
    ])
    header = SLIM_HEADER if slim else GRAMMAR
    prompt = BATCH_PROMPT.format(grammar=header, tasks_json=tasks_json)
    raw = call_claude(prompt, model, timeout=600)
    if not raw:
        return {}
    arr = extract_json_array(raw)
    if not arr:
        return {}
    out = {}
    for item in arr:
        if not isinstance(item, dict):
            continue
        tid = item.get("id")
        code = item.get("code", "")
        if tid and isinstance(code, str) and code.strip():
            out[tid] = strip_fences(code)
    return out


def gen_single(task: dict, model: str) -> str:
    """Single-task fallback for batch failures. Uses full grammar for max quality."""
    prompt = SINGLE_PROMPT.format(grammar=GRAMMAR, desc=task["desc"],
                                  args=task["args"], expected=task["expected"])
    raw = call_claude(prompt, model, timeout=180)
    return strip_fences(raw) if raw else ""


def validate_and_save(task: dict, code: str) -> tuple[bool, str]:
    """Run Sigil with task args, check stdout. Saves on match. Returns (ok, info)."""
    ok, out, err = run_sigil(code, task["args"])
    if ok and out == task["expected"]:
        out_path = OUT_DIR / f"{task['id']}.sigil"
        out_path.write_text(code.rstrip() + "\n")
        return True, f"{len(code)}b"
    if not ok:
        return False, f"runtime: {err[:80]}"
    return False, f"mismatch: got {out[:60]!r}"


def process_batch(batch: list[dict], primary_model: str, fallback_model: str | None,
                 force: bool, slim: bool = True) -> list[dict]:
    """Process one batch. Returns list of result dicts."""
    # Filter out already-done tasks unless force
    pending = []
    results = []
    for t in batch:
        out_path = OUT_DIR / f"{t['id']}.sigil"
        if out_path.exists() and not force:
            results.append({"id": t["id"], "status": "skip-exists"})
            continue
        # Validate Python ref
        ok_py, out_py = run_python(t["python"], t["args"])
        if not ok_py or out_py != t["expected"]:
            results.append({"id": t["id"], "status": "bad-python-spec",
                          "note": f"py_out={out_py!r}"})
            continue
        pending.append(t)

    if not pending:
        return results

    # Batch attempt with primary model
    code_map = gen_batch(pending, primary_model, slim=slim)
    failed_for_fallback = []
    for t in pending:
        code = code_map.get(t["id"], "")
        if not code:
            failed_for_fallback.append((t, "no code in batch reply"))
            continue
        ok, info = validate_and_save(t, code)
        if ok:
            results.append({"id": t["id"], "status": "ok", "via": primary_model,
                          "info": info})
        else:
            failed_for_fallback.append((t, info))

    # Fallback: single-shot with fallback model
    if fallback_model:
        for t, prev_err in failed_for_fallback:
            code = gen_single(t, fallback_model)
            if not code:
                results.append({"id": t["id"], "status": "failed",
                              "note": f"primary: {prev_err}; fallback: empty"})
                continue
            ok, info = validate_and_save(t, code)
            if ok:
                results.append({"id": t["id"], "status": "ok",
                              "via": f"{fallback_model} (fallback)", "info": info})
            else:
                results.append({"id": t["id"], "status": "failed",
                              "note": f"primary: {prev_err}; fallback: {info}"})
    else:
        for t, err in failed_for_fallback:
            results.append({"id": t["id"], "status": "failed", "note": err})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=8, help="Tasks per Sonnet call")
    ap.add_argument("--full-grammar", action="store_true",
                    help="Send full grammar (.sigil.grammar) instead of slim header")
    ap.add_argument("--workers", type=int, default=2, help="Parallel batches")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", type=str, default=None,
                    help="Comma-separated task ids")
    ap.add_argument("--force", action="store_true",
                    help="Regenerate even if file exists")
    ap.add_argument("--primary", type=str, default="claude-sonnet-4-6")
    ap.add_argument("--fallback", type=str, default="",
                    help="Opus-tier fallback for per-task retries; '' (default) skips it. "
                         "Pass --fallback claude-opus-4-7 to enable.")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fallback = args.fallback if args.fallback else None

    tasks = TASKS
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",")}
        tasks = [t for t in tasks if t["id"] in wanted]
    if not args.force:
        tasks = [t for t in tasks if not (OUT_DIR / f"{t['id']}.sigil").exists()]
    if args.limit:
        tasks = tasks[:args.limit]

    if not tasks:
        print("Nothing to do.")
        return

    # Split into batches
    batches = [tasks[i:i + args.batch] for i in range(0, len(tasks), args.batch)]
    print(f"{len(tasks)} tasks → {len(batches)} batches of up to {args.batch}, "
          f"primary={args.primary}, fallback={fallback or 'none'}, "
          f"workers={args.workers}")
    start = time.time()

    all_results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        slim = not args.full_grammar
        futs = {
            pool.submit(process_batch, b, args.primary, fallback, args.force, slim): i
            for i, b in enumerate(batches)
        }
        for fut in as_completed(futs):
            i = futs[fut]
            res = fut.result()
            ok = sum(1 for r in res if r["status"] == "ok")
            failed = sum(1 for r in res if r["status"] == "failed")
            skip = sum(1 for r in res if r["status"] == "skip-exists")
            print(f"  batch {i + 1}/{len(batches)}: ok={ok} failed={failed} skip={skip}")
            all_results.extend(res)

    elapsed = time.time() - start
    counts = {}
    for r in all_results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"\n=== DONE in {elapsed:.1f}s ===")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")

    log_path = REPO_ROOT / "benchmark" / "corpus_extension_batched_log.json"
    log_path.write_text(json.dumps(all_results, indent=2))
    print(f"\nLog saved to {log_path}")


if __name__ == "__main__":
    main()
