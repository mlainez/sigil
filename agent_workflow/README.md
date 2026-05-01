# Routing host-tooling tasks to a local Sigil model

A practical guide to wiring `qwen-sigil:7b` (or any local Sigil-fine-tuned
model) into an agentic AI workflow as the backend for *tooling-script
generation* — short verifiable programs the agent uses to traverse
files, parse logs, transform text, and otherwise act on the host.

The goal is to keep tooling work entirely local — no cloud round-trip
for tasks that the local model can handle competently — while
preserving the option of cloud fallback for hard cases or
non-Sigil-expressible tasks.

## When to route a task to the local Sigil backend

A task is a *good fit* for the local Sigil backend when ALL of the
following hold:

1. **Self-contained.** The task can be expressed as a single Sigil
   program that reads CLI args (or stdin-shaped string) and writes
   stdout. No multi-file edits, no follow-up turns, no context
   threading.
2. **Verifiable.** A sample input and expected output exist, so the
   agent can run the generated program and check the result before
   trusting it.
3. **Within Sigil's stdlib.** The task fits one of the shapes Sigil
   supports natively: file walks, text transforms, log/CSV/JSON
   parsing, output formatting, numeric or scan operations on small
   data.
4. **Latency-tolerant.** The agent can wait 2-15 seconds for
   generation, since local 7B inference is slower than cloud
   frontier inference per call.

A task is a *bad fit* for the local backend (route to cloud instead)
when ANY of the following hold:

1. The task needs to make decisions about architecture, refactoring
   strategy, or API design.
2. The task crosses many files or requires multi-step reasoning over
   a large codebase.
3. The required output is in a language Sigil can't replace (a
   working PyTorch script, a real-time GUI, a network service).
4. Latency must be under 1 second (interactive UX).

The choice is workflow-shaped, not model-quality-shaped. A frontier
cloud model would beat the local Sigil-7B on accuracy for almost any
single task; the local backend wins on cost, energy, privacy, and
batch throughput for tooling-shape work.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Parent Agent (Claude Code, Cursor, custom)                      │
│                                                                  │
│   1. Receives high-level task                                    │
│   2. Decides: local Sigil or cloud LLM?                         │
│      ├─ tooling-shape ───→ local Sigil sub-agent                │
│      └─ otherwise ───────→ cloud LLM directly                   │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  Local Sigil Sub-Agent                                           │
│                                                                  │
│   1. Build prompt: TASK + sample-input + expected-output         │
│   2. Call ollama HTTP: POST /api/generate model=qwen-sigil:7b    │
│   3. Strip fences, get raw Sigil code                            │
│   4. Run interpreter: ./vm.exe code.sigil <args>                 │
│   5. Validate: stdout == expected?                               │
│      ├─ yes → return Sigil program to parent                    │
│      └─ no  → retry (up to N) with stderr/output as hint        │
│   6. After N retries: return failure for parent re-routing      │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  Parent Agent runs the validated Sigil program against real     │
│  data. Local-only at every step. No network egress occurred.    │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Local model serving (ollama)

```bash
# One-time setup (assumes you have a fine-tuned LoRA in benchmark/lora_out_7b/)
ollama pull qwen2.5-coder:7b

# Convert LoRA to GGUF (using llama.cpp)
python3 /path/to/llama.cpp/convert_lora_to_gguf.py \
    --base-model-id Qwen/Qwen2.5-Coder-7B-Instruct \
    --outfile sigil_lora_7b.gguf --outtype f16 \
    benchmark/lora_out_7b

# Build the ollama model
cat > Modelfile.sigil <<'EOF'
FROM qwen2.5-coder:7b
ADAPTER ./sigil_lora_7b.gguf
PARAMETER temperature 0
PARAMETER num_ctx 8192
SYSTEM "You write Sigil programs. Output ONLY raw Sigil code, no markdown, no prose."
EOF
ollama create qwen-sigil:7b -f Modelfile.sigil

# Verify
ollama run qwen-sigil:7b "Print Hello World in Sigil." # → (println "Hello, World!")
```

### 2. Sub-agent definition

Save as `agent_workflow/sigil_subagent.md` and reference from your
parent agent's configuration:

```markdown
---
name: sigil-tooling
description: Generates and validates Sigil programs for host-tooling tasks (file traversal, log parsing, text transforms). Routes to local qwen-sigil:7b — no cloud calls. Use when the task is a single self-contained tooling-shape program with verifiable expected output.
tools: [Bash, Read, Write]
---

You are a Sigil-tooling sub-agent. The user gives you:
- A task description in natural language
- Sample input(s) the program should handle
- Expected output for the sample input

Your job:
1. Construct a Sigil-generation prompt with the task and sample
2. Call the local model: `curl -s http://localhost:11434/api/generate -d {...}`
3. Save the response to a `.sigil` file
4. Run it: `./vm.exe code.sigil <sample_args>`
5. Compare stdout to expected output
6. If match: return the Sigil program path to the parent
7. If mismatch:
   - Capture stderr and the diff
   - Build a retry prompt including the previous attempt and the diagnostic
   - Generate again (up to 4 attempts total)
8. After 4 failures, return `{"status":"failed","reason":"..."}` so
   the parent can route to a cloud model

Never call cloud models. Never make network requests.
```

### 3. Router logic (parent-agent side)

```python
# agent_workflow/router.py
"""Decides whether a task goes to local Sigil or cloud LLM."""

LOCAL_SHAPES = {
    "file_walk", "log_parse", "text_transform", "csv_parse",
    "config_parse", "format_output", "scan_with_state",
    "string_manipulation", "numeric_aggregation",
}

CLOUD_REQUIRED_SHAPES = {
    "multi_file_refactor", "architecture_design", "library_research",
    "interactive_chat", "non_sigil_language",
}


def route_task(task_description: str, latency_budget_seconds: float,
               privacy_required: bool) -> str:
    """Returns 'local' or 'cloud' or 'cloud_required_for_privacy'."""
    if privacy_required:
        # If the task touches sensitive data and Sigil can express it,
        # go local even at accuracy cost.
        shape = classify_shape(task_description)
        if shape in LOCAL_SHAPES:
            return "local"
        else:
            return "cloud_required_for_privacy"  # Caller must decide
                                                  # whether to abort or accept.
    if latency_budget_seconds < 2.0:
        return "cloud"
    shape = classify_shape(task_description)
    if shape in CLOUD_REQUIRED_SHAPES:
        return "cloud"
    if shape in LOCAL_SHAPES:
        return "local"
    return "cloud"  # default: when in doubt, cloud has more capacity


def classify_shape(description: str) -> str:
    """Heuristic — replace with a learned classifier later."""
    desc = description.lower()
    if any(kw in desc for kw in ["walk", "traverse", "find files"]):
        return "file_walk"
    if any(kw in desc for kw in ["log", "grep", "filter lines"]):
        return "log_parse"
    if "csv" in desc or "tsv" in desc:
        return "csv_parse"
    if any(kw in desc for kw in ["transform", "replace", "uppercase"]):
        return "text_transform"
    if any(kw in desc for kw in ["refactor", "redesign", "architecture"]):
        return "multi_file_refactor"
    if any(kw in desc for kw in ["explain", "summarize", "document"]):
        return "interactive_chat"
    return "unknown"
```

### 4. End-to-end worked example

Suppose the parent agent receives:

> *"In `~/projects/`, find all .py files modified in the last 7 days
> and produce a CSV with columns filename, size, mtime. Sort by size
> descending."*

The router classifies this as `file_walk` + `format_output` = local.

The sub-agent generates a Sigil program along these lines:

```lisp
(set root $0)
(set lines (split (process_run "find" [root "-name" "*.py" "-mtime" "-7"
                                        "-printf" "%f|%s|%T@\n"]) "\n"))
(set rows (filter lines (\l (gt (len l) 0))))
(set parsed (map_arr rows (\l (split l "|"))))
(set sorted (sort_by parsed (\p (neg (parse_int (array_get p 1))))))
(println "filename,size,mtime")
(for-each row sorted
  (println (join row ",")))
```

The sub-agent runs it with sample input, validates, and returns the
program. The parent runs it for real against the user's filesystem.

No file paths, no code patterns, no project names ever crossed the
network boundary.

### 5. Failure handling

When the local model can't solve a task within the retry budget, the
sub-agent returns:

```json
{
  "status": "failed",
  "attempts": 4,
  "last_code": "(set ...) ...",
  "last_error": "Runtime error: ...",
  "suggested_route": "cloud"
}
```

The parent agent then decides whether to:
- Re-route to a cloud LLM (loses confidentiality but may be faster
  than further local retries)
- Hand back to the human for manual completion
- Accept the partial result if it's "good enough"

The decision should be informed by the original privacy_required
flag — a task originally marked privacy-sensitive should never
silently fall back to cloud without explicit human consent.

## Performance and cost characteristics (measured)

From the 100-task benchmark in this repository, fine-tuned 7B + RAG
on consumer AMD hardware (RX 7800 XT, 16 GB):

| Metric | Value |
|---|---|
| Average generation latency | 2-5 seconds |
| 1-shot pass rate (synthetic Sigil tasks) | 74% |
| Multi-shot pass rate (up to 4 attempts) | ~85-90% |
| Idle GPU power | ~50 W |
| Inference GPU power | ~180 W |
| Energy per call | ~0.25 Wh |
| Marginal $ cost per call | $0 |

Comparison: Sonnet on the same tasks scored ~95% but at ~$0.005/call,
~1-2 Wh/call, and external data exposure.

## Testing the integration

A simple end-to-end test that exercises the full loop:

```bash
# Start ollama if not running
ollama serve &

# Test sub-agent with a known task
cat > /tmp/test_task.json <<'EOF'
{
  "description": "Take a CSV string in arg0 and a column name in arg1. Print the values from that column for all data rows, one per line.",
  "args": ["name,age\nalice,30\nbob,25", "name"],
  "expected": "alice\nbob\n"
}
EOF

# Run the sub-agent (assume ./run_subagent.sh wraps the logic above)
./run_subagent.sh /tmp/test_task.json
# → Should print the validated Sigil program path within 5-10 seconds
```

## Limitations

This integration approach has known limitations:

- **The classifier is heuristic.** A learned classifier trained on
  past routing decisions would be more accurate but adds complexity.
- **The sub-agent doesn't share context across calls.** Each task is
  independent. Multi-step workflows must be decomposed by the
  parent.
- **Sigil's stdlib has gaps.** Some real tooling tasks (HTTP/2,
  binary protocols, GUI) cannot be expressed at all.
- **Local model accuracy trails cloud.** For workflows where the
  cost of an incorrect program is high, the validate-and-retry loop
  is essential — never trust local-generated code without running
  it first.

## What's NOT in this guide

- A specific Claude Code subagent YAML schema (varies by agent
  runtime; the markdown above is the structural outline)
- Production hardening for the ollama serving layer (TLS, auth,
  rate-limiting — needed for multi-user scenarios but out of scope
  for single-user local use)
- A learned router classifier (heuristic above is a placeholder)
- Telemetry / observability (if you need it, wire it into the
  sub-agent's output path)

These are reasonable next steps once the basic flow is validated
end-to-end on real workloads.
