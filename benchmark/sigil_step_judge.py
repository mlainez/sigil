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

Apply these GENERIC reasoning principles to whatever the step happens to
be about. The principles are domain-agnostic; the examples below use
abstract placeholder data so you don't anchor to a particular task.

PRINCIPLES (check in order):

  P1. NUMERIC LIMIT. If the step states a numeric limit (e.g. "top N",
      "first N", "N most ...", "at most N"), COUNT the output lines.
      Answer NO when the count exceeds the limit.

  P2. ORDERING. If the step asks for a sort, ORDER, ascending, or
      descending — verify the relevant column is monotonic in the right
      direction. Answer NO when it isn't. If the step does NOT mention
      ordering, never mark unsorted output as wrong.

  P3. TRANSFORMATION HAPPENED. If the step asks for a COMPUTED value
      (sum, count, total, average, max, min, cumulative, frequency,
      duration, length, mean, median), the output must differ from the
      input in a way consistent with that computation. Answer NO when
      the output equals the input verbatim — that means the transform
      was not applied.

  P4. FILTERING APPLIED. If the step says "filter", "keep only", "where
      ...", "matching ...", the output should be a strict subset of the
      input that satisfies the predicate. Answer NO when output rows
      visibly violate the predicate.

  P5. STRUCTURAL CHANGE. If the step says "skip header", "drop first
      line", "remove the header" — the first output line should not look
      like a header (i.e. should not be the same as the input's first
      line). If "extract X", "parse X", "select X", verify X is in the
      output and unrelated material is gone.

  P6. FORMAT MATCH. If the step prescribes a literal format (delimiter,
      separator, prefix, wrapper, e.g. "comma-separated", "TAB-separated",
      "as 'KEY VALUE'", "wrap each in <li>...</li>"), spot-check the
      first row matches that format.

  P7. DEFAULT YES. If none of P1–P6 raise a problem, the output
      plausibly matches the description: answer YES.

CRITICAL — do NOT invent constraints the description does not state:
  - "Extract all X" / "Find all X" / "Print every X" means keep all
    occurrences INCLUDING duplicates. Duplicates are NEVER a P4 violation.
    Only flag duplicates if the step literally says "unique", "deduplicate",
    "distinct", "no duplicates", or "remove duplicates".
  - VALIDITY (e.g. "real" values, semantically valid IPs, well-formed
    URLs) is fine unless the step says "valid", "well-formed", or gives
    a constraint. The model is allowed to emit data that the upstream
    contained.
  - SUBSEQUENT STEPS are not your concern. Judge only this step against
    its own description.
  - Your reason MUST describe what the OUTPUT actually contains. Never
    say "output is empty" if it has non-whitespace characters.

Reply on ONE line, exactly:
YES <one-clause reason>
or
NO <one-clause reason>

EXAMPLES (synthetic, domain-agnostic):

STEP: Extract all FOO tokens from the input
OUTPUT: foo-1
foo-2
foo-1
JUDGE: YES three FOO tokens; duplicates are fine since step did not ask for unique

STEP: Print only the top 3 entries
OUTPUT: aa 100
bb 80
cc 60
dd 40
ee 20
JUDGE: NO P1: 5 lines but step asked for top 3

STEP: Print the running running-total after each value
INPUT (for context): 7
2
5
OUTPUT: 7
2
5
JUDGE: NO P3: output equals input, the running-total was not applied

STEP: Sort lines descending by the WIDGET column (column 2)
OUTPUT: alpha 5
beta 25
gamma 12
delta 50
JUDGE: NO P2: column-2 values 5,25,12,50 are not descending

STEP: Sort lines descending by score
OUTPUT: alpha 50
gamma 25
beta 5
JUDGE: YES P2: column-2 values 50,25,5 are descending

STEP: Drop the header row and print KEY|VALUE pairs
OUTPUT: KEY|VALUE
red|1
blue|2
JUDGE: NO P5: first line "KEY|VALUE" is the header that should have been dropped

STEP: Drop the header row and print KEY|VALUE pairs
OUTPUT: red|1
blue|2
green|3
JUDGE: YES P5/P6: header dropped, KEY|VALUE format consistent

STEP: Filter lines where the second field is greater than 10
OUTPUT: alpha 5
beta 25
gamma 12
JUDGE: NO P4: "alpha 5" violates the predicate (5 is not greater than 10)

STEP: Compute the sum grouped by the first column, print KEY TOTAL
INPUT (for context): a 5
a 3
b 4
OUTPUT: a 8
b 4
JUDGE: YES P3: per-key totals computed (a=5+3=8, b=4)"""


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
    m = _re.search(r"\bcolumn\s+(\d+)\b", d)
    if m:
        return int(m.group(1))
    m = _re.search(r"\bcol\s*(\d+)\b", d)
    if m:
        return int(m.group(1))
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
    # Smoke test cases. Two pools:
    #   IN-DOMAIN: shapes that resemble our agent_tasks corpus (sanity: judge
    #     still works on what we built it for).
    #   OUT-OF-DOMAIN: shapes the harness has NEVER seen — different domains
    #     (chemistry, finance, geocoding, code metrics, log shapes from other
    #     ecosystems). If the judge generalizes, OOD performance should match
    #     in-domain. If the judge is overfit to the corpus, OOD will degrade.
    in_domain = [
        # (description, output, upstream, expected_ok, label)
        ("Extract all IPv4 dotted-quad addresses",
         "10.0.0.1\n192.168.1.1\n",
         "garbage 10.0.0.1 more 192.168.1.1",
         True, "valid IPs"),
        ("Skip the header and print category,amount per row",
         "food,12\nrent,800\ntransit,45\n",
         "category,amount\nfood,12\nrent,800\ntransit,45\n",
         True, "header removed, format correct"),
        ("Print only the top 3 lines",
         "a 100\nb 80\nc 60\n",
         "a 100\nb 80\nc 60\nd 40\ne 20\n",
         True, "exactly 3 lines"),
        ("Sort lines descending by the second whitespace-separated number",
         "spam 50\nham 30\nfoo 10\n",
         "foo 10\nspam 50\nham 30\n",
         True, "correctly sorted descending"),
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
    ]
    ood = [
        # ---- Generalization: shapes/domains not in our corpus ----
        # Chemistry: extract atomic symbols from a formula
        ("Extract each element symbol followed by its count from the formula",
         "C 6\nH 12\nO 6\n",
         "C6H12O6",
         True, "OOD chemistry: element/count pairs"),
        # Finance: filter trades above threshold
        ("Filter trades with notional value greater than 1000000",
         "AAPL 1500000\nGOOG 2300000\nMSFT 800000\n",
         "AAPL 1500000\nGOOG 2300000\nMSFT 800000\nINTC 50000\n",
         False, "OOD finance: 'MSFT 800000' violates predicate"),
        # Code metrics: cyclomatic complexity per function, take top 5
        ("Print the top 5 functions by cyclomatic complexity",
         "parse 14\nrender 12\nvalidate 11\ndispatch 9\ncache 8\nlookup 6\n",
         "",
         False, "OOD code metrics: 6 lines but step asked for top 5"),
        # Geocoding: latitude/longitude pairs sorted ascending by lat
        ("Sort entries ascending by latitude (column 2)",
         "Quito -0.18\nNairobi -1.28\nLima -12.04\nWellington -41.29\n",
         "",
         False, "OOD geocoding: not ascending: -0.18, -1.28, ... is descending"),
        # Geocoding ascending properly
        ("Sort entries ascending by latitude (column 2)",
         "Wellington -41.29\nLima -12.04\nNairobi -1.28\nQuito -0.18\n",
         "",
         True, "OOD geocoding: correctly ascending"),
        # Genome: count of each base
        ("Count each nucleotide base and emit BASE COUNT per line",
         "A 4\nC 3\nG 2\nT 4\n",
         "ACGTACGTAACGTAATCGT",
         True, "OOD genome: per-base counts"),
        # Genome where transform NOT applied
        ("Count each nucleotide base and emit BASE COUNT per line",
         "ACGT\nACGT\nAACGTAATCGT\n",
         "ACGT\nACGT\nAACGTAATCGT\n",
         False, "OOD genome: output equals input, no count applied"),
        # Heisting: emit the SHA hashes from a manifest, no order constraint
        ("Extract every SHA-256 hash from the manifest",
         "a3b1c4d5e6f78901234567890abcdef0123456789abcdef0123456789abcdef0\n"
         "ffeeddccbbaa99887766554433221100ffeeddccbbaa9988776655443322110a\n",
         "",
         True, "OOD: 64-hex hashes, no order asked"),
        # Order NOT asked, output is unsorted — should still be YES
        ("Extract every SHA-256 hash from the manifest",
         "ffeeddccbbaa99887766554433221100ffeeddccbbaa9988776655443322110a\n"
         "a3b1c4d5e6f78901234567890abcdef0123456789abcdef0123456789abcdef0\n",
         "",
         True, "OOD: unsorted output where no sort was asked (P2 must not fire)"),
        # Time-series: trim leading whitespace and parse epoch
        ("Convert each ISO timestamp to a Unix epoch second integer",
         "1714521600\n1714525200\n1714528800\n",
         "2024-05-01T00:00:00Z\n2024-05-01T01:00:00Z\n2024-05-01T02:00:00Z\n",
         True, "OOD time: epochs computed"),
        # Time-series transform NOT applied
        ("Convert each ISO timestamp to a Unix epoch second integer",
         "2024-05-01T00:00:00Z\n2024-05-01T01:00:00Z\n",
         "2024-05-01T00:00:00Z\n2024-05-01T01:00:00Z\n",
         False, "OOD time: output equals input, no conversion"),
        # Format wrap: wrap each line in <li>...</li>
        ("Wrap each input line in <li>...</li> tags",
         "<li>apple</li>\n<li>banana</li>\n<li>cherry</li>\n",
         "apple\nbanana\ncherry\n",
         True, "OOD format: HTML li wrap"),
        # Format wrap NOT applied
        ("Wrap each input line in <li>...</li> tags",
         "apple\nbanana\ncherry\n",
         "apple\nbanana\ncherry\n",
         False, "OOD format: wrap not applied"),
        # Empty handling — judge should not flag empty (handled upstream)
        ("Extract all phone numbers",
         "",
         "no phones here",
         True, "empty stdout passthrough"),
    ]
    cases = [(*c, "in-domain") for c in in_domain] + [(*c, "OOD") for c in ood]
    print(f"Running {len(cases)} judge cases against {JUDGE_MODEL}\n")
    correct_in = correct_ood = total_in = total_ood = 0
    for desc, out, upstream, expected, label, bucket in cases:
        v = judge_step(desc, out, upstream)
        match = v.ok == expected
        ok_icon = "+" if match else "-"
        if bucket == "in-domain":
            total_in += 1
            if match:
                correct_in += 1
        else:
            total_ood += 1
            if match:
                correct_ood += 1
        print(f"[{ok_icon}] {bucket:9s} {label}")
        print(f"    desc:    {desc[:80]}")
        print(f"    output:  {repr(out[:80])}")
        print(f"    expect:  {'YES' if expected else 'NO '}    got: {'YES' if v.ok else 'NO '}")
        print(f"    reason:  {v.reason}")
        print()
    print(f"== in-domain {correct_in}/{total_in}  |  OOD {correct_ood}/{total_ood} ==")
