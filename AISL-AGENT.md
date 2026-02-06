# AISL-Agent Specification v1.0

**Status**: STABLE  
**Last Updated**: 2026-02-06

## Philosophy

AISL-Agent is the **ergonomic surface language** for writing AISL programs. It is:
- **High-level**: Structured control flow (while, loop, break, continue)
- **LLM-friendly**: Natural syntax that LLMs understand
- **Desugared**: All Agent constructs compile to AISL-Core
- **Extensible**: Can add new constructs without changing Core

AISL-Agent is what LLMs should write. It desugars to AISL-Core during compilation.

## Agent Constructs

### 1. `while` - Conditional loop
```lisp
(while condition body)
```

Desugars to:
```lisp
(call label loop_start_N)
(set _cond_N bool condition)
(call ifnot _cond_N loop_end_N)
body
(call goto loop_start_N)
(call label loop_end_N)
```

Example:
```lisp
(fn count_to_ten () -> i32
  (set n i32 0)
  (while (call lt n 10)
    (set n i32 (call add n 1)))
  (ret n))
```

### 2. `loop` - Infinite loop
```lisp
(loop body)
```

Desugars to:
```lisp
(call label loop_start_N)
body
(call goto loop_start_N)
(call label loop_end_N)  ; For break statements
```

Example:
```lisp
(fn infinite_server () -> unit
  (loop
    (call handle_request)
    (call sleep 1000)))
```

### 3. `break` - Exit loop
```lisp
(break)
```

Desugars to:
```lisp
(call goto loop_end_N)  ; Where N is the enclosing loop
```

Must be inside a `while` or `loop`.

Example:
```lisp
(fn find_first_match ((arr Array) (target i32)) -> i32
  (set i i32 0)
  (loop
    (set val i32 (call array_get arr i))
    (if (call eq val target)
      (break))
    (set i i32 (call add i 1)))
  (ret i))
```

### 4. `continue` - Skip to next iteration
```lisp
(continue)
```

Desugars to:
```lisp
(call goto loop_start_N)  ; Where N is the enclosing loop
```

Must be inside a `while` or `loop`.

Example:
```lisp
(fn sum_evens ((arr Array)) -> i32
  (set sum i32 0)
  (set i i32 0)
  (while (call lt i (call array_len arr))
    (set val i32 (call array_get arr i))
    (if (call ne (call mod val 2) 0)
      (continue))
    (set sum i32 (call add sum val))
    (set i i32 (call add i 1)))
  (ret sum))
```

### 5. `if` - Conditional expression (FUTURE)
```lisp
(if condition then_expr else_expr)
```

Currently implemented via desugaring to ifnot+labels.
Future: Native expression form.

## Desugaring Process

The AISL compiler performs desugaring in these phases:

1. **Parse** - Parse Agent syntax into AST
2. **Type Check** - Verify types (operates on Agent AST)
3. **Desugar** - Transform Agent AST → Core AST
   - `while` → `label`/`goto`/`ifnot`
   - `loop` → `label`/`goto`
   - `break` → `goto loop_end`
   - `continue` → `goto loop_start`
4. **Compile** - Compile Core AST → Bytecode

### Desugaring Implementation

Location: `compiler/c/src/desugar.c`

Key functions:
- `desugar_module()` - Entry point
- `desugar_while()` - While loop transformation
- `desugar_loop()` - Infinite loop transformation
- `desugar_break()` - Break statement transformation
- `desugar_continue()` - Continue statement transformation

### Loop Context Tracking

The desugarer maintains a loop context stack to track:
- `start_label` - Label to jump to for continue
- `end_label` - Label to jump to for break
- `parent` - Enclosing loop (for nested loops)

This ensures `break` and `continue` jump to the correct loop.

## Nesting Rules

### Loops can nest
```lisp
(while outer_condition
  (while inner_condition
    (if something
      (break))  ; Breaks inner loop only
    ...))
```

### Break/Continue target nearest enclosing loop
```lisp
(while outer_condition
  (set x i32 0)
  (while inner_condition
    (continue))  ; Continues inner loop
  (break))       ; Breaks outer loop
```

## LLM Usage Guidelines

### ✅ DO write Agent code
```lisp
(fn factorial ((n i32)) -> i32
  (set result i32 1)
  (set i i32 1)
  (while (call le i n)
    (set result i32 (call mul result i))
    (set i i32 (call add i 1)))
  (ret result))
```

### ❌ DON'T write Core IR directly
```lisp
; Don't do this - let desugarer handle it
(fn factorial ((n i32)) -> i32
  (set result i32 1)
  (set i i32 1)
  (call label loop_start_0)
  (set _cond_0 bool (call le i n))
  (call ifnot _cond_0 loop_end_0)
  ...)
```

## Polymorphic Operations

Agent code uses **short names** for operations:

```lisp
; Agent code (what LLMs write)
(call add x y)      ; Instead of op_add_i32
(call lt a b)       ; Instead of op_lt_i32
(call mul x 2)      ; Instead of op_mul_i32
```

The compiler resolves these to typed operations based on argument types.

See AISL-CORE.md for full list of polymorphic operations.

## Control Flow Legality

### Allowed
- ✅ Forward jumps (goto label ahead)
- ✅ Backward jumps (loops)
- ✅ Jumping out of nested blocks
- ✅ Jumping into nested blocks (via goto)
- ✅ Break from any loop depth
- ✅ Continue from any loop depth

### Forbidden
- ❌ Cross-function jumps
- ❌ Break outside any loop
- ❌ Continue outside any loop
- ❌ Duplicate labels in same function

## Examples

### Fibonacci
```lisp
(fn fibonacci ((n i32)) -> i32
  (if (call le n 1)
    (ret n))
  (set a i32 0)
  (set b i32 1)
  (set i i32 2)
  (while (call le i n)
    (set temp i32 b)
    (set b i32 (call add a b))
    (set a i32 temp)
    (set i i32 (call add i 1)))
  (ret b))
```

### Find in array
```lisp
(fn find ((arr Array) (target i32)) -> i32
  (set i i32 0)
  (while (call lt i (call array_len arr))
    (set val i32 (call array_get arr i))
    (if (call eq val target)
      (ret i))
    (set i i32 (call add i 1)))
  (ret -1))
```

### Break example
```lisp
(fn first_negative ((arr Array)) -> i32
  (set i i32 0)
  (loop
    (if (call ge i (call array_len arr))
      (break))
    (set val i32 (call array_get arr i))
    (if (call lt val 0)
      (ret val))
    (set i i32 (call add i 1)))
  (ret 0))
```

## Testing

Agent constructs should be tested via the test framework:

```lisp
(mod test_while
  (fn count_to_n ((n i32)) -> i32
    (set i i32 0)
    (while (call lt i n)
      (set i i32 (call add i 1)))
    (ret i))
  
  (test-spec count_to_n
    (case "count to 5"
      (input 5)
      (expect 5))
    (case "count to 10"
      (input 10)
      (expect 10))))
```

## Future Extensions

Potential Agent constructs to add:
- `for` loops with ranges
- `match` expressions (pattern matching)
- `defer` statements
- List comprehensions
- Error propagation (`?` operator)

All future extensions will desugar to Core - Core remains frozen.

## Implementation Status

| Construct | Status | File |
|-----------|--------|------|
| `while` | ✅ Implemented | desugar.c:104-171 |
| `loop` | ✅ Implemented | desugar.c:173-217 |
| `break` | ✅ Implemented | desugar.c:219-226 |
| `continue` | ✅ Implemented | desugar.c:228-235 |
| `if/else` | ⚠️ Partial | Needs expression form |

## Version History

- **v1.0** (2026-02-06): Initial specification
  - while, loop, break, continue
  - Desugaring to Core
  - Polymorphic operation dispatch
