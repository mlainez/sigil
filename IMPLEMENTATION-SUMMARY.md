# AISL Two-Layer Architecture - Implementation Summary

**Date**: 2026-02-06  
**Status**: Core Implementation Complete

## What We Built

### 1. ✅ AISL-Core (Frozen IR)
- **6 statements**: `set`, `call`, `label`, `goto`, `ifnot`, `ret`
- **Specification**: `AISL-CORE.md` (frozen)
- **Implementation**: `compiler/c/src/compiler.c:345-457, 2519-2547`
- **Key innovation**: Labels + two-pass compilation with jump patching

### 2. ✅ AISL-Agent (Surface Language)
- **Constructs**: `while`, `loop`, `break`, `continue`
- **Specification**: `AISL-AGENT.md`
- **Implementation**: `compiler/c/src/desugar.c`
- **Process**: Agent AST → Desugar → Core AST → Compile → Bytecode

### 3. ✅ Type-Directed Dispatch (Partial)
- **Short names**: `add`, `sub`, `mul`, `div`, `mod`, `neg`, `lt`, `gt`, `le`, `ge`, `eq`, `ne`, `abs`, `min`, `max`
- **Implementation**: `compiler/c/src/compiler.c:130-175`
- **Status**: Working for arithmetic and comparisons
- **Remaining**: Need to collapse ALL built-ins (see below)

### 4. ✅ Control Flow Legality Rules
- Documented in both AISL-CORE.md and AISL-AGENT.md
- Function-scoped labels
- No cross-function jumps
- Break/continue target nearest enclosing loop

### 5. ✅ Tests
- `tests/test_desugar_while.aisl` - While loop desugaring
- `tests/test_type_dispatch.aisl` - Polymorphic operations
- `tests/test_polymorphic_ops.aisl` - Type-directed dispatch

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│         LLM writes AISL-Agent               │
│  (while, loop, break, continue, add, sub)   │
└────────────────┬────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │  Parser (AST)  │
        └────────┬───────┘
                 │
                 ▼
     ┌──────────────────────┐
     │  Type Checker (AST)  │
     └──────────┬───────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │  Desugarer (Agent→Core)│
    │  - while → label/goto  │
    │  - loop → label/goto   │
    │  - break → goto end    │
    │  - continue → goto start│
    └────────────┬───────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│           AISL-Core (Frozen IR)             │
│   set, call, label, goto, ifnot, ret        │
└────────────────┬────────────────────────────┘
                 │
                 ▼
     ┌──────────────────────┐
     │  Compiler (Core→VM)  │
     │  - Type dispatch     │
     │  - Label resolution  │
     │  - Jump patching     │
     └──────────┬───────────┘
                 │
                 ▼
        ┌───────────────┐
        │   Bytecode    │
        └───────┬───────┘
                 │
                 ▼
          ┌──────────┐
          │    VM    │
          └──────────┘
```

## What Remains (Priority Order)

### 🔥 Priority 1: Collapse Built-in Explosion

**Problem**: We have 200+ built-in functions with typed names:
- `op_add_i32`, `op_add_i64`, `op_add_f32`, `op_add_f64`
- `array_push_i32`, `array_push_i64`, `array_push_string`
- `string_split`, `string_trim`, `string_contains`, ...

**Solution**: Extend type-directed dispatch to ALL built-ins

**Categories to collapse**:

1. **Arithmetic** (✅ DONE)
   - add, sub, mul, div, mod, neg

2. **Comparisons** (✅ DONE)
   - lt, gt, le, ge, eq, ne

3. **Math functions** (✅ DONE)
   - abs, min, max

4. **Array operations** (❌ TODO)
   ```
   array_new     → array_new (type inferred from usage)
   array_push    → push      (dispatch on array element type)
   array_get     → get       (dispatch on array element type)
   array_set     → set       (dispatch on array element type)
   array_len     → len       (polymorphic)
   ```

5. **String operations** (❌ TODO)
   ```
   string_concat   → concat
   string_split    → split
   string_trim     → trim
   string_contains → contains
   string_len      → len (same as array_len!)
   ```

6. **I/O operations** (❌ TODO)
   ```
   io_print_i32    → print   (dispatch on type)
   io_print_string → print
   io_read_line    → read_line
   ```

7. **File operations** (✅ Keep as-is)
   ```
   file_open, file_read, file_write, file_close
   ```
   These are naturally polymorphic already.

### 🔥 Priority 2: Add Result Type

**Implementation plan**:

1. Add to type system:
   ```c
   typedef enum {
       TYPE_RESULT_I32,
       TYPE_RESULT_STRING,
       TYPE_RESULT_ARRAY,
       ...
   } TypeKind;
   ```

2. Add runtime support (VM):
   ```c
   typedef struct {
       bool is_ok;
       union {
           Value ok_value;
           struct {
               i32 code;
               char* message;
           } error;
       } data;
   } ResultValue;
   ```

3. Add built-in operations:
   ```lisp
   (call ok value)           ; Create ok result
   (call err code message)   ; Create error result
   (call is_ok result)       ; Check if ok
   (call is_err result)      ; Check if error
   (call unwrap result)      ; Get value or panic
   (call unwrap_or result default)  ; Get value or default
   ```

4. Usage example:
   ```lisp
   (fn divide ((a i32) (b i32)) -> (result i32)
     (if (call eq b 0)
       (ret (call err 1 "division by zero")))
     (ret (call ok (call div a b))))
   
   (fn safe_divide ((a i32) (b i32)) -> i32
     (set result (result i32) (call divide a b))
     (if (call is_err result)
       (ret 0))
     (ret (call unwrap result)))
   ```

### Priority 3: Update Test Suite

Need to update tests to use polymorphic operations:
- `tests/test_add.aisl` - Use `add` instead of `op_add_i32`
- `tests/test_comparisons.aisl` - Use `lt`, `gt` instead of typed ops
- `tests/test_fibonacci.aisl` - Use polymorphic ops
- 20+ more tests

### Priority 4: Documentation

- [ ] Update README.md with two-layer architecture
- [ ] Add migration guide (old → new syntax)
- [ ] LLM prompting guide for AISL-Agent

## Design Decisions Made

### 1. Core constructs are function calls
**Decision**: `(call label name)` instead of `(label name)`  
**Rationale**: 
- Avoids parser changes
- Treats Core uniformly
- Simpler implementation

**Trade-off**: Slightly more verbose, but only in generated code

### 2. Labels don't emit bytecode
**Decision**: Labels are virtual, mark positions only  
**Rationale**:
- No runtime overhead
- Clean separation: labels = compile-time, jumps = runtime

**Critical fix**: Labels must push unit for stack balance in sequences

### 3. Two-pass compilation
**Decision**: Collect labels, emit placeholders, then patch  
**Rationale**:
- Handles forward jumps elegantly
- Allows arbitrary jump patterns
- Standard compiler technique

**Alternative considered**: Backpatching (rejected - more complex)

### 4. Function-scoped labels
**Decision**: Labels are unique per function, not block-scoped  
**Rationale**:
- Simpler to implement
- Matches how generated labels work
- Core is low-level, scoping is Agent's job

### 5. Flat goto (no restrictions)
**Decision**: Can jump anywhere in same function  
**Rationale**:
- Core is IR, not high-level language
- Agent layer enforces structured control flow
- Maximum flexibility for optimization

## Performance Characteristics

### Desugaring Overhead
- **Zero runtime cost** - desugaring is compile-time only
- Generated Core is equivalent to hand-written Core
- No indirection, no metadata

### Jump Performance
- Direct bytecode jumps (OP_JUMP, OP_JUMP_IF_FALSE)
- No label lookup at runtime
- Comparable to native while/for loops

### Type Dispatch Overhead
- **Zero runtime cost** - resolved at compile time
- `add` → `op_add_i32` happens during compilation
- No type checking at runtime

## Lessons Learned

### 1. Stack discipline matters
**Problem**: Labels didn't push unit → stack corruption  
**Solution**: Every expression in sequence must leave value  
**Takeaway**: IR design requires thinking about abstract machine

### 2. Keywords vs identifiers
**Problem**: `label` as keyword prevented `(call label ...)`  
**Solution**: Remove from lexer, treat as identifier  
**Takeaway**: Minimize keywords in extensible languages

### 3. Forward jumps need two passes
**Problem**: Can't emit jump offset to label not yet seen  
**Solution**: Placeholder + patching  
**Takeaway**: Standard compiler technique for good reason

### 4. Testing at right level
**Problem**: Initially tested without expect statements  
**Solution**: Use test framework with proper assertions  
**Takeaway**: Test infrastructure matters from day one

## Success Metrics

✅ **Minimalism**: Core has exactly 6 statements (cannot be reduced)  
✅ **Stability**: Core is frozen (v1.0)  
✅ **Completeness**: Can express any computation  
✅ **Ergonomics**: Agent layer provides natural syntax  
✅ **Performance**: Zero-cost abstraction  
✅ **Tested**: Desugaring verified to work correctly  

## Next Session Priorities

1. **Collapse built-ins** (half-day)
   - Array operations
   - String operations
   - I/O operations

2. **Add Result type** (half-day)
   - Type system changes
   - VM support
   - Built-in operations
   - Example tests

3. **Update test suite** (few hours)
   - Mass find-replace typed operations
   - Verify all tests pass

4. **Documentation** (few hours)
   - Update README
   - Migration guide
   - LLM usage guide

## Long-term Vision

**AISL as LLM-native agent language**:
- LLMs write natural Agent code
- Zero runtime overhead (compiles to same bytecode)
- Robust error handling (Result type)
- Stable core (frozen IR)
- Extensible surface (new Agent constructs don't break Core)

**Competitive advantages**:
- Smaller than Python/JS (simpler for LLMs)
- Type-safe (catches errors at compile time)
- Fast (compiles to bytecode)
- LLM-optimized (polymorphic ops, natural syntax)
- Stable (frozen core prevents entropy)

## Files Changed This Session

### Created
- `AISL-CORE.md` - Core specification (frozen)
- `AISL-AGENT.md` - Agent specification
- `tests/test_desugar_while.aisl` - Desugaring tests
- `THIS-FILE` - Implementation summary

### Modified
- `compiler/c/src/compiler.c` - Label resolution, type dispatch
- `compiler/c/src/lexer.c` - Removed label/goto/ifnot keywords
- `compiler/c/src/desugar.c` - While/loop/break/continue desugaring
- `compiler/c/Makefile` - Added desugar.c

### Test Results
✅ `tests/test_desugar_while.aisl` - Passes  
✅ `tests/test_type_dispatch.aisl` - Passes  
✅ `tests/test_polymorphic_ops.aisl` - Passes  

## Conclusion

**AISL now has a proper two-layer architecture**. The Core is frozen and minimal. The Agent layer provides ergonomic syntax that desugars to Core. Type-directed dispatch eliminates built-in explosion for arithmetic/comparison operations.

**Remaining work is mechanical**, not architectural:
1. Extend type dispatch to all built-ins
2. Add Result type
3. Update tests
4. Document

The hard design problems are solved. The implementation is clean. The architecture is sound.

**AISL is ready to be an LLM-native agent language.** 🎉
