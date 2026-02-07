# Session Summary: 2026-02-07

## What We Did

### 1. Identified Regex Already Exists ✅
**Problem**: Assumed AISL lacked regex support, planned to implement it.  
**Discovery**: Regex is fully implemented (vm.c:3593-3650, bytecode.h:237-241)
- `regex_compile`, `regex_match`, `regex_find`, `regex_find_all`, `regex_replace`
- Uses POSIX Extended Regular Expression syntax

**Actions Taken**:
- Updated AGENTS.md: Kept existing regex section with examples
- Updated .aisl.grammar: Added `regex` to type list and operations
- Updated .aisl.meta: Added stdlib section documenting regex availability
- Updated LANGUAGE_SPEC.md: Added comprehensive regex section with examples
- Added philosophy note: `(stdlib-first "check-before-assuming-missing")`

**Lesson**: Always check existing stdlib before assuming features are missing.

---

### 2. Discovered Type Size Ambiguity Problem ✅

**Question Raised**: Why do we have i32/i64 and f32/f64? Does this create ambiguity?

**Analysis**:
- Having 4 numeric types violates "one way only" principle
- LLMs must arbitrarily choose between i32/i64, f32/f64
- No real benefit for typical AISL programs:
  - Performance: Negligible on modern hardware
  - Memory: Irrelevant for most code
  - FFI: AISL has no FFI yet

**Conclusion**: Pure ambiguity with zero benefit.

**Actions Taken**:
- Created SIMPLIFICATION-PLAN.md: Comprehensive plan to eliminate sized types
- Updated .aisl.analysis: Added type-size-ambiguity section
- Documented recommendation: Keep only `int` (→i64) and `float` (→f64)

---

## Current State

### What's Working
- ✅ Regex fully functional in AISL
- ✅ Documentation updated with regex examples
- ✅ Type ambiguity problem identified and analyzed
- ✅ Simplification plan documented

### What's Broken
- ⚠️ Parser only accepts flat syntax: `a i32 b i32`
- ⚠️ 79/88 tests still use old nested syntax: `((a i32) (b i32))`
- ⚠️ Tests will fail until converted

### Files Modified (Uncommitted)
```
M  AGENTS.md                      (removed duplicate regex section)
M  compiler/c/src/parser.c        (removed nested param support)
M  LANGUAGE_SPEC.md               (added regex section, updated types)
M  .aisl.analysis                 (added type-size-ambiguity analysis)
M  .aisl.grammar                  (added regex type and ops)
M  .aisl.meta                     (added stdlib, updated tasks)
A  SIMPLIFICATION-PLAN.md         (new: type system simplification plan)
A  scripts/convert_syntax.aisl    (partial: needs completion)
```

---

## Next Steps (In Order)

### Option A: Fix Current Breaking Change First
1. Complete `scripts/convert_syntax.aisl` using regex
2. Convert all 79 test files from nested to flat syntax
3. Verify 88/88 tests pass
4. Commit: "Remove parameter syntax ambiguity - one way only"

### Option B: Do Both Simplifications Together
1. Implement `int`/`float` types (map to i64/f64)
2. Write converter: nested→flat AND i32/i64→int, f32/f64→float
3. Convert all 88 tests in one pass
4. Remove old syntax support from parser
5. Commit: "Simplify syntax: flat params only, int/float types"

**Recommendation**: Option B - Do both at once
- Already breaking backward compatibility
- More efficient to convert once
- Cleaner git history
- Less disruption overall

---

## Implementation Plan (Option B)

### Phase 1: Add New Types (2h)
```c
// In lexer.c
case 'i':
    if (match_keyword("int")) return TOKEN_INT;
    if (match_keyword("i32")) return TOKEN_I32;
    if (match_keyword("i64")) return TOKEN_I64;
    ...
case 'f':
    if (match_keyword("float")) return TOKEN_FLOAT;
    ...

// In parser.c  
Type* parse_type(Parser* p) {
    if (check(p, TOKEN_INT)) {
        advance(p);
        return type_i64();  // int maps to i64
    }
    if (check(p, TOKEN_FLOAT)) {
        advance(p);
        return type_f64();  // float maps to f64
    }
    ...
}
```

### Phase 2: Write Complete Converter (2h)
```lisp
(fn convert_file path string -> string
  ; 1. Convert nested params: ((a i32) (b i32)) -> a i32 b i32
  ; 2. Convert types: i32|i64 -> int, f32|f64 -> float
  ; 3. Return converted content
  ...)
```

### Phase 3: Mass Convert (1h)
```bash
# Convert all tests
for f in tests/test_*.aisl; do
    ./aisl scripts/convert_syntax.aisl "$f"
done

# Convert all examples
for f in examples/*.aisl; do
    ./aisl scripts/convert_syntax.aisl "$f"
done

# Verify
make test  # Should pass 88/88
```

### Phase 4: Documentation (2h)
- Update all docs to show `int`/`float` only
- Remove references to i32/i64/f32/f64
- Add migration notes
- Update .aisl.grammar

### Phase 5: Commit (30min)
```
Simplify AISL syntax for LLM code generation

- Remove nested parameter syntax: use flat params only
- Remove sized numeric types: use int/float only  
- Eliminate arbitrary choices that create ambiguity
- Align with "one way only" design principle

BREAKING CHANGE: Old syntax no longer supported
- ((a i32)) -> a int
- i32/i64 -> int (maps to i64)
- f32/f64 -> float (maps to f64)

All tests and examples updated.
Rationale documented in .aisl.analysis and SIMPLIFICATION-PLAN.md
```

---

## Questions to Resolve

1. **Should we do both simplifications together (Option B)?**
   - Pro: More efficient, cleaner history, one breaking change
   - Con: Larger change, more testing needed

2. **Should int/float be aliases or replacements?**
   - Alias: i32/i64 still work, int is shorthand
   - Replacement: Remove i32/i64 entirely (recommended)

3. **Timeline?**
   - Full implementation: ~7-9 hours
   - Can be done in one session or split across multiple

---

## Key Insights from This Session

### 1. Always Check Stdlib First
- Assumed regex was missing → wasted time planning implementation
- Reality: Fully implemented already
- Lesson: Read vm.c and bytecode.h before assuming gaps

### 2. Simplicity Beats Features
- Multiple numeric types = false flexibility
- Creates choice → creates ambiguity → creates errors
- LLMs want ONE way, not multiple options

### 3. Explicitness > Compactness
- Don't optimize syntax for brevity
- Optimize for clarity and unambiguity
- Token savings should come from caching/binary formats, not shortcuts

### 4. One Way Only is Non-Negotiable
- Backward compatibility is human baggage
- LLMs regenerate, they don't edit legacy code
- Supporting "both ways" violates core principle

---

## Files to Read for Context

### Language Design
- `AGENTS.md` - LLM-focused guide (current state)
- `.aisl.analysis` - Design philosophy and decisions
- `.aisl.grammar` - Ultra-compact language reference
- `.aisl.meta` - Project context in compressed format
- `SIMPLIFICATION-PLAN.md` - Type system redesign plan

### Implementation
- `compiler/c/src/parser.c:728` - Where nested params were removed
- `compiler/c/src/vm.c:3593-3650` - Regex implementation
- `compiler/c/include/bytecode.h:237-241` - Regex opcodes
- `compiler/c/src/compiler.c:2051-2096` - Regex compiler support

### Tests
- `tests/test_*.aisl` - 88 test files (79 need conversion)
- `scripts/convert_syntax.aisl` - Converter (incomplete)

---

## Status: Ready to Proceed

We have:
- ✅ Identified the problems (syntax ambiguity, type ambiguity)
- ✅ Analyzed the solutions (flat params, int/float only)
- ✅ Documented the rationale (.aisl.analysis, SIMPLIFICATION-PLAN.md)
- ✅ Planned the implementation (clear phases)

**Awaiting decision**: Should we proceed with both simplifications?
