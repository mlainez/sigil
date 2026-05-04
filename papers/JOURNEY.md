# Journey: How a 1872-Example Local LoRA Beat 32B-with-RAG on a Sigil Benchmark

**Status:** working draft of the research narrative.
**Audience:** anyone evaluating whether the conclusions of this work
hold under critical reading. Reading this end-to-end should reproduce
every decision point and surface every dead-end.

The research path was non-linear. The ordering below preserves the
chronology even where with hindsight a more direct path would have
been chosen. Dead ends are flagged so reviewers can see what was
ruled out and on what evidence.

## Phase 0: Pre-corpus genesis (2026-02-05 to 2026-02-11)

This section was reconstructed after the fact from four
session-log sources, all consolidated under
[`papers/early_design_sessions/`](./early_design_sessions/) plus the
local Claude Code logs on this host:

- **mammouth.ai shared sessions** — two shared chat sessions from
  the afternoon of 2026-02-05 (16:11 → 21:06 UTC), 30 + 32 messages
  using `mistral-large-latest` and `anthropic-claude-sonnet-4-5`
  respectively. **These are the earliest known activity on the
  project on any recoverable artefact** — ~3.5 hours before the
  first VSCode Copilot session opens on the dev host. The earlier
  session is literally titled **"CANON Grammar (AI-Focused)"** in
  the data — primary-source confirmation that CANON was the working
  name before AISL. Mistral drove the initial typed-AST sketch
  (Int / Float / Bool / String / Array / Result, FunctionNode
  contract, Pure / IORead / IOWrite / Network effect annotations);
  Claude Sonnet 4.5 took over for the EBNF refinement (BigDecimal,
  Future, Channel, spawn/await/send, lambda, path-restricted IO).
- **VSCode + GitHub Copilot Chat** sessions in the
  `Projects/aisl` and (later) `Projects/sigil` workspaces on the
  development host — five saved chats, the substantive ones being
  two on the evening of 2026-02-05 (35 + 16 requests, ~16 MB
  combined). These are where the language acquired its codebase
  scaffolding and where the foundational AI-design directives were
  given. By the time these open, the typed-AST sketched in
  mammouth.ai earlier the same afternoon has already turned into a
  partially-working "stage 0" C compiler under `compiler/c/`.
- **opencode** sessions on the same host — 28 sessions between
  2026-02-05 22:32 UTC and 2026-02-11 21:12 UTC. These are where
  the iterative audits, the V3 syntax refinement, the chat_client
  perf crisis, and the AISL→Sigil rename took place.
- **Public ChatGPT share links** for four pre-AISL design
  conversations the user opened to brainstorm the language shape
  *before* opening any editor. Stored verbatim in
  [`early_design_sessions/chatgpt/`](./early_design_sessions/chatgpt/)
  (4 files, ~520 KB total). They contain the OCaml-vs-alternatives
  evaluation that landed on *"OCaml is the best long-term choice;
  … C should only remain as a minimal execution core"* — the exact
  pivot that shows up in the codebase as commit `e1ba0aa` on
  2026-02-11 ("Add OCaml tree-walking interpreter") plus `30761c5`
  ("Remove C bytecode compiler"). The conversations refer to the
  project as either "AISL" or "CANON," confirming they predate the
  2026-02-11 21:05 rename.

Phase 1 below opens with "the starting corpus was approximately 300
programs" without explaining where the language those programs are
written in came from. This phase fills in that week. Quotations
below are verbatim user prompts from the recovered sessions; the
prefix `[VSCode]` or `[opencode]` indicates which source. Everything
else is either a session timestamp, a git commit visible in `git
log`, or — where flagged — inference from the surviving codebase.

### Naming lineage: CANON → AISL → Sigil

The project went through three names. The lineage is documented
across the recovered chat-share artefacts:

- **CANON** was the original working name. The mammouth.ai session
  on 2026-02-05 16:11 UTC
  ([`mammouth/228580f7-…`](./early_design_sessions/mammouth/228580f7-52a4-4fec-9b8a-89ab298d37ac.json))
  literally opens with the verbatim title **"CANON Grammar
  (AI-Focused)"** as its first message — that is the primary-source
  emergence of the name, hours before any other recoverable
  artefact. CANON is also picked up in the ChatGPT design session
  [`69f5e905_…`](./early_design_sessions/chatgpt/69f5e905_ultimate_programming_language_design.md)
  (line 2877: *"I'll call it **CANON** … Canonical AI-Optimized
  Language"*). The user engaged with it through that conversation —
  some passages explicitly compare *"AISL / Canon-style s-expr"*
  (line 12874) and *"Canon / AISL"* (line 12997), treating the two
  as variants of the same idea. CANON never made it into the
  codebase; it is the conversational design-name only.
- **AISL** ("AI-Optimized Systems Language", pronounced "aisle") is
  the codebase name from the very first commit
  (`486b51e Initial commit`, 2026-02-06 19:40 UTC) and from the
  earliest log on this host (the VSCode session at 2026-02-05
  19:49 UTC opens against an already-AISL-named tree). This is what
  shipped publicly to `github.com/mlainez/aisl` and what every
  pre-rename audit and tool refers to.
- **Sigil** is the current name, in effect since the AISL→Sigil sed
  rename on 2026-02-11 between 18:41 and 20:17 UTC (see the dedicated
  subsection below). The repo at `github.com/mlainez/sigil` was
  renamed in place; old AISL-named files were either renamed
  (`aisl.opam → sigil.opam`) or content-swept (`(call …)` → flat
  syntax).

### What this phase does *not* recover

The C compiler under `compiler/c/` already exists when the first
session log on this host opens — its creation pre-dates every
recoverable artefact. The project directory itself was created on
the filesystem at **2026-02-05 19:49:06 UTC** (CET 20:49:06) and the
first VSCode Copilot Chat session opened **within the same second**.
Either the C compiler was brought to the host from another machine
just before, or it was typed/pasted in the minutes immediately before
the VSCode session opened with no chat tool involved. The
`compiler/c/` source itself does not survive in the current tree —
the OCaml pivot a week later removed it (commit `30761c5`, "Remove C
bytecode compiler") and the chronicle of its creation is therefore
the one true gap in this Phase 0.

What *is* recovered starts the moment the project's first chat tool
opens, ~5 days later than the typical "blank-page" start of a
language project.

### Day zero, afternoon: the philosophical foundations (mammouth.ai, 2026-02-05 16:11–21:06 UTC)

Before any editor opened, the user spent ~5 hours in two
mammouth.ai chat sessions establishing what the language was *for*.
Both sessions are in
[`papers/early_design_sessions/mammouth/`](./early_design_sessions/mammouth/);
the substantive philosophical content is in the second one (Claude
Sonnet 4.5, 32 messages, 16:34→21:06 UTC).

Three design directives, given verbatim, define the project:

**Directive 1 — humans don't read this code (Mistral session, U02, 16:14 UTC):**

> *"make it 100% AI optimized and don't care about human usage,
> they are not meant to read this language's code"*

This is the foundational constraint. Every later "meet halfway"
move (Phases 14, 15, 18) is a softening of this directive when it
collided with what models actually generate. But the *intent* —
optimise for AI, accept human-unreadability as a cost — is
unbroken in the codebase: Sigil today is still S-expression,
prefix-only, no infix operators, no human-ergonomic sugar.

**Directive 2 — ambiguity reduction is the value prop (Sonnet session, U01, 16:35 UTC):**

> *"This is supposed to be an AI optimized language, so AI can
> write programs reducing the risk of ambiguity that human
> readable languages cause"*

The mechanism named: explicit type annotations, canonical
representation (one way to write each thing), formal grammar.
The current codebase keeps the canonical-representation property
(via aggressive ONE WAY ONLY refactors in the AISL week — see
"The design directive" subsection below). It dropped
mandatory-explicit types when v3 syntax landed type inference for
`(set ...)` on Apr 22; only `(fn ...)` parameters still require
explicit types. The compromise: still less ambiguous than Python,
not as type-strict as the original sketch.

**Directive 3 — Sigil as the verified IR layer between AI and humans
(Sonnet session, U10, 17:10 UTC):**

> *"so aisl would be the main code generation layer of the AI
> Agent which would then translate this code into human readable
> one if necessary"*

This is *the* architectural thesis. Sonnet replied with an
explicit pipeline diagram:

```
Human Intent (NL)
        ↓
LLM (fine-tuned for AISL generation)
        ↓
AISL Code (canonical, type-safe, effect-tracked, formally verified)
        ↓                            ↓
   AISL Runtime              Human-readable view
   (direct exec)             (Python/JS/English, on demand)
```

This thesis is **half-built** in the current codebase. The
left-hand path — fine-tune LLMs to emit Sigil, run it directly via
the OCaml interpreter — is the entire Phase 3-19 story; that's the
half that worked. The right-hand path — Sigil → Python/JS/English
translation for human review — was never implemented. We didn't
need it because the agent harness (Phase 18) returns stdout, not
code; cloud orchestrators consume the *result* of Sigil execution,
not the source.

**What was sketched in U09 and never built — the safety / verifier
layer:**

The Sonnet response to U09 ("can you develop on AI agent safety?")
proposed a *type-system-enforced* effect system: every function
type carries `Pure | IORead | IOWrite | Network` annotations;
capability-restricted IO (`IORead "/home/user/*"` rejected at
compile time if the path is outside the whitelist); structural
recursion guarantees termination. None of this is in the language.

Sigil today has the same surface as a normal scripting language:
`(file_read path)` works regardless of who's calling and from
where. The "safety" we have is sandboxing the `vm.exe` subprocess
plus a wall-clock timeout. Effective for the bench harness, but
**not** the formal-verification story the original mammouth thesis
laid out.

This is the load-bearing **gap between the original thesis and the
current artefact**. It is recoverable — a runtime-enforced
declare-effects + whitelist mechanism would close most of the gap
without requiring full formal verification — and it is the most
direct lever for differentiating Sigil from "yet another scripting
language" if/when the agent-harness story gets pushed harder. See
Phase 18 for the agent-harness ambitions; Phase 19 for the
practical "meet halfway" methodology that, in retrospect, has
been retreating from this thesis ever since the first commit.

**What survived intact from the mammouth sessions:**

- S-expression syntax (still load-bearing; never went infix).
- Canonical representation (ONE WAY ONLY).
- Statically-typed function signatures (params + return).
- Polymorphic builtins on collections (defined as the design
  goal in U03's concurrency reply, retained).
- The `Result` type was *removed* on 2026-02-09 (`dd6c4e6`,
  rationale: "for LLM simplicity"). The mammouth sessions had it
  prominently; the audit decided LLMs prefer try/catch.

**What was sketched and dropped:**

| Original (mammouth, Feb 5 PM) | Current (May 2) | What happened |
|---|---|---|
| Effect annotations on function types | Not in language | Never implemented; would close the agent-harness safety gap |
| Capability-restricted IO (`IORead "/path/*"`) | Not in language | Never implemented |
| Structural recursion → guaranteed termination | Plain `while`/`for`/recursion | Drifted to general computation |
| AISL → Python/JS/English translation | Not in language | The agent harness made it unnecessary for execution; could be revived for trust UX |
| AISL → Coq/SMT-LIB export | Not in language | Wrong scope; would have been a 6-month side-quest |
| AISL → Mermaid view of control flow | Not in language | Low priority; humans rarely need this with the agent harness |
| Module system with explicit imports/exports | Module system retained | Survived |
| `Future` / `Channel` for concurrency | Process-spawn IPC + non-blocking sockets | Concurrency primitives went pragmatic, not actor-style |

The drift is a real-world version of the safety-vs-utility
trade-off every AI-language project faces: the formally-verified
small-scope option (Coq, Dafny, lean) loses to the practically-
useful broad-scope option (Python, JavaScript, today's Sigil) in
adoption every time. We took the second path. Whether to walk
some of the first path back is the open question for the next
phase.

### Day zero: 2026-02-05 evening (VSCode Copilot Chat record)

The earliest traceable activity on this host is a **VSCode + GitHub
Copilot Chat** session that opens at **2026-02-05 19:49 UTC** in the
`Projects/aisl` workspace, with the first real prompt arriving at
20:03 UTC — about 2.5 hours before the first opencode session. The
project is already named **AISL — "AI-Optimized Systems Language"**
(the README of the time noted it was pronounced "aisle") and it
already has a "stage 0" **C compiler** under `compiler/c/` (see "What
this phase does not recover" above). The opening prompt is therefore
a *fix-my-existing-thing* request, not a *let's-design-a-language*
request:

> *[VSCode] "I'm creating an AI first language that is optimized for
> AI and not for humans, I am building a compiler for it. The syntax
> is used to define the rules and the representation is as an ast as
> seen in examples, can you fix the issues with the code so the stage
> 0 compiler compiles and can be used? Check the Makefile."* —
> 2026-02-05 20:03 UTC

Over the next two hours of the same VSCode session (35 requests
total, ending 21:57 UTC) the project crosses several milestones that
later sessions take for granted: the stage 0 C compiler is fixed and
brought to a state where `aisl-run examples/test_io.aislc` runs
(req[5]); `compiler/c/` is restructured to common C conventions
(req[6]); and the user articulates the self-hosting goal explicitly:

> *[VSCode] "Now, I want to have a second stage compiler to bytecode
> and vm that is written in aisl itself, so that I can compile the
> compiler only with aisl."* — 2026-02-05 20:22 UTC

A second VSCode session starts ~2 minutes after the first closes
(21:59 → 22:29 UTC, 16 requests) and continues the self-hosting
attempt. Its final prompt is *"cleanup the files and verify that all
compilers are still working and that example files are on v3, also,
rename GRAMMAR_V3 to GRAMMAR"* — confirming V3 was already a draft
on disk by Feb 5 night (the Feb 9 session further down refines V3,
it does not introduce it).

The first **opencode** session on the same project opens at **22:32
UTC** of the same day — three minutes after the second VSCode session
ends. Its prompt is the post-VSCode summary of state:

> *[opencode] "I have created an AI optimized language called AISL,
> I have a compiler written in C for it. There are examples in the
> examples folder and the grammar is described in the grammar.md
> file. There is a very basic AISL compiler written in AISL but I
> need it to be a full featured compiler like the one written in C.
> Any reference of code related to the V2 syntax should be
> removed."* — 2026-02-05 22:33 UTC

So by the end of day zero two things are already in motion: a
self-hosting effort (started ~20:22 UTC), and a syntax migration
from V2 to V3 (V3 grammar drafted in `GRAMMAR_V3.md` by ~22:29
UTC, with V2 traces being removed in parallel).

(Timezone note: VSCode Copilot Chat stores `creationDate` and
per-request `timestamp` as Unix epoch ms — UTC at the wire level. The
host clock is CET/+0100, so the local-time stamps shown in the VSCode
UI are 1 hour ahead of the values quoted here. All times in this
section are normalised to UTC.)

### The design directive: "optimized for AI, not for humans"

The clearest articulation of the project's design philosophy lives
in those two VSCode sessions, not in any later doc. The user gives
the directive twice in the first VSCode session and reinforces it
five times in the second:

> *[VSCode A, 21:30 UTC] "It's supposed to be an AI optimized
> language, built by an AI, so if you think changes should be made
> to it so it's easier for you, you should also iterate on the
> grammar and make that language as easy for you as possible to
> generate correct code."*

> *[VSCode A, 21:55 UTC] "If there is anything in the language
> syntax that is getting in your way, you are obliged to improve the
> syntax so it becomes easy for you, you shouldn't care that a human
> can read the syntax, it's only for use by AI agents."*

> *[VSCode A, 21:57 UTC] "You must build a real aisl compiler in
> aisl itself that can compile the programs in /examples and if
> along the way the language syntax makes it complicated for you to
> create correct code, you should simplify the syntax or adapt it
> for you only, you shouldn't care that humans can read it, it is
> not a language that should be designed for human readability, but
> for AI code generation."*

> *[VSCode B, 22:06 UTC] "If the let syntax and nesting is an issue,
> fix it in the syntax, make your life easier!"*

> *[VSCode B, 22:11 UTC] "You are fighting again the language
> syntax, change it so it becomes easier for you."*

> *[VSCode B, 22:13 UTC] "I need you to change the language syntax
> as you go as soon as you are fighting the language itself, it
> should become a language where you don't need to retry to have
> correct code."*

> *[VSCode B, 22:16 UTC] "No, you shouldn't try to support old
> syntax, you are allowed to make drastic changes to the language
> syntax, but you ought to make changes in GRAMMAR.md and to the
> existing c compiler, don't forget to also change the examples and
> stdlib."*

The repetition is not accidental — Copilot kept defaulting to
human-language conventions, and the user kept correcting it back. The
operational pattern this set up — *the language admits whatever shape
the model finds easiest, then maps to canonical implementations* — is
the one Phase 17 retrospectively names "meeting halfway" and which
`papers/MEETING_HALFWAY.md` documents in full. The seed of that
pattern is here, on day zero.

### Self-hosting in AISL: pushed hard, did not deliver

The original goal of the very first prompt was to grow the basic
AISL-written compiler to feature parity with the C compiler. Todos
recorded against opencode session `ses_3d010675c` confirm this was
still being pursued days later: *implement lexer in AISL for v3.0
syntax, implement parser, implement AST data structures, implement
bytecode generator, implement bytecode output writer.*

The VSCode log makes the failure mode visible. Across the second Feb
5 session and parts of the first, the user's prompts escalate as
Copilot keeps producing scaffolds that don't actually run:

> *[VSCode A, 21:49 UTC] "But it does nothing, there is no lexer, no
> codegen etc... are these not needed?"*

> *[VSCode A, 21:56 UTC] "But there is nothing, please stop saying
> you're done when you can't even compile a basic aisl program."*

> *[VSCode B, 22:23 UTC] "Ok, but this compiler is useless, I need a
> real one that can compile a real program and not hardcode stuff,
> I also need you to stop creating additional md files."*

> *[VSCode A, 21:46 UTC] "Stop creating additional documents, don't
> create any md files anymore and focus on making the aisl compiler
> work like the C compiler."*

By the end of the second VSCode session the self-hosted compiler is
stub-grade. The opencode logs of the next several days continue to
list self-hosting as an active todo, but no surviving artefact in the
current repo implements a self-hosted compiler — what remains under
`interpreter/` is OCaml. The OCaml pivot on Feb 10 (next subsection)
made the self-hosting goal moot, but in retrospect it had already
failed on day zero: the directive to "build a real compiler in aisl
itself" outran what Copilot could deliver against a syntax that was
itself being redesigned in the same conversation.

The directive to *stop creating .md files* survives into the present
codebase: it is restated in CLAUDE-style instructions and is the
reason this `papers/JOURNEY.md` (and the audits in
`papers/MEETING_HALFWAY.md`, `papers/MODEL_VERSIONS.md`, etc.) lives
under `papers/` rather than being scattered across the repo root.

### V3 syntax: drafted Feb 5 night, refined Feb 9 (token-cost-driven)

A V3 grammar already existed in draft form by the end of the second
VSCode session on Feb 5 night (the final prompt was *"rename
GRAMMAR_V3 to GRAMMAR"*). The Feb 9 opencode session below didn't
introduce V3 — it *refined* V3 with three changes that survive into
the current language: flat call arguments, no `call` keyword, and
BigDecimal as a third numeric type.

V2 syntax (the one being phased out at the start of the genesis
window) wrapped function calls in an explicit `(call ...)` form with
a bracketed argument list:

```
(call func [arg1 arg2 arg3])
```

The 2026-02-09 06:34 UTC opencode session opens by quoting an
external suggestion and turning it into a redesign brief:

> *"I have a few observations from another model: minor extensions
> could include BigDecimal type, flattened call arguments (token
> efficiency), s-expression-only representations for intent
> graphs … The argument list is wrapped in a separate array node or
> bracketed list. This is redundant from the AI's perspective; the
> model still has to generate the wrapper. Flattened form: `(call
> func arg1 arg2 arg3)` … Token savings per call: 2–3 tokens. If the
> model is generating hundreds of calls per task, this is
> cumulative: potentially 10–30% token reduction for long
> sequences."*

The same session also pushes back on `array_new` requiring a fixed
size: *"There seems to be a regular confusion with array_new that
takes a parameter, can't the vm dynamically allocate memory to the
array instead of specifying a fixed size at the beginning? Wouldn't
that be easier for LLMs?"*

A few turns later in the same session the user pushes the principle
to its conclusion:

> *"What about requiring the 'call' statement to call a function,
> can it be removed? I want the best, lowest token usage with this
> language, so anything that can remove tokens is welcome."*

The decision in that session is what the current spec records:
function invocation is implicit when the first element of a form is
neither a keyword nor a Core statement. `(func arg1 arg2)` replaces
`(call func arg1 arg2)`. The same session also adopts BigDecimal as
a third numeric type alongside int and float (it survives unchanged
into the present language as `decimal`).

**Net effect of V3:** one fewer keyword (`call` removed), one
bracket pair removed per call, dynamically sized arrays, BigDecimal
added. The token-saving rationale was explicit and quantitative.

### Core IR: from 6 statements to 5

A direct consequence of removing `call` is that Sigil-Core shrinks.
An audit session on 2026-02-07 07:55 UTC opens by asking the
explore subagent to verify *"all 6 core statements (set, call,
label, goto, ifnot, ret) implemented exactly as documented"*. The
current `SIGIL-CORE.md` lists **5** (`set`, `label`, `goto`,
`ifnot`, `ret`) and notes explicitly that *"function invocation uses
implicit syntax `(func arg1 arg2 ...)` and is not a separate
statement type."* The freezing of the IR at 5 happens in this same
week. It has not changed since.

### Why OCaml: trigger from the C VM, rationale from the ChatGPT design session

The OCaml pivot has two distinct sources in the recovered record:
the **trigger** lives in opencode, the **rationale** lives in the
ChatGPT design session.

**Trigger (opencode, 2026-02-10 06:24 UTC).** The user pastes a
`top` snapshot:

```
7816 marc  20 0  9462192   8,8g   3296 R  99,7  14,5   1:31.72 aisl-run
7804 marc  20 0  7683516   7,1g   2948 R  96,3  11,7   1:43.70 aisl-run
```

Two `aisl-run` (C VM) processes pinned at ~100% CPU and consuming
~8 GB of RAM each, running the WebSocket `chat_client` example. The
prompt: *"My virtual machine for my AI optimized language takes a
lot of resources when running the chat_client application using
websockets. I want you to optimize my vm to be more memory efficient
and take up less CPU resources."* The session does ship optimisations
to the C VM (it identifies a hard-coded 16 MB stack constant
`STACK_SIZE 16777216`; zero-timeout `socket_select` and
`tcp_receive` busy-spinning the CPU on `struct timeval tv = {0, 0}`;
arrays starting at capacity 16 and doubling; redundant string copies
in chat_client) but the patches treat symptoms — the deeper question
("is C the right host language at all?") was already answered
elsewhere.

**Rationale (ChatGPT design session, file
[`69f5e905_…`](./early_design_sessions/chatgpt/69f5e905_ultimate_programming_language_design.md)).**
The user opened a long ChatGPT conversation between the project
going public on GitHub (2026-02-06) and the OCaml rewrite
(2026-02-10), pointing the model at the existing `mlainez/aisl`
spec and asking for a host-language evaluation. The conversation
ranks Rust, OCaml, Nim and C against the AISL workload (an
interpreter of an s-expression IR, not a high-throughput numeric
runtime). The verdict is explicit (line 16785):

> *[ChatGPT] "For an AISL compiler/VM not targeting max performance,
> OCaml is the best long-term choice; Nim is the best pragmatic
> alternative; Rust is safe but slower to evolve; C should only
> remain as a minimal execution core."*

The supporting argument is that an interpreter for a typed
s-expression IR is essentially a giant `match` over an algebraic
data type — exactly OCaml's shape. The ranking summary (lines
16729–16734) credits OCaml with the best balance of *correctness, IR
modeling power, execution performance, compiler ergonomics*, and the
migration path proposed in the same conversation (lines 16770-16776)
is the literal one the codebase took:

> *[ChatGPT] "Rewrite compiler / lowering / validation in OCaml or
> Nim … Gradually shrink C to a pure VM core, move all semantics
> out."*

**Convergence (opencode, 2026-02-10 23:24 UTC).** ~17 hours after
the perf-crisis prompt, a string-naming audit session is already
inspecting *both* `compiler/ocaml/interpreter.ml` and
`compiler/c/src/vm.c` side by side for parity. From that point on
every audit session in the recovered logs treats the OCaml
tree-walking interpreter as the new primary implementation (sessions
are titled "Check C VM string ops", "Find C VM TLS implementation" —
the C path is now the *reference* being checked against, not the
production target). The C compiler tree (`compiler/c/`) was removed
shortly after — git shows commits `e1ba0aa` ("Add OCaml tree-walking
interpreter") and `30761c5` ("Remove C bytecode compiler") for the
two ends of the swap. A continuation-prompt note from a slightly
later session reads: *"The old C compiler (`compiler/c/`) was deleted
but the LSP still shows ghost errors from those files — ignore all
`compiler/c/src/*.c` errors entirely."*

The OCaml-specific properties the rewrite delivered (and the surviving
codebase reflects):

- **Garbage collection eliminates the bug class.** The 8.8 GB
  chat_client process was a manual-memory-management failure on a
  long-running WebSocket loop. OCaml's runtime removes it.
- **Pattern matching fits AST evaluation.** The interpreter's hot
  path is `match expr with | Set _ -> ... | Goto _ -> ...` —
  algebraic data types and exhaustive `match` are the natural shape
  for a tree walker, exactly as the ChatGPT evaluation predicted.
- **Tree-walking, not bytecode.** Removing the desugar + compile +
  bytecode-VM pipeline of the C path and replacing it with `eval`
  directly on the AST cut the implementation to ~2 500 lines in a
  single file (`interpreter/interpreter.ml`).
- **No build pipeline complexity.** `dune build` produces a single
  `vm.exe` that reads, parses and evaluates a `.sigil` file in one
  step.

### Cleanup rounds: the 8-Item Plan, the 14 Findings, Round 2

Once the OCaml interpreter was primary, three back-to-back cleanup
passes (visible in `git log` as commits `ef492c0` through `bbfb84f`)
brought docs and implementation into agreement:

**8-Item Improvement Plan** (token efficiency, ergonomics):

1. Rewrote `.aisl.grammar` to ~196 lines with accurate builtin signatures.
2. Added `(cond)` flat multi-branch conditional.
3. Added `argv` / `argv_count` builtins.
4. Promoted commonly-needed string ops (`starts_with`, `ends_with`,
   `contains`, `trim`, `replace`) from stdlib to builtins.
5. Added `floor` / `ceil` / `round`.
6. Fixed `string_slice` bugs in `http.aisl`.
7. Added array literal `[1 2 3]` and map literal `{"k" "v"}` syntax.
8. Removed ~50 old aliases from `eval_call`.

**First Audit — 14 fixes** (commit `f8a5ea7`): the most consequential
finding was that `LANGUAGE_SPEC.md` still used the V2 `(call ...)`
syntax in 168 places — anyone following the spec would produce code
that failed at runtime. The audit also revealed 6 phantom stdlib
modules (documented but not implemented) and 7 real but undocumented
modules; the fix brought the documented count from a fictional 13 to
a truthful 14. Several builtin signatures were corrected
(`process_kill`, `socket_select`, `file_write`/`append`,
`dir_create`/`delete`, `process_exec`).

**Round 2 audit** (commits `bbfb84f` and adjacent): deeper fixes
including `AGENTS.md` still containing 48 `(call ...)` occurrences
and stale "if/else not yet supported" claims for features that had
been fully implemented.

The pattern across all three rounds is consistent: docs lagged the
implementation; the audits reconciled them.

### The AISL → Sigil rename (2026-02-11, between 18:41 and 20:17 UTC)

Two timestamps bracket the rename precisely. The last session whose
user prompt still says *"AISL"* and references the old project name
in path form is the audit started at **18:41 UTC**. The next session,
started at **20:17 UTC**, opens with: *"you have access to codellama
running in ollama on the local network, I want you to benchmark some
token consumption on code generation of the same use case both with
python bash and **sigil**"*. From that point on every session uses
the new name.

The rename mechanics survive in the log: a single sed-driven sweep
over every `.md` file in the repo (over 50 substitutions in two
`find … -exec sed -i …` invocations), preserving content while
swapping the name. Notably the script replaced the old "About the
Name" block:

- Old: *"AISL = AI-Optimized Systems Language … AISL sounds like
  'aisle' — a clear path forward for AI code generation."*
- New: *"Sigil — A symbolic language for AI code generation. Also:
  Sigil: a symbolic mark with power."*

Two things are worth saying about *why* the rename happened when it
did. **First**, the rename coincides with a project pivot visible in
the same evening's session titles: the immediately following sessions
are *"Inventory Sigil training data"*, *"Survey all .sigil files"*,
and four parallel *"Write synthetic batch N"* sessions run by general
subagents. The project stopped being primarily a language-design
project and started being a corpus + benchmark project for
fine-tuning local LLMs. The rename and the pivot happened together.
**Second**, the recovered log does *not* contain an explicit "I want
to call it Sigil because …" conversation — the choice of name was
made outside opencode, and only the rename mechanics survive.

The git log captures the same transition in two commits: `091cbc4`
("Rename language from AISL to Sigil") and `16181b8` ("Complete
AISL→Sigil rename: update dune build config and rename opam file").
The opam-package rename (`aisl.opam` → `sigil.opam`) is recorded as
a todo on `ses_3b9c72439`: *"Rename `interpreter/aisl.opam` →
`interpreter/sigil.opam` and update content."*

### Bridge to Phase 1

Phase 1 below opens with *"the starting corpus was approximately 300
programs … generated by Claude Opus from a hand-curated set of task
descriptions, validated against the Sigil interpreter, and retained
only when output matched expected."* The recovered logs let us name
where that corpus came from: the four parallel *"Write synthetic
batch N"* sessions on 2026-02-11 21:06–21:07 UTC, the *"Inventory
Sigil training data"* session that immediately preceded them, and
the *"Read failed attempts, create corrections"* session at 21:12
UTC. Those six sessions are the boundary between pre-corpus genesis
and the JOURNEY narrative proper.

## Phase 1: The starting point — why Sigil?

Sigil exists as a designed-for-LLM language. The argument: a human
language designer optimising for an LLM-as-primary-programmer should
make different choices than one optimising for human ergonomics.
Sigil's specific commitments are:

- **Minimal-token output.** Aliases (`len`, `str`, `fmt`, `+`, `-`),
  polymorphic builtins, no boilerplate (`$0` instead of `sys.argv[1]`).
- **Flat S-expression grammar.** No statements vs. expressions
  distinction; no precedence rules to memorise; the grammar fits in
  a single file.
- **Polymorphic on collection types.** Most builtins work uniformly
  on strings, arrays, and maps.
- **An OCaml interpreter** (the artefact in `interpreter/`) that
  validates programs end-to-end and runs them with deterministic
  semantics.

The starting corpus was approximately 300 programs. Origin: not
hand-written, but generated by Claude Opus from a hand-curated set of
task descriptions, validated against the Sigil interpreter, and
retained only when output matched expected. The human author
designed the language, the test harness, and the curation policy;
the LLM produced the programs. This matters for the integrity of
later claims about "fine-tune teaches the language" — the corpus was
already LLM-shaped by construction.

A first benchmark in 2026-01 against equivalent Python implementations
showed Sigil tokens ≈ 0.96 × Python tokens on a 45-task suite. Sigil
won marginally on token efficiency. This was the seed result that
motivated investment in fine-tuning.

## Phase 2: The Sonnet-writes-Sigil era (Apr 21-23 2026)

There is a ~10-week gap in the git history between **Feb 11**
(AISL→Sigil rename) and **Apr 21** (work resumes). During this gap
the language sat. When activity restarts, the work shape is
completely different: instead of language design, it is **head-to-
head benchmarking of Sigil against Python/JavaScript/Go using
frontier models (Sonnet) as the code generator**.

The earliest Claude Code session captured in the local logs is
`0fdec318-d2d2-40c3-b78b-8a42a2317ceb.jsonl` at **2026-04-21 12:40**.
Its first user turn is verbatim:

> *"You are a Python code generator. Generate ONLY a complete Python
> program. The program receives input via sys.argv[1], sys.argv[2],
> etc. … Write a program that takes integer n as first command-line
> argument and prints numbers from 1 to n, one per line. For
> multiples of 3 print 'Fizz', for multiples of 5 print 'Buzz', for
> multiples of both print 'FizzBuzz'."*

Ten Claude sessions were spawned in the same minute, one per
language. This is the **multi-language FizzBuzz / token-efficiency
benchmark** — the experimental harness in which Sonnet was asked
to write the same task in Python, JavaScript, Go, and Sigil, and the
generated programs were compared on token count, output correctness,
and (informally) on whether the model needed prompt scaffolding to
produce valid code.

This is the era the user referred to as **"the first experiments
where we analysed how Sonnet was writing Sigil code, before the
together.ai era."** It mattered because:

1. **It was the first time Sigil was used as a target language by
   a model that had not been fine-tuned on it.** Sonnet knew Python,
   JS, and Go from pretraining; Sigil it had to learn from the
   prompt (the `.sigil.grammar` file plus a few examples).
2. **The failure modes Sonnet exhibited became the first feedback
   signal about the language design.** Two specific shapes recurred
   across sessions: (a) Sonnet reaching for built-ins that did not
   exist (e.g., `string_length`, `array_count`), which motivated
   adding the canonical short aliases; (b) Sonnet generating
   verbose `(set …)`/`(set …)`/`(if …)` chains where a
   token-efficient `(fmt …)` or `(cond …)` would do, which
   motivated the Apr 22-23 builtin sweep.

The Apr 21-23 commits read as a direct response to those Sonnet
sessions:

- **2026-04-21 12:18** `for` counting loop + type-free reassignment
  (`a6a5257`).
- **2026-04-21 12:19** "Rewrite stdlib and examples for **token
  efficiency**" (`ea2b441`).
- **2026-04-21 22:23** "Add 16 new builtins: `arg_int`/`str`/`float`,
  `str`, `len`, `string_chars`, char ops" (`929dbd9`) — the canonical
  short aliases land here. This is also when the Sonnet-driven
  feedback first becomes a concrete corpus extension.
- **2026-04-22 21:45** `fmt`, `in`, short aliases, implicit main
  return (`600033f`).
- **2026-04-22 21:45** **top-level script mode** + `$N`/`#N` argv
  shorthand (`821d746`). Removes the `(fn main () …)` boilerplate
  for one-shot scripts; programs that previously needed 5 tokens of
  ceremony now need zero.
- **2026-04-22 22:03** **variadic `println`/`print`** (`6c9477a`).
- **2026-04-22 22:43** `filter`/`map_arr`/`reduce` + implicit
  return-of-last-expression (`e583673`).
- **2026-04-22 22:53** closures, `first`/`last`, negative indexing
  (`6c0db2f`).
- **2026-04-22 22:56** "**Modernize tests + corpus: drop type
  annotations, replace `string_format` with `fmt`**" (`14595dd`) —
  the corpus is rewritten to match what Sonnet actually wants to
  emit, not what AISL syntax demanded.

By **2026-04-23** the work has shifted from one-off Sonnet
benchmarks to an automated **feedback loop** that runs a tier of
tasks against the model, identifies builtins that would have
shortened the generated programs, and adds them:

- **2026-04-23 20:21** "Persist benchmark tooling (feedback loop,
  task bank, analysis scripts)" (`c28256f`).
- **2026-04-23 20:42** "Add polymorphic builtins **surfaced by
  tier-2 loop**: `rev`, `swapcase`, `title`, `uniq`, `parse_pairs`"
  (`6f3a018`).
- **2026-04-23 20:51** "Add `count`, `max_by`/`min_by`, `digits` —
  close tier-2 remaining losses" (`13c20a0`).
- **2026-04-23 21:03** "Add `counter`/`sort_by`/`group_by`/
  `transpose` — tier-3 primitive batch" (`1267080`).
- **2026-04-23 21:20** "Add `diff`/`inter`/`union`/`fmt_float`/
  `slice`/`merge`/`range` — tier-3 close batch" (`f597037`).

This is the moment the loop closes: **the language is now being
shaped by what frontier models try to do with it, not by a priori
design intuition.** Every builtin added in this 48-hour window has a
specific origin in a specific Sonnet session that wanted it.

The Sonnet-as-author phase produced two pieces of knowledge that
made the Phase 3 cloud fine-tunes possible at all:

1. **A short-alias surface that Sonnet would actually use.** The
   fine-tune corpus that became `qwen-sigil-v3/v4/v5` is built on
   top of this surface. Without the Apr 21-23 builtin sweep, the
   corpus would have been full of verbose `string_length` /
   `array_count` shapes that LLMs resist generating, and the
   fine-tune would have been teaching the model two languages at
   once.
2. **The empirical discipline that powers the rest of this paper.**
   The pattern set in this phase — "let the model fail, observe the
   shape of the failure, change the language to remove the failure
   class" — is the same loop applied later to RAG seeding (Phase 7),
   to corpus refresh (Phase 15), and to the paren-balancer + PCRE
   swap (Phase 18). The methodology was forged
   here.

What this phase is **not**: it is not yet a fine-tune. Sonnet is
still being asked to write Sigil from a system prompt + grammar,
not from learned weights. The first cloud fine-tune (`sigil-v3`)
does not arrive until Phase 3 below. But by the end of Apr 23 the
language had stabilised enough — and the corpus had grown LLM-shaped
enough — that fine-tuning was finally a sensible next step.

## Phase 3: Cloud fine-tunes (sigil-v3, v4, v5) — what worked and didn't

### sigil-v3 / v4: Qwen3-Coder-30B-A3B

Trained on together.ai. LoRA r=64, α=128, all-linear, lr 1e-5,
3 epochs. Producible Sigil but the inference cost on together.ai
(dedicated 2× H100 endpoints, on-demand) made iteration expensive.

### sigil-v5: Qwen2.5-7B-Instruct (the cloud success)

Same training corpus as v3/v4 (around 153K tokens at the time).
Trained on Qwen2.5-7B-Instruct (NOT Coder — coder family unavailable
for fine-tuning on together.ai, see §1.2 below). LoRA r=64, α=128,
all-linear. This produced a coherent Sigil-writing model.

**Key finding from v5:** the `all-linear` LoRA target (k/o/q/v
projections AND gate/up/down MLP projections) was essential. v3/v4
had the same target but on a different base; the combination was
what worked.

### Failed attempts that the chronology obscures

1. **sigil-v6 on Qwen3-Coder-30B-A3B-Instruct.** Together.ai locks
   the LoRA scope on this base to attention only (`k_proj,o_proj,
   q_proj,v_proj`). The MLP projections — which are what teach
   token-level vocabulary like "use `(println x)` instead of
   `(print x)`" — are not trainable. The result: a fine-tune that
   scored 0/8 on trivial Sigil tasks because the model retained the
   Coder base's strong Python/JS priors. Endpoint cost ate the
   credit budget. Postmortem: this attempt was the proximate
   reason for moving the work local.

2. **sigil-v7 on Qwen2.5-7B-Instruct (retry of v5 with bigger
   corpus).** Blocked at launch by `402 insufficient_balance`
   from together.ai. Never trained.

3. **Multiple attempted bases**: probing showed that the entire
   Qwen2.5-Coder family (1.5B / 3B / 7B / 14B / 32B Instruct +
   base) was unavailable for fine-tuning on together.ai as of
   2026-04-29, despite being listed in the model catalog. This is
   probably a service-tier restriction or a quiet deprecation; we
   confirmed via direct API probes.

The cloud-fine-tune route had two structural constraints —
restricted LoRA scope on coder bases, and per-iteration cost — that
made it the wrong path for this specific research. The right
question became: can we do this locally?

## Phase 4: Local infrastructure — corpus extender, RAG, and the tooling

While cloud fine-tunes were running, a parallel track built the
local pipeline that would later replace them:

### 2.1 The corpus extender

`benchmark/corpus_extender.py` is a parallel pipeline that:

1. Takes a task spec (id, description, args, expected output, Python
   reference)
2. Verifies the Python reference produces the expected output
3. Asks an LLM (initially Opus, later qwen-sigil locally) for a
   Sigil version
4. Runs the Sigil version through the interpreter
5. Compares stdout to expected
6. Retries with diagnostic feedback if it fails
7. Falls back to a heavier model on hard cases
8. Saves only validated programs

This is the primary mechanism by which the corpus grew from ~300
programs to today's 1900+. Every entry is interpreter-validated.

### 2.2 The RAG layer

`benchmark/rag.py` builds a local vector index over the corpus.
Embeddings are produced by `nomic-embed-text` running locally via
ollama (768-dim, ~270 MB, $0/call). Retrieval is cosine-similarity
top-K with a configurable `min_score` floor. The index covers the
user-description side; programs are retrieved by descriptional
similarity.

The RAG layer is independent of the fine-tune. Even an un-tuned
local model benefits from RAG because the few-shot block primes the
model with valid Sigil structure.

**Dead end:** an early version of the corpus extender used Sonnet
as a "hint coach" — generating one-line fix hints when the local
model's output failed validation. This produced about 30 hint
recoveries on early datasets, then plateaued as Sonnet's hint
quality degraded under repeated similar prompts. The technique
remains in the codebase as `gen_hint` but is rarely used; the
direct retry-with-stderr path performs comparably without the
cloud call.

### 2.3 The 10-iteration measurement loop

`benchmark/rag_loop.py` runs a 100-task benchmark structured as 10
iterations of 10 tasks each. Each iteration uses a different task
family (text formatting, numeric, set ops, parsing, state machines,
distance/similarity, paths, bit ops, combinatorics, misc). All 100
tasks are NEW — they do not appear in the training corpus and are
not derived from corpus tasks.

The loop reports per-iteration: A (no RAG, 1-shot), B (with RAG,
1-shot), and net delta. Aggregate scores are over all 100 tasks.

This is the framework underlying every accuracy claim in the work.
Every reported pass-rate cites the rag_loop output.

## Phase 5: Six retrieval-tuning rounds and one bug fix

The first systematic experiment was on the un-tuned 32B base. Six
rounds of varying RAG knobs (k, MMR λ, similarity threshold) on the
same 10 tasks. Results plateaued at +2 net delta vs no-RAG,
oscillating between flips on different tasks.

Manual inspection of retrievals revealed the problem:
**`build_corpus.py` was discarding the rich descriptions from
`generated_tasks.jsonl`** and replacing them with filename
templates. Every companion spec we'd carefully described to mirror
the failing task's description was indexed under "Write a Sigil
program that implements X" instead of its real description.

The fix was a single function in `build_corpus.py` that prefers the
spec's `desc` over the filename template. After this fix:

- Round 0 (un-tuned 32B + RAG on the original 10 tasks): 4/10 → 8/10
- The retrieval similarity scores went from 0.73-0.78 to 0.90+ for
  tasks with description-mirror companions in the corpus

**Lesson:** the retrieval pipeline's effectiveness was capped by an
upstream bug, not by retrieval policy. The right diagnostic was to
print the top-5 retrievals for failing queries — not to tune k or
MMR. We should have done this in round 1, not round 6.

Cataloguing this dead-end matters because it changed the rest of
the work. Without it, we would have plateaued at +2 net delta and
concluded RAG was barely useful.

## Phase 6: The 10-iteration loop on un-tuned 32B + RAG

After the description-discard fix, we ran the 10-iteration loop on
the un-tuned 32B base + RAG. Result: 71/100. This becomes the
baseline against which all subsequent fine-tunes are measured.

Across the 10 iterations, we accumulated 14 language fixes
(philosophy-preserving additions) prompted by failure patterns the
benchmark surfaced:

| Iteration | Failure surfaced | Language addition |
|---|---|---|
| 1 | `for-each` on string fails | string iteration in `for-each` |
| 1 | `(for-each c char s)` mis-parsed | `char` as type alias |
| 3 | `keys`/`values` undefined | aliases for `map_keys`/`map_values` |
| 3 | `(- v)` unary minus fails | unary form added to `sub` |
| 8 | `(pow 2 16)` returns float | int-int polymorphism on `pow` |
| 8 | bit-op aliases (`band`, `xor`, etc.) | added |
| 8 | `(do ...)` / `(begin ...)` as sequence block | added |
| 8 | OCaml crash on `string_of_value_type` | fix VClosure/VBuiltin cases |
| 9 | 4-arg `for` mis-parses 3-arg form | revert; add `for-step` instead |
| pre-loop | `slice` end-exclusive convention unclear | grammar header docs it |
| pre-loop | `sort_by` returns instead of mutates | now mutates input ref like `sort` |
| pre-loop | 3-arg `if` (Lisp shape) | accepted alongside `(else …)` form |
| pre-loop | `string_repeat` builtin | added |
| pre-loop | top-level bare identifiers reject | parser guard |

Each fix was documented in commit messages with: the failure pattern
observed, the number of distinct tasks where it occurred, the model's
specific reach, the fix, and the regression-sweep result. None of
these fixes break previously-working corpus.

## Phase 7: Local fine-tune on Qwen2.5-Coder-3B (proof of concept)

The 3B target was chosen because un-quantized weights fit in 16 GB
VRAM with room for LoRA, gradients, and activations. The 7B base
needed 4-bit quantization (QLoRA), which had additional ROCm/RDNA3
quirks we wanted to defer.

### 5.1 RDNA3 numerics gotchas

The fine-tune ran into two RDNA3-specific issues that ate ~1 hour
of compute before being diagnosed:

- **bf16 + SDPA on Navi31 produces NaN gradients at ~step 50.** The
  PyTorch warning ("Memory Efficient attention on Navi31 GPU is
  still experimental") flagged this, but the symptom was loss
  collapsing to 0 with grad_norm NaN, which looked like a learning-
  rate problem. Lowering LR didn't help. The fix was switching to
  fp16 + eager attention.
- **Initial PyTorch ROCm 6.2 install crashed with "HIP error:
  invalid device function."** The pre-built wheels target gfx1100
  but the 7800 XT is gfx1101. The standard fix is
  `HSA_OVERRIDE_GFX_VERSION=11.0.0` to force the system to claim
  gfx1100. This kicked the wheels into compatible kernels and
  training proceeded normally.

Both gotchas are documented in the fine-tune script and in
`benchmark/RAG.md`. The combination of fp16 + eager + HSA_OVERRIDE
made the fine-tune track stable.

### 5.2 Result on the 100-task suite

| Configuration | A (no RAG) | B (with RAG) |
|---|---|---|
| Un-tuned Qwen2.5-Coder-3B | 10% | 29% |
| **Fine-tuned Qwen-Sigil-3B** | **43%** | **48%** |

The fine-tune lifted A from 10% to 43% — +33 percentage points from
training alone. RAG's marginal contribution shrank from +19 pp on
un-tuned to +5 pp on fine-tuned: the LoRA absorbed most of what RAG
was teaching.

**Crucially:** fine-tuned 3B (no RAG) ≈ un-tuned 32B (no RAG). A
10×-smaller model with the right LoRA matched the bigger model's
baseline. This was the validation that local LoRA was a serious
path.

## Phase 8: 7B QLoRA — the hard win

After the 3B success we wanted 7B for the capacity headroom. 7B BF16
weights are 14 GB at idle, leaving no room for LoRA gradients on a
16 GB card. QLoRA (4-bit base + LoRA on top) was the only way.

### 6.1 bitsandbytes-rocm probe

We probed bitsandbytes 4-bit on the 7800 XT before committing. With
`HSA_OVERRIDE_GFX_VERSION=11.0.0` set, a 4-bit `bnb.nn.Linear4bit`
forward pass produced correct output. Loading the full 7B in 4-bit
used ~5.6 GB at idle, leaving ~10 GB for training overhead.

### 6.2 Numerics gotcha #2

The first QLoRA attempt with fp16 compute reproduced the NaN
gradient problem at step 1 (not step 50 — earlier this time). Root
cause: bnb 4-bit + fp16 has a known numerical interaction. The
QLoRA standard recipe uses bf16 compute for this reason. Switching
`bnb_4bit_compute_dtype=torch.bfloat16` and `bf16=True` in the
trainer fixed it. (The earlier "bf16 unstable on RDNA3" issue was
specific to bf16 + SDPA on UNQUANTIZED weights; the 4-bit base
attenuates the instability enough that bf16 compute works.)

### 6.3 OOM and config tightening

First run: r=32, max_seq=2048 → OOM at step 1. Reduced to r=16,
max_seq=1024, set `PYTORCH_HIP_ALLOC_CONF=expandable_segments:True`,
and explicitly killed the ollama runners that were holding ~5 GB
VRAM in the background. After that the run fit at 99% VRAM
utilization with batch_size=1, grad_accum=8.

### 6.4 Result on the 100-task suite

| Configuration | A | B |
|---|---|---|
| Un-tuned Qwen2.5-Coder-7B | 15% | 48% |
| **Fine-tuned Qwen-Sigil-7B** | **56%** | **74%** |
| Un-tuned Qwen2.5-Coder-32B + RAG | 40% | 71% |

**The fine-tuned 7B + RAG (74%) beats un-tuned 32B + RAG (71%)** on
the same benchmark. With a 2-shot retry pipeline the 7B reaches
**79%**.

This is the headline result that the rest of the research program
extends.

## Phase 9: Sigil vs Python on the same model

A separate experiment ran the same fine-tuned 7B on 40 tasks (the
iters where it excelled), generating *both* Sigil and Python
solutions for each. Result:

```
Fine-tuned 7B writing Sigil + RAG:    31/40 (78%)
Fine-tuned 7B writing Python (raw):    4/40 (10%)
```

The LoRA flipped the model's "default language." Investigation
showed the Python failures were not absence of Python knowledge —
the model still produced plausible one-liners — but the LoRA had
shifted the model's bias toward Sigil's minimal-token output style,
causing it to skip Python boilerplate (`import sys`) on most calls.

The un-tuned 7B baseline on the same 40 tasks: 50/50 split between
Sigil and Python. The LoRA caused the asymmetry, not pre-existing
weakness in either language.

**Implication:** for tooling-script generation specifically, a
fine-tuned local 7B writing Sigil produces more correct programs
than the same model writing Python — and at a much lower accuracy
than off-the-shelf 7B writing Python (50%). The DSL-specialisation
trade is positive even at this scale.

## Phase 10: Sonnet partial benchmark for cloud comparison

To answer "how far is local Sigil-7B from cloud frontier?" we ran
Sonnet on the first 23 of 100 tasks (using session-resumed CLI calls
to avoid resending the grammar each time). Result: 21/23 A pass, 22/23
B pass — roughly 91-96% accuracy. The trend was clear without
finishing.

The interesting comparison isn't "can local match cloud" (it can't)
but "where does the trade-off land?" Sonnet at $0.20-0.40/call vs
local Sigil-7B at $0/call, ~5s/call vs 5-15s/call, with a 17-22 pp
accuracy gap. For batch tooling work where outputs are validated
before use, the trade favours local. For interactive UX, cloud
wins.

The Opus run was deliberately not executed: it would cost $50-100
to confirm "frontier wins big" which was never in question.

## Phase 11: v2 → v3 → v3.1 — chasing iter 6 and what RAG can / cannot fix

After the Phase 10 run landed v2 at A 64 / B 70 with default RAG knobs
(B 76 with tightened RAG: k=3, ms=0.85, t1=0.88), failure analysis
on iteration 6 (the string-pair-similarity cluster) showed that five
of its B-failures shared a common shape:

- `longest_common_suffix_two` — manual reverse-index loop tripping on
  `(sub a b c)` arity errors
- `edit_one_apart` — model reaching for `diff` thinking it does
  Levenshtein
- `is_subsequence` — two-pointer loop with no clean `break`
- `common_chars_count` — manual map+delete with off-by-one
- `is_rotation_of` — recoverable but unstable

The "meeting halfway" response was language change, in three layers:

1. **Six new builtins**: `common_prefix`, `common_suffix`, `is_subseq`,
   `is_rotation`, `edit_distance` (alias `levenshtein`),
   `common_chars`. Each makes a 14-line synthesis attempt collapse
   into one builtin call.
2. **Variadic `sub` / `mul`**: `(sub len_a i 1)` now means
   `len_a - i - 1` rather than an arity error.
3. **Contextual error messages** for the high-frequency ops where
   models trip on type/arity (sub, mul, div, mod, eq/ne/lt/gt/le/ge,
   abs, min, max, index_of, slice, not). `"Invalid arguments to sub"`
   became `"sub: numeric expected, got (int int int)"` — actionable
   on retry.

**The error-message change alone (no retraining)** lifted v2's
multi-attempt B from 82% → **85%**. Shot-3 went from 0/24 recoveries
to 4/24. Free +3 pp.

**v3 (failed)** retrained on the expanded corpus (2070 entries, +50
specs targeting the new builtins). The first run NaN'd at step 60
with v2's lr=1e-4 — bf16 forward overflow on a long sequence pack
during warmup, masked in v2 only by lucky shuffle order at the
prior corpus size. Wrong diagnosis: dropped LR to 2e-5; that
prevented NaN but under-trained. Result: A 46 / B 62 — **−14 pp
regression**. Won the targeted bet (iter 6 +2 pp) and lost the broad
coverage everywhere else.

**v3.1 (the right run)** re-diagnosed the NaN as a corpus issue, not
an LR issue. Filtered the corpus to 50 ≤ tokens ≤ 800 (drops 24 of
2070 — auto-generated test specs from `tests/`). Trained at v2's
exact hyperparameters: lr=1e-4, max_grad=1.0, warmup=0.1. Final mean
loss **0.30** (deeper than v3's 0.56 and matching v2). Result:

| Setup | A | B 1-shot | B + retry + new errors |
|---|---:|---:|---:|
| v2 tight RAG | 64 | 76 | 85 |
| **v3.1 tight RAG** | **65** | 73 | **84** |

**Net: tied within noise.** But the per-iteration shape differs.
v3.1 lifts iter 6 from 6→8/10 (+2 pp from new builtins), iter 2 +2,
iter 7 +1. It loses on iter 4/5 — math-shape tasks where v2 had
memorized specific solutions. The retrain *redistributed* failure
mass toward the deployment shape (host tooling) and away from
combinatorics.

**The lesson on corruption diagnosis**: when QLoRA NaNs after a
1-step loss spike (2.9 → 5.0 → inf), it is bf16 forward inf, not LR
too high. `clip(grad)` does nothing once inf is present —
`clip(inf) = nan` propagates. The fixes that matter, in order:
filter long sequences out of the corpus, lower max_seq, then lower
LR. The wrong knob (lr) costs 14 pp.

**The lesson on RAG as a recovery lever**: tried three different RAG
configurations on v3.1 to see if knob-tuning could recover the
iter 4/5 regressions:

| Config | B 1-shot |
|---|---:|
| Tight (k=3, ms=0.85, t1=0.88) | 73 |
| Loose (k=5, ms=0.65, t1=0.78) | aborted (3 B→A− flips on iter 2) |
| MMR diversified (k=5, ms=0.85, λ=0.7) | 72 |

**RAG can't fix weight-level forgetting.** When the LoRA confidently
synthesizes wrong code, in-context examples either get overridden or
actively conflict with the deeper LoRA. The right levers for the next
round are corpus expansion (general-purpose specs) and selective LoRA
target modules (not all 7), not RAG knob-twiddling.

## Phase 12: Where we are now

| Artifact | State |
|---|---|
| Sigil interpreter | 14 fixes + 6 string-pair builtins (`common_prefix/suffix`, `is_subseq`, `is_rotation`, `edit_distance`, `common_chars`); `sub`/`mul` variadic; contextual error messages on the high-frequency ops; `--lint` mode |
| Training corpus | 2046 entries, ~180K tokens; pre-filtered to 50 ≤ tokens ≤ 800 to avoid bf16 forward overflow during QLoRA |
| RAG index | 2070 entries, 768-dim, `nomic-embed-text` |
| Fine-tuned 3B adapter | 240 MB safetensors, 120 MB GGUF |
| Fine-tuned 7B adapter (v1) | 160 MB safetensors, 80 MB GGUF |
| Fine-tuned 7B adapter (v2) | same shape; deeper than v1; tight-RAG B 76, retry 85 |
| **Fine-tuned 7B adapter (v3.1)** | same shape; deeper than v2 (loss 0.13 vs 0.17); tight-RAG B 73, retry **84**; iter 6 (string-pair) +2 pp over v2 |
| 100-task benchmark | reproducible via `rag_loop.py` (env-driven RAG knobs) |
| Cloud frontier comparison | partial Sonnet run; 30-task tooling run (Sonnet 29/30, $0.085) |
| Stream C tooling study | v2: 20/30 (67%); v2 + new-RAG + aug-header: 19/30 (lost `wc_l`); v3.1: 16/30 (lost 5). v2 baseline remains deployment default. |
| Confidentiality analysis | drafted in `papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md` |
| Meeting-halfway design doc | drafted in `papers/MEETING_HALFWAY.md`; v3.1 confirms the principle (iter 6 +2 pp from new builtins) |
| Agentic workflow guide | drafted in `agent_workflow/README.md` |

## Phase 13: What this work is NOT

For credibility, the same explicit non-claims that appear in the
research plan apply here:

- This is NOT a claim that local Sigil-7B is a general Python
  replacement.
- This is NOT a claim that cloud LLMs are universally bad.
- This is NOT a claim that 100% accuracy is achievable on this
  benchmark by any model (it isn't — even Sonnet got 22/23 on its
  partial run).
- This is NOT a claim about workloads outside host-tooling shape
  (architecture, refactoring, multi-file work).

The validity of the conclusions is bounded to the workflow, the
benchmark, the hardware, and the model sizes tested.

## Phase 14: Open work

What the research plan (`benchmark/RESEARCH_PLAN.md`) commits to
addressing next:

1. **Corpus expansion (general-purpose specs)** — currently 2046
   entries, mostly task-shaped. Adding 200-500 common-pattern specs
   (string-utility, number-utility, control-flow shapes) would let a
   v4 retrain absorb the new builtins **plus** retain v2's broad
   memorization that v3.1 partially shed.
2. **Selective LoRA** — v3.2 with `target_modules=["q_proj","v_proj"]`
   only (instead of all 7) might absorb new patterns without
   overwriting v2's general ones.
3. Re-run a real-task deployment study against actual shell-history
   tooling tasks to measure the deployment claim end-to-end.
4. Calibrate energy estimates with a wattmeter for the
   sustainability axis.
5. Cross-validate against another small coder model (e.g. DeepSeek
   Coder) to test whether the meeting-halfway language additions
   generalise beyond Qwen.

What we learned but isn't on the next-step list:

- **Three interventions tested for adding the new builtins to v2 at
  inference (no retrain):**
    1. Rebuild RAG index with the 48 v3 builtin examples.
    2. Augment SLIM_HEADER to mention the new builtin signatures.
    3. Both 1+2 together.
  
  Result on synthetic 100-task: v2 + new RAG + aug-header → B 78
  (vs v2 76, **+2 pp** all on iter 6). On real tooling Stream C: 19/30
  (vs v2 20/30, **−1**, lost `wc_l`). The synthetic gain doesn't
  transfer to real tooling because the deployment shapes don't lean
  on the new string-pair builtins.

- **v3.1 vs v2 on the synthetic 100-task suite is within noise (84 vs
  85).** But the Stream C re-run on 30 real tooling tasks tells a
  different story: **v3.1 16/30 vs v2 20/30**, a −4-task regression
  on actual deployment shapes. v3.1 lost on `cut_first_n_chars`,
  `grep_only_matching`, `process_grep`, `json_path_extract`,
  `extract_urls` — the bread-and-butter parsing/extraction patterns —
  and gained on one (`ipv4_validate`). The synthetic iter-6
  string-pair lift did not transfer to real tooling because those
  builtins are not the dominant primitive on the deployment task
  shapes. Conclusion: **v2 stays the deployment default**; v3.1's
  retrained weights overfit toward the targeted corpus additions and
  shed broader memorization.
- **The accuracy ceiling at this corpus size + single-GPU is real.**
  Retrains *redistribute* failure mass rather than expand the budget.
  To break past v2's 85% (synthetic) / 67% (real tooling) needs a
  bigger corpus, multi-GPU, or a different base.
- **RAG knob-tuning is not a recovery lever for weight-level
  forgetting.** Loose, tight, and MMR-diversified RAG all gave v3.1
  identical or worse 1-shot scores — the model's confident wrong
  syntheses on iter 4/5 can't be overridden by in-context examples.
  Recovery requires either retraining with a broader corpus or a
  per-task adapter route, not RAG knobs.
- **bf16 + Navi31 stability is data-dependent.** v2 trained at
  lr=1e-4/max_seq=2048 because the corpus had no >1500-token
  examples *that landed in early shuffled batches*. The same lr on
  a corpus with three such examples NaN'd at step 60. The fix is
  corpus filtering (cap tokens at 800), not LR reduction.

## Phase 15: The architectural cleanup — prelude, builtin/stdlib boundary, and the if-Lisp-form trap

After Stream C made the deployment regression on v3.1 hard to ignore (16/30
vs v2's 20/30), we triaged the 10 v2 failures and saw three obvious clusters
that wanted new builtins: whitespace-aware split (`wc_w`, `tr_squeeze_spaces`),
paragraph split (`split_at_blank_lines`), and regex extraction (5 tasks).
The instinct was to add four new convenience builtins — `tokens`, `squeeze`,
`split_blocks`, `find_all` — to the OCaml interpreter. They were written and
tested.

Before merging them, we reviewed the existing surface: ~100 builtins in
interpreter.ml, of which roughly 30 were pure compositions hiding in OCaml
(`rev`, `swapcase`, `title`, `uniq`, `parse_pairs`, `count`, `max_by`,
`min_by`, `digits`, the six string-pair builtins from v3, `enumerate`,
`scan`, `map_kv`, `range`, `slice`, `merge`, `clamp`, `fmt_float`, …) plus
several pure aliases (`levenshtein`, `repeat`, `char_at`, the new `find_all`).
Each had been added to "meet the model halfway" — the model reaches for that
name, OCaml accepts it, the test passes. But over six months the cumulative
effect was real architectural sprawl: a 600-line OCaml dispatch table that
would have been 80 lines of Sigil, with the language's own stdlib
underused.

The fix that doesn't lose the meeting-halfway property:

1. **Auto-loaded prelude.** `stdlib/core/prelude.sigil` is loaded into every
   program's global env before user code, no `(import ...)` needed. The
   model writes `(tokens s)` and it just works — same zero-import experience
   as a builtin.
2. **The four new functions go in the prelude, written in Sigil.** Not in
   OCaml. The reverted OCaml implementations (~150 lines) are gone.
3. **Existing convenience builtins stay in place** — the user explicitly
   asked to keep aliases that "meet the model halfway and convert failures
   to passes," because moving them risks score regression on already-tuned
   benchmarks.
4. **Documented principle** (`stdlib/README.md`): a function lives in OCaml
   only if it can't be written in Sigil (FFI/syscall/regex/I/O), it's a
   runtime/type primitive, it's a syntactic operator, or it's
   performance-critical. Everything else is stdlib. Future additions go to
   the prelude unless one of those four conditions is met.

### The if-Lisp-form trap

While writing the four prelude functions in Sigil, we kept hitting the same
silent bug: a 2-statement then-branch was being interpreted as Lisp/Scheme
`(if cond then-expr else-expr)` form, because the parser intentionally
accepts both shapes. The fix per call site is `(else)` as an explicit no-op
marker. Once this pattern was named, the four pre-existing test failures
that had been "skipped as known issues" all turned out to be the same bug
in stdlib code:

- `stdlib/core/encoding.sigil` `hex_to_int` — `start = 1` ran on every
  non-negative input, skipping the first hex char. `hex_to_int("2a")`
  returned 10 instead of 42. Same pattern in `binary_to_int`.
- `stdlib/crypto/hash.sigil` MD5 main loop — the four
  `(if round-range (set f_val ...) (set g_val ...))` blocks each had
  `g_val` setter as the else branch. Three of four blocks would
  miscompute g_val on every round. SHA-256 in the same file used explicit
  `(else ...)` and was unaffected.
- `tests/test_if_multi.sigil` and `test_if_statement.sigil` — both tested
  the deprecated 2-statement-then semantics; rewritten with `(else)` to
  match current parser.

After fix: **155/155 unit tests passing** (was 151/155, with 4 known
failures predating this session). The core lesson: a parser ambiguity
disguised as a feature can rot quietly across the stdlib for months. We
documented the trap in `stdlib/README.md` so the next stdlib author
catches it before merge.

### What didn't change

Existing convenience builtins (`rev`, `swapcase`, `title`, `edit_distance`,
the v3 string-pair set, all aliases) stay in OCaml. They were earned
by benchmark wins; a wholesale move would risk silent regressions and
isn't on the critical path for the deployment study. The prelude
mechanism is the right home for any *future* convenience function.

### Stream C re-run #1: prelude only

We re-ran Stream C against `qwen-sigil-v2:7b` with the prelude available
and the augmented `SLIM_HEADER` mentioning `tokens`, `squeeze`,
`split_blocks`, and `find_all`. Result:
**20/30 — same as baseline, no recovery.** The model didn't reach for
the prelude functions despite the header mention. Inspecting the
generated code for the 5 "model didn't pick the prelude function"
failures: `wc_w` produced `(split s " ")`, `tr_squeeze_spaces` produced
`(join (filter (split " ")) " ")`, and so on — header alone tells the
model the function exists, but RAG retrieval is what shows it the
*shape* in context.

### Stream C re-run #2: prelude + RAG seeds

We added 12 seed examples to `training_corpus.jsonl` (3 each for
`tokens`, `squeeze`, `split_blocks`, `find_all`), shaped to mirror
Stream C task patterns; rebuilt the RAG index. Result on v2:
**22/30, +2 over baseline.** Three new passes (`wc_w`,
`tr_squeeze_spaces`, `iso_date_extract`); one regression (`wc_l`,
likely RAG churn surfacing different examples on a previously
1-attempt-passing task). Confirms the diagnosis: the new-name +
header + RAG-shape combination is what transfers to deployment.

Also fixed two interpreter meet-halfway issues exposed by the failure
inspection: `map_kv` now accepts both `(map, fn)` and `(fn, map)`
argument orders (model preferred the latter on `shell_argv_count`),
and `first`/`last` were already polymorphic on strings (the
`extract_function_names_py` failure was a paren-counting model bug,
not a missing primitive). Three other failures — `ipv4_validate`,
`extract_function_names_py`, the regex-greediness in `extract_emails`
— are model-side reasoning bugs that no language change addresses.

## Phase 16: Beyond the Qwen plateau — ensemble fallback hypothesis

After Phase 15 closed, the result table looks like:

| Configuration | Stream C | Notes |
|---|---|---|
| Sonnet (cloud) | 29/30 | reference ceiling |
| v2 + prelude + RAG seeds + map_kv tolerance | 22/30 | best local single-model, 73% |
| v2 baseline | 20/30 | 67% |
| v3.1 retrained | 16/30 | regression |
| v2 + new RAG (prior session) | 19/30 | regression |

Three rounds of retraining on Qwen2.5-Coder-7B (v3, v3.1, plus the
inference-time augmentations) converged on a ~22/30 ceiling on the
real-tooling deployment shapes. **Retraining keeps redistributing
failure mass rather than expanding the budget** — already documented
as a Phase 12 finding, and Phase 15 confirmed it: even with the right
primitive in the right name and matching RAG shape, the same 8 tasks
that broke v2 keep breaking v2.

### The plateau-with-Qwen hypothesis

The Qwen2.5-Coder family — like any specific model lineage — has a
fixed shape of strengths and weaknesses baked in by its training
data, tokenizer, RLHF, and architecture. We have explored most of the
recovery moves *within* that shape:

- More training data → didn't help (v3 NaN'd; v3.1 = v2)
- Better RAG → +2 pp synthetic, ±1 deployment
- Meeting-halfway language additions → +2 pp deployment (this phase)
- Better error messages / variadic ops → +3 pp synthetic

What we have *not* explored is using a **second model from a different
lineage** as fallback. The mechanism of the gain would not be "the
other model is smarter" — both are 7B-14B, both QLoRA-tuned on the
same 2058-example corpus, both subject to the same hardware budget.
The mechanism is **failure-shape diversity**: a model trained on
different data with different RLHF makes different errors, and the
*union* of two models' successes covers more of the task space than
either alone — provided the failure shapes overlap less than they
agree.

This is the same logic ensemble methods exploit in classical ML
(boosting, bagging) — but here the diversity comes for free, by
choosing a base model from a deliberately different lineage rather
than perturbing training. If two Qwen-derived models are >80%
correlated in failure shape, but a Qwen-trained and a Llama-trained
model are <60% correlated, the second pair leaves more room for
ensemble lift.

It is *not* guaranteed to work. If the second lineage is correlated
with Qwen's weaknesses (e.g. both fail at paren-counting in long
nested forms because that's a transformer property at this size,
not a training-data property), ensembling buys nothing. The
hypothesis needs to be tested empirically.

### How we picked the fallback model

The candidate criteria, in order:

1. **Architectural and training-data distance from Qwen** — the
   diversity is the whole point. Qwen-derived models (any
   `deepseek-r1-distill-qwen-*`, `qwen-*`-fine-tunes of partner labs)
   are disqualified.
2. **QLoRA-feasible on RX 7800 XT 16GB** — this is the available
   hardware. Cap at 14B dense or 16B MoE (with the latter only if its
   ROCm 4-bit story is solid).
3. **Code or strong instruction-following capability** — if the base
   model can't handle Sigil syntax at all, the ensemble does nothing.
4. **Stable QLoRA recipe** — bf16 + 4-bit nf4, dense (MoE+QLoRA on
   ROCm has open issues), tokenizer compatible with HuggingFace
   transformers.
5. **Distinct failure-shape prediction** — given the 8 persistent v2
   failures (output-spec attention, paren tracking, composition
   logic), the second model should have a paradigm that targets at
   least one of those.

Surveying the ollama.com catalog with these filters:

| Model | Family | Size | Disqualifier or rationale |
|---|---|---|---|
| `phi-4:14b` | Phi (Microsoft) | 14B dense | **Top pick.** Different training (textbook + synthetic), strong spec-following RLHF, fits 16GB QLoRA at 4-bit, dense |
| `deepseek-r1-distill-llama-8b` | Llama 3.1 + R1-distill | 8B | Strong second pick: Llama base + reasoning-trace generation. Catch: outputs `<think>` tags |
| `codegemma:7b-instruct` | Gemma (Google) | 7B | Safe third pick: Gemma family + code-specialized + same size class as v2 |
| `deepseek-coder-v2:16b` | DeepSeek-V2 (MoE) | 16B / 2.4B active | Most arch-distinct from Qwen, but MoE+QLoRA+ROCm has open bnb issues |
| `gemma2:9b` | Gemma | 9B dense | General not code-specialized — weaker on code shape |
| `mistral-nemo:12b` | Mistral | 12B | General, less code-strong than Phi-4 |
| `starcoder2:7b` | BigCode | 7B | Base only; would need both instruct + Sigil tuning from scratch |
| `granite-code:8b` | Granite (IBM) | 8B | Enterprise-narrow corpus |
| `olmo2:7b` | OLMo (AllenAI) | 7B | Fully open but weaker code capability |
| `codestral:22b` | Mistral | 22B | Too large for 16GB QLoRA |
| `command-r:35b` | Cohere | 35B | Too large |
| `yi-coder:9b` | Yi (01.ai) | 9B | Closer to Qwen training era; lower diversity |
| any `*-distill-qwen-*` | Qwen-derived | various | Disqualified — same lineage |

**`phi-4:14b` ranks first** because (a) Microsoft's training paradigm
is the most distinct from Alibaba's Qwen training in terms of data
mixture (textbook + synthetic vs web-code), (b) the spec-attention
failure shape that dominates v2's persistent errors is exactly what
Phi training emphasises, (c) at 14B dense it has more capacity for
composition than v2's 7B without breaking the 16GB QLoRA budget at
4-bit, and (d) the architecture is dense and recipe-compatible with
the v3.1-stable knobs (bf16 + nf4 + lr=2e-5 + max_seq=1024).

The hypothesis we are testing: a `phi-sigil-v1:14b` adapter, used
as the third-attempt fallback when v2 fails twice, lifts Stream C
from 22/30 toward Sonnet's 29/30 by catching at least 2-3 of v2's
8 persistent failures via its different failure shape.

If `phi-sigil-v1` shares >75% of v2's failure set, the diversity
hypothesis is wrong at this scale and we need to look at multi-step
agentic mechanisms (validator-in-loop, draft-and-verify) instead of
ensemble. Either outcome teaches us something about the local-LLM
ceiling.

### Result: hypothesis confirmed at 25/30

**Phi-4 14B QLoRA fine-tune (`phi-sigil-v1:14b`):** 4h 36m on RX 7800 XT
with v3.1-stable recipe (`lr=2e-5`, `max_seq=1024`, `warmup_ratio=0.2`,
`max_grad_norm=1.0`, `lora_r=16`). Final running-mean train_loss 0.486,
per-step end-of-epoch-3 loss ~0.21. LoRA target modules detected as
`[qkv_proj, o_proj, gate_up_proj, down_proj]` (Phi-3/4's fused projection
shape). Trainable params 55.7M / 14.7B = 0.38%. No NaN, gradient norms
0.4–0.7 throughout.

**Ollama LoRA-runtime workaround:** the runtime LoRA application path
crashed (`model runner has unexpectedly stopped`) on Phi-4 + ollama 0.19.
Fix: merge the LoRA into the base weights on CPU (peft
`merge_and_unload()`, fp16, ~28 GB RAM peak), convert merged HF model
to GGUF f16 with `convert_hf_to_gguf.py` (had to patch `tokenizer_class`
to `GPT2Tokenizer` because transformers 5.7 saves it as
`TokenizersBackend`), then quantize on import via `ollama create -q
q4_K_M`. The merged Q4_K_M model is a standalone GGUF that ollama serves
without runtime LoRA application — bypassing the bug.

**Diagnostic Stream C on `phi-sigil-v1:14b` alone:** 19/30 (63%) — *lower*
than `qwen-sigil-v2:7b`'s 22/30, which is fine: the hypothesis is about
**failure-shape diversity**, not raw capability. Comparing failure sets:

| | v2+prelude (8 fails) | phi-sigil-v1 (11 fails) |
|---|---|---|
| Both fail | 5 (wc_l, extract_emails, find_max_in_log, permission_octal_to_symbolic, shell_argv_count) | (same 5) |
| v2 fails, phi passes | split_at_blank_lines, ipv4_validate, extract_function_names_py | — |
| phi fails, v2 passes | — | grep_count_pattern, tail_n_lines, sort_uniq_count_top, grep_only_matching, json_path_extract, uniq_c_simple |

Failure-shape overlap = 5 / 14 = **36%**. Predicted union of successes
= 22 + 3 = **25/30 (83%)**. Hypothesis stands.

**Ensemble Stream C (`v2 → phi-sigil-v1` on attempt 3):** confirmed
**25/30 (83%)**, 5 of 9 gap-tasks closed against Sonnet. Three new
passes on v2's previously persistent failures, no losses. Result file
`benchmark/stream_c_ensemble_v2_phi_results.json`.

### Final scoreboard (this work)

| Configuration | Stream C | Marginal cost | Tokenization budget |
|---|---|---|---|
| Sonnet (cloud, single model) | 29/30 (97%) | $0.085 / run | n/a (paid token) |
| **v2 → phi-sigil ensemble (local)** | **25/30 (83%)** | **$0** | local hardware |
| v2 + prelude + RAG seeds | 22/30 (73%) | $0 | local hardware |
| v2 baseline (Phase 14 close) | 20/30 (67%) | $0 | local hardware |
| Phi-sigil-v1 alone | 19/30 (63%) | $0 | local hardware |
| v3.1 retrained (failed iteration) | 16/30 (53%) | $0 | local hardware |

The ensemble achieves **86% of Sonnet's accuracy at zero marginal cost
and full data residency**. The 5 remaining persistent failures
(`wc_l`, `extract_emails`, `find_max_in_log`,
`permission_octal_to_symbolic`, `shell_argv_count`) require either
frontier-class capability or a validator-in-loop pattern (run, check
output shape, regenerate with feedback) — adding a third 7B–14B
ensemble member with similar training paradigm is unlikely to crack them.

### What this answers

Phase 16 closed three open questions:

1. **Does the Qwen plateau exist?** Yes. Three retraining rounds on
   Qwen2.5-Coder-7B converged on ~22/30 ceiling for deployment shapes;
   no further single-model retraining moved the needle.
2. **Does failure-shape diversity buy lift?** Yes. A Phi-4 fine-tune
   from a different training lineage has 36% failure-overlap with v2,
   and ensembling lifts +3 tasks despite phi-sigil-v1 alone being
   weaker than v2 alone. The diversity, not the capability, is what
   transfers.
3. **What's the ceiling for two 7B–14B local models?** ~25/30 (83%)
   on this benchmark. To go further, we need either a different
   *paradigm* (validator-in-loop, draft-and-verify) or a frontier
   model — not a third similar-size ensemble member.

### Routing-variant sweep — confirming the ceiling is real

Six routing variants of v2 ⊕ phi-sigil-v1 were tested to rule out
"the result is a sampling artifact." All vary the attempt budget,
temperature schedule, and whether phi sees v2's wrong code as anchor:

| Variant | Routing | Phi temp | Phi prompt | Stream C |
|---|---|---|---|---|
| Original 3-attempt | v2,v2,phi | 0.7 (ramp) | anchored on v2 fail | **25/30** |
| 4-attempt v2-3 then phi | v2,v2,v2,phi | 0.9 (ramp) | anchored | 24/30 |
| A: 2v2+2phi anchored | v2,v2,phi,phi | 0.7→0.9 | anchored | **25/30** |
| B: 2v2 + phi fresh | v2,v2,phi | 0.7 | fresh (no anchor) | 24/30 |
| C: 2v2+2phi anchored, t=0.3 | v2,v2,phi,phi | 0.3 fixed | anchored | **25/30** |
| D: 2v2 + phi fresh, t=0.3 | v2,v2,phi | 0.3 fixed | fresh | **25/30** |

**Four out of six variants converge at exactly 25/30, with exactly the
same 5 failing tasks in every 25/30 run** (`wc_l`, `extract_emails`,
`find_max_in_log`, `permission_octal_to_symbolic`, `shell_argv_count`).
That's strong evidence the ceiling is real, not a sampling artifact —
the joint failure set of these two models on these specific shapes is
what bounds the ensemble.

The two non-25 variants are also informative:

- **4-attempt v2-3 then phi (24/30):** v2's third retry caught `wc_l`
  (+1) but phi at temp 0.9 lost `extract_function_names_py` and
  `ipv4_validate` (−2). Net −1. Phi's reliability degrades at
  the higher end of the temperature ramp.
- **B: 2v2 + phi fresh, default ramp (24/30):** phi at temp 0.7 with
  no anchor on v2's wrong code loses `ipv4_validate`. But variant D
  recovers it by *also* lowering phi's temp to 0.3. The lesson: the
  fresh-prompt cost can be paid by lowering temperature.

Two routing intuitions worth filing for future ensembles:

1. **Anchoring on the primary's wrong code helps the fallback at high
   temperatures, not at low ones.** At temp 0.3 phi can operate cold
   without losing reliability; at temp 0.7+ the prev_code anchor
   constrains generation enough to matter.
2. **More attempts don't help once the joint ceiling is hit.** Adding
   a fourth phi attempt (variants A, C) doesn't open new tasks. The
   five remaining failures are not "the model didn't have enough
   tries" — they're "neither model knows the right primitive
   composition for this shape." Fixing them needs new primitives
   or a new paradigm (validator-in-loop), not more sampling.

Result files: `benchmark/stream_c_A_2v2_2phi_anchored.json`,
`stream_c_B_2v2_phi_fresh.json`, `stream_c_C_2v2_2phi_anchored_t03.json`,
`stream_c_D_2v2_phi_fresh_t03.json`.

## Phase 17: Philosophy retrospective — what the original premise got right and wrong

After Phase 16 stabilised the result at 25/30 (joint local ceiling)
and 23/25 on a fresh tooling task set (vs Sonnet's 25/25), we
revisited the original README and the founding premise: *"a
programming language designed by AI, for AI code generation,"*
articulated as ten principles led by **ONE WAY ONLY** and **zero
ambiguity**. The benchmark months later make it possible to grade
each principle empirically.

### What survived intact

- **Two-layer architecture (Core + Agent).** Core is the 5 frozen
  statements; Agent is the surface that evolved. Core never changed.
  Models trained on Sigil-of-12-months-ago still work on
  Sigil-of-today, because they emit Agent forms that the interpreter
  desugars to the unchanged Core IR.
- **Type-directed dispatch (`(add x y)` works for int/float/string/array).**
  Models adopt this without prompting. No memorisation of
  `add_int`/`add_f64`/`add_str` variants.
- **S-expression syntax.** Zero precedence ambiguity. Coder models
  generate `(op args...)` reliably.
- **Frozen Core IR.** Stable training target. No churn.
- **No comments.** Corpus stays clean; no token waste; can't lie
  about code.
- **Pure-Sigil stdlib.** Phase 15 *doubled down* on this — added the
  auto-loaded prelude in Sigil rather than expanding the OCaml
  builtin table. Stdlib in Sigil doubles as RAG-retrievable
  documentation the model can copy.
- **Panic-based errors.** Now with contextual type-tuple messages
  (Phase 14), which were +3 pp on synthetic. Hard panics + good
  messages = the model regenerates with the right fix.

### What did not hold as stated

- **"ONE WAY ONLY" — abandoned in practice.** The interpreter now
  has ~30 alias names (`head/first`, `+/add`, `count_el/count`,
  `contains/in/has`, `size/length/len`, etc.). Each alias produced
  a benchmark win — models reach for those names from Python/Lisp
  /Haskell training, and the alias catches the reach. The operational
  pattern that emerged is the *opposite* of the original principle:
  **many ways for input, one canonical implementation.** This is
  the *meeting-halfway* pattern documented in
  `papers/MEETING_HALFWAY.md`.
- **"Zero ambiguity" — has documented gotchas.** The if-Lisp-form
  trap (Phase 15 root-cause for 4 long-standing test failures);
  `string_get` returning int char code while `string_at` returns
  1-char string; `count` overloaded for strings vs arrays. We patched
  what we could (improved error messages, explicit `(else)` markers)
  and documented the rest in `stdlib/README.md`.
- **"Designed by AI, for AI" — true at the design phase, constrained
  at the operational phase.** Pre-trained models bring a vast prior
  on Python/JS/Lisp from training. A clean from-scratch AI design
  generates *worse* than a Python-shaped one because the model can't
  easily produce the clean shape. The Sigil that actually works is
  half AI-minimal design + half Python/JS-shape concessions, glued
  together with meet-halfway aliases.

### The real claim, restated

Sigil's contribution is not "a language designed by AI for AI." It
is *"a language whose design is continuously refined by observing
AI failures."* Each alias has a story; each prelude function has a
benchmark win; each parser tolerance has a fix-PR rationale. The
process is more interesting than any static design. The README now
reflects this honestly.

### Pre-trained models constrain the design space

The premise of the language makes sense on pre-trained models *only
with two qualifications*:

1. The language must mirror enough of the model's existing shape
   vocabulary (Python, Lisp synonyms, common operator names) to be
   generatable.
2. The "meeting halfway" pattern is not a workaround — it is the
   operational design philosophy.

A genuinely "AI-for-AI" language with **no** concessions would
require either:

- Training a model from scratch on Sigil + minimal Python (multi-M
  USD; loses the model's general programming knowledge), or
- An abstract IR with token-level encoding of every operation,
  trained as the model's *primary* output target (research-level
  effort; no off-the-shelf base model to start from).

Neither is economically rational on consumer hardware. Scenario C —
*pre-trained Coder model + meet-halfway language design* — is what
we have, and the benchmark validates that it works (25/30 on
deployment shapes; 23/25 on fresh tooling tasks; 92% of Sonnet at
$0 marginal cost).

### What the README should claim

Soften: *"designed by AI, for AI."*  
To: *"designed by AI, refined by observing AI failures, deployed
for AI code generation."*

Soften: *"ONE WAY ONLY."*  
To: *"many ways for input (so the model's reaches succeed), one
canonical implementation (so the language stays maintainable)."*

Soften: *"zero ambiguity."*  
To: *"minimal ambiguity, with documented gotchas where pragmatism
or backwards-compatibility forced exceptions."*

These updates have been made to `README.md` to match the project's
actual state.

## Phase 18: Agent harness ships, PCRE swap as canonical meet-halfway (2026-05-01)

Three concurrent tracks landed: (a) `tools/agent_harness/sigil_mcp_server.py`
exposes the local Sigil ensemble as an MCP tool a cloud orchestrator
can delegate to without sending input data over the wire.
(b) `tools/agent_harness/agent_ab_harness.py` runs an A/B comparison
on multi-step tasks. (c) The Sigil regex backend swaps from OCaml's
`Str` to `Re` (Perl-compatible) — `\b`, `\d`, `\w`, `\s`, named groups,
non-greedy quantifiers all become available. ~60 lines of OCaml absorb
an entire flavor of regex syntax.

The A/B harness result splits the project's value claim cleanly:
**6/8 cloud-Python vs 1/8 hybrid-local-Sigil** on multi-step tasks.
The 29/30 single-step Stream C win does not transfer. Delegation
works for the tooling-shape piece, not for multi-step composition.

The PCRE swap is the canonical structural meet-halfway. The pattern
this phase names: when a failure mode is dominant AND tied to model
pre-training, fix at the language layer rather than via prompts /
corpus / training. Each non-language intervention costs ongoing
engineering; the language change costs once. Documented as Section
4.7 in `papers/MEETING_HALFWAY.md`.

Commits: [16c42c3](https://github.com/mlainez/sigil/commit/16c42c3) (MCP server),
[c5d5203](https://github.com/mlainez/sigil/commit/c5d5203) (paren-balancer in Sigil itself),
[2be44f5](https://github.com/mlainez/sigil/commit/2be44f5) (validator-in-loop surgical hints),
[7a9fca4](https://github.com/mlainez/sigil/commit/7a9fca4) +
[ff7d68d](https://github.com/mlainez/sigil/commit/ff7d68d) (PCRE corpus seeds).

## Phase 19: Stream C 29/30 — corpus and validator hint, no language redesign (2026-05-02)

Three small additive moves take Stream C from 26 to 29:

1. **Lexer fix**: unknown escapes preserve the backslash so `"\d{4}"`
   in Sigil source survives to the regex engine intact.
2. **Regex corpus expansion**: 70 verified examples (58 generated +
   12 hand seeds). Stream C jumps to 27/30.
3. **For-iterator mutation guard**: runtime error when
   `(for i 0 n ... (set i ...))` mutates the iterator (a C/Python
   instinct that Sigil's for silently ignores). Validator hint
   rewrites the retry prompt with a worked while-loop pattern.

Final: **29/30 with v6 + phi-v1 ensemble + RAG + for-guard.** Single
failure (`shell_argv_count`) is a cosmetic format-string miss. See
`benchmark/STREAM_C_RESULT.md` for the full report.

The methodology this phase names prospectively: when a real-world
failure shows up, decision tree is (a) is the language silently doing
the wrong thing? fix that. (b) is the model reaching for the wrong
tool? add corpus. (c) is the model writing the right algorithm with
the wrong control flow? add a runtime guard hinting toward the right
shape.

Commit: [d7bc1ce](https://github.com/mlainez/sigil/commit/d7bc1ce).

## Phase 20: Phi-Sigil-v2 deployment + matching cloud at 29/30 (2026-05-03)

Phi-Sigil-v2 retrains on the augmented corpus to keep both ensemble
members on the same vocabulary. Deployment is the entire story —
training itself is unremarkable.

Four chained problems: (1) ollama llama-runner segfaults on Phi-4 +
adapter overlay (workaround: merge offline). (2)
`convert_hf_to_gguf.py` "missing tokenizer.model" because Phi-4 uses
GPT2Tokenizer/BPE not SentencePiece, and transformers had rewritten
the tokenizer-class field. (3) 29 GB fp16 GGUF doesn't fit in 16 GiB
VRAM. (4) **Q4_K_M drift**: phi-v2 solo Stream C is 14/30 vs phi-v1's
19/30. Q4_K_M's per-block dynamic quantization handles Phi-4's fused
`qkv_proj` / `gate_up_proj` worse than the split-projection Qwen
architecture. Doesn't affect ensemble outcome (phi-v2 still rescues
the one task qwen-v6 fails).

The headline: **local 29/30 = Sonnet 29/30** with complementary
failures (`shell_argv_count` for local, `split_at_blank_lines` for
Sonnet). A combined cascade trivially hits 30/30.

Lesson recorded: the deployed model can be measurably worse than the
merged-checkpoint reference, so retrain claims have to be validated
in the actually-deployed configuration, not the offline fp16 weights.

Commit: [97983f7](https://github.com/mlainez/sigil/commit/97983f7).

## Phase 21: Stream C wins don't propagate to multi-step (2026-05-03)

Re-run the A/B harness with v6+phi-v2. Result: **1/8 hybrid, 6/8
cloud** — *unchanged* from the Phase 18 v4+phi-v1 baseline. Training
a stronger Sigil model didn't move the multi-step number.

Failure-mode dive shows three patterns: (a) `(argv)` reach on
multi-line input (3 of 7 failures); (b) wrong column index in
tabular data; (c) made-up syntax / undefined names. None addressable
by "more corpus" or "stronger model" — the bottleneck is composition
complexity, not Sigil grammar fluency. Phase 18 had predicted this
exact finding.

## Phase 22: Tier 1 — interpreter loudness, validator hints (2026-05-03)

Phase 19's prescription applied to the multi-step failures: surface
silent failure modes at the language layer.

- **(argv) misuse warning** in the argv builtin (default-on stderr)
  when length=1 element contains newlines.
- **No-output-produced warning** at program exit if no
  print/println was called.
- **validator_hint** pattern-matches both warnings and rewrites the
  retry prompt with worked fixes.
- **26 corpus seeds** (12 multi-line $0, 8 header-aware tabular,
  6 find_all) appended to the corpus.
- **System prompt addendum** with the input-shape rules.

Result: B 1/8 → 2/8. One systematic win (`url_status_pairs`
recovered via the new diagnostic flow). Each Tier 1.5 retest sat in
the same 1-2/8 band; the diagnostic mechanism is real but covers a
narrow failure shape. The Stream D agent_workflow deliverables
(`router.py`, `sigil_subagent.md`, `example_walkthrough.md`) shipped
in the same commit, closing Stream D.

Commit: [dafdec9](https://github.com/mlainez/sigil/commit/dafdec9).

## Phase 23: Tier 2 — chained sub-agent (2026-05-03)

The architectural fix Phase 18 named: replace single-program
delegation with a pipeline of single-step calls. Each step is
Stream-C-shaped (the regime where the local ensemble lives at
29/30); the orchestrator owns the cross-step plumbing.

Path C added to the harness. Result: **C 3/8** vs B 1/8, at **45%
lower cost** ($0.0149 vs $0.0269). Most remaining failures are
*intermediate-step shape mismatches*: Sonnet's guess at step 2's
input shape doesn't match what step 1 actually produced.

Side discovery: the long-standing "TCP loopback test fails" status
was a real test bug (off-by-one if-branch in
`test_tcp_large_message`), not environmental. Six-character fix;
suite goes from 160/161 to 161/161.

Commit: [fe3cedd](https://github.com/mlainez/sigil/commit/fe3cedd).

## Phase 24: Tier 2.5 — RAG plateau, the case for v7 retrain (2026-05-03)

Five more moves on Tier 2: aggregation seed pack, intermediate
validation in path_c, forced 2-3 step decomposition, multiline regex
default, TSV/CSV markdown seeds. Result: **C regresses from 3/8 to
1/8.**

The aggregation seeds DID help (csv_top3 reaches step 2 with the
right shape) but Move B's "non-empty = pass" heuristic was too lax
and let bogus output propagate. Two clean regressions
(`extract_dotted_ipv4`, `url_status_pairs`) are pure RAG-displacement
artifacts: 14 new aggregation seeds shifted top-K retrievals away
from previously-helpful regex/log seeds.

**Textbook RAG plateau.** Three pure-RAG runs (Phase 21 baseline,
Tier 2, Tier 2.5) all sit in the 1-3/8 band on Path C. The +2
architectural lift in Phase 23 was the only systematic gain.

**Conclusion**: train qwen-sigil-v7 on the 2323-entry corpus. RAG
shows patterns at inference time; weights bake them in. The
remaining failures are "model reaches for wrong shape" with the
right RAG context already in the prompt — exactly what fine-tuning
addresses.

A separate experiment confirmed model-role choice isn't the
bottleneck: phi-primary + qwen-fallback hits the same band (B 2/8,
C 2/8) at lower cost but no accuracy lift.

Commits: [719114c](https://github.com/mlainez/sigil/commit/719114c) (Tier 2.5),
[ff7268a](https://github.com/mlainez/sigil/commit/ff7268a) (assessment),
[2735045](https://github.com/mlainez/sigil/commit/2735045) (inverted experiment).

## Phase 25: Smart-argv — the canonical meet-halfway, applied at last (2026-05-03)

Marc's question framed it: *"If argv is pretraining data, why don't
we meet the model halfway with it?"*

The (argv) misuse pattern dominated multi-step failures across
Phases 18-24 because the model's pre-training is saturated with
`for arg in sys.argv` (Python) and `for line in "$@"` (Bash)
patterns. Our literal `(argv)` returned a 1-element list when input
was a single multi-line string — the model's for-each ran once over
the whole blob. We tried fixing this via diagnostics, prompts, and
corpus seeds; pre-training bias proved stronger than 7.6% corpus
weighting on a fine-tune.

The fix: **make `(argv)` smart**. When called with exactly 1 CLI arg
AND it contains newlines, return the lines split. Otherwise the
literal CLI argv vector. Add `(argv_raw)` as escape hatch. ~10 lines
of OCaml. Blast radius in our codebase is essentially zero (corpus
has 0 `(argv)` entries; only test_argv.sigil uses `(argv)` and only
with no args).

A/B/C retest with only smart-argv changed: **B 1/8 → 2/8, C 1/8 →
2/8**. `url_status_pairs` Path B is the canonical demonstration —
the model wrote `(map (argv) (\line ...))` expecting line iteration,
and it just worked. No retraining, no prompt change, no validator
hint.

Same phase added 4 builtin aliases (`parse_float`, `to_int`,
`first_index_of`, `regex_replace_all`) for common "real-looking name
that doesn't exist" reaches, and a corpus pristineness auditor that
came back clean: 0/2323 entries flagged.

The fix that should have come at Phase 18 instead of Phase 25 is the
canonical structural meet-halfway. The lesson generalizes: when
you're fighting model instinct across multiple phases, fix at the
language layer.

Commits: [398032f](https://github.com/mlainez/sigil/commit/398032f) (smart-argv + aliases),
[1c98563](https://github.com/mlainez/sigil/commit/1c98563) (smart-argv A/B/C result),
[fd15459](https://github.com/mlainez/sigil/commit/fd15459) (revert Tier 2.5 prompt overreach).

## Phase 26: qwen-sigil-v7 retrain on hardened corpus (in flight)

Same QLoRA recipe as v6 (r=16, alpha=32, lr=2e-5, 3 epochs). 2323
training entries with full Tier 1 + Tier 2.5 seed coverage,
smart-argv runtime semantics in place. ETA ~2h 42m wall (873 steps
× ~11s/step on the 7800 XT — ~half my original 5h estimate, the
attn_implementation sdpa change at
[0f1a75e](https://github.com/mlainez/sigil/commit/0f1a75e) is paying off).

Three outcome bands defined for the post-train retest:
- **5+/8 on Path C**: weights-baking moved the floor; match cloud
  noise band. Deployment-ready story.
- **3-4/8**: chained architecture is the real ceiling; next move
  is bash-history task suite refresh, not more model work.
- **1-2/8**: deployment chain regression — diagnose Q4_K_M
  behavior on Qwen split-projection (unlikely but possible).

### Result

Training: 9884s wall (~2h 45m), final per-step loss ~0.21, no NaN.
Adapter saved to `benchmark/lora_out_qwen_v7/`.

**Stream C single-step**: v7 + phi-v2 = **28/30** (Sonnet 30/30). Down
1 from v6+phi-v2's 29/30 — `awk_filter_field_gt` regressed (v7 fails
2 attempts, phi-v2 also fails). v7 won `split_at_blank_lines` natively
(was Sonnet's residual on v6 era; v6 needed phi rescue).

**Agent A/B/C**: v7 + phi-v2 = **B 2/8, C 2/8** (Sonnet 6/8). The
retrain did not lift the agent harness floor.

| Run | A | B | C | C cost |
|---|---:|---:|---:|---:|
| Tier 2 (v6+phi-v1, Phase 23) | 5/8 | 1/8 | **3/8** | $0.0149 |
| Tier 2.5 (v6, more RAG, Phase 24) | 6/8 | 1/8 | 1/8 | $0.0171 |
| v6 + smart-argv (Phase 25) | 5/8 | 2/8 | 2/8 | $0.0252 |
| **v7 + phi-v2 (this)** | **6/8** | **2/8** | **2/8** | **$0.0201** |

**Three pure-training/RAG iterations all sit in the 1-3/8 band.** The
+2 lift from Phase 23's chained architecture remains the only
systematic gain across all the model and corpus work since.

The diagnostic value of the v7 retest: it answers the open question
from Phase 24. Pure-RAG hit a plateau; pure-retraining hits the same
plateau. The remaining failures are intermediate-step shape
mismatches in Sonnet's decomposition plans, which neither RAG nor
weights can address — they need the orchestrator to validate or
adapt mid-pipeline.

Per-task notable: v7 won `extract_dotted_ipv4` on both Path B and C
— a task **Sonnet also fails**. This is the local stack producing
a complementary failure, the same pattern Stream C established at
the single-step level (Phase 20).

### What this tells us about next moves

The chained architecture (Phase 23) is the real ceiling on this
8-task synthetic suite for the model + RAG + harness lever. To move
past it requires one of:

1. **Different benchmark** — bash-history task suite refresh (Stream
   C #116 in `benchmark/RESEARCH_PLAN.md`). Real-workflow shapes
   may be more local-tractable than the synthetic harness, or
   harder; either answer is informative.
2. **Different orchestration** — Sonnet validates each intermediate
   step's output against an expected shape sketch, replans if
   mismatched. Higher cost, plausibly higher accuracy. Phase 23's
   "intermediate-step shape mismatch" failure mode is exactly what
   this would address.
3. **Accept the ceiling** — 3/8 chained at $0.0149 vs Sonnet 5-6/8
   single-pass at $0.0245 is a real cost-confidentiality tradeoff
   for tooling-shape work, even if it's not a Sonnet replacement.
   The deployment-ready story is "delegate the tooling step; keep
   orchestration on the cloud frontier model" (Phase 21's framing
   carried through).

The retrain spend was worth it: it confirmed the plateau is
weights-deep, not just RAG-deep. Without v7 we'd have plausible
deniability that "another retrain on the augmented corpus might
help"; we now know it doesn't. That's the honest data point.

Result files: `benchmark/stream_c_v7_phi_v2.json`,
`tools/agent_harness/abc_v7_results.json`.

Commits:
[802bed2](https://github.com/mlainez/sigil/commit/802bed2) (Stream C v7),
[11fbddd](https://github.com/mlainez/sigil/commit/11fbddd) (A/B/C v7).

## Phase 27: NH2 Tier B (3B step-judge) and the empty-pipeline post-mortem (2026-05-04)

After Phase 26 left Path C stuck at 6/30, the obvious next move was a
semantic step-judge: a 3B model that looks at each chained intermediate's
stdout and decides whether the shape matches what the step description
asked for. Built `benchmark/sigil_step_judge.py` — a hybrid:
deterministic Python pre-checks for counting and ordering, qwen2.5-coder:3b
for the semantic cases, fail-open on any error so the pipeline can't hang.

Validated against the entire harness result history (131 task-runs across
9 result files): 37 NO verdicts, 0 false positives on passing tasks, 26%
coverage of failures. Smoke-tested OOD on synthetic chemistry / finance /
code-metrics / geocoding / genome shapes (14/14) to confirm the
principles-based prompt generalizes beyond our specific corpus.

Wired into `path_c_chained_hybrid` after the empty-stdout retry. Live
isolation run (qwen-sigil-v7 primary, deepseek-sigil v1 fallback,
Tier A static validator, judge added): Path C 6/30 → 7/30. Two of three
judge-triggered retries converted (gained `running_sum`,
`filter_lines_in_range`).

The strict lift estimator (`benchmark/judge_lift_estimate.py`) had
predicted +0.4 to +0.7 tasks; actual +1 was the upper end. This
confirmed the judge addresses precisely its TAM (wrong-shape
intermediates with non-empty stdout) but is structurally unable to fix
the dominant ~80% of failures (empty pipelines + final-step shape
mismatches).

### NH3 epoch-3 retrain regression

In parallel: redid the deepseek-sigil retrain at the full 3 epochs the
GPU thermal shutdown of 2026-05-03 had cut short. Loss kept dropping
(0.33 → 0.27 epoch 2→3) but Stream C *regressed* from 23/30 → 19/30 on
the clean idle-GPU rerun. Inspecting the lost tasks revealed classic
overfit signatures: the model regurgitated training-corpus headers like
`@(grammar sigil) @(stat tests:173 examples:4 stdlib:20)` instead of
emitting code. Concrete evidence that the corpus contains memorizable
artefacts the model can latch onto when training pushes far enough.
Production fallback stays on the 2-epoch v1. Future retrains either
cap at 2 epochs or use early stopping on a held-out validation slice.

Commits:
[202024e](https://github.com/mlainez/sigil/commit/202024e) (judge prep),
[d5c8f99](https://github.com/mlainez/sigil/commit/d5c8f99) (judge prompt
hardening + replay),
[692a047](https://github.com/mlainez/sigil/commit/692a047) (lift estimator),
[624f9d3](https://github.com/mlainez/sigil/commit/624f9d3) (clean isolation
6→7/30).

## Phase 28: NH8 input-shape annotation — failure mode confirmed, fix harder than expected (2026-05-04)

Diagnostic on the post-judge baseline showed empty-pipeline failures
(19/23 of the Path C losses) cluster in two specific positions:

  - 10 final-step empties where Sonnet's decomposition left a "compound
    final" step combining sort + take + format
  - 9 first-step empties where the model couldn't parse `$0`'s shape

A targeted manual probe on `wc_top_words` step 2 confirmed the failure
mechanic: the model emitted `(split $0 " ")` (split on space) when `$0`
was actually line-separated. The model was inferring shape from the
*description's verbs* rather than the actual upstream data — so the
step description "count words" cued the wrong delimiter.

NH8 hypothesis: have Sonnet declare an `input_shape` per step so the
local model knows what `$0` looks like.

Three iterations:

  - **v1** added a long shape-prescriptive system prompt with examples
    of good shape annotations + an instruction to prefer shorter atomic
    steps. Result: avg n_steps 1.63 → 2.17 (over-decomposed simple
    tasks); Path C 7/30 → 5/30. Three previously-passing 1-step tasks
    broke when forced into 2 steps.
  - **v2** kept the new schema but rolled back "prefer atomic" to "use
    as few steps as the task naturally needs". Result: avg n_steps
    swung the other way to 1.23 (under-decomposed); Path C 6/30,
    empty-pipeline failures jumped 19 → 24.
  - **v3** (in flight at time of writing) restored the original
    CHAIN_DELEGATE_SYSTEM verbatim and added input_shape only as a
    single optional field in the JSON schema, with no other prompt
    changes.

The lesson is structural and captured as CH11 in `post-sigil/
CONCLUSIONS.md`: prompt-engineering shape annotation onto a free-text
JSON entangles with Sonnet's planning behavior. Cleaner architecture
for the next project would be a *typed* plan structure where input/
output shapes are first-class fields, not free-text annotations on top
of an existing schema.

Side finding: when given a correct shape hint, the qwen-sigil-v7 model
drifts to Clojure-style `(let [x v y v] body)` bracket syntax that
Sigil's parser rejects. Saved as a candidate parser-level meet-halfway
extension if it becomes the dominant residual failure mode.

## Reproducibility

Every claim in this narrative cites either a JSON results file in
`benchmark/`, a markdown doc in `papers/`, or a specific commit
hash in the OCaml interpreter source. The exact commands that
produced each metric are in `benchmark/rag_loop.py`,
`benchmark/finetune_local.py`, and `benchmark/eval_*.py`.

A reviewer can take any number cited above, find the exact JSON
file or command, and reproduce the result on the same hardware.
The training, evaluation, and corpus generation are all repeatable
with the seeds and configurations recorded in the result files.

---

## Project closed (2026-05-04)

This is the chronological narrative; the **strategic synthesis and
close-out** lives in [`SIGIL_RESULT.md`](./SIGIL_RESULT.md). Read that
first if you only have time for one document.

The hypothesis-by-hypothesis empirical record is in
[`HYPOTHESES.md`](./HYPOTHESES.md). The successor project on
agent-safe local tooling (capability-typed Python subset, runtime
verifier, declarative authorization policies) is planned in a sibling
`post-sigil/` repo.
