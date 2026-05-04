---
title: Sigil Project — Hypotheses Tracked, Falsified, and Open
status: v1
date: 2026-05-03
---

# Hypotheses

This document tracks every load-bearing hypothesis the project has tested,
what the evidence said, and what we have not yet questioned. It is a
strategic companion to [`JOURNEY.md`](./JOURNEY.md), which records what
happened phase-by-phase. Where JOURNEY answers *what we did*, this doc
answers *what we believed at each step and what the data said back*.

Maintained alongside JOURNEY. New phases that overturn or refine a
hypothesis should update the verdict here.

---

## Part I — Hypotheses we tested

### H1. Token-efficient AI-native language

**Claim.** A Lisp-shaped, type-directed-dispatch language designed for
minimum-token AI output is more efficient than mainstream languages on
agentic tooling work, primarily by avoiding cloud LLM token spend.

**Evidence.** Phase 1 (motivation), Phase 2 (Sonnet writes Sigil),
Phase 9 (Sigil vs Python on the same model).

**Verdict — partial.** The token-efficiency claim is about *input*
tokens, not output. Sigil grammar prompt costs ~1,600 tokens per call
(cached after first hit), Python prompt ~40. Output tokens are
2-10× *higher* in Sigil than Python (S-expression syntax). The win is
in cached-input savings + retry overhead avoidance, not raw output. The
deployment story this validates is "Sigil is a delegation target, not a
general programming language" — see Phase 21 framing.

### H2. Fine-tuning a small local model on Sigil reaches frontier accuracy on tooling tasks

**Claim.** A 7B QLoRA on a curated Sigil corpus matches Sonnet-class
single-step tooling accuracy.

**Evidence.** Phase 7 (3B proof of concept), Phase 8 (7B QLoRA hard
win), Phase 11 (v2/v3/v3.1 iterations), Phase 19 (Stream C 29/30 =
Sonnet 29/30 with complementary failures).

**Verdict — true, single-step only.** Stream C 29/30 vs Sonnet 29/30 is
the load-bearing data point. Local matches cloud at zero marginal API
cost on consumer hardware. The qualifier matters: this is single-step
tooling, not multi-step composition (see H6, H9).

### H3. Ensemble (Qwen-7B + Phi-4-14B) with failure-shape diversity outperforms a single model

**Claim.** Adding Phi-Sigil as a fallback to Qwen-Sigil rescues tasks
the primary fails, because Phi's failure modes are different.

**Evidence.** Phase 16 (introduction), Phase 20 (29/30 ensemble vs
~28/30 qwen solo with RAG).

**Verdict — true but small effect, with deployment cost.** Phi-v2
rescues 1-2 tasks per Stream C run. Real but small. **The deployment
cost was substantial**: Phase 20's Q4_K_M drift on Phi-4's fused
projections regressed phi-v2 solo from 19/30 to 14/30. Ensemble outcome
unaffected (the rescued task was still rescued), but solo figures were
worse than they should have been. Fallback-model choice is itself a
hypothesis we never properly tested — see [O2](#o2-fallback-model-choice).

### H4. RAG retrieval + corpus growth scales accuracy linearly with corpus size

**Claim.** More verified seeds in the training corpus mean better
retrieval, mean higher accuracy.

**Evidence.** Phases 4-6 (corpus extender, RAG infra), Phase 19 (70
regex seeds → +12 Stream C tasks), Phase 24 (Tier 2.5 +14 seeds → -2
agent tasks).

**Verdict — true up to a threshold, non-monotonic past it.** Phase 19's
+12 jump was the proof; Phase 24's regression was the disproof. Adding
seeds shifts top-K retrieval for *every* task — sometimes helping,
sometimes hurting. On a small held-out suite (8 tasks), the
shift dominates the signal once you're past the obvious wins. See also
[NH5](#nh5-suite-size).

### H5. Validator-in-loop (write → run → diff → retry) closes the gap to cloud

**Claim.** Iterative retry with a structured-diff hint converts model
near-misses into successes.

**Evidence.** Phase 11 (generic structural diff), Phase 18 (surgical
hints), Phase 22 (interpreter loudness + hint pattern matching).

**Verdict — true, +1 to +2 tasks. Surgical > generic. Ceiling-bound.**
The hint mechanism is real but its leverage is task-shape-specific.
Generic diffs help less than shape-specific ("you over-matched the
regex"; "your for-loop iterator was mutated"). Once the dominant silent
failure modes are covered, additional hints have diminishing returns.

### H6. Stream C single-step success translates to multi-step agentic delegation

**Claim.** If the local ensemble does single-step tooling at 93%+, it
will also handle multi-step composition delegated by a cloud
orchestrator.

**Evidence.** Phase 18.1 (A/B harness debut: 6/8 cloud vs 1/8 hybrid),
Phase 21 (Stream C wins don't propagate; 1/8 unchanged with v6+phi-v2).

**Verdict — false.** Multi-step composition is a *different* problem
from single-step tooling. The bottleneck on multi-step is the model's
ability to hold spec + input shape + output shape + intermediate
constraints in working memory across one delegation call. v7 didn't
have more working memory than v4; phi-v2 didn't have more than phi-v1.
The architecture of the call is the bottleneck, not the model. This
is the strongest negative result of the project so far.

### H7. "Meeting the model halfway" at the language layer absorbs failure modes more efficiently than prompts or training

**Claim.** When a failure mode is dominant AND tied to model
pre-training distribution, fix at the language/runtime layer.

**Evidence.** Phase 18.6 (PCRE swap, ~60 lines absorbing all of
Perl-style regex), Phase 19 (lexer escape preservation, for-iterator
guard), Phase 25 (smart-argv, ~10 lines absorbing the
`for arg in sys.argv` instinct).

**Verdict — true and the highest-leverage lever in the project.** Each
meet-halfway change took a one-time engineering cost (10-60 lines) and
absorbed an entire failure-mode class. Prompts/seeds need to be
maintained against new corpus rounds; language changes don't.
Documented in [`MEETING_HALFWAY.md`](./MEETING_HALFWAY.md) §4.

### H8. A chained sub-agent (single-step pipeline) closes the multi-step gap

**Claim.** Replacing single-program multi-step delegation with a
pipeline of single-step Sigil calls (each Stream-C-shaped) lifts
multi-step accuracy.

**Evidence.** Phase 23 (Path C added; 1/8 → 3/8 at 45% lower cost than
single-program delegation).

**Verdict — partially true.** +2 tasks (1/8 → 3/8) is the largest
systematic lift on the multi-step harness across all phases. Real and
reproducible. But ceiling-bound at 3/8 ± 1 noise band; the residual
failures are *intermediate-step shape mismatches* (Sonnet's plan
assumes step 2 receives shape X; step 1 actually produced Y). Neither
RAG nor weights address this; orchestration validation does.

### H9. Pure retraining on a richer corpus moves the agent harness floor

**Claim.** v7 trained on the augmented 2323-entry corpus + smart-argv
runtime will lift Path C from 2-3/8 toward Sonnet's 5-6/8 noise band.

**Evidence.** Phase 26 (v7 retrain + Stream C diagnostic + A/B/C
retest).

**Verdict — false.** Stream C v7 = 28/30 (regressed -1 from v6 due to
sampling variance on `awk_filter_field_gt`). Agent A/B/C v7 = B 2/8,
C 2/8 — same band as every prior pure-RAG/training iteration. The
remaining failures are not addressable by training. This was the
diagnostic outcome the v7 retest was set up to produce; the cost was
worth it because it converted "another retrain might help" plausible
deniability into a confirmed plateau.

---

## Part II — Variables we held constant without questioning

These are the meta-decisions that lived underneath every hypothesis
above. We never tested whether different defaults would have produced
better outcomes.

### O1. Base-model choice

We picked **Qwen2.5-Coder-7B-Instruct** at Phase 7 for defensible
reasons (split-projection architecture for clean Q4 quantization, code
pre-training, fits in 16GB VRAM at 4-bit) and never benchmarked
alternatives. The downstream effect: every retrain (v3 through v7) was
optimizing within a base we never validated was best.

Alternatives never tested: **DeepSeek-Coder-7B**,
**DeepSeek-Coder-V2-Lite (MoE)**, **Codestral-7B**,
**Mistral-Small-22B**. Each has a different inductive bias for
code-shaped pattern reach.

The signal we missed: the diminishing-returns curve across v3→v7
deltas (Phase 11, 19, 26) was a sign we were at the base's ceiling, not
a sign more epochs would help.

### O2. Fallback-model choice

Phi-4-14B was added in Phase 16 as the ensemble fallback specifically
because it was failure-shape-diverse from Qwen. Phase 20 surfaced that
**Phi-4's fused `qkv_proj` / `gate_up_proj` quantize poorly under
Q4_K_M** — phi-v2 solo regressed 19/30 → 14/30 vs the merged
checkpoint. We knew this and didn't switch.

Alternatives never tested: **Codestral-22B** (split-projection,
code-specialized, would survive Q4_K_M cleanly), **DeepSeek-Coder-V2
16B** (MoE, genuine architectural diversity), **Mistral-Small-22B**
(broader reasoning). Each plausibly recovers the 5-task quantization
loss AND provides better ensemble diversity than phi-v2 currently does.

### O3. Specialized small-model judges

We have **qwen-sigil:3b** registered (never trained beyond a Phase 7
proof-of-concept). The 3B has been idle while we iterated 7B and 14B.

The role we never assigned to it: **classifier / step-validator**. Path
C residual failures are intermediate-shape mismatches. A small
"does this output match the expected shape?" model in the chained loop
is exactly the validate-each-step capability Phase 26 named as next-move
#2 (which we then planned to do via Sonnet — expensive).

The 3B model is local, free at inference, and has training data
already (every Phase 23-26 step result is labeled).

### O4. Generation strategy (sequential 1-shot retry)

Every model call generates ONE program, runs it, retries on fail. We
never tried **beam search / N-best** (generate K candidates per attempt,
run all, take the matching one). Phase 11+ retries used incremented
temperature; never used it as a population.

### O5. Self-distillation / rejection-sampling

Our corpus is hand-curated examples. The model's *own* successful
generations from prior runs (we have hundreds of these in the
benchmark JSON files) were never used as training data. Standard
rejection-sampling fine-tune (keep model outputs where stdout matched
expected, retrain on those) reinforces correct reach patterns and
dampens wrong ones. We did this once manually for Phase 19's regex
seeds (12 hand seeds were extracted from observed wins) but not
systematically.

### O6. Single test case in prompt

Stream C tasks have multiple test cases internally (see
`benchmark/real_tooling_tasks.json`). The harness only ever shows the
model ONE input/expected pair. Showing 3-5 would constrain the search
substantially on harder tasks.

### O7. Multi-stage generation (decompose then synthesize)

We never tried "3B writes a plan in pseudo-Sigil; 7B fleshes out
syntax" decomposition. The chained sub-agent (Phase 23) decomposes at
the *task* level (Sonnet plans 1-3 Sigil calls); we never decomposed at
the *program* level (sketch + flesh).

---

## Part III — New hypotheses to test

Ranked by leverage estimate. Each cites which falsified prior
hypothesis it builds on, and what success looks like.

### NH1. Base-model choice is a load-bearing variable we should benchmark before another retrain

**Builds on:** [O1](#o1-base-model-choice), [H9](#h9-pure-retraining-on-a-richer-corpus-moves-the-agent-harness-floor)

**Hypothesis.** A different 7B base (DeepSeek-Coder, Codestral, or
Mistral-Small) writes Sigil with 5-15 percentage-point higher baseline
accuracy than Qwen2.5-Coder at the *no-fine-tune, RAG-only* level. If
true, every subsequent retrain inherits that advantage.

**Verdict (Phase 27, 2026-05-03) — partially falsified, but the
diagnostic was load-bearing.**

Run on the 30-task Stream C suite, vanilla un-fine-tuned, RAG only:

| Base | Pass | Time | Energy | Unique catches vs qwen | qwen+X 2-way oracle |
|---|---:|---:|---:|:---:|---:|
| **qwen-coder:7b** | **23/30** | 199s | 9.9 Wh | (baseline) | — |
| deepseek-coder:6.7b | 18/30 | 209s | 10.5 Wh | **3** | 26/30 |
| deepseek-coder-v2:16b MoE | 17/30 | 2723s | 136 Wh | 1 | 24/30 |
| codestral:22b | 19/30 | 1101s | 55 Wh | **4** | **27/30** |

4-way oracle = 29/30 — nearly matches v6+phi-v2 fine-tuned at 29/30
*without any Sigil fine-tuning*.

**Two findings, only one of them was the original NH1 question:**

1. **Qwen-coder IS the right primary base.** No alternative beats it
   solo. The v3→v7 retrain trajectory was on the right model. The
   "we never benchmarked this" worry from O1 turns out to have been
   unfounded — the obvious choice was the obvious choice.

2. **Phi-4 was the WRONG fallback** (this is the new finding). The
   diagnostic that NH1 actually surfaced wasn't about the primary; it
   was about the fallback. DeepSeek-Coder-6.7B vanilla picks up 3
   tasks qwen misses, including `shell_argv_count` (the project's
   hardest persistent residual, which survived 7 retrains plus
   smart-argv) and `split_at_blank_lines` (Sonnet's residual on the
   v6 era). At 3.8 GB and ~7s/task it's smaller and faster than
   phi-v2 (9.1 GB, ~15s/task), with split-projection avoiding Phase
   20's Q4_K_M drift. This rewrites NH3.

3. **Codestral-22B has the best failure-shape diversity** (4 unique
   catches including `awk_filter_field_gt`, the task v7 lost vs v6)
   but 5× slower than the 6.7B for +1 oracle task. Optional
   secondary fallback only.

4. **DeepSeek-V2-16B MoE is dominated** on every axis — strictly
   worse than the 6.7B. ROCm has poor MoE kernel support.

**Result files**: `benchmark/stream_c_nh1_{qwen,deepseek,deepseek-v2,codestral}.json`.
Commit: [901760d](https://github.com/mlainez/sigil/commit/901760d).

### NH2. A specialized 3B step-judge will close the chained-pipeline plateau

**Builds on:** [O3](#o3-specialized-small-model-judges), [H8](#h8-a-chained-sub-agent-single-step-pipeline-closes-the-multi-step-gap)

**Hypothesis.** Training qwen-sigil:3b as a yes/no classifier on
`(intermediate_output, expected_shape) → ok/not-ok` pairs catches
intermediate-step shape mismatches in the chained pipeline. Wired into
Path C between steps, it triggers replan-or-retry when step N's output
doesn't match step N+1's input expectation. Lifts Path C from 2-3/8 to
5+/8.

**Test.**

1. Generate training data from Phase 23-26 step results: ~200-300
   labeled (intermediate, expected, ok) tuples. Augment with
   handcrafted shape-mismatch negatives (~50).
2. Fine-tune qwen2.5-coder:3b as a classifier (single token: "yes"/"no"
   after a structured prompt).
3. Wire into `path_c_chained_hybrid` between steps: if judge says "no",
   retry the prior step with a hint OR ask Sonnet to replan.
4. Re-run A/B/C harness.

**Success criterion.** Path C ≥ 4/8 with the judge in place. If 3/8 or
below, the judge isn't firing usefully; revert and try NH3.

**Estimated cost.** 3-4 days. Most expensive piece is curating the
labeled data.

**Risk.** Judge could be too strict (rejects correct intermediates),
which would lower Path C. Mitigation: validate judge accuracy on a
held-out subset before wiring into pipeline.

### NH3. Replace Phi-4 with DeepSeek-Coder-6.7B fine-tuned on the Sigil corpus

**Builds on:** [O2](#o2-fallback-model-choice), [H3](#h3-ensemble-qwen-7b--phi-4-14b-with-failure-shape-diversity-outperforms-a-single-model), [NH1](#nh1-base-model-choice-is-a-load-bearing-variable-we-should-benchmark-before-another-retrain)

**Refined after NH1's diagnostic.** The original NH3 sketch named
Codestral-22B and DeepSeek-Coder-V2-Lite as candidates. NH1 measured
both — DeepSeek-V2 is dominated, Codestral has slightly better
failure diversity (+4 unique catches vs +3) but is 5× slower and 5×
more energy than the 6.7B. **DeepSeek-Coder-6.7B is the practical
winner** — same family of catches with much cleaner deployment.

**Hypothesis.** Fine-tune DeepSeek-Coder-6.7B on the same 2323-entry
Sigil corpus, deploy as `deepseek-sigil:6.7b`. Use as ensemble
fallback in place of phi-sigil-v2:14b. The expected outcome:

1. Stream C ensemble (qwen-sigil-v7 + deepseek-sigil) ≥ 30/30 — the
   3 unique catches DeepSeek-Coder vanilla already provides
   (`shell_argv_count`, `split_at_blank_lines`, `sort_uniq_count_top`)
   should remain after fine-tune AND likely expand.
2. Half the VRAM footprint vs phi-v2 (3.8 GB vs 9.1 GB).
3. Roughly half the per-call latency (~7s vs ~15s).
4. No Q4_K_M drift (split-projection architecture).
5. No llama-runner segfault workaround (no offline merge needed).

**Test.**

1. Train deepseek-sigil:6.7b. Same QLoRA recipe as v7 (r=16, alpha=32,
   lr=2e-5, 3 epochs). Estimated wall: ~3-5h on the 7800 XT (similar
   per-step cost as v7's 7B since DeepSeek-Coder-6.7B has roughly
   matched parameter count).
2. Convert via convert_lora_to_gguf, register with ollama as
   `deepseek-sigil:6.7b`.
3. Sanity-check Stream C solo. Threshold: ≥ 23/30 with RAG (matches
   vanilla deepseek-coder; fine-tune should add, not subtract).
4. Run Stream C ensemble: qwen-sigil-v7 primary + deepseek-sigil
   fallback. Compare to v7+phi-v2's 28/30.
5. Run agent A/B/C harness with new ensemble. Compare to v7+phi-v2's
   B 2/8, C 2/8.

**Success criteria** (any one is a win):
- Stream C ensemble ≥ 30/30
- Stream C ensemble = 29/30 but at materially lower latency / energy
- Agent harness Path C ≥ 4/8

**Estimated cost.** ~6-8 hours total: 3-5h training, 30 min deploy,
30-60 min eval.

**Risk.** DeepSeek-Coder-6.7B's tokenizer differs from Qwen's
(different vocab); the corpus chat template may need a small
adjustment for the chat-format wrapper. Verify training loss
trajectory mirrors v7's before committing the full 3 epochs.

### NH4. System-around-model interventions consistently outperform model-side iterations

**Builds on:** [H7](#h7-meeting-the-model-halfway-at-the-language-layer-absorbs-failure-modes-more-efficiently-than-prompts-or-training), [H8](#h8-a-chained-sub-agent-single-step-pipeline-closes-the-multi-step-gap), [H9](#h9-pure-retraining-on-a-richer-corpus-moves-the-agent-harness-floor)

**Hypothesis (meta).** Across the project's history, every gain >1
task on multi-step has come from changing the system *around* the
model (PCRE swap, for-iterator guard, chained sub-agent, smart-argv).
Pure model-side iterations (retrain, more seeds, prompt tightening)
plateau quickly. The next round of work should default to
*orchestration / runtime / interpreter* changes before reaching for
training.

**Operational rule (not a test).** When the next failure-mode dive
identifies a recurring shape, the first three options to consider are
(in order):

1. Can the *interpreter* absorb the shape? (smart-argv pattern)
2. Can the *runtime* surface a structured signal that retry can act
   on? (for-iterator guard pattern)
3. Can the *orchestration* rearrange where the model is being asked
   to do too much in one shot? (chained sub-agent pattern)

Only if all three are inapplicable should we reach for "more corpus"
or "another retrain". This is a process-level hypothesis; its
falsification would look like another phase where retraining
demonstrably outperforms a system-side fix on the same failure shape.

### NH5. Suite size

**Builds on:** [H4](#h4-rag-retrieval--corpus-growth-scales-accuracy-linearly-with-corpus-size)

**Hypothesis.** The 8-task agent harness is too small to distinguish
signal from noise at 1-3 task differences. Multiple Phase 24-26
experiments showed *which* 2 tasks pass changing while the count
stayed at 2/8. A 30-50 task suite would let us measure ±1 lifts with
confidence.

**Test.** Build a 30-task multi-step suite. Sources:

- ~10 tasks expanded from current 8 with shape variations
- ~15 tasks sampled from the user's `~/.bash_history` (the
  bash-history task suite refresh from Stream C #116 in
  `RESEARCH_PLAN.md`)
- ~5 tasks from real public log/CSV/JSON shapes (nginx, journald,
  package manager output)

**Success criterion.** With 30 tasks, the noise band on Path C should
narrow from ±1 to ±0.5 (because any individual task contributes 3.3pp
instead of 12.5pp to the score). Decisions about NH1-NH4 can then be
made on solid statistical footing.

**Estimated cost.** 1-2 days for task curation (mostly the
bash-history piece).

**Risk.** Bash-history sampling could leak personal data into the
benchmark corpus; redact before committing.

---

## Part IV — Recommended sequence

Given the leverage estimates and dependencies, a sensible order:

1. **NH5 first** (1-2 days). Build the 30-task suite. Every subsequent
   experiment is more measurable on the larger suite. Without it, the
   decisions on NH1-NH4 are noise-dominated.

2. **NH1 in parallel** (1 day, no GPU contention with NH5 curation).
   Tests whether the base-model assumption is load-bearing. Result
   gates NH3.

3. **NH2 next** (3-4 days). Highest-leverage targeted intervention.
   If it lifts Path C to 5+/8 on the new suite, the deployment story
   becomes "local matches cloud at substantially lower cost on
   multi-step tooling delegation." This is the headline outcome the
   project has been pointed at.

4. **NH3 if NH2 doesn't fully close the gap** (2-3 days). Tests
   whether a better fallback model materially improves both Stream C
   solo and ensemble diversity.

5. **NH4 is operational** — applies to all of the above. Default to
   system-side fixes.

Total estimated cost: ~10 days of focused work. Each test produces a
clear yes/no signal on the hypothesis, so the sequence terminates
naturally if any one of them lifts the multi-step floor decisively.

If by NH5 + NH1 + NH2 + NH3 the floor is still 2-3/8, we have
strong evidence that the chained-on-8-task harness is fundamentally
not the right benchmark for the local stack's value claim, and the
project's deployment-ready story should refocus on Stream C-shaped
single-step tooling delegation (where local already matches cloud at
29-30/30) rather than multi-step composition.

---

## Part V — Additional hypotheses (post-NH2 Tier B retrospective)

Added after NH2 Tier B prep + lift estimation (2026-05-04). The strict
lift estimator showed the judge's TAM is only ~4 candidates per 30-task
run (~+0.5 task lift), revealing that **80% of multi-step failures are
not in the wrong-shape-with-content band the judge addresses**:

  - 10/24 are "empty pipelines" (every step's stdout is empty)
  - 10/24 are "final-step shape mismatch" (intermediates fine, final off)
  - 4/24 are "wrong-shape intermediates" (judge's actual TAM)

The rest of this section identifies hypotheses that would address the
*other* 80% of failures, plus structural directions we haven't tested.
**Constraint** (from project thesis): all interventions must be
local-only at production time. Sonnet may be used as a one-shot
*measurement instrument* but not as a per-task validator.

### NH6. The orchestration ceiling is well below 30/30

**Premise.** Path A (Sonnet writes Python) scores 26/30. Path C
(Sonnet decomposes, local Sigil executes) scores 6/30. The 20-point
gap is interpreted as a code-gen problem ("the local model writes bad
Sigil"). It might mostly be an *orchestration* problem: the
decomposition + cross-step plumbing leaks information that no executor
can recover.

**Test.** Have Sonnet decompose as today, but run each step with
Sonnet itself as the executor instead of Sigil. This is a one-shot
diagnostic (Sonnet only used to *measure*, not in production).

**Decision rule.**
  - If this scores ≥24/30: code-gen is the bottleneck; every
    fine-tuning move and judge improvement is justified.
  - If it scores ≤14/30: orchestration is leaking; no amount of
    local-model improvement closes the gap. Priority shifts to
    NH8 (longer pipelines), NH9 (typed contracts), NH11 (persistent
    state).

**Cost.** ~30 minutes for one A/C harness run with a swapped executor.

**Why it's load-bearing.** Resolves a question we've been guessing at
for weeks. Every other hypothesis depends on this answer.

**Result (2026-05-04, CONFIRMED — orchestration is NOT the bottleneck;
the local executor is).** Built `sonnet_execute_step` as a drop-in
alternative to `generate_and_run` in `path_c_chained_hybrid` (gated by
`--executor sonnet` flag). Same decomposition, same harness, same
shape annotation, same judge — only the per-step executor swapped.

| metric | sigil-executor (v3) | sonnet-executor (NH6) | delta |
|---|---|---|---|
| Path A (cached) | 26/30 | 26/30 | — |
| Path B (cached) | 5/30 | 5/30 | — |
| **Path C** | **7/30** | **26/30** | **+19** |
| avg n_steps | 1.70 | 1.70 | — |

The 19-task lift comes from swapping ONLY the executor. Same task
descriptions reach each path; the orchestration is healthy. With a
strong executor, the chained pipeline matches Path A's single-shot
performance (26/30 ≡ 26/30) — the chained recipe is not lossy.

Concretely: every prior "Path C = X/30" claim in Sigil's history was
a *local-executor capability* statement, not an orchestration limit.
The multi-step plateau is a 7B local Sigil model gap to Sonnet on
per-step Sigil generation under the conditions Sonnet's decomposition
creates. It is not a chained-pipeline artifact.

**This also retroactively explains NH16:** Opus regressed because it
over-decomposed (avg n_steps 2.03), forcing the executor through more
steps where the gap manifests; even with the best orchestrator, the
executor is what's bottlenecking the chain.

**Decision-rule outcome (per the original NH6 spec):** Path C
sonnet-executor is ≥24/30 (specifically 26/30), so "code-gen is the
bottleneck; every fine-tuning move is justified" applies. But with a
critical caveat: fine-tuning has been the wrong axis. The local model
is at 23-29/30 on *Stream-C-shape* single-step tasks (its training
distribution); the gap to Sonnet's executor performance shows up
specifically on the *Sonnet-decomposed step shapes* — descriptions
written by an orchestrator that assumes a Sonnet-quality executor.

The right inference is the one already captured in `post-sigil/
CONCLUSIONS.md` C1+CH13: pre-training proximity dominates, and a
Python-subset executor (qwen2.5-coder:7b at Python, no Sigil
fine-tuning) would close most of this gap by being on-distribution
for whatever step shape Sonnet writes.

Result file: `abc_NH6_sonnet_executor_30task.json`. Cost: $0.086
incremental over the cached A/B (the per-step Sonnet calls).

### NH7. N-of-K sampling lifts the small local model substantially

**Premise.** We always generate one candidate at temp=0. The literature
on small open-weight code models consistently shows that
generate-K-pick-best is a major lift, especially at K=4-8. We've never
tested it.

**Test.** Generate K candidates at temp=0.5 per step, run all K, pick
the candidate whose stdout passes the most deterministic structural
checks (parses, non-empty, line count matches expected, format-string
match). No retraining required.

**Cost.** K× wall time per step (~1-2 min slowdown per task on the
30-task suite). Pure-local. Easy to A/B with --n-samples flag.

**Risk.** If the local model is *consistently* wrong (same failure mode
across all K), N-of-K does not help. NH6's outcome predicts this —
high orchestration ceiling means N-of-K helps; low ceiling means it
doesn't.

### NH8. Step-level context augmentation

**Premise.** Each Sigil step today receives only its description and
the prior stdout via `$0`. The model can't see the *overall* task goal
(so it can't shape the output for the eventual aggregation) nor the
*shape* of `$0` (so it has to infer from data). Both are cheap to
inject from the orchestrator without extra cloud calls.

**Test.** Two sub-experiments:
  - Prepend "Overall goal: {task['goal']}" to each step's description.
  - Compute `$0`'s shape annotation server-side from the previous
    step's stdout ("$0 is 8 lines of `IP COUNT` space-separated") and
    inject as a prompt prefix. Pure-local string manipulation.

**Cost.** Minutes of wiring, no retrain.

**Why valuable.** Many of the 10 "empty pipeline" failures may be the
model not knowing what shape to emit. Telling it the downstream
contract is free information.

**Status (2026-05-04, partial).** Empty-pipeline post-mortem on the
post-judge baseline (`abc_v7_deepseekV1_judge_30task.json`) found:

  - 19/23 failed Path C tasks had at least one empty-stdout step
  - These cluster in TWO positions:
      * 10 final-step empties — all "compound final" (sort + take + format
        in one step description, e.g. "Sort lines descending by count, take
        top 3, reformat as 'word: count'")
      * 9 first-step empties — model can't identify $0's shape correctly

A targeted probe on `wc_top_words` step 2 confirmed the failure mechanic:
the model emitted `(split $0 " ")` (split on space) when $0 was actually
line-separated. With an explicit shape hint prepended ("$0 is 6 lines of
'WORD COUNT'"), the model correctly switched to `(split $0 "\n")` — but
then drifted into Clojure-style `(let [parts ...])` bracket syntax that
Sigil's parser rejects.

**Implementation attempts:**

  - **v1**: Sonnet decomposes with `input_shape` field per step + system
    prompt instruction "prefer shorter atomic steps". Result: avg n_steps
    1.63 → 2.17 (over-decomposed simple tasks); Path C 7→5/30. Three
    previously-passing 1-step tasks broke when over-decomposed
    (env_filter_prefix, filter_lines_in_range, lines_only_in_a). The
    "prefer atomic" instruction was the regression.
  - **v2**: Same JSON schema but rolled back the "prefer atomic"
    instruction to "use as few steps as the task naturally needs".
    Result: avg n_steps swung the other way to 1.23 (under-decomposed),
    Path C 6/30, empty-pipeline failures jumped 19→24. The shape-prompt
    edits were over-rotating Sonnet's planning behavior, not just adding
    annotation.
  - **v3**: Restored the original CHAIN_DELEGATE_SYSTEM verbatim;
    added input_shape only as a single optional field in the JSON
    schema, no other prompt changes. Result: avg n_steps 1.70 (back
    near baseline 1.63), Path C **7/30** (ties baseline). 3 gained, 3
    lost. Empty-pipeline failures 19 → 21.

**Verdict (2026-05-04, NH8 closed).** The shape-annotation mechanism
is informationally correct — the 3 v3-gained tasks (`histogram_buckets`,
`json_users_with_admin_role`, `uniq_c_with_threshold`) are exactly the
Pattern B "cannot infer $0 shape from description" failures the
hypothesis targeted. But the annotation also introduces noise on tasks
that didn't need it (3 lost: `filter_lines_in_range`, `lines_only_in_a`,
`running_sum`). Net-zero on this 30-task benchmark.

**Refined hypothesis for follow-up (NH8b):** apply shape annotation
*conditionally* — only when the step description has 2+ action verbs
or contains words that the model is known to misinterpret (e.g. "count
words" with line-separated input). The gain side appears real; the
loss side comes from blanket application. Could be A/B-tested with a
deterministic verb-counter on each step description.

Result files:
  - `abc_v7_judge_shapeann_30task.json` (v1)
  - `abc_v7_judge_shapeann_v2_30task.json` (v2)
  - `abc_v7_judge_shapeann_v3_30task.json` (v3, clean isolation)

**Side finding (worth its own meet-halfway move):** when given a correct
input-shape hint, the qwen-sigil-v7 model drifts to Clojure-style
`(let [x v y v] body)` bracket syntax. Saved to memory as a candidate
parser-level meet-halfway extension if it becomes the dominant residual
failure shape.

### NH9. Soft-pass measurement closes the perceived gap

**Premise.** Path A's 26/30 may partly be because Sonnet's Python
forgives whitespace/trailing-newline; our `expected_shape` check is
byte-exact. The local ensemble's 6/30 might be 8-10/30 by a sane
definition. We've never measured this.

**Test.** Re-score the latest result file with normalized comparison
(strip trailing whitespace, collapse internal whitespace, optionally
ignore line ordering when no sort is asked). Report the gap.

**Cost.** Trivial — one Python script over an existing JSON.

**Why it matters.** Tells us if the harness is harder than the task.
If "soft pass" is meaningfully higher than "exact pass" on Path C but
not on Path A, our scoring is the bug, not the model.

**Result (2026-05-04, REFUTED).** Built `benchmark/soft_pass_rescore.py`
applying a graduated set of comparators (exact → trim → rstrip →
collapse → unordered) to the 4 most recent A/B/C result files. Per
task, the "qualified" comparator is the most permissive one that's
*defensibly correct* (unordered allowed only when the task has no
explicit sort/top-N requirement; otherwise capped at collapse).

Across all 4 result files:
  - Path A: 26/30 exact = 26/30 qualified (no change; A already uses
    `.strip()` in its harness ok-check)
  - Path B: 5-6/30 exact = 5-6/30 qualified (no change)
  - Path C: 6-7/30 exact = 6-7/30 qualified (no change)

Only one task (`filter_lines_in_range` on the OPUS run) flipped
under any softer comparator (trim).

**Conclusion.** The harness's strict scoring is *not* artificially
deflating the local ensemble's accuracy. The Path A → Path C gap
(26/30 → 7/30 on the v3 run) is the real capability gap, not a
byte-pedantry artifact. Every prior "Path C is X/30" claim is now
defended against the "scoring is too strict" objection.

This is methodologically valuable but doesn't unlock any new lift.

Result file: `benchmark/soft_pass_rescore.py` (one-shot script).

### NH10. Python-as-control on the same multi-step suite

**Premise.** Strategically important: we've never directly measured
"what does Sigil buy us at this scale?" If the local model does Python
multi-step at 18/30 and Sigil at 6/30, the gap is Sigil-specific
(corpus depth, language idiosyncrasy). If both score similarly, we're
hitting compositional limits of small models that no language change
fixes.

**Test.** Same harness, same decomposition, same local model — produce
Python instead of Sigil. Run with the standard Python interpreter as
the executor.

**Cost.** ~half day to write the Python-output prompt + executor
plumbing. Reuses everything else.

**Why this can't be skipped.** It's the only honest answer to "is
Sigil load-bearing for this project's value claim?". Marc has already
parked this question once (Python-subset counterfactual in memory);
NH10 is the empirical answer.

**Result (2026-05-04, partial confirmation with refined story).** Built
`local_python_execute_step` as a third executor option (alongside
sigil and sonnet), gated by `--executor python`. Same Sonnet
decomposition, same shape annotation, same harness. Per-step executor
swapped to qwen2.5-coder:7b writing Python — same model size as
qwen-sigil-v7 but no Sigil fine-tune.

Three-way Path C comparison (all on identical orchestration):

| executor | passes | model |
|---|---|---|
| qwen-sigil-v7:7b (Sigil) | 7/30 | 7B fine-tuned |
| **qwen2.5-coder:7b (Python)** | **12/30** | **7B base, no Sigil fine-tune** |
| Sonnet (Python) | 26/30 | cloud |

**Decomposition of the 19-task gap NH6 identified:**
  - **+5 tasks** from removing the Sigil fine-tune (i.e. moving the
    same 7B parameter count to its native Python distribution)
  - **+14 tasks** from model scale (7B → Sonnet)

So roughly **74% of the multi-step ceiling is model-scale-driven**,
**~26% is language-proximity-driven**. Both axes matter; scale matters
more.

**Tasks gained moving from Sigil → Python on the same 7B body:**
`extract_dotted_ipv4`, `extract_python_def_lines`,
`extract_python_imports`, `find_files_by_size`, `running_sum`,
`syslog_grep_unique_processes`. All heavy on regex / sort+take /
cumulative arithmetic — exactly the patterns where Python's `re` and
list/dict ergonomics are on-distribution and Sigil's API is friction.

**Tasks still missed by local Python but solved by Sonnet's Python:**
the harder composition cases (`csv_lookup_join`, `log_count_by_hour`,
`wc_top_words`, `tsv_to_markdown`, etc.) — Sonnet's per-step Python is
materially more sophisticated than a 7B can write.

**Refined strategic conclusion (post-NH10):** the C1 thesis in
`post-sigil/CONCLUSIONS.md` is empirically supported but more
carefully: a Python-subset (Starlark-shape) executor closes ~26% of
the cloud gap at zero additional model cost. To close the rest, you
need executor scale. A deployment-ready hybrid stack therefore looks
like:

  - Cloud orchestrator (cheap once per task)
  - Mid-size local executor (14B+ on a Python subset) for the
    composition-heavy tasks the 7B can't reach
  - Maybe a small executor for the Stream-C-shape easy steps the 7B
    handles cleanly (29/30 single-step is real)
  - Capability-aware orchestration that routes per step

Result file: `abc_NH10_local_python_30task.json`. Cost: $0 cloud
(Path A and B cached, Path C purely local).

### NH10b. Larger local Python executor (codestral:22b)

**Result (2026-05-04, REFINES NH10's "scale closes the gap" story).**
Same harness, same orchestration, same Path A/B cache. Per-step
executor: codestral:22b (3× more parameters than qwen2.5-coder:7b)
writing Python.

**Outcome: 12/30 — identical to the 7B version.** Tasks shuffled but
the count didn't move:

  - 22B gained 6 tasks the 7B lost: `csv_lookup_join`,
    `extract_phone_then_format`, `extract_versions_sorted`,
    `filter_lines_in_range`, `ini_section_keys`,
    `uniq_c_with_threshold` (more structural-parsing oriented)
  - 22B lost 6 tasks the 7B had: `extract_dotted_ipv4`,
    `extract_python_imports`, `find_files_by_size`,
    `histogram_buckets`, `json_path_max_value`,
    `syslog_grep_unique_processes` (more regex-extract oriented)

The two open-weight Python coders specialize on different task families
but neither closes meaningful ground on Sonnet (still 14 tasks behind).

**Refined finding (REVISES NH10):** scale doesn't help monotonically
in the 7B → 22B band on this benchmark. The 74% scale share from
NH10's decomposition was misleading — that share requires a *much*
bigger jump (likely 70B+ local, or cloud-scale) to materialize.
There's a **capability cliff** between mid-size local Python and
cloud Python that 22B does not bridge.

**Project-level implication:** for deployment-ready multi-step
composition, **there is no "mid-size local sweet spot."** Either you
deploy with cloud-scale executors (or a hybrid that delegates only
the easy single-step shapes locally and escalates the hard ones), or
you accept ~12/30 on this kind of benchmark.

Updated conclusion in `post-sigil/CONCLUSIONS.md` C1: the
language-vs-scale attribution is reframed — language proximity gains
~5 tasks at fixed 7B size, but scaling 7B → 22B locally gains zero on
this benchmark. The scale axis is *non-monotonic in this band* and
requires a much larger jump to manifest.

Result file: `abc_NH10b_codestral_22b_30task.json`.

### NH11. Parameterized templates as a parallel architecture

**Premise.** Inspecting our 30 tasks, 25+ decompose into 5-7
recurring verbs: filter, sort, project, group, count, format,
sort-take-N. Instead of code-gen per step, expose those as
parameterized templates and have the local model fill slots.

**Test.** Build a small DSL of templates (each one is a tested,
working Sigil snippet with named slots). Sonnet (or a local 3B)
classifies each step as "use template T with slots X" and we
substitute. Code-gen replaced by structured slot-filling.

**Cost.** 1-2 days. Significant architectural deviation.

**Why interesting.** Specifically addresses the "10 empty pipelines"
failure mode where the model can't generate any working code.
Templates can never be empty — they are working code by construction.

**Risk.** Reduces what the local stack does to "match a template,
fill slots." Loses the agentic-code-generation story. Possibly the
right outcome anyway: Stream C's strength (29/30 on single-step) plus
templated multi-step plumbing might be the deployment-ready
configuration the project is actually pointed at.

### NH12. Persistent state across pipeline steps

**Premise.** Each step today is stateless except for `$0`. Closer to a
Unix pipe than a REPL. What if intermediate variables persist across
steps with declared types?

**Test.** Extend the harness with a step-level scope: each step
declares output names and types, the next step asserts inputs by
name+type. Reduces ambiguity in description-to-code mapping; makes
cross-step contracts explicit instead of bytes-on-stdout.

**Cost.** ~2 days, mostly harness wiring + a small Sigil-side
extension.

**Why valuable.** If NH6 reveals an orchestration ceiling, this is the
direct fix.

### NH13. Coverage gap analysis on the corpus

**Premise.** We've been seeding the corpus reactively (failure
appears → seed added). A structural gap analysis (what verb × data-shape
combinations are under-represented relative to the failure set?) might
reveal a class of patterns we've never trained on.

**Test.** Tag each failed task by (verb_set, data_shape). Tag each
corpus example similarly. Compute residual: which (verb_set, data_shape)
cells have many failures and few training examples?

**Cost.** Pure data work, no GPU. Half-day with the right tagging
heuristic.

**Why this might be in the residual.** It would explain why retraining
keeps yielding small lifts: we keep adding the *examples* of failures
we observe, not the *coverage classes* we lack.

### NH14. Self-critique with the same local model (no new judge)

**Premise.** The 3B step-judge runs on a *different* model than the
generator. Self-critique is a known lift: same model, second pass,
"grade your own output." Cheaper than a separate judge (no extra model
loaded), might catch errors that match the model's own competence
distribution.

**Test.** After generation, re-prompt the *same* sigil model with
"here is your output for this step; does it match the description?"
If it self-flags NO, retry once. Compare lift to the 3B judge alone.

**Cost.** Zero extra VRAM. Wall-time impact = 1 extra model call per
step.

**Why interesting.** If self-critique converges to similar lift as the
3B judge, we eliminate the judge model entirely and simplify the
deployment.

**Risk.** Self-critique has the same blind spots that produced the
wrong code. Empirically often weaker than cross-model critique.

### NH15. Larger local judge or generator

**Premise.** We picked qwen2.5-coder:3b for the judge based on
"smallest plausible model that does shape comparison." Same logic for
the generator picked 7B. We've never measured: does the
qwen-sigil-v7:7b → 14B (codestral or similar fine-tune) jump matter
on multi-step?

**Test.** Drop-in swap to a 14B-tier fine-tuned base. Re-run A/B/C.
Compare wall time, VRAM, lift.

**Cost.** Already have phi-sigil-v2:14b sitting unused. Could repeat
for codestral if we run a fresh fine-tune.

**Why we under-tested.** NH1 measured *base* reach in 14B+ (codestral
22B was dominated). We never re-tested with the *Sigil-fine-tuned*
14B as the primary in production after the harness fixes (Phase 25
moves) landed.

---

### NH16. Orchestrator reasoning quality propagates through the chain

**Premise.** Distinct from NH6 ("is the orchestration ceiling above the
local executor's capability?") — this asks: with the same local executor,
does a stronger *orchestrator* produce decompositions whose steps each
land closer to the local model's competence distribution?

The local executor's failure modes documented in NH8 (compound-final
steps, $0-shape misperception) are downstream of *what the orchestrator
decided to ask*. A stronger reasoning model may:
  - Produce more atomic decompositions where each step is a clean
    Stream-C-shape (which the local model handles at 29/30).
  - Predict more accurate input_shape annotations (NH8's mechanism).
  - Anticipate where the local model is likely to fail and adjust the
    plan (e.g., split sort+take+format into 3 steps even when the task
    description bundles them).

**Test.** Re-run A/B/C harness with `--cloud-model claude-opus-4-7`,
keeping the local stack identical (qwen-sigil-v7 + deepseek-sigil v1
fallback + Tier A validator + 3B step-judge + NH8 shape annotation).
Path A cached. Path B and Path C run fresh under Opus.

**Decision rule.**
  - If Path C lifts substantially (e.g. 7→11+/30) while Stream C single-
    step is unchanged: bottleneck has been orchestrator prompt quality,
    not local model capacity. The right next move is investing in better
    orchestration recipes (planner-side fine-tunes, structured plan
    schemas, or just paying for stronger orchestrators in production).
  - If Path C lifts only marginally (e.g. +1): local model truly is
    capped at this benchmark.

**Cost.** Opus is ~5× the per-token cost of Sonnet. For 30 tasks at the
current B+C orchestration cost (~$0.20 with Sonnet), Opus run is ~$1.00.
One-shot diagnostic, not a production cost.

**Why this is load-bearing.** It separates two confounded variables that
have been entangled in every prior multi-step result. Every "the local
ceiling is X" claim in Sigil's history was implicitly conditioned on
"...given Sonnet-quality decomposition." If Opus changes Path C
substantially, every prior multi-step verdict needs revisiting.

This is also a generalizable principle for the next project (captured as
CH13 in `post-sigil/CONCLUSIONS.md`): orchestrator-quality investment
can pay back at the executor, which has implications for how local-
deployment stacks are budgeted (cheaper executor + better orchestrator
may dominate stronger executor + cheaper orchestrator).

**Result (2026-05-04, REFUTED in this form).** Ran A/B/C with
`--cloud-model claude-opus-4-7` on the v3 stack (judge + shape
annotation), Path A cached.

| metric | Sonnet (v3) | Opus | delta |
|---|---|---|---|
| Path A | 26/30 (cached) | 26/30 | — |
| Path B hybrid | 5/30 | 1/30 | **−4** |
| Path C chained | 7/30 | 4/30 | **−3** |
| avg n_steps (C) | 1.70 | 2.03 | +0.33 |
| empty pipeline fails | 21 | 23 | +2 |
| B+C cloud cost | $0.16 | $1.07 | 6.6× |

The hypothesis was that a stronger orchestrator would produce
decompositions whose steps land closer to the local executor's
competence distribution. The data says the opposite: Opus *over-
decomposes* (avg n_steps 1.70 → 2.03, the same pattern that broke
NH8 v1) and emits more verbose step descriptions that the 7B local
model cannot track. Path B's collapse from 5 → 1 is especially
striking — Opus reshaped the "decide + run + report" orchestration
enough to break the executor on tasks Sonnet handled cleanly.

**Refined conclusion.** Stronger orchestrators do not automatically
help limited executors and can actively hurt them when the
orchestrator's natural verbosity / decomposition density exceeds what
the executor can track. There's a sweet spot in orchestrator-executor
capability matching; beyond that, more orchestrator capability is
wasted or counterproductive — analogous to the "teacher-student gap"
problem in ML knowledge distillation.

For the next project: budget orchestrator capability to *match* the
executor, not exceed it. If you want to take advantage of a stronger
orchestrator, also enforce a structural constraint on its output (e.g.
a typed plan schema, capped step count, length-bounded descriptions).
Free-text decompositions inherit the orchestrator's style — and Opus's
style is more elaborate than the executor can handle.

Result file: `abc_v7_judge_shapeann_OPUS_30task.json`. Cost (this
single experiment): $1.07 incremental over the cached Path A.

---

### Sequencing for Part V

The diagnostic value of **NH6** is unique — it determines which of
the others are even worth doing.

  1. **NH9** (1 hour) — soft-pass instrument. Cheap baseline normalization.
  2. **NH6** (30 min) — orientation test. Decides everything else.
  3. **Branch A (NH6 says code-gen):** NH7 (N-of-K), NH8 (context aug),
     NH13 (corpus gap analysis), NH14 (self-critique).
  4. **Branch B (NH6 says orchestration):** NH8, NH11 (templates),
     NH12 (persistent state). Stop fine-tuning.
  5. **NH10 in parallel** with whichever branch — strategically
     load-bearing for the project narrative regardless of outcome.
