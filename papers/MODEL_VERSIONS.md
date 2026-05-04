# Sigil model versions — catalog and rationale

> **Status (2026-05-04): Sigil project closed.** This catalog is the
> definitive list of every fine-tune attempted. The final production
> stack is qwen-sigil-v7:7b (primary) + deepseek-sigil:6.7b
> (fallback, 2-epoch). The 3-epoch deepseek-sigil-v2 retrain
> (2026-05-04) was overfit and rolled back — see
> [`SIGIL_RESULT.md`](./SIGIL_RESULT.md) for the close-out and
> [`HYPOTHESES.md`](./HYPOTHESES.md) NH3 for the overfit signature.

This document is a flat index of every fine-tuned Sigil model produced in this project, with the **why behind each version**, the result it produced, and the lesson it taught (or didn't). Cross-references `papers/JOURNEY.md` for the narrative arc.

Format: each entry has fixed fields so it can be diffed across versions.

---

## Cloud era (together.ai LoRA fine-tunes, no longer in active use)

The cloud era ran 5+ LoRA fine-tunes on together.ai across multiple base models. The driver was `benchmark/finetune.py` (since removed in commit `f46d6a7` when it was clear the path was abandoned). The supported bases were:

```
qwen3-8b           Qwen/Qwen3-8B
qwen3-coder-30b    Qwen/Qwen3-Coder-30B-A3B-Instruct  (MoE)
qwen3-4b           Qwen/Qwen3-4B
qwen2.5-7b         Qwen/Qwen2.5-7B-Instruct
gemma-4b           google/gemma-3-4b-it
llama-8b           meta-llama/Meta-Llama-3.1-8B-Instruct-Reference
```

All used together.ai's LoRA fine-tune API with `n_epochs=3-4`, `learning_rate=1e-5`, and a hand-crafted training-data generator (~145 examples in the early days, distinct from the benchmark suite to avoid contamination). The exact lineage of which adapter became "sigil-v1", "v2", etc. is partially lost — the only result file that survives locally is `benchmark/eval_v5_qwen2.5-7b.json`, identifying that adapter as `marclainez_f68b/Qwen2.5-7B-Instruct-sigil-v5-174eb962-3bf78ef7`.

### sigil-v1 / sigil-v2 (cloud, base unknown — likely Qwen3-8B / Qwen3-Coder-30B)
- **Why**: First attempts at fine-tuning a Coder model on Sigil. The plausible bases (per `finetune.py` ordering) were `Qwen/Qwen3-8B` and `Qwen/Qwen3-Coder-30B-A3B-Instruct`.
- **Recipe**: Together.ai LoRA, `lr=1e-5`, `n_epochs=3-4`, ~145 hand-crafted training examples.
- **Result**: No eval JSON survives. The work was superseded by later versions before benchmark infrastructure stabilised. Anecdotal: produced syntactically valid Sigil but with substantial issues on the early task suite.
- **Lesson**: Hand-crafted training data at this scale is too narrow to teach a 7B-30B model a new syntax. Drove the move to programmatic corpus generation (the precursor to `corpus_extender.py`).

### sigil-v3 / sigil-v4 (cloud, iterations on training data)
- **Why**: Successive iterations on the corpus and prompt template, after v1/v2 underperformed.
- **Recipe**: Same together.ai LoRA shape, with corpus rewrites between runs.
- **Result**: No eval JSON survives. Marginal-or-negative improvements over v1/v2 per anecdotal notes.
- **Lesson**: Same as v1/v2 — the corpus needed structural change (size, validator-driven generation), not iteration on prompt details. Together with the cloud cost-per-call problem, this was when "abandon cloud" became the right call.

### sigil-v5 (cloud, Qwen2.5-7B-Instruct via together.ai LoRA)
- **Why**: Test whether a different base (Qwen2.5 was newer than Qwen3 at the time of the original finetune work? actually older — but 7B Instruct was a known-good shape) could rescue the cloud path.
- **Recipe**: Together.ai LoRA on `Qwen/Qwen2.5-7B-Instruct`, `lr=1e-5`, `n_epochs=3`. Adapter id `marclainez_f68b/Qwen2.5-7B-Instruct-sigil-v5-174eb962-3bf78ef7`.
- **Result**: **6/45 (13%) on the 45-task benchmark**, broken down 5/15 / 1/15 / 0/15 across tier 1 / 2 / 3. Tier-1 (basic constructs) was passable; tier-2 (collection ops) collapsed; tier-3 (composition) was unusable. Result file: `benchmark/eval_v5_qwen2.5-7b.json`.
- **Lesson**: The killing blow for cloud LoRA. A small training corpus on a stock cloud LoRA configuration produced a model that costs real money at inference time and only solved 13% of tasks — vastly worse than the un-tuned cloud frontier (Sonnet) at the same cost. Local QLoRA on a smaller corpus *with* a real validator-feedback loop became the only path that justified itself. The cloud-LoRA infrastructure (`finetune.py`) was deleted; together.ai access was retained for one-off Sonnet calls only.

---

## Local QLoRA era — Qwen2.5-Coder lineage

All Qwen-Sigil-* models below are QLoRA fine-tunes of `Qwen/Qwen2.5-Coder-7B-Instruct`, run on an AMD RX 7800 XT (Navi31, gfx1101, 16 GB VRAM).

### qwen-sigil:3b (proof of concept)
- **Why**: Validate the local-QLoRA path on a small model before committing to 7B.
- **Base**: `Qwen/Qwen2.5-Coder-3B-Instruct`.
- **Recipe**: bf16 + nf4 4-bit, fp16 compute path (NaN'd briefly on RDNA3 numerics; resolved by switching to bf16 compute for QLoRA, see Phase 7.1).
- **Corpus**: ~1977-example `training_corpus.jsonl` v1.
- **Result**: 240 MB safetensors / 120 MB GGUF.
  - **Synthetic 100-task A/B (10 iter × 10 tasks): A=43/100 (43%), B=48/100 (48%)** — vs baseline (un-tuned 3B) **A=10/100, B=29/100**. Net **+33 pp on A, +19 pp on B** from fine-tuning. Result files: `benchmark/rag_loop_3b_baseline.json`, `benchmark/rag_loop_3b_finetuned.json`.
  - End-to-end workflow proven: local fine-tune → GGUF → ollama serve.
- **Lesson**: 3B was too small to absorb the full Sigil pattern set (final score still 43-48% on the synthetic suite vs the eventual 80%+ of the 7B). Informed the move to 7B. The numerics gotcha (RDNA3 + bf16 + bnb) became Phase 7.1 documentation.

### qwen-sigil:7b (v1)
- **Why**: Scale up from 3B once 3B confirmed the workflow.
- **Recipe**: First successful 7B-on-16GB QLoRA. 4-bit nf4, bf16 compute, lr=1e-4, max_seq=2048, lora_r=16.
- **Corpus**: same v1 corpus as the 3B run.
- **Result**: 160 MB safetensors / 80 MB GGUF.
  - **Synthetic 100-task A/B: A=56/100 (56%), B=74/100 (74%)** — vs baseline (un-tuned 7B) **A=15/100, B=48/100**. Net **+41 pp on A, +26 pp on B**. Result files: `benchmark/rag_loop_7b_baseline.json`, `benchmark/rag_loop_7b_finetuned.json`.
  - First model that produced reliable Sigil at consumer-hardware cost.
- **Lesson**: bnb-rocm is workable on RDNA3 with `HSA_OVERRIDE_GFX_VERSION=11.0.0`; also confirmed the OOM gotcha (ollama-loaded models reserve VRAM during training and must be unloaded with `keep_alive=0` first).

### qwen-sigil-v2:7b (deployment default for months)
- **Why**: Deeper retrain than v1 with prompt-format and corpus refinements.
- **Recipe**: lr=1e-4, max_seq=2048 (the v1 settings — they happened to work on the v2 corpus because no example exceeded 1500 tokens *in the early-shuffled batches*).
- **Corpus**: refined v2 corpus. Final loss 0.17.
- **Result**: 76% pass on synthetic 100-task; 85% with retry. **20/30 (67%) on Stream C deployment study.** Held as deployment default through Phase 15.
- **Lesson**: v2's success at lr=1e-4 was data-dependent (no long-token examples). When v3's corpus added longer Python refs, the same lr regimen NaN'd — the bf16 + Navi31 stability finding documented in `feedback_navi31_qlora.md`.

### qwen-sigil-v3:7b (failed retrain — bf16 forward overflow)
- **Why**: First attempt to add 6 new string-pair builtins (`common_prefix`, `common_suffix`, `is_subseq`, `is_rotation`, `edit_distance`, `common_chars`) to v2.
- **Recipe**: same as v2 (lr=1e-4, max_seq=2048).
- **Corpus**: v2 corpus + new examples featuring the 6 new builtins. Critically, this batch included longer Python reference examples (up to ~1700 tokens).
- **Result**: **NaN'd at step 60.** loss → inf → grad → nan → all subsequent gradients nan.
- **Lesson**: The `feedback_navi31_qlora.md` recipe was born here. *"clip(inf) = nan"* — gradient clipping does not save you from a forward-pass overflow. The defenses must be in precision (lower max_seq, slower warmup), not in clipping.

### qwen-sigil-v3.1:7b (recovery, but regressed)
- **Why**: Retrain with `bf16-stable` settings: lr=2e-5, max_seq=1024, warmup_ratio=0.2, max_grad_norm=1.0, plus corpus filtering to drop examples >1500 tokens.
- **Recipe**: the v3.1-stable recipe documented in `feedback_navi31_qlora.md`.
- **Corpus**: v3 corpus, filtered to ≤1500-token examples (drops about 1% of entries).
- **Result**: Trained successfully with no NaN. Final loss 0.13 (deeper than v2's 0.17). **84% on synthetic with retry. But 16/30 (53%) on Stream C — −4 vs v2.**
- **Lesson**: This is the **failure-mass-redistribution finding** (Phase 12). Three retrains on the same corpus shape converged on a ~22/30 ceiling. Retraining shifts which tasks fail, but doesn't expand the budget. v3.1 lost 5 tasks v2 had memorised (`cut_first_n_chars`, `grep_only_matching`, `process_grep`, `json_path_extract`, `extract_urls`) and gained one (`ipv4_validate`). v2 stayed deployment default.

### qwen-sigil-v4:7b (corpus + prelude seeds)
- **Why**: Test whether adding the new prelude functions (tokens, squeeze, split_blocks, find_all, line_count) and 14 seed examples to the corpus would let a v4 retrain combine v2's broad coverage with new-pattern coverage.
- **Recipe**: v3.1-stable recipe (lr=2e-5, max_seq=1024, warmup=0.2, clip=1.0, lora_r=16).
- **Corpus**: 2046-entry v2-style + 14 new prelude seeds = 2060 entries. **Bulk corpus unchanged**; 99.3% of training signal was identical to v2.
- **Result**:
  - **Alone, no RAG**: 13/30 (43%) — markedly weaker than v2's 20/30 because the bulk-corpus retraining shifted weights without adding meaningful new signal (only 0.1% of corpus had each new prelude function — well below the ~2% threshold).
  - **With targeted RAG seeds (10 v4-specific)**: 23/30 (77%).
  - **+ phi-sigil-v1 ensemble (3-attempt)**: **26/30** (87%).
  - **+ extended seeds (12) + phi ensemble**: **28/30** (93%) — the highest single-corpus result before v5.
- **Lesson**: RAG retrieval and weight-level training are **complementary, not redundant**. v4's weights didn't internalize new patterns (corpus signal too weak), but RAG retrieval delivered them at inference time. The retrain's only real benefit was making v4 slightly better at *composing* the patterns RAG surfaces (e.g., for `find_max_in_log`, `permission_octal_to_symbolic`).

### qwen-sigil-v5:7b (clean corpus retrain)
- **Why**: After v4 confirmed the corpus-signal-too-weak hypothesis, do a thorough corpus rewrite + audit + retrain. This was the user's explicit ask: *"I want a proper corpus consistent with the current state of Sigil"* — meaning the corpus needs to use canonical names, working primitives, no silent training poison.
- **Recipe**: v3.1-stable recipe (unchanged). 822 steps in 9124 s (~2h32m) on the RX 7800 XT.
- **Corpus**: **2186 entries**, thoroughly cleaned:
  - Phase A — mechanical safe rewrites: `arg_int <int>` → `argv_int <int>` (12 entries), `regex_find_all` → `find_all` (5 entries).
  - Phase B — 114 new verified examples covering canonical names (verified by running each through `vm.exe` and matching expected output).
  - Phase C — if-Lisp-trap fixes (added explicit `(else)` markers in 48 places that had the silent 2-stmt-then trap).
  - Phase D — runtime verification: ran every entry through `vm.exe` to flag undefined-variable / unknown-function references. After fixing the regex bug in Phase C, 0 entries dropped.
  - Plus interpreter additions: `second`/`third`/`string_length` aliases (catches model reaches the corpus had been training on as silent poison).
  - **`tokens` 1.7%, `find_all` 1.6%, `argv_int` 0.9%** — all above the 0.1% baseline of v4 but still well below the ~5% threshold needed for confident weight-level absorption per the literature.
- **Result**:
  - Final running-mean train_loss **0.554** (vs v4's 0.486, v3.1's 0.13). Higher because the corpus now contains the new prelude/canonical patterns the model has to absorb against its strong Python-shaped prior.
  - **Alone, no RAG: 14/30 (47%)** — virtually identical to v4 alone (13/30). Cleaning the corpus did NOT push canonical names into the weights.
  - **+ phi-sigil-v1 ensemble (3-attempt): 27/30 (90%)** — slightly below v4+phi's 28/30. Lost 1 task (`shell_argv_count`) that v4 had caught.
- **Lesson**: The cleaner corpus is **better hygiene but not better accuracy** at this corpus size. The 7B model's strong Python-shape prior dominates over canonical-name signal at 1.7-2% corpus coverage; you'd need either substantially more examples (~5-10%) or full pre-training to shift the default. **The v5 retrain validates the v4 finding rather than overturning it**: weight-level training at this scale shifts which tasks fail, not how many.

  The cleaner corpus pays off in three other ways:
  1. **Lower silent training poison** — entries calling non-existent `(second arr)` / `(string_length s)` / `arg_int <string>` no longer teach the model bad patterns (those names now work via aliases AND every retained entry is lint+runtime-verified).
  2. **Reproducibility** — the `corpus_refresh.py` + `cleanup_corpus.py` + `runtime_check_corpus.py` + `refresh_seeds.py` pipeline is documented and re-runnable, so the next retrain (v6) starts from a known-good baseline.
  3. **Real measured energy data** — the v5+phi Stream C run was the first executed with `amdgpu_top` sampling. Measured workload-attributable energy: **0.370 Wh/task** (vs the 0.382 Wh/task estimate previously used — within 3%). See `papers/PLAN_local_vs_cloud_economics.md` and `benchmark/power_logs/v5_ensemble_stream_c.csv`.

---

## Phi-4 lineage (failure-shape diversity for ensemble)

### phi-sigil-v1:14b (introduced for ensemble diversity)
- **Why**: After v3.1 confirmed three rounds of single-model retraining produced no further gain, the next move was failure-shape diversity (Phase 16). Phi-4 was chosen because it's the most architecturally distinct from Qwen on the ollama.com catalog that fits 16 GB QLoRA: dense 14B, Microsoft's textbook+synthetic training data, completely different prior from Qwen's Alibaba web-code mix.
- **Recipe**: v3.1-stable recipe, with two Phi-3-arch-specific tweaks:
  - LoRA target modules: `[qkv_proj, o_proj, gate_up_proj, down_proj]` (Phi-3/4 uses fused projections, not Qwen's split `q_proj`/`k_proj`/`v_proj`).
  - Auto-detection added in `finetune_local.py`.
- **Corpus**: same as v4's (2060 entries).
- **Result**: 4h 36m training. **19/30 alone**, **+3 unique wins over v2** (split_at_blank_lines, ipv4_validate, extract_function_names_py). **Failure-shape overlap with v2 = 36%**.
- **Critical workaround — runtime LoRA bug**: ollama 0.19's runtime ADAPTER application path crashes on Phi-3/4 (likely due to fused projection handling). Cannot ship the LoRA via Modelfile `ADAPTER` directive. Fix: merge the LoRA into the base weights on CPU (peft `merge_and_unload()`, ~28 GB RAM peak), convert merged HF model to GGUF f16, quantize on import via `ollama create -q q4_K_M`. The merged Q4_K_M model is a standalone GGUF that ollama serves without runtime LoRA application. Documented in `feedback_phi4_lora_ollama.md`.
- **Lesson**: **Failure-shape diversity is a real lever**, even when the second model is weaker alone. v2+phi-v1 ensemble = 25/30, +3 over v2 alone. The diversity, not raw capability, is what transfers. Phi-4 was the right pick: distinct lineage, distinct failure shapes.

### phi-sigil-v2:14b (planned, not yet trained)
- **Why**: Once v5 confirms the clean corpus path, retrain phi on the same clean corpus to give the ensemble matched canonical-name training on both legs.
- **Status**: Pending v5 results. ~4.5h training time when scheduled.

---

## Recipe across all local versions

The QLoRA recipe converged to a single stable shape after the v3 NaN incident:

```
--lr 2e-5
--max-seq 1024
--warmup-ratio 0.2
--max-grad-norm 1.0
--lora-r 16
--lora-alpha 32
--epochs 3
--micro-batch 1
--grad-accum 8
--four-bit  (nf4 + bf16 compute + double quant)
HSA_OVERRIDE_GFX_VERSION=11.0.0
PYTORCH_HIP_ALLOC_CONF=expandable_segments:True
```

**Why not the v2 settings (lr=1e-4, max_seq=2048)?** Because they're *data-dependent*. They work as long as no example > ~1500 tokens lands in an early-shuffled batch with high LR. Any retrain with novel data risks NaN. The v3.1-stable recipe trades a tiny under-fit (final loss 0.13 → 0.20) for unconditional stability. The trade is correct.

## Lookup: which model do you want?

| Use case | Recommended model |
|---|---|
| **Production deployment, single model** | `qwen-sigil-v2:7b` (or v5 once available) |
| **Best deployment accuracy (ensemble)** | `qwen-sigil-v4:7b` → `phi-sigil-v1:14b` (28/30 on Stream C) |
| **Cheapest first-attempt** | `qwen-sigil-v2:7b` (5-7s per task) |
| **Different failure shape needed** | `phi-sigil-v1:14b` (slower at 8-15s per task; catches what Qwen misses) |
| **Anything that needs the new prelude** | v4 or v5 (v2 doesn't know `tokens`/`find_all`/etc. natively) |

## File locations

- LoRA adapters: `benchmark/lora_out_*` (one directory per version).
- GGUF adapters: `benchmark/sigil_lora_*.gguf`.
- Modelfiles: `benchmark/Modelfile.sigil_*`.
- Result JSONs: `benchmark/stream_c_*.json` (one per (model, config) combination tested).
- Training corpus: `benchmark/training_corpus.jsonl` (current = 2186-entry clean version after Phase D).
- Pre-cleanup snapshots: `benchmark/training_corpus.before_refresh.jsonl`, `benchmark/training_corpus.cleaned.jsonl`, `benchmark/training_corpus.runtime_clean.jsonl`.
