# Research Plan: Sigil as a Local LLM-Native DSL for Confidential Tooling

**Status:** draft v1, 2026-04-30
**Scope:** ~3 weeks of focused work, six interconnected work streams.
**Output:** a single coherent paper-style report plus replicable
artifacts (corpus, model adapters, benchmarks, deployment guides).

## 1. Abstract

**Central question.** *Can an AI-optimised programming language —
designed for minimal-token output, polymorphic builtins, and a flat
S-expression grammar — make small (<10B) local-hostable LLMs useful
enough as agentic-AI tooling backends to (a) replace cloud-LLM calls
on a meaningful share of host-tooling work, while (b) reducing the
data-leakage exposure that cloud calls necessarily carry?*

The motivation is asymmetric. The popular path for AI agents today
is: cloud LLM writes Python or Bash scripts that are then executed
locally to do file traversal, log filtering, text transformation,
output formatting, and the rest of the small-tooling work an agent
needs. That path leaks filesystem layouts, code patterns, and
operational metadata to a third party on every call. Local LLMs
exist that can write Python, but at the 7B-and-under scale they
under-perform cloud frontier models by 30-50 percentage points on
this exact shape of task — the gap that drives the cloud habit in
the first place.

This research asks whether designing the *target language* for the
local model — rather than asking the local model to imitate Python
or Bash — closes enough of that gap to make local-only agentic
tooling a defensible default for confidentiality-sensitive
workflows.

**Prior work in this repo.** A series of escalating experiments,
documented in `RAG.md` and the earlier `project_benchmark_status.md`
memory, has produced a Sigil training corpus of 1884 validated
examples (origin: bootstrapped from ~300 Opus-generated programs,
extended via a `corpus_extender.py` pipeline that uses local ollama
+ RAG with cloud-LLM fallback for hard residuals, validated
end-to-end through the Sigil interpreter), a fine-tuning recipe that
runs on consumer AMD hardware (RX 7800 XT, 16 GB), and a 100-task
benchmark on which a fine-tuned Qwen2.5-Coder-7B + RAG scores 74-79%
1-shot vs un-tuned 32B + RAG at 71% and Sonnet at ~95% (partial).
A separate experiment shows the *same* fine-tuned 7B writes Sigil
correctly on 78% of these tasks vs 10% for Python on the *same* 7B
— meaning the LoRA effectively shifts the model's "default
language."

**This program** addresses the central question through six
interconnected work streams:

(a) Expand the corpus and re-train to push fine-tuned 7B above 80%
1-shot and 90% multi-shot, closing the residual gap to frontier
cloud accuracy.

(b) Address the two largest residual failure classes (off-by-one
errors and unmatched parens) in a way that respects Sigil's
philosophy — additive language changes only, no semantics shift.

(c) Run a deployment-study comparison on real host-tooling tasks
(file walks, log filters, text transforms drawn from actual shell
history) across three configurations: fine-tuned local 7B writing
Sigil, un-tuned local 7B writing Python, and Claude Opus writing
Python.

(d) Specify the agent-workflow integration: how a Claude Code or
similar runtime routes tooling tasks to the local backend, validates
outputs via the Sigil interpreter, and falls back gracefully when
the local model fails.

(e) Write a sourced confidentiality analysis of cloud LLM use for
tooling tasks specifically — threat model, regulatory landscape,
documented incidents — to make the leakage-reduction claim
defensible rather than rhetorical.

(f) Document the full research path, including dead ends (failed
together.ai fine-tunes, retrieval mis-tuning, the
`build_corpus.py` description-discard bug, RDNA3 numerics
gotchas), so the conclusions are reproducible.

**Falsifiable headline claim.** A fine-tuned 7B Sigil-writing model
running locally on a 16 GB consumer GPU produces correct host-tooling
programs more often than a same-class local model writing Python,
at a small multiple of cloud LLM accuracy on the same tasks, while
keeping all task-relevant data — paths, code, env, intent — inside
the local process boundary. We will report whether this claim holds
under controlled measurement, including all four falsification
conditions in §8 even if they undermine the conclusion.

## 2. Background and current results (synopsis)

This section will cite specific numbers from the existing record.

| Configuration | A (no RAG) | B (RAG) | + retry |
|---|---:|---:|---:|
| Un-tuned Qwen2.5-Coder-3B | 10% | 29% | — |
| Un-tuned Qwen2.5-Coder-7B | 15% | 48% | — |
| Un-tuned Qwen2.5-Coder-32B (full upgrades) | 40% | 71% | — |
| Fine-tuned Qwen-Sigil-3B (LoRA r=32) | 43% | 48% | — |
| **Fine-tuned Qwen-Sigil-7B (QLoRA r=16)** | **56%** | **74%** | **79%** |
| Sonnet (partial 23/100) | 91% | 96% | — |

Two prior cloud fine-tunes (sigil-v3/v4 on Qwen3-Coder-30B-A3B,
sigil-v5 on Qwen2.5-7B) and two failed cloud paths (sigil-v6 on
Qwen3-Coder-30B with attention-only LoRA → 0/8; sigil-v7 blocked on
together.ai credits) preceded the local route. The full chronology is
in `project_benchmark_status.md` memory.

The 26 residual failures of the 7B Sigil fine-tune split: 15
wrong_output (logic), 3 parse error (almost all unmatched parens),
3 type error, 3 runtime, 2 empty output. Of these, 5 were
shot-2 recoverable; the remaining 21 are predominantly off-by-one
in scans and deep-nested parens.

A separate experiment shows the same fine-tuned model writes Sigil
(31/40 = 78%) at 7.8× the rate it writes Python (4/40 = 10%) on the
*same* tasks — a +28 pp Sigil gain at the cost of a −40 pp Python
collapse versus its un-tuned base (50% Python). This proves the LoRA
genuinely shifted the model's "default language." It also opens the
deployment question: a Sigil-specialised local 7B is more accurate
than an off-the-shelf 7B writing Python, on tasks both can express.

## 3. Six work streams

### Stream A — Corpus expansion to lift the 7B fine-tune to >80% / ≥90%

**Hypothesis.** The 21 still-failing tasks after 2-shot retry cluster
into a small set of identifiable idioms (off-by-one, deep nesting,
type-correct numeric conversion, multi-pass scanning). Targeted
companion specs that teach those idioms on *different* tasks will
lift first-try accuracy.

**Method.**
1. Cluster the 21 failures by failure-bucket and idiom (off-by-one
   in scan, missing-paren in deep cond, decimal/int rebind, etc.)
2. For each cluster, hand-author 3-6 description-mirror companion
   specs that target the idiom on a structurally distinct task.
   Avoid overfitting: companion descriptions must NOT be near
   duplicates of any iter-task description (cosine < 0.85).
3. Validate Python references; generate Sigil via the upgraded
   `corpus_extender.py` (RAG + Opus fallback); accept only what the
   interpreter validates.
4. Hold out 10 fresh tasks (iters 11-12 worth, hand-curated) as a
   never-seen evaluation set distinct from the existing 100.
5. Re-train Qwen2.5-Coder-7B QLoRA on the expanded corpus. LoRA r=32
   if VRAM permits with shorter max-seq, else r=16.
6. Run the 100-task benchmark + the 10-task held-out set.
7. Measure 1-shot, 2-shot, and 4-shot retry accuracy. Each retry uses
   the previous attempt's stderr/stdout as a hint at temperature
   stepped 0.0 → 0.3 → 0.5 → 0.7.

**Success criteria.**
- 1-shot ≥ 80% on the 100-task suite (currently 74%)
- 4-shot retry ≥ 90% (currently 79% at 2-shot)
- Held-out 10-task set within 5 pp of the 100-task figures (overfit
  detector)

**Failure modes.**
- More corpus does not lift: indicates a model-capacity ceiling.
  Mitigation: try 14B base via aggressive offload / longer training.
- Held-out drops sharply vs 100-task: overfitting to companion specs.
  Mitigation: stricter cosine threshold, fewer specs per cluster.

**Deliverables.**
- `benchmark/finetune_companions_v2.py` (curated specs)
- `benchmark/training_corpus_v2.jsonl` (expanded)
- `benchmark/lora_out_7b_v2/` (re-trained adapter)
- `benchmark/sigil_lora_7b_v2.gguf` + Modelfile
- `benchmark/rag_loop_7b_v2.json` (re-evaluation)
- `benchmark/heldout_v2.json` (never-trained-on tasks)
- A short report `benchmark/STREAM_A_RESULT.md`

### Stream B — Language-aligned fixes for off-by-one and unmatched parens

**Hypothesis.** These two failure classes are not language-design
deficiencies but model-output artifacts. The right fix is *better
diagnostics that the retry loop can act on*, not new semantics.

**Method.**

For unmatched parens:
1. Add a `--lint` mode to the Sigil interpreter that performs a
   syntactic-only pass (no evaluation) and reports:
   - Line and column of the unmatched paren (instead of the current
     `Expected expression but got EOF`)
   - The opening paren's location if the imbalance is "missing close"
   - The unexpected token's location if "extra close"
2. Update the retry-with-hint pipeline to prefer the lint output as
   the hint when stderr is `Parse error`. The model gets a precise
   "you forgot a `)` after line 7" message instead of a generic EOF
   complaint.

For off-by-one:
1. *Not* a language fix. These are reasoning errors. The
   intervention is corpus-side via Stream A.
2. *Add* corpus examples that show common boundary patterns
   explicitly: `(for i 0 (len arr) ...)` vs `(for i 0 (- (len arr) 1)
   ...)`, half-open vs inclusive ranges, last-index access patterns.
3. *Possibly* add a `last-index` or `inclusive-range` builtin that
   gives the model a less-error-prone way to express the most common
   shapes. Decision: only add if the corpus-side fix doesn't close
   the gap by Stream A's evaluation.

**Success criteria.**
- After Stream A, parse_error bucket on the 7B benchmark drops from
  3/26 to 0-1/N (where N is the new failure count)
- Off-by-one wrong_output bucket drops by ≥30%
- Both fixes pass the 1944-file regression sweep cleanly

**Philosophy check.** Both interventions are additive (a new lint
flag, more corpus, optional builtins). They don't remove or change
existing semantics. The user-facing language stays the same.

**Deliverables.**
- Patch to `interpreter/parser.ml` adding `--lint` mode
- Updated `corpus_extender.py` retry pipeline using lint output
- Optional language builtins `last_index`, `inclusive_range` (only if
  Stream A's corpus-side fix is insufficient)
- A short report `benchmark/STREAM_B_RESULT.md`

### Stream C — Deployment proof: 7B-Sigil vs 7B-Python vs Opus-Python on real tasks

**Hypothesis.** On real tooling-script tasks (file walks, log
filters, text transforms, output formatters), a fine-tuned local
Sigil-7B with validate-and-retry produces correct output more often
than off-the-shelf 7B writing Python, and at a fraction of the cost
of Opus writing Python — for the subset of tasks expressible in
Sigil's stdlib.

**Method.**
1. Extract 30-50 real tooling tasks from `~/.bash_history`,
   `~/scripts/`, recent commits adding small utilities. Bucket
   by shape (file-walk, log-filter, text-transform, output-format,
   misc). Per task, capture the original implementation, sample
   input, expected output. The original is the ground truth.
2. Validate that each task is Sigil-expressible (Sigil's stdlib
   covers it). Skip tasks that need libraries Sigil doesn't have.
3. Build `benchmark/eval_real_tooling.py` that runs each task
   through three paths:
   - **A**: Local Sigil-7B v2 + RAG, validate-and-retry up to 3
     attempts (use Stream A's improved retry)
   - **B**: Local Qwen2.5-Coder-7B (un-tuned), Python single-shot
   - **C**: Claude Opus, Python single-shot
4. Measure per task: pass/fail, wall-clock seconds, token counts
   in/out, $ cost (cloud paths via published rates), Wh estimate
   (calibrated wattmeter readings: see Stream C-supplemental below)
5. Aggregate per bucket; compute decision matrix.

**Stream C-supplemental — energy calibration.**
Replace the order-of-magnitude estimates from `PLAN_local_vs_cloud_economics.md`
with actual measurements:
- Wall plug power (USB or Kasa wattmeter) on the local box, idle vs
  during inference
- Estimate cloud Wh from Anthropic's published model size + typical
  data-center PUE 1.2-1.4
- Network energy: ~50 nJ/byte for residential broadband, ~10 nJ/byte
  for data center transit (conservative)

**Success criteria.**
- Local Sigil v2 ≥ un-tuned 7B Python on pass-rate (any margin)
- Local Sigil v2 within 15 pp of Opus Python on pass-rate
- Local Wh/call ≤ 25% of Opus Wh/call (conservative)
- $ cost ratio ≥ 100× in local's favor at workload of 1000 calls/day

**Failure modes.**
- Real tasks expose Sigil stdlib gaps not seen in synthetic benchmark.
  Mitigation: track per-task whether failure is Sigil-capability or
  model-capability.
- Sample size 30-50 too small for statistical claims. Mitigation:
  bootstrap CIs and report explicitly.

**Deliverables.**
- `benchmark/real_tooling_tasks.json` (30-50 curated tasks)
- `benchmark/eval_real_tooling.py`
- `benchmark/eval_real_tooling_results.json`
- A short report `benchmark/STREAM_C_RESULT.md` with the decision
  matrix and bucket-by-bucket recommendation

### Stream D — Agentic workflow integration guide

**Hypothesis.** A local Sigil-tuned 7B can be wired into Claude Code
(or any agent runtime) as a tooling-tool — the agent recognises
"this is a tooling-shape task" and delegates locally instead of
running its own Python generation through the cloud roundtrip.

**Method.** A practical, replicable guide covering:
1. Local model serving recipe (ollama with `qwen-sigil:7b` from this
   work's adapter)
2. Sigil interpreter as a runner — the validation step is
   `./vm.exe code.sigil <args>` and a stdout match
3. A Claude Code subagent definition that:
   - Takes a tooling-task description
   - Calls the local model via ollama HTTP
   - Validates the output via the Sigil interpreter
   - Retries on failure with hint feedback
   - Returns the validated Sigil program OR signals failure for
     parent-agent re-routing
4. A routing heuristic at the parent agent: which task shapes go
   local, which go cloud
5. A small worked example: an agent that, given a directory and a
   transformation goal, produces a Sigil program that does the work

**Success criteria.**
- The subagent can be installed with one command
- A worked example end-to-end works in <30 seconds
- The routing rules produce stable decisions across 100 simulated
  task descriptions

**Deliverables.**
- `agent_workflow/sigil_subagent.md` (Claude Code subagent definition)
- `agent_workflow/router.py` (parent-agent routing logic)
- `agent_workflow/example_walkthrough.md` (worked end-to-end example)

### Stream E — Confidentiality analysis: cloud LLM use for tooling

**Position in the program.** This stream is co-equal with Streams A-D,
not an aside. The central question of this research has two limbs —
"can we make small local LLMs useful enough" and "can we reduce data
leakage" — and Stream E quantifies the second limb. Without a
defensible analysis of *what* leaks, *to whom*, *for how long*, and
*under what regulatory exposure*, the second limb is unsupported and
the program collapses to a cost-of-inference comparison.

**Hypothesis.** Cloud LLM use for host-tooling-script generation —
the specific workflow this program addresses — externalises a
quantifiable set of artefacts (filesystem paths, code patterns,
environment variables, sample data, error messages, intent
expressed in natural language) on every call. For workflows
operating under GDPR, HIPAA, SOX, CCPA, EU AI Act, CMMC, or any
employer's IP protection policy, this externalisation is a
defensible reason to prefer a local backend even at meaningful
accuracy cost. The local Sigil-tuned 7B closes the network channel
entirely; the threat model collapses to the same local-process
boundary the user already trusts to run shell commands.

This needs to be a careful, sourced argument, not a polemic. We
will treat it as a threat-model + compliance-mapping exercise.

**Method.**
1. **Threat model.** Enumerate what is sent to cloud LLMs during
   typical tooling-script generation:
   - Filesystem paths (often imply directory structure and naming
     conventions)
   - Code patterns (imply architecture and IP)
   - Environment variable names and sample values
   - Sample data files used as inputs
   - Error messages and stack traces (imply infrastructure)
   - Task descriptions in natural language (imply intent)
2. **Provider-side handling**, with citations:
   - Anthropic, OpenAI, Google: published policies on training data,
     log retention, encryption-at-rest, encryption-in-transit
   - Caveats: business associate agreements (HIPAA), DPAs (GDPR),
     SCCs for cross-border transfers
   - What "we don't train on your inputs" actually says (not what it
     implies)
3. **Regulatory landscape.**
   - GDPR: cross-border transfer, automated decision-making, data
     minimisation
   - CCPA / CPRA
   - EU AI Act risk categories for tooling
   - Sector-specific: HIPAA (healthcare), SOX (financial), CMMC
     (defence)
   - Open Question: does "code that mentions health data" count as
     protected? (Generally yes for processing intent)
4. **Documented incidents.**
   - Samsung Bixby leaked source code via ChatGPT (2023)
   - Various law firm AUP violations
   - GitHub Copilot training-data lawsuits
5. **How local fixes the problem.** Local inference closes the
   network channel entirely. The threat model collapses to local
   process boundary, which is the same boundary an `eval` of a
   shell script already crosses.

**Success criteria.**
- Threat model and citations are complete enough to hand to a
  privacy/legal reviewer
- The "local fixes this" claim is bounded properly (some local
  approaches still call cloud APIs internally)

**Deliverables.**
- `papers/CONFIDENTIALITY_AND_LOCAL_LLMS.md` — sourced, structured
  argument

### Stream F — Iteration narrative: how we got here

**Hypothesis.** The conclusions of this work are only as credible as
the visibility of the path that produced them. Hidden dead-ends
matter; visible dead-ends build credibility.

**Method.** A narrative document that walks through:
1. The starting point: a Sigil corpus of ~300 programs bootstrapped
   from Claude Opus generation (not hand-written — the human author
   designed the language and a test harness, but the corpus itself
   was LLM-produced and validated against the Sigil interpreter).
   No RAG, no fine-tune. Benchmark vs Python: ~0.96× tokens
   (slight win) at the corpus generation stage.
2. Together.ai fine-tunes (sigil-v3 / v4 / v5): what worked, what
   didn't. Key data: v5 on Qwen2.5-7B-Instruct with `all-linear`
   LoRA was the only one that produced good Sigil-writing model.
3. The corpus-extender pipeline development: ollama + RAG + Opus
   fallback. Why we needed it (manual extension didn't scale).
4. The RAG layer: why we built it, the 6 retrieval-tuning rounds,
   the `build_corpus.py` description-discard bug discovery.
5. The 10-iteration loop: methodology, metric, what each iteration
   taught us about language gaps.
6. The 14 language fixes: chronological list, motivation per fix,
   regression cost.
7. The local-LoRA pivot: why we stopped trying together.ai, what we
   gained.
8. The 7B QLoRA: the bf16/fp16 numerics issues on RDNA3, the
   HSA_OVERRIDE workaround, the 4-bit compute-dtype bug.
9. The final 9-config benchmark: what each row says.
10. Open questions and the next steps.

**Success criteria.**
- A reader unfamiliar with the project can follow the narrative
  end-to-end and reproduce any single decision
- The dead-ends are visible (not just the wins)
- The decision points are explained, not just listed

**Deliverables.**
- `papers/JOURNEY.md` — full narrative
- A reproducibility appendix: exact commands for each major step

## 4. Sequencing and dependencies

```
Stream A (corpus + retrain) ──────┐
                                  ├─→ Stream C (deployment proof)
Stream B (lint + diagnostics) ────┤
                                  └─→ Stream D (agent workflow)

Stream E (confidentiality) ─── independent, runs in parallel
Stream F (narrative) ─── depends on A, B, C, D, E completion
```

A and B can run in parallel; both feed C and D. E is independent.
F is the synthesis and runs last.

## 5. Schedule

Conservative two-to-three-week plan:

| Week | Streams active | Focus |
|---|---|---|
| 1 | A, B, E | Corpus expansion + linter + threat model |
| 2 | A (re-train), B (validate), C, D | 7B v2 + deployment study |
| 3 | C, D, F | Agent workflow + final synthesis |

Compute budget assumptions: 1× RX 7800 XT, ~5 hr/day available for
training/inference. Cloud budget: ~$50-100 for the deployment study
(Opus calls only).

## 6. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stream A hits 7B capacity ceiling at <80% | medium | high | Try 14B with aggressive offload; or accept ceiling and adjust claim |
| Real tooling tasks reveal Sigil stdlib gaps | medium | medium | Track per-task and add stdlib expansions case-by-case |
| Lint mode introduces parser regressions | low | medium | Full 1944-file regression sweep gates the change |
| Energy calibration too noisy for claims | medium | low | Report ranges, not point estimates |
| Confidentiality stream slips into polemic | medium | medium | Source every claim; use established threat-model frameworks |

## 7. Reproducibility commitments

For every result quoted in the final paper:
- Exact command line that produced it
- Hash of the corpus version used
- Adapter file checksum
- Timestamp and hardware fingerprint
- Raw JSON in the repo

This applies to numbers as small as a single B-pass count.

## 8. Falsification criteria

A research-grade plan must specify how it could be wrong.

The deployment-economics claim ("local Sigil-7B is competitive with
or better than cloud LLMs for tooling tasks") is falsifiable as
follows:

- If Stream A's expanded corpus + retraining does not lift first-try
  accuracy beyond 75%, the local-only deployment story weakens
- If Stream C's real tooling tasks produce >50% Sigil stdlib gaps,
  the deployment story collapses (need Python anyway)
- If Stream C's $ ratio at realistic volumes is <10× in local's
  favor, the cost case isn't strong enough to override convenience
- If energy measurements show local Wh/call is within 50% of cloud
  Wh/call (i.e. cloud isn't actually that wasteful), the
  sustainability axis disappears

We will report all four checks honestly even if they fail.

## 9. What this plan deliberately does NOT claim

- That local Sigil-7B is a general-purpose Python replacement (it is
  not — only for tooling shapes)
- That this approach scales to every workload (it doesn't — needs
  larger models for hard reasoning)
- That cloud LLMs are universally bad (they are not — they win on
  many axes for many problems)
- That the energy comparison is precise to within 10% (the estimates
  have wide error bars even with calibration)

## 10. Final artifact

A single readable paper-style document, ~6000-9000 words, citing every
artifact in this repo, with the structure:

1. Abstract
2. Background and prior work
3. Methodology (drawing on the streams above)
4. Results (the corpus-expansion benchmark, deployment study, energy
   measurements)
5. Discussion (when local wins, when cloud wins, how to decide)
6. Confidentiality argument
7. Reproducibility appendix
8. The narrative (Stream F integrated as Section 9 or appendix)

Plus the supporting code, data, and adapters in the repo.
