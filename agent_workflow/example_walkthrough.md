# End-to-end walkthrough: routing one task through the local Sigil stack

This doc shows what actually happens when a parent agent (Claude
Code, opencode, or a custom orchestrator) hands a host-tooling task
to the local Sigil sub-agent. The example is grounded in real
output from the A/B harness (`tools/agent_harness/ab_results*.json`)
— *not* a hypothetical transcript.

The companion files in this directory:
- [`router.py`](./router.py) — the parent-agent routing logic
- [`sigil_subagent.md`](./sigil_subagent.md) — the sub-agent definition

## The task

User asks the parent agent:

> "Take this JSON and give me the names of users whose role is 'admin', one per line."
>
> ```json
> {"users":[{"name":"alice","role":"member"},{"name":"bob","role":"admin"},{"name":"carol","role":"admin"},{"name":"dave","role":"member"}]}
> ```

Expected output:

```
bob
carol
```

This is the `json_extract_paths` task from
`tools/agent_harness/agent_tasks.json`. It is the canonical
local-eligible shape: self-contained, verifiable, single-step,
within Sigil's stdlib.

## Step 1 — Parent agent classifies and routes

The parent agent calls `route_task` from `router.py`:

```python
from agent_workflow.router import route_task

decision = route_task(
    "Take a JSON object of the form {\"users\":[...]}. "
    "Print the names of users whose role is 'admin', one per line.",
    latency_budget_seconds=30.0,
    privacy_required=False,
)
# decision.route == Route.LOCAL
# decision.shape == "json_path_extract"
# decision.reason == "shape 'json_path_extract' is in local-eligible set"
```

The router classifies the task as `json_path_extract` (matched by
the `\bjson\b ... \b(extract|select|get)\b` pattern), recognises
that as a local-eligible shape, and returns `Route.LOCAL`. The
parent now hands off to the `sigil-tooling` sub-agent.

## Step 2 — Sub-agent calls `sigil_run_task` via MCP

The sub-agent (per `sigil_subagent.md`) constructs the MCP call:

```jsonc
// Tool: sigil_run_task
{
  "description": "Take a JSON object of the form {users:[{name,role}...]}. Print names of users whose role is 'admin', one per line in input order.",
  "input": "{\"users\":[{\"name\":\"alice\",\"role\":\"member\"},{\"name\":\"bob\",\"role\":\"admin\"},{\"name\":\"carol\",\"role\":\"admin\"},{\"name\":\"dave\",\"role\":\"member\"}]}",
  "expected_shape": "bob\ncarol\n"
}
```

The MCP server (`tools/agent_harness/sigil_mcp_server.py`) takes
over from here. The orchestrator pays *only* for the small
delegation prompt — it does not write the Sigil program itself.

## Step 3 — Local ensemble generates Sigil code

The MCP server calls the primary model (`qwen-sigil-v6:7b`) via
ollama with the task description prompt and the slim system header
including the Tier 1 input-shape rules. With temperature 0 and
RAG retrieval seeded by the description, the model produces:

```sigil
(set j (json_parse $0))
(for-each u (json_get j ["users"])
  (if (eq (json_get u ["role"]) "admin")
    (println (json_get u ["name"]))))
```

This program took **2 stages × ~3 tokens in / ~135 out** of
orchestrator tokens (Sonnet's delegation+report) plus zero
cloud-side code-generation tokens. The Sigil program itself was
generated locally at 0$ marginal cost.

## Step 4 — Sigil interpreter validates against the sample

The MCP server writes the generated code to a temp file and runs
the OCaml interpreter against the supplied `input` argument:

```bash
./interpreter/_build/default/vm.exe /tmp/tmpXXXXX.sigil \
    '{"users":[{"name":"alice"...}]}'
```

stdout:

```
bob
carol
```

Exact byte match against `expected_shape`. The MCP server
returns:

```json
{
  "ok": true,
  "stdout": "bob\ncarol\n",
  "code": "(set j (json_parse $0))\n(for-each u (json_get j [\"users\"])\n  (if (eq (json_get u [\"role\"]) \"admin\")\n    (println (json_get u [\"name\"]))))",
  "attempts": 1,
  "model_used": "qwen-sigil-v6:7b",
  "fallback_used": false,
  "wall_seconds": 9.6,
  "balancer_applied": false
}
```

## Step 5 — Sub-agent returns the validated program

The sub-agent reports to the parent:

```json
{
  "status": "success",
  "code_path": "/tmp/tmpXXXXX.sigil",
  "code": "(set j (json_parse $0))\n(for-each u (json_get j [\"users\"]) ...)",
  "validated_against": {
    "input": "{\"users\":[...]}",
    "expected": "bob\ncarol\n"
  },
  "model_used": "qwen-sigil-v6:7b",
  "fallback_used": false,
  "wall_seconds": 9.6
}
```

The parent agent runs the same Sigil program against real
production data via `Bash` and surfaces the result to the user.

## What happens on the *failure* path: `csv_top3_categories`

The `csv_top3_categories` task from the same suite is the honest
counter-example: with Phase 21's v6+phi-v2 ensemble (pre-Tier 1)
the local stack failed it — phi-sigil-v2 indexed `(first row)`
(the date column) instead of `(array_get row 1)` (the category
column the header named).

In Phase 22 we tightened three things to address this class of
failure:

1. **Interpreter** emits a "no output produced" warning when the
   program completes without writing anything (Phase 22.1).
2. **`validator_hint`** pattern-matches that warning and rewrites
   the retry prompt with the canonical fix (Phase 22.2).
3. **Corpus + system prompt** include header-aware tabular shapes
   that explicitly index by column position from the header
   description (Phase 22.4–22.5).

When the local ensemble fails after retries, the sub-agent does
**not** silently fall back to a cloud model. It returns:

```json
{
  "status": "failed",
  "attempts": 3,
  "last_code": "(set rows (split $0 \"\\n\")) ...",
  "last_error": "Warning: program completed without writing any output. Common causes: (a) (argv) returned ...",
  "suggested_route": "cloud"
}
```

The parent decides:
- If `privacy_required=False`: route to cloud Sonnet for this
  task. The fallback is explicit and observable.
- If `privacy_required=True`: hand back to the human with the
  partial result, **never** silently leak the input to a cloud
  provider.

## Cost and latency snapshot (from the v6+phi-v2 + Tier 1 A/B run)

For the 8-task multi-step agent suite:

| | Path A: Sonnet writes Python | Path B: hybrid (orchestrator delegates to local Sigil) |
|---|---:|---:|
| Pass rate | (filled in JOURNEY Phase 22) | (filled in JOURNEY Phase 22) |
| Wall time | ~5 s/task | ~25 s/task (qwen primary) — ~33 s/task on phi-v2 fallback |
| Marginal cost | ~$0.003/task | ~$0.003 orchestrator + $0 local |
| Network egress | full task data + generated Python | only the small delegation/report exchange |

The cost differential is *not* the headline. The differential is
**confidentiality** — Path B never sends the actual input data to
the cloud orchestrator, only the abstracted task spec. That is
the load-bearing argument for the local stack on regulated data;
see `papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`.

## When NOT to use this flow

The router will route to cloud (or escalate) for any of:

- Architecture/refactor questions ("redesign this auth module")
- Library research ("which JSON parser should I use in Rust?")
- Multi-file changes
- Sub-second-interactive latency budgets
- Tasks that don't classify into a known local-shape family

This is by design. The local stack is *not* a general substitute
for a cloud frontier model; it is a tooling-shape delegation
target. Single-step Stream C: 29/30 = Sonnet's 29/30. Multi-step
A/B harness: see Phase 22 numbers — the bottleneck on
multi-step composition is structural and being addressed by the
Tier 2 chained sub-agent work, not by a stronger base model.

## Reproducing this walkthrough end-to-end

```bash
# 1. Bring up ollama with both Sigil models registered
ollama serve &
ollama list | grep sigil   # qwen-sigil-v6:7b and phi-sigil-v2:14b should appear

# 2. Build the interpreter
cd interpreter && eval $(opam env) && dune build

# 3. Run the A/B harness on the 8 multi-step tasks
SIGIL_PRIMARY_MODEL=qwen-sigil-v6:7b \
SIGIL_FALLBACK_MODEL=phi-sigil-v2:14b \
python3 tools/agent_harness/agent_ab_harness.py \
  --out tools/agent_harness/ab_results.json

# 4. Inspect a single task's path-B transcript
python3 -c "
import json
d = json.load(open('tools/agent_harness/ab_results.json'))
for t in d['tasks']:
    if t['id'] == 'json_extract_paths':
        print(json.dumps(t['B'], indent=2))
"
```

The `json_extract_paths` task is the canonical success case: 1
attempt, qwen-sigil-v6:7b primary (no fallback), exact-byte match
against `expected_shape`. It is small enough to read end-to-end
and large enough to exercise every step of the flow.
