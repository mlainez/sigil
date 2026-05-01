#!/usr/bin/env python3
"""Local-only corpus extender. Uses qwen-sigil:7b (or any local ollama
model) with up to N retries. Each retry feeds:

  - The previous Sigil attempt
  - The interpreter's stderr (or --lint output if it was a parse error)
  - The expected output vs got output (if it ran but produced wrong text)

This eats our own dog food: the local fine-tuned 7B generates the corpus
that will train the next fine-tuned model. No cloud calls.

Usage:
    python local_corpus_extender.py --ids id1,id2,id3 --model qwen-sigil:7b --max-attempts 4
"""
from __future__ import annotations

import argparse, json, os, subprocess, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag
from corpus_extender import (
    GRAMMAR, PROMPT, gen_sigil_ollama, run_python, run_sigil, strip_fences,
)
from iteration_tasks import ALL_BATCHES

OLLAMA_URL = "http://localhost:11434"
SIGIL_BIN = str(REPO / "interpreter" / "_build" / "default" / "vm.exe")
OUT_DIR = REPO / "examples" / "corpus_extensions"


RETRY_PROMPT = """{grammar}

Write a Sigil program that does exactly this:

TASK: {desc}

When called with CLI args {args}, output must be EXACTLY:
{expected!r}

YOUR PREVIOUS ATTEMPT (which was wrong):
```
{prev_code}
```

Diagnostic feedback:
{hint}

Apply the feedback and try again. Output ONLY the corrected Sigil code.
No markdown fences, no prose."""


def lint_or_run_for_hint(code: str, args: list, expected: str) -> tuple[str, bool]:
    """Run lint then runtime; return (hint string, passed bool)."""
    # First, lint pass for paren errors
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        path = f.name
    try:
        lr = subprocess.run([SIGIL_BIN, "--lint", path],
                            capture_output=True, text=True, timeout=10)
        if lr.returncode != 0 and lr.stderr.strip():
            return (lr.stderr.strip(), False)
        # Lint OK → run the program
        rr = subprocess.run([SIGIL_BIN, path] + list(args),
                            capture_output=True, text=True, timeout=10)
        if rr.returncode == 0 and rr.stdout == expected:
            return ("(passed)", True)
        if rr.stderr.strip():
            return (rr.stderr.strip().splitlines()[0], False)
        # Ran cleanly but wrong output
        return (
            f"Program ran cleanly but produced {rr.stdout!r} instead of "
            f"the required exact output {expected!r}. Trace through your "
            f"logic step by step against the expected output to find the "
            f"discrepancy.",
            False,
        )
    finally:
        os.unlink(path)


def gen_with_retries(task: dict, model: str, max_attempts: int,
                     index: dict, rag_k: int = 5) -> dict:
    """Generate Sigil for a task with up to N attempts. Each retry
    receives the previous attempt + lint/runtime feedback."""
    hits = rag.query(task["desc"], k=rag_k, index=index, min_score=0.65)
    block = rag.format_examples(hits) if hits else ""

    last_code = ""
    last_err = ""
    temps = [0.0, 0.3, 0.5, 0.7][:max_attempts]

    for i, temp in enumerate(temps):
        if i == 0:
            code = gen_sigil_ollama(task, model, OLLAMA_URL,
                                    temperature=temp, slim=False, rag_block=block)
        else:
            prompt = RETRY_PROMPT.format(
                grammar=GRAMMAR, desc=task["desc"], args=task["args"],
                expected=task["expected"], prev_code=last_code, hint=last_err)
            # Send custom prompt directly via the same ollama endpoint
            import urllib.request
            body = json.dumps({
                "model": model, "prompt": prompt, "stream": False,
                "options": {"temperature": temp, "num_predict": 4096, "top_p": 0.9},
            }).encode()
            req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=body,
                                          headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    code = strip_fences(json.loads(resp.read()).get("response", ""))
            except Exception:
                code = ""

        if not code:
            last_err = "(empty response from model)"
            continue

        last_code = code
        hint, passed = lint_or_run_for_hint(code, task["args"], task["expected"])
        if passed:
            return {"id": task["id"], "status": "ok", "attempts": i + 1,
                    "code": code, "tokens": len(code)}
        last_err = hint

    return {"id": task["id"], "status": "failed", "attempts": max_attempts,
            "last_code": last_code, "last_err": last_err[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="comma-separated task ids")
    ap.add_argument("--model", default="qwen-sigil:7b")
    ap.add_argument("--max-attempts", type=int, default=4)
    ap.add_argument("--rag-k", type=int, default=5)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load all tasks (handcrafted + generated)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from task_bank import TASKS as HAND_TASKS
    all_tasks = list(HAND_TASKS)
    with open(REPO / "benchmark" / "generated_tasks.jsonl") as f:
        for ln in f:
            if ln.strip():
                all_tasks.append(json.loads(ln))

    wanted = {s.strip() for s in args.ids.split(",")}
    tasks = [t for t in all_tasks if t["id"] in wanted]
    print(f"Targeting {len(tasks)} task(s) using {args.model}, max_attempts={args.max_attempts}")

    print("Loading RAG index...")
    index = rag.load_index()
    print(f"  {index['count']} entries\n")

    results = []
    for i, t in enumerate(tasks, 1):
        out_path = OUT_DIR / f"{t['id']}.sigil"
        if out_path.exists() and not args.force:
            print(f"  [{i}/{len(tasks)}] = {t['id']} (skip exists)")
            results.append({"id": t["id"], "status": "skip-exists"})
            continue

        # Verify python ref
        py_ok, py_out = run_python(t["python"], t["args"])
        if not (py_ok and py_out == t["expected"]):
            print(f"  [{i}/{len(tasks)}] ! {t['id']} bad python spec")
            results.append({"id": t["id"], "status": "bad-python-spec"})
            continue

        t0 = time.time()
        r = gen_with_retries(t, args.model, args.max_attempts, index, args.rag_k)
        elapsed = time.time() - t0
        if r["status"] == "ok":
            out_path.write_text(r["code"].rstrip() + "\n")
            print(f"  [{i}/{len(tasks)}] ✓ {t['id']} (att {r['attempts']}, "
                  f"{r['tokens']}b, {elapsed:.1f}s)")
        else:
            print(f"  [{i}/{len(tasks)}] ✗ {t['id']} after {r['attempts']} "
                  f"attempts ({elapsed:.1f}s) — {r['last_err'][:80]}")
        results.append(r)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n=== DONE: {ok}/{len(tasks)} added ===")
    log_path = REPO / "benchmark" / "local_extender_log.json"
    log_path.write_text(json.dumps(results, indent=2))
    print(f"Log saved to {log_path}")


if __name__ == "__main__":
    main()
