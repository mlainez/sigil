# AISL-Core Specification v1.0

**Status**: FROZEN  
**Last Updated**: 2026-02-06

## Philosophy

AISL-Core is the **frozen intermediate representation** of the AISL language. It is:
- **Minimal**: Only 6 statement types
- **Stable**: Will not change once frozen
- **Complete**: Can express any computation
- **Low-level**: Direct mapping to interpreter evaluation

AISL-Core is NOT meant for humans to write directly. It is the target for AISL-Agent, which the interpreter handles directly.

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
(set result bool (lt x 100))
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
(add x y)              ; Type-directed: resolves to add_int or add_float
(my_function 10 20)    ; User function
(label loop_start)     ; Core construct
```

### 3. `label` - Jump target marker
```
(label name)
```
- Marks a position in the instruction stream
- Does not emit bytecode (virtual construct)
- Must be unique within function scope
- Returns: unit

Example:
```lisp
(label loop_start)
; ... code ...
(goto loop_start)
```

### 4. `goto` - Unconditional jump
```
(goto target)
```
- Jumps to label `target`
- Target must exist in same function
- Returns: unit (but execution continues at target)

Example:
```lisp
(goto loop_end)
```

### 5. `ifnot` - Conditional jump
```
(ifnot condition target)
```
- Evaluates `condition` (must be bool)
- If condition is **false**, jumps to `target`
- If condition is **true**, continues to next statement
- Returns: unit

Example:
```lisp
(set cond bool (lt n 10))
(ifnot cond loop_end)
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
(ret (add x y))
```

## Types

Core supports these primitive types:
- `int` - 64-bit signed integer
- `float` - 64-bit floating point
- `bool` - Boolean
- `string` - String (heap-allocated)
- `unit` - Unit type (void)

## Type-Directed Dispatch

Built-in operations use **short names** that resolve based on argument types:

| Short Name | Typed Operations |
|------------|------------------|
| `add` | `add_int`, `add_float`, `add_decimal`, `add` |
| `sub` | `sub_int`, `sub_float`, `sub_decimal`, `sub` |
| `mul` | `mul_int`, `mul_float`, `mul_decimal`, `mul` |
| `div` | `div_int`, `div_float`, `div_decimal`, `div` |
| `mod` | `mod_int`, `mod` |
| `neg` | `neg_int`, `neg_float`, `neg_decimal`, `neg` |
| `lt` | `lt_int`, `lt_float`, `lt_decimal`, `lt` |
| `gt` | `gt_int`, `gt_float`, `gt_decimal`, `gt` |
| `le` | `le_int`, `le_float`, `le_decimal`, `le` |
| `ge` | `ge_int`, `ge_float`, `ge_decimal`, `ge` |
| `eq` | `eq_int`, `eq_float`, `eq_decimal`, `eq` |
| `ne` | `ne_int`, `ne_float`, `ne_decimal`, `ne` |
| `abs` | `abs_int`, `abs_float`, `abs_decimal`, `abs` |
| `min` | `min_int`, `min_float`, `min_decimal`, `min` |
| `max` | `max_int`, `max_float`, `max_decimal`, `max` |

The interpreter infers the correct typed operation from argument types at runtime.

## Function Definitions

```lisp
(fn name param1 type1 param2 type2 -> return_type
  body)
```

Example:
```lisp
(fn add_numbers x int y int -> int
  (ret (add x y)))
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
  (label loop_start)
  (set cond bool (lt n 5))
  (ifnot cond loop_end)
  (set n int (add n 1))
  (goto loop_start)
  (label loop_end)
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
- `if/else` conditionals
- `for-each` iteration
- `and`/`or` short-circuit boolean operators
- `match` expressions
- `for` loops

See AISL-AGENT.md for Agent layer specification.

## Implementation

- **Interpreter**: `interpreter/interpreter.ml` — Tree-walking interpreter (~1930 lines)
- **Parser**: `interpreter/parser.ml` — Recursive descent S-expression parser
- **Lexer**: `interpreter/lexer.ml` — Tokenizer
- **AST**: `interpreter/ast.ml` — AST node types
- **Types**: `interpreter/types.ml` — Type kind definitions
- **Entry Point**: `interpreter/vm.ml` — Reads file, tokenizes, parses, executes

The interpreter handles Agent constructs (while, loop, break, continue, if, if-else, for-each, and, or) directly during evaluation — there is no separate desugaring pass or bytecode compilation step.

## Version History

- **v1.0** (2026-02-06): Initial frozen specification
  - 6 core statements: set, call, label, goto, ifnot, ret
  - Type-directed dispatch for built-ins
  - Function-scoped labels with jump patching
