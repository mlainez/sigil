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
