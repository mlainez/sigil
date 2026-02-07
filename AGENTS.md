# AISL for AI Agents: A Complete Guide

**Last Updated**: 2026-02-07  
**Target Audience**: LLMs, AI Agents, Code Generation Systems

---

## What is AISL?

AISL (AI-Optimized Systems Language) is a programming language specifically designed for **code generation by AI systems**. It eliminates the ambiguities and complexities that make traditional languages difficult for LLMs to generate reliably.

### The Core Problem AISL Solves

**Traditional languages are hard for LLMs because:**
- Operator precedence creates ambiguity (is `a + b * c` parsed as `(a + b) * c` or `a + (b * c)`?)
- Implicit conversions hide behavior
- Complex syntax has many equivalent forms
- Control flow nesting requires careful tracking
- Built-in explosion: hundreds of type-specific operations to remember

**AISL fixes this by:**
- Zero operator precedence - all operations are explicit function calls
- No implicit conversions - types are always explicit
- One canonical form for each construct
- Flat, sequential control flow with simple desugaring
- Type-directed dispatch - write `add`, compiler infers `add_i32` vs `add_f64`

---

## Two-Layer Architecture: The Key Innovation

AISL uses a **two-layer design** that prevents entropy over time:

```
┌─────────────────────────────────────────┐
│         AISL-Agent (Surface)            │
│  What LLMs Write: while, loop, break    │
│  Ergonomic, evolves over time           │
└───────────────┬─────────────────────────┘
                │ Desugaring
                ▼
┌─────────────────────────────────────────┐
│          AISL-Core (IR)                 │
│  What VM Runs: set, call, goto, label   │
│  Minimal, frozen forever                │
└─────────────────────────────────────────┘
```

### Why This Matters

- **LLMs write Agent code** - Natural, structured syntax they understand
- **VM runs Core code** - Minimal, stable IR that never changes
- **Desugaring is automatic** - Compiler handles the transformation
- **Core is frozen** - No breaking changes, ever
- **Agent can evolve** - Add new constructs without touching Core

This means:
1. Your LLM training never becomes outdated (Core is stable)
2. New ergonomic features can be added (Agent evolves)
3. Generated code has predictable semantics (desugaring is deterministic)

---

## Quick Reference: What to Generate

### Module Structure

Every AISL program is a module with functions:

```lisp
(mod module_name
  (fn function_name ((param1 type1) (param2 type2)) -> return_type
    statements...)
  
  (fn another_function () -> i32
    statements...))
```

### The 6 Core Statements (What Everything Becomes)

You rarely write these directly - they're what Agent code desugars to:

| Statement | Syntax | Purpose |
|-----------|--------|---------|
| `set` | `(set var type expr)` | Variable binding |
| `call` | `(call func arg1 arg2)` | Function invocation |
| `label` | `(call label name)` | Mark jump target |
| `goto` | `(call goto target)` | Unconditional jump |
| `ifnot` | `(call ifnot bool_var target)` | Jump if false |
| `ret` | `(ret expr)` | Return from function |

### Agent Constructs (What You Should Generate)

Generate these - the compiler desugars them to Core:

```lisp
; While loop - iterate while condition holds
(while (call lt i 10)
  (set i i32 (call add i 1)))

; Infinite loop - for servers
(loop
  (call handle_request))

; Break - exit loop early
(if (call eq val target)
  (break))

; Continue - skip to next iteration
(if (call eq val 0)
  (continue))
```

---

## Type System

### Primitive Types

| Type | Description | Example |
|------|-------------|---------|
| `i32` | 32-bit signed integer | `42` |
| `i64` | 64-bit signed integer | `9223372036854775807` |
| `f32` | 32-bit float | `3.14` |
| `f64` | 64-bit float | `2.718281828` |
| `bool` | Boolean | `true`, `false` |
| `string` | UTF-8 string | `"hello"` |

### Type Annotations

**Every variable must have an explicit type:**

```lisp
(set count i32 0)              ; Integer counter
(set price f64 19.99)          ; Float price
(set name string "Alice")      ; String
(set active bool true)         ; Boolean
```

**No implicit conversions - be explicit:**

```lisp
; ❌ Wrong - mixing types
(set x i32 10)
(set y f64 (call add x 3.14))  ; Type error!

; ✅ Correct - explicit conversion
(set x i32 10)
(set x_f64 f64 (call cast_i32_f64 x))
(set y f64 (call add x_f64 3.14))
```

---

## Operations: Type-Directed Dispatch

**The killer feature for LLMs**: Write generic operation names, compiler infers types.

### Arithmetic

```lisp
(call add x y)     ; Becomes add_i32, add_i64, add_f32, or add_f64
(call sub x y)     ; Subtraction
(call mul x y)     ; Multiplication
(call div x y)     ; Division
(call mod x y)     ; Modulo (integers only)
(call neg x)       ; Negation
```

**You don't need to remember:** `op_add_i32`, `op_add_i64`, `op_add_f32`, `op_add_f64`  
**Just write:** `(call add x y)` and the compiler figures it out from `x`'s type.

### Comparisons

```lisp
(call eq x y)      ; Equal
(call ne x y)      ; Not equal
(call lt x y)      ; Less than
(call gt x y)      ; Greater than
(call le x y)      ; Less or equal
(call ge x y)      ; Greater or equal
```

### Math Functions

```lisp
(call abs x)       ; Absolute value
(call min a b)     ; Minimum
(call max a b)     ; Maximum
(call sqrt x)      ; Square root (f32/f64 only)
(call pow x y)     ; Power (f32/f64 only)
```

### String Operations

```lisp
(call string_length text)              ; Get length -> i32
(call string_concat a b)               ; Concatenate -> string
(call string_contains haystack needle) ; Check contains -> bool
(call string_split text delimiter)     ; Split -> array
(call string_trim text)                ; Remove whitespace -> string
(call string_replace text old new)     ; Replace substring -> string
```

### I/O Operations

```lisp
(call print value)           ; Print (dispatches on type)
(call print_ln value)        ; Print with newline
(call read_line)             ; Read line from stdin -> string
```

### File Operations

```lisp
(call file_read path)        ; Read file -> string
(call file_write path data)  ; Write file
(call file_append path data) ; Append to file
(call file_exists path)      ; Check exists -> bool
(call file_delete path)      ; Delete file
```

---

## Control Flow Patterns

### Pattern 1: While Loop

```lisp
(fn countdown ((n i32)) -> i32
  (while (call gt n 0)
    (call print n)
    (set n i32 (call sub n 1)))
  (ret 0))
```

### Pattern 2: Infinite Loop with Break

```lisp
(fn find_first ((arr string) (target i32)) -> i32
  (set i i32 0)
  (loop
    (set val i32 (call array_get arr i))
    (if (call eq val target)
      (break))
    (set i i32 (call add i 1)))
  (ret i))
```

### Pattern 3: Skip with Continue

```lisp
(fn count_positive ((arr string) (len i32)) -> i32
  (set i i32 0)
  (set count i32 0)
  (while (call lt i len)
    (set val i32 (call array_get arr i))
    (set i i32 (call add i 1))
    (if (call le val 0)
      (continue))
    (set count i32 (call add count 1)))
  (ret count))
```

### Pattern 4: Conditional Logic

```lisp
(fn max ((a i32) (b i32)) -> i32
  (set greater bool (call gt a b))
  (call ifnot greater return_b)
  (ret a)
  (call label return_b)
  (ret b))
```

---

## Common Patterns for LLMs

### Accumulator Pattern

```lisp
(fn sum ((arr string) (n i32)) -> i32
  (set sum i32 0)
  (set i i32 0)
  (while (call lt i n)
    (set val i32 (call array_get arr i))
    (set sum i32 (call add sum val))
    (set i i32 (call add i 1)))
  (ret sum))
```

### Recursive Pattern

```lisp
(fn factorial ((n i32)) -> i32
  (set is_zero bool (call eq n 0))
  (call ifnot is_zero recurse)
  (ret 1)
  (call label recurse)
  (set n_minus_1 i32 (call sub n 1))
  (set result i32 (call factorial n_minus_1))
  (ret (call mul n result)))
```

### Search Pattern

```lisp
(fn find ((arr string) (target i32) (len i32)) -> i32
  (set i i32 0)
  (while (call lt i len)
    (set val i32 (call array_get arr i))
    (if (call eq val target)
      (ret i))
    (set i i32 (call add i 1)))
  (ret -1))  ; Not found
```

### Filter Pattern

```lisp
(fn filter_evens ((arr string) (len i32)) -> string
  (set result string (call array_new))
  (set i i32 0)
  (while (call lt i len)
    (set val i32 (call array_get arr i))
    (set remainder i32 (call mod val 2))
    (set is_even bool (call eq remainder 0))
    (if is_even
      (call array_push result val))
    (set i i32 (call add i 1)))
  (ret result))
```

---

## Testing Your Generated Code

AISL has a built-in test framework. Add tests to verify behavior:

```lisp
(mod my_module
  (fn add_numbers ((x i32) (y i32)) -> i32
    (ret (call add x y)))
  
  (test-spec add_numbers
    (case "adds two positive numbers"
      (input 5 3)
      (expect 8))
    (case "adds negative numbers"
      (input -5 -3)
      (expect -8))))
```

---

## Where to Look for Information

### Core Documentation

| File | Purpose | Read When |
|------|---------|-----------|
| **AGENTS.md** | This file - LLM quick reference | Generating AISL code |
| **AISL-CORE.md** | Frozen IR specification | Understanding internals |
| **AISL-AGENT.md** | Surface language spec | Learning Agent constructs |
| **LANGUAGE_SPEC.md** | Complete language reference | Full syntax and stdlib |
| **README.md** | Project overview | First time here |

### Implementation Reference

| Path | Purpose |
|------|---------|
| `compiler/c/src/compiler.c` | Core statement compilation |
| `compiler/c/src/desugar.c` | Agent → Core transformation |
| `compiler/c/src/parser.c` | Syntax parsing |
| `compiler/c/include/bytecode.h` | Bytecode operations |
| `tests/` | 81+ test files with examples |
| `examples/` | Complete working programs |

### Quick Lookups

- **Syntax questions**: See LANGUAGE_SPEC.md sections 1-3
- **Control flow**: See AISL-AGENT.md examples
- **Built-in functions**: See LANGUAGE_SPEC.md section 5 (180+ functions)
- **Type system**: See AISL-CORE.md section "Types"
- **Error handling**: Currently limited - file operations may panic

---

## Common Pitfalls for LLMs

### ❌ Don't: Mix types implicitly

```lisp
(set x i32 10)
(set y f64 (call add x 3.14))  ; ERROR: i32 + f64
```

### ✅ Do: Convert explicitly

```lisp
(set x i32 10)
(set x_float f64 (call cast_i32_f64 x))
(set y f64 (call add x_float 3.14))
```

### ❌ Don't: Use infix operators

```lisp
(set sum i32 (x + y))  ; ERROR: Not valid syntax
```

### ✅ Do: Use function calls

```lisp
(set sum i32 (call add x y))
```

### ❌ Don't: Forget type annotations

```lisp
(set count 0)  ; ERROR: Missing type
```

### ✅ Do: Always specify types

```lisp
(set count i32 0)
```

### ❌ Don't: Use break/continue outside loops

```lisp
(fn example () -> i32
  (break)  ; ERROR: Not in a loop
  (ret 0))
```

### ✅ Do: Only use break/continue inside while/loop

```lisp
(fn example () -> i32
  (loop
    (break))  ; OK: Inside loop
  (ret 0))
```

### ❌ Don't: Write Core IR directly (usually)

```lisp
(fn example () -> i32
  (call label loop_start)
  (call goto loop_start)  ; Tedious, error-prone
  (ret 0))
```

### ✅ Do: Use Agent constructs

```lisp
(fn example () -> i32
  (loop
    (call do_something))  ; Desugars automatically
  (ret 0))
```

---

## Performance Characteristics

AISL is designed for predictable performance:

- **Zero runtime dispatch**: Type dispatch happens at compile time
- **No GC pauses**: Manual memory management (strings are ref-counted)
- **Predictable jumps**: All control flow compiles to simple jumps
- **Flat bytecode**: No complex stack frames, direct instruction execution
- **Fast compilation**: Single-pass compilation with simple desugaring

---

## Current Limitations (as of 2026-02-07)

### Not Yet Implemented

1. **Result/Option types**: Documented in LANGUAGE_SPEC.md but not yet implemented
   - `file_read_result`, `is_ok`, `unwrap` etc. are placeholders
   - Current file operations panic on error instead of returning results
   - **Workaround**: Check `file_exists` before reading

2. **Struct/Record types**: Planned but not implemented
   - Use multiple variables or arrays for now

3. **Generics**: Not planned - use type-directed dispatch instead

### Design Decisions

- **No exceptions**: Use explicit error checking
- **No null**: Variables must be initialized
- **No undefined behavior**: All operations have defined semantics
- **No operator overloading**: One operation name = one meaning

---

## Example: Complete Web Server

```lisp
(mod web_server
  (fn handle_request ((client_socket string)) -> i32
    (set request string (call tcp_receive client_socket 4096))
    (set response string "HTTP/1.1 200 OK\r\n\r\nHello, World!")
    (call tcp_send client_socket response)
    (call tcp_close client_socket)
    (ret 0))
  
  (fn main () -> i32
    (set port i32 8080)
    (set server_socket string (call tcp_listen port))
    (call print "Server listening on port 8080")
    (loop
      (set client_socket string (call tcp_accept server_socket))
      (call handle_request client_socket))
    (ret 0)))
```

---

## Summary: AISL in 10 Points

1. **Two layers**: Agent (what you write) desugars to Core (what runs)
2. **Explicit everything**: Types, calls, control flow - no hidden behavior
3. **Type dispatch**: Write `add`, compiler picks `add_i32` or `add_f64`
4. **S-expressions**: Uniform syntax, easy to parse and generate
5. **Structured control**: `while`, `loop`, `break`, `continue` desugar to jumps
6. **No precedence**: All operations are function calls
7. **Deterministic**: Same input = same output, always
8. **Flat structure**: Sequential statements, minimal nesting
9. **Test framework**: Built-in testing with `test-spec`
10. **LLM-first**: Designed for reliable code generation by AI

---

## Support and Community

- **Repository**: [Link to be added]
- **Documentation**: This directory (`*.md` files)
- **Examples**: `examples/` directory (working programs)
- **Tests**: `tests/` directory (81 test files)
- **Issues**: [Link to be added]

---

**AISL - Designed for AI, Built for Everyone.**

*For detailed technical specifications, see AISL-CORE.md and AISL-AGENT.md.*
