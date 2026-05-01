#!/usr/bin/env python3
"""Evaluate Claude on the 100-task suite using session-resumed CLI calls.

The grammar header (~5K tokens) is sent ONCE per pass via a priming
turn; all subsequent task prompts use `claude --resume <session>` and
only ship the per-task delta. That cuts the bill ~50× vs sending the
grammar with every call.

A and B passes use separate sessions so each only carries the relevant
priming. The B pass primes with grammar + a shared "RAG block" stub;
each retrieval is sent inline as part of the per-task delta.

Usage:
    python eval_claude.py --model claude-sonnet-4-6 --out eval_sonnet.json
    python eval_claude.py --model claude-opus-4-7    --out eval_opus.json
"""
from __future__ import annotations

import json, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag
from corpus_extender import GRAMMAR, run_sigil, strip_fences
from iteration_tasks import ALL_BATCHES

RAG_K = 5
RAG_MIN_SCORE = 0.72
RAG_TOP1_FLOOR = 0.78


PRIMING_PROMPT = (
    "You will write Sigil programs in subsequent turns. Sigil is an S-expression "
    "language with a grammar I will give you now. Acknowledge with the single word "
    "'ready' and wait for tasks.\n\n"
    "GRAMMAR:\n" + GRAMMAR + "\n"
    "RULES:\n"
    "1. Output ONLY the raw Sigil code for each task. No markdown fences, no prose.\n"
    "2. Prefer top-level script mode unless multiple fns are needed.\n"
    "3. CLI args: $0 string, #0 int, $1/$2/..., (arg_str i)/(arg_int i) for dynamic index.\n"
    "4. Functional pipelines preferred. Empty collections: [] and {}.\n"
    "5. Comparisons are prefix: (eq a b), (lt a b), etc.\n"
    "Reply 'ready'."
)


TASK_DELTA = (
    "Write a Sigil program that does exactly this:\n\n"
    "TASK: {desc}\n\n"
    "Example: when called with CLI args {args}, output must be EXACTLY:\n"
    "{expected!r}\n\n"
    "Output ONLY raw Sigil code."
)


TASK_DELTA_RAG = (
    "{rag_block}\n\n"
    "TASK: {desc}\n\n"
    "Example: when called with CLI args {args}, output must be EXACTLY:\n"
    "{expected!r}\n\n"
    "Output ONLY raw Sigil code, no markdown."
)


def claude(prompt: str, model: str, session_id: str | None, timeout: int = 180) -> tuple[str, str]:
    cmd = ["claude", "--print", "--output-format", "json", "--model", model]
    if session_id:
        cmd += ["--resume", session_id]
    cmd += ["-p", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd="/tmp", errors="replace")
    except Exception:
        return "", session_id or ""
    if not r.stdout.strip():
        return "", session_id or ""
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout, session_id or ""
    return (data.get("result") or data.get("text") or "",
            data.get("session_id") or session_id or "")


def prime(model: str) -> str:
    """Send the grammar priming turn. Returns the session_id."""
    print(f"  priming {model}...", end="", flush=True)
    t0 = time.time()
    text, sid = claude(PRIMING_PROMPT, model, None)
    print(f" ready in {time.time()-t0:.1f}s (sid={sid[:8]}...)")
    return sid


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    print(f"Loading RAG index...")
    index = rag.load_index()
    print(f"  {index['count']} entries")

    print(f"Priming sessions for {args.model}...")
    sid_a = prime(args.model)
    sid_b = prime(args.model)

    out_data = {"iterations": [], "model": args.model}
    grand_a = grand_b = 0

    for batch_idx, batch in enumerate(ALL_BATCHES, 1):
        print(f"\n=== Iteration {batch_idx} ===")
        rows = []
        a_pass = b_pass = 0
        for i, t in enumerate(batch, 1):
            # A pass: no RAG
            t0 = time.time()
            delta = TASK_DELTA.format(desc=t["desc"], args=t["args"], expected=t["expected"])
            code_a, sid_a = claude(delta, args.model, sid_a)
            code_a = strip_fences(code_a)
            ta = time.time() - t0
            a_ok, a_out, a_err = (False, "", "no code")
            if code_a:
                a_ok, a_out, a_err = run_sigil(code_a, t["args"])
            a_good = a_ok and a_out == t["expected"]

            # B pass: with RAG block in delta
            hits = rag.query(t["desc"], k=RAG_K, index=index,
                             min_score=RAG_MIN_SCORE, top1_floor=RAG_TOP1_FLOOR)
            block = rag.format_examples(hits) if hits else ""
            t0 = time.time()
            delta_b = TASK_DELTA_RAG.format(rag_block=block, desc=t["desc"],
                                            args=t["args"], expected=t["expected"])
            code_b, sid_b = claude(delta_b, args.model, sid_b)
            code_b = strip_fences(code_b)
            tb = time.time() - t0
            b_ok, b_out, b_err = (False, "", "no code")
            if code_b:
                b_ok, b_out, b_err = run_sigil(code_b, t["args"])
            b_good = b_ok and b_out == t["expected"]

            if a_good: a_pass += 1
            if b_good: b_pass += 1
            top = hits[0]["score"] if hits else 0.0
            mark_a = "P" if a_good else "F"
            mark_b = "P" if b_good else "F"
            print(f"  [{i:2}/10] {t['id']:30s} A:{mark_a} ({ta:.1f}s) B:{mark_b} ({tb:.1f}s) top={top:.2f}")

            rows.append({
                "id": t["id"], "a_pass": a_good, "b_pass": b_good,
                "a_seconds": round(ta, 1), "b_seconds": round(tb, 1),
                "a_code": code_a, "b_code": code_b,
                "a_stdout": a_out, "b_stdout": b_out,
                "a_stderr": a_err, "b_stderr": b_err,
                "rag_top_sim": top,
            })

        grand_a += a_pass; grand_b += b_pass
        print(f"  iter {batch_idx}: A={a_pass}/10 B={b_pass}/10")
        out_data["iterations"].append({
            "iteration": batch_idx,
            "a_pass": a_pass, "b_pass": b_pass,
            "tasks": rows,
        })
        Path(args.out).write_text(json.dumps(out_data, indent=2))

    print(f"\n=== {args.model} FINAL ===")
    print(f"  A (no RAG):   {grand_a}/100")
    print(f"  B (with RAG): {grand_b}/100")
    print(f"  Net: {grand_b - grand_a:+d}")
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
