#!/usr/bin/env python3
"""Offline replay of an existing path_c result file through the judge.

Predicts how often the judge would have flagged a wrong-shape intermediate
(or a final step) without re-running the costly Sigil generation step.
This gives a quick estimate of the judge's expected-NO rate before paying
the wall time of a full harness re-run.

Usage:
  python benchmark/judge_replay.py tools/agent_harness/abc_v7_deepseek_nh2a_v2_30task.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sigil_step_judge import judge_step


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "tools/agent_harness/abc_v7_deepseek_nh2a_v2_30task.json"
    tasks_path = sys.argv[2] if len(sys.argv) > 2 else \
        "tools/agent_harness/agent_tasks.json"
    data = json.loads(Path(path).read_text())
    raw_tasks = {t["id"]: t for t in json.loads(Path(tasks_path).read_text())}

    n_tasks = len(data["tasks"])
    n_path_c_pass = sum(1 for t in data["tasks"] if t["C"]["ok"])
    n_path_c_fail = n_tasks - n_path_c_pass

    judge_no_count = 0
    judge_yes_count = 0
    judge_skip_count = 0  # empty stdout — already handled upstream
    flagged_failures = []  # task ids where judge disagreed with (intermediate ok && task failed)
    spurious_no = []  # task ids where judge said NO on a step from a passing task

    for t in data["tasks"]:
        c = t["C"]
        steps = c.get("step_results", [])
        if not steps:
            continue
        cur_input = raw_tasks.get(t["id"], {}).get("input", "")
        for idx, s in enumerate(steps):
            is_final = idx == len(steps) - 1
            stdout = s.get("stdout", "")
            desc = s.get("description", "")
            if is_final:
                # Final-step shape is checked against expected; we can still
                # report what the judge would say but treat it as informational.
                pass
            if not stdout.strip():
                judge_skip_count += 1
                cur_input = stdout
                continue
            v = judge_step(desc, stdout, cur_input)
            if v.ok:
                judge_yes_count += 1
            else:
                judge_no_count += 1
                # If task failed and step was non-final intermediate that the
                # harness recorded as ok=True, judge would have triggered a
                # retry that might have lifted the task.
                if not c["ok"] and not is_final and s.get("ok"):
                    flagged_failures.append((t["id"], idx, desc[:80], v.reason))
                # If task passed but judge said NO, that's a spurious retry
                # signal (would have wasted tokens).
                if c["ok"]:
                    spurious_no.append((t["id"], idx, desc[:80], v.reason,
                                        stdout[:120]))
            cur_input = stdout

    print(f"Replay: {path}")
    print(f"Tasks: {n_tasks} (C_pass={n_path_c_pass}, C_fail={n_path_c_fail})")
    print(f"Judge calls: YES={judge_yes_count}, NO={judge_no_count}, "
          f"skipped(empty)={judge_skip_count}")
    print()
    print(f"-- Judge-flagged intermediate steps from FAILED tasks ({len(flagged_failures)}) --")
    print("(These are candidate lifts: judge would have triggered retry that might have helped)")
    for tid, idx, desc, reason in flagged_failures:
        print(f"  {tid} step {idx}: {desc}")
        print(f"    reason: {reason}")
    print()
    print(f"-- Spurious NO on PASSING tasks ({len(spurious_no)}) --")
    print("(These would have caused unnecessary retries — false-positive cost)")
    for tid, idx, desc, reason, sample in spurious_no:
        print(f"  {tid} step {idx}: {desc}")
        print(f"    reason: {reason}")
        print(f"    sample: {sample!r}")


if __name__ == "__main__":
    main()
