#!/usr/bin/env python3
"""Same 40 tasks as sigil_vs_python.py, but Python only on un-tuned 7B.
Establishes the Python-capability baseline for the model BEFORE LoRA."""
from __future__ import annotations

import json, sys, time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_extender import run_python
from iteration_tasks import ALL_BATCHES

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5-coder:7b"   # un-tuned

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


def gen_python(task, model, url, timeout=120):
    body = json.dumps({
        "model": model,
        "prompt": PYTHON_PROMPT.format(desc=task["desc"], args=task["args"], expected=task["expected"]),
        "system": PYTHON_SYSTEM,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2048, "top_p": 0.9},
    }).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/generate", data=body,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        out = data.get("response", "").strip()
        for fence in ["```python", "```py", "```"]:
            if out.startswith(fence):
                out = out[len(fence):].lstrip(); break
        if out.endswith("```"):
            out = out[:-3].rstrip()
        return out
    except Exception:
        return ""


def main():
    target_iters = [4, 5, 8, 10]
    rows = []
    grand = {"pass": 0, "n": 0, "seconds": 0.0, "chars": 0}

    for iter_idx in target_iters:
        batch = ALL_BATCHES[iter_idx - 1]
        print(f"\n=== Iteration {iter_idx} ===")
        for t in batch:
            grand["n"] += 1
            t0 = time.time()
            code = gen_python(t, MODEL, OLLAMA_URL)
            tp = time.time() - t0
            ok, out_p = (False, "")
            if code:
                ok, out_p = run_python(code, t["args"])
            good = ok and out_p == t["expected"]
            grand["pass"] += int(good)
            grand["seconds"] += tp
            grand["chars"] += len(code)
            mark = "P" if good else "F"
            print(f"  {t['id']:30s} python:{mark} ({tp:5.1f}s, {len(code):3d}c)")
            rows.append({"iter": iter_idx, "id": t["id"], "pass": good,
                         "seconds": round(tp, 2), "chars": len(code),
                         "code": code, "stdout": out_p})

    print(f"\n=== UN-TUNED 7B PYTHON ===")
    n = grand['n']
    print(f"  passes:    {grand['pass']:2d}/{n} ({grand['pass']*100/n:.0f}%)")
    print(f"  avg gen:   {grand['seconds']/n:.2f}s")
    print(f"  avg chars: {grand['chars']/n:.0f}")

    out = REPO / "benchmark" / "python_baseline_results.json"
    out.write_text(json.dumps({"summary": grand, "tasks": rows}, indent=2))
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
