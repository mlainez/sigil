#!/usr/bin/env python3
"""Estimate lift from the step-judge against a specific result file.

Uses the same replay logic as judge_replay_all.py but asks a sharper
question: of the failed tasks, which ones COULD be recovered by the judge?

A failed task can only be recovered when:
  (a) the judge flags at least one intermediate step's output, AND
  (b) every intermediate step before the flagged one already passed
      (otherwise the upstream is already broken — judge retry won't help), AND
  (c) the flagged step is the FIRST broken intermediate
      (so retrying it could in principle unblock the rest).

We then apply a step-level retry conversion rate prior. Empirically, when
NH2 Tier A's validator-driven retries fired, conversion was ~15-25% per
retry.  We use a 25% optimistic, 15% conservative band.

Output: per-task verdict + an aggregate predicted lift band.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from sigil_step_judge import judge_step

HARNESS_DIR = REPO / "tools" / "agent_harness"


def load_tasks_index() -> dict:
    idx = {}
    for path in (HARNESS_DIR / "agent_tasks_8.json",
                 HARNESS_DIR / "agent_tasks.json"):
        if path.exists():
            for t in json.loads(path.read_text()):
                idx[t["id"]] = t
    return idx


def estimate(result_path: Path) -> None:
    raw_tasks = load_tasks_index()
    data = json.loads(result_path.read_text())
    tasks = data["tasks"]

    n_pass = sum(1 for t in tasks if t["C"]["ok"])
    n_fail = len(tasks) - n_pass

    # Categorize each failed task
    categories = {
        "no_steps": [],          # path_c didn't run pipeline (e.g. decompose error)
        "no_flag": [],           # judge said YES on every non-empty intermediate
        "flag_after_break": [],  # judge flagged a step AFTER an earlier broken step
        "flag_at_first_break": [],  # judge flagged the first broken step (lift candidate)
        "flag_only_final": [],   # only the final step failed (judge doesn't run on final)
        "all_empty": [],         # every step had empty stdout (caught by upstream retry)
    }
    lift_candidates = []
    ok_false_extension_candidates = []  # would lift if wiring extended

    for t in tasks:
        if t["C"]["ok"]:
            continue
        tid = t["id"]
        steps = t["C"].get("step_results", [])
        if not steps:
            categories["no_steps"].append(tid)
            continue

        # Walk forward; identify the first broken intermediate step.
        cur_input = raw_tasks.get(tid, {}).get("input", "")
        first_break_idx = None
        flag_at_first_break = None
        flag_idxs = []
        any_nonempty = False
        # Extended pool: judge would flag an ok=False intermediate with
        # non-empty stdout. Current path_c wiring doesn't run the judge
        # on these (it gates on result["ok"]) — counted separately.
        ok_false_flag_at_first_break = None
        for idx, s in enumerate(steps):
            is_final = idx == len(steps) - 1
            stdout = s.get("stdout", "")
            desc = s.get("description", "")
            step_ok_intermediate = s.get("ok") and stdout.strip()
            if stdout.strip():
                any_nonempty = True
            # Run the judge if there's a non-empty stdout to inspect
            judge_ok = True
            judge_reason = ""
            if stdout.strip():
                v = judge_step(desc, stdout, cur_input)
                judge_ok = v.ok
                judge_reason = v.reason
                if not v.ok:
                    flag_idxs.append((idx, judge_reason, is_final))
            # Track first broken intermediate (non-final, ok=False or empty)
            if first_break_idx is None and not is_final:
                if not step_ok_intermediate:
                    first_break_idx = idx
                    if (not judge_ok and stdout.strip()
                            and ok_false_flag_at_first_break is None):
                        ok_false_flag_at_first_break = judge_reason
                elif not judge_ok:
                    # judge identified a non-final step as semantically wrong
                    first_break_idx = idx
                    flag_at_first_break = judge_reason
            cur_input = stdout

        # Bucketing
        if not any_nonempty:
            categories["all_empty"].append(tid)
            continue
        non_final_flags = [f for f in flag_idxs if not f[2]]
        if first_break_idx is None:
            # No broken intermediate — the failure is in the final step
            if non_final_flags:
                # Shouldn't happen given the logic above, but be safe
                categories["no_flag"].append(tid)
            else:
                categories["flag_only_final"].append(tid)
            continue
        if not non_final_flags:
            # Has a broken step but judge said YES on intermediates — judge
            # missed it (or the break is from a non-judgeable empty step the
            # upstream retry couldn't fix).
            categories["no_flag"].append(tid)
            continue
        # Find the EARLIEST flagged non-final step
        earliest_flagged = min(non_final_flags, key=lambda f: f[0])[0]
        if earliest_flagged == first_break_idx and flag_at_first_break:
            categories["flag_at_first_break"].append(tid)
            lift_candidates.append((tid, earliest_flagged, flag_at_first_break))
        elif earliest_flagged > first_break_idx:
            # Earlier step is broken AND non-empty AND the judge flags it
            # with a hint — extending the wiring to retry ok=False intermediates
            # would pick this up.
            if ok_false_flag_at_first_break:
                ok_false_extension_candidates.append(
                    (tid, first_break_idx, ok_false_flag_at_first_break))
            categories["flag_after_break"].append(tid)
        else:
            if ok_false_flag_at_first_break:
                ok_false_extension_candidates.append(
                    (tid, first_break_idx, ok_false_flag_at_first_break))
            categories["no_flag"].append(tid)

    print(f"Result file: {result_path.name}")
    print(f"  Total: {len(tasks)} tasks  (pass={n_pass}, fail={n_fail})")
    print()
    print("Failure categorization:")
    print(f"  Lift candidates  (judge flagged the FIRST broken step): {len(categories['flag_at_first_break'])}")
    print(f"  Final-step only  (judge can't help, final shape check):  {len(categories['flag_only_final'])}")
    print(f"  Already broken   (judge flagged AFTER an earlier break): {len(categories['flag_after_break'])}")
    print(f"  Empty pipeline   (every step empty, upstream retry job): {len(categories['all_empty'])}")
    print(f"  Judge missed     (had broken step, judge said YES):      {len(categories['no_flag'])}")
    print(f"  No pipeline      (decompose error):                      {len(categories['no_steps'])}")
    print()

    print(f"-- Current-wiring lift candidates ({len(lift_candidates)}) --")
    for tid, idx, reason in lift_candidates:
        print(f"  {tid} step {idx}: {reason[:90]}")
    print()

    print(f"-- Wiring-extension candidates ({len(ok_false_extension_candidates)}) --")
    print("  (Judge would flag an ok=False intermediate with non-empty stdout;")
    print("   current path_c wiring skips these — extending wiring picks them up)")
    for tid, idx, reason in ok_false_extension_candidates:
        print(f"  {tid} step {idx}: {reason[:90]}")
    print()

    n_cand = len(lift_candidates)
    n_ext = len(ok_false_extension_candidates)
    n_total_cand = n_cand + n_ext
    # Conversion model: judge retry triggers a fresh code-gen with a hint.
    # Empirically, validator-driven retries convert at ~15-25% (NH2 Tier A
    # showed 1/5 lift = 20%; NH2 Tier B is acting on richer signal — the
    # hint is more semantically targeted — so 25% upper, 15% lower band).
    # Plus a downstream factor: even if step-N retry succeeds, the next
    # step has to also work. We estimate that ~70% of these tasks have
    # only one broken step (single-fault tasks), reducing realized lift
    # by ~0.7.
    p_step = (0.15, 0.25)
    p_downstream = 0.70

    # Current wiring (judge runs only on ok=True intermediates)
    lo = n_cand * p_step[0] * p_downstream
    hi = n_cand * p_step[1] * p_downstream
    # With wiring extension to ok=False intermediates that have non-empty
    # stdout. These often had model output but a runtime error (still useful
    # to retry). Conversion may be lower since the underlying program had
    # an error, so we apply a 0.7 derating.
    p_ext_derate = 0.7
    lo_ext = n_ext * p_step[0] * p_downstream * p_ext_derate
    hi_ext = n_ext * p_step[1] * p_downstream * p_ext_derate
    total_lo = lo + lo_ext
    total_hi = hi + hi_ext

    print(f"Lift estimate:")
    print(f"  Per-retry conversion prior:       {p_step[0]:.0%}–{p_step[1]:.0%}  "
          f"(from NH2 Tier A validator-driven retries)")
    print(f"  Downstream factor (rest works):   {p_downstream:.0%}")
    print(f"  Extension derating (ok=False):    {p_ext_derate:.0%}")
    print()
    print(f"  Current wiring   ({n_cand} cands):  +{lo:.1f} to +{hi:.1f} tasks")
    print(f"  + extension      ({n_ext} cands):  +{lo_ext:.1f} to +{hi_ext:.1f} tasks")
    print(f"  TOTAL projected lift:                    +{total_lo:.1f} to +{total_hi:.1f} tasks")
    print()
    print(f"  Projected pass: {n_pass + total_lo:.1f}/{len(tasks)} to {n_pass + total_hi:.1f}/{len(tasks)}  "
          f"(baseline {n_pass}/{len(tasks)})")


def main():
    paths = sys.argv[1:] if len(sys.argv) > 1 else [
        "tools/agent_harness/abc_v7_deepseek_nh2a_v2_30task.json"
    ]
    for p in paths:
        estimate(Path(p))
        print()


if __name__ == "__main__":
    main()
