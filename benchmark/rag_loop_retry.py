#!/usr/bin/env python3
"""Re-run iteration B failures with a 2-shot self-correcting retry.

For each B failure:
  Attempt 1: same as the 1-shot loop (RAG block, temp=0).
  Attempt 2: feed the 1-shot's stderr/stdout back as a hint, slightly
             higher temp, same RAG block.

Mirrors the existing gen_sigil_ollama_with_hint pattern from corpus_extender.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag
from corpus_extender import (
    gen_sigil_ollama, gen_sigil_ollama_with_hint, run_sigil,
)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:32b")
RAG_K = int(os.environ.get("RAG_K", "5"))
RAG_MIN_SCORE = float(os.environ.get("RAG_MIN_SCORE", "0.65"))
RAG_TOP1_FLOOR = float(os.environ.get("RAG_TOP1_FLOOR", "0.0"))
RAG_MMR_LAMBDA = float(os.environ.get("RAG_MMR_LAMBDA", "1.0"))

DEFAULT_RESULTS = Path(__file__).resolve().parent / "rag_loop_results.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "rag_loop_retry_results.json"


def retry_iter(iter_idx: int, all_tasks: list, index: dict,
               max_attempts: int = 3) -> dict:
    """Re-run only the B-failures from iteration `iter_idx` with up to
    max_attempts shots. Attempt 1 mirrors the original B pass; subsequent
    attempts feed prior stderr/stdout back as a hint with rising temperature.

    `all_tasks` is the iteration's full task data."""
    from iteration_tasks import ALL_BATCHES
    batch = ALL_BATCHES[iter_idx - 1]
    rows = []
    pass_at: dict[int, int] = {k: 0 for k in range(1, max_attempts + 1)}
    n = 0
    for t in all_tasks:
        if t.get("b_pass"):
            continue
        n += 1

        full_spec = next((s for s in batch if s["id"] == t["id"]), None)
        if not full_spec:
            print(f"  WARN: spec not found for {t['id']}")
            continue
        spec = full_spec

        hits = rag.query(spec["desc"], k=RAG_K, index=index,
                         min_score=RAG_MIN_SCORE, top1_floor=RAG_TOP1_FLOOR,
                         mmr_lambda=RAG_MMR_LAMBDA)
        block = rag.format_examples(hits) if hits else ""

        attempt_codes = []
        attempt_errs = []
        attempt_outs = []
        attempt_secs = []
        prev_code = ""
        prev_out = ""
        prev_err = ""
        passed_at = None

        for attempt in range(1, max_attempts + 1):
            t0 = time.time()
            if attempt == 1:
                code = gen_sigil_ollama(spec, OLLAMA_MODEL, OLLAMA_URL,
                                        temperature=0.0, slim=False,
                                        rag_block=block)
            else:
                hint = (prev_err.strip().splitlines()[0]
                        if prev_err else
                        f"output was {prev_out!r}, expected {spec['expected']!r}")
                code = gen_sigil_ollama_with_hint(
                    spec, OLLAMA_MODEL, OLLAMA_URL,
                    prev_code=prev_code, got_stdout=prev_out,
                    got_stderr=prev_err, hint=hint,
                    temperature=0.1 + 0.2 * attempt, rag_block=block,
                )
            sec = time.time() - t0
            ok, out, err = (False, "", "no code")
            if code:
                ok, out, err = run_sigil(code, spec["args"])
            good = ok and out == spec["expected"]
            attempt_codes.append(code)
            attempt_errs.append(err)
            attempt_outs.append(out)
            attempt_secs.append(round(sec, 1))
            if good:
                pass_at[attempt] += 1
                passed_at = attempt
                break
            prev_code, prev_out, prev_err = code, out, err

        if passed_at is None:
            short = (prev_err.strip().splitlines()[0]
                     if prev_err else (prev_out or "no out"))[:90]
            print(f"  {t['id']}: still FAIL after {max_attempts} attempts ({short})")
        elif passed_at == 1:
            print(f"  {t['id']}: shot1 PASS")
        else:
            print(f"  {t['id']}: shot1 FAIL -> shot{passed_at} PASS")

        rows.append({
            "id": t["id"],
            "passed_at": passed_at,
            "attempts": attempt_codes,
            "errs": attempt_errs,
            "outs": attempt_outs,
            "secs": attempt_secs,
        })

    return {
        "iteration": iter_idx, "retried": n,
        "pass_at_attempt": pass_at,
        "total_pass": sum(pass_at.values()),
        "tasks": rows,
    }


def main():
    global OLLAMA_MODEL
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", nargs="+", type=int,
                    help="Iteration indices (1-based) to retry. Default: all.")
    ap.add_argument("--results", default=str(DEFAULT_RESULTS),
                    help="Input results JSON to read B-failures from")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="Where to write retry results")
    ap.add_argument("--model", default=OLLAMA_MODEL,
                    help="Ollama model tag (default: env OLLAMA_MODEL or qwen2.5-coder:32b)")
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="Maximum attempts per task (default 3)")
    args = ap.parse_args()
    OLLAMA_MODEL = args.model
    print(f"Using ollama model: {OLLAMA_MODEL}")
    print(f"RAG knobs: k={RAG_K} min_score={RAG_MIN_SCORE} top1_floor={RAG_TOP1_FLOOR}")
    print(f"Max attempts: {args.max_attempts}")

    results_path = Path(args.results)
    out_path = Path(args.out)
    data = json.loads(results_path.read_text())
    iter_data = {it["iteration"]: it for it in data["iterations"]}

    iters = args.iters if args.iters else sorted(iter_data.keys())
    print(f"Iterations to process: {iters}")
    print(f"Reading from: {results_path}")
    print(f"Writing to:   {out_path}\n")

    print("Loading RAG index...")
    index = rag.load_index()
    print(f"  {index['count']} entries\n")

    out_data = {
        "model": OLLAMA_MODEL,
        "rag": {"k": RAG_K, "min_score": RAG_MIN_SCORE,
                "top1_floor": RAG_TOP1_FLOOR},
        "max_attempts": args.max_attempts,
        "source": str(results_path),
        "iterations": [],
    }
    for it_idx in iters:
        if it_idx not in iter_data:
            print(f"iteration {it_idx} not found in results")
            continue
        print(f"\n=== Iteration {it_idx} retry ===")
        summary = retry_iter(it_idx, iter_data[it_idx]["tasks"], index,
                             max_attempts=args.max_attempts)
        out_data["iterations"].append(summary)
        out_path.write_text(json.dumps(out_data, indent=2))
        breakdown = ", ".join(f"shot{k}+{v}" for k, v in summary['pass_at_attempt'].items() if v)
        print(f"  retry summary: {summary['total_pass']}/{summary['retried']} recovered  ({breakdown or 'none'})")

    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
