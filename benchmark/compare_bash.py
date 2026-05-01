#!/usr/bin/env python3
"""Compare Sigil vs Bash on tier-2 tasks.

For each TIER_2 task in feedback_loop.py, ask Opus to write a minimal bash
pipeline that produces the expected output. Validate by running bash with the
task args. Measure tokens via tiktoken cl100k_base (generated code only).

Output: wins/ties/losses vs Sigil, and combined overall ratio.

Uses existing tier2_results.json for Sigil numbers (no Sigil re-generation).
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import tiktoken

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feedback_loop import TIER_2

REPO_ROOT = Path(__file__).resolve().parent.parent
ENC = tiktoken.get_encoding("cl100k_base")

PROMPT = """Write a minimal bash script that does exactly this:

TASK: {desc}

Example: when called with args {args}, output MUST be exactly:
{expected!r}

Rules — strictly minimize tokens:
1. Use bash pipelines. Prefer awk/sed/sort/tr/uniq one-liners.
2. CLI args: "$1" is the first arg, "$2" is the second.
3. No shebang. No comments. No error handling beyond what the task needs.
4. Output is on stdout. Use echo/printf/awk as appropriate.
5. Exit cleanly on success.

Output ONLY the raw bash code. No ``` fences. No explanation."""


def count(s: str) -> int:
    return len(ENC.encode(s))


def gen_bash(task: dict) -> str:
    prompt = PROMPT.format(desc=task["desc"], args=task["args"], expected=task["expected"])
    try:
        r = subprocess.run(
            ["claude", "--print", "--model", "claude-opus-4-7", "-p", prompt],
            capture_output=True, text=True, timeout=90, cwd="/tmp",
        )
        code = r.stdout.strip()
        for fence in ["```bash", "```sh", "```shell", "```"]:
            if code.startswith(fence):
                code = code[len(fence):].strip()
                break
        if code.endswith("```"):
            code = code[:-3].strip()
        return code
    except Exception:
        return ""


def run_bash(code: str, args: list) -> tuple[bool, str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run(["bash", f.name] + args,
                             capture_output=True, text=True, timeout=10)
            return r.returncode == 0, r.stdout, r.stderr
        finally:
            os.unlink(f.name)


def main():
    # Load Sigil results
    sigil_path = REPO_ROOT / "benchmark" / "tier2_results.json"
    sigil_results = {r["id"]: r for r in json.loads(sigil_path.read_text())["results"] if r.get("status") == "ok"}

    print(f"=== TIER 2 Sigil vs Bash (vs Python baseline) ===\n")
    print(f"{'Task':<22} {'Sigil':>6} {'Bash':>6} {'Python':>7}  {'S/B':>5} {'S/Py':>5}")
    print("-" * 70)

    sigil_tot = 0
    bash_tot = 0
    py_tot = 0
    valid = 0
    results = []

    for task in TIER_2:
        sigil_r = sigil_results.get(task["id"])
        if not sigil_r:
            print(f"{task['id']:<22} no sigil result, skip")
            continue

        # Try bash up to 3 times
        for attempt in range(3):
            bash_code = gen_bash(task)
            if not bash_code:
                continue
            ok, out, err = run_bash(bash_code, task["args"])
            if ok and out == task["expected"]:
                break
        else:
            print(f"{task['id']:<22} {sigil_r['sigil_tokens']:>6} {'FAIL':>6} {sigil_r['python_tokens']:>7}  -")
            results.append({"id": task["id"], "sigil": sigil_r["sigil_tokens"],
                          "bash": None, "python": sigil_r["python_tokens"]})
            continue

        bt = count(bash_code)
        st = sigil_r["sigil_tokens"]
        pt = sigil_r["python_tokens"]
        sigil_tot += st; bash_tot += bt; py_tot += pt; valid += 1
        ratio_sb = st / bt if bt else 0
        ratio_sp = st / pt if pt else 0
        print(f"{task['id']:<22} {st:>6} {bt:>6} {pt:>7}  {ratio_sb:>4.2f}x {ratio_sp:>4.2f}x")
        results.append({"id": task["id"], "sigil": st, "bash": bt, "python": pt, "bash_code": bash_code})

    print("-" * 70)
    print(f"{'TOTAL':<22} {sigil_tot:>6} {bash_tot:>6} {py_tot:>7}")
    if bash_tot:
        print(f"\nSigil / Bash   : {sigil_tot/bash_tot:.2f}x ({'Sigil wins' if sigil_tot < bash_tot else 'Bash wins'})")
        print(f"Sigil / Python : {sigil_tot/py_tot:.2f}x")
        print(f"Bash  / Python : {bash_tot/py_tot:.2f}x")
        print(f"\nValid comparisons: {valid}/{len(TIER_2)}")

    out_path = REPO_ROOT / "benchmark" / "tier2_bash_comparison.json"
    out_path.write_text(json.dumps({
        "results": results,
        "totals": {"sigil": sigil_tot, "bash": bash_tot, "python": py_tot},
    }, indent=2))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
