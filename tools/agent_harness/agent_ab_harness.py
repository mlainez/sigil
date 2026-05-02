#!/usr/bin/env python3
"""A/B comparison harness for the Sigil agentic harness.

For each agentic task, runs two paths:

  Path A — CLOUD-ONLY: Sonnet writes a Python program inline, executes it,
           returns stdout. Sonnet bears the full code-generation token cost.

  Path B — HYBRID: Sonnet receives the same task spec, calls the
           sigil_run_task MCP tool (simulated via direct Python call to the
           local Sigil ensemble), reads back the result, returns. Sonnet
           bears only orchestration tokens, NOT code-generation tokens.

We measure cloud tokens, $ cost, accuracy, and wallclock for each path.
The headline result is whether Path B saves cloud tokens with acceptable
accuracy on tooling-shape work.

Run:
  python3 tools/agent_harness/agent_ab_harness.py \\
      --tasks tools/agent_harness/agent_tasks.json \\
      --out  tools/agent_harness/ab_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools" / "agent_harness"))
from sigil_mcp_server import generate_and_run

# Anthropic Sonnet pricing as of 2026-04 (per million tokens)
SONNET_INPUT_PER_M = 3.0
SONNET_OUTPUT_PER_M = 15.0


def claude_call(prompt: str, system: str = "") -> dict:
    """Call Sonnet via the local `claude` CLI, return result + token usage.
    Returns: {text, prompt_tokens, completion_tokens, cost_usd, ok, raw_err}"""
    cmd = ["claude", "--print", "--output-format", "json",
           "--model", "claude-sonnet-4-6"]
    full_prompt = (system + "\n\n" + prompt) if system else prompt
    cmd += ["-p", full_prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=180, cwd="/tmp")
        if not r.stdout.strip():
            return {"text": "", "prompt_tokens": 0, "completion_tokens": 0,
                    "cost_usd": 0.0, "ok": False, "raw_err": r.stderr[:200]}
        data = json.loads(r.stdout)
        text = data.get("result") or ""
        usage = data.get("usage", {})
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        return {
            "text": text,
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "cost_usd": in_tok * SONNET_INPUT_PER_M / 1e6 + out_tok * SONNET_OUTPUT_PER_M / 1e6,
            "ok": True,
            "raw_err": "",
        }
    except Exception as e:
        return {"text": "", "prompt_tokens": 0, "completion_tokens": 0,
                "cost_usd": 0.0, "ok": False, "raw_err": str(e)[:200]}


# ============================================================================
# Path A: cloud-only (Sonnet writes Python)
# ============================================================================

PYTHON_SYSTEM = (
    "You write Python 3 programs. Use sys.argv[1] for input. Output ONLY "
    "raw Python code, no markdown, no prose. Always include `import sys` "
    "if you use sys.argv. Use sys.stdout.write(...) for output (no extra "
    "trailing newline unless requested)."
)
PYTHON_PROMPT = (
    "Write a Python 3 program that does exactly this:\n\n"
    "TASK: {goal}\n\n"
    "When called with the input string as sys.argv[1], output must be EXACTLY:\n"
    "{expected!r}\n\n"
    "Output ONLY the raw Python code."
)


def path_a_cloud_only(task: dict) -> dict:
    """Sonnet writes Python inline, we execute, compare."""
    t0 = time.time()
    prompt = PYTHON_PROMPT.format(goal=task["goal"], expected=task["expected"])
    r = claude_call(prompt, PYTHON_SYSTEM)
    if not r["ok"]:
        return {"path": "A_cloud_only", "ok": False, "stdout": "",
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                "wall_seconds": round(time.time() - t0, 2),
                "error": r.get("raw_err", "")}

    # Strip fences if any
    code = r["text"].strip()
    for fence in ["```python", "```py", "```"]:
        if code.startswith(fence):
            code = code[len(fence):].lstrip(); break
    if code.endswith("```"):
        code = code[:-3].rstrip()

    # Execute
    import tempfile
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    f.write(code); f.close()
    try:
        run = subprocess.run(["python3", f.name, task["input"]],
                             capture_output=True, text=True, timeout=10)
        stdout = run.stdout
        ok = run.returncode == 0 and stdout == task["expected"]
    except subprocess.TimeoutExpired:
        stdout = ""
        ok = False
    finally:
        os.unlink(f.name)

    return {
        "path": "A_cloud_only",
        "ok": ok,
        "stdout": stdout,
        "code": code,
        "tokens_in": r["prompt_tokens"],
        "tokens_out": r["completion_tokens"],
        "cost_usd": round(r["cost_usd"], 6),
        "wall_seconds": round(time.time() - t0, 2),
    }


# ============================================================================
# Path B: hybrid (Sonnet plans + delegates to local Sigil via MCP)
# ============================================================================

# In the real MCP-integrated flow, Sonnet decides to call sigil_run_task. Here
# we simulate that flow: we ask Sonnet to ONLY produce the delegation
# arguments (a small JSON), then we directly call the local generation
# (mimicking what the MCP server would return), then Sonnet sees the result
# and reports back. This gives us realistic token accounting WITHOUT requiring
# Sonnet to actually be MCP-connected during the test.

DELEGATE_SYSTEM = (
    "You decide whether to delegate a tooling task to the local Sigil ensemble. "
    "You have access to one tool: sigil_run_task(description, input, expected_shape). "
    "For deterministic data-processing tasks (parsing, filtering, counting, "
    "regex extraction, format conversion, aggregation), DELEGATE — output "
    "a JSON object with {\"description\": ..., \"input\": ..., \"expected_shape\": ...} "
    "and nothing else. The description should be a one-sentence task spec the "
    "local model can follow; you may copy or paraphrase the user's goal. "
    "Output ONLY the JSON object, no markdown."
)
DELEGATE_PROMPT = (
    "Task: {goal}\n\n"
    "Sample input string (will be passed as the program's CLI arg 0):\n"
    "{input!r}\n\n"
    "Expected output (exact stdout the program should produce):\n"
    "{expected!r}\n\n"
    "Decide: delegate to sigil_run_task. Output the JSON args."
)

REPORT_SYSTEM = (
    "You ran a sigil_run_task tool call. Report back to the user with the "
    "result. If the tool returned ok=true, report the stdout. If ok=false, "
    "say so briefly. Keep your answer to ONE LINE."
)
REPORT_PROMPT = (
    "Tool result:\n{result!r}\n\n"
    "Original user task: {goal}\n\n"
    "One-line summary."
)


def path_b_hybrid(task: dict) -> dict:
    """Sonnet plans + delegates to local Sigil via simulated MCP call."""
    t0 = time.time()
    total_in = total_out = total_cost = 0.0
    stage_records = []

    # 1. Sonnet decides delegation args
    delegate_prompt = DELEGATE_PROMPT.format(
        goal=task["goal"], input=task["input"], expected=task["expected"])
    r1 = claude_call(delegate_prompt, DELEGATE_SYSTEM)
    if not r1["ok"]:
        return {"path": "B_hybrid", "ok": False, "stdout": "",
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                "wall_seconds": round(time.time() - t0, 2),
                "error": r1.get("raw_err", "")}
    total_in += r1["prompt_tokens"]; total_out += r1["completion_tokens"]
    total_cost += r1["cost_usd"]
    stage_records.append({"stage": "decide", "in": r1["prompt_tokens"],
                          "out": r1["completion_tokens"]})

    # Parse the delegation args (Sonnet should return JSON)
    text = r1["text"].strip()
    for fence in ["```json", "```"]:
        if text.startswith(fence):
            text = text[len(fence):].lstrip(); break
    if text.endswith("```"):
        text = text[:-3].rstrip()
    try:
        args = json.loads(text)
        desc = args.get("description", task["goal"])
        local_input = args.get("input", task["input"])
        expected_shape = args.get("expected_shape", task["expected"])
    except json.JSONDecodeError:
        # Sonnet didn't produce JSON; fall back to original task
        desc, local_input, expected_shape = task["goal"], task["input"], task["expected"]

    # 2. Local Sigil ensemble generates + runs (zero cloud cost)
    sigil_result = generate_and_run(desc, local_input, expected_shape)
    sigil_summary = {
        "ok": sigil_result["ok"],
        "stdout": sigil_result["stdout"][:500],
        "attempts": sigil_result["attempts"],
        "model": sigil_result["model_used"],
    }

    # 3. Sonnet reports back to user (small final summary)
    report_prompt = REPORT_PROMPT.format(
        result=json.dumps(sigil_summary, ensure_ascii=False),
        goal=task["goal"])
    r3 = claude_call(report_prompt, REPORT_SYSTEM)
    total_in += r3["prompt_tokens"]; total_out += r3["completion_tokens"]
    total_cost += r3["cost_usd"]
    stage_records.append({"stage": "report", "in": r3["prompt_tokens"],
                          "out": r3["completion_tokens"]})

    return {
        "path": "B_hybrid",
        "ok": sigil_result["ok"] and sigil_result["stdout"] == task["expected"],
        "stdout": sigil_result["stdout"],
        "code": sigil_result["code"],
        "tokens_in": total_in,
        "tokens_out": int(total_out),
        "cost_usd": round(total_cost, 6),
        "wall_seconds": round(time.time() - t0, 2),
        "sigil_attempts": sigil_result["attempts"],
        "sigil_model": sigil_result["model_used"],
        "stages": stage_records,
    }


# ============================================================================
# Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(REPO / "tools" / "agent_harness" / "agent_tasks.json"))
    ap.add_argument("--out", default=str(REPO / "tools" / "agent_harness" / "ab_results.json"))
    ap.add_argument("--skip-cloud", action="store_true",
                    help="Skip cloud calls (Path A and Sonnet stages of Path B); "
                         "only run the local Sigil portion. For dry runs.")
    args = ap.parse_args()

    tasks = json.loads(Path(args.tasks).read_text())
    print(f"Loaded {len(tasks)} agentic tasks\n")

    rows = []
    for i, t in enumerate(tasks, 1):
        print(f"[{i:2}/{len(tasks)}] {t['id']}")
        if args.skip_cloud:
            a = {"path": "A_cloud_only", "ok": False, "tokens_in": 0,
                 "tokens_out": 0, "cost_usd": 0.0, "wall_seconds": 0,
                 "skipped": True}
            b_local = generate_and_run(t["goal"], t["input"], t["expected"])
            b = {"path": "B_hybrid", "ok": b_local["ok"] and b_local["stdout"] == t["expected"],
                 "stdout": b_local["stdout"], "code": b_local["code"],
                 "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                 "wall_seconds": b_local["wall_seconds"],
                 "sigil_attempts": b_local["attempts"], "sigil_model": b_local["model_used"]}
        else:
            a = path_a_cloud_only(t)
            b = path_b_hybrid(t)
        print(f"   A cloud:  {'P' if a['ok'] else 'F'} (in={a['tokens_in']} out={a['tokens_out']} ${a['cost_usd']:.4f}, {a['wall_seconds']:.1f}s)")
        print(f"   B hybrid: {'P' if b['ok'] else 'F'} (in={b['tokens_in']} out={b['tokens_out']} ${b['cost_usd']:.4f}, {b['wall_seconds']:.1f}s)")
        rows.append({"id": t["id"], "shape": t["shape"], "A": a, "B": b})

    # Aggregate
    total_a_in = sum(r["A"]["tokens_in"] for r in rows)
    total_a_out = sum(r["A"]["tokens_out"] for r in rows)
    total_a_cost = sum(r["A"]["cost_usd"] for r in rows)
    total_a_pass = sum(1 for r in rows if r["A"]["ok"])
    total_b_in = sum(r["B"]["tokens_in"] for r in rows)
    total_b_out = sum(r["B"]["tokens_out"] for r in rows)
    total_b_cost = sum(r["B"]["cost_usd"] for r in rows)
    total_b_pass = sum(1 for r in rows if r["B"]["ok"])

    aggregate = {
        "n_tasks": len(rows),
        "A_cloud_only": {
            "pass": total_a_pass, "input_tokens": total_a_in,
            "output_tokens": total_a_out, "cost_usd": round(total_a_cost, 4),
        },
        "B_hybrid": {
            "pass": total_b_pass, "input_tokens": total_b_in,
            "output_tokens": total_b_out, "cost_usd": round(total_b_cost, 4),
        },
        "savings": {
            "input_tokens_saved_pct": round(100 * (total_a_in - total_b_in) / max(total_a_in, 1), 1),
            "output_tokens_saved_pct": round(100 * (total_a_out - total_b_out) / max(total_a_out, 1), 1),
            "cost_saved_pct": round(100 * (total_a_cost - total_b_cost) / max(total_a_cost, 1e-9), 1),
            "accuracy_delta_pp": total_b_pass - total_a_pass,
        },
    }

    print()
    print(f"=== AGGREGATE ({len(rows)} tasks) ===")
    print(f"  Cloud-only (A): pass {total_a_pass}/{len(rows)}  in={total_a_in:>6} out={total_a_out:>5} ${total_a_cost:.4f}")
    print(f"  Hybrid     (B): pass {total_b_pass}/{len(rows)}  in={total_b_in:>6} out={total_b_out:>5} ${total_b_cost:.4f}")
    print(f"  Savings:        input −{aggregate['savings']['input_tokens_saved_pct']}%  output −{aggregate['savings']['output_tokens_saved_pct']}%  cost −{aggregate['savings']['cost_saved_pct']}%  accuracy {aggregate['savings']['accuracy_delta_pp']:+d} pp")

    out_data = {"aggregate": aggregate, "tasks": rows}
    Path(args.out).write_text(json.dumps(out_data, indent=2, ensure_ascii=False))
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
