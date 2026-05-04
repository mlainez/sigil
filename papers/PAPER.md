# Sigil: An Empirical Study of AI-Native Languages, Pre-Training Bias, and the Cost of Novel Surface Design for Local LLM Tooling

**A retrospective research paper closing the Sigil project.**

---

## Abstract

We designed and implemented Sigil, a deliberately AI-shaped programming
language (prefix-Lisp surface, canonical representation, deterministic
runtime), as an experiment in *language-design-as-AI-reasoning-aid*:
we hypothesized that a language target shaped to the model's
distribution would let small local LLMs (≤22B parameters) do
agentic-AI tooling work at cloud-quality reliability and substantially
reduced cost. Over ~3 months we built a 2,300-entry training corpus,
ran 7 QLoRA fine-tunes across qwen2.5-coder, phi-4, and deepseek-coder
bases on consumer hardware (AMD RX 7800 XT, 16 GB), built a four-path
A/B/C/diagnostic harness with 30-task single-step and 30-task
multi-step suites, and tested 16 named hypotheses (H1-H9, NH1-NH16).

The single-step delegation result is positive and load-bearing: the
local Sigil ensemble reaches **29/30** on the Stream C single-step
tooling benchmark, parity with Claude Sonnet 4.6 (29-30/30), at ≈6×
lower per-task cost. The multi-step composition result is negative
and decisive: the best local Sigil configuration scored **7/30** on
the chained 30-task suite (`abc_v7_deepseekV1_judge_30task.json`),
and the orchestration-ceiling diagnostic — replacing only the
per-step executor with Sonnet writing inline Python while keeping
the same decomposition, harness, and shape annotations — lifted the
identical pipeline to **26/30** (`abc_NH6_sonnet_executor_30task.json`).
The 19-task gap is the local 7B Sigil model's per-step capability
under Sonnet-decomposed step shapes, not orchestration loss.

A controlled counterfactual on the same harness and orchestration —
qwen2.5-coder:7b writing Python instead of Sigil — scored 12/30
(`abc_NH10_local_python_30task.json`), a +5-task improvement at fixed
parameter count. Scaling the local Python executor to codestral:22b
returned an identical 12/30 (`abc_NH10b_codestral_22b_30task.json`),
demonstrating that scale gains are non-monotonic in the 7B-22B band.
This decomposes the 19-task NH6 gap as ≈26% language-proximity-driven
and ≈74% scale-bound (cloud-tier or 70B+ local).

We argue that the original premise of an AI-optimized, non-ambiguous
language splits empirically into a *valid* component (canonical
representation reduces model failure surface, effect-typed safety
guarantees would have real value) and an *invalid-at-consumer-scale*
component (designing a novel syntactic surface and training a model
from scratch on it is infeasible without trillions of unavailable
tokens and millions of dollars of GPU time). The valid component does
not require a novel surface and ports cleanly to a Python-subset host
(e.g. Starlark). The strongest unbuilt thesis from the project — type-
system-enforced effects with capability-restricted IO — is the right
direction for future research and is the natural successor project.

---

## 1. Introduction

### 1.1 Motivation

Today's agentic AI workflows route routine tooling work — log filtering,
CSV transformation, regex extraction, format conversion — through cloud
LLMs. Two costs are structural: (a) every call leaks filesystem layouts,
code patterns, and operational metadata across a third-party network
boundary [`papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`]; (b) cloud token
spend dominates the unit economics of long agent traces, especially
where the agent's "thinking" is dominated by writing-and-running
ephemeral programs over data. Local LLMs in the 7-14B class can run on
consumer GPUs but, at the time this project was started (2026-02), they
underperformed cloud frontier models by 30-50 percentage points on
exactly this shape of work.

This research asks whether designing the *target language* — rather than
asking the local model to imitate Python — closes that gap on the
isolated tooling-task subset, while preserving the privacy boundary
that drives the local-deployment use case in the first place.

### 1.2 Thesis (as stated 2026-02-05)

The Sigil project's day-zero design sessions (recorded as primary-source
artifacts in `papers/early_design_sessions/mammouth/`) gave four explicit
directives, two of which are the substantive thesis under test in this
paper:

1. *"Make it 100% AI-optimized and don't care about human usage."* The
   target was the model's distribution; human ergonomics were an
   accepted cost.
2. *"AI can write programs reducing the risk of ambiguity that human-
   readable languages cause"* — explicit type annotations, canonical
   representation (one way to write each thing), formal grammar.
3. *"AISL (later Sigil) would be the main code-generation layer of the
   AI agent which would then translate into human-readable code if
   necessary"* — Sigil as the verified IR between AI generation and
   execution.
4. **A type-system-enforced effect system** with capability-restricted
   IO (every function annotated `Pure | IORead | IOWrite | Network`,
   `(file_read path)` rejected at compile time if `path` outside an
   embedder-supplied whitelist, structural recursion guarantees
   termination). *Sketched in mammouth U09 and never built.* This is
   the safety story.

The bet was: a deliberately AI-shaped language with token efficiency
(directive 2), canonical representation (directive 2), deterministic
execution (directive 3), and effect-typed safety (directive 4) would
let small local models do agent tooling at cloud-quality reliability,
at low cost, and safely by construction.

### 1.3 Scope evolution (preview)

The project's scope contracted in two stages over ~3 months. We
foreshadow them here and develop them in §6:

- **First contraction (Phase 14-19):** from "general AI language" to
  "local LLM-native DSL for confidential tooling." The token-efficiency
  argument was empirically smaller than expected (~10-15%), and the
  agent-harness use case was the only deployment where the local
  ensemble's accuracy was competitive.
- **Second contraction (Phase 27-28, the present paper):** from "we
  need a new language for local tooling" to "for the reduced scope, a
  new language is *not* the right move; the methodology and the safety
  thesis are." This is the conclusion we defend below.

### 1.4 Contributions

- An empirical decomposition of the local-vs-cloud multi-step
  capability gap into a language-proximity component (≈26%) and a
  model-scale component (≈74%), measured on identical orchestration
  with three different per-step executors (Sigil, Python, cloud Python).
- A decisive diagnostic (NH6) showing that chained-pipeline
  orchestration is not lossy: the same pipeline that scores 7/30 with
  the local Sigil executor scores 26/30 with the Sonnet executor,
  isolating the gap to per-step code-gen capability.
- A reusable methodology for fine-tuning small local models on
  syntactically novel languages: validator-in-loop, principle-based
  small-model judges, cross-base ensembles, sequential corpus
  generation, and "meeting the model halfway" via language-layer
  absorption of pre-training reflexes.
- A clear assessment of the "AI-optimized, non-ambiguous language"
  thesis: split into a valid sub-claim (canonical representation +
  effect-typed safety) and an invalid-at-consumer-scale sub-claim
  (novel syntactic surface), with the consumer-hardware limits
  quantified.
- A concrete identification of what should be pursued in future
  research (the safety thesis, on a Python-subset host).

---

## 2. Background and Related Work

### 2.1 Token-efficient and AI-targeted languages

The intuition that a language designed for machine generation might
differ from a language designed for human reading is older than
LLMs (Lisp's S-expressions are an example), but the AI-coding boom
of 2022-2025 has given it new life. RPython
(PyPy's restricted Python subset), Starlark (Bazel/Buck2/Tilt's
configuration language), RestrictedPython (Zope's sandbox subset),
and Mojo (Modular's Python superset for ML) all live in the design
space of "languages that are easier than full Python for some
machine consumer." None of these is *AI-targeted* in Sigil's sense —
they predate LLM code generation as a primary use case.

The closest contemporary example is AICL/CANON-style sketches — the
ChatGPT and mammouth.ai design sessions Sigil grew from
[`papers/early_design_sessions/`]. The literature on actually
deploying AI-native languages with empirical accuracy measurements is
thin; this paper is one data point.

### 2.2 Local LLM inference for code

The relevant model families are qwen2.5-coder (Alibaba, 0.5B-32B
range, Apache-2 licensed, dense), deepseek-coder (DeepSeek, 1.3B-33B
range, MIT licensed), codestral (Mistral, 22B dense), and phi-4
(Microsoft, 14B). All four are trained extensively on Python and
common languages; none has meaningful training data for prefix-Lisp
languages or for Sigil specifically. Their zero-shot accuracy on
single-step tooling-shaped Python tasks at the 7B scale is ~50-70%
on the suites we used; at 22B-32B it climbs to ~70-80%; the cloud
frontier (Sonnet 4.6) sits at ~95%.

### 2.3 The agent-tooling use case

Agentic-AI workflows — Claude Code, opencode, Cursor, Aider, custom
agentic scaffolds — generate short Python or Bash programs that
execute locally against the user's data. The pattern is: cloud LLM
emits code, host runs code, host returns stdout to the cloud LLM,
cloud LLM uses stdout to drive the next decision. The cloud LLM is
doing two distinct things: orchestration (planning the next step,
synthesizing answers) and code-gen (writing the Python that
processes data). Sigil targeted the second of those, intending to
keep orchestration on the cloud and delegate per-step code-gen to a
local model speaking a more model-friendly target language.

### 2.4 The confidentiality boundary

The privacy argument for local execution is independently strong and
not contingent on Sigil's accuracy story. We documented it in
`papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`: cloud cloud-LLM tooling
calls leak filesystem layouts, code patterns, intent, and sometimes
sample data; provider retention policies and regulatory frameworks
(GDPR, CCPA, EU AI Act, HIPAA, SOX, CMMC) make this a real exposure
for many deployments. Local execution closes this boundary
unconditionally — even before any accuracy result. This motivates
the project even when the language-design subclaim doesn't pay off.

---

## 3. The Original Premise and Project Scope

### 3.1 Design directives

We restate the four directives from §1.2 with implementation status as
of close-out (2026-05-04):

| # | Directive | Status |
|---|---|---|
| 1 | "100% AI-optimized" surface | **Held in syntax.** Sigil today is S-expression, prefix-only, no infix operators, no human-ergonomic sugar. |
| 2 | Canonical representation, type-safe, formal grammar | **Mostly held.** Canonical representation strong; type system softer than original sketch (type inference for `(set ...)` since 2026-04-22; explicit types still required for `(fn ...)` parameters). |
| 3 | Sigil as verified IR between AI and human-readable target | **Half-built.** Left-hand path (LLM emits Sigil → OCaml interpreter executes) is the project's central artifact and works. Right-hand path (Sigil → Python/JS/English translation for human review) was never implemented; the agent harness consumes stdout, not source. |
| 4 | Type-system-enforced effects, capability-restricted IO, structural recursion guarantees | **Never built.** This is the load-bearing gap between the original thesis and the current artifact. |

The detailed phase-by-phase narrative of how directives 1-3 were
implemented and where they bent under empirical pressure is in
`papers/JOURNEY.md` (Phases 0-28). The "meeting the model halfway"
methodology that *softened* directive 1 in practice is documented in
`papers/MEETING_HALFWAY.md`.

### 3.2 Original scope

The day-zero scope was deliberately broad: a general-purpose programming
language with AI-friendly properties, with the agent-tooling use case as
the first concrete deployment but not the only one. The token-efficiency
argument was framed as "valuable for any AI code generation," not just
for tooling. The safety story was "for any agent that runs generated
code," not just for filesystem-touching tooling.

This scope did not survive contact with the data, in two distinct
contractions detailed in §6.

---

## 4. Methodology

### 4.1 Implementation

All implementation lives in this repository. Cross-referenced as needed:

- **Interpreter:** `interpreter/*.ml` — OCaml tree-walking interpreter,
  ~85 builtins, ~157 internal tests (2 of which are now failing
  per the project-closed snapshot; see `interpreter/test/`).
- **Standard library:** `stdlib/core/prelude.sigil` — auto-loaded
  helpers (paren-balancer, string utilities, etc.).
- **Training corpus:** `benchmark/training_corpus.jsonl` — 2,323
  validated examples generated sequentially via Sonnet (parallel
  generation produced ~13% validity vs ~96% sequential, see
  `memory/feedback_corpus_generation.md`).
- **Fine-tuning pipeline:** `benchmark/finetune_local.py` — QLoRA on
  AMD ROCm, BF16 + 4-bit nf4, lr=2e-5, max_seq=1024, warmup_ratio=0.2,
  max_grad_norm=1.0 (recipe stable on Navi31; details in
  `memory/feedback_navi31_qlora.md`).
- **Validators:** `benchmark/sigil_name_validator.py` (Tier A: static
  name-validity), `benchmark/sigil_step_judge.py` (Tier B: principle-
  based 3B step-judge with deterministic pre-checks).
- **Harness:** `tools/agent_harness/agent_ab_harness.py` — four-path
  A/B/C/diagnostic harness with cached cloud baselines, judge wiring,
  shape-annotation, and pluggable executors (sigil / sonnet / python
  / python-ensemble).
- **MCP server:** `tools/agent_harness/sigil_mcp_server.py` — three
  tools (`sigil_run_task`, `sigil_run_code`, `sigil_capabilities`) for
  Claude Code / opencode integration.

### 4.2 Benchmarks

We define two benchmark suites, both n=30, both included in the repo:

- **Stream C single-step tooling** (`benchmark/real_tooling_tasks.json`):
  30 single-shot tasks of the form "given input X as $0, produce
  output Y" — common shell shapes (cut/grep/sort/uniq/sed-style),
  format conversion (CSV ↔ JSON ↔ markdown), regex extraction. Each
  task has an exact-match expected stdout. Detailed spec and
  per-task pass/fail tables in `benchmark/STREAM_C_RESULT.md`.
- **Multi-step agentic 30-task suite**
  (`tools/agent_harness/agent_tasks.json`): 30 tasks that naturally
  decompose into 2-3 single-step sub-tasks (filter→count→sort,
  parse→aggregate→format, etc.). Used to measure compositional
  capability over chained pipelines.

Both suites are exact-match-graded on stdout. We verified that this
strict comparison is not artificially deflating local accuracy by
re-scoring under graduated softer comparators (whitespace-strip,
whitespace-collapse, line-unordered-when-no-sort-asked) — the gap to
cloud changes by 0-1 task across all configurations. The exact-match
result is the real result. (NH9, refuted; details in
`papers/HYPOTHESES.md`.)

### 4.3 Architectural paths

The harness measures four configurations on each task. We report
`pass/30` for each:

- **Path A — Cloud-only:** Sonnet writes Python, host executes
  Python, Sonnet ingests stdout. Baseline.
- **Path B — Hybrid (single-step delegation):** Sonnet decides to
  delegate, calls `sigil_run_task` once with a one-sentence
  description and the input; local Sigil ensemble produces and runs
  Sigil; Sonnet summarizes. Tests the value claim "delegate per-step
  tooling work to local."
- **Path C — Chained-hybrid (multi-step delegation):** Sonnet
  decomposes the task into 1-3 single-step descriptions, the harness
  threads stdout→stdin between calls, each step calls the local Sigil
  ensemble. Tests whether chained single-step delegation closes the
  multi-step gap.
- **Diagnostic paths (NH6, NH10, NH10b, NH10c, NH16):** Path C with
  the per-step *executor* swapped (Sonnet writing Python; local 7B
  writing Python; local 22B writing Python; 22B+7B ensemble) or with
  the orchestrator swapped (Opus instead of Sonnet). These isolate
  *which* of orchestration, executor language, executor scale, and
  orchestrator capability is binding.

### 4.4 Models trained and evaluated

The project ran two distinct fine-tuning eras. The full catalog of
both is in `papers/MODEL_VERSIONS.md`.

**Cloud era (sigil-v1 through sigil-v5, deprecated and removed).**
The first 5+ fine-tunes used together.ai's hosted LoRA API on
qwen3-8b, qwen3-coder-30b (MoE), and qwen2.5-coder-7b bases at
n_epochs=3-4, lr=1e-5, with a hand-crafted ~145-example training
set. The killing blow was sigil-v5: a small training corpus on a
stock cloud-LoRA configuration produced a model that scored 13%
on the early Stream C suite — vastly worse than untuned Sonnet at
comparable inference cost. This is what empirically validated the
pivot to local QLoRA: cloud LoRA had unfavorable unit economics
*and* didn't actually beat the cloud frontier. The cloud-LoRA
infrastructure (`benchmark/finetune.py`) was deleted in commit
`f46d6a7`; together.ai access was retained for one-off Sonnet
calls only. The exact lineage of which adapter became
sigil-v1/v2/etc. is partially lost; only one cloud-era result file
survives in-repo (`benchmark/eval_v5_qwen2.5-7b.json`). This era
is the empirical foundation for the local-QLoRA-on-consumer-
hardware approach the rest of the project took.

**Local era (sigil-v3 through v7, deepseek-sigil, phi-sigil).**
Local QLoRA on the AMD RX 7800 XT, recipe and rationale in §4.1.
The production stack at close-out:

- **Primary executor:** `qwen-sigil-v7:7b` — qwen2.5-coder-7b base,
  QLoRA-tuned on the v7 corpus (commit `f65e802` and antecedents).
- **Fallback executor:** `deepseek-sigil:6.7b` — deepseek-coder-6.7b-
  instruct base, 2-epoch QLoRA. (A 3-epoch retrain `deepseek-sigil-v2`
  was attempted on 2026-05-04 and *regressed* Stream C from 23/30 to
  19/30 due to overfit on training-corpus metadata headers; rolled
  back. NH3 in `papers/HYPOTHESES.md`.)
- **Step-judge:** `qwen2.5-coder:3b` (no fine-tune) — used as a
  small principle-based judge for intermediate-step shape correctness.

---

## 5. Results

### 5.1 Single-step tooling delegation (the positive result)

The Stream C suite measures the project's strongest claim. The local
Sigil ensemble's progression across versions
(`benchmark/STREAM_C_RESULT.md` and `papers/HYPOTHESES.md` H1, H3, H4):

| Configuration | Pass | Date | Notes |
|---|---|---|---|
| sigil-v5 (together.ai cloud LoRA, qwen2.5-coder-7b base) | ~13% | 2026-03 | Killed the cloud-LoRA path; details in `papers/MODEL_VERSIONS.md` |
| qwen-sigil-v3 base, no RAG | 13/30 | 2026-04 | Pre-PCRE, pre-corpus expansion (first local QLoRA) |
| v6 + PCRE corpus + RAG | 27/30 | 2026-04 | After regex backend swap, +77 seeds |
| v6 + phi-sigil-v1 fallback + RAG | 28/30 | 2026-04 | Cross-base ensemble pattern |
| v6 + phi-sigil-v2 fallback + for-iterator-guard + RAG | 29/30 | 2026-05-03 | Production until 2026-05 |
| **v7 + deepseek-sigil:6.7b fallback + RAG (close-out)** | **29/30** | 2026-05-04 | Final production |
| Sonnet 4.6 (Path A baseline) | 29-30/30 | 2026-04..05 | Cloud reference |

The local ensemble's single failure (`shell_argv_count`, the project's
hardest persistent residual that survived 7 retrains) does not overlap
with Sonnet's single failure (`split_at_blank_lines`, cosmetic spec
adherence on multi-trailing-newline). A trivial cascade (try local
first, fall back to cloud on local failure) yields a combined 30/30
at 1/30-th cloud cost. This is the deployment-ready single-step
delegation story.

Energy and cost (from `benchmark/measure_gpu_power.py` calibration on
RX 7800 XT, 1 Hz `amdgpu_top` sampling): production-config
workload-attributable 0.367 Wh/task; total wall ~218 s for 30 tasks;
$0.000 per task vs $0.0028 (Sonnet) for the same suite. The savings
claim — *delegate per-step tooling to local at near-zero marginal
cost without sacrificing accuracy* — is empirically defensible at the
single-step granularity.

**The single-step delegation thesis is validated.**

### 5.2 Multi-step composition (the negative result)

The 30-task multi-step suite tells a different story. Best Sigil
configuration (`abc_v7_deepseekV1_judge_30task.json`, qwen-sigil-v7
primary + deepseek-sigil fallback + Tier A static name-validator +
Tier B 3B step-judge + shape-annotation):

```
Path A (cloud-only):   26/30
Path B (hybrid 1-step): 5/30
Path C (chained):       7/30
```

Path B and Path C both lose ~20 tasks to Path A. The chained
delegation story — "decompose into single-step Stream-C-shaped tasks,
each handled by the local ensemble" — does not reach within 60% of
the cloud baseline. Successive interventions (validator-in-loop,
shape annotation, judge-driven retry, ensemble fallback) produced
small lifts (typically +1-2 tasks per intervention) but never moved
the floor above 7/30.

The full hypothesis-by-hypothesis record with per-task gains and
losses is in `papers/HYPOTHESES.md`.

### 5.3 The decisive diagnostic: NH6 (orchestration ceiling)

We hypothesized that the multi-step ceiling could be either an
*orchestration* limitation (the chained recipe loses information
across steps) or an *executor* limitation (each individual step is
harder for the local model than the single-step Stream C tasks
suggest). NH6 is a clean diagnostic that separates these. We replaced
*only* the per-step executor — keeping Sonnet's decomposition, the
same harness, the same shape annotations, the same step-judge — with
Sonnet writing inline Python per step.

Result (`abc_NH6_sonnet_executor_30task.json`):

| Path C executor | Pass |
|---|---|
| qwen-sigil-v7 writing Sigil | 7/30 |
| **Sonnet writing per-step Python** | **26/30** |

A single change in the per-step executor lifted the same chained
pipeline by 19 tasks. The orchestration recipe is *not* lossy. The
gap is the 7B local model's per-step capability under Sonnet-
decomposed step shapes. **The multi-step ceiling is a code-gen
problem, not an orchestration problem.**

This result has retroactive consequences:

- Every prior interpretation of "Path C = X/30" as a chained-pipeline
  bound was wrong. It was an executor-capability bound under a
  specific orchestration recipe.
- Sigil-side interventions (more retrains, more corpus, better
  RAG) cannot move the structural component of the gap.
- The chained sub-agent thesis (H8 in `HYPOTHESES.md`) — "single-step
  Stream-C strength translates to multi-step via decomposition" —
  fails not because decomposition is wrong, but because *Sonnet's
  decomposition produces step shapes the 7B Sigil model can't write
  cleanly*. Strong-orchestrator decompositions assume strong-
  executor capability.

### 5.4 Decomposing the executor gap: NH10, NH10b, NH10c

Given NH6 isolated the gap to executor capability, we ran a series
of executor-substitution diagnostics on the same orchestration to
quantify *language* vs *scale* contributions.

**NH10 (Python-as-control, qwen2.5-coder:7b)**: same harness, same
orchestration, qwen2.5-coder:7b (no Sigil fine-tune) writing Python
per step. Result: **12/30**
(`abc_NH10_local_python_30task.json`).

That is +5 tasks vs the 7B Sigil ensemble at 7/30, on the same
parameter count. The marginal effect of switching the language
target from Sigil to Python at fixed model size is ≈+5/30. Tasks
gained are the regex/sort+take/cumulative-arithmetic shapes where
Python's `re` module and built-in list/dict ergonomics are exactly
what the 7B knows.

**NH10b (Python at 22B, codestral:22b)**: same harness, codestral:22b
writing Python. Result: **12/30**
(`abc_NH10b_codestral_22b_30task.json`).

The 3× larger local executor produced *the same total*. The composition
of which 12 tasks pass shifted (22B gained 6 structural-parsing tasks,
lost 6 regex-extract tasks; the disjoint-strengths pattern is a
robust observation), but the count did not move. **Scale is non-
monotonic in the 7B-22B band** on this benchmark.

**NH10c (live primary→fallback ensemble, codestral:22b → qwen-coder:7b)**:
the post-hoc oracle union of NH10 and NH10b is 18/30 — the two models
pass disjoint task subsets. We tested whether a live primary→fallback
ensemble (codestral primary; if codestral fails clearly, fall back to
qwen-coder) could approach this oracle.

Result: **6/30** (`abc_NH10c_python_ensemble_30task.json`). Worse
than either model alone. Mechanics: the fallback gates on "primary
errored or empty stdout"; codestral's wrong-shape-but-non-empty
outputs bypass the fallback and lock in the wrong answer. Plus the
combined VRAM (12 GB + 4.7 GB = 16.7 GB > 16 GB card) caused ollama
to swap the loaded model out and back per call, which appears to
have degraded generation quality. **Simple primary→fallback
ensembles do not capture the disjoint-strengths union.** A
production-effective ensemble would require either per-task model-
shape routing or running both unconditionally with deterministic-
check picking — both architectural moves beyond simple stacking.

**Decomposition of the 19-task NH6 gap:**

| Component | Tasks | Share |
|---|---|---|
| Language proximity (Sigil → Python at 7B) | +5 | ≈26% |
| Scale (7B → 22B local Python) | +0 | ≈0% (in this band) |
| Scale (22B local → cloud Sonnet Python) | +14 | ≈74% |
| Total | 19 | 100% |

The scale axis is *non-monotonic*: a much larger jump (likely 70B+
local or cloud-tier) is required to manifest the 14-task share.
There is no mid-size local sweet spot for hard composition on this
benchmark.

### 5.5 The orchestrator-capability test: NH16

We further hypothesized that a stronger orchestrator might produce
decompositions whose per-step descriptions land closer to the local
executor's competence band, lifting Path C even with the executor
unchanged. We swapped the orchestrator from Sonnet to Opus, keeping
the Sigil executor.

Result (`abc_v7_judge_shapeann_OPUS_30task.json`):

| | Sonnet orchestrator | Opus orchestrator |
|---|---|---|
| Path B | 5/30 | 1/30 |
| Path C | 7/30 | 4/30 |
| avg n_steps (C) | 1.70 | 2.03 |
| Cloud cost | $0.16 | $1.07 (6.6×) |

Opus *regressed* both Path B (−4) and Path C (−3) at 6.6× the cloud
cost. The mechanism: Opus over-decomposes (avg n_steps 1.70 → 2.03,
matching the regression pattern from a separate hypothesis where we
explicitly instructed Sonnet to "prefer shorter atomic steps") and
emits more verbose step descriptions that the 7B local executor
cannot track. Free-text decompositions inherit the orchestrator's
style; Opus's style exceeds the limited executor's competence band.

This is the LLM analogue of the "teacher-student gap" in knowledge
distillation: a teacher (orchestrator) too far above the student's
(executor's) capability distribution becomes counterproductive.
**Orchestrator-executor capability calibration is a first-class
hybrid-stack design variable.** A weaker local executor cannot keep
up with a strong orchestrator's natural decomposition; pairing them
requires either (a) passing the executor's capability profile to the
orchestrator, or (b) constraining the orchestrator's output via a
typed plan schema with bounded step complexity.

### 5.6 Summary of all tested hypotheses

The full record is in `papers/HYPOTHESES.md`. Headline status:

| ID | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | Token-efficient AI-native language is reachable | Validated, single-step only | 29/30 Stream C |
| H2 | Fine-tuning a small model on Sigil reaches frontier on tooling | Validated, single-step only | 29/30 Stream C ensemble |
| H3 | Cross-base ensemble outperforms single model | Validated | +2 tasks, complementary failures |
| H4 | RAG retrieval scales corpus-size linearly | Validated up to 30 tasks | v6+RAG 27/30 vs v6 no-RAG 15/30 |
| H5 | Validator-in-loop closes the gap | Validated, +2-3 tasks | Hint-driven retry conversion ~15-25% |
| H6 | Single-step success translates to multi-step | **Refuted** | Stream C 29/30 ↛ Path C 7/30 |
| H7 | "Meeting halfway" is the operational design philosophy | Validated | Documented in `MEETING_HALFWAY.md` |
| H8 | Chained sub-agent closes the multi-step gap | **Refuted** | Path C 7/30 stays at 7/30 across interventions |
| H9 | Pure retraining on richer corpus moves the floor | **Refuted** | v7 retrain didn't lift Path C |
| NH1 | Different base model would help | Mostly refuted | DeepSeek 18/30, codestral 19/30, no path to lift |
| NH2-A | Static name+language pre-validator | Validated | +1 task on Path C |
| NH2-B | Principle-based 3B step-judge | Validated | +1 task on Path C, 0 FP across 131 historical runs |
| NH3 | DeepSeek-coder fine-tune as fallback | Validated as 2-epoch | 23/30 Stream C; 3-epoch overfit, rolled back |
| NH5 | 30-task multi-step suite | Validated as benchmark | Replaced 8-task suite |
| NH6 | Orchestration ceiling diagnostic | **Decisive** | Path C 7→26 with Sonnet executor |
| NH8 | Input-shape annotation per step | Net-zero | Mechanism right, blanket application breaks simple tasks |
| NH9 | Soft-pass scoring closes gap | **Refuted** | Gap unchanged under any reasonable softer comparator |
| NH10 | Python-as-control on same harness | Partial confirmation | +5/30 from language-only swap at 7B |
| NH10b | Larger local Python executor (22B) | Refuted (no scale benefit in band) | Same 12/30 as 7B |
| NH10c | Live primary→fallback ensemble | **Refuted** | Regressed to 6/30 |
| NH16 | Stronger orchestrator helps limited executor | **Refuted** | Opus regressed Path C 7→4 at 6.6× cost |

The strategic question — *can the chained-Sigil-delegation thesis be
made to work on consumer hardware?* — was answered "no, not at any
intervention we tested" by NH6 + NH10 + NH10b + NH16 acting in
combination. The remaining hypotheses that were closed without
testing (NH7 N-of-K sampling, NH11 templates, NH12 typed state, NH13
corpus coverage gap analysis, NH14 self-critique) are all refinements
that would change the picture by ±1-3 tasks at most, not by the 19
tasks needed to close the gap.

---

## 6. Scope Evolution: From General Language to Local Tooling DSL

### 6.1 First contraction (Phase 14-19, late 2026-04 to early 2026-05)

The day-zero scope (general-purpose AI-friendly language) survived
the early empirical work because the early benchmarks were small
isolated tasks where Sigil's token efficiency and canonical
representation were neither helpful nor harmful relative to Python.
The argument shifted in two phases:

- **Phase 14-15 ("meeting the model halfway"):** the practical Sigil
  acquired ~30 aliases (`parse_float` for `float`, `to_int` for
  `parse_int`, etc.) and parser tolerances (paren auto-balancer,
  language-header strip, smart-argv) that softened directive 1.
  The "ONE WAY ONLY / 100% AI-optimized" framing became
  aspirational; the practical Sigil admits whatever shape the
  pre-trained model reaches for. (`papers/MEETING_HALFWAY.md`.)
- **Phase 17-18 (the value-claim retrospective):** with the language
  surface stabilized, we asked which deployment would actually
  *use* Sigil in production. The answer that survived honest
  examination was: agentic-AI tooling — local model writes short
  programs that run on the host against the user's data, where the
  privacy and cost arguments (`papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`)
  are independently strong. The general-purpose framing dropped
  out: writing application code, libraries, full systems in a novel
  prefix-Lisp surface had no buyer-side argument that overcame the
  human-readability cost.

The first contraction produced the official scope of the v2 research
plan (`benchmark/RESEARCH_PLAN.md`): "Sigil as a Local LLM-Native DSL
for Confidential Tooling." The corpus, retrains, and harness from
that point on were tuned to that scope.

### 6.2 Second contraction (Phase 27-28, 2026-05-04, the close-out)

The second contraction is the contribution of this paper. The
empirical results of §5 — particularly the NH6 + NH10 + NH10b
combination — argue that **for the reduced scope, a new language is
not the right move**. The case is:

1. **NH6 isolated the multi-step ceiling to executor capability**, not
   to chained-orchestration loss. The 19-task gap is the local 7B
   Sigil model's per-step generation capability under Sonnet-
   decomposed step shapes.
2. **NH10 measured the language-vs-scale split** at fixed 7B size:
   ≈26% of the gap is language-proximity-driven, ≈74% is scale-
   bound. The language share is real but minority.
3. **NH10b showed scale is non-monotonic** in the deployable band:
   7B → 22B local Python yields 0 task improvement on this benchmark.
   The remaining 14 tasks of the gap require either cloud-tier or
   70B+ local executors, neither of which is the Sigil project's
   target deployment.
4. **The Sigil-specific bring-up cost is the project's largest
   expense.** ~3 months of corpus generation (2,323 entries), 7
   QLoRA retrains, parser-level absorption work, validator
   infrastructure, harness construction. A baseline qwen2.5-coder:7b
   writing Starlark with zero fine-tuning and a 50-line system
   prompt scored 37% shape-correct on a multi-step Path-C-shape probe
   on n=8 representative tasks (probe data, 2026-05-04, kept outside
   this repo per project decision). The pre-training proximity tax
   for a Python-subset target is paid down to nearly zero.

The conclusion: the methodology Sigil developed is the durable
contribution. The language Sigil designed is not. For local tooling
work, a Python-subset target (Starlark, RestrictedPython, or a
similar embeddable Python-subset host) inherits the language-
proximity benefit (≈+5 tasks at fixed 7B) without paying the bring-
up cost.

### 6.3 What survives both contractions

- The methodology (validator-in-loop, principle-based judging,
  cross-base ensemble fresh-prompt-temp-0, sequential corpus
  generation, soft-pass scoring discipline, meet-halfway).
- The harness shape (MCP server with three tools, A/B/C/diagnostic
  paths, cached-cloud-baseline pattern).
- The single-step delegation deployment story (Stream C 29/30 at
  ≈6× lower cost than cloud).
- The privacy / confidentiality argument (independent of the
  language-design subclaim).
- The unbuilt safety thesis (directive 4): type-system-enforced
  effects + capability-restricted IO. We argue in §9 that this is
  the right direction for follow-on work.

What does *not* survive is the case for designing a *novel
syntactic surface* as the AI-tooling target. That sub-claim is
refuted on cost grounds alone, even before its incremental accuracy
benefit (≈+5 tasks vs Python at fixed model size) is weighed against
the 3-month bring-up.

---

## 7. Assessment of the AI-Optimized, Non-Ambiguous Language Thesis

The original thesis bundled three claims under "AI-optimized,
non-ambiguous language." The data forces us to evaluate them
separately.

### 7.1 Claim A: Token efficiency

*Sub-claim:* Sigil's prefix-Lisp surface and short builtin names
produce shorter programs than Python for equivalent tasks, and that
shorter output translates to lower model latency, lower cost, and
better small-model accuracy.

*Evidence:* token-count audits across the corpus (`benchmark/
tokenizer_audit.py`) show Sigil at ~10-15% denser than Python on
cl100k_base for the tooling-task subset. Notably this gain comes
*only* when builtin names are common dictionary words (`split`,
`sort`, `len`, `fmt` — all 1-token). Vowel-stripping or compound
underscore names (`array_get`, `string_to_int`) make tokenization
*worse*, not better, because BPE merges high-frequency English
words but fragments unusual character sequences (corpus generation
memo `feedback_corpus_generation.md`).

The 10-15% token gain at 7B local inference is noise; per-task
inference time on RX 7800 XT is dominated by model load + KV-cache
warm-up rather than output token count. At cloud inference cost it
is small. It does not pay for the bring-up tax.

**Verdict: claim A is true in the strict measurement sense but not
load-bearing for the project's value claim.** The right design
metric was never tokens-per-task; it was *failure-modes-per-task*,
which the safety claim (D, below) was supposed to address.

### 7.2 Claim B: Canonical representation

*Sub-claim:* "One way to write each thing" reduces the surface area
where the model can produce subtly-wrong programs (e.g. multiple
ways to express list comprehensions, multiple ways to format
strings, multiple ways to iterate). Canonical representation
narrows the failure manifold.

*Evidence:* directly observable. Sigil today admits ~30 aliases for
common operations (the meet-halfway compromise of §6.1) — but the
*canonical* form to which they normalize is unique. The model can
reach for any pretrained-Python idiom; the parser canonicalizes;
the canonical form is what the corpus, the runtime, and the
test-validator all consume. We never observed a class of failure
that a non-canonical Sigil would have prevented and a canonical
Sigil enabled.

But canonical representation does *not* require a novel surface.
Restricted-Python subsets (Starlark in particular) achieve the same
property by *removing* features (no while loops, no comprehensions
over mutable state, no list/dict mutation outside specific contexts)
rather than by *replacing* the surface syntax. The canonical-rep
benefit is real but *language-independent*: it can be obtained on a
Python-subset target as well as on a prefix-Lisp target.

**Verdict: claim B is real and valuable but does not motivate a
novel surface language.** It motivates *some constraint* on the
surface; restricted-Python suffices.

### 7.3 Claim C: AI-optimized syntax (ambiguity reduction via parse
clarity)

*Sub-claim:* prefix S-expression syntax is unambiguous to parse
(no precedence rules, no infix), reducing the model's failure
modes around operator precedence, statement-vs-expression confusion,
and similar parsing-relevant errors.

*Evidence:* mixed. We did observe specific Python-side parsing
errors that Sigil's prefix syntax made impossible (chained
comparison precedence in particular: NH8 found qwen-sigil-v7
correctly using `(and (ge x 10.0) (le x 50.0))` where Python
`10.0 <= x <= 50.0` is correct in Python but rejected by Starlark's
no-chained-comparison rule). On the other hand, the prefix syntax
introduced new failure modes: paren-balance errors (which the
paren-balancer absorbs), unfamiliar-to-pretrained-models lambda
syntax (`(\p body)`), and sometimes lower attention to argument
order because the prefix form puts the operator first.

Net: claim C trades one set of failure modes for another. The new
failures are *novel-to-the-model* (because the model has seen
~zero prefix-Lisp in training) while the old failures are
*pretrained-but-tractable* (because the model has seen Python
chained comparisons billions of times). At small fine-tune scale
(2,300 examples), the trade did not net positive.

**Verdict: claim C is partially true (some Python failure modes are
eliminated by prefix syntax), but the new failure modes introduced
by syntactic novelty are larger in practice.** A
restricted-Python target keeps the model on its native distribution
while still excluding the worst-of-Python failure modes by removing
the offending features.

### 7.4 Claim D: Effect-typed safety

*Sub-claim:* every function carries a static effect annotation
(`Pure | IORead | IOWrite | Network`); IO operations are gated by
an embedder-supplied capability whitelist checked at compile time;
structural recursion guarantees termination. *(The mammouth U09
sketch.)*

*Status:* not built. The claim is therefore not empirically tested.
But the empirical results we *do* have argue strongly that this is
the part of the original thesis that would have produced *value
unobtainable from a Python-subset alternative*. Restricted-Python
subsets deliver canonical representation and AI-friendly parse
clarity for free; what they do *not* deliver is statically-checked
effect annotations or capability-bounded IO at the language level.

Bazel's Starlark approaches this property by *removing* I/O from
the surface entirely (no filesystem, no network, no time, no env)
and routing all effecting operations through host-registered
builtins. That is one valid implementation of capability-bounded
IO; it is closer to "no effects" than to "tracked effects." The
mammouth U09 thesis was richer: not "no I/O" but "I/O whose effects
are statically annotated, whose targets are capability-checked, and
whose audit is structurally guaranteed."

**Verdict: claim D is the part of the original thesis that
genuinely justifies a novel language design.** It is also the
part the project did not build.

### 7.5 Combined assessment

Claims A and C do not justify a novel syntactic surface at consumer
fine-tuning scale. Claim B is real but achievable on restricted-
Python without a novel surface. Claim D is the part that would
have justified the project — and is the part still on the table
for follow-on work.

The right reading of the original thesis is therefore: the *non-
ambiguous, safety-by-construction* core is valid; the *AI-optimized
syntactic surface* dressing is invalid at consumer scale.

---

## 8. Pre-Training From Scratch: Feasibility on Consumer Hardware

A natural objection to §5's results: *we never trained a model from
scratch on Sigil; we only QLoRA-adapted models pretrained on Python.
A model with sufficient Sigil exposure during pre-training would not
suffer the pre-training-bias tax. Could that change the verdict?*

We address this directly.

### 8.1 The cost of fine-tuning at consumer scale

A QLoRA fine-tune of a 7B model on the 2,323-entry Sigil corpus,
3 epochs, max_seq=1024, took ~3 hours on the AMD RX 7800 XT (16 GB
VRAM, ~300 W board power). Energy cost: ~1 kWh per retrain. 7
retrains over the project's 3 months: ~7 kWh, ~$1-2 in electricity
(`benchmark/measure_gpu_power.py` calibration; Phase 9 onward in
`papers/JOURNEY.md`).

A QLoRA fine-tune of a 22B model on the same corpus would have taken
~10-12 hours on the same hardware (we did not run this; the
estimate is from `codestral:22b` inference latency × proportional
training-step wall-time). VRAM is binding: a 4-bit quantized 22B
QLoRA fine-tune just fits in 16 GB; a 32B model does not without
multi-GPU splitting or CPU offload.

These are accessible costs. QLoRA on consumer hardware is the
path the project actually took — but not the path it tried first.
The early phases (sigil-v1 through v5) used together.ai's hosted
LoRA fine-tune API at ~$10-20 per training run. The final cloud-era
fine-tune (sigil-v5, on Qwen2.5-7B-Instruct) scored ~13% on the
early Stream C suite at real per-token inference cost. That result
killed the cloud-LoRA path: it cost real money to *run* (cloud
inference is not free per-token like local) and didn't beat untuned
cloud frontier models at comparable cost. Local QLoRA — slower per
retrain in human wall-time but free at inference and fast enough at
training time on consumer hardware — was the only fine-tuning path
with viable unit economics at our scale. (Detail in
`papers/MODEL_VERSIONS.md` "Cloud era" section.)

### 8.2 The cost of pre-training a foundation model from scratch

Modern foundation code models in the 7B-14B class are pre-trained on
trillions of tokens on hundreds-to-thousands of A100/H100/MI300X-
class GPUs over weeks-to-months. Public estimates (qwen2.5-coder
technical reports, deepseek-coder technical reports, codestral
release notes):

- **7B class:** ~5-10 trillion training tokens; ~100-500 H100-equivalent
  GPU-months; ~$50K-200K cloud compute spend.
- **70B class:** ~10-30 trillion training tokens; ~5,000-20,000 H100
  GPU-months; ~$500K-5M cloud compute spend.
- **State-of-the-art frontier (Sonnet/Opus class):** undisclosed,
  estimated tens to hundreds of millions of dollars.

These numbers preclude foundation-model pre-training as a
consumer-hardware activity. A single RX 7800 XT cannot meaningfully
pre-train a 1B foundation model; even a high-end consumer setup
(4× RTX 4090, ~96 GB total VRAM) is multiple orders of magnitude
short of the compute required.

### 8.3 The deeper barrier: the corpus does not exist

Even if compute were free, foundation-model pre-training requires a
training corpus of trillions of tokens of *natural* code in the
target language. For Python, that corpus exists: GitHub, Stack
Overflow, package indexes, language-specific data dumps. The
publicly-available code corpus weighted by language is dominated by
JavaScript, Python, TypeScript, Java, C, C++, Go, Rust — all
established languages with millions of repositories.

For Sigil, the corpus is what we generated: 2,323 examples,
synthesized via Sonnet, validated by the Sigil interpreter. That is
six orders of magnitude short of the trillion-token scale a
foundation model would require. Even if we generated examples
continuously at the rate observed (~96% validity, ~10 examples per
minute via sequential Sonnet generation), reaching 10⁹ examples
would take ~190 years of wall time, and the resulting corpus would
be drawn from a single underlying generator (Sonnet) — degenerate
in the diversity-of-style sense that pre-training requires.

The "AI-native language with foundation-model-scale pretraining" path
is therefore *theoretically interesting but practically blocked* by
two compounding factors: (a) consumer hardware cannot do the
compute, and (b) the corpus does not exist and cannot be synthesized
at the relevant scale.

### 8.4 Implication for the thesis

This means the AI-native-syntax claim (C in §7.3) cannot be saved
by "training a model from scratch." A novel syntactic surface
*requires* a corpus the world has not produced and a compute budget
consumer hardware does not approach. The viable path for any AI-
targeted language is therefore to design *within* an existing
language's pre-training distribution — i.e., to be a subset (or
constrained dialect) of an already-pretrained-on language.

This is the empirical case for the Python-subset / restricted-Python
direction. It is independent of any specific properties of Python as
a language; it follows from the asymmetry between (i) the cost of
adapting a pretrained model to a new surface (which Sigil paid: 3
months, ~$1-2 in electricity, and 19 tasks of remaining gap on a
30-task multi-step benchmark) and (ii) the cost of pretraining from
scratch on a new surface (which neither this project nor any
consumer-hardware project can pay).

---

## 9. Discussion: What Was Proven, What Was Not, What Remains Valid

### 9.1 What was proven

1. **Single-step tooling delegation to a fine-tuned local 7B-class
   ensemble works at cloud parity.** Stream C 29/30 vs Sonnet 29-30/30,
   ≈6× lower per-task cost, complementary failures (combined cascade
   30/30 at <1% cloud cost). This is the project's durable
   contribution. (§5.1, `papers/STREAM_C_RESULT.md`.)

2. **Multi-step compositional ceiling on local 7B-22B is structural
   and not closeable by language design at this scale.** NH6 + NH10
   + NH10b establish that the 19-task gap to cloud on the multi-step
   suite is ≈26% language-proximity-driven and ≈74% scale-bound,
   and that the scale share is non-monotonic in the 7B-22B band.
   (§5.3-5.4.)

3. **Orchestrator-executor capability matching is a first-class
   design variable.** A stronger orchestrator (Opus) regressed
   results when the executor was unchanged. (§5.5, NH16.) This is
   the LLM analogue of the teacher-student gap in distillation.

4. **The methodology — validator-in-loop, principle-based small-model
   judging, cross-base ensembles, sequential corpus generation,
   meeting-the-model-halfway absorption — generalizes to any future
   language target.** It was developed and validated empirically on
   Sigil and survives any language-design pivot. (`papers/MEETING_HALFWAY.md`,
   `papers/HYPOTHESES.md`.)

5. **Pre-training proximity is a real, cheap, and accessible
   capability axis.** ≈+5/30 tasks at fixed 7B size from switching
   the language target from Sigil to Python (NH10).

### 9.2 What was not proven (and where the data was silent or
adverse)

1. **The "AI-optimized novel syntactic surface improves AI-tooling
   accuracy enough to justify its bring-up cost" claim.** The
   accuracy gain we measured (~+5/30 tasks at fixed model size, in
   the *opposite* direction: Python beats Sigil) is small in
   absolute terms and runs against the original direction of the
   claim. The cost (3 months, 7 retrains, 2,300-entry corpus,
   meet-halfway absorption work) was substantial. The claim is not
   refuted in a Popperian sense — the project simply does not
   produce evidence supporting it.

2. **Scale alone closes the cloud gap on multi-step composition.**
   NH10b directly tested this in the deployable consumer-GPU band
   and the result was zero gain (12/30 → 12/30). We did not test
   above 22B; literature suggests 70B+ may close more of the gap
   but the unit economics of running 70B+ locally are not the
   project's target.

3. **The mammouth U09 safety thesis (effect typing + capability-
   restricted IO).** Not built; cannot be evaluated on its own
   terms. We argue in §9.3 that this is where future work should
   concentrate.

### 9.3 What remains valid for future research

The following statements are still on the table after the close-out:

1. **Capability-typed effects on a restricted-Python host are a
   real, valuable, unbuilt contribution.** Bazel/Starlark and
   RestrictedPython prove that the embedded-Python-subset pattern
   works in production at scale. None of them adds the static
   effect-annotation + capability-whitelist layer the mammouth U09
   sketch described. Building that layer on a Starlark host produces
   a system where:
   - The model never touches the OS directly.
   - Every effecting builtin is gated by a typed capability token
     the embedder grants per-task.
   - Effects are declared in the plan before code runs and verified
     against granted capabilities at parse time.
   - Destructive operations (delete, drop table, force-push) require
     either pre-authorized scoped capabilities or synchronous human
     confirmation.
   - Every action is audit-logged with structured provenance.

   The headline product claim under this design — *"agents cannot
   delete production databases by construction"* — is concrete,
   demoable, and addresses a real problem organizations feel today.
   This is qualitatively different from "AI-native language": it is
   *agent-safe language*, where the value claim is safety, not token
   efficiency.

2. **Capability-aware orchestrator-executor calibration as a
   research problem.** NH16 demonstrated the regression mode but
   not the cure. Open questions: should the orchestrator's system
   prompt include the executor's capability profile? Should the
   plan structure be typed (input/output schemas per step) rather
   than free-text? Should a small local orchestrator be fine-tuned
   *specifically* for plan-shape matching the executor's competence,
   rather than for general reasoning? Each of these is a tractable
   experiment.

3. **The "meeting halfway" methodology generalizes beyond Sigil.**
   Any future language with a fine-tuned model target will encounter
   the same pre-training reflexes (Python idioms creeping into the
   target, alternate-language brackets, etc.). The discoverable
   trigger pattern (model produces a non-target idiom *consistently*
   under composition pressure → absorb at the parser/grammar level)
   transfers verbatim. (`papers/MEETING_HALFWAY.md`.)

4. **Pre-training-language-proximity as a measurable axis.** NH10
   gave a single data point: ≈+5 tasks at fixed 7B from Sigil to
   Python on a 30-task suite. This deserves systematic study across
   more target languages, more model sizes, and more task shapes.
   The axis is real; the calibration is not.

5. **The privacy/confidentiality argument
   (`papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`) is independent of
   any of the above.** Local execution of agent-generated tooling
   code closes the third-party-data-flow boundary unconditionally.
   This argument did not depend on Sigil's accuracy claims and
   continues to hold after Sigil closes.

### 9.4 What the data is silent on

A few questions the project did not resolve and which a follow-on
study could address:

- **Larger local executors (70B+)** on the same multi-step harness.
  We measured 7B and 22B; the gap is non-monotonic in that band but
  literature suggests 70B+ closes more of the cloud gap. Unit
  economics for 70B local are unfavorable for consumer deployment
  but the data point is missing.
- **N-of-K sampling at the per-step executor level** (NH7). Generate
  K=4-8 candidates per step at temp>0, pick the one passing
  deterministic structural checks. We did not run this; it could
  lift any of the local executors by a few tasks.
- **Domain-specific corpora.** The 30-task multi-step suite is
  synthetic; bash-history-derived task suites would more faithfully
  represent deployment. We did not refresh the suite this way.

---

## 10. Conclusion and Future Work

The Sigil project began as a bet on three claims bundled together —
AI-optimized surface, non-ambiguous representation, deterministic
execution — with effect-typed safety as a fourth claim sketched but
unbuilt. After ~3 months of empirical work on consumer hardware, the
data forces us to unbundle those claims:

- The single-step tooling-delegation deployment story is **validated**.
  Local Sigil ensemble at Stream C 29/30 vs Sonnet 29-30/30, ≈6×
  cheaper, complementary failures, deployment-ready.
- The multi-step compositional thesis is **refuted** for the
  consumer-hardware deployment band. The orchestration-ceiling
  diagnostic (NH6) isolates the gap to per-step executor capability;
  the language-vs-scale decomposition (NH10/NH10b) shows the gap is
  ≈26% language-proximity and ≈74% scale, with the scale share
  non-monotonic and not bridgeable in the 7B-22B band.
- The "AI-optimized novel syntactic surface" sub-claim is **invalid
  at consumer scale** on cost grounds: a Python-subset alternative
  inherits the language-proximity benefit (≈+5/30 at 7B) without
  paying the bring-up tax, and pre-training a foundation model from
  scratch on a novel surface is precluded by both the absent corpus
  and the unaffordable compute (§8).
- The canonical-representation sub-claim is **valid but
  language-independent**: achievable on a restricted-Python host.
- The effect-typed safety sub-claim is **the unbuilt valuable piece**
  and is the right direction for follow-on work, on a Python-subset
  host.

The empirical methodology Sigil developed is the project's most
durable contribution. It transfers without modification to any
future language-meets-pretrained-model design work.

The strongest unbuilt thesis is the safety story: agent-safe local
tooling with capability-typed effects, runtime verifier, declarative
authorization policies, and audit-logged execution, designed to make
the failure mode "agent deletes production database" structurally
impossible. We argue this is qualitatively a stronger product
positioning than "AI-native language": the value claim is sharp,
demoable in five minutes, and addresses a real and felt problem in
deployed agentic systems today. It is the natural successor project
and inherits all of Sigil's methodology with none of its language-
specific debt.

---

## Supporting Documents

This paper is a synthesis. The underlying record is in this repository:

- **`papers/SIGIL_RESULT.md`** — project-team retrospective with
  TL;DR; reader-cold pickup version of this paper's argument.
- **`papers/JOURNEY.md`** — chronological narrative across Phase 0
  through Phase 28 with primary-source attribution.
- **`papers/HYPOTHESES.md`** — per-hypothesis empirical record
  (H1-H9, NH1-NH16) with verdicts, evidence, and result-file
  citations.
- **`papers/MEETING_HALFWAY.md`** — operational design philosophy
  that emerged from Phase 14-19; the meeting-the-model-halfway
  methodology.
- **`papers/MODEL_VERSIONS.md`** — catalog of every fine-tune
  attempted and the lesson each taught.
- **`papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md`** — confidentiality-
  risk analysis (independent of the language-design subclaim).
- **`papers/STREAM_C_RESULT.md`** — consolidated single-step
  benchmark report with per-task pass/fail tables, energy and cost
  measurements, failure analysis, reproduction commands.
- **`benchmark/RESEARCH_PLAN.md`** — original research plan v2.1
  (one day before close-out), preserved for archaeological context.
- **Result JSONs** in `tools/agent_harness/abc_*_30task.json` —
  every numbered result table in this paper traces to one of these
  files; all reproducible from `tools/agent_harness/agent_ab_harness.py`.

---

*Sigil project closed 2026-05-04. This paper is the synthesis. The
single-step delegation deployment story is the durable contribution;
the safety thesis is the unbuilt direction for follow-on work.*
