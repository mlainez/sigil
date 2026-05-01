# Agentic harness + comparison test suite — plan

**Status:** plan, awaiting confirmation before implementation.
**Goal:** quantify whether delegating tooling-style code generation from a cloud LLM to the local Sigil ensemble saves meaningful cost (tokens, $, Wh) without hurting task success rate, on **multi-step agentic tasks** that mirror real tool-use workloads.

This plan is the next phase after Phase 14 (philosophy retrospective). The Phase 13 result — local Sigil ensemble at 92% of Sonnet on isolated tooling tasks — does not directly imply a cost win when those tasks are embedded in an agentic flow. The agentic question is different: in a multi-step "plan → tool → inspect → tool → synthesize" loop, **which tool calls are economical to delegate and which are not?**

---

## 1. The hypothesis to test

**Claim:** for agentic tasks where the cloud LLM's work is dominated by writing-and-running tools over data (parsing logs, filtering CSVs, regex extraction, format conversion), delegating tool-code-generation to a local Sigil model **saves at least 30% of cloud-model tokens with < 5% accuracy drop on a representative suite of 25-40 multi-step tasks**.

If this holds, the local Sigil work is *worth it* economically — not as a Sonnet replacement, but as a Sonnet *cost-reduction layer*. If the saving is < 30% or accuracy drops > 5%, the local layer doesn't justify the complexity for general agentic use, even if the isolated benchmark numbers are strong.

The exact thresholds are tuneable; what matters is publishing them in advance, then measuring against them.

## 2. Architectures to compare

Four configurations, each measured on the same task suite with the same input data.

### Path A: Cloud-only (baseline)
- **Orchestrator**: Sonnet
- **Tool generation**: Sonnet (writes Python)
- **Tool execution**: local Python interpreter, output captured
- **Synthesizer**: Sonnet (reads tool output, drafts answer)
- **Cost dominator**: Sonnet input/output tokens for everything

### Path B: Hybrid (the value claim)
- **Orchestrator**: Sonnet (plans, decides what tools to invoke, synthesizes)
- **Tool generation**: local Sigil ensemble (`qwen-sigil-v2:7b` → `phi-sigil-v1:14b` fallback)
- **Tool execution**: local `vm.exe` running the generated Sigil
- **Synthesizer**: Sonnet (reads tool output, drafts answer)
- **Cost dominator**: still Sonnet, but on shorter prompts (no "write me a Python program" round-trip)

### Path C: Pure local
- **Orchestrator**: local model (qwen-sigil-v2 or qwen2.5-coder:7b in instruct mode)
- **Tool generation**: same local Sigil ensemble
- **Tool execution**: local `vm.exe`
- **Synthesizer**: local model
- **Cost dominator**: zero $ marginal cost; Wh dominator. The accuracy upper-bound here is what we measured in Phase 13 (~83% on isolated tasks), so we expect this to be the lowest-accuracy path.

### Path D (optional, if budget allows): Sonnet-only-tools
- Like Path A, but Sonnet writes Sigil instead of Python.
- Useful as a **control** to separate "delegation saves tokens" from "Sigil itself produces shorter tool code than Python."

The headline comparison is **A vs B**. C is an asymptote (zero $); D is a control.

## 3. The task suite — design constraints

We need tasks that are:

1. **Multi-step**: the model has to decide *what to do*, do it, look at the result, possibly do another step. Single-shot tasks would not exercise the orchestration layer that Path B compresses.
2. **Tooling-heavy**: the work is dominated by parsing/filtering/transforming data, not by abstract reasoning. Tasks where 80% is reasoning aren't where the local layer pays off — we want to measure the regime where it does.
3. **Real, not synthetic**: mirror real shell-tooling and data-wrangling shapes. Inputs are real logs / CSVs / file listings, not toy examples.
4. **Verifiable**: each task has a reference answer or a rubric (regex match, set equality, file-line equality) that is **mechanically checkable**, not LLM-judged. LLM-judging would inflate measurement variance.

### Concrete task families (target: 30-40 total tasks, 4-7 per family)

| Family | Example task |
|---|---|
| **Log analysis** | "Find the IP address that issued the most failed (4xx/5xx) requests in this 10K-line nginx log; print IP and count." |
| **CSV/TSV transformation** | "From this 500-row CSV of transactions, output the top 5 categories by total spend, formatted as 'CATEGORY: $TOTAL'." |
| **Code-corpus mining** | "From this directory of 50 Python files, list every function whose name starts with `test_` and which doesn't import pytest. Output as `path:function_name`." |
| **JSON wrangling** | "Given this nested JSON object representing a Slack export, extract every message containing 'urgent', sorted by timestamp, formatted as 'YYYY-MM-DD HH:MM <user>: <text>'." |
| **Format conversion** | "Convert this man-page output to a JSON object with keys NAME / SYNOPSIS / DESCRIPTION / OPTIONS, where OPTIONS is an array of {flag, description} pairs." |
| **Multi-step pipelines** | "From this 1-week server log: bucket events by hour, find the hour with peak ERROR rate, then print the 10 distinct error messages from that hour ordered by frequency." |
| **Validation / extraction** | "Given this list of strings, classify each as 'email', 'url', 'ipv4', 'ipv6', or 'none'. Print 'STRING -> CLASS', one per line." |

Each family stresses a different mix of: pattern matching, aggregation, sorting, formatting, multi-stage filtering.

### Task spec format

```json
{
  "id": "log_top_ip_4xx",
  "family": "log_analysis",
  "goal": "Find the IP address that issued the most 4xx-status requests; print 'IP\tCOUNT'.",
  "inputs": [{"name": "access.log", "path": "data/agent_suite/access_10k.log"}],
  "max_steps": 8,
  "verification": {
    "type": "exact_stdout",
    "value": "192.168.1.42\t1283\n"
  },
  "tags": ["regex", "frequency", "filter", "real_log"]
}
```

For tasks where the answer has multiple valid forms, use a `rubric` verifier instead of `exact_stdout` — but keep it mechanical (regex/set/length checks), never LLM-judged.

## 4. The harness

### High level

```
+-------------------------+
|     Task Spec           |
|  goal + input files     |
+-----------+-------------+
            |
            v
+---------------------------+
|   Orchestrator LLM        |   Path A,B,D: Sonnet
|   (plans + synthesizes)   |   Path C:    qwen-sigil-v2 / qwen2.5-coder
+---+---------+----+--------+
    |         |    |
    | tool    | tool   ... up to N steps
    | call    | call
    v         v    v
+---------------------------+
|   Tool generator + runtime|   Path A:    Sonnet writes Python; subprocess
|                           |   Path B:    qwen-sigil ensemble writes Sigil; vm.exe
|                           |   Path C:    same as B
|                           |   Path D:    Sonnet writes Sigil; vm.exe
+-----------+---------------+
            |
            v
        tool output -> back to orchestrator
            |
            v
+---------------------------+
|   Final answer            |
+---------------------------+
```

The orchestrator implements an MCP-style or direct-tool-use loop. We use Anthropic's tool-use API for Sonnet paths so we can measure cloud tokens cleanly.

### Tool definitions

For Sonnet we expose a single tool, `run_tool`:

```python
{
  "name": "run_tool",
  "description": "Generate and run a small program to process the supplied input data. Return its stdout. Use this whenever the task requires deterministic data processing (filtering, parsing, counting, formatting). Avoid using it for pure reasoning.",
  "input_schema": {
    "type": "object",
    "properties": {
      "task_description": {"type": "string", "description": "One-sentence description of what the program should do."},
      "input_files": {"type": "array", "items": {"type": "string"}, "description": "File paths from the available inputs."},
      "expected_output_shape": {"type": "string", "description": "What the stdout should look like."}
    },
    "required": ["task_description", "input_files", "expected_output_shape"]
  }
}
```

Internally:
- **Path A**: `run_tool` → Sonnet generates a Python program inline (subagent call), executes, returns stdout. Token cost is the inner generation prompt.
- **Path B**: `run_tool` → local Sigil ensemble generates Sigil program (no cloud round-trip for code), `vm.exe` executes, returns stdout. The cloud sees only the **stdout** as the tool result.
- **Path D**: `run_tool` → Sonnet generates Sigil program, `vm.exe` executes, returns stdout. Same accounting as A but with Sigil tool code instead of Python.

The token-saving claim is straightforward in this framing: Path B's `run_tool` calls don't include "write me 30 lines of code" in the cloud's output budget — only the brief task spec in the input.

### Token accounting (the most-important measurement detail)

For each path, per task, log:

```
{
  "input_tokens_cloud":     1842,   # accumulated across all turns
  "output_tokens_cloud":    312,    # accumulated across all turns
  "local_inference_seconds": 14.2,  # accumulated
  "wh_local":               0.71,
  "$_cloud":                0.0064,
  "tool_calls":             3,
  "tool_failures":          0,
  "wall_seconds":           18.3,
  "passed":                 true,
  "answer":                 "...",
}
```

Aggregate across the suite. The headline numbers are:
- **$ per task (mean)**, with std-dev
- **Tokens per task (mean)**, broken down input/output
- **Pass rate**
- **Wh per task (mean)**

### Anthropic SDK specifics

- Use `claude-sonnet-4-6` for Path A/B/D. Same model for fair comparison.
- **Enable prompt caching** on the system prompt + tool schema. This affects the token math significantly for repeated tasks; we want both *with* and *without* cache numbers to make the comparison fair (cloud-only also benefits from caching).
- Use the official Anthropic Python SDK; report cache-hit / cache-miss tokens separately.
- Set temperature 0 for the orchestrator (deterministic plan); temperature 0 for Sonnet's Python generation; the local Sigil ensemble uses the v3.1-stable retry ramp from `eval_real_tooling.py`.

### Local execution sandboxing

Tool execution (Sigil and Python) runs in `/tmp` with a 30-second timeout, no network access in the test suite (use only the supplied input files), and stdin redirected from `/dev/null`. Programs that write to disk write to a per-task temp dir.

## 5. Implementation phases

### Phase A — Task suite (estimated: 6-10 hours)
- Design the 30-40 task specs (drawing from the families above).
- Generate or curate the input data files (real logs, real CSVs, etc.).
- Verify each task by writing a Python reference and confirming the expected output is achievable.
- Write a JSON validator for the spec format.
- Output: `benchmark/agent_suite/` directory with task JSONs and input data files.

### Phase B — Harness (estimated: 12-16 hours)
- Write the orchestrator driver (Python). Use the Anthropic SDK with prompt caching enabled.
- Implement the four paths (A, B, C, optional D) as configurable variants of the same driver.
- Wire the local Sigil ensemble path: same `eval_real_tooling.py` plumbing for code-gen + retry, but called as a sub-procedure for each tool invocation.
- Implement token accounting (cache-aware).
- Implement the verifiers (exact_stdout, regex, set-equality).
- Output: `benchmark/agent_harness.py` that takes `(task_spec, path_config) → result_record`.

### Phase C — Measurement (estimated: 4-6 hours wall, mostly waiting)
- Run all 30-40 tasks × 4 paths = 120-160 task-runs.
- Cloud paths: bound the budget with a $ ceiling per task (e.g., $0.50 hard stop; tasks that exceed are recorded as "budget exceeded" and counted as failures).
- Local paths: bound with a wall-clock ceiling (60s per task).
- Re-run any task with non-deterministic outcome 3x to measure variance.
- Output: `benchmark/agent_suite_results.json` with per-task records and the aggregate.

### Phase D — Analysis and writeup (estimated: 4-6 hours)
- Compute the headline numbers: $ per task, tokens per task, pass rate, Wh per task.
- Per-family breakdown: which families show the largest savings? Which show none?
- Threshold check: does Path B clear "30% saving with <5% accuracy drop" vs Path A?
- Decision matrix: when is local delegation a win, when is it not?
- Write up as `papers/AGENTIC_HARNESS_RESULTS.md` (numbers + per-family breakdown + the decision rules).
- If hypothesis holds: update README with the agentic claim and a one-line summary of the cost saving.
- If hypothesis fails: write up *why*; the failure mode is information.

**Total effort:** 26-38 hours of focused work. Most of it is task design and harness plumbing; the actual measurement is fast.

## 6. Risks and decision points

### Risk 1: Tasks may not be "tooling-heavy" enough
If the suite is dominated by reasoning-heavy tasks where the model could plausibly answer without tool use, Path A and Path B will look similar and the saving will be invisible. We should explicitly weight the suite toward tooling-dominant tasks (60%+ of the work in tool calls).

**Mitigation:** During Phase A, profile task complexity by counting reference-tool-output bytes vs reference-final-answer bytes. Tasks where tool output is >5x final answer length are tooling-dominant. Aim for 25 of 35 tasks in this category.

### Risk 2: Local tool failures cascade
If the local Sigil ensemble fails on a tool call, the orchestrator needs to retry, which costs cloud tokens. If failures are common, Path B could end up *more* expensive than Path A.

**Mitigation:** Track tool failure rate per path. If Path B's tool failure rate > 15%, the saving claim is moot until we improve generation reliability. The Phase 13 result of 25/30 on isolated tasks (83%) is below the 85% threshold this would need; the agentic suite may show similar.

### Risk 3: Caching makes Path A look cheaper than it is
Sonnet's prompt caching can dramatically reduce repeated-prompt costs. The "true" comparison should be cache-aware: same caching strategy for both paths.

**Mitigation:** Run both paths with caching enabled, report both *uncached-equivalent* and *as-cached* numbers.

### Risk 4: The cost saving might not justify the complexity
Even at 30% saving, if the absolute cost of Path A is already small ($0.10/task), the operational complexity of maintaining the local layer (model files, RAG index, retraining) might not be worth it.

**Mitigation:** Frame the value claim in two parts:
1. **Cost**: $/task savings (the headline).
2. **Confidentiality**: Path B sends *only the stdout* of tool calls to the cloud, never the input data. For data-residency-constrained workflows, that's a separate value claim independent of cost. Reference `papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`.

### Decision point at end of Phase B
Before running the full Phase C measurement (which spends $ on cloud calls), do a **dry run on 5 tasks** to verify the harness end-to-end and to estimate the per-task cost. If the per-task cloud cost is implausible (e.g., > $0.50 for what should be a 5-step task), debug before committing the full run.

## 7. What success looks like

If at the end we can publish (in `papers/AGENTIC_HARNESS_RESULTS.md`):

> "On a 35-task agentic suite, delegating tool generation to a local Sigil ensemble (Qwen-Sigil-7B + Phi-Sigil-14B) reduces Sonnet token consumption by **N%** with **M%** task pass rate, vs **K%** pass rate for cloud-only. Per-task $ cost drops from $X.XX to $Y.YY. Confidentiality bonus: tool inputs never leave the host; only tool outputs (stdout) reach the cloud."

…then the project has a measurable, defensible value claim that goes beyond "the language is internally consistent" and "the local model gets 92% on isolated tasks." It connects the engineering to the dollar amount someone would save by deploying it.

If the saving is < 10%, the honest writeup is also valuable: it tells future researchers that local-tool delegation, *at this model size and data scale*, doesn't pay for itself in pure agentic settings — only in confidentiality-constrained ones.

## 8. Open questions before implementation

1. **Task suite size**: 30 or 40? Variance vs runtime trade-off. Recommend 35.
2. **Real input data**: should we curate from real public datasets (Apache logs, public CSVs from data.gov) or synthesise? Recommend curate, with attribution.
3. **Path D (Sonnet writes Sigil)**: include or skip? Useful control but doubles measurement runs. Recommend skip in v1; add later if Path A vs B is ambiguous.
4. **Multi-turn budget**: max_steps per task. 8 is generous; some tasks may need more. Recommend 12 with budget escalation logged.
5. **Failure-mode taxonomy**: when Path B fails, is it (a) tool generation produced wrong code, (b) tool ran but produced wrong output, (c) orchestrator misused the tool? We should log this distinction; it shapes the next iteration's work.
