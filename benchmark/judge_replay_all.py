#!/usr/bin/env python3
"""Replay the step-judge against the full harness result history.

For each abc_*.json result file in tools/agent_harness/, walk every
intermediate step's recorded stdout through the judge and compute:
  - Judge NO rate per file
  - True positives: judge said NO on a step from a TASK that ultimately failed
  - False positives: judge said NO on a step from a TASK that ultimately passed
  - Coverage: fraction of failed tasks where the judge would have flagged at
    least one intermediate step

Outputs a per-file table + a unique flagged-failure list (deduplicated by
task_id + step description) for inspection.
"""
from __future__ import annotations

import json
import sys
import glob
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from sigil_step_judge import judge_step

HARNESS_DIR = REPO / "tools" / "agent_harness"
TASKS_FILE = HARNESS_DIR / "agent_tasks.json"
TASKS_8_FILE = HARNESS_DIR / "agent_tasks_8.json"


def load_tasks_index() -> dict:
    """Build a map task_id -> task dict from both task files."""
    idx = {}
    for path in (TASKS_8_FILE, TASKS_FILE):
        if not path.exists():
            continue
        for t in json.loads(path.read_text()):
            idx[t["id"]] = t  # later (TASKS_FILE) wins for shared ids
    return idx


def replay_file(path: Path, raw_tasks: dict) -> dict:
    data = json.loads(path.read_text())
    tasks = data.get("tasks", [])

    judge_yes = judge_no = judge_skip = 0
    no_on_failed_task = 0       # judge NO from a task that failed -> potential lift
    no_on_passed_task = 0       # judge NO from a task that passed -> spurious
    failed_tasks_with_no = set()
    failed_tasks_total = set()
    passed_tasks_total = set()
    flagged = []  # (task_id, step_idx, desc, reason, sample, task_passed)

    for t in tasks:
        tid = t["id"]
        c = t.get("C", {})
        steps = c.get("step_results", [])
        if not steps:
            continue
        if c.get("ok"):
            passed_tasks_total.add(tid)
        else:
            failed_tasks_total.add(tid)
        cur_input = raw_tasks.get(tid, {}).get("input", "")
        for idx, s in enumerate(steps):
            stdout = s.get("stdout", "")
            desc = s.get("description", "")
            if not stdout.strip():
                judge_skip += 1
                cur_input = stdout
                continue
            v = judge_step(desc, stdout, cur_input)
            if v.ok:
                judge_yes += 1
            else:
                judge_no += 1
                if c.get("ok"):
                    no_on_passed_task += 1
                else:
                    no_on_failed_task += 1
                    failed_tasks_with_no.add(tid)
                flagged.append((tid, idx, desc, v.reason, stdout[:120],
                                bool(c.get("ok"))))
            cur_input = stdout

    return {
        "file": path.name,
        "n_tasks": len(tasks),
        "n_passed": len(passed_tasks_total),
        "n_failed": len(failed_tasks_total),
        "judge_yes": judge_yes,
        "judge_no": judge_no,
        "judge_skip": judge_skip,
        "no_on_failed_task": no_on_failed_task,
        "no_on_passed_task": no_on_passed_task,
        "failed_with_no_count": len(failed_tasks_with_no),
        "failed_with_no": failed_tasks_with_no,
        "flagged": flagged,
    }


def main():
    raw = load_tasks_index()
    files = sorted(HARNESS_DIR.glob("abc_*.json"))
    print(f"Replaying {len(files)} files against the judge\n")
    print(f"{'file':50s}  {'n':>3s} {'pass':>4s} {'fail':>4s} "
          f"{'YES':>4s} {'NO':>4s} {'NO/F':>5s} {'FP':>3s} {'covF':>5s}")
    print("-" * 100)

    all_flagged = []
    sum_no = sum_no_pass = sum_failed = sum_failed_with_no = 0

    for f in files:
        r = replay_file(f, raw)
        cov_pct = (100.0 * r["failed_with_no_count"] / r["n_failed"]
                   if r["n_failed"] else 0)
        print(f"{r['file']:50s}  {r['n_tasks']:>3d} {r['n_passed']:>4d} "
              f"{r['n_failed']:>4d} {r['judge_yes']:>4d} {r['judge_no']:>4d} "
              f"{r['no_on_failed_task']:>5d} "
              f"{r['no_on_passed_task']:>3d} {cov_pct:>4.0f}%")
        all_flagged.extend(r["flagged"])
        sum_no += r["judge_no"]
        sum_no_pass += r["no_on_passed_task"]
        sum_failed += r["n_failed"]
        sum_failed_with_no += r["failed_with_no_count"]

    print("-" * 100)
    print(f"\nGlobal: {sum_no} NO verdicts, {sum_no_pass} on passing tasks (FP), "
          f"{sum_failed_with_no}/{sum_failed} failed tasks flagged "
          f"({100*sum_failed_with_no/sum_failed if sum_failed else 0:.0f}% coverage of failures).")
    fp_rate = (100.0 * sum_no_pass / sum_no) if sum_no else 0
    print(f"False-positive rate: {fp_rate:.1f}% of all NO verdicts came from passing tasks.")

    # Deduplicate flagged failures by (tid, desc[:60])
    print("\n--- Unique flagged steps from FAILED tasks (deduped by tid+desc) ---")
    seen = set()
    unique = []
    for tid, idx, desc, reason, sample, passed in all_flagged:
        if passed:
            continue
        key = (tid, desc[:60])
        if key in seen:
            continue
        seen.add(key)
        unique.append((tid, idx, desc, reason, sample))
    for tid, idx, desc, reason, sample in unique:
        print(f"  [{tid}] step {idx}: {desc[:70]}")
        print(f"    reason: {reason[:120]}")
        print(f"    output: {sample!r}")
    print(f"\n  ({len(unique)} unique flagged failure-step patterns across all files)")

    # Spurious NOs (from passing tasks) — full list for FP review
    print("\n--- All FP cases: judge NO on PASSING tasks ---")
    fps = [(tid, idx, desc, reason, sample) for tid, idx, desc, reason, sample, passed
           in all_flagged if passed]
    if not fps:
        print("  (none — judge has 0% FP rate across all replayed history)")
    else:
        for tid, idx, desc, reason, sample in fps:
            print(f"  [{tid}] step {idx}: {desc[:70]}")
            print(f"    reason: {reason[:120]}")
            print(f"    output: {sample!r}")


if __name__ == "__main__":
    main()
