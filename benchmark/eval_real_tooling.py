#!/usr/bin/env python3
"""Stream C deployment study: 30 real tooling tasks tested across three paths.

Path A: Local fine-tuned Sigil-7B (qwen-sigil:7b or qwen-sigil-v2:7b),
        with RAG and validate-and-retry up to N=3 attempts.

Path B: Local un-tuned Qwen2.5-Coder-7B, single shot, raw Python.

Path C: Cloud Sonnet (or other --model), single shot, raw Python.

For each task, measure:
  - pass/fail
  - wall-clock seconds
  - output length (chars)
  - $ cost (cloud paths) — based on token count × per-token rate
  - Wh estimate (local paths) — wall_seconds × power_draw

Aggregate per category and overall, output decision matrix.
"""
from __future__ import annotations

import argparse, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag
from corpus_extender import (
    GRAMMAR, gen_sigil, gen_sigil_ollama, gen_sigil_ollama_with_hint,
    run_python, run_sigil, strip_fences,
)

OLLAMA_URL = "http://localhost:11434"

# Pricing (USD per million tokens, approximate as of 2026-04)
PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
}

# Power draw estimates (Watts)
POWER_LOCAL_INFERENCE = 180.0  # GPU during inference
POWER_LOCAL_IDLE = 50.0


PYTHON_SYSTEM = (
    "You write Python 3 programs. Use sys.argv for input. Output ONLY raw Python code, "
    "no markdown fences, no prose. Always include `import sys` if you use sys.argv."
)
PYTHON_PROMPT = (
    "Write a Python 3 program that does exactly this:\n\n"
    "TASK: {desc}\n\n"
    "Example: when called with CLI args {args}, output must be EXACTLY:\n"
    "{expected!r}\n\n"
    "Output ONLY the raw Python code."
)


def gen_python_local(task: dict, model: str) -> tuple[str, dict]:
    body = json.dumps({
        "model": model,
        "prompt": PYTHON_PROMPT.format(desc=task["desc"], args=task["args"], expected=task["expected"]),
        "system": PYTHON_SYSTEM,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2048},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=body,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    out = data.get("response", "").strip()
    for fence in ["```python", "```py", "```"]:
        if out.startswith(fence): out = out[len(fence):].lstrip(); break
    if out.endswith("```"): out = out[:-3].rstrip()
    meta = {
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "completion_tokens": data.get("eval_count", 0),
    }
    return out, meta


def gen_python_cloud(task: dict, model: str) -> tuple[str, dict]:
    """Use claude --print with the python prompt."""
    full_prompt = PYTHON_SYSTEM + "\n\n" + PYTHON_PROMPT.format(
        desc=task["desc"], args=task["args"], expected=task["expected"])
    cmd = ["claude", "--print", "--output-format", "json",
           "--model", model, "-p", full_prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=180, cwd="/tmp")
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        text = data.get("result") or ""
        for fence in ["```python", "```py", "```"]:
            if text.startswith(fence): text = text[len(fence):].lstrip(); break
        if text.endswith("```"): text = text[:-3].rstrip()
        usage = data.get("usage", {})
        return text, {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
        }
    except Exception:
        return "", {}


def cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    p = PRICING.get(model)
    if not p: return 0.0
    return in_tok * p["input"] / 1e6 + out_tok * p["output"] / 1e6


def wh_local(seconds: float) -> float:
    return (seconds * POWER_LOCAL_INFERENCE) / 3600.0


def validator_hint(got_stdout: str, expected: str, got_stderr: str) -> str:
    """Synthesize a structured diff hint from (got_stdout, expected, stderr).

    The default 'hint' the retry prompt sees is just last_err[:200] — fine for
    runtime errors but useless for output-shape mismatches where the program
    ran successfully but produced the wrong text. This builds a short, specific
    diagnostic the model can act on:
      - byte/char/line counts
      - first-difference position
      - trailing-newline mismatch flag
      - extra/missing lines
    """
    if got_stderr:
        # Real runtime error — short error message is the most actionable thing.
        return got_stderr.strip().splitlines()[0][:200]
    if got_stdout == expected:
        # Shouldn't happen — caller would have passed already.
        return "No diff."

    notes = []

    # Trailing-newline mismatch is the single highest-frequency wrong-output
    # shape (wc_l, every count-of-X task). Call it out explicitly.
    g_tail = got_stdout.endswith("\n")
    e_tail = expected.endswith("\n")
    if g_tail and not e_tail:
        notes.append("Your output has a TRAILING NEWLINE that should not be there.")
    elif e_tail and not g_tail:
        notes.append("Your output is MISSING the final newline. The expected output ends with '\\n'.")

    # Line-count mismatch — second highest frequency (off-by-one wc_l, missed
    # log lines, extra paragraph separator).
    g_lines = got_stdout.split("\n")
    e_lines = expected.split("\n")
    if len(g_lines) != len(e_lines):
        notes.append(
            f"Your output had {len(g_lines)} lines (split on \\n), expected {len(e_lines)}."
        )

    # First-difference char position — pinpoints exactly where the divergence
    # starts. Useful for off-by-one on a single numeric output.
    common = 0
    for i in range(min(len(got_stdout), len(expected))):
        if got_stdout[i] != expected[i]:
            break
        common += 1
    if common < min(len(got_stdout), len(expected)):
        ctx_g = repr(got_stdout[max(0, common - 5):common + 10])
        ctx_e = repr(expected[max(0, common - 5):common + 10])
        notes.append(
            f"Outputs match for {common} chars, then diverge: yours has {ctx_g}, expected {ctx_e}."
        )
    elif len(got_stdout) > len(expected):
        notes.append(
            f"Your output is LONGER than expected by {len(got_stdout) - len(expected)} chars: extra trailing {got_stdout[len(expected):]!r}."
        )
    elif len(expected) > len(got_stdout):
        notes.append(
            f"Your output is SHORTER than expected by {len(expected) - len(got_stdout)} chars: missing trailing {expected[len(got_stdout):]!r}."
        )

    return " ".join(notes) if notes else f"got {got_stdout!r} expected {expected!r}"


def wh_cloud_estimate(in_tok: int, out_tok: int) -> float:
    """Rough order-of-magnitude estimate. Frontier models are estimated at
    roughly 0.3 Wh per 1K input tokens + 0.5 Wh per 1K output tokens
    (compute + DC overhead). Wide error bars."""
    return (in_tok * 0.3 + out_tok * 0.5) / 1000.0


def eval_task_local_sigil(task: dict, model: str, index: dict, max_attempts: int = 3,
                          fallback_model: str = "", fallback_start: int = -1,
                          fallback_fresh: bool = False,
                          fallback_temp: float = -1.0,
                          validator: bool = False,
                          no_rag: bool = False) -> dict:
    """Fine-tuned Sigil model with RAG and retry. The ensemble routing knobs:
    - fallback_model: model name to swap to when the primary's retries are exhausted
    - fallback_start: attempt index (0-based) at which to swap; -1 = swap on the final
      attempt only (matches old single-attempt fallback). E.g. with max_attempts=4 and
      fallback_start=2: attempts 0-1 = primary, attempts 2-3 = fallback.
    - fallback_fresh: when fallback runs, use the cold prompt (no prev_code/hint) so
      it isn't anchored on the primary's wrong code.
    - fallback_temp: explicit temperature for fallback attempts (-1 = use the
      0.3 + 0.2 * attempt ramp).
    - no_rag: skip RAG entirely. The prompt only contains SLIM_HEADER + task. Useful
      for measuring what the fine-tuned model knows on its own, before adding RAG seeds.
    """
    if no_rag:
        block = ""
    else:
        hits = rag.query(task["desc"], k=5, index=index, min_score=0.65)
        block = rag.format_examples(hits) if hits else ""
    last_code = ""; last_err = ""; last_stdout = ""
    total_seconds = 0.0
    fallback_used = False
    swap_at = (max_attempts - 1) if fallback_start < 0 else fallback_start
    for attempt in range(max_attempts):
        t0 = time.time()
        use_fallback = fallback_model and attempt >= swap_at
        active_model = fallback_model if use_fallback else model
        if use_fallback:
            fallback_used = True

        ramp_temp = 0.3 + 0.2 * attempt
        eff_temp = ramp_temp if (fallback_temp < 0 or not use_fallback) else fallback_temp

        if attempt == 0:
            code = gen_sigil_ollama(task, active_model, OLLAMA_URL,
                                    temperature=0.0, slim=False, rag_block=block)
        elif use_fallback and fallback_fresh:
            # Cold call on the fallback — don't anchor it on the primary's code.
            code = gen_sigil_ollama(task, active_model, OLLAMA_URL,
                                    temperature=eff_temp, slim=False, rag_block=block)
        else:
            # Validator-in-loop: synthesize a structured diff hint from the
            # previous run's stdout/stderr instead of just the raw stderr line.
            if validator:
                hint = validator_hint(last_stdout, task["expected"], last_err)
            else:
                hint = last_err[:200]
            code = gen_sigil_ollama_with_hint(
                task, active_model, OLLAMA_URL,
                prev_code=last_code, got_stdout=last_stdout, got_stderr=last_err,
                hint=hint, temperature=eff_temp,
                rag_block=block)
        total_seconds += time.time() - t0
        if not code: continue
        ok, out, err = run_sigil(code, task["args"])
        if ok and out == task["expected"]:
            return {"path": "local_sigil", "pass": True, "attempts": attempt+1,
                    "code": code, "seconds": round(total_seconds, 2),
                    "chars": len(code), "wh": round(wh_local(total_seconds), 4),
                    "cost_usd": 0.0, "stdout": out, "stderr": "",
                    "model_used": active_model, "fallback_used": fallback_used}
        last_code = code
        last_stdout = out if ok else ""
        last_err = err.strip().splitlines()[0] if err else f"got {out!r} expected {task['expected']!r}"
    return {"path": "local_sigil", "pass": False, "attempts": max_attempts,
            "code": last_code, "seconds": round(total_seconds, 2),
            "chars": len(last_code), "wh": round(wh_local(total_seconds), 4),
            "cost_usd": 0.0, "stdout": "", "stderr": last_err[:200],
            "model_used": active_model, "fallback_used": fallback_used}


def eval_task_local_python(task: dict, model: str) -> dict:
    t0 = time.time()
    code, meta = gen_python_local(task, model)
    seconds = time.time() - t0
    if not code:
        return {"path": "local_python", "pass": False, "seconds": round(seconds,2),
                "chars": 0, "wh": round(wh_local(seconds), 4),
                "cost_usd": 0.0, "stdout": "", "stderr": "no code"}
    ok, out = run_python(code, task["args"])
    return {"path": "local_python", "pass": ok and out == task["expected"],
            "code": code, "seconds": round(seconds,2), "chars": len(code),
            "wh": round(wh_local(seconds), 4), "cost_usd": 0.0,
            "stdout": out, "stderr": "", "tokens": meta}


def eval_task_cloud_python(task: dict, model: str) -> dict:
    t0 = time.time()
    code, meta = gen_python_cloud(task, model)
    seconds = time.time() - t0
    in_tok = meta.get("prompt_tokens", 0)
    out_tok = meta.get("completion_tokens", 0)
    if not code:
        return {"path": f"cloud_{model}", "pass": False, "seconds": round(seconds,2),
                "chars": 0, "wh": round(wh_cloud_estimate(in_tok, out_tok), 4),
                "cost_usd": round(cost_usd(model, in_tok, out_tok), 4),
                "stdout": "", "stderr": "no code"}
    ok, out = run_python(code, task["args"])
    return {"path": f"cloud_{model}", "pass": ok and out == task["expected"],
            "code": code, "seconds": round(seconds,2), "chars": len(code),
            "wh": round(wh_cloud_estimate(in_tok, out_tok), 4),
            "cost_usd": round(cost_usd(model, in_tok, out_tok), 4),
            "stdout": out, "stderr": "", "tokens": meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(REPO / "benchmark" / "real_tooling_tasks.json"))
    ap.add_argument("--sigil-model", default="qwen-sigil-v2:7b")
    ap.add_argument("--sigil-fallback", default="",
                    help="Optional second Sigil model used on the final retry "
                         "attempt. The point is failure-shape diversity: a "
                         "different-lineage model can catch tasks the primary "
                         "keeps missing.")
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="Total attempts per task. With --sigil-fallback set, "
                         "the primary model gets (max_attempts - 1) attempts "
                         "and the fallback gets the last one. Default 3 = "
                         "two primary tries plus one fallback. Use 4 for the "
                         "safer routing where the primary keeps its full retry "
                         "budget before fallback.")
    ap.add_argument("--fallback-start", type=int, default=-1,
                    help="0-based attempt index at which the fallback model "
                         "takes over. -1 (default) = only the final attempt. "
                         "Set to N to give fallback attempts N..max_attempts-1.")
    ap.add_argument("--fallback-fresh", action="store_true",
                    help="When fallback attempts run, use the cold prompt "
                         "without prev_code/hint anchoring, so the fallback "
                         "isn't biased toward fixing the primary's wrong code.")
    ap.add_argument("--fallback-temp", type=float, default=-1.0,
                    help="Explicit temperature for fallback attempts. -1 = use "
                         "the default 0.3+0.2*attempt ramp. Lower (e.g. 0.3) "
                         "gives more deterministic fallback output.")
    ap.add_argument("--validator", action="store_true",
                    help="Use the validator-in-loop hint generator: feeds a "
                         "structural diff (line counts, trailing-newline mismatch, "
                         "first-difference position) into the retry prompt "
                         "instead of just the truncated stderr.")
    ap.add_argument("--no-rag", action="store_true",
                    help="Skip RAG entirely; the prompt only contains "
                         "SLIM_HEADER + the task. Useful for diagnosing what the "
                         "fine-tuned model knows on its own before adding seeds.")
    ap.add_argument("--python-local", default="qwen2.5-coder:7b")
    ap.add_argument("--cloud-model", default="claude-sonnet-4-6")
    ap.add_argument("--out", default=str(REPO / "benchmark" / "stream_c_results.json"))
    ap.add_argument("--skip-cloud", action="store_true",
                    help="Skip cloud comparison (saves $; use for offline runs)")
    args = ap.parse_args()

    tasks = json.loads(Path(args.tasks).read_text())
    print(f"Loaded {len(tasks)} real tooling tasks")
    print(f"Sigil model:        {args.sigil_model}")
    print(f"Python local model: {args.python_local}")
    print(f"Cloud model:        {args.cloud_model if not args.skip_cloud else '(skipped)'}\n")

    print("Loading RAG index...")
    index = rag.load_index()
    print(f"  {index['count']} entries\n")

    rows = []
    aggregates = {"local_sigil": {"pass":0,"sec":0,"wh":0,"cost":0},
                  "local_python": {"pass":0,"sec":0,"wh":0,"cost":0}}
    if not args.skip_cloud:
        aggregates[f"cloud_{args.cloud_model}"] = {"pass":0,"sec":0,"wh":0,"cost":0}

    for i, t in enumerate(tasks, 1):
        print(f"[{i:2}/{len(tasks)}] {t['id']}")
        a = eval_task_local_sigil(t, args.sigil_model, index,
                                  max_attempts=args.max_attempts,
                                  fallback_model=args.sigil_fallback,
                                  fallback_start=args.fallback_start,
                                  fallback_fresh=args.fallback_fresh,
                                  fallback_temp=args.fallback_temp,
                                  validator=args.validator,
                                  no_rag=args.no_rag)
        b = eval_task_local_python(t, args.python_local)
        c = None
        if not args.skip_cloud:
            c = eval_task_cloud_python(t, args.cloud_model)

        for r in [a, b, c]:
            if not r: continue
            k = r["path"]
            aggregates[k]["pass"] += int(r["pass"])
            aggregates[k]["sec"] += r["seconds"]
            aggregates[k]["wh"] += r["wh"]
            aggregates[k]["cost"] += r["cost_usd"]

        print(f"   sigil:  {'P' if a['pass'] else 'F'} ({a['seconds']:.1f}s, {a.get('attempts',1)} attempts)")
        print(f"   python: {'P' if b['pass'] else 'F'} ({b['seconds']:.1f}s)")
        if c: print(f"   cloud:  {'P' if c['pass'] else 'F'} ({c['seconds']:.1f}s, ${c['cost_usd']:.4f})")

        rows.append({"id": t["id"], "category": t.get("source",""),
                     "sigil": a, "python_local": b, "cloud": c})

    print(f"\n=== AGGREGATE ({len(tasks)} tasks) ===")
    for path, agg in aggregates.items():
        n = len(tasks)
        print(f"  {path:25s} pass {agg['pass']:>2}/{n} | "
              f"avg {agg['sec']/n:5.2f}s | "
              f"total Wh {agg['wh']:.3f} | "
              f"total $ {agg['cost']:.4f}")

    out_data = {"sigil_model": args.sigil_model,
                "python_local_model": args.python_local,
                "cloud_model": args.cloud_model if not args.skip_cloud else None,
                "n_tasks": len(tasks),
                "aggregates": aggregates,
                "tasks": rows}
    Path(args.out).write_text(json.dumps(out_data, indent=2))
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
