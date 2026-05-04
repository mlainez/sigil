# Sigil — Project Retrospective

> Closing the experiment. What we set out to build, what the data validated,
> what the data refuted, and what we carry forward.

---

## TL;DR

**Sigil was a 3-month bet** that a deliberately AI-shaped language —
prefix-Lisp, canonical, type-light, deterministic — would let small local
models (7B-class) do agentic tooling work at cloud-quality reliability and
low cost, with effect-typed safety as the eventual differentiator.

**What worked:**

- **Single-step tooling delegation reaches cloud parity.** Stream C: 29/30
  with the qwen-sigil-v7 + deepseek-sigil ensemble vs Sonnet 29-30/30, at
  ~6× lower cost per task. The deployment story for which Sigil was
  designed — delegate per-step tooling work to local, keep orchestration
  on cloud — is real and validated.
- **The methodology is durable.** Validator-in-loop, principle-based 3B
  step-judges (14/14 on synthetic OOD), cross-base ensembles with
  fresh-prompt-temp-0, sequential corpus generation, the "meet the model
  halfway" pattern — all transferable to any future language target.

**What didn't work:**

- **Designing a syntactically novel surface language was expensive.** A
  baseline 7B Python coder produces shape-correct Starlark on 37% of the
  same task class with zero fine-tuning, just a system prompt. We paid
  ~3 months to reach 29/30 on Sigil; pre-training proximity is the
  cheapest form of capability.
- **Multi-step composition is not a language problem.** The orchestration-
  ceiling diagnostic (NH6) lifted Path C from 7/30 → 26/30 by swapping
  *only* the per-step executor (Sigil → Sonnet). The 19-task gap was the
  local model's per-step capability under Sonnet's decompositions. NH10
  + NH10b decomposed it further: ~26% language-proximity, ~74% scale-bound.
  No mid-size local model bridges the cloud gap on this benchmark.
- **The safety thesis was the most valuable piece and we never built it.**
  The original mammouth U09 sketch — type-system-enforced effects,
  capability-restricted IO — is exactly where novel language design pays
  off. We deferred it through every phase.

**What's next:**

The successor project (planned in a sibling repo, `post-sigil/PROJECT_PLAN.md`)
takes the unbuilt safety thesis as its headline product, on a Python-subset
host (Starlark) where the pre-training tax is paid down to nearly zero.
The value claim sharpens from "AI-native language" to **"agents can't
delete production databases by construction"** — declarative authorization
policies enforced by the language itself, not by the agent runtime's
interpretation of what the model emitted.

The sections below give the full retrospective.

---

## I. The original premise (2026-02-05, mammouth.ai sessions)

Sigil started from three explicit design directives recorded in the
day-zero design sessions (`papers/early_design_sessions/mammouth/`):

1. **"Make it 100% AI optimized and don't care about human usage"** — humans
   wouldn't read this code; the language target was the model's distribution,
   not human ergonomics.
2. **"AI can write programs reducing the risk of ambiguity that human-readable
   languages cause"** — explicit type annotations, canonical representation
   (one way to write each thing), formal grammar.
3. **"AISL would be the main code-generation layer of the AI agent which
   would then translate into human readable code if necessary"** — Sigil as
   the verified IR between AI generation and execution.

A fourth thesis was sketched in mammouth U09 but never built:

4. **Type-system-enforced effects + capability-restricted IO.** Every
   function type carries `Pure | IORead | IOWrite | Network` annotations.
   `(file_read path)` rejected at compile time if `path` is outside an
   embedder-supplied whitelist. Structural recursion guarantees termination.
   This was the safety story.

The bet was: a deliberately AI-shaped language with token efficiency,
canonical representation, deterministic execution, and effect-typed safety
would let small local models do agent tooling at cloud-quality reliability,
at low cost, *and safely by construction*.

---

## II. What we built

Over ~3 months of empirical work (Phase 0 → Phase 28 in `JOURNEY.md`):

| component | scope |
|---|---|
| Language | Prefix-Lisp surface, ~85 builtins, OCaml tree-walking interpreter, ~157 internal tests |
| Stdlib | `stdlib/core/prelude.sigil` auto-loaded helpers; PCRE-flavor regex; smart-argv |
| Corpus | 2323 validated training examples, sequentially generated through Sonnet |
| Fine-tuning | Local QLoRA on a 16GB AMD card (Navi31). 7 retrains across qwen + phi + deepseek bases |
| Validators | Static name validator (Tier A), 3B principle-based step-judge (Tier B), paren auto-balancer, "meet halfway" interpreter aliases |
| Harness | MCP server (`sigil_run_task`, `sigil_run_pipeline`); A/B/C agent harness with cached cloud baselines; Stream C single-step suite (30 tasks); Multi-step suite (30 tasks) |
| RAG | nomic-embed-text-based retrieval; principles-based judge prompt that generalizes OOD |
| Methodology | "Meet the model halfway", validator-in-loop, sequential corpus generation, soft-pass scoring discipline |

What we **did not** build:
- The effect-type system. None.
- Capability-restricted IO. None — `file_read` and friends are unconditional builtins.
- Termination guarantees. None.
- The Sigil → Python/JS/English translation layer.

---

## III. What made sense (validated by data)

### A. The methodology

The most durable contribution is the **experimental discipline**, not the
language. It transfers verbatim to the next project:

- **Validator-in-loop with surgical hints.** Catches a known failure shape
  (wrong language emission, unknown call-name, hallucinated builtin) and
  generates a targeted retry hint. Empirically converts ~15-25% of attempts.
  Implemented in `benchmark/sigil_name_validator.py` (Tier A).
- **Principles-based 3B step-judge.** Teaches a small model generic
  reasoning principles (numeric-limit, ordering, transformation-happened,
  filtering-applied) with synthetic domain-agnostic examples. Validated
  14/14 OOD on shapes the harness never saw. 0 FP on 131 historical task
  runs. Lifted multi-step Path C 6 → 7/30 in clean isolation.
  In `benchmark/sigil_step_judge.py` (Tier B).
- **Cross-base ensemble pattern.** Fresh-prompt + temperature=0 on
  alternative-base models so validator-hint pollution doesn't stomp on
  their natural reach. Lifted Stream C from 26/30 to 29/30.
- **Sequential corpus generation.** Parallel synthesis produced correlated
  examples that didn't teach diverse shapes. Sequential generation hit ~96%
  validity rate vs ~13% under parallel.
- **Soft-pass scoring discipline.** NH9 confirmed our exact-match grader
  isn't deflating local accuracy — the gap to cloud is real, not
  byte-pedantry artifact.

### B. Single-step delegation reaches cloud parity

**Stream C: 29/30 with qwen-sigil-v7 + deepseek-sigil ensemble vs Sonnet 29-30/30.**
At ~6× cheaper per task. This is Sigil's strongest value claim and it holds.
Single-step tooling delegation to a fine-tuned local model is *real*: parse,
filter, sort, count, format, regex-extract — the small model handles all of
this at cloud quality after sufficient corpus + retrain investment.

The deployment story for which Sigil was designed — "delegate single-step
tooling work to local models, keep orchestration on cloud" — works.

### C. "Meet the model halfway" is a transferable methodology

When the model misuses a construct consistently, the cheapest fix is not
prompt engineering or more fine-tuning — it's changing the language layer
to absorb the misuse. We did this for:

- Smart `(argv)` that handles both literal-vector and `\n`-joined inputs
  (NH8's predecessor at the language layer)
- `parse_float`, `to_int`, `first_index_of` aliases for what the model
  naturally types
- PCRE multiline default
- Bare language-header stripping (`python\n<code>`)
- Paren auto-balancer for ±1-2 closing-paren slips

This methodology has a discoverable trigger pattern (CONCLUSIONS.md CH12)
and ports cleanly to any future language target.

---

## IV. What didn't make sense (refuted by data)

### A. Designing a syntactically novel surface language for AI use

This is the core directive (#1) and the data refutes it on cost grounds.

- Sigil reached single-step parity (29/30) only after **7 retrains, a
  2300-entry corpus, and ~3 months of methodology work**.
- A baseline qwen2.5-coder:7b produces shape-correct Starlark on **37%** of
  the same task class with **zero fine-tuning, just a system prompt**
  (probe data, 2026-05-04, run outside the repo).
- The pre-training tax — the cost of pulling a model away from its native
  distribution to a novel surface — is the most expensive force in
  language-onboarding. We paid it for 3 months for ~5 tasks of multi-step
  benefit (NH10: Sigil → Python at fixed 7B size = +5/30 on Path C).
- The "humans don't read this code" framing assumed novel syntax was a
  *neutral* design choice. It wasn't. Every byte of distance from the
  pre-training center is a bring-up cost we paid in time and attempts.

What the data says: **for AI-only languages, syntactic distance from the
pre-training center should be measured and budgeted before any work begins**.
A Python-subset surface (Starlark-shape) is the cheapest viable distance.

### B. Token efficiency was not load-bearing

Directive #2 (canonical representation, type-safe, formal grammar) was
partially achieved (canonical representation strong, types softer than the
original sketch). Token efficiency for Sigil vs Python at equivalent tasks:
~10-15% denser. At 7B local inference cost, that's noise. At cloud cost,
it's small.

The "AI uses fewer tokens with Sigil" claim is true but doesn't pay for
the bring-up tax. The right design metric was never tokens-per-task; it
was **failure-modes-per-task**, which Sigil's effect system was supposed
to address (and didn't).

### C. Multi-step composition is not a language problem

NH6 (the orchestration-ceiling diagnostic) was decisive. Replacing only the
per-step executor — keeping Sonnet's decomposition, the same harness, same
shape annotations, same step-judge — lifted multi-step Path C from 7/30 to
**26/30**, equal to Path A's single-shot performance. The chained
orchestration is *not* lossy. The 19-task gap was purely the local 7B
Sigil model's per-step generation under Sonnet-decomposed step shapes.

NH10 + NH10b refined this: at fixed 7B, switching language target Sigil →
Python gains 5 tasks (12/30); scaling 7B → 22B with Python gains zero
(still 12/30). So the multi-step ceiling has two components:

- **~26%** language-proximity-driven (cheap to fix at language level)
- **~74%** scale-bound (not bridgeable mid-size; needs cloud or 70B+)

Sigil specifically can't move the larger share of this ceiling regardless
of corpus or retrain investment.

### D. The safety thesis was the most valuable piece and never got built

This is the project's largest gap. The U09 sketch — type-system-enforced
effects, capability-restricted IO, structural recursion guarantees — is
exactly the kind of contribution where a language change pays off. *Token
efficiency* and *canonical representation* are nice-to-have. *Safety
guarantees that prevent agents from deleting production databases* is a
real value claim that justifies novel language design.

We spent ~3 months pursuing the wrong half of the original thesis. The
single-step delegation work (left-hand path of the original architecture)
worked, but produces no safety guarantees. The safety / verifier work
(U09 thesis) was repeatedly deferred and is the one piece worth resuming
in a new project.

### E. Stronger orchestrators don't help limited executors

NH16 refuted the "scale up the orchestrator and the chain works better"
hypothesis: Opus orchestrating the same local Sigil executor *regressed*
Path C from 7/30 to 4/30. The orchestrator's decomposition style matters,
and a stronger orchestrator emits decompositions that exceed the
executor's competence band. There's a capability-matching sweet spot;
beyond it, more orchestrator capability is wasted or counterproductive.

---

## V. Transferable lessons

Concrete things the next project inherits without redoing:

1. **Methodology** — validator-in-loop, principle-based judging,
   meet-halfway absorption, sequential corpus generation, cross-base
   ensemble fallback (fresh prompt + temp=0).
2. **Infrastructure** — MCP server design, A/B/C harness shape, Stream-C
   suite as a per-step quality benchmark, soft-pass rescoring discipline.
3. **Empirical findings**:
   - Pre-training language proximity gains ~5/30 tasks on multi-step at
     fixed 7B size.
   - Mid-size local scale (7B → 22B) doesn't help in isolation on this
     benchmark.
   - The orchestration recipe is fine; executor capability is the gap.
   - Strong orchestrators must be calibrated to limited executors.
   - 3-epoch retrain on a corpus with synthesis-metadata artifacts overfit;
     cap retrains at 2 epochs or use early-stopping on held-out validation.
4. **Architectural patterns**:
   - Typed plan structure > free-text decomposition (CH11).
   - Capability-aware orchestrator routing (CH14).
   - Per-task model specialization is real — the python-coder ensemble
     measures different competences across same-size open coders.

Each of these was paid for once. The next project starts with them
already validated.

---

## VI. The link forward

The original mammouth U09 thesis — capability-restricted IO with declared
effects — was the most valuable piece of Sigil's design and never got
built. We deferred it through every phase because the language work was
in front of us. With Sigil's empirical answers in hand, that ordering can
flip: **build the safety story first, on a host where the surface
language doesn't have to be re-learned**.

The next project's bet:

> **Agent-safe local tooling.** Capability-typed Python subset, runtime
> effect verifier, sandboxed execution, audit-logged actions. Designed to
> make the failure mode "agent deletes a production database" structurally
> impossible.

Why this is a stronger bet than Sigil's original framing:

- The pre-training tax is paid down to nearly zero (Python-shape).
- The methodology Sigil validated transfers in full.
- The value claim ("agents can't delete databases by construction") is
  much sharper than "AI-native language" and addresses a real problem
  that organizations actually feel.
- Starlark/RestrictedPython are already mature embeddable hosts; the
  language work is reduced to *capability extension*, not invention.
- The ~26% language-proximity lift NH10 measured is preserved.

The new project's design plan lives in a sibling repo (`post-sigil/`),
under `CONCLUSIONS.md` and `PROJECT_PLAN.md`, which close Sigil's
strategic notes and open the next project's seed plan.

---

## VII. Numbers, for the record

Final headline metrics across all 30-task multi-step Path C runs
(`tools/agent_harness/abc_*_30task.json`):

| executor | Path C / 30 | provenance |
|---|---|---|
| qwen-sigil-v7:7b ensemble + judge + Tier A + shape ann | 7 | best Sigil setup |
| qwen2.5-coder:7b (Python) | 12 | NH10 |
| codestral:22b (Python) | 12 | NH10b |
| 22B+7B Python ensemble (oracle ceiling) | 18 | post-hoc union |
| 22B primary + 7B fallback live ensemble | 6 | NH10c — live regressed (VRAM swap thrash + wrong-shape bypass) |
| Sonnet (Python) per-step | 26 | NH6 + Path A both |

Stream C single-step:

| executor | Stream C / 30 |
|---|---|
| qwen-sigil-v7:7b + deepseek-sigil:6.7b ensemble + RAG | 29 |
| Sonnet (Python) | 29-30 |

This is what Sigil delivered. The single-step row is the durable
contribution. The multi-step row is the empirical answer to "where does
this approach plateau."

---

*Closed 2026-05-04. Next project planning continues in `post-sigil/`.*
