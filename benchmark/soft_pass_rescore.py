#!/usr/bin/env python3
"""NH9: re-score harness result files under softer comparison.

Path A passes 26/30 partly because Sonnet's Python output is forgiving on
whitespace; the harness's `expected_shape` check is byte-exact. The local
Sigil ensemble's Path C 7/30 might be 8-10/30 by a defensible definition.

This script re-applies a graduated set of comparators to every (got,
expected) pair in a result file and reports the pass count under each.

Comparators (each strictly more permissive than the prior):
  exact      — byte-for-byte match (current harness behavior)
  trim       — strip leading/trailing whitespace at file level
  rstrip     — strip trailing whitespace from each line
  collapse   — collapse runs of internal whitespace within each line
  unordered  — sort lines and compare; ignores order when no sort was asked

We apply all comparators to every task, but the "fair" soft-pass for
each task depends on whether its expected output has a meaningful
order. The script reports per-task results so we can manually qualify
which tasks should use which comparator.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def cmp_exact(got: str, expected: str) -> bool:
    return got == expected


def cmp_trim(got: str, expected: str) -> bool:
    return got.strip() == expected.strip()


def cmp_rstrip(got: str, expected: str) -> bool:
    g = "\n".join(line.rstrip() for line in got.split("\n"))
    e = "\n".join(line.rstrip() for line in expected.split("\n"))
    return g.strip() == e.strip()


def cmp_collapse(got: str, expected: str) -> bool:
    import re
    def norm(s: str) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in s.split("\n")]
        return "\n".join(line for line in lines if line)
    return norm(got) == norm(expected)


def cmp_unordered(got: str, expected: str) -> bool:
    g = sorted(line.strip() for line in got.strip().split("\n") if line.strip())
    e = sorted(line.strip() for line in expected.strip().split("\n") if line.strip())
    return g == e


COMPARATORS = [
    ("exact",     cmp_exact),
    ("trim",      cmp_trim),
    ("rstrip",    cmp_rstrip),
    ("collapse",  cmp_collapse),
    ("unordered", cmp_unordered),
]

# Tasks whose semantics REQUIRE a specific order. For these, "unordered"
# is too permissive — a model that outputs the right values in the wrong
# order should still fail. Anything else can use unordered as the most
# permissive comparator.
ORDER_SENSITIVE = {
    # explicit "sort" / "top N" / "first" / "running" tasks
    "log_top_4xx_ip", "csv_top3_categories", "log_peak_error_hour",
    "passwd_top_shells", "wc_top_words", "find_files_by_size",
    "errors_by_category", "csv_filter_then_top", "log_count_by_hour",
    "extract_versions_sorted", "uniq_c_with_threshold",
    "extract_python_imports", "csv_lookup_join", "running_sum",
    "syslog_grep_unique_processes",
}


def get_pair(task: dict, path: str) -> tuple[str, str] | None:
    """Extract (got, expected) for a given path (A/B/C). Returns None if missing."""
    p = task.get(path, {}) or {}
    if "stdout" not in p:
        return None
    return p.get("stdout", ""), task.get("expected", "")


def rescore(result_path: Path, tasks_path: Path) -> None:
    data = json.loads(result_path.read_text())
    raw_tasks = {t["id"]: t for t in json.loads(tasks_path.read_text())}

    paths = ["A", "B", "C"] if all(p in data["tasks"][0] for p in ("A","B","C")) else ["A","B"]
    print(f"Re-scoring {result_path.name}")
    print(f"  paths: {paths}\n")

    summary = {p: {c[0]: 0 for c in COMPARATORS} for p in paths}
    summary_qualified = {p: 0 for p in paths}  # most-permissive-allowed comparator
    per_task: dict[str, dict] = {}

    for t in data["tasks"]:
        tid = t["id"]
        expected = raw_tasks.get(tid, {}).get("expected", "")
        if not expected:
            # Older format
            expected = t.get("expected", "")
        per_task[tid] = {"order_sensitive": tid in ORDER_SENSITIVE}
        for p in paths:
            entry = t.get(p, {}) or {}
            got = entry.get("stdout", "") if isinstance(entry, dict) else ""
            results = {}
            for cname, cfn in COMPARATORS:
                ok = cfn(got or "", expected or "")
                results[cname] = ok
                if ok:
                    summary[p][cname] += 1
            # Qualified: pick the most permissive comparator that's
            # appropriate for this task. Order-sensitive tasks can use
            # up to 'collapse'; others can use 'unordered'.
            allowed = "unordered" if not per_task[tid]["order_sensitive"] else "collapse"
            allowed_idx = next(i for i, c in enumerate(COMPARATORS) if c[0] == allowed)
            if any(results[c[0]] for c in COMPARATORS[:allowed_idx + 1]):
                summary_qualified[p] += 1
            per_task[tid][p] = results

    # Cumulative pass counts (each row = "passes under this comparator OR stricter")
    print(f"{'comparator':12s} {'  A':>6s} {'  B':>6s} {'  C':>6s}")
    print("-" * 38)
    for cname, _ in COMPARATORS:
        line = f"{cname:12s}"
        for p in paths:
            line += f"  {summary[p][cname]:>3d}/30"
        print(line)
    print("-" * 38)
    line = f"{'qualified':12s}"
    for p in paths:
        line += f"  {summary_qualified[p]:>3d}/30"
    print(line)
    print()

    # Tasks that flip from fail to pass under the qualified comparator
    print("Tasks that flip exact→qualified:")
    for tid, info in per_task.items():
        for p in paths:
            results = info.get(p, {})
            if not results:
                continue
            allowed = "unordered" if not info["order_sensitive"] else "collapse"
            allowed_idx = next(i for i, c in enumerate(COMPARATORS) if c[0] == allowed)
            qualified_pass = any(results[c[0]] for c in COMPARATORS[:allowed_idx + 1])
            if qualified_pass and not results.get("exact"):
                # Find the most-permissive comparator that succeeded
                first_pass = next(c[0] for c in COMPARATORS if results.get(c[0]))
                print(f"  [{p}] {tid:35s}  ({first_pass}, order_sensitive={info['order_sensitive']})")


def main():
    if len(sys.argv) < 2:
        # Default: rescore the latest A/B/C results
        files = [
            "tools/agent_harness/abc_v7_deepseek_nh2a_v2_30task.json",     # baseline
            "tools/agent_harness/abc_v7_deepseekV1_judge_30task.json",     # judge isolation
            "tools/agent_harness/abc_v7_judge_shapeann_v3_30task.json",    # NH8 v3
            "tools/agent_harness/abc_v7_judge_shapeann_OPUS_30task.json",  # NH16 Opus
        ]
    else:
        files = sys.argv[1:]
    tasks_path = Path("tools/agent_harness/agent_tasks.json")
    for f in files:
        rescore(Path(f), tasks_path)
        print()


if __name__ == "__main__":
    main()
