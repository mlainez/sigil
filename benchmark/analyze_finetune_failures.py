#!/usr/bin/env python3
"""Analyze failures from the fine-tuned-3B loop run.

Buckets failures by error type, surfaces patterns, and exports the
exact (task_id, generated_code, error) tuples so a follow-up training
session can target them.

Usage:
    python analyze_finetune_failures.py
    python analyze_finetune_failures.py --results benchmark/rag_loop_3b_finetuned.json
    python analyze_finetune_failures.py --compare benchmark/rag_loop_3b_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


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


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def collect_failures(data: dict, pass_field: str = "b_pass") -> list[dict]:
    out = []
    for it in data["iterations"]:
        for t in it["tasks"]:
            if not t.get(pass_field):
                stderr = t.get(f"{pass_field[0]}_stderr", "") or ""
                stdout = t.get(f"{pass_field[0]}_stdout", "") or ""
                code = t.get(f"{pass_field[0]}_code", "") or ""
                bucket = classify(stderr, stdout, "")
                out.append({
                    "iter": it["iteration"],
                    "id": t["id"],
                    "bucket": bucket,
                    "stderr": stderr.strip().splitlines()[0][:200] if stderr.strip() else "",
                    "stdout": (stdout[:120] if stdout else ""),
                    "code": code,
                })
    return out


def common_undefineds(failures: list[dict]) -> Counter:
    """Extract undefined-variable names from stderr to find what builtins
    the model is reaching for that don't exist."""
    c = Counter()
    for f in failures:
        if f["bucket"] == "undefined_var":
            err = f["stderr"]
            # parse "Undefined variable: X"
            if "undefined variable:" in err.lower():
                idx = err.lower().index("undefined variable:") + len("undefined variable:")
                name = err[idx:].strip().split()[0] if err[idx:].strip() else ""
                if name:
                    c[name] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(REPO / "benchmark" / "rag_loop_3b_finetuned.json"))
    ap.add_argument("--compare", default=None,
                    help="Optional baseline results to compute lift / regressions vs")
    ap.add_argument("--pass-field", default="b_pass",
                    choices=["a_pass", "b_pass"],
                    help="Which pass to analyze (default b_pass = with RAG)")
    ap.add_argument("--export", default=str(REPO / "benchmark" / "finetune_failures.jsonl"),
                    help="JSONL export of failures (id, bucket, code, error)")
    args = ap.parse_args()

    data = load(Path(args.results))
    fails = collect_failures(data, args.pass_field)
    total_tasks = sum(len(it["tasks"]) for it in data["iterations"])

    print(f"=== {args.results} ({args.pass_field}) ===")
    print(f"Failures: {len(fails)} / {total_tasks}")

    # Bucket histogram
    buckets = Counter(f["bucket"] for f in fails)
    print("\nFailure buckets:")
    for b, n in sorted(buckets.items(), key=lambda x: -x[1]):
        print(f"  {b:20s} {n:3d}")

    # Per-iter
    by_iter: dict[int, list] = defaultdict(list)
    for f in fails:
        by_iter[f["iter"]].append(f)
    print("\nPer-iteration:")
    for it in sorted(by_iter):
        print(f"  iter {it:2d}: {len(by_iter[it]):2d} fails — "
              f"{', '.join(f['id'] for f in by_iter[it])}")

    # Undefined variable name frequency — these are concrete missing builtins
    undef = common_undefineds(fails)
    if undef:
        print("\nMost common undefined names (= candidate missing builtins/aliases):")
        for name, n in undef.most_common(15):
            print(f"  {name:24s} {n}")

    # Optional comparison
    if args.compare:
        comp = load(Path(args.compare))
        comp_fails = {(f["iter"], f["id"]) for f in collect_failures(comp, args.pass_field)}
        new_fails = [f for f in fails if (f["iter"], f["id"]) not in comp_fails]
        new_passes = comp_fails - {(f["iter"], f["id"]) for f in fails}
        print(f"\nVs baseline {args.compare}:")
        print(f"  Newly failing (regression): {len(new_fails)}")
        for f in new_fails[:10]:
            print(f"    iter {f['iter']} {f['id']} ({f['bucket']})")
        print(f"  Newly passing (lift): {len(new_passes)}")

    # Export full failure data
    with open(args.export, "w") as f:
        for fail in fails:
            f.write(json.dumps(fail) + "\n")
    print(f"\nFull failure data exported to {args.export}")


if __name__ == "__main__":
    main()
