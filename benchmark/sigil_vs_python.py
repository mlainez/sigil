#!/usr/bin/env python3
"""Same fine-tuned model, same tasks, two languages: Sigil vs Python.

For the iterations the fine-tuned 7B excelled at (iter 4 parsing,
iter 5 state machines, iter 8 bit ops, iter 10 misc), generate both
languages and compare correctness rates. Headline question: does the
LoRA make qwen-sigil:7b *better* at Sigil than at the language it was
already pre-trained on?

Both passes use RAG (Sigil retrievals are skipped for the Python pass —
not relevant). System prompts differ to disambiguate the target.
"""
from __future__ import annotations

import json, sys, time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag
from corpus_extender import gen_sigil_ollama, run_sigil, run_python
from iteration_tasks import ALL_BATCHES

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen-sigil:7b"


PYTHON_SYSTEM = (
    "You write Python 3 programs. Use stdin/argv. Output ONLY raw Python code, "
    "no markdown fences, no prose. Keep it simple — read sys.argv, do the work, "
    "print the result."
)


PYTHON_PROMPT = (
    "Write a Python 3 program that does exactly this:\n\n"
    "TASK: {desc}\n\n"
    "Example: when called with CLI args {args}, output must be EXACTLY:\n"
    "{expected!r}\n\n"
    "Output ONLY the raw Python code."
)


def gen_python(task: dict, model: str, url: str, timeout: int = 120) -> str:
    """Ask the model for Python via /api/generate with python system prompt."""
    body = json.dumps({
        "model": model,
        "prompt": PYTHON_PROMPT.format(
            desc=task["desc"], args=task["args"], expected=task["expected"]),
        "system": PYTHON_SYSTEM,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2048, "top_p": 0.9},
    }).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        out = data.get("response", "").strip()
        # Strip fences
        for fence in ["```python", "```py", "```"]:
            if out.startswith(fence):
                out = out[len(fence):].lstrip()
                break
        if out.endswith("```"):
            out = out[:-3].rstrip()
        return out
    except Exception:
        return ""


def main():
    # Iterations to test (1-indexed → 0-indexed batch lookup)
    target_iters = [4, 5, 8, 10]

    print(f"Loading RAG index...")
    index = rag.load_index()

    rows = []
    grand = {"sigil": 0, "python": 0, "n": 0,
             "sigil_seconds": 0.0, "python_seconds": 0.0,
             "sigil_chars": 0, "python_chars": 0}

    for iter_idx in target_iters:
        batch = ALL_BATCHES[iter_idx - 1]
        print(f"\n=== Iteration {iter_idx} ===")
        for t in batch:
            grand["n"] += 1

            # Sigil with RAG (matching the 74% loop conditions)
            hits = rag.query(t["desc"], k=5, index=index, min_score=0.72, top1_floor=0.78)
            block = rag.format_examples(hits) if hits else ""
            t0 = time.time()
            code_sigil = gen_sigil_ollama(t, MODEL, OLLAMA_URL,
                                          temperature=0.0, slim=False, rag_block=block)
            ts = time.time() - t0
            ok_s, out_s, err_s = (False, "", "no code")
            if code_sigil:
                ok_s, out_s, err_s = run_sigil(code_sigil, t["args"])
            sigil_good = ok_s and out_s == t["expected"]

            # Python (no RAG — model has Python in its base)
            t0 = time.time()
            code_python = gen_python(t, MODEL, OLLAMA_URL)
            tp = time.time() - t0
            ok_p, out_p = (False, "")
            if code_python:
                ok_p, out_p = run_python(code_python, t["args"])
            python_good = ok_p and out_p == t["expected"]

            grand["sigil"] += int(sigil_good)
            grand["python"] += int(python_good)
            grand["sigil_seconds"] += ts
            grand["python_seconds"] += tp
            grand["sigil_chars"] += len(code_sigil)
            grand["python_chars"] += len(code_python)
            sm = "P" if sigil_good else "F"
            pm = "P" if python_good else "F"
            print(f"  {t['id']:30s} sigil:{sm} ({ts:5.1f}s, {len(code_sigil):3d}c) "
                  f"python:{pm} ({tp:5.1f}s, {len(code_python):3d}c)")

            rows.append({
                "iter": iter_idx, "id": t["id"],
                "sigil_pass": sigil_good, "python_pass": python_good,
                "sigil_seconds": round(ts, 2), "python_seconds": round(tp, 2),
                "sigil_code": code_sigil, "python_code": code_python,
                "sigil_chars": len(code_sigil), "python_chars": len(code_python),
                "sigil_stdout": out_s, "python_stdout": out_p,
                "sigil_stderr": err_s,
            })

    print(f"\n=== SUMMARY ({grand['n']} tasks across iters {target_iters}) ===")
    n = grand['n']
    print(f"  Sigil  passes: {grand['sigil']:2d}/{n} ({grand['sigil']*100/n:.0f}%) | "
          f"avg gen {grand['sigil_seconds']/n:5.2f}s | "
          f"avg code {grand['sigil_chars']/n:5.0f} chars")
    print(f"  Python passes: {grand['python']:2d}/{n} ({grand['python']*100/n:.0f}%) | "
          f"avg gen {grand['python_seconds']/n:5.2f}s | "
          f"avg code {grand['python_chars']/n:5.0f} chars")
    print(f"  Sigil − Python correctness: {grand['sigil'] - grand['python']:+d}")
    if grand['python_seconds'] > 0:
        print(f"  Sigil/Python time ratio: {grand['sigil_seconds']/grand['python_seconds']:.2f}×")
    if grand['python_chars'] > 0:
        print(f"  Sigil/Python length ratio: {grand['sigil_chars']/grand['python_chars']:.2f}×")

    out = REPO / "benchmark" / "sigil_vs_python_results.json"
    out.write_text(json.dumps({"summary": grand, "tasks": rows}, indent=2))
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
