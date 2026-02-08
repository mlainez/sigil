# AISL-Core Specification v1.0

**Status**: FROZEN  
**Last Updated**: 2026-02-06

## Philosophy

AISL-Core is the **frozen intermediate representation** of the AISL language. It is:
- **Minimal**: Only 6 statement types
- **Stable**: Will not change once frozen
- **Complete**: Can express any computation
- **Low-level**: Direct mapping to bytecode

AISL-Core is NOT meant for humans to write directly. It is the compilation target for AISL-Agent.

## Core Statements (FROZEN)

### 1. `set` - Variable binding
```
(set var type expr)
```
- Binds `expr` result to `var` with explicit `type`
- Creates variable if it doesn't exist
- Updates variable if it exists
- Returns: unit

Example:
```lisp
(set x int 42)
(set result bool (call lt x 100))
```

### 2. `call` - Function invocation
```
(call func arg1 arg2 ...)
```
- Invokes function `func` with arguments
- Functions can be:
  - User-defined functions
  - Built-in operations (resolved via type-directed dispatch)
  - Core constructs (label, goto, ifnot)
- Returns: function result

Examples:
```lisp
(call add x y)              ; Type-directed: resolves to add or add
(call my_function 10 20)    ; User function
(call label loop_start)     ; Core construct
```

### 3. `label` - Jump target marker
```
(call label name)
```
- Marks a position in the instruction stream
- Does not emit bytecode (virtual construct)
- Must be unique within function scope
- Returns: unit

Example:
```lisp
(call label loop_start)
; ... code ...
(call goto loop_start)
```

### 4. `goto` - Unconditional jump
```
(call goto target)
```
- Jumps to label `target`
- Target must exist in same function
- Returns: unit (but execution continues at target)

Example:
```lisp
(call goto loop_end)
```

### 5. `ifnot` - Conditional jump
```
(call ifnot condition target)
```
- Evaluates `condition` (must be bool)
- If condition is **false**, jumps to `target`
- If condition is **true**, continues to next statement
- Returns: unit

Example:
```lisp
(set cond bool (call lt n 10))
(call ifnot cond loop_end)
```

### 6. `ret` - Return from function
```
(ret expr)
```
- Evaluates `expr` and returns from current function
- Must match function return type
- Terminates function execution

Example:
```lisp
(ret (call add x y))
```

## Types

Core supports these primitive types:
- `int` - 32-bit signed integer
- `int` - 64-bit signed integer  
- `float` - 32-bit float
- `float` - 64-bit float
- `bool` - Boolean
- `string` - String (heap-allocated)
- `unit` - Unit type (void)

## Type-Directed Dispatch

Built-in operations use **short names** that resolve based on argument types:

| Short Name | Typed Operations |
|------------|------------------|
| `add` | `add`, `add`, `add`, `add` |
| `sub` | `sub`, `sub`, `sub`, `sub` |
| `mul` | `mul`, `mul`, `mul`, `mul` |
| `div` | `div`, `div`, `div`, `div` |
| `mod` | `mod`, `mod` |
| `neg` | `neg`, `neg`, `neg`, `neg` |
| `lt` | `lt`, `lt`, `lt`, `lt` |
| `gt` | `gt`, `gt`, `gt`, `gt` |
| `le` | `le`, `le`, `le`, `le` |
| `ge` | `ge`, `ge`, `ge`, `ge` |
| `eq` | `eq`, `eq`, `eq`, `eq` |
| `ne` | `ne`, `ne`, `ne`, `ne` |
| `abs` | `abs`, `abs`, `abs`, `abs` |
| `min` | `min`, `min`, `min`, `min` |
| `max` | `max`, `max`, `max`, `max` |

The compiler infers the correct typed operation from argument types at compile time.

## Function Definitions

```lisp
(fn name param1 type1 param2 type2 -> return_type
  body)
```

Example:
```lisp
(fn add_numbers x int y int -> int
  (ret (call add x y)))
```

## Module Structure

```lisp
(module module_name
  (fn function1 ...)
  (fn function2 ...)
  ...)
```

## Control Flow Rules

1. **Labels** are function-scoped
   - Must be unique within a function
   - Cannot be referenced outside their function

2. **Jumps** must target labels in the same function
   - Forward jumps are allowed
   - Backward jumps are allowed (loops)
   - Cross-function jumps are forbidden

3. **Label scope** is flat
   - Labels are not block-scoped
   - Any goto can jump to any label in the same function
   - This includes jumping into/out of conceptual "loops"

4. **Stack discipline**
   - All statements in sequences must leave stack in consistent state
   - label/goto/ifnot push unit for stack balance
   - Compiler handles stack management

## Examples

### Simple loop (Core IR)
```lisp
(fn count_to_five () -> int
  (set n int 0)
  (call label loop_start)
  (set cond bool (call lt n 5))
  (call ifnot cond loop_end)
  (set n int (call add n 1))
  (call goto loop_start)
  (call label loop_end)
  (ret n))
```

### Conditional (Core IR)
```lisp
(fn max ((a int) (b int)) -> int
  (set cond bool (call gt a b))
  (call ifnot cond else_branch)
  (ret a)
  (call label else_branch)
  (ret b))
```

## What's NOT in Core

These constructs are **AISL-Agent** features that desugar to Core:
- `while` loops
- `loop` (infinite loops)
- `break` statements
- `continue` statements
- `if/else` expressions
- `match` expressions
- `for` loops

See AISL-AGENT.md for Agent layer specification.

## Implementation

- **Compiler**: `compiler/c/src/compiler.c`
- **Desugarer**: `compiler/c/src/desugar.c` (Agent → Core)
- **Bytecode**: `compiler/c/include/bytecode.h`

## Version History

- **v1.0** (2026-02-06): Initial frozen specification
  - 6 core statements: set, call, label, goto, ifnot, ret
  - Type-directed dispatch for built-ins
  - Function-scoped labels with jump patching
