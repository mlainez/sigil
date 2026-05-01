# Sigil Corpus Generation Pipeline

> **See also**: [`llm_generation_strategy.md`](./llm_generation_strategy.md) —
> the *how and why* of the generation pipeline (ollama → coaching → Sonnet
> fallback, evidence-based language tweaks, no Opus by default).

Target: **5-10M tokens** of validated Sigil code for continued pretraining + SFT.

Current: ~150K tokens (265 corpus files + 153 tests + 20 stdlib).
Gap: **30-65× more data needed.**

## Four generation streams

### Stream A: Python → Sigil translation (biggest lever)
Pull real Python programs from open-source repos, translate to Sigil using Opus/Sonnet with the grammar prompt, validate each through the interpreter.

**Sources:**
- Python standard library examples
- LeetCode/HackerRank-style problems (well-defined I/O)
- Small CLI utilities from GitHub
- Exercism Python exercises

**Volume target: 5,000 programs × ~200 tokens avg = 1M tokens**

**Pipeline:**
```
1. Scrape or download 5000 short Python programs (<50 LOC each)
2. For each, use Claude to write Sigil equivalent
3. Run both through their interpreters with same inputs
4. Keep only pairs where outputs match exactly
5. Format as (problem_description, python_code, sigil_code) triples
```

### Stream B: Algorithmic variants (volume + coverage)
For each algorithm (sort, search, parse, transform), generate multiple valid Sigil implementations using different idioms.

**Categories:**
- 50 sorting variants (bubble, insertion, selection, merge, quick, ...)
- 50 string processing (reverse, palindrome, anagram, encode, ...)
- 50 math (prime, factorial, fibonacci, gcd, lcm, power, ...)
- 50 array ops (map, filter, reduce, unique, flatten, ...)
- 50 data processing (CSV, JSON, URL, query string, ...)
- 50 state machines (parsers, FSMs)
- 50 I/O patterns (file read/write, stdin, network)

**Volume target: 350 algorithms × 5 variants × ~150 tokens = 260K tokens**

### Stream C: Error + fix pairs (crucial for correctness)
Take every working program, corrupt it in systematic ways, record the error message, and pair it with the fix.

**Corruption types:**
- Missing parens
- Wrong argument count
- Wrong type in `set`
- Undefined variable
- Reserved keyword as variable
- Off-by-one in loop bounds

**Volume target: 5,000 corruption triples × ~150 tokens = 750K tokens**

**Format:**
```
Problem: <task description>
Attempt: <corrupted code>
Error: <interpreter error message>
Fix: <corrected code>
Explanation: <brief why>
```

### Stream D: Documentation/explanation pairs (for SFT)
Generate natural-language descriptions of what code does, and vice versa.

**Volume target: 2,000 pairs × ~300 tokens = 600K tokens**

**Formats:**
- Code → natural description
- Description → code
- Code with bug → diagnosis
- Question about Sigil concept → explanation + code example

## Combined totals

| Stream | Programs | Tokens |
|--------|----------|--------|
| A: Python → Sigil | 5,000 | ~1M |
| B: Algorithmic variants | 1,750 | ~260K |
| C: Error + fix | 5,000 | ~750K |
| D: Documentation | 2,000 | ~600K |
| Plus existing corpus | 265 | ~100K |
| Plus stdlib + tests | 170 | ~50K |
| **Total** | **~14,000** | **~2.8M** |

Still short of the 5-10M minimum, but **20× current size**. Enough to attempt continued pretraining.

## Concrete next steps

### Phase 1: Python corpus harvester (1-2 days)
- Download 10,000 Python programs from public sources
- Filter for <50 LOC, self-contained, deterministic output
- Store as (description, inputs, expected_output, python_code) JSON

### Phase 2: Batch translator (3-5 days)
- Write a parallel Claude-based translator
- For each Python program, emit Sigil candidates
- Validate by running both through interpreters with test inputs
- Rate limit ~1 req/sec with 10 workers = 36,000/day possible

### Phase 3: Error/fix generator (2-3 days)
- Write systematic corruption tool
- Run through interpreter, capture errors
- Use Claude to explain/fix

### Phase 4: Tokenizer retraining (optional, 1 day)
- Train a BPE tokenizer on the Sigil-only corpus
- Merge with base model tokenizer by adding Sigil-specific tokens
- Evaluate chars/token improvement

### Phase 5: Continued pretraining (compute-bound)
- Use Together.ai or local GPU
- Target: Qwen2.5-Coder-7B or Qwen3-Coder-30B-A3B
- ~2-5B tokens processed (multiple epochs on our 2.8M)
- Cost estimate: $50-200 on Together.ai

### Phase 6: SFT (1 day)
- Instruction-format the existing corpus
- LoRA fine-tune on the continued-pretrained model

### Phase 7: Evaluation
- Run benchmark harness against base + fine-tuned models
- Measure: first-attempt correctness, total tokens, retry count
- Compare against Python baseline

## Realistic timeline

- **Week 1**: Phase 1 + 2 (harvest + translate ~5000 programs)
- **Week 2**: Phase 3 (error/fix data) + tokenizer audit decision
- **Week 3**: Phase 5 + 6 (training)
- **Week 4**: Phase 7 (eval) + iteration

## Budget estimate

- Claude API for translation: 5000 programs × 2 calls avg × ~3000 tokens = 30M tokens ≈ $300 on Sonnet
- Error generation: 5000 × 2 calls × ~2000 tokens = 20M tokens ≈ $200
- Documentation: 2000 × ~2000 tokens = 4M tokens ≈ $40
- **Total Claude cost: ~$540**

- Together.ai fine-tuning: LoRA on 7B model with ~3M tokens × 3 epochs ≈ $30-50
- Inference evaluation: ~$10-20

- **Total project cost: ~$600-700**
