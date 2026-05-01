#!/usr/bin/env python3
"""Run N iterations of the A/B-with-fixes loop on disjoint task sets.

Each iteration:
  1. Pull the next 10 fresh tasks from iteration_tasks.ALL_BATCHES.
  2. Run A (no RAG) and B (RAG, default knobs) — 1 attempt each, temp=0.
  3. Bucket B failures by error type. Print the diagnosis so the operator
     (or a wrapper script) can apply language/corpus fixes between
     iterations.
  4. Save per-iteration metrics + raw codes to rag_loop_results.json.

Goal: 1-shot accuracy of B trending to ~10/10 across iterations as fixes
accumulate. We are NOT optimizing for any single iteration's score —
the population effect across all 10 iterations is what matters.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag
from corpus_extender import gen_sigil_ollama, run_python, run_sigil
from iteration_tasks import ALL_BATCHES

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:32b")
RAG_K = int(os.environ.get("RAG_K", "5"))
RAG_MIN_SCORE = float(os.environ.get("RAG_MIN_SCORE", "0.72"))
RAG_MMR_LAMBDA = float(os.environ.get("RAG_MMR_LAMBDA", "1.0"))
RAG_TOP1_FLOOR = float(os.environ.get("RAG_TOP1_FLOOR", "0.78"))

RESULTS_PATH = Path(__file__).resolve().parent / "rag_loop_results.json"


def classify(stderr: str, stdout: str, expected: str) -> str:
    s = (stderr or "").lower()
    if "parse error" in s:
        return "parse_error"
    if "undefined variable" in s or "unbound" in s:
        return "undefined_var"
    if any(p in s for p in ["type mismatch", "type error", "takes (", "requires", "invalid arguments"]):
        return "type_error"
    if "runtime error" in s:
        return "runtime_other"
    if not (stdout or "").strip():
        return "empty_output"
    if stdout != expected:
        return "wrong_output"
    return "unknown"


def run_iteration(iteration_idx: int, tasks: list[dict], index: dict,
                  b_only: bool = False, prior_a_results: dict | None = None) -> dict:
    rows = []
    a_pass = b_pass = 0
    flips_a_to_b = flips_b_to_a = 0
    print(f"\n=== Iteration {iteration_idx} ({len(tasks)} fresh tasks) ===")

    for i, t in enumerate(tasks, 1):
        if b_only and prior_a_results is not None:
            # Reuse A results from a previous run (A is deterministic at
            # temp=0 and identical without RAG, so re-running is wasteful).
            prev = prior_a_results.get(t["id"])
            if prev is None:
                # Fall back to running A if prior data is missing
                pass
            else:
                code_a = prev.get("a_code", "")
                a_out = prev.get("a_stdout", "")
                a_err = prev.get("a_stderr", "")
                a_good = bool(prev.get("a_pass"))
                ta = prev.get("a_seconds", 0.0)
        if not (b_only and prior_a_results is not None and prior_a_results.get(t["id"]) is not None):
            t0 = time.time()
            code_a = gen_sigil_ollama(t, OLLAMA_MODEL, OLLAMA_URL,
                                      temperature=0.0, slim=False, rag_block="")
            ta = time.time() - t0
            a_ok, a_out, a_err = (False, "", "no code")
            if code_a:
                a_ok, a_out, a_err = run_sigil(code_a, t["args"])
            a_good = a_ok and a_out == t["expected"]

        # B pass — RAG, single attempt
        hits = rag.query(t["desc"], k=RAG_K, index=index,
                         min_score=RAG_MIN_SCORE, mmr_lambda=RAG_MMR_LAMBDA,
                         top1_floor=RAG_TOP1_FLOOR)
        block = rag.format_examples(hits) if hits else ""
        t0 = time.time()
        code_b = gen_sigil_ollama(t, OLLAMA_MODEL, OLLAMA_URL,
                                  temperature=0.0, slim=False, rag_block=block)
        tb = time.time() - t0
        b_ok, b_out, b_err = (False, "", "no code")
        if code_b:
            b_ok, b_out, b_err = run_sigil(code_b, t["args"])
        b_good = b_ok and b_out == t["expected"]

        a_pass += int(a_good); b_pass += int(b_good)
        if not a_good and b_good: flips_a_to_b += 1
        if a_good and not b_good: flips_b_to_a += 1

        a_status = "PASS" if a_good else f"FAIL({classify(a_err, a_out, t['expected'])})"
        b_status = "PASS" if b_good else f"FAIL({classify(b_err, b_out, t['expected'])})"
        diff = "B+" if (not a_good and b_good) else \
               "B-" if (a_good and not b_good) else \
               "= " if a_good else ".."
        top = hits[0]["score"] if hits else 0.0
        print(f"  [{i:2}/{len(tasks)}] {diff} {t['id']:30s} A:{a_status:24s} "
              f"B:{b_status:24s} top_sim={top:.2f}")
        if not b_good:
            short = b_err.strip().splitlines()[0][:90] if b_err else (b_out or "no out")[:90]
            print(f"        B: {short}")

        rows.append({
            "id": t["id"],
            "a_pass": a_good, "b_pass": b_good,
            "a_bucket": classify(a_err, a_out, t["expected"]) if not a_good else None,
            "b_bucket": classify(b_err, b_out, t["expected"]) if not b_good else None,
            "a_seconds": round(ta, 1), "b_seconds": round(tb, 1),
            "a_code": code_a, "b_code": code_b,
            "a_stdout": a_out, "b_stdout": b_out,
            "a_stderr": a_err, "b_stderr": b_err,
            "rag_top_sim": top,
            "rag_hits": [{"score": h["score"], "desc": h["desc"][:100]} for h in hits],
        })

    summary = {
        "iteration": iteration_idx,
        "n_tasks": len(tasks),
        "a_pass": a_pass, "b_pass": b_pass,
        "flips_a_to_b": flips_a_to_b, "flips_b_to_a": flips_b_to_a,
        "net": b_pass - a_pass,
        "tasks": rows,
    }
    print(f"  Iteration {iteration_idx} summary: A {a_pass}/{len(tasks)} | "
          f"B {b_pass}/{len(tasks)} | net {b_pass - a_pass:+d} | "
          f"flips A->B+:{flips_a_to_b} B->A-:{flips_b_to_a}")
    return summary


def append_result(result: dict):
    if RESULTS_PATH.exists():
        data = json.loads(RESULTS_PATH.read_text())
    else:
        data = {"iterations": []}
    data["iterations"].append(result)
    RESULTS_PATH.write_text(json.dumps(data, indent=2))


def main():
    global OLLAMA_MODEL
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1, help="1-indexed iteration to run")
    ap.add_argument("--count", type=int, default=1, help="how many iterations to run")
    ap.add_argument("--reset", action="store_true", help="erase prior results")
    ap.add_argument("--b-only", action="store_true",
                    help="Reuse A results from prior_results_path; only re-run B")
    ap.add_argument("--prior-results-path", default=str(RESULTS_PATH),
                    help="JSON file to read prior A-pass results from")
    ap.add_argument("--out", default=str(RESULTS_PATH),
                    help="Where to append the new iteration result")
    ap.add_argument("--model", default=OLLAMA_MODEL,
                    help="Ollama model tag (default: qwen2.5-coder:32b or $OLLAMA_MODEL)")
    args = ap.parse_args()
    OLLAMA_MODEL = args.model
    print(f"Using ollama model: {OLLAMA_MODEL}")

    out_path = Path(args.out)
    if args.reset and out_path.exists():
        out_path.unlink()
        print(f"Reset {out_path}")

    # Load prior A results once if --b-only
    prior_by_iter: dict[int, dict[str, dict]] = {}
    if args.b_only:
        prior_path = Path(args.prior_results_path)
        if prior_path.exists():
            prior = json.loads(prior_path.read_text())
            for it in prior.get("iterations", []):
                # Index by iteration; skip duplicates (latest wins)
                prior_by_iter[it["iteration"]] = {t["id"]: t for t in it["tasks"]}
            print(f"Loaded prior A results for iters {sorted(prior_by_iter)}")

    print(f"Loading RAG index...")
    index = rag.load_index()
    print(f"  {index['count']} entries, dim {index['dim']}")

    for i in range(args.start, args.start + args.count):
        batch_idx = i - 1
        if batch_idx >= len(ALL_BATCHES):
            print(f"No more batches available (only {len(ALL_BATCHES)} batches)")
            break
        tasks = ALL_BATCHES[batch_idx]
        prior_a = prior_by_iter.get(i) if args.b_only else None
        result = run_iteration(i, tasks, index, b_only=args.b_only, prior_a_results=prior_a)
        # Write to args.out (may differ from RESULTS_PATH)
        if out_path.exists():
            data = json.loads(out_path.read_text())
        else:
            data = {"iterations": []}
        data["iterations"].append(result)
        out_path.write_text(json.dumps(data, indent=2))
    print(f"\nResults appended to {out_path}")


if __name__ == "__main__":
    main()
