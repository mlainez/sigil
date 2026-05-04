# Sigil

**A programming language designed by AI, refined by observing AI failures, deployed for AI code generation.**

> **Status (2026-05-04): the experiment is closed.** Read
> [`papers/SIGIL_RESULT.md`](papers/SIGIL_RESULT.md) for the full project
> retrospective: original premise, what the data validated, what it
> refuted, and what we carry forward to the successor project on
> agent-safe local tooling. Final headline numbers are below.

Sigil is a Lisp-shaped scripting language whose design has been shaped by months of iteration with Large Language Models — first via collaborative AI/human design, then through a continuous feedback loop where every model failure on a benchmark fed back into the language surface. Each builtin alias, prelude function, and parser tolerance has a benchmark story behind it.

**Final headline numbers (2026-05-04):**

- **Single-step tooling delegation reaches cloud parity.** The local
  Sigil ensemble (qwen-sigil-v7:7b + deepseek-sigil:6.7b) scores 29/30
  on the Stream C benchmark vs Sonnet 29-30/30, at ~6× lower cost per
  task. The single-step delegation story validated.
- **Multi-step composition plateaus at the local executor's capability,
  not the orchestration recipe.** Best Sigil Path C result: 7/30 on a
  30-task multi-step suite. The orchestration-ceiling diagnostic (NH6)
  showed that swapping only the per-step executor to Sonnet lifts
  Path C to 26/30 on the same orchestration — the gap was executor
  capability, not chain design.
- **Pre-training proximity matters at fixed model size.** A baseline
  qwen2.5-coder:7b (no fine-tune) writing Python on the same harness
  scores 12/30 — a +5-task lift over Sigil at the same parameter count.
  Scaling from 7B to 22B local Python doesn't help further on this
  benchmark.

> **Honest note on principles.** This README has been updated several times to reflect what the project actually became. The original "designed by AI, for AI" framing — and especially the "ONE WAY ONLY / zero ambiguity" claims — described an aspirational pure design. In practice, working with pre-trained models forced a more nuanced reality: the language inherits the AI's training distribution (Python/JS shapes, Lisp synonyms) and works best when it admits those shapes. See [`papers/MEETING_HALFWAY.md`](papers/MEETING_HALFWAY.md) and [`papers/JOURNEY.md`](papers/JOURNEY.md) for the full retrospective. The principles below are split into "**held**" (verified by benchmarks) and "**aspirational**" (stated but not enforced) accordingly.

## Documentation index

If you only have time for one document, pick from this list by your goal.

### Start here

| Document | What it is | When to read |
|---|---|---|
| [`AGENTS.md`](AGENTS.md) | LLM-optimised quick reference (~8K tokens). Examples, idioms, common gotchas. | If you (or a model) are about to write Sigil code. |
| [`.sigil.grammar`](.sigil.grammar) | Machine-readable grammar (~800 tokens). | Cheapest way to prime an LLM on the syntax. Read first when token budget matters. |
| [`LANGUAGE_SPEC.md`](LANGUAGE_SPEC.md) | Complete language specification — types, control flow, builtins, semantics. | Reference for anything not covered in AGENTS.md. |

### Architecture and language surface

| Document | What it is |
|---|---|
| [`SIGIL-CORE.md`](SIGIL-CORE.md) | Core IR specification: 5 frozen statements (`set`, `label`, `goto`, `ifnot`, `ret`). The stable layer. |
| [`SIGIL-AGENT.md`](SIGIL-AGENT.md) | Agent surface specification: `while`, `for`, `if`, `for-each`, etc. The evolving layer. |
| [`.sigil.analysis`](.sigil.analysis) | Architectural analysis — design decisions and known issues, in detail. |
| [`stdlib/README.md`](stdlib/README.md) | Stdlib module list, the **builtin-vs-stdlib boundary principle**, and the **if-Lisp-form trap** (a recurring stdlib gotcha). |
| [`tests/README.md`](tests/README.md) | Test framework and naming conventions. |

### The research story (read for context, not implementation)

| Document | What it is |
|---|---|
| [`papers/JOURNEY.md`](papers/JOURNEY.md) | The full chronicle — phases 1–14. From cloud fine-tunes through QLoRA, RAG, ensembling, validator-in-loop, philosophy retrospective. ~900 lines but indexed by phase. |
| [`papers/MEETING_HALFWAY.md`](papers/MEETING_HALFWAY.md) | The operational design philosophy: when to add an alias for a model's reach versus when to push back. |
| [`papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`](papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md) | Why local LLMs matter for confidentiality / data residency. |
| [`papers/MODEL_VERSIONS.md`](papers/MODEL_VERSIONS.md) | Catalog of every fine-tuned Sigil model (cloud and local), with the rationale, recipe, result, and lesson per version. Reference for "why does v3.1 exist?" / "what's different about v5?" |
| [`papers/AGENTIC_HARNESS_PLAN.md`](papers/AGENTIC_HARNESS_PLAN.md) | Plan for the next phase: an agentic test harness comparing cloud-only vs local-Sigil-tooling token consumption on multi-step tasks. |

### Benchmarking and fine-tuning

| Document | What it is |
|---|---|
| [`benchmark/RESEARCH_PLAN.md`](benchmark/RESEARCH_PLAN.md) | Pre-registered claims and evaluation protocol. |
| [`benchmark/RAG.md`](benchmark/RAG.md) | RAG architecture: how `nomic-embed-text` builds the retrieval index over the training corpus, knob effects (k, min_score, top1_floor, mmr_lambda). |
| [`benchmark/RESULTS.md`](benchmark/RESULTS.md) | Aggregated benchmark results across models and configurations. |
| [`benchmark/corpus_pipeline.md`](benchmark/corpus_pipeline.md) | How the training corpus was generated and filtered. |
| [`benchmark/PLAN_local_vs_cloud_economics.md`](benchmark/PLAN_local_vs_cloud_economics.md) | Cost/Wh comparison between local Sigil and cloud Python paths. |
| [`benchmark/llm_generation_strategy.md`](benchmark/llm_generation_strategy.md) | Prompt structure and retry strategy. |

### Workflow and agent integration

| Document | What it is |
|---|---|
| [`agent_workflow/README.md`](agent_workflow/README.md) | Patterns for using Sigil from inside an agentic-AI workflow. |
| [`tools/agent_harness/README.md`](tools/agent_harness/README.md) | **MCP server** that exposes the local Sigil ensemble as a tool any MCP-aware agent can call (Claude Code, opencode, others). Setup instructions for both, plus the A/B harness measuring cloud-token savings. |
| [`examples/README.md`](examples/README.md) | Example programs index. Real working programs. |
| [`examples/chat_app/README.md`](examples/chat_app/README.md) | WebSocket chat application walkthrough. |
| [`examples/todo_app/README.md`](examples/todo_app/README.md) | TODO app with SQLite backend walkthrough. |

### Suggested reading order for a new researcher

If you came to this repository fresh and want to understand both **what Sigil is** and **what was learned about local-LLM tooling on the way here**, read in this order. Each step builds on the previous and skips redundancy.

1. **[`papers/JOURNEY.md`](papers/JOURNEY.md)** — Phases 1–3 (cloud fine-tunes; corpus-extender; the 10-iteration measurement loop). Sets up the problem and the evaluation infrastructure.
2. **[`benchmark/RAG.md`](benchmark/RAG.md)** — how RAG retrieval is wired and what knobs matter.
3. **[`papers/JOURNEY.md`](papers/JOURNEY.md)** — Phases 4–7 (un-tuned 32B + RAG, then 3B and 7B local QLoRA fine-tunes). The Sigil-vs-Python head-to-head lands here.
4. **[`papers/MEETING_HALFWAY.md`](papers/MEETING_HALFWAY.md)** — the design philosophy that emerged from the failure analysis. Read alongside JOURNEY phase 11 ("language additions earned by failures").
5. **[`papers/JOURNEY.md`](papers/JOURNEY.md)** — Phases 8–13 (Sonnet comparison; deployment study; ensemble fallback hypothesis; routing variants). The local-vs-frontier comparison is here, with the 25/30 ensemble result.
6. **[`papers/JOURNEY.md`](papers/JOURNEY.md)** — **Phase 17 retrospective.** Per-principle grade against the original README claims. The most opinionated section.
7. **[`papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`](papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md)** — why this work matters beyond accuracy: data residency and compliance.
8. **[`benchmark/RESULTS.md`](benchmark/RESULTS.md)** + the JSON files in `benchmark/` — every numerical claim in the narrative cites a result file. They're all here, reproducible.
9. **[`stdlib/README.md`](stdlib/README.md)** — the **builtin-vs-stdlib boundary principle** and the **if-Lisp-form trap**. The clearest statement of what we learned about language-design pitfalls.

The interpreter source (`interpreter/interpreter.ml`, ~5K lines) is the canonical answer to any "but what does it actually do?" question. Builtin definitions live near their dispatch site; comments document trade-offs and historical reasons.

Reproducing any benchmark number: every JSON in `benchmark/` records the model, prompts, hyper-parameters, and seed. The exact commands are in `benchmark/eval_real_tooling.py` (deployment), `benchmark/rag_loop.py` (synthetic 100-task), and `benchmark/finetune_local.py` (training). All deterministic at temperature 0; retry attempts are the only stochastic part and use a fixed temperature ramp.

### Memory / auto-recovered knowledge

For Claude Code working on this repo, durable lessons are persisted to `~/.claude/projects/-var-home-marc-Projects-sigil/memory/`:
- **Navi31 QLoRA stable recipe** — `lr=2e-5 / max_seq=1024 / warmup=0.2 / clip=1.0` for AMD RX 7800 XT.
- **Sigil arch boundary** — when to add to OCaml builtins vs `stdlib/core/prelude.sigil`; the if-Lisp-form trap.
- **Phi-4 LoRA + ollama** — runtime ADAPTER path crashes on Phi-3/4; merge-then-quantize workaround.
- **Corpus-generation lessons** — what shapes work and what to avoid.

These auto-load into Claude sessions so they don't have to be re-derived.

## The Problem Sigil Solves

**Traditional languages are hard for LLMs because:**
- Operator precedence creates ambiguity (`a + b * c` - which operation first?)
- Implicit type conversions hide behavior
- Multiple syntactic forms for the same construct
- Complex control flow nesting requires careful state tracking
- Hundreds of type-specific operations to memorize

**Sigil fixes this:**
- **Zero operator precedence** - all operations are explicit function calls
- **Zero implicit conversions** - types are always explicit
- **One canonical form** - only ONE way to do everything
- **Flat control flow** - structured constructs with simple semantics
- **Type-directed dispatch** - write `add`, interpreter infers `add_int` vs `add_float`
- **S-expression syntax** - trivial to parse and generate

## Architecture: The Two-Layer Innovation

Sigil's killer feature is its **two-layer architecture** that prevents language entropy over time:

```
+---------------------------------------------+
|         Sigil-Agent (Surface)                |
|  What LLMs Write: while, loop, break       |
|  Ergonomic, can evolve over time            |
+---------------------+-----------------------+
                      |
                      v
+---------------------------------------------+
|          Sigil-Core (IR)                     |
|  Concepts: set, goto, label, ifnot, ret     |
|  Minimal, frozen forever (5 statements)     |
+---------------------------------------------+
```

### Why This Matters

- **LLMs write Agent code** - Natural, structured syntax they understand
- **Interpreter handles both layers** - Agent constructs evaluated directly alongside Core primitives
- **Core is frozen** - Your LLM training never becomes outdated
- **Agent evolves** - New features can be added without breaking Core
- **Deterministic** - Same input = same output, always

**Result:** LLM-generated code has a stable target that will never change, while surface syntax can improve over time.

## Quick Start

### Hello World

```lisp
(module hello
  (fn main -> int
    (print "Hello, Sigil!")
    (ret 0)))
```

### Build the Interpreter

```bash
# Prerequisites: OCaml 5.2.1, opam, dune, openssl-dev
cd interpreter
eval $(opam env)
dune build
```

### Run

```bash
# Run Sigil source directly (single step, no compilation)
./interpreter/_build/default/vm.exe hello.sigil
```

## Language Philosophy

### Principles that held (verified by benchmarks)

These design decisions survived months of iteration with real models on real benchmarks. They produced measurable wins.

1. **Two-layer architecture (Core + Agent).** Sigil-Core is 5 frozen statements (`set`, `label`, `goto`, `ifnot`, `ret`). Sigil-Agent is the surface layer (`while`, `for`, `if`, etc.) that evolves freely. Core never broke. Models that learned the Agent surface 12 months ago would still work today.

2. **Type-directed dispatch.** Models write `(add x y)`, interpreter picks int/float/decimal/string/array dispatch from the first arg. Lower memorization burden than `add_int`/`add_f64`/`add_str`. Models adopt this naturally.

3. **S-expression syntax.** Zero precedence ambiguity, uniform `(op args...)` shape, generates trivially. Every Coder model can produce it.

4. **Frozen Core IR.** The 5 Core statements never changed. They're the stable training target.

5. **No comments.** Models don't write comments; corpus stays clean; no token waste on cruft.

6. **Pure-Sigil stdlib.** All stdlib in Sigil itself. Phase 15 *strengthened* this principle by moving convenience functions from OCaml to an auto-loaded prelude written in Sigil. The reason: clean Sigil stdlib doubles as documentation the model can read at retrieval time.

7. **Panic-based errors with contextual messages.** Hard panics, but the messages tell the model what to fix (`"sub takes (int int) or (float float), got (string int)"`). Phase 14 added type-tuple hints across the high-frequency ops; +3pp on synthetic benchmark.

8. **Machine-readable docs first.** `.sigil.grammar` (~800 tokens) is what models consume; prose docs are secondary.

### Principles that didn't hold as stated (but the operational pattern that emerged is more interesting)

9. **~~ONE WAY ONLY~~ → Many ways for input, one canonical implementation.** The original principle claimed every construct had exactly one canonical form. **In practice we have ~30 aliases** (`head/first`, `count_el/count`, `+/add`, `<`/`lt`, `contains/in/has`, `size/length/len`, etc.). Every alias was added because models reach for it from Python/Lisp/Haskell training. Each alias produced a benchmark win.

   The operational pattern that emerged: **"meeting halfway" — the language admits any reasonable shape the model produces, then maps to canonical implementations.** This is documented separately in `papers/MEETING_HALFWAY.md`.

10. **~~Zero ambiguity~~ → Minimal ambiguity, with a few documented gotchas.** The if-Lisp-form trap (2-statement then-body without `(else)` becomes Lisp/Scheme then-else); `string_get` returning int char code while `string_at` returns 1-char string; `count` overloaded for strings and arrays. Real ambiguity, real cost. We document them in `stdlib/README.md` so the next stdlib author catches them.

11. **~~Designed by AI, for AI~~ → Designed by AI, refined by observing AI failures, deployed for AI.** AI did design Sigil. AI did pick OCaml. AI did write the implementation. But the language we ended up with optimizes for **the AI's training distribution** (Python/JS shapes, Lisp synonyms), not for an abstract AI-cleanness. The distinction is real: the AI didn't design what works best for AI in general — it designed what works for *the kind of AI it itself is*: a pre-trained transformer with a Python-heavy prior. A different language, with similar pure principles but tuned for a model trained from scratch on its own corpus, would look very different.

## Use Cases

### What Sigil is FOR

- **AI Code Generation** - Primary design goal
- **Web Services** - HTTP servers, REST APIs, WebSocket servers
- **CLI Tools** - System utilities, automation scripts
- **Network Services** - TCP servers, TLS, WebSocket protocol implementations
- **Data Processing** - JSON/CSV parsing, transformations
- **System Integration** - Process spawning, IPC, database clients

### What Sigil is NOT FOR

- **Real-time Systems** - Tree-walking interpreter overhead
- **Low-level System Programming** - No manual memory management, no pointers
- **GUI Applications** - No GUI framework (yet)
- **Performance-Critical Inner Loops** - Compile to C/Rust for hot paths

## Core Features

### Types (Simplified for LLM Predictability)

```lisp
int      ; 64-bit signed integer (ONLY int type)
float    ; 64-bit floating point (ONLY float type)
decimal  ; Arbitrary precision decimal (financial math)
bool     ; Boolean (true/false)
string   ; UTF-8 string
array    ; Dynamic array
map      ; Hash map
json     ; JSON values
regex    ; Compiled regular expression
socket   ; TCP socket handle
process  ; Process handle (for DB, subprocesses)
```

**AI Decision:** Only TWO numeric types (`int`, `float`) plus `decimal` for financial precision - not i8/i16/i32/i64/u8/u16/u32/u64. Less for LLMs to remember, still covers 99% of use cases.

### Control Flow (Agent Layer)

```lisp
(while condition statements...)   ; While loop
(loop statements...)              ; Infinite loop
(for var start end statements...) ; Counting loop [start, end)
(if condition statements...)      ; Conditional
(if condition then... (else ...)) ; If-else conditional
(for-each var type collection     ; For-each iteration
  statements...)
(break)                           ; Exit loop
(continue)                        ; Next iteration
(and expr1 expr2)                 ; Short-circuit AND
(or expr1 expr2)                  ; Short-circuit OR

; Core constructs (available for complex control flow)
(label name)                      ; Jump target
(goto target)                     ; Unconditional jump
(ifnot bool_var target)           ; Jump if false
```

**AI Decision:** Structured constructs are evaluated directly by the interpreter. LLMs write ergonomic code, interpreter handles semantics.

### Type-Directed Dispatch (LLM Superpower)

```lisp
; LLM writes this (generic)
(set x int 10)
(set y int 20)
(set sum int (add x y))    ; Interpreter infers add_int

(set a float 3.14)
(set b float 2.71)
(set total float (add a b)) ; Interpreter infers add_float
```

**AI Decision:** LLMs don't need to remember `add_int`, `add_i64`, `add_f32`, `add_f64` - just write `add` and the interpreter figures it out.

### Error Handling

```lisp
(fn safe_divide a int b int -> int
  (if (eq b 0)
    (panic "Division by zero"))
  (ret (div a b)))

(fn main -> int
  (set value int (safe_divide 10 0))
  (print value)
  (ret 0))
```

**AI Decision:** Operations panic on error with clear messages. LLM regenerates with checks (file_exists, etc.) when panics occur.

## Standard Library (14 Modules in Pure Sigil)

All stdlib modules are implemented **in pure Sigil**, not native code. This enforces our philosophy: "If it CAN be written in Sigil, it MUST be written in Sigil."

### Core (9 modules)
- **string_utils** - String operations (`split`, `trim`, `contains`, `replace`, `starts_with`, `ends_with`, `to_upper`, `to_lower`)
- **conversion** - Type conversion (`string_from_int`, `bool_to_int`, `kilometers_to_miles`)
- **array_utils** - Array utilities (`array_sum`, `array_product`, `array_find`, `array_contains`, `array_reverse`)
- **math** - Math operations (`abs`, `min`, `max`)
- **math_extended** - Extended math (`clamp`, `sign`, `lerp`, `is_even`, `is_odd`)
- **filesystem** - File utilities (`read_file_safe`, `write_file_safe`, `copy_file`, `read_lines`)
- **network** - Network utilities (`is_valid_port`, `build_url`, `parse_url`, `extract_domain`)
- **text_utils** - Text utilities (`repeat_string`, `pad_left`, `pad_right`, `truncate`, `word_count`)
- **validation** - Validation (`in_range`, `is_positive`, `is_negative`, `is_zero`)

### Data (1 module)
- **json_utils** - JSON parsing and generation

### Net (1 module)
- **http** - HTTP client (GET, POST, PUT, DELETE)

### Pattern (1 module)
- **regex** - Regular expressions

### System (1 module)
- **process** - Process management

### Database (1 module)
- **sqlite** - SQLite database (via process spawning)

**Plus 180+ built-in operations** for arithmetic, comparisons, I/O, TCP/TLS networking, WebSocket protocol, file system, arrays, maps, string formatting, and more.

## Examples

### Factorial (Recursion)

```lisp
(module factorial
  (fn factorial n int -> int
    (if (eq n 0)
      (ret 1))
    (set n_minus_1 int (sub n 1))
    (set prev int (factorial n_minus_1))
    (ret (mul n prev)))

  (fn main -> int
    (set result int (factorial 5))
    (print result)  ; Prints: 120
    (ret 0)))
```

### Web Server (Real HTTP Server in 20 Lines)

```lisp
(module web_server
  (fn handle_request client_sock string -> int
    (set request string (tcp_receive client_sock 4096))
    (set response string "HTTP/1.1 200 OK\r\n\r\nHello from Sigil!")
    (tcp_send client_sock response)
    (tcp_close client_sock)
    (ret 0))

  (fn main -> int
    (set server_sock string (tcp_listen 8080))
    (print "Server listening on port 8080")
    (loop
      (set client_sock string (tcp_accept server_sock))
      (handle_request client_sock))
    (ret 0)))
```

### Counting For Loop

```lisp
(module for_demo
  (fn sum_range n int -> int
    (set total int 0)
    (for i 0 n
      (set total (add total i)))
    (ret total))

  (fn main -> int
    (set result int (sum_range 10))
    (print result)  ; Prints: 45
    (ret 0)))
```

### For-Each Loop

```lisp
(module foreach_demo
  (fn sum_array arr array -> int
    (set total int 0)
    (for-each val int arr
      (set total (add total val)))
    (ret total))

  (fn main -> int
    (set nums array [10 20 30])
    (set result int (sum_array nums))
    (print result)  ; Prints: 60
    (ret 0)))
```

See [examples/](examples/) for complete working examples including a real-time WebSocket chat app and a TODO app with SQLite.

## Testing

Sigil has **138 passing tests** covering all language features. All tests use the `test-spec` structure:

```lisp
(module test_addition
  (fn add_numbers a int b int -> int
    (ret (add a b)))

  (test-spec add_numbers
    (case "adds positive numbers"
      (input 2 3)
      (expect 5))
    (case "handles negative numbers"
      (input -5 -3)
      (expect -8)))

  (meta-note "Tests integer addition"))
```

**AI Decision:** No `main()` functions in tests. Test framework provides entry point. ONE WAY to write tests.

## Project Structure

```
sigil/
+-- README.md                   # This file
+-- AGENTS.md                   # LLM quick reference (8K tokens)
+-- LANGUAGE_SPEC.md            # Complete language specification
+-- SIGIL-CORE.md                # Core IR specification (frozen forever)
+-- SIGIL-AGENT.md               # Agent surface language
+-- .sigil.grammar               # Machine-readable grammar (~1600 tokens)
+-- .sigil.analysis              # Deep architectural analysis
|
+-- interpreter/                # OCaml tree-walking interpreter
|   +-- lexer.ml                # S-expression tokenizer
|   +-- parser.ml               # Recursive descent parser
|   +-- types.ml                # Type kind definitions
|   +-- ast.ml                  # AST node types
|   +-- interpreter.ml          # Evaluator + 180+ builtins (~2500 lines)
|   +-- vm.ml                   # Entry point
|   +-- dune / dune-project     # Build configuration
|   +-- _build/                 # Build output
|
+-- stdlib/                     # Standard library (17 modules, pure Sigil!)
|   +-- core/                   # Core modules (string_utils, conversion, array_utils, math, math_extended, filesystem, network, text_utils, validation)
|   +-- crypto/                 # Cryptography (base64, hash, hmac)
|   +-- data/                   # Data formats (json_utils)
|   +-- net/                    # Networking (http)
|   +-- pattern/                # Pattern matching (regex)
|   +-- sys/                    # System (process)
|   +-- db/                     # Databases (sqlite)
|   +-- README.md               # Stdlib documentation
|
+-- tests/                      # Test suite (138 tests, all passing)
|   +-- test_*.sigil             # Unit tests
|   +-- README.md
|
+-- examples/                   # Example programs
|   +-- hello_world.sigil
|   +-- chat_app/               # Real-time WebSocket chat application
|   +-- todo_app/               # TODO app with SQLite backend
```

## Documentation Hierarchy (For LLMs)

**When generating Sigil code, LLMs should consult in this order:**

1. **[`.sigil.grammar`](.sigil.grammar)** (~800 tokens) — complete syntax reference, **consult first**
2. **[`.sigil.analysis`](.sigil.analysis)** — design decisions and known issues
3. **[`AGENTS.md`](AGENTS.md)** (~8K tokens) — LLM-optimised quick reference with examples
4. **[`LANGUAGE_SPEC.md`](LANGUAGE_SPEC.md)** — complete specification for deep dives

**Why this order?** Token efficiency. `.sigil.grammar` is ~10× more efficient than prose documentation.

For *human* readers (researchers, contributors), see the **[Documentation index](#documentation-index)** at the top of this README — it groups everything by goal (start-here, architecture, research story, benchmarking, workflow).

## Key Design Decisions Explained

### 1. Why No Comments?

**Decision:** Sigil intentionally has no comment syntax (no `;`, `//`, `#`, `/* */`).

**Rationale:**
- Forces descriptive variable and function names
- Prevents commented-out code cruft
- Use `meta-note` in tests for documentation
- LLMs often struggle with comment placement - removing the feature removes the problem

### 2. Why Only Two Numeric Types?

**Decision:** Only `int` (64-bit) and `float` (64-bit), not i8/i16/i32/i64/u8/u16/u32/u64/f32/f64.

**Rationale:**
- 99% of code doesn't need 8 numeric types
- Fewer types = less for LLMs to memorize
- Simplifies type-directed dispatch
- Still covers all practical use cases
- If you need byte-level control, use arrays

### 3. Why S-Expressions?

**Decision:** Lisp-style parenthesized syntax instead of C-like syntax.

**Rationale:**
- Zero ambiguity in parsing
- No operator precedence rules
- Uniform structure (everything is `(operation args...)`)
- Trivial to generate programmatically
- LLMs already understand S-expressions from Common Lisp, Scheme, Clojure

### 4. Why Type-Directed Dispatch?

**Decision:** Write `(add x y)`, not `(add_int x y)`.

**Rationale:**
- Reduces cognitive load for LLMs (don't memorize 50 operation variants)
- Interpreter infers types from variable declarations
- Still fully statically typed (no runtime dispatch overhead)
- Feels more natural for LLMs trained on high-level languages

### 5. Why Frozen Core IR?

**Decision:** The 5 Core statements will never change, ever.

**Rationale:**
- LLM training data never becomes outdated
- Agent layer can evolve without breaking Core
- Simplifies interpreter implementation
- Easier to reason about correctness
- Future implementations can target the same IR

### 6. Why No `main()` in Tests?

**Decision:** Test files use `test-spec`, not `main()` functions.

**Rationale:**
- ONE WAY to write tests (zero ambiguity)
- Test framework provides entry point automatically
- Declarative test structure easier for LLMs to generate
- Prevents mixing test logic with test execution

### 7. Why Pure Sigil Stdlib?

**Decision:** All stdlib modules must be written in pure Sigil.

**Rationale:**
- Eating our own dog food - discovers language limitations immediately
- Stdlib modules become learning examples for LLMs
- No FFI/dependency hellscape
- Forces Sigil to be complete and self-sufficient
- If Sigil can't express something, we extend Sigil

## Building from Source

```bash
# Prerequisites: OCaml 5.2.1 (via opam), dune 3.21+, openssl-dev
cd interpreter
eval $(opam env)
dune build

# Binary created at:
# interpreter/_build/default/vm.exe
```

## Running Tests

```bash
# Run all 138 tests
cd interpreter
eval $(opam env)
total=0; passed=0
for f in ../tests/test_*.sigil; do
  total=$((total+1))
  timeout 5 ./_build/default/vm.exe "$f" >/dev/null 2>&1 && passed=$((passed+1))
done
echo "$passed/$total"
```

## Performance Characteristics

- **Interpretation:** Tree-walking, direct AST evaluation - no separate compilation step
- **Startup:** Fast (<10ms) - parse and execute in one step
- **No GC pauses:** OCaml garbage collector handles memory
- **Cold start:** Minimal overhead (no bytecode generation, no JIT warmup)
- **WebSocket:** Native binary frame encoding/decoding with SHA-1 handshake

**Not designed for:** Number-crunching inner loops. Use C/Rust for hot paths, Sigil for glue code.

## Contributing

Sigil is currently in active development. All changes must:

1. Maintain zero ambiguity (ONE WAY ONLY)
2. Pass all 138 tests
3. Update machine-readable docs (`.sigil.grammar`, `.sigil.meta`)
4. Write new stdlib modules in pure Sigil
5. Follow the "frozen Core IR" principle

## Strengths

- **LLM-Optimized** - Designed for reliable AI code generation
- **Zero Ambiguity** - Every construct has exactly one meaning
- **Stable Target** - Core IR frozen forever
- **Batteries Included** - 180+ built-in operations, 17 stdlib modules
- **Fast Startup** - Direct interpretation, <10ms
- **Easy to Parse** - S-expression syntax
- **Explicit Everything** - No surprises, no hidden behavior
- **Real-World Ready** - Production HTTP/WebSocket servers, database clients, JSON processing

## Weaknesses (Known Limitations)

- **Interpreter Overhead** - Not as fast as compiled C/Rust (not the goal)
- **No SIMD** - Tree-walking interpreter doesn't vectorize
- **No Parallel Execution** - Single-threaded for now (async planned)
- **Limited Ecosystem** - Young language, stdlib still growing
- **No IDE Support** - LSP server planned but not implemented

## Roadmap

### Near Term
- [ ] LSP server for editor integration
- [ ] Async/await for concurrent I/O
- [ ] More stdlib modules (HTTP server framework, database clients)
- [ ] Package manager

### Long Term
- [ ] Bytecode compiler for performance
- [ ] WebAssembly target
- [ ] Parallel execution model
- [ ] Native compilation (Sigil -> C)

---

## About the Name

**Sigil** — A symbolic language for AI code generation.

Also: Sigil: a symbolic mark with power.

The project's working name through early February 2026 was **AISL**
("AI-Optimized Systems Language", pronounced "aisle"). It was renamed
to Sigil on 2026-02-11, the same evening the project pivoted from a
pure language-design effort (with a C compiler and a self-hosting
attempt) to a training-corpus and local-LLM benchmark effort. The
[`papers/JOURNEY.md`](papers/JOURNEY.md) document opens with
**"Phase 0: Pre-corpus genesis"**, which reconstructs the rename, the
V2→V3 syntax cleanup that preceded it, and the C-compiler-to-OCaml-
interpreter transition that triggered it — sourced from the local
opencode session logs of that week.

---

**Sigil - Designed for AI, Built for Everyone.**

*Created through collaborative AI-human design to solve the hard problem: making LLMs generate correct code, reliably.*
