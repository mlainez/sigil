# Sigil agentic harness — local-tooling MCP server

This directory contains a Model Context Protocol (MCP) server that exposes the local Qwen-Sigil + Phi-Sigil ensemble as a tool any MCP-aware agent can call. It is the implementation of the plan in [`papers/AGENTIC_HARNESS_PLAN.md`](../../papers/AGENTIC_HARNESS_PLAN.md).

**The point**: a cloud orchestrator (Claude Sonnet, GPT-5, Gemini, etc.) can **delegate tooling-shape code generation to local models** instead of generating Python inline. The cloud sees only the task spec and the validated output — never has to spend tokens writing the program itself. Cost saving + confidentiality win.

## Tools exposed

| Tool | Purpose |
|---|---|
| `sigil_run_task(description, input, expected_shape="")` | Generate + run a Sigil program for the described task. Returns stdout. Retries up to 3× with the ensemble fallback. |
| `sigil_run_code(code, input)` | Run a Sigil program directly without generating. Useful for re-using known-good programs. |
| `sigil_capabilities()` | Returns a description of what Sigil + this server can do, so the orchestrator can route intelligently. |

## Prerequisites

1. **Sigil interpreter built** (`interpreter/_build/default/vm.exe` exists). See top-level `README.md`.
2. **ollama running** on `http://localhost:11434` (override via `OLLAMA_URL` env).
3. **Local Sigil models registered**:
   - `qwen-sigil-v4:7b` (primary) — see `benchmark/Modelfile.sigil_v4`
   - `phi-sigil-v1:14b` (fallback) — see `benchmark/Modelfile.sigil_phi4_merged`
   Override with `SIGIL_PRIMARY_MODEL` / `SIGIL_FALLBACK_MODEL` env if you want different models.
4. **Python 3.10+ with the `mcp` package** in the project venv at `benchmark/.venv/`. Install via `pip install mcp` if missing.

## Quick check (does it work?)

```bash
# From the repo root:
echo '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  | benchmark/.venv/bin/python tools/agent_harness/sigil_mcp_server.py
```

You should see a JSON-RPC initialize response. If you do, the server starts correctly. Hit Ctrl-C.

## Setup: Claude Code

Add the MCP server to your Claude Code config. Two scopes are possible:

### Project-scoped (recommended for this repo)

Create `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "sigil-local-tooling": {
      "command": "/var/home/marc/Projects/sigil/benchmark/.venv/bin/python",
      "args": ["/var/home/marc/Projects/sigil/tools/agent_harness/sigil_mcp_server.py"],
      "env": {
        "SIGIL_PRIMARY_MODEL": "qwen-sigil-v4:7b",
        "SIGIL_FALLBACK_MODEL": "phi-sigil-v1:14b",
        "OLLAMA_URL": "http://localhost:11434",
        "SIGIL_MAX_ATTEMPTS": "3"
      }
    }
  }
}
```

Adjust the absolute paths to match your install. Restart Claude Code; the `sigil_run_task` / `sigil_run_code` / `sigil_capabilities` tools will appear under the `sigil-local-tooling` namespace.

### User-scoped (available in every project)

Place the same JSON in `~/.claude/mcp.json` (or use `claude mcp add sigil-local-tooling …` per the official docs). Same `mcpServers` block.

### Telling Claude when to delegate

Add a one-paragraph hint to your `CLAUDE.md` (project- or user-level):

```markdown
For host-tooling-shape tasks (parsing logs, filtering CSVs, regex
extraction, format conversion, counting/aggregation), prefer calling
`sigil_run_task` from the `sigil-local-tooling` MCP server over writing
Python inline. This keeps tooling work local (no token cost, no data
egress) and uses a model fine-tuned specifically for the language.
Call `sigil_capabilities` if unsure whether a task fits.
```

## Setup: opencode

[`opencode`](https://opencode.ai) supports MCP via its config file at `~/.config/opencode/config.json`:

```json
{
  "mcp": {
    "sigil-local-tooling": {
      "type": "local",
      "command": [
        "/var/home/marc/Projects/sigil/benchmark/.venv/bin/python",
        "/var/home/marc/Projects/sigil/tools/agent_harness/sigil_mcp_server.py"
      ],
      "environment": {
        "SIGIL_PRIMARY_MODEL": "qwen-sigil-v4:7b",
        "SIGIL_FALLBACK_MODEL": "phi-sigil-v1:14b",
        "OLLAMA_URL": "http://localhost:11434"
      },
      "enabled": true
    }
  }
}
```

Restart opencode; the same three tools appear.

## Setup: any other MCP-aware agent

Use the same command line as the Claude/opencode entries:

```
/path/to/python /path/to/repo/tools/agent_harness/sigil_mcp_server.py
```

Speaks JSON-RPC 2.0 over stdio (the standard MCP transport). All env vars are optional; see the `os.environ.get` calls in `sigil_mcp_server.py` for defaults.

## Example agent interactions

These are the kinds of conversations the harness enables. The italicised lines are what the orchestrator decides to do internally; only the bold parts are what the user sees.

### Example 1: parse a log file

> **User**: From this nginx access log, find the IP that issued the most failed (4xx/5xx) requests and tell me the count.

*Orchestrator (Claude/Opencode) sees this is a parse-and-aggregate task. Routes to `sigil_run_task`:*

```json
{
  "description": "From an nginx access log (lines like '192.168.1.1 - - [date] \"GET /path\" 404 56'), filter to lines with 4xx or 5xx status codes (the 4-digit status field), then count occurrences of each IP, then print 'IP COUNT' for the IP with the highest count.",
  "input": "<contents of the log file as a string>"
}
```

*Server: generates `(...) (...)`, runs it via vm.exe, returns:*

```json
{
  "ok": true,
  "stdout": "192.168.1.42 1283\n",
  "code": "(let lines (split $0 \"\\n\")) ...",
  "attempts": 2,
  "wall_seconds": 7.4,
  "model_used": "qwen-sigil-v4:7b",
  "fallback_used": false
}
```

> **Claude**: 192.168.1.42 made the most failed requests (1,283).

The orchestrator never wrote the parser. Tokens it would have spent generating Python and reading the program back are saved.

### Example 2: explicit code provided

> **User**: I wrote this Sigil program. Run it on this CSV.

*Orchestrator routes to `sigil_run_code` (no generation needed):*

```json
{
  "code": "(for-each row (split $0 \"\\n\") ...)",
  "input": "<csv content>"
}
```

### Example 3: capability discovery

*Orchestrator on first call of a session, before a tooling-shape task:*

```json
{ "tool": "sigil_capabilities", "args": {} }
```

The returned text is the routing rubric the orchestrator uses to decide future delegations.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: mcp` | venv missing the package | `benchmark/.venv/bin/pip install mcp` |
| `Connection refused` to ollama | `ollama serve` not running | `nohup ollama serve > /tmp/ollama.log 2>&1 &` |
| `Model not found: qwen-sigil-v4:7b` | adapter not registered | `cd benchmark && ollama create qwen-sigil-v4:7b -f Modelfile.sigil_v4` |
| Server starts but generates nothing | wrong PRIMARY_MODEL env | check `ollama list` and pick a model that's actually present |
| Sub-process timeout | `vm.exe` not built | `cd interpreter && eval $(opam env) && dune build` |

## What this does NOT do

- **Does not** orchestrate multi-step tasks itself. The orchestrator (Claude/opencode/your agent) decides when to call this tool. The server is a single-call generate+run primitive.
- **Does not** read files. `input` is always a single string. If you want the program to read files, pass the file contents in `input`, or have the orchestrator stitch reads via its own filesystem tools first.
- **Does not** maintain conversational state. Each `sigil_run_task` call is independent. If you want a chained workflow, the orchestrator chains them.

## Measuring the value claim

`agent_ab_harness.py` runs the same task suite twice — once with the orchestrator generating Python inline (Path A), once delegating to this MCP server (Path B) — and reports the cloud-token saving. See [`papers/AGENTIC_HARNESS_PLAN.md`](../../papers/AGENTIC_HARNESS_PLAN.md) for the methodology.

### First-run results (seeded 8-task suite, 2026-05-02)

Run with: `python3 tools/agent_harness/agent_ab_harness.py`

| | Path A (cloud Python) | Path B (hybrid local Sigil) |
|---|---|---|
| Pass rate | **6/8** | **1/8** |
| Cloud input tokens | 24 | 48 |
| Cloud output tokens | 1517 | 1813 |
| Cost ($) | $0.0228 | $0.0273 |
| Avg time/task | ~5s | ~25s |

**Path B was worse on every axis on this seed suite.** The 8 tasks were intentionally multi-step (filter → count → sort → format) which is the failure shape we already documented for the local ensemble: Stream C tooling tasks (single-step, ~51 output tokens) hit 93%, multi-step composition collapses to 12%.

This is honest data — the harness is doing its job. Two readings:

1. **Negative for the headline value claim**: at this task complexity, delegation costs more cloud tokens AND fails more often than just letting Sonnet write Python.
2. **Positive for the next architectural move**: the failure mode is composition, not Sigil itself. A *chained-Sigil-calls* harness (one tool call per step instead of one per task) would let each step stay in the Stream C size where local already works. See `papers/JOURNEY.md` Phase 15.5 — this is the #1 strategic recommendation that came out of this finding.

Raw per-task results: `tools/agent_harness/ab_results.json`.

### When the harness IS valuable today

For *single-shape* tooling tasks within an agentic workflow:
- "parse this CSV" → one delegation
- "extract these regex matches" → one delegation
- "format this output" → one delegation

The MCP server is appropriate. The cost math flips: Sonnet writes ~30 tokens of "I'll delegate" + reads back the result, vs ~150 tokens of Python. On single-step delegation, expected savings ~50-70% of cloud output tokens.

The 1/8 score on the multi-step suite says **don't use Path B for compose-multiple-steps tasks.** Use it for the single-step tooling pieces.
