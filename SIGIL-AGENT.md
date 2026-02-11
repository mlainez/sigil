# Sigil-Agent Specification v1.0

**Status**: STABLE  
**Last Updated**: 2026-02-11

## Philosophy

Sigil-Agent is the **ergonomic surface language** for writing Sigil programs. It is:
- **High-level**: Structured control flow (while, loop, break, continue, if-else, cond, for-each)
- **LLM-friendly**: Natural syntax that LLMs understand
- **Directly evaluated**: The interpreter handles Agent constructs natively during evaluation
- **Extensible**: Can add new constructs without changing Core

Sigil-Agent is what LLMs should write. The interpreter handles Agent constructs directly during evaluation.

## Agent Constructs

### 1. `while` - Conditional loop
```lisp
(while condition body...)
```

Semantically equivalent to:
```lisp
(label loop_start_N)
(set _cond_N bool condition)
(ifnot _cond_N loop_end_N)
body...
(goto loop_start_N)
(label loop_end_N)
```

Example:
```lisp
(fn count_to_ten -> int
  (set n int 0)
  (while (lt n 10)
    (set n int (add n 1)))
  (ret n))
```

### 2. `loop` - Infinite loop
```lisp
(loop body...)
```

Semantically equivalent to:
```lisp
(label loop_start_N)
body...
(goto loop_start_N)
(label loop_end_N)
```

Example:
```lisp
(fn infinite_server -> int
  (loop
    (handle_request))
  (ret 0))
```

### 3. `break` - Exit loop
```lisp
(break)
```

Semantically equivalent to:
```lisp
(goto loop_end_N)
```

Must be inside a `while` or `loop`.

Example:
```lisp
(fn find_first_match arr array target int -> int
  (set i int 0)
  (loop
    (set val int (array_get arr i))
    (if (eq val target)
      (break))
    (set i int (add i 1)))
  (ret i))
```

### 4. `continue` - Skip to next iteration
```lisp
(continue)
```

Semantically equivalent to:
```lisp
(goto loop_start_N)
```

Must be inside a `while` or `loop`.

Example:
```lisp
(fn sum_evens arr array -> int
  (set sum int 0)
  (set i int 0)
  (while (lt i (array_length arr))
    (set val int (array_get arr i))
    (set i int (add i 1))
    (if (ne (mod val 2) 0)
      (continue))
    (set sum int (add sum val)))
  (ret sum))
```

### 5. `if` / `if-else` - Conditional execution
```lisp
(if condition then-statements...)
(if condition then-statements... (else else-statements...))
```

Fully implemented. Supports optional `(else ...)` block as the last element.

Example:
```lisp
(fn classify n int -> string
  (set result string "zero")
  (if (gt n 0)
    (set result string "positive")
    (else
      (if (lt n 0)
        (set result string "negative"))))
  (ret result))
```

### 6. `cond` - Flat multi-branch conditional
```lisp
(cond
  (condition1 statements...)
  (condition2 statements...)
  (true statements...))
```

Evaluates conditions top-to-bottom, executes the first matching branch. Use `true` as the last condition for a default branch.

Example:
```lisp
(fn grade score int -> string
  (set result string "F")
  (cond
    ((ge score 90) (set result string "A"))
    ((ge score 80) (set result string "B"))
    ((ge score 70) (set result string "C"))
    ((ge score 60) (set result string "D"))
    (true (set result string "F")))
  (ret result))
```

### 7. `for-each` - Collection iteration
```lisp
(for-each var type collection statements...)
```

Iterates over array elements or map keys.

Example:
```lisp
(fn sum_array arr array -> int
  (set total int 0)
  (for-each val int arr
    (set total int (add total val)))
  (ret total))
```

### 8. `and` / `or` - Short-circuit boolean operators
```lisp
(and expr1 expr2)
(or expr1 expr2)
```

Special forms (not function calls). The second expression is not evaluated if the result is determined by the first.

Example:
```lisp
(if (and (ne b 0) (gt (div a b) threshold))
  (print "above threshold"))
```

### 9. `try` / `catch` - Error handling
```lisp
(try
  body-statements...
  (catch var string
    handler-statements...))
```

Catches `RuntimeError` exceptions. The error message is bound to the catch variable as a string.

Example:
```lisp
(try
  (set result int (div 10 0))
  (catch err string
    (print "Caught: ")
    (print err)))
```

## Interpreter Implementation

Location: `interpreter/interpreter.ml`

The interpreter evaluates Agent constructs in `eval_block` and `eval`:
- `while` expressions re-evaluate their condition each iteration
- `loop` expressions run forever until `break` is raised
- `break`/`continue` use OCaml exceptions to unwind to the enclosing loop
- `if`/`if-else` evaluates the condition and executes the appropriate branch
- `cond` evaluates conditions in order, executes the first matching branch
- `for-each` iterates over array elements or map keys
- `and`/`or` short-circuit evaluation
- `try`/`catch` wraps evaluation in OCaml try/with

### Loop Context Tracking

The interpreter maintains loop context via OCaml exception handling:
- `Break` exception — caught by the enclosing `while` or `loop`
- `Continue` exception — caught by the enclosing `while` or `loop`
- Nested loops work correctly because each loop handler catches exceptions from its own body only

## Nesting Rules

### Loops can nest
```lisp
(while outer_condition
  (while inner_condition
    (if something
      (break))
    ...))
```

### Break/Continue target nearest enclosing loop
```lisp
(while outer_condition
  (set x int 0)
  (while inner_condition
    (continue))
  (break))
```

## LLM Usage Guidelines

### DO write Agent code
```lisp
(fn factorial n int -> int
  (set result int 1)
  (set i int 1)
  (while (le i n)
    (set result int (mul result i))
    (set i int (add i 1)))
  (ret result))
```

### DON'T write Core IR directly
```lisp
(fn factorial n int -> int
  (set result int 1)
  (set i int 1)
  (label loop_start_0)
  (set _cond_0 bool (le i n))
  (ifnot _cond_0 loop_end_0)
  ...)
```

## Polymorphic Operations

Agent code uses **short names** for operations. The interpreter resolves these to typed operations based on argument types:

```lisp
(add x y)      ; Interpreter infers add_int, add_float, or add_decimal
(lt a b)       ; Interpreter infers lt_int, lt_float, or lt_decimal
(mul x 2)      ; Interpreter infers mul_int, mul_float, or mul_decimal
```

See SIGIL-CORE.md for full list of polymorphic operations.

## Control Flow Legality

### Allowed
- Forward jumps (goto label ahead)
- Backward jumps (loops)
- Jumping out of nested blocks
- Break from any loop depth
- Continue from any loop depth

### Forbidden
- Cross-function jumps
- Break outside any loop
- Continue outside any loop
- Duplicate labels in same function

## Examples

### Fibonacci
```lisp
(fn fibonacci n int -> int
  (if (le n 1)
    (ret n))
  (set a int 0)
  (set b int 1)
  (set i int 2)
  (while (le i n)
    (set temp int b)
    (set b int (add a b))
    (set a int temp)
    (set i int (add i 1)))
  (ret b))
```

### Find in array
```lisp
(fn find arr array target int -> int
  (set i int 0)
  (while (lt i (array_length arr))
    (set val int (array_get arr i))
    (if (eq val target)
      (ret i))
    (set i int (add i 1)))
  (ret -1))
```

### Break example
```lisp
(fn first_negative arr array -> int
  (set i int 0)
  (loop
    (if (ge i (array_length arr))
      (break))
    (set val int (array_get arr i))
    (if (lt val 0)
      (ret val))
    (set i int (add i 1)))
  (ret 0))
```

## Testing

Agent constructs should be tested via the test framework:

```lisp
(module test_while
  (fn count_to_n n int -> int
    (set i int 0)
    (while (lt i n)
      (set i int (add i 1)))
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

All future extensions will be evaluated directly by the interpreter — Core remains frozen.

## Implementation Status

| Construct | Status | Location |
|-----------|--------|----------|
| `while` | Implemented | interpreter.ml — eval/eval_block |
| `loop` | Implemented | interpreter.ml — eval/eval_block |
| `break` | Implemented | interpreter.ml — Break exception |
| `continue` | Implemented | interpreter.ml — Continue exception |
| `if/else` | Implemented | interpreter.ml — eval/eval_block |
| `cond` | Implemented | interpreter.ml — eval/eval_block |
| `for-each` | Implemented | interpreter.ml — eval/eval_block |
| `and/or` | Implemented | interpreter.ml — eval (short-circuit) |
| `try/catch` | Implemented | interpreter.ml — eval/eval_block |

## Version History

- **v1.0** (2026-02-06): Initial specification
  - while, loop, break, continue
  - Desugaring to Core
  - Polymorphic operation dispatch
- **v1.1** (2026-02-11): Updated to match implementation
  - Fixed all examples to use correct syntax (no `(call ...)`, flat params, lowercase types)
  - Documented if-else, cond, for-each, and/or, try/catch
  - Updated implementation status table
