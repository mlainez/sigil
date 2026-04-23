# Sigil Benchmark Results — Anthropic Models (April 2026)

## Setup

- **Benchmark harness**: `benchmark/harness.py` via Claude CLI (`--provider claude-cli`)
- **Languages**: Sigil, Python, JavaScript, Go
- **Tasks**: 10 tasks across 3 difficulty tiers (40 test cases total)
- **Runs**: 1 per (task, language, model)
- **Max retries**: 5 per task
- **Sigil system prompt**: ~1,600 token grammar reference (`.sigil.grammar`)
- **Other languages**: minimal ~40 token instruction prompt

## Summary Table

### First-Attempt Correctness (out of 10 tasks)

| Model | Sigil | Python | JavaScript | Go |
|-------|-------|--------|------------|-----|
| Haiku 4.5 | 6/10 (60%) | **10/10 (100%)** | **10/10 (100%)** | 9/10 (90%) |
| **Sonnet 4.6** | **10/10 (100%)** | **10/10 (100%)** | **10/10 (100%)** | 9/10 (90%) |
| Opus 4.6 | 9/10 (90%) | **10/10 (100%)** | **10/10 (100%)** | **10/10 (100%)** |
| Opus 4.7 | 9/10 (90%) | **10/10 (100%)** | **10/10 (100%)** | **10/10 (100%)** |

### Final Correctness (after up to 5 retries)

All models achieved **100% final correctness** across all languages — every task was eventually solved.

### Average Total Tokens

| Model | Sigil | Python | JavaScript | Go |
|-------|-------|--------|------------|-----|
| Haiku 4.5 | 69,539 | 33,854 | 34,177 | 37,344 |
| Sonnet 4.6 | 25,792 | 17,392 | 17,422 | 19,282 |
| Opus 4.6 | 31,440 | 17,542 | 17,571 | 17,647 |
| Opus 4.7 | 35,811 | 23,956 | 24,026 | 24,093 |

### Average Output Tokens (code generation only)

| Model | Sigil | Python | JavaScript | Go |
|-------|-------|--------|------------|-----|
| Haiku 4.5 | 6,883 | 1,046 | 1,356 | 1,208 |
| Sonnet 4.6 | 2,444 | 116 | 132 | 222 |
| Opus 4.6 | 816 | 99 | 114 | 189 |
| Opus 4.7 | 1,501 | 123 | 175 | 242 |

## Key Findings

### 1. Sonnet 4.6 is the best Sigil model (without fine-tuning)

Sonnet 4.6 achieved **10/10 first-attempt correctness** on Sigil — matching Python and JavaScript. This is the only model where Sigil correctness equals mainstream languages. It also had the lowest Sigil token overhead among models that achieved 100%.

### 2. Token overhead is dominated by the grammar system prompt

The Sigil grammar (`~1,600 tokens`) is loaded as a system prompt for every request. Due to prompt caching, this manifests as ~3,700-6,000 additional input tokens per request. This is a fixed cost that fine-tuning eliminates entirely.

Breakdown for first-attempt passes:

| Model | Sigil avg input | Python avg input | Input delta (grammar cost) |
|-------|-----------------|------------------|---------------------------|
| Haiku 4.5 | 36,488 | 32,808 | +3,680 |
| Sonnet 4.6 | 23,348 | 17,276 | +6,072 |
| Opus 4.6 | 21,125 | 17,443 | +3,682 |
| Opus 4.7 | 27,605 | 23,833 | +3,772 |

### 3. Sigil output tokens are 2-10x higher than Python

This is expected — S-expression syntax is more verbose per operation. However, for Opus 4.6, the gap is small in absolute terms: 816 vs 99 output tokens (only 717 tokens more per task).

### 4. Retry costs dominate when they occur

When Sigil fails on first attempt, the retry loop is expensive:
- `query_string` on Haiku: 4 attempts = 164,596 total tokens (vs 33,833 for Python)
- `balanced_parens` on Haiku: 3 attempts = 126,322 total tokens
- `stack_calculator` on Opus 4.7: 3 attempts = 93,638 total tokens

The retry multiplier (3-5x per additional attempt) overwhelms any per-line verbosity difference.

### 5. The stumbling block task: query_string

`07_query_string` (parse `key=val&key=val` and print sorted) is the hardest Sigil task:
- Haiku: 4 attempts
- Opus 4.6: 3 attempts
- Sonnet 4.6: 1 attempt (the only model to get it first try)
- Opus 4.7: 1 attempt

This involves string parsing, sorting, and map operations — areas where Sigil's unfamiliarity costs the most thinking.

## Implications for Fine-Tuning

These results establish the **baseline without fine-tuning**. The key takeaways for the fine-tuning experiment:

1. **The grammar prompt overhead (~3,700 tokens) disappears entirely** with a fine-tuned model that knows Sigil natively.
2. **First-attempt correctness should improve** because the model won't be learning the language from a prompt — it will know it from training.
3. **Output tokens should decrease** as the model learns idiomatic Sigil patterns rather than reasoning about how to construct them.
4. **The strongest proof** would be a fine-tuned 7B model matching or exceeding these base-model results on both correctness and total tokens.

## Per-Tier Breakdown

### Tier 1 (Simple): fizzbuzz, reverse_words, two_sum

All models achieved 100% first-attempt correctness across all languages, except:
- Haiku/Sigil: 67% (failed two_sum)

### Tier 2 (Medium): word_frequency, balanced_parens, run_length_encode, query_string

| Model | Sigil | Python | JavaScript | Go |
|-------|-------|--------|------------|-----|
| Haiku 4.5 | 50% | 100% | 100% | 75% |
| Sonnet 4.6 | 100% | 100% | 100% | 100% |
| Opus 4.6 | 75% | 100% | 100% | 100% |
| Opus 4.7 | 100% | 100% | 100% | 100% |

### Tier 3 (Complex): stack_calculator, matrix_transpose, caesar_cipher

| Model | Sigil | Python | JavaScript | Go |
|-------|-------|--------|------------|-----|
| Haiku 4.5 | 67% | 100% | 100% | 100% |
| Sonnet 4.6 | 100% | 100% | 100% | 67% |
| Opus 4.6 | 100% | 100% | 100% | 100% |
| Opus 4.7 | 67% | 100% | 100% | 100% |
