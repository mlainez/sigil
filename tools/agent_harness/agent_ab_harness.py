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
sys.path.insert(0, str(REPO / "benchmark"))
from sigil_mcp_server import generate_and_run
from sigil_step_judge import judge_step

# Anthropic per-million-token pricing as of 2026-04. Adjust here if you
# change models. The cost line in the aggregate uses these rates.
MODEL_PRICING = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7":   (15.0, 75.0),
}
SONNET_INPUT_PER_M = 3.0   # legacy aliases retained for compatibility
SONNET_OUTPUT_PER_M = 15.0

# Module-level default; override via --cloud-model on the CLI.
CLOUD_MODEL = "claude-sonnet-4-6"


def claude_call(prompt: str, system: str = "") -> dict:
    """Call the configured cloud model via the local `claude` CLI, return
    result + token usage.
    Returns: {text, prompt_tokens, completion_tokens, cost_usd, ok, raw_err}"""
    in_per_m, out_per_m = MODEL_PRICING.get(
        CLOUD_MODEL, (SONNET_INPUT_PER_M, SONNET_OUTPUT_PER_M))
    cmd = ["claude", "--print", "--output-format", "json",
           "--model", CLOUD_MODEL]
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
            "cost_usd": in_tok * in_per_m / 1e6 + out_tok * out_per_m / 1e6,
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
# NH6: Sonnet-as-step-executor — drop-in alternative to local Sigil for path_c
# ============================================================================
# This is a *diagnostic* path, not a deployment path. It tests whether the
# multi-step ceiling is the local executor's capability (Path C currently
# 7/30) or the orchestration recipe itself. Sonnet decomposes as today,
# but each step's executor is Sonnet writing inline Python instead of
# the local Sigil model.
#
#   - If Path C with Sonnet executor scores ~26/30 (Path A's level),
#     the local executor is the bottleneck. Every fine-tuning move is
#     justified.
#   - If it scores significantly below Path A (~10-15/30), the chained
#     decomposition itself adds friction even with a strong executor —
#     the orchestration recipe is the limiting factor regardless of
#     who executes.
#
# The Sonnet stage costs cloud tokens per step, so this is a measurement
# tool only.

STEP_PYTHON_SYSTEM = (
    "You are a step-executor in a chained data-processing pipeline. For "
    "the given step description, write a Python 3 program that reads "
    "sys.argv[1] (the previous step's stdout, or the user-supplied input "
    "for the first step) and emits the result of THIS STEP ONLY to stdout. "
    "Do NOT try to solve the whole task — only the step you are given. "
    "Output ONLY raw Python code, no markdown, no prose."
)
STEP_PYTHON_PROMPT = (
    "Step description: {desc}\n\n"
    "When called with the input string as sys.argv[1], your program's "
    "stdout will be passed to the next step (or returned to the user "
    "if this is the final step). Use sys.stdout.write(...) for output."
)


def sonnet_execute_step(desc: str, cur_input: str, expected_shape: str = "") -> dict:
    """Drop-in alternative to generate_and_run (NH6 diagnostic).

    Same dict shape as generate_and_run: {ok, stdout, stderr, code,
    attempts, model_used, fallback_used, wall_seconds}. expected_shape is
    accepted for signature compatibility but ignored (Sonnet doesn't get
    a retry loop here — one-shot per step).
    """
    t0 = time.time()
    prompt = STEP_PYTHON_PROMPT.format(desc=desc)
    r = claude_call(prompt, STEP_PYTHON_SYSTEM)
    if not r["ok"]:
        return {"ok": False, "stdout": "", "stderr": r.get("raw_err", ""),
                "code": "", "attempts": 1, "model_used": CLOUD_MODEL,
                "fallback_used": False,
                "wall_seconds": round(time.time() - t0, 2),
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    code = r["text"].strip()
    for fence in ["```python", "```py", "```"]:
        if code.startswith(fence):
            code = code[len(fence):].lstrip(); break
    if code.endswith("```"):
        code = code[:-3].rstrip()

    import tempfile
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    f.write(code); f.close()
    try:
        run = subprocess.run(
            ["python3", f.name, cur_input],
            capture_output=True, text=True, timeout=15,
        )
        stdout, stderr = run.stdout, run.stderr
        ok = (run.returncode == 0)
    except subprocess.TimeoutExpired:
        stdout, stderr, ok = "", "TIMEOUT", False
    finally:
        os.unlink(f.name)

    return {
        "ok": ok, "stdout": stdout, "stderr": stderr[:240], "code": code,
        "attempts": 1, "model_used": CLOUD_MODEL, "fallback_used": False,
        "wall_seconds": round(time.time() - t0, 2),
        "tokens_in": r["prompt_tokens"],
        "tokens_out": r["completion_tokens"],
        "cost_usd": round(r["cost_usd"], 6),
    }


# ============================================================================
# NH10: Local-model-Python executor — same chain harness, Python instead of Sigil
# ============================================================================
# Tests CONCLUSIONS.md C1 directly: would the same local model writing
# Python (its native pretraining distribution) close most of the
# 19-task gap NH6 identified between qwen-sigil-v7 and Sonnet?
#
# Same orchestration. Same chained pipeline. Only the per-step
# executor language target swapped: Python instead of Sigil.
# Generator: a base coder model (qwen2.5-coder:7b by default), no
# Sigil fine-tune. Output runs as a Python subprocess.

LOCAL_PYTHON_MODEL = "qwen2.5-coder:7b"   # set via --python-model

LOCAL_PYTHON_SYSTEM = (
    "You are a step-executor in a chained data-processing pipeline. "
    "For the given step description, write a Python 3 program that "
    "reads sys.argv[1] (the previous step's stdout, or the user-supplied "
    "input for the first step) and emits the result of THIS STEP ONLY "
    "to stdout. Do NOT try to solve the whole task — only the step you "
    "are given. Output ONLY raw Python code, no markdown, no prose. "
    "Always `import sys` if you use sys.argv. Use sys.stdout.write(...) "
    "for output (no extra trailing newline unless requested)."
)
LOCAL_PYTHON_PROMPT = (
    "Step description: {desc}\n\n"
    "When called with the input string as sys.argv[1], your program's "
    "stdout will be passed to the next step (or returned to the user "
    "if this is the final step). Write the Python."
)


def local_python_execute_step(desc: str, cur_input: str,
                              expected_shape: str = "") -> dict:
    """Local-model Python executor (NH10 — Python-as-control on Sigil's
    chained harness). Same dict shape as generate_and_run."""
    import urllib.request, urllib.error, tempfile
    t0 = time.time()
    body = json.dumps({
        "model": LOCAL_PYTHON_MODEL,
        "system": LOCAL_PYTHON_SYSTEM,
        "prompt": LOCAL_PYTHON_PROMPT.format(desc=desc),
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2048, "top_p": 0.9},
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        raw = data.get("response", "")
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        return {"ok": False, "stdout": "", "stderr": f"ollama error: {e}",
                "code": "", "attempts": 1, "model_used": LOCAL_PYTHON_MODEL,
                "fallback_used": False, "wall_seconds": round(time.time()-t0, 2),
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    code = raw.strip()
    for fence in ("```python", "```py", "```"):
        if code.startswith(fence):
            code = code[len(fence):].lstrip(); break
    if code.endswith("```"):
        code = code[:-3].rstrip()
    # Strip a bare language-name first line if the model emitted one
    first, _, rest = code.partition("\n")
    if first.strip().lower() in {"python", "py"}:
        code = rest.lstrip()

    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    f.write(code); f.close()
    try:
        run = subprocess.run(["python3", f.name, cur_input],
                             capture_output=True, text=True, timeout=15)
        stdout, stderr = run.stdout, run.stderr
        ok = (run.returncode == 0)
    except subprocess.TimeoutExpired:
        stdout, stderr, ok = "", "TIMEOUT", False
    finally:
        os.unlink(f.name)

    return {
        "ok": ok, "stdout": stdout, "stderr": stderr[:240], "code": code,
        "attempts": 1, "model_used": LOCAL_PYTHON_MODEL,
        "fallback_used": False, "wall_seconds": round(time.time()-t0, 2),
        "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
    }


# Module-level executor selector. Defaults to local Sigil ensemble.
# --executor sonnet swaps in the cloud step-executor above for path_c.
# --executor python  swaps in the local-Python executor (NH10).
def _default_executor(desc, cur_input, expected_shape):
    return generate_and_run(desc, cur_input, expected_shape)
STEP_EXECUTOR = _default_executor


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
# Path C: chained hybrid (Sonnet decomposes → multiple single-step Sigil calls)
# ============================================================================
#
# Premise (Phase 21 / 22.6): the local Sigil ensemble solves single-step
# Stream-C-shaped tasks at 29/30 but multi-step composition (one program
# does filter + aggregate + format + sort) at 1-2/8. The bottleneck is
# composition complexity within one program, not Sigil grammar fluency.
#
# Path C tests the architectural fix: ask Sonnet to DECOMPOSE the task
# into N single-step Sigil snippets, run each one, thread stdout → stdin
# between steps. Each step is then a Stream-C-shaped task.

CHAIN_DELEGATE_SYSTEM = (
    "You decide how to delegate a tooling task to the local Sigil ensemble. "
    "The local ensemble is excellent at SINGLE-STEP data transforms (parse, "
    "filter, count, sort, format) but struggles when one program has to do "
    "many steps in sequence. Decompose the task into 1-3 SINGLE-PURPOSE "
    "steps — use however many the task actually needs. Each step's input "
    "is the previous step's stdout (the first step's input is the "
    "user-supplied data). Output JSON of the form:\n"
    "  {\"steps\": [{\"description\": \"<one-sentence Sigil task>\", "
    "\"input_shape\": \"<concrete one-sentence description of what $0 looks "
    "like for this step: line separator, field shape>\"}, ...]}\n"
    "Each description should be one sentence, present tense, focused on a "
    "single transform. Examples of good steps: 'Skip the header and print "
    "category,amount comma-separated for each row', 'Sum the amount column "
    "by the first column key (the category), print KEY TOTAL each line', "
    "'Sort lines descending by the second whitespace-separated number, "
    "print top 3 formatted as KEY: $TOTAL'. Output ONLY the JSON, no markdown."
)
CHAIN_DELEGATE_PROMPT = (
    "Task: {goal}\n\n"
    "Sample input string (passed as $0 to the FIRST step):\n"
    "{input!r}\n\n"
    "Final expected output:\n"
    "{expected!r}\n\n"
    "Decompose into 1-3 single-purpose steps. Output the JSON."
)


def path_c_chained_hybrid(task: dict) -> dict:
    """Sonnet decomposes the task into a pipeline of single-step Sigil calls;
    we run them sequentially, threading stdout → next step's stdin.

    Single-step Stream-C is where the local ensemble lives at 29/30. Chained
    composition is the bet: each individual step is the shape the model
    handles well, and the orchestrator owns the cross-step plumbing.
    """
    t0 = time.time()
    total_in = total_out = total_cost = 0.0
    stage_records = []

    # 1. Sonnet decomposes
    decomp_prompt = CHAIN_DELEGATE_PROMPT.format(
        goal=task["goal"], input=task["input"], expected=task["expected"])
    r1 = claude_call(decomp_prompt, CHAIN_DELEGATE_SYSTEM)
    if not r1["ok"]:
        return {"path": "C_chained", "ok": False, "stdout": "",
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                "wall_seconds": round(time.time() - t0, 2),
                "error": r1.get("raw_err", "")}
    total_in += r1["prompt_tokens"]; total_out += r1["completion_tokens"]
    total_cost += r1["cost_usd"]
    stage_records.append({"stage": "decompose", "in": r1["prompt_tokens"],
                          "out": r1["completion_tokens"]})

    text = r1["text"].strip()
    for fence in ["```json", "```"]:
        if text.startswith(fence): text = text[len(fence):].lstrip(); break
    if text.endswith("```"): text = text[:-3].rstrip()
    try:
        plan = json.loads(text)
        steps = plan.get("steps", [])
        if not steps or not isinstance(steps, list):
            raise ValueError("no steps")
    except (json.JSONDecodeError, ValueError):
        # Fallback: collapse to a single-step delegation
        steps = [{"description": task["goal"]}]

    # 2. Run pipeline; thread stdout → stdin.
    # Move B (Tier 2.5, refined Phase 26): validate intermediate steps.
    # Empty stdout from a non-final step is almost always a pipeline bug —
    # retry up to 2 additional times before giving up. The prior version
    # also augmented the next step's description with a 200-char excerpt
    # of the prior step's output; that was reverted because (a) it
    # polluted the prompt for simple tasks and (b) it caused regressions
    # on tasks Sonnet's natural decomposition handled cleanly.
    cur_input = task["input"]
    step_results = []
    last_step_idx = len(steps) - 1
    final_stdout = ""
    final_ok = False
    for idx, step in enumerate(steps):
        is_final = idx == last_step_idx
        expected_shape = task["expected"] if is_final else ""
        raw_desc = step.get("description", "")
        # NH8: prepend Sonnet's input_shape annotation to the description.
        # The local 7B otherwise guesses $0's structure from the description's
        # verbs and frequently picks the wrong split delimiter (e.g. splits on
        # space when $0 is line-separated). Sonnet sees the actual sample input
        # at decompose-time and can predict the shape per step deterministically.
        input_shape = (step.get("input_shape") or "").strip()
        if input_shape:
            desc = f"INPUT SHAPE: {input_shape}\n\n{raw_desc}"
        else:
            desc = raw_desc
        result = STEP_EXECUTOR(desc, cur_input, expected_shape)
        intermediate_retry_attempts = 0
        # Intermediate-step empty-output retry: up to 2 extra attempts
        # if stdout is empty. Skip retry on the final step (its retries
        # are already handled via expected_shape inside generate_and_run).
        while (not is_final
               and intermediate_retry_attempts < 2
               and result["ok"]
               and not result["stdout"].strip()):
            intermediate_retry_attempts += 1
            retry_desc = (f"{desc}\n\nYour previous attempt produced no output; "
                          f"that's almost certainly a pipeline bug. Make sure "
                          f"to (split $0 \"\\n\") and emit (println ...) for "
                          f"each computed value.")
            result = STEP_EXECUTOR(retry_desc, cur_input, expected_shape)

        # NH2 Tier B: semantic step-judge. After we have a non-empty
        # intermediate stdout, ask the 3B judge whether it matches the
        # step's described shape. If NO, retry once with the reason as
        # a hint. Final-step shape is already checked against expected,
        # so we only judge intermediates. Skipped when the upstream
        # retry already exhausted the budget (avoids stacking retries).
        judge_verdict = None
        judge_retry_used = False
        if (not is_final
                and result["ok"]
                and result["stdout"].strip()
                and intermediate_retry_attempts == 0):
            judge_verdict = judge_step(desc, result["stdout"], cur_input)
            if not judge_verdict.ok:
                judge_retry_used = True
                retry_desc = (f"{desc} Your previous output was rejected: "
                              f"{judge_verdict.reason}. Re-emit a corrected "
                              f"output that matches the step's shape exactly.")
                result = STEP_EXECUTOR(retry_desc, cur_input, expected_shape)

        step_results.append({
            "idx": idx,
            "description": raw_desc[:120],
            "input_shape": input_shape[:200],
            "ok": result["ok"] and (is_final or bool(result["stdout"].strip())),
            "stdout": result["stdout"][:400],
            "code": result.get("code", "")[:600],
            "stderr": (result.get("stderr") or "")[:240],
            "attempts": result["attempts"],
            "intermediate_retries": intermediate_retry_attempts,
            "model_used": result["model_used"],
            "fallback_used": result["fallback_used"],
            "wall_seconds": result["wall_seconds"],
            "judge_ok": (judge_verdict.ok if judge_verdict else None),
            "judge_reason": (judge_verdict.reason if judge_verdict else None),
            "judge_retry_used": judge_retry_used,
        })
        if is_final:
            final_stdout = result["stdout"]
            final_ok = result["ok"] and result["stdout"] == task["expected"]
        cur_input = result["stdout"]
        # Hard-stop the pipeline if an intermediate step still failed
        # (empty stdout after retries) — running subsequent steps on empty
        # input wastes cycles and produces noisy step_results.
        if not is_final and not cur_input.strip():
            break

    # 3. Sonnet reports
    summary = {
        "n_steps": len(steps),
        "final_stdout": final_stdout[:500],
        "ok": final_ok,
    }
    report_prompt = REPORT_PROMPT.format(
        result=json.dumps(summary, ensure_ascii=False), goal=task["goal"])
    r3 = claude_call(report_prompt, REPORT_SYSTEM)
    total_in += r3["prompt_tokens"]; total_out += r3["completion_tokens"]
    total_cost += r3["cost_usd"]
    stage_records.append({"stage": "report", "in": r3["prompt_tokens"],
                          "out": r3["completion_tokens"]})

    return {
        "path": "C_chained",
        "ok": final_ok,
        "stdout": final_stdout,
        "n_steps": len(steps),
        "step_results": step_results,
        "tokens_in": total_in,
        "tokens_out": int(total_out),
        "cost_usd": round(total_cost, 6),
        "wall_seconds": round(time.time() - t0, 2),
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
    ap.add_argument("--with-chained", action="store_true",
                    help="Also run Path C: chained sub-agent. Sonnet "
                         "decomposes the task into 1-3 single-step Sigil "
                         "calls, results pipe through. Tests whether "
                         "single-step delegation lifts multi-step accuracy.")
    ap.add_argument("--no-step-judge", action="store_true",
                    help="Disable the NH2 Tier B step-judge in path_c. "
                         "Use to ablate the judge's contribution.")
    ap.add_argument("--cache-a", default=None,
                    help="Reuse Path A results from a prior result JSON file "
                         "(by task id). Path A is essentially deterministic "
                         "for a given task+Sonnet model — re-running it on "
                         "every harness invocation wastes cloud tokens.")
    ap.add_argument("--cache-b", default=None,
                    help="Reuse Path B results from a prior result JSON. "
                         "Use only when neither the local Sigil model nor "
                         "the harness logic has changed — otherwise B "
                         "should be re-run.")
    ap.add_argument("--cloud-model", default="claude-sonnet-4-6",
                    help="Cloud model used by Path A and the orchestration "
                         "stages of Paths B and C. Default claude-sonnet-4-6. "
                         "Pass claude-opus-4-7 to test whether a stronger "
                         "orchestrator/decomposer changes the chained-pipeline "
                         "ceiling — at 5x the price.")
    ap.add_argument("--executor", default="sigil",
                    choices=("sigil", "sonnet", "python"),
                    help="Step executor for Path C. 'sigil' (default) uses "
                         "the local Sigil ensemble; 'sonnet' uses Sonnet "
                         "writing inline Python per step (NH6 diagnostic); "
                         "'python' uses a local coder model writing Python "
                         "(NH10 control — tests whether the same local model "
                         "with a Python target closes the executor gap).")
    ap.add_argument("--python-model", default="qwen2.5-coder:7b",
                    help="ollama model name for --executor python. Default "
                         "qwen2.5-coder:7b (no Sigil fine-tune).")
    args = ap.parse_args()
    global CLOUD_MODEL, STEP_EXECUTOR, LOCAL_PYTHON_MODEL
    CLOUD_MODEL = args.cloud_model
    LOCAL_PYTHON_MODEL = args.python_model
    if args.executor == "sonnet":
        STEP_EXECUTOR = sonnet_execute_step
        print(f"  [diagnostic] Path C executor: SONNET ({CLOUD_MODEL})")
    elif args.executor == "python":
        STEP_EXECUTOR = local_python_execute_step
        print(f"  [control] Path C executor: LOCAL PYTHON ({LOCAL_PYTHON_MODEL})")
    if args.no_step_judge:
        # Monkey-patch the judge to always pass (ablation).
        import sigil_step_judge as _sj
        _sj.judge_step = lambda *a, **kw: _sj.JudgeVerdict(
            ok=True, reason="judge disabled", raw="")
        # Also rebind the symbol imported into this module.
        global judge_step
        judge_step = _sj.judge_step

    tasks = json.loads(Path(args.tasks).read_text())
    print(f"Loaded {len(tasks)} agentic tasks\n")

    cache_a = {}
    if args.cache_a:
        prior = json.loads(Path(args.cache_a).read_text())
        cache_a = {t["id"]: t["A"] for t in prior.get("tasks", [])}
        print(f"  Loaded Path A cache from {args.cache_a}: {len(cache_a)} entries\n")
    cache_b = {}
    if args.cache_b:
        prior = json.loads(Path(args.cache_b).read_text())
        cache_b = {t["id"]: t["B"] for t in prior.get("tasks", [])}
        print(f"  Loaded Path B cache from {args.cache_b}: {len(cache_b)} entries\n")

    enable_c = args.with_chained
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
            c = None
        else:
            if t["id"] in cache_a:
                a = dict(cache_a[t["id"]])
                a["from_cache"] = args.cache_a
            else:
                a = path_a_cloud_only(t)
            if t["id"] in cache_b:
                b = dict(cache_b[t["id"]])
                b["from_cache"] = args.cache_b
            else:
                b = path_b_hybrid(t)
            c = path_c_chained_hybrid(t) if enable_c else None
        print(f"   A cloud:    {'P' if a['ok'] else 'F'} (in={a['tokens_in']} out={a['tokens_out']} ${a['cost_usd']:.4f}, {a['wall_seconds']:.1f}s)")
        print(f"   B hybrid:   {'P' if b['ok'] else 'F'} (in={b['tokens_in']} out={b['tokens_out']} ${b['cost_usd']:.4f}, {b['wall_seconds']:.1f}s)")
        if c is not None:
            print(f"   C chained:  {'P' if c['ok'] else 'F'} (in={c['tokens_in']} out={c['tokens_out']} ${c['cost_usd']:.4f}, {c['wall_seconds']:.1f}s, {c.get('n_steps', '?')} steps)")
        row = {"id": t["id"], "shape": t["shape"], "A": a, "B": b}
        if c is not None:
            row["C"] = c
        rows.append(row)

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
    if enable_c:
        total_c_in = sum(r["C"]["tokens_in"] for r in rows if "C" in r)
        total_c_out = sum(r["C"]["tokens_out"] for r in rows if "C" in r)
        total_c_cost = sum(r["C"]["cost_usd"] for r in rows if "C" in r)
        total_c_pass = sum(1 for r in rows if "C" in r and r["C"]["ok"])
        aggregate["C_chained"] = {
            "pass": total_c_pass, "input_tokens": total_c_in,
            "output_tokens": total_c_out, "cost_usd": round(total_c_cost, 4),
            "vs_A_accuracy_pp": total_c_pass - total_a_pass,
            "vs_B_accuracy_pp": total_c_pass - total_b_pass,
        }

    print()
    print(f"=== AGGREGATE ({len(rows)} tasks) ===")
    print(f"  Cloud-only (A): pass {total_a_pass}/{len(rows)}  in={total_a_in:>6} out={total_a_out:>5} ${total_a_cost:.4f}")
    print(f"  Hybrid     (B): pass {total_b_pass}/{len(rows)}  in={total_b_in:>6} out={total_b_out:>5} ${total_b_cost:.4f}")
    if enable_c:
        print(f"  Chained    (C): pass {aggregate['C_chained']['pass']}/{len(rows)}  in={total_c_in:>6} out={total_c_out:>5} ${total_c_cost:.4f}  vs B {aggregate['C_chained']['vs_B_accuracy_pp']:+d}pp")
    print(f"  Savings B vs A: input −{aggregate['savings']['input_tokens_saved_pct']}%  output −{aggregate['savings']['output_tokens_saved_pct']}%  cost −{aggregate['savings']['cost_saved_pct']}%  accuracy {aggregate['savings']['accuracy_delta_pp']:+d} pp")

    out_data = {"aggregate": aggregate, "tasks": rows}
    Path(args.out).write_text(json.dumps(out_data, indent=2, ensure_ascii=False))
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
