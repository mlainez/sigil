#!/usr/bin/env python3
"""Sigil MCP server — exposes the local Qwen-Sigil + Phi-Sigil ensemble as
a tool that Claude Code, opencode, or any MCP-aware agent can call.

The point of this server is to let a cloud orchestrator (Claude Sonnet,
GPT-5, etc.) DELEGATE tooling-shape code generation to local models that
already speak Sigil natively, instead of generating Python inline. The
cloud orchestrator gets back validated stdout — never has to spend tokens
writing the program itself.

Tools exposed:

  sigil_run_task(description, input, expected_shape="")
    - The main agentic delegation tool. Generates a Sigil program for
      the described task, runs it on `input`, returns stdout.
    - If the first attempt's output doesn't look right (model retry
      logic), the server retries up to 3 times with a hint.
    - Returns a structured result the orchestrator can chain on.

  sigil_run_code(code, input)
    - Raw Sigil execution. Skips generation. Useful when the orchestrator
      already has the code (e.g. user wrote it, or a previous turn
      generated something the orchestrator wants to re-use).

  sigil_capabilities()
    - Returns a short description of what Sigil + this server can do.
      Helps orchestrators decide whether to delegate vs handle in-cloud.

Run as:
  python3 tools/agent_harness/sigil_mcp_server.py
  # speaks JSON-RPC on stdio (the MCP standard transport)

Configure in Claude Code:
  See tools/agent_harness/README.md for `.claude/mcp.json` setup.

Configure in opencode:
  See tools/agent_harness/README.md for opencode mcp config.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SIGIL_BIN = str(REPO / "interpreter" / "_build" / "default" / "vm.exe")
PAREN_BALANCE_TOOL = str(REPO / "tools" / "balance_parens.sigil")

# Default models — overridable via env. NH3 (Phase 27) replaced the
# Phi-4 fallback with DeepSeek-Coder-6.7B fine-tuned on the same Sigil
# corpus. Smaller (3.9 GB vs 9.1 GB), faster, no Q4_K_M drift, and
# catches shell_argv_count (the project's hardest persistent residual).
PRIMARY_MODEL = os.environ.get("SIGIL_PRIMARY_MODEL", "qwen-sigil-v7:7b")
FALLBACK_MODEL = os.environ.get("SIGIL_FALLBACK_MODEL", "deepseek-sigil:6.7b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MAX_ATTEMPTS = int(os.environ.get("SIGIL_MAX_ATTEMPTS", "3"))

# Reuse the SLIM_HEADER + retry prompt from the existing harness so we get
# the same generation behavior here as in eval_real_tooling.py.
sys.path.insert(0, str(REPO / "benchmark"))
from corpus_extender import SLIM_HEADER, gen_sigil_ollama, gen_sigil_ollama_with_hint, strip_fences
from eval_real_tooling import validator_hint  # surgical retry-hint rewriter
from sigil_name_validator import validate as name_validate, format_validation_hint


# ============================================================================
# Sigil execution
# ============================================================================

def lint_sigil(code: str) -> tuple[bool, str]:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False)
    f.write(code); f.close()
    try:
        r = subprocess.run([SIGIL_BIN, "--lint", f.name],
                          capture_output=True, text=True, timeout=5)
        return (r.returncode == 0,
                (r.stderr.strip() or r.stdout.strip()).splitlines()[0] if r.returncode != 0 else "")
    finally:
        os.unlink(f.name)


def balance_parens_sigil(code: str) -> tuple[str, str]:
    """Delegate to the Sigil-implemented balancer at tools/balance_parens.sigil.
    Returns (balanced_code, note). Note is empty if no change was made."""
    try:
        r = subprocess.run([SIGIL_BIN, PAREN_BALANCE_TOOL, code],
                          capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return code, ""
        candidate = r.stdout.rstrip("\n")
        if candidate != code:
            ok, _ = lint_sigil(candidate)
            if ok:
                return candidate, "auto-balancer applied"
    except Exception:
        pass
    return code, ""


def run_sigil(code: str, input_arg: str, timeout: int = 15) -> tuple[bool, str, str]:
    """Run Sigil code with one CLI arg. Returns (success, stdout, stderr).
    Diagnostics (argv-misuse, no-output-produced) are on by default in the
    interpreter so the orchestrator's retry prompt builder can pattern-match
    the warning strings with worked fixes."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False)
    f.write(code); f.close()
    try:
        r = subprocess.run([SIGIL_BIN, f.name, input_arg],
                          capture_output=True, text=True, timeout=timeout,
                          errors="replace")
        return r.returncode == 0, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"timed out after {timeout}s"
    finally:
        os.unlink(f.name)


# ============================================================================
# Generation with retry + ensemble fallback
# ============================================================================

def generate_and_run(description: str, input_arg: str, expected_shape: str = "") -> dict:
    """Generate Sigil code for the task, run it, retry on failure with hint.

    Returns:
      {
        "ok": bool, "stdout": str, "stderr": str, "code": str,
        "attempts": int, "model_used": str, "fallback_used": bool,
        "wall_seconds": float, "balancer_applied": bool
      }
    """
    # Build a synthetic 'task' dict matching corpus_extender's expectations
    task = {
        "desc": description,
        "args": [input_arg],
        "expected": expected_shape or "",
    }

    last_code = ""
    last_err = ""
    last_stdout = ""
    fallback_used = False
    balancer_applied = False
    t0 = time.time()

    for attempt in range(MAX_ATTEMPTS):
        is_final = attempt == MAX_ATTEMPTS - 1
        active_model = FALLBACK_MODEL if (is_final and FALLBACK_MODEL) else PRIMARY_MODEL
        if active_model == FALLBACK_MODEL:
            fallback_used = True

        if attempt == 0:
            code = gen_sigil_ollama(task, active_model, OLLAMA_URL,
                                    temperature=0.0, slim=True)
        elif active_model == FALLBACK_MODEL:
            # Cross-base ensemble fallback: call the fallback with a FRESH
            # prompt at TEMPERATURE 0. The validator_hint rewrites + ramped
            # temperature were calibrated for the primary's failure modes
            # (qwen-shaped) and biased the fallback (deepseek-shaped) toward
            # worse code. Stream C demonstrated 27/30 ramped vs 29/30 fresh
            # at temp 0 for the v7 + deepseek-sigil pair (Phase 27 / NH3).
            code = gen_sigil_ollama(task, active_model, OLLAMA_URL,
                                    temperature=0.0, slim=True)
        else:
            ramp_temp = 0.3 + 0.2 * attempt
            # Surgical validator_hint rewriter: turn SIGIL_DIAGNOSE warnings
            # into worked fixes in the retry prompt instead of raw text.
            hint = validator_hint(last_stdout, expected_shape or "", last_err) \
                   if (last_err or last_stdout) \
                   else f"got {last_stdout!r} expected {expected_shape!r}"
            code = gen_sigil_ollama_with_hint(
                task, active_model, OLLAMA_URL,
                prev_code=last_code, got_stdout=last_stdout, got_stderr=last_err,
                hint=hint, temperature=ramp_temp,
            )

        if not code:
            continue
        code = strip_fences(code)

        # Apply paren auto-balancer (Sigil-implemented)
        ok_lint, _ = lint_sigil(code)
        if not ok_lint:
            fixed, note = balance_parens_sigil(code)
            if note:
                code = fixed
                balancer_applied = True

        # NH2 Tier A pre-validator: catch wrong-language drift (Python emission
        # under multi-step pressure — accounts for ~75% of NH5 30-task A/B/C
        # failures) and hallucinated builtins. Skip the doomed run; let the
        # retry loop hand back the targeted hint.
        nv_result = name_validate(code)
        if nv_result.wrong_language or nv_result.unknown_names:
            last_code = code
            last_stdout = ""
            last_err = format_validation_hint(nv_result)
            continue

        ok, out, err = run_sigil(code, input_arg)
        if ok:
            # Caller may not have provided expected_shape; "ok" means the
            # interpreter ran without error. We return the output regardless,
            # but mark "ok" reflecting the run, not output-shape match.
            if not expected_shape or out == expected_shape:
                return {
                    "ok": True,
                    "stdout": out,
                    "stderr": "",
                    "code": code,
                    "attempts": attempt + 1,
                    "model_used": active_model,
                    "fallback_used": fallback_used,
                    "wall_seconds": round(time.time() - t0, 2),
                    "balancer_applied": balancer_applied,
                }
            # Ran but output differs from expected_shape. Prefer the
            # interpreter's diagnostic (argv-misuse, no-output-produced) over
            # a generic "got X expected Y" so validator_hint can pattern-match
            # the worked-fix prompt; fall back to the diff if stderr is empty.
            last_stdout = out
            last_err = err.strip() if err else f"got {out!r} expected {expected_shape!r}"
        else:
            last_stdout = ""
            last_err = err.strip().splitlines()[0] if err else "unknown error"
        last_code = code

    return {
        "ok": False,
        "stdout": last_stdout,
        "stderr": last_err[:500],
        "code": last_code,
        "attempts": MAX_ATTEMPTS,
        "model_used": active_model,
        "fallback_used": fallback_used,
        "wall_seconds": round(time.time() - t0, 2),
        "balancer_applied": balancer_applied,
    }


# ============================================================================
# MCP server
# ============================================================================

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("sigil-local-tooling")


@mcp.tool()
def sigil_run_task(description: str, input: str, expected_shape: str = "") -> str:
    """Generate and run a Sigil program for a tooling-shape task using the
    local fine-tuned Sigil ensemble (Qwen-Sigil-7B → Phi-Sigil-14B fallback).

    USE THIS WHEN:
      - The task is short verifiable data processing: parse a log, filter
        a CSV, extract a regex, transform output, count/sort, etc.
      - You have or can fabricate a sample input string.
      - The expected output is text that you can validate.
      - You want to avoid spending tokens writing Python inline.

    DO NOT use for: architecture decisions, multi-file refactoring, code review,
    anything requiring deep reasoning about other code.

    Args:
        description: One-sentence description of the transformation.
        input: The input data as a single string (paths to files in this
               string get read as files when the program reads stdin).
        expected_shape: Optional. Exact expected stdout. If provided, the
                        server will retry the generation up to 3× until the
                        output matches.

    Returns:
        JSON-encoded result with: ok, stdout, code, attempts, wall_seconds,
        model_used, fallback_used. The orchestrator can then either trust
        the stdout or re-call with a different description.
    """
    result = generate_and_run(description, input, expected_shape)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def sigil_run_code(code: str, input: str) -> str:
    """Execute a Sigil program without generating it. The orchestrator (or
    the user) provides the program directly; the server runs it on `input`
    and returns stdout/stderr.

    Useful when:
      - The orchestrator wants to re-use a program from a previous call.
      - A user wrote the program by hand and wants to test it.
      - The orchestrator generated the program itself (e.g. for tasks
        Sigil supports but the local ensemble fails on).

    Args:
        code: Sigil source code (no fences).
        input: Single string passed as $0 to the program.

    Returns:
        JSON: {ok, stdout, stderr, wall_seconds}.
    """
    t0 = time.time()
    code = strip_fences(code)
    ok_lint, lint_err = lint_sigil(code)
    if not ok_lint:
        # Try the auto-balancer first
        fixed, note = balance_parens_sigil(code)
        if note:
            code = fixed
            ok_lint, lint_err = lint_sigil(code)
    if not ok_lint:
        return json.dumps({
            "ok": False, "stdout": "", "stderr": f"lint failed: {lint_err}",
            "wall_seconds": round(time.time() - t0, 2),
        })
    ok, out, err = run_sigil(code, input)
    return json.dumps({
        "ok": ok, "stdout": out, "stderr": err,
        "wall_seconds": round(time.time() - t0, 2),
    }, ensure_ascii=False)


@mcp.tool()
def sigil_capabilities() -> str:
    """Return a short description of what Sigil + this server can do, so the
    orchestrator can route tasks intelligently. Call this at the start of a
    session if you're not sure when to delegate."""
    return """Sigil is an S-expression Lisp-shaped scripting language with an
interpreter at vm.exe. The local fine-tuned ensemble (Qwen-Sigil-7B + Phi-Sigil-14B)
is good at host-tooling-shape tasks:

GOOD FIT:
  - Parsing: CSV, TSV, JSON, log lines, /etc/passwd-format, etc.
  - Filtering: grep-like patterns, line filters
  - Counting and aggregation: word counts, frequency tables, sums
  - Text transforms: case, replace, dedup, sort, join, split
  - Regex extraction: emails, URLs, dates, IPs (basic)
  - Format conversion: TSV↔CSV, JSON↔lines, etc.
  - Arithmetic over parsed data

NOT A FIT (route to cloud orchestrator instead):
  - Architecture / API design decisions
  - Multi-file refactoring or codebase-wide changes
  - Output in non-Sigil-expressible languages (e.g. SQL, Dockerfile)
  - Tasks requiring multi-step reasoning over large context

PERFORMANCE: 5-15 seconds per call (vs ~3 seconds for cloud Sonnet),
zero marginal $ cost, no network egress. Accuracy on Stream C tooling
benchmark: 27-28/30 (~93%) vs Sonnet 29/30. Confidentiality: input data
never leaves the local process."""


if __name__ == "__main__":
    mcp.run()
