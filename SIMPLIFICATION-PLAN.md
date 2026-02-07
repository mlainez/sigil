# AISL Type System Simplification Plan

**Date**: 2026-02-07  
**Goal**: Eliminate ambiguity by removing sized numeric types

---

## 🚨 CRITICAL PRINCIPLE: AISL-ONLY TOOLING

**ALL tools and scripts in this project MUST be written in pure AISL.**

This includes:
- Converters (like convert_syntax.aisl)
- Code generators
- Build scripts
- Test utilities
- Documentation generators

**Why?**
1. Forces us to make AISL complete (discover gaps immediately)
2. Every script is a working example for LLMs
3. Zero external dependencies
4. Validates that AISL can handle real tasks

**If you write Python/Bash, you're avoiding the problem, not solving it.**

---

## Problem Statement

Current AISL has 4 numeric types: `i32`, `i64`, `f32`, `f64`

This creates **arbitrary choice** for LLMs:
- Should `count` be `i32` or `i64`? No clear answer.
- Should `price` be `f32` or `f64`? Pure guesswork.
- Results in multiple ways to write identical logic
- Violates AISL's "one way only" principle

**Analysis of real benefits:**
- Performance: ❌ Negligible on modern hardware
- Memory: ❌ Irrelevant for typical AISL programs  
- FFI: ❌ AISL has no FFI yet

**Result: Zero benefit, pure ambiguity**

## Proposed Solution

**Remove sized types entirely. Keep only:**

| Current | Proposed | VM Type |
|---------|----------|---------|
| i32, i64 | `int` | i64 |
| f32, f64 | `float` | f64 |
| bool | `bool` | bool |
| string | `string` | string |
| + array, map, regex, result | (unchanged) | (unchanged) |

## Benefits

1. **Zero ambiguity** - One way to write integer code
2. **Simpler grammar** - Fewer type keywords
3. **Easier for LLMs** - No guessing, no choice paralysis
4. **Still expressive** - Can represent all computations
5. **Matches principle** - "One way only"

## Implementation Steps

### Phase 1: Add new types (non-breaking)
- [ ] Add `int` keyword to lexer (maps to i64)
- [ ] Add `float` keyword to lexer (maps to f64)
- [ ] Allow `int`/`float` everywhere types are used
- [ ] Test: both old and new work

### Phase 2: Convert codebase
- [ ] Write converter script: `i32|i64` → `int`, `f32|f64` → `float`
- [ ] Convert all 88 test files (334 occurrences)
- [ ] Convert all examples
- [ ] Convert documentation
- [ ] Verify all tests pass

### Phase 3: Remove old types (breaking)
- [ ] Remove `i32`, `i64`, `f32`, `f64` from lexer
- [ ] Remove from type checker
- [ ] Update error messages
- [ ] Final test pass

### Phase 4: Documentation
- [ ] Update AGENTS.md - show only `int`/`float`
- [ ] Update LANGUAGE_SPEC.md - remove sized types section
- [ ] Update .aisl.grammar - `ty int|float|bool|string|...`
- [ ] Update .aisl.meta - note simplification

## Migration Strategy

**For users/LLMs:**
- Simply replace `i32`/`i64` with `int`
- Simply replace `f32`/`f64` with `float`
- No semantic changes, pure syntax

**Example:**

```lisp
; Before
(fn factorial n i32 -> i32
  (if (call eq n 0)
    (ret 1))
  (set n_minus_1 i32 (call sub n 1))
  (set result i32 (call factorial n_minus_1))
  (ret (call mul n result)))

; After  
(fn factorial n int -> int
  (if (call eq n 0)
    (ret 1))
  (set n_minus_1 int (call sub n 1))
  (set result int (call factorial n_minus_1))
  (ret (call mul n result)))
```

## Considerations

**"What if we need 32-bit for FFI later?"**
- Add `i32`/`f32` back **only when FFI is implemented**
- Make them **explicit opt-in** for FFI use cases
- Keep `int`/`float` as default for all normal code

**"What about performance-critical code?"**
- AISL is not designed for bit-level optimization
- If you need that, use C/Rust and call from AISL (future FFI)
- 64-bit is default on modern platforms anyway

**"What about educational value of teaching type sizes?"**
- Not AISL's goal - AISL is for LLM code generation
- Clarity > pedagogy
- Users learning systems programming should use C

## Timeline Estimate

- Phase 1 (add new types): 2 hours
- Phase 2 (convert codebase): 4 hours  
- Phase 3 (remove old types): 1 hour
- Phase 4 (documentation): 2 hours

**Total: ~9 hours of work**

## Decision

Should we proceed with this simplification?

**Arguments FOR:**
- ✅ Eliminates choice/ambiguity
- ✅ Aligns with "one way only" principle
- ✅ Makes AISL easier for LLMs
- ✅ No loss of expressiveness
- ✅ Can add sized types back later if needed

**Arguments AGAINST:**
- ❌ Breaking change (but we're already doing one)
- ❌ Work to convert codebase (but worthwhile)
- ❌ Different from C/Java/etc (but that's the point)

**Recommendation: PROCEED**

This is the right move for AISL's design goals.
