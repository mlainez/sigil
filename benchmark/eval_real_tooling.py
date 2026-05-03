#!/usr/bin/env python3
"""Stream C deployment study: 30 real tooling tasks tested across three paths.

Path A: Local fine-tuned Sigil-7B (qwen-sigil:7b or qwen-sigil-v2:7b),
        with RAG and validate-and-retry up to N=3 attempts.

Path B: Local un-tuned Qwen2.5-Coder-7B, single shot, raw Python.

Path C: Cloud Sonnet (or other --model), single shot, raw Python.

For each task, measure:
  - pass/fail
  - wall-clock seconds
  - output length (chars)
  - $ cost (cloud paths) — based on token count × per-token rate
  - Wh estimate (local paths) — wall_seconds × power_draw

Aggregate per category and overall, output decision matrix.
"""
from __future__ import annotations

import argparse, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO / "interpreter" / "_build" / "default" / "vm.exe")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rag
from corpus_extender import (
    GRAMMAR, gen_sigil, gen_sigil_ollama, gen_sigil_ollama_with_hint,
    run_python, run_sigil, strip_fences,
)

OLLAMA_URL = "http://localhost:11434"

# Pricing (USD per million tokens, approximate as of 2026-04)
PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
}

# =====================================================================
# Energy estimation — sourced, with explicit uncertainty bounds.
# Treat the outputs as ORDER-OF-MAGNITUDE; the per-task numbers below
# carry roughly ±50% uncertainty until calibrated with a real wattmeter.
# =====================================================================
#
# Local GPU power during inference. The RX 7800 XT has a TBP of 263 W (AMD
# spec). Sustained inference on RDNA3 typically draws 150-200 W during
# compute-bound generation per third-party power measurements (TechPowerUp,
# Tom's Hardware reviews; values consistent across Ada/Hopper too at
# similar perf-per-watt). 180 W is the midpoint we use here. The whole
# system at the wall adds ~50-80 W (CPU + RAM + motherboard + idle drives);
# we DO NOT include this — it's effectively a wash with the cloud's
# baseline machine load.
POWER_LOCAL_INFERENCE = 180.0  # W; midpoint of published RDNA3 inference draw
POWER_LOCAL_IDLE = 50.0        # W; not currently used in per-task accounting

# Cloud per-token energy (Wh per 1K tokens). Sources for the ranges:
#
# - Luccioni, Jernite, & Strubell (2024), "Power Hungry Processing: Watts
#   Driving the Cost of AI Deployment" (FAccT '24).
#   https://arxiv.org/abs/2311.16863
#   Measured 0.047 Wh/query for 1B models, ~0.4 Wh/query for 11B BLOOM
#   class on text-gen tasks (input+output combined, batch size 32).
#
# - Samsi et al. (2023), "From Words to Watts: Benchmarking the Energy Costs
#   of LLM Inference." MIT Lincoln Lab.
#   https://arxiv.org/abs/2310.03003
#   Measured 0.3-0.5 Wh per 1K generated tokens on H100s for 7B-class
#   models; closer to 1.5-3 Wh per 1K for 70B-class.
#
# - Patterson et al. (2021), "Carbon Emissions and Large Neural Networks"
#   https://arxiv.org/abs/2104.10350
#   Establishes that hyperscale datacenter PUE is now 1.10-1.20, so the
#   compute-energy figures above multiply by ~1.15 to capture cooling and
#   power distribution. Network/transit energy is small at modern
#   intensities (Aslan et al. 2018, ~0.06 kWh/GB for residential at the
#   time, lower now).
#
# Sonnet's exact size is undisclosed; Anthropic does not publish per-call
# energy. We therefore report a RANGE bracketed by the 7B-class lower
# bound (0.3 Wh/1K out tokens) and the 70B-class upper bound (3 Wh/1K out
# tokens). For input tokens we use ~0.04 Wh/1K (mostly memory bandwidth,
# little compute on prefill once cached). PUE 1.15 is folded in.
CLOUD_INPUT_WH_PER_1K = 0.04   # Wh; lower bound (prefill, cache-hit dominated)
CLOUD_OUTPUT_WH_LOWER = 0.3    # Wh per 1K output tokens; 7B-class lower bound
CLOUD_OUTPUT_WH_UPPER = 3.0    # Wh per 1K output tokens; 70B-class upper bound
CLOUD_PUE_FACTOR      = 1.15   # PUE multiplier (Patterson 2021)


PYTHON_SYSTEM = (
    "You write Python 3 programs. Use sys.argv for input. Output ONLY raw Python code, "
    "no markdown fences, no prose. Always include `import sys` if you use sys.argv."
)
PYTHON_PROMPT = (
    "Write a Python 3 program that does exactly this:\n\n"
    "TASK: {desc}\n\n"
    "Example: when called with CLI args {args}, output must be EXACTLY:\n"
    "{expected!r}\n\n"
    "Output ONLY the raw Python code."
)


def gen_python_local(task: dict, model: str) -> tuple[str, dict]:
    body = json.dumps({
        "model": model,
        "prompt": PYTHON_PROMPT.format(desc=task["desc"], args=task["args"], expected=task["expected"]),
        "system": PYTHON_SYSTEM,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2048},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=body,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    out = data.get("response", "").strip()
    for fence in ["```python", "```py", "```"]:
        if out.startswith(fence): out = out[len(fence):].lstrip(); break
    if out.endswith("```"): out = out[:-3].rstrip()
    meta = {
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "completion_tokens": data.get("eval_count", 0),
    }
    return out, meta


def gen_python_cloud(task: dict, model: str) -> tuple[str, dict]:
    """Use claude --print with the python prompt."""
    full_prompt = PYTHON_SYSTEM + "\n\n" + PYTHON_PROMPT.format(
        desc=task["desc"], args=task["args"], expected=task["expected"])
    cmd = ["claude", "--print", "--output-format", "json",
           "--model", model, "-p", full_prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=180, cwd="/tmp")
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        text = data.get("result") or ""
        for fence in ["```python", "```py", "```"]:
            if text.startswith(fence): text = text[len(fence):].lstrip(); break
        if text.endswith("```"): text = text[:-3].rstrip()
        usage = data.get("usage", {})
        return text, {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
        }
    except Exception:
        return "", {}


def cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    p = PRICING.get(model)
    if not p: return 0.0
    return in_tok * p["input"] / 1e6 + out_tok * p["output"] / 1e6


def wh_local(seconds: float) -> float:
    return (seconds * POWER_LOCAL_INFERENCE) / 3600.0


def _paren_depth_ignoring_strings(s: str) -> int:
    """Count net paren depth in s, ignoring parens inside double-quoted strings.
    Sigil has no comments so no need to handle those. Backslash-escapes inside
    strings are honored."""
    depth = 0
    in_string = False
    i = 0
    while i < len(s):
        c = s[i]
        if in_string:
            if c == "\\" and i + 1 < len(s):
                i += 2
                continue
            if c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
        i += 1
    return depth


PAREN_BALANCE_TOOL = str(REPO / "tools" / "balance_parens.sigil")


def auto_balance_parens(code: str, lint_fn) -> tuple[str, str]:
    """Delegate to the Sigil-implemented balancer at tools/balance_parens.sigil.

    The actual balancing logic is in the Sigil prelude (`balance_parens`).
    Per the project principle: if it CAN be written in Sigil, it MUST be.
    Python here is just an orchestrator: invoke vm.exe on the tool, capture
    stdout. The Sigil tool returns the input unchanged when balanced or off
    by more than 2; otherwise returns the appended/trimmed variant.

    This function then lints the result via the supplied lint_fn — only
    accepts the fix if it actually parses clean. Returns (code, note).
    """
    depth = _paren_depth_ignoring_strings(code)
    if depth == 0:
        return code, ""
    if abs(depth) > 2:
        return code, ""

    # Call the Sigil tool. Single arg = the code. Stdout = balanced version.
    try:
        r = subprocess.run(
            [SIGIL_BIN, PAREN_BALANCE_TOOL, code],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return code, ""
        # The tool calls (println ...) which adds a trailing \n we strip.
        candidate = r.stdout.rstrip("\n")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return code, ""

    if candidate == code:
        return code, ""
    ok, _ = lint_fn(candidate)
    if ok:
        action = "appended" if depth > 0 else "trimmed"
        return candidate, f"auto-balancer (Sigil): {action} {abs(depth)} ')'"
    return code, ""


def lint_sigil(code: str) -> tuple[bool, str]:
    """Lint Sigil code via vm.exe --lint. Returns (ok, first_error_line)."""
    import tempfile
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False)
    f.write(code); f.close()
    try:
        r = subprocess.run([SIGIL_BIN, "--lint", f.name],
                          capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return True, ""
        msg = (r.stderr.strip() or r.stdout.strip()).splitlines()
        return False, msg[0] if msg else ""
    except subprocess.TimeoutExpired:
        return False, "lint timeout"
    finally:
        os.unlink(f.name)


# =====================================================================
# Surgical-hint validator — replaces the generic structural-diff hint
# with shape-specific diagnostics that tell the model exactly which
# pattern is wrong, plus the canonical fix.
# =====================================================================

def _format_lines_diff(got_lines: list[str], exp_lines: list[str], maxn: int = 6) -> str:
    """Show a side-by-side line diff truncated to maxn lines."""
    n = max(len(got_lines), len(exp_lines))
    rows = []
    for i in range(min(n, maxn)):
        g = got_lines[i] if i < len(got_lines) else "(none)"
        e = exp_lines[i] if i < len(exp_lines) else "(none)"
        marker = " " if g == e else "*"
        rows.append(f"  {marker} L{i+1}: got {g!r:30s}  expected {e!r}")
    if n > maxn:
        rows.append(f"  ... ({n - maxn} more lines)")
    return "\n".join(rows)


def validator_hint(got_stdout: str, expected: str, got_stderr: str) -> str:
    """Surgical-hint validator. Detects the FAILURE SHAPE and emits a
    targeted, actionable hint with the canonical fix. Replaces the earlier
    generic structural-diff which gave the model context but no direction.
    """
    # ---- Interpreter diagnostics (SIGIL_DIAGNOSE=1) come through stderr
    # even when the program "succeeded" with returncode=0. These fire on
    # the empty-output failure mode that dominates the agent harness:
    # (argv) misuse, no-output-produced. Match before the runtime-error
    # branch since they're warnings prefixed with "Warning: ". ----
    if got_stderr and "Warning: (argv) returned a 1-element list" in got_stderr:
        return ("Your program called (argv) with a 1-element list whose "
                "element contains newlines — that means the harness passed "
                "the input as ONE argument and you treated it as if it were "
                "already split. "
                "FIX: replace (argv) with (split $0 \"\\n\") for line-by-line "
                "input. $0 is the first CLI argument as a single string; "
                "(argv) is the list of SEPARATE CLI arguments. Example:\n"
                "  (set lines (split $0 \"\\n\"))\n"
                "  (for-each line lines (println line))")
    if got_stderr and "Warning: program completed without writing any output" in got_stderr:
        return ("Your program ran without errors but produced no output. "
                "Most common causes on this harness: (a) you used (argv) "
                "when you should have used (split $0 \"\\n\") — the input "
                "is in $0 as a single multi-line string; (b) an (if cond ...) "
                "guard was always false because you indexed the wrong field; "
                "(c) the array you iterated was empty because (split ...) "
                "returned a single string. Add (println intermediate) at the "
                "first step to see what your variables actually contain, "
                "then fix the reaching shape.")

    # ---- Runtime errors first: did-you-mean for undefined names ----
    if got_stderr:
        first = got_stderr.strip().splitlines()[0][:200]
        # Structural anti-patterns that point to a different control-flow shape
        if "for-loop iterator" in first and "was mutated" in first:
            return (f"{first}  HINT: (for i 0 n ...) is fixed-stride. "
                    "For skip-loops / variable-stride iteration, use "
                    "(set i 0) (while (lt i n) ...body... (set i (add i k))). "
                    "Pattern for consecutive runs:\n"
                    "  (set i 0) (while (lt i n)\n"
                    "    (set j i) (while (and (lt j n) (eq xs[j] xs[i])) (set j (add j 1)))\n"
                    "    (println ...)\n"
                    "    (set i j))")
        # Common reach corrections
        suggestions = {
            "string_length": "use (len s) — Sigil string length is just len",
            "arg_int": "if you want to parse a STRING into int, use parse_int instead — arg_int takes a CLI arg INDEX, not the string itself",
            "first_index_of": "use index_of",
            "list_": "Sigil arrays use array_* prefix, e.g. (array_get arr i), not list_*",
            "to_int": "use parse_int s for string→int; to_int doesn't exist",
            "regex_replace_all": "use regex_replace (it already replaces all matches by default)",
            "string_split": "use split (no string_ prefix)",
            "string_join": "use join (no string_ prefix)",
        }
        for bad, hint in suggestions.items():
            if bad in first:
                return f"{first}  HINT: {hint}"
        return first

    if got_stdout == expected:
        return "No diff."

    # ---- Pure-numeric off-by-one detection (single int output) ----
    g_strip = got_stdout.rstrip("\n")
    e_strip = expected.rstrip("\n")
    try:
        gi = int(g_strip)
        ei = int(e_strip)
        diff = gi - ei
        if abs(diff) <= 2:
            sign = "MORE" if diff > 0 else "LESS"
            cause = ""
            if diff == 1:
                cause = (" Common cause: (split s \"\\n\") returns N+1 parts when "
                         "s contains N newlines — for wc -l style counting use "
                         "(count s \"\\n\") instead of (len (split s \"\\n\")).")
            elif diff == -1:
                cause = (" Common cause: missing the final element in a loop "
                         "(off-by-one in (for i 0 n) — n is exclusive). Or "
                         "you're counting newlines not lines: try (line_count s).")
            return f"Got {gi}, expected {ei} — off by {abs(diff)} {sign}.{cause}"
    except ValueError:
        pass

    # ---- Line-by-line shape analysis ----
    g_lines = got_stdout.splitlines(keepends=False)
    e_lines = expected.splitlines(keepends=False)
    g_tail = got_stdout.endswith("\n")
    e_tail = expected.endswith("\n")

    notes: list[str] = []

    # Trailing newline
    if g_tail and not e_tail:
        notes.append("Output has a TRAILING newline that shouldn't be there. (println adds \\n; use (print) without newline, or trim.)")
    elif e_tail and not g_tail:
        notes.append("Output is MISSING the final \\n. End with (println last) or add \\n explicitly.")

    # Line count mismatch — surgical analysis
    if len(g_lines) != len(e_lines):
        if len(g_lines) > len(e_lines):
            extra = g_lines[len(e_lines):]
            notes.append(
                f"Output has {len(g_lines)} lines, expected {len(e_lines)}. "
                f"Extra lines at end: {extra[:3]}. "
                "Likely cause: a final separator/extra println after the loop."
            )
        else:
            missing = e_lines[len(g_lines):]
            notes.append(
                f"Output has {len(g_lines)} lines, expected {len(e_lines)}. "
                f"Missing lines: {missing[:3]}. "
                "Likely cause: loop bound off-by-one, or filtering out a row that should pass."
            )

    # Per-line content checks — detect over-match (line in got is a SUPERSTRING
    # of the corresponding line in expected). Common in regex extraction tasks.
    if len(g_lines) >= 1 and len(e_lines) >= 1:
        over_matches = []
        under_matches = []
        for gl, el in zip(g_lines, e_lines):
            if gl != el:
                if el in gl and len(gl) > len(el):
                    over_matches.append((el, gl))
                elif gl in el and len(el) > len(gl):
                    under_matches.append((gl, el))
        if over_matches:
            sample = over_matches[0]
            notes.append(
                f"Output line OVER-matched: extracted {sample[1]!r} but expected exactly {sample[0]!r}. "
                "Likely cause: regex too greedy. Tighten the pattern boundaries: "
                "use \\b word-anchors, bound character classes (e.g. {2,6} not {2,}), "
                "or use a more specific class like [^ ] instead of .* "
            )
        if under_matches:
            sample = under_matches[0]
            notes.append(
                f"Output line UNDER-matched: extracted {sample[0]!r} but expected {sample[1]!r}. "
                "Pattern was too restrictive — broaden the character class."
            )

    # Output-too-short / first-line-only diagnostic
    if not notes:
        # Fall back to first-difference position with surgical formatting
        common = 0
        for i in range(min(len(got_stdout), len(expected))):
            if got_stdout[i] != expected[i]:
                break
            common += 1
        if common == 0:
            notes.append(
                f"Output diverges immediately. Got {got_stdout[:60]!r}, expected {expected[:60]!r}."
            )
        else:
            ctx_g = got_stdout[max(0, common - 8):common + 12]
            ctx_e = expected[max(0, common - 8):common + 12]
            notes.append(
                f"Output matches first {common} chars, then diverges: "
                f"got ...{ctx_g!r}... expected ...{ctx_e!r}..."
            )

    # Always include a compact lines-diff block when both have multiple lines
    if len(g_lines) > 1 or len(e_lines) > 1:
        notes.append("Lines diff:\n" + _format_lines_diff(g_lines, e_lines))

    return " ".join(notes)


def wh_cloud_estimate(in_tok: int, out_tok: int, upper: bool = False) -> float:
    """Sourced energy estimate per cloud call. See module-level docstring for
    citations (Luccioni 2024, Samsi 2023, Patterson 2021). Returns either the
    7B-class lower bound (default) or the 70B-class upper bound (upper=True).
    Wide uncertainty: report both ends, never a single number, for any claim."""
    out_wh_per_1k = CLOUD_OUTPUT_WH_UPPER if upper else CLOUD_OUTPUT_WH_LOWER
    compute_wh = (in_tok * CLOUD_INPUT_WH_PER_1K + out_tok * out_wh_per_1k) / 1000.0
    return compute_wh * CLOUD_PUE_FACTOR


def eval_task_local_sigil(task: dict, model: str, index: dict, max_attempts: int = 3,
                          fallback_model: str = "", fallback_start: int = -1,
                          fallback_fresh: bool = False,
                          fallback_temp: float = -1.0,
                          validator: bool = False,
                          no_rag: bool = False,
                          paren_balance: bool = False) -> dict:
    """Fine-tuned Sigil model with RAG and retry. The ensemble routing knobs:
    - fallback_model: model name to swap to when the primary's retries are exhausted
    - fallback_start: attempt index (0-based) at which to swap; -1 = swap on the final
      attempt only (matches old single-attempt fallback). E.g. with max_attempts=4 and
      fallback_start=2: attempts 0-1 = primary, attempts 2-3 = fallback.
    - fallback_fresh: when fallback runs, use the cold prompt (no prev_code/hint) so
      it isn't anchored on the primary's wrong code.
    - fallback_temp: explicit temperature for fallback attempts (-1 = use the
      0.3 + 0.2 * attempt ramp).
    - no_rag: skip RAG entirely. The prompt only contains SLIM_HEADER + task. Useful
      for measuring what the fine-tuned model knows on its own, before adding RAG seeds.
    """
    if no_rag:
        block = ""
    else:
        hits = rag.query(task["desc"], k=5, index=index, min_score=0.65)
        block = rag.format_examples(hits) if hits else ""
    last_code = ""; last_err = ""; last_stdout = ""
    total_seconds = 0.0
    fallback_used = False
    swap_at = (max_attempts - 1) if fallback_start < 0 else fallback_start
    for attempt in range(max_attempts):
        t0 = time.time()
        use_fallback = fallback_model and attempt >= swap_at
        active_model = fallback_model if use_fallback else model
        if use_fallback:
            fallback_used = True

        ramp_temp = 0.3 + 0.2 * attempt
        eff_temp = ramp_temp if (fallback_temp < 0 or not use_fallback) else fallback_temp

        if attempt == 0:
            code = gen_sigil_ollama(task, active_model, OLLAMA_URL,
                                    temperature=0.0, slim=False, rag_block=block)
        elif use_fallback and fallback_fresh:
            # Cold call on the fallback — don't anchor it on the primary's code.
            code = gen_sigil_ollama(task, active_model, OLLAMA_URL,
                                    temperature=eff_temp, slim=False, rag_block=block)
        else:
            # Validator-in-loop: synthesize a structured diff hint from the
            # previous run's stdout/stderr instead of just the raw stderr line.
            if validator:
                hint = validator_hint(last_stdout, task["expected"], last_err)
            else:
                hint = last_err[:200]
            code = gen_sigil_ollama_with_hint(
                task, active_model, OLLAMA_URL,
                prev_code=last_code, got_stdout=last_stdout, got_stderr=last_err,
                hint=hint, temperature=eff_temp,
                rag_block=block)
        total_seconds += time.time() - t0
        if not code: continue

        # Paren auto-balancer: cheap try at fixing ±1-2 paren-count slips
        # before submitting to the interpreter. Only kicks in if the code
        # would otherwise fail to lint AND has a small balance offset.
        balance_note = ""
        if paren_balance:
            ok_lint, _ = lint_sigil(code)
            if not ok_lint:
                fixed, balance_note = auto_balance_parens(code, lint_sigil)
                if balance_note:
                    code = fixed

        # Diagnostics are on by default; argv-misuse and no-output-produced
        # surface to stderr so validator_hint can rewrite the retry prompt
        # with a worked fix.
        ok, out, err = run_sigil(code, task["args"])
        if ok and out == task["expected"]:
            return {"path": "local_sigil", "pass": True, "attempts": attempt+1,
                    "code": code, "seconds": round(total_seconds, 2),
                    "chars": len(code), "wh": round(wh_local(total_seconds), 4),
                    "cost_usd": 0.0, "stdout": out, "stderr": "",
                    "model_used": active_model, "fallback_used": fallback_used,
                    "paren_balanced": balance_note}
        last_code = code
        last_stdout = out if ok else ""
        last_err = err.strip().splitlines()[0] if err else f"got {out!r} expected {task['expected']!r}"
    return {"path": "local_sigil", "pass": False, "attempts": max_attempts,
            "code": last_code, "seconds": round(total_seconds, 2),
            "chars": len(last_code), "wh": round(wh_local(total_seconds), 4),
            "cost_usd": 0.0, "stdout": "", "stderr": last_err[:200],
            "model_used": active_model, "fallback_used": fallback_used}


def eval_task_local_python(task: dict, model: str) -> dict:
    t0 = time.time()
    code, meta = gen_python_local(task, model)
    seconds = time.time() - t0
    if not code:
        return {"path": "local_python", "pass": False, "seconds": round(seconds,2),
                "chars": 0, "wh": round(wh_local(seconds), 4),
                "cost_usd": 0.0, "stdout": "", "stderr": "no code"}
    ok, out = run_python(code, task["args"])
    return {"path": "local_python", "pass": ok and out == task["expected"],
            "code": code, "seconds": round(seconds,2), "chars": len(code),
            "wh": round(wh_local(seconds), 4), "cost_usd": 0.0,
            "stdout": out, "stderr": "", "tokens": meta}


def eval_task_cloud_python(task: dict, model: str) -> dict:
    t0 = time.time()
    code, meta = gen_python_cloud(task, model)
    seconds = time.time() - t0
    in_tok = meta.get("prompt_tokens", 0)
    out_tok = meta.get("completion_tokens", 0)
    if not code:
        return {"path": f"cloud_{model}", "pass": False, "seconds": round(seconds,2),
                "chars": 0, "wh": round(wh_cloud_estimate(in_tok, out_tok), 4),
                "cost_usd": round(cost_usd(model, in_tok, out_tok), 4),
                "stdout": "", "stderr": "no code"}
    ok, out = run_python(code, task["args"])
    return {"path": f"cloud_{model}", "pass": ok and out == task["expected"],
            "code": code, "seconds": round(seconds,2), "chars": len(code),
            "wh": round(wh_cloud_estimate(in_tok, out_tok), 4),
            "cost_usd": round(cost_usd(model, in_tok, out_tok), 4),
            "stdout": out, "stderr": "", "tokens": meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(REPO / "benchmark" / "real_tooling_tasks.json"))
    ap.add_argument("--sigil-model", default="qwen-sigil-v2:7b")
    ap.add_argument("--sigil-fallback", default="",
                    help="Optional second Sigil model used on the final retry "
                         "attempt. The point is failure-shape diversity: a "
                         "different-lineage model can catch tasks the primary "
                         "keeps missing.")
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="Total attempts per task. With --sigil-fallback set, "
                         "the primary model gets (max_attempts - 1) attempts "
                         "and the fallback gets the last one. Default 3 = "
                         "two primary tries plus one fallback. Use 4 for the "
                         "safer routing where the primary keeps its full retry "
                         "budget before fallback.")
    ap.add_argument("--fallback-start", type=int, default=-1,
                    help="0-based attempt index at which the fallback model "
                         "takes over. -1 (default) = only the final attempt. "
                         "Set to N to give fallback attempts N..max_attempts-1.")
    ap.add_argument("--fallback-fresh", action="store_true",
                    help="When fallback attempts run, use the cold prompt "
                         "without prev_code/hint anchoring, so the fallback "
                         "isn't biased toward fixing the primary's wrong code.")
    ap.add_argument("--fallback-temp", type=float, default=-1.0,
                    help="Explicit temperature for fallback attempts. -1 = use "
                         "the default 0.3+0.2*attempt ramp. Lower (e.g. 0.3) "
                         "gives more deterministic fallback output.")
    ap.add_argument("--validator", action="store_true",
                    help="Use the validator-in-loop hint generator: feeds a "
                         "structural diff (line counts, trailing-newline mismatch, "
                         "first-difference position) into the retry prompt "
                         "instead of just the truncated stderr.")
    ap.add_argument("--no-rag", action="store_true",
                    help="Skip RAG entirely; the prompt only contains "
                         "SLIM_HEADER + the task. Useful for diagnosing what the "
                         "fine-tuned model knows on its own before adding seeds.")
    ap.add_argument("--paren-balance", action="store_true",
                    help="Before each interpreter submission, run the paren "
                         "auto-balancer: if the code is unbalanced by ±1-2 closing "
                         "parens, try the balanced variant. Cheap fix for the "
                         "model's recurring nesting-count slips.")
    ap.add_argument("--python-local", default="qwen2.5-coder:7b")
    ap.add_argument("--cloud-model", default="claude-sonnet-4-6")
    ap.add_argument("--out", default=str(REPO / "benchmark" / "stream_c_results.json"))
    ap.add_argument("--skip-cloud", action="store_true",
                    help="Skip cloud comparison (saves $; use for offline runs)")
    args = ap.parse_args()

    tasks = json.loads(Path(args.tasks).read_text())
    print(f"Loaded {len(tasks)} real tooling tasks")
    print(f"Sigil model:        {args.sigil_model}")
    print(f"Python local model: {args.python_local}")
    print(f"Cloud model:        {args.cloud_model if not args.skip_cloud else '(skipped)'}\n")

    print("Loading RAG index...")
    index = rag.load_index()
    print(f"  {index['count']} entries\n")

    rows = []
    aggregates = {"local_sigil": {"pass":0,"sec":0,"wh":0,"cost":0},
                  "local_python": {"pass":0,"sec":0,"wh":0,"cost":0}}
    if not args.skip_cloud:
        aggregates[f"cloud_{args.cloud_model}"] = {"pass":0,"sec":0,"wh":0,"cost":0}

    for i, t in enumerate(tasks, 1):
        print(f"[{i:2}/{len(tasks)}] {t['id']}")
        a = eval_task_local_sigil(t, args.sigil_model, index,
                                  max_attempts=args.max_attempts,
                                  fallback_model=args.sigil_fallback,
                                  fallback_start=args.fallback_start,
                                  fallback_fresh=args.fallback_fresh,
                                  fallback_temp=args.fallback_temp,
                                  validator=args.validator,
                                  no_rag=args.no_rag,
                                  paren_balance=args.paren_balance)
        b = eval_task_local_python(t, args.python_local)
        c = None
        if not args.skip_cloud:
            c = eval_task_cloud_python(t, args.cloud_model)

        for r in [a, b, c]:
            if not r: continue
            k = r["path"]
            aggregates[k]["pass"] += int(r["pass"])
            aggregates[k]["sec"] += r["seconds"]
            aggregates[k]["wh"] += r["wh"]
            aggregates[k]["cost"] += r["cost_usd"]

        print(f"   sigil:  {'P' if a['pass'] else 'F'} ({a['seconds']:.1f}s, {a.get('attempts',1)} attempts)")
        print(f"   python: {'P' if b['pass'] else 'F'} ({b['seconds']:.1f}s)")
        if c: print(f"   cloud:  {'P' if c['pass'] else 'F'} ({c['seconds']:.1f}s, ${c['cost_usd']:.4f})")

        rows.append({"id": t["id"], "category": t.get("source",""),
                     "sigil": a, "python_local": b, "cloud": c})

    print(f"\n=== AGGREGATE ({len(tasks)} tasks) ===")
    for path, agg in aggregates.items():
        n = len(tasks)
        print(f"  {path:25s} pass {agg['pass']:>2}/{n} | "
              f"avg {agg['sec']/n:5.2f}s | "
              f"total Wh {agg['wh']:.3f} | "
              f"total $ {agg['cost']:.4f}")

    out_data = {"sigil_model": args.sigil_model,
                "python_local_model": args.python_local,
                "cloud_model": args.cloud_model if not args.skip_cloud else None,
                "n_tasks": len(tasks),
                "aggregates": aggregates,
                "tasks": rows}
    Path(args.out).write_text(json.dumps(out_data, indent=2))
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
