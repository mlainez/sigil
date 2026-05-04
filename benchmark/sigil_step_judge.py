#!/usr/bin/env python3
"""NH2 Tier B: 3B semantic step-judge for chained Sigil pipelines.

Tier A (sigil_name_validator) catches *syntactic* problems: wrong language,
unknown call-names, hallucinated builtins. It runs before execution.

Tier B catches *semantic* problems in intermediate-step output: the program
ran, parsed, emitted text — but the shape doesn't match what the step
description asked for. Examples observed in NH5 Path C failures:

  step: "Print the running cumulative sum after each value"
  got:  "5\\n3\\n8\\n2\\n"     # raw values, not cumulative

  step: "Print only the top 3 lines"
  got:  "/tmp/a 16384\\n.../tmp/b 512\\n"   # 6 lines, kept everything

  step: "Extract IPv4 dotted-quads"
  got:  "10.0.0.1\\n999.999.999.999\\n"     # included an invalid quad

The judge runs a small local model (qwen2.5-coder:3b at temp=0) AFTER the
Sigil step succeeds (ok=True, non-empty stdout) and BEFORE threading to the
next step. If the judge says NO with a reason, path_c retries the step
with the reason as a hint.

Design constraints:
- Conservative: prefer YES when unsure. False NO wastes a retry; false YES
  has no harm (next step will fail and surface the problem).
- Cheap: target <2s per call. Local 3B Q4_K_M is ~1s on the 7800 XT.
- Non-blocking: if the judge times out or errors, treat as YES (don't kill
  the pipeline).
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass


JUDGE_MODEL = os.environ.get("SIGIL_JUDGE_MODEL", "qwen2.5-coder:3b")
JUDGE_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
JUDGE_TIMEOUT = int(os.environ.get("SIGIL_JUDGE_TIMEOUT", "20"))
JUDGE_MAX_OUTPUT_CHARS = 600  # truncate stdout sample we send to the judge


JUDGE_SYSTEM = """You judge whether a single data-transform step produced
the right SHAPE of output. You are NOT checking grammar or syntax — only
whether the OUTPUT matches what the STEP DESCRIPTION asks for.

Before answering, mentally check these in order:
  1. If the step says "top N" or "first N" or "N most" — COUNT the output lines.
     If the count is greater than N, answer NO.
  2. If the step says "sort descending" — check that the relevant column's
     values go big -> small as you read down. If they go small -> big or are
     unordered, answer NO.
  3. If the step says "sort ascending" — values should go small -> big.
  4. If the step asks for a computed value (sum, count, total, average, max,
     min, cumulative) — the output must NOT equal the input. If it does,
     answer NO.
  5. If the step says "skip header" — the first line of the output should not
     look like a header (column names like 'name', 'category', 'amount').
  6. Otherwise, if the output plausibly matches: answer YES.

Reply on ONE line, exactly:
YES <one-clause reason>
or
NO <one-clause reason>

Examples:

STEP: Extract all IPv4 dotted-quad addresses
OUTPUT: 10.0.0.1
192.168.1.1
JUDGE: YES looks like dotted quads

STEP: Print only the top 3 lines
OUTPUT: a 100
b 80
c 60
d 40
JUDGE: NO 4 lines present but step asked for top 3

STEP: Print only the top 3 lines
OUTPUT: a 100
b 80
c 60
d 40
e 20
f 10
JUDGE: NO 6 lines present but step asked for top 3

STEP: Print the running cumulative sum after each value
INPUT (for context, what the step received as $0): 5
3
8
OUTPUT: 5
3
8
JUDGE: NO output equals input, no cumulation applied

STEP: Sort lines descending by the second whitespace-separated number
OUTPUT: alpha 5.0
beta 25.5
delta 12.3
epsilon 50.0
JUDGE: NO column-2 values are 5.0, 25.5, 12.3, 50.0 — not descending

STEP: Sort lines descending by count
OUTPUT: spam 50
ham 30
foo 10
JUDGE: YES 50, 30, 10 is descending

STEP: Sort lines descending by the second whitespace-separated number
OUTPUT: epsilon 50.0
beta 25.5
delta 12.3
alpha 5.0
JUDGE: YES column-2 values 50.0, 25.5, 12.3, 5.0 are descending

STEP: Skip the header and print category,amount per row
OUTPUT: food,12
rent,800
JUDGE: YES header removed, format correct

STEP: Skip the header and print category,amount per row
OUTPUT: category,amount
food,12
rent,800
JUDGE: NO first line is the header, step said skip it"""


JUDGE_PROMPT = """STEP: {desc}
{input_block}OUTPUT:
{output}
JUDGE:"""


@dataclass
class JudgeVerdict:
    ok: bool
    reason: str
    raw: str  # raw model response, for debugging


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"\n... [truncated, {len(s)} chars total]"


# ----------------------------------------------------------------------------
# Deterministic pre-checks.  The 3B model is unreliable on counting and
# ordering — but those are exactly the patterns Python can verify directly
# from the description's structure.  We run these BEFORE the 3B judge and
# return immediately on a confident NO.  YES from the pre-check just means
# "I have nothing to say here" — we then fall through to the 3B for semantic
# judgment.
# ----------------------------------------------------------------------------

import re as _re


def _topn_target(desc: str) -> int | None:
    """Extract N from 'top N', 'first N', 'N most ...', etc."""
    m = _re.search(r"\btop\s+(\d+)\b", desc, _re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = _re.search(r"\bfirst\s+(\d+)\b", desc, _re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = _re.search(r"\b(\d+)\s+(?:most|largest|smallest|highest|lowest|biggest)\b",
                   desc, _re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _sort_direction(desc: str) -> str | None:
    """Return 'asc', 'desc', or None."""
    d = desc.lower()
    if "descending" in d or "desc " in d or " desc." in d:
        return "desc"
    if "ascending" in d or "asc " in d or " asc." in d:
        return "asc"
    return None


def _sort_column_index(desc: str) -> int | None:
    """1-based index, only when explicit and unambiguous."""
    d = desc.lower()
    if "second" in d:
        return 2
    if "third" in d:
        return 3
    if "first" in d and "field" in d:
        return 1
    return None


def _try_float(tok: str) -> float | None:
    try:
        return float(tok)
    except ValueError:
        return None


def deterministic_check(description: str, output: str) -> JudgeVerdict | None:
    """Return a JudgeVerdict if we can decide deterministically, else None.

    Strategy: only emit NO when we are *highly confident*. If even one
    interpretation could make the output correct, return None and let the
    3B judge decide.
    """
    desc = description.strip()
    out_lines = [ln for ln in output.rstrip("\n").split("\n") if ln.strip()]

    # ---- Top-N line count ----
    n = _topn_target(desc)
    if n is not None and len(out_lines) > n:
        return JudgeVerdict(
            ok=False,
            reason=f"step asks for top {n} but output has {len(out_lines)} lines",
            raw="precheck:topn",
        )

    # ---- Sort order check (only when we know direction + column) ----
    direction = _sort_direction(desc)
    col = _sort_column_index(desc)
    sort_verified_correct = False
    if direction and col and len(out_lines) >= 3:
        vals = []
        for ln in out_lines:
            toks = ln.split()
            if len(toks) < col:
                vals = None
                break
            v = _try_float(toks[col - 1])
            if v is None:
                vals = None
                break
            vals.append(v)
        if vals is not None and len(vals) >= 3:
            asc = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
            desc_ord = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
            if direction == "desc" and not desc_ord:
                return JudgeVerdict(
                    ok=False,
                    reason=f"col-{col} values {vals[:5]} are not sorted descending",
                    raw="precheck:sort",
                )
            if direction == "asc" and not asc:
                return JudgeVerdict(
                    ok=False,
                    reason=f"col-{col} values {vals[:5]} are not sorted ascending",
                    raw="precheck:sort",
                )
            sort_verified_correct = True

    # If the description is structurally simple ("sort by ..." with no
    # additional transform verbs) and the sort verified, short-circuit YES.
    # The 3B model wobbles on monotonicity even when correct, so this
    # avoids spurious NO retries.
    if sort_verified_correct:
        transform_verbs = ("compute", "extract", "format", "convert", "join",
                           "filter", "skip", "remove", "replace", "wrap",
                           "encode", "decode", "parse")
        if not any(v in desc.lower() for v in transform_verbs):
            return JudgeVerdict(
                ok=True,
                reason=f"col-{col} values are correctly sorted {direction}",
                raw="precheck:sort-ok",
            )

    # ---- "Skip the header" check ----
    if _re.search(r"\bskip(?:ping)?\s+(?:the\s+)?header\b", desc, _re.IGNORECASE):
        if out_lines:
            first = out_lines[0].lower().strip()
            # Heuristic: header lines tend to be all-words (no digits, no IPs)
            # AND match common header-token names.
            header_tokens = {"name", "category", "amount", "value", "key", "count",
                             "id", "type", "status", "code", "user", "email", "date",
                             "time", "score", "size", "path", "url", "ip", "host"}
            words = _re.findall(r"[a-z_]+", first)
            if (words and not _re.search(r"\d", first)
                    and any(w in header_tokens for w in words)
                    and len(words) <= 5):
                return JudgeVerdict(
                    ok=False,
                    reason=f"first line '{out_lines[0][:40]}' looks like the header that was supposed to be skipped",
                    raw="precheck:header",
                )

    return None


def judge_step(
    description: str,
    output: str,
    upstream_input: str = "",
    *,
    model: str = JUDGE_MODEL,
    url: str = JUDGE_URL,
    timeout: int = JUDGE_TIMEOUT,
) -> JudgeVerdict:
    """Ask the local judge whether `output` matches what `description` asked for.

    `upstream_input` is the previous step's stdout (or task input for step 0);
    used as context for relative judgments like "running sum" or "filter".
    Pass empty string to omit.

    On timeout, network error, or unparseable response: returns YES (fail-open).
    """
    output = output or ""
    if not output.strip():
        # Empty output is already handled by the existing empty-stdout retry.
        # Don't double-judge.
        return JudgeVerdict(ok=True, reason="empty (handled upstream)", raw="")

    # Deterministic pre-check first — fast, no model call, very precise on
    # counting and ordering. Only returns a verdict when confident (NO);
    # otherwise None and we fall through to the 3B semantic judge.
    pre = deterministic_check(description, output)
    if pre is not None:
        return pre

    input_block = ""
    if upstream_input.strip():
        input_block = (f"INPUT (for context, what the step received as $0):\n"
                       f"{_truncate(upstream_input, 300)}\n")
    prompt = JUDGE_PROMPT.format(
        desc=description.strip(),
        input_block=input_block,
        output=_truncate(output, JUDGE_MAX_OUTPUT_CHARS),
    )

    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "system": JUDGE_SYSTEM,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 80,
            "top_p": 0.9,
            "stop": ["\n\n", "STEP:", "OUTPUT:"],
        },
    }).encode()

    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        raw = (data.get("response") or "").strip()
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        return JudgeVerdict(ok=True, reason=f"judge unavailable ({type(e).__name__})", raw="")

    if not raw:
        return JudgeVerdict(ok=True, reason="judge empty response", raw="")

    first_line = raw.splitlines()[0].strip()
    upper = first_line.upper()
    if upper.startswith("NO"):
        reason = first_line[2:].strip(" :,-")
        return JudgeVerdict(ok=False, reason=reason or "shape mismatch", raw=raw)
    # Default to YES (fail-open): includes "YES ...", any other text, etc.
    reason = first_line[3:].strip(" :,-") if upper.startswith("YES") else first_line
    return JudgeVerdict(ok=True, reason=reason, raw=raw)


# ============================================================================
# Standalone smoke test (run: python sigil_step_judge.py)
# ============================================================================
if __name__ == "__main__":
    cases = [
        # (description, output, upstream, expected_ok, label)
        # ---- True YES (legitimate intermediate outputs) ----
        ("Extract all IPv4 dotted-quad addresses",
         "10.0.0.1\n192.168.1.1\n",
         "garbage 10.0.0.1 more 192.168.1.1",
         True, "valid IPs"),
        ("Skip the header and print category,amount per row",
         "food,12\nrent,800\ntransit,45\n",
         "category,amount\nfood,12\nrent,800\ntransit,45\n",
         True, "header removed, format correct"),
        ("Count occurrences of each unique IP, print IP and count space-separated",
         "10.0.0.1 3\n192.168.1.42 5\n",
         "10.0.0.1\n192.168.1.42\n10.0.0.1\n192.168.1.42\n192.168.1.42\n10.0.0.1\n192.168.1.42\n192.168.1.42\n",
         True, "valid count output"),
        ("Print only the top 3 lines",
         "a 100\nb 80\nc 60\n",
         "a 100\nb 80\nc 60\nd 40\ne 20\n",
         True, "exactly 3 lines"),
        ("Sort lines descending by the second whitespace-separated number",
         "spam 50\nham 30\nfoo 10\n",
         "foo 10\nspam 50\nham 30\n",
         True, "correctly sorted descending"),
        ("Compute the duration in minutes for each HH:MM-HH:MM range",
         "60\n45\n30\n",
         "10:00-11:00\n09:15-10:00\n14:00-14:30\n",
         True, "looks like minutes per range"),
        ("Print each row as a Markdown table row | name | value |",
         "| alpha | 1 |\n| beta | 2 |\n",
         "name\tvalue\nalpha\t1\nbeta\t2\n",
         True, "valid markdown rows"),
        # ---- True NO (caught failures) ----
        ("Print only the top 3 lines",
         "/tmp/a 16384\n/tmp/b 8192\n/tmp/c 4096\n/tmp/d 2048\n/tmp/e 1024\n/tmp/f 512\n",
         "",
         False, "6 lines instead of 3"),
        ("Print the running cumulative sum after each value",
         "5\n3\n8\n2\n4\n",
         "5\n3\n8\n2\n4\n",
         False, "raw values, no cumulation"),
        ("Sort lines descending by the second whitespace-separated number",
         "alpha 5.0\nbeta 25.5\ndelta 12.3\nepsilon 50.0\n",
         "",
         False, "not sorted descending"),
        ("Skip the header and print category,amount per row",
         "category,amount\nfood,12\nrent,800\n",
         "category,amount\nfood,12\nrent,800\n",
         False, "header still present"),
        ("Count occurrences of each unique IP, print IP and count space-separated",
         "10.0.0.1\n192.168.1.42\n10.0.0.1\n",
         "10.0.0.1\n192.168.1.42\n10.0.0.1\n",
         False, "no count column emitted"),
    ]
    print(f"Running {len(cases)} judge cases against {JUDGE_MODEL}\n")
    correct = 0
    for desc, out, upstream, expected, label in cases:
        v = judge_step(desc, out, upstream)
        ok_icon = "+" if (v.ok == expected) else "-"
        if v.ok == expected:
            correct += 1
        print(f"[{ok_icon}] {label}")
        print(f"    desc:    {desc[:80]}")
        print(f"    output:  {repr(out[:80])}")
        print(f"    expect:  {'YES' if expected else 'NO '}    got: {'YES' if v.ok else 'NO '}")
        print(f"    reason:  {v.reason}")
        print()
    print(f"== {correct}/{len(cases)} judgments matched expectation ==")
