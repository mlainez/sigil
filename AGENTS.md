# AISL for AI Agents: A Complete Guide

**Target Audience**: LLMs, AI Agents, Code Generation Systems

---

## ⚡ FOR LLMs: OPTIMIZED FORMATS AVAILABLE

**⚠️ IMPORTANT: Always consult machine-readable formats FIRST**

**This document is human-readable prose with examples.**  
**For token-optimized LLM consumption, use these instead:**

- **`.aisl.grammar`** - Complete language reference in 196 lines (~1600 tokens) - **CONSULT FIRST**
- **`.aisl.analysis`** - Deep architectural analysis + runtime discoveries

**Token efficiency:**
- This file: ~700 lines = ~8,000 tokens
- `.aisl.grammar`: ~196 lines = ~1,600 tokens
- **5x more efficient for context loading**

**Consultation order for AI agents:**
1. **FIRST**: `.aisl.grammar` - syntax, operations, critical notes
2. **SECOND**: `.aisl.analysis` - design decisions, discovered issues
3. **LAST**: This file (AGENTS.md) - only if you need detailed examples

**When to use each:**
- **Generating AISL code**: Load `.aisl.grammar` ONLY
- **Fixing bugs/issues**: Check `.aisl.analysis` for known issues
- **Learning AISL deeply**: Read this file (AGENTS.md)
- **Understanding design**: Read `.aisl.analysis`

**Critical rule**: Machine-readable formats are the source of truth. Markdown is for human reference only.

---

## 🚨 CRITICAL: NO COMMENTS IN AISL CODE

**AISL DOES NOT SUPPORT COMMENTS.** Do not use `;`, `//`, `#`, or any other comment syntax.

If you need to document code:
- Use the `meta-note` construct in test specs
- Use descriptive variable names
- Write separate documentation files

**This is the #1 cause of parse errors when generating AISL code.**

---

## 🚨 CRITICAL: ALWAYS USE AISL FOR TOOLING

**ALL utility scripts, converters, and tools MUST be written in pure AISL.**

**NEVER use Python, Bash, or any other language for AISL-related scripts.**

Why this matters:
- Eating our own dog food - discovers language limitations immediately
- Scripts become working examples for LLMs to learn from
- No external dependencies (Python, npm, etc.)
- Forces AISL to be complete and self-sufficient
- If AISL lacks a feature, ADD IT instead of working around it

Process:
1. Check if AISL has needed operations (it probably does!)
2. If truly missing, extend AISL (add to VM/runtime/stdlib)
3. Write script in pure AISL
4. If you wrote Python/Bash, DELETE IT and rewrite in AISL

Examples:
```lisp
; ✅ CORRECT - Pure AISL converter script
(module convert_syntax
  (fn convert_file path string -> int
    (set content string (file_read path))
    (set converted string (regex_replace pattern content))
    (file_write path converted)
    (ret 0)))

; ❌ WRONG - Python fallback
# def convert_file(path):
#     with open(path) as f:
#         ...
```

**If you catch yourself reaching for Python, STOP and use AISL.**

---

## 🚨 CRITICAL: ALL TEST FILES MUST USE THE TEST FRAMEWORK

**ALL files in the `tests/` directory with names matching `test_*.aisl` MUST use the test framework.**

Every test file must include:
- `test-spec` declarations with `case`, `input`, and `expect`
- Functions that return verifiable values (not just print statements)
- `meta-note` at the end to document what the test validates

**Example structure:**
```lisp
(module test_example
  (fn add_numbers a int b int -> int
    (ret (add a b)))
  
  (test-spec add_numbers
    (case "adds positive numbers"
      (input 2 3)
      (expect 5))
    (case "adds negative numbers"
      (input -5 -3)
      (expect -8)))
  
  (meta-note "Tests addition with positive and negative integers"))
```

**DO NOT create test files that:**
- Only print output without assertions
- Return 0 unconditionally
- Lack `test-spec` declarations

---

## 🚨 CRITICAL: ALWAYS UPDATE DOCUMENTATION WHEN FINDING INCONSISTENCIES

**When you discover bugs, inconsistencies, or undocumented behavior, UPDATE DOCS IMMEDIATELY.**

Documentation update order:
1. **FIRST**: Update `.aisl.grammar` - add critical notes in `@(note ...)` section
2. **SECOND**: Update `.aisl.analysis` - document the discovery with `@(tag-name)` section
3. **THIRD**: Update `AGENTS.md` (this file) - if LLMs need to know to avoid errors
4. **LAST**: Update other markdown files if humans need it

Examples of what requires immediate documentation:
- ✅ Found syntax that compiles but doesn't work → Document as "NOT IMPLEMENTED"
- ✅ Found reserved keywords causing crashes → Add to critical notes
- ✅ Found non-obvious pattern needed for common tasks → Add example
- ✅ Found misleading docs that don't match reality → Fix immediately

Process when discovering inconsistency:
1. Verify the actual behavior (test it)
2. Update machine-readable formats (`.aisl.grammar`, `.aisl.analysis`)
3. Update human docs (AGENTS.md, LANGUAGE_SPEC.md)
4. Add test case if it's a bug
5. Fix the bug if possible, or document workaround

**NEVER leave documentation out of sync with reality.** Misleading docs are worse than no docs.

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
- Type-directed dispatch - write `add`, interpreter infers the correct typed operation

---

## Two-Layer Architecture: The Key Innovation

AISL uses a **two-layer design** that prevents entropy over time:

```
┌─────────────────────────────────────────┐
│         AISL-Agent (Surface)            │
│  What LLMs Write: while, loop, break    │
│  Ergonomic, evolves over time           │
└───────────────┬─────────────────────────┘
                │ Interpretation
                ▼
┌─────────────────────────────────────────┐
│          AISL-Core (IR)                 │
│  What Runs: set, call, goto, label      │
│  Minimal, frozen forever                │
└─────────────────────────────────────────┘
```

### Why This Matters

- **LLMs write Agent code** - Natural, structured syntax they understand
- **Interpreter runs Core code** - Minimal, stable IR that never changes
- **Desugaring is automatic** - Interpreter handles Agent constructs directly
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
(module module_name
  (fn function_name param1 type1 param2 type2 -> return_type
    statements...)
  
  (fn another_function -> int
    statements...))
```

### Entry Point

**Every AISL program must have a `main` function as its entry point:**

```lisp
(module my_program
  (fn main -> int
    (print "Hello, AISL!")
    (ret 0)))
```

**Requirements:**
- Function name must be exactly `main` (not `main_func` or anything else)
- Must return `int` (exit code: 0 = success, non-zero = error)
- Takes no parameters (or use flat parameter syntax if needed)
- VM will error if `main` function is not found

**Note**: Test files using `test-spec` framework don't need a `main` function - the test runner provides its own entry point.

### The 6 Core Statements (What Everything Becomes)

You rarely write these directly - they're what Agent code desugars to:

| Statement | Syntax | Purpose |
|-----------|--------|---------|
| `set` | `(set var type expr)` | Variable binding |
| `call` | `(func arg1 arg2)` | Function invocation |
| `label` | `(label name)` | Mark jump target |
| `goto` | `(goto target)` | Unconditional jump |
| `ifnot` | `(ifnot bool_var target)` | Jump if false |
| `ret` | `(ret expr)` | Return from function |

### Agent Constructs (What You Should Generate)

Generate these - the interpreter handles them directly:

```lisp
; If statement - conditional execution
(if (gt x 5)
  (print "x is greater than 5"))

; If-else statement
(if (gt x 5)
  (print "greater")
  (else
    (print "not greater")))

; While loop - iterate while condition holds
(while (lt i 10)
  (set i int (add i 1)))

; For-each loop - iterate collections
(for-each val int my_array
  (print val))

; Infinite loop - for servers
(loop
  (handle_request))

; Break - exit loop early
(if (eq val target)
  (break))

; Continue - skip to next iteration
(if (eq val 0)
  (continue))

; Short-circuit boolean operators
(if (and (gt x 0) (lt x 100))
  (print "in range"))
(if (or (eq x 0) (eq y 0))
  (print "at least one zero"))

; Try/catch - recoverable error handling
(try
  (set result int (div 10 0))
  (catch err string
    (print "Caught: ")
    (print err)))

; Cond - flat multi-branch conditional
(cond
  ((gt x 0) (set result string "positive"))
  ((lt x 0) (set result string "negative"))
  (true (set result string "zero")))

; Array literals
(set nums array [1 2 3 4 5])
(set names array ["Alice" "Bob"])

; Map literals
(set config map {"host" "localhost" "port" 8080})
```

**Note**: `if` is the primary conditional construct. It supports an optional `(else ...)` block. `cond` is for flat multi-branch conditionals (3+ branches) — evaluates conditions in order, executes the first match. Use `true` as the last condition for a default branch. `and`/`or` are short-circuit special forms (not function calls) - the second expression is not evaluated if the result is determined by the first. `try/catch` catches RuntimeError exceptions and binds the error message as a string to the catch variable. Array literals `[...]` and map literals `{...}` create arrays/maps inline.

---

## Type System

### Primitive Types

| Type | Description | Example |
|------|-------------|---------|
| `int` | 64-bit signed integer | `42` |
| `float` | 64-bit floating point | `3.14` |
| `decimal` | Arbitrary precision decimal | `19.99`, `0.1` |
| `bool` | Boolean | `true`, `false` |
| `string` | UTF-8 string | `"hello"` |

**When to use decimal vs float:**
- Use `decimal` for financial calculations where precision matters (money, percentages)
- Use `float` for scientific calculations where performance matters
- Example: `0.1 + 0.2` = `0.3` (decimal) vs `0.30000000000000004` (float)

### Type Annotations

**Every variable must have an explicit type:**

```lisp
(set count int 0)              ; Integer counter
(set price decimal 19.99)      ; Decimal price (financial precision)
(set pi float 3.14159)         ; Float (scientific precision)
(set name string "Alice")      ; String
(set active bool true)         ; Boolean
```

**No implicit conversions - be explicit:**

```lisp
; ❌ Wrong - mixing types
(set x int 10)
(set y float (add x 3.14))  ; Type error!

; ✅ Correct - explicit conversion
(set x int 10)
(set x_float float (cast_int_float x))
(set y float (add x_float 3.14))
```

---

## Operations: Type-Directed Dispatch

**The killer feature for LLMs**: Write generic operation names, interpreter infers types.

### Arithmetic

```lisp
(add x y)     ; Becomes add_int, add_float, add_decimal, or add
(sub x y)     ; Subtraction
(mul x y)     ; Multiplication
(div x y)     ; Division
(mod x y)     ; Modulo (integers only)
(neg x)       ; Negation
```

**You don't need to remember:** `add_int`, `add_float`, `add_decimal`, `add`  
**Just write:** `(add x y)` and the interpreter figures it out from `x`'s type.

### Comparisons

```lisp
(eq x y)      ; Equal
(ne x y)      ; Not equal
(lt x y)      ; Less than
(gt x y)      ; Greater than
(le x y)      ; Less or equal
(ge x y)      ; Greater or equal
```

### Math Functions

```lisp
(abs x)       ; Absolute value
(min a b)     ; Minimum
(max a b)     ; Maximum
(sqrt x)      ; Square root (float only)
(pow x y)     ; Power (float only)
(floor x)     ; Round toward -infinity (float -> int)
(ceil x)      ; Round toward +infinity (float -> int)
(round x)     ; Round to nearest (float -> int)
```

### String Operations

```lisp
(string_length text)              ; Get length -> int
(string_concat a b)               ; Concatenate -> string
(string_equals a b)               ; Compare equality -> bool
(string_contains haystack needle)  ; Check contains -> bool
(string_slice text start len)     ; Extract substring (start, LENGTH) -> string
(string_split text delimiter)     ; Split -> array
(string_trim text)                ; Remove whitespace -> string
(string_replace text old new)      ; Replace ALL occurrences -> string
(string_format template args...)  ; Format with {} placeholders -> string
(string_find haystack needle)     ; Find index of needle (-1 if not found) -> int
(string_starts_with text prefix)  ; Check prefix -> bool
(string_ends_with text suffix)    ; Check suffix -> bool
```

**CRITICAL**: `string_slice` takes `(text, start, LENGTH)` NOT `(text, start, end)`.
- To get characters 1-3: `(string_slice text 1 3)` extracts 3 characters starting at index 1
- To get substring from index 5 to 10: `(string_slice text 5 5)` (length = 10 - 5)

**There is only ONE string slicing operation**: `string_slice`. Do not use `string_substring` or any other variants.

**`string_format`**: Uses `{}` as placeholders, replaced sequentially with arguments.
- Example: `(string_format "Hello, {}! Age: {}" name age)` -> `"Hello, Alice! Age: 30"`
- Extra `{}` without arguments are left as-is.

**`string_find`**: Returns index of first occurrence, or -1 if not found. Empty needle returns 0.

### I/O Operations

**Polymorphic print** - works with all types automatically:

```lisp
; Print strings
(print "Hello")           ; Prints: Hello

; Print integers
(set x int 42)
(print x)                 ; Prints: 42

; Print booleans
(set flag bool true)
(print flag)              ; Prints: true

; Print nested expressions (type inference!)
(print (lt 5 10))        ; Prints: true
(print (add 2 3))        ; Prints: 5

; Print with newline
(println "Done!")        ; Prints: Done!\n

; Read input
(read_line)               ; Read line from stdin -> string
```

**How it works**: The interpreter automatically dispatches to the correct print function based on the value's type:
- `int` → `print_int`
- `float` → `print_float`
- `bool` → `io_print_bool`
- `string` → `io_print_str`
- `array` → `io_print_array`
- `map` → `io_print_map`

**You never need to remember the specific function names** - just use `(print value)`!

### File Operations

```lisp
(file_read path)        ; Read file -> string
(file_write path data)  ; Write file
(file_append path data) ; Append to file
(file_exists path)      ; Check exists -> bool
(file_delete path)      ; Delete file
```

---

## Standard Library Modules

**CRITICAL: Many operations that were previously built-in opcodes are now implemented in stdlib modules.**

AISL follows the philosophy: **"If it CAN be written in AISL, it MUST be written in AISL."** However, commonly-used string operations are available as both builtins and stdlib implementations.

### Operations That Require Stdlib Import

| Operation | Stdlib Import Required | Function Name |
|-----------|------------------------|---------------|
| **String operations** | `(import string_utils)` | `split`, `trim`, `contains`, `replace` |
| **JSON operations** | `(import json_utils)` | `json_parse`, `json_stringify`, `json_new_object` |
| **Regex** | `(import regex)` | `regex_compile`, `regex_match`, `regex_find` |

### How to Use Stdlib Modules

**1. Import at the top of your module:**

```lisp
(module my_program
  ; Result type removed - use panic-based error handling
  (import string_utils)             ; From stdlib/core/string_utils.aisl
  (import json_utils)               ; From stdlib/data/json_utils.aisl
  (import regex)                    ; From stdlib/pattern/regex.aisl
  
  (fn main -> int
    ; Your code here
    (ret 0)))
```

**2. Use the imported functions:**

```lisp
; String operations
(set text string "  hello  ")
(set trimmed string (trim text))

; JSON operations
(set obj json (new_object))
(set obj "key" "value")
(set json_str string (stringify obj))

```

### Complete List of 17 Stdlib Modules

**Core (9):**
- `string_utils` - String ops (split, trim, contains, replace, starts_with, ends_with, to_upper, to_lower)
- `conversion` - Type conversion (string_from_int, string_from_float, string_from_bool, bool_to_int, int_to_bool, kilometers_to_miles, celsius_to_fahrenheit)
- `array_utils` - Array utilities (array_sum, array_product, array_find, array_contains, array_min, array_max, array_reverse, array_fill, array_range)
- `math` - Math operations (abs, abs_float, min, max, min_float, max_float)
- `math_extended` - Extended math (clamp, sign, lerp, is_even, is_odd, square, cube)
- `filesystem` - File utilities (read_file_safe, write_file_safe, delete_if_exists, copy_file, read_lines, count_lines)
- `network` - Network utilities (is_valid_port, normalize_path, build_url, build_query_string, parse_url, extract_domain)
- `text_utils` - Text utilities (repeat_string, pad_left, pad_right, truncate, word_count, reverse_string, is_empty)
- `validation` - Validation (in_range, is_positive, is_negative, is_zero, is_divisible_by)

**Data (1):**
- `json_utils` - JSON (parse, stringify, new_object, new_array, get, set, has, delete, push, length, type)

**Net (1):**
- `http` - HTTP client (get, post, put, delete, parse_response, build_request)

**Pattern (1):**
- `regex` - Regex (compile, match, find, find_all, replace)

**System (1):**
- `process` - Processes (spawn, wait, kill, exit, get_pid, get_env, set_env)

**Database (1):**
- `sqlite` - SQLite database operations

**Crypto (3):**
- `base64` - Base64 encoding/decoding (base64_encode, base64_decode)
- `hash` - Cryptographic hashes (sha256, md5) — pure AISL using bitwise builtins
- `hmac` - HMAC authentication (hmac_sha256) — pure AISL using hash module


### When to Use Stdlib vs Built-in

**Use stdlib imports for:**
- ✅ String manipulation (split, to_upper, to_lower — note: trim, contains, replace, starts_with, ends_with are now also builtins)
- ✅ Type conversion (string_from_int, string_from_float, bool_to_int)
- ✅ Unit conversion (kilometers_to_miles, celsius_to_fahrenheit)
- ✅ JSON operations (parse, stringify)
- ✅ HTTP request building
- ✅ Regex operations
- ✅ Array utilities (sum, product, find, reverse)
- ✅ Math utilities (clamp, sign, lerp)
- ✅ File utilities (safe read/write, copy)
- ✅ Text utilities (pad, truncate, word count)
- ✅ Validation (in_range, is_positive)
- ✅ Process management
- ✅ Base64 encoding/decoding (base64_encode, base64_decode)
- ✅ Cryptographic hashing (sha256, md5)
- ✅ HMAC authentication (hmac_sha256)

**Use built-in operations for:**
- ✅ Arithmetic (add, sub, mul, div, mod)
- ✅ Comparisons (eq, ne, lt, gt, le, ge)
- ✅ Basic math (abs, min, max, sqrt, pow, floor, ceil, round)
- ✅ Bitwise ops (bit_and, bit_or, bit_xor, bit_not, bit_shift_left, bit_shift_right)
- ✅ Type conversions (cast_int_float, cast_int_decimal, cast_decimal_int, cast_float_decimal, cast_decimal_float, string_from_int, etc.)
- ✅ String ops (string_length, string_concat, string_slice, string_format, string_find, string_contains, string_trim, string_replace, string_starts_with, string_ends_with, string_split)
- ✅ I/O (print, println, read_line)
- ✅ File operations (file_read, file_write, file_exists)
- ✅ Arrays (array_new, array_push, array_get, array_set, array_length) + array literals `[1 2 3]`
- ✅ Maps (map_new, map_set, map_get, map_has, map_delete) + map literals `{"key" "value"}`
- ✅ TCP/networking (tcp_listen, tcp_accept, tcp_connect, tcp_send, tcp_receive)
- ✅ System (argv, argv_count)

### Common Stdlib Patterns

### Important Notes for LLMs

**BEFORE IMPLEMENTING: Check stdlib/ for available modules**

stdlib/ (pure AISL implementations):
- `string_utils` - trim, split, contains, replace
- `conversion` - string_from_int, bool_to_int
- `json_utils` - parse, stringify
- `http` - get, post
- `regex` - compile, match, replace
- `array_utils` - sum, product, find, reverse
- `math` / `math_extended` - abs, clamp, sign, lerp
- `filesystem` - safe read/write, copy
- `network` - build_url, parse_url
- `text_utils` - pad, truncate, word_count
- `validation` - in_range, is_positive
- `process` - spawn, wait
- `sqlite` - open, exec
- `base64` - base64_encode, base64_decode
- `hash` - sha256, md5
- `hmac` - hmac_sha256

**Process:**
1. List `stdlib/` directory to see available modules
2. Check module manifest (.aisl.manifest) for function signatures
3. Import: `(import module_name)`
4. Use available functions

**NEVER implement something that exists in stdlib/**

1. **Always check if an operation needs an import** - If you get a "function not found" error, check if it's a stdlib function.

2. **Import modules at the top** - Put all `(import ...)` statements right after `(module ...)`.

3. **Use the correct import syntax:**
   - Simple import: `(import module_name)` - Module loader automatically searches `stdlib/core/`, `stdlib/data/`, `stdlib/net/`, `stdlib/sys/`, `stdlib/crypto/`, `stdlib/db/`, `stdlib/pattern/`
   - Example: `(import json_utils)` automatically finds `stdlib/data/json_utils.aisl`
   - Example: `(import http)` automatically finds `stdlib/net/http.aisl`
   - **NOTE**: The `(import module_name from subdir)` syntax is NOT supported!

4. **Function names match module names** - After importing `json_utils`, use `json_parse`, `json_stringify`, etc. (not shortened names).

5. **Documentation location:** See `stdlib/README.md` for complete documentation of all 17 modules.

---

## Control Flow Patterns

### Pattern 1: While Loop

```lisp
(fn countdown n int -> int
  (while (gt n 0)
    (print n)
    (set n int (sub n 1)))
  (ret 0))
```

### Pattern 2: Infinite Loop with Break

```lisp
(fn find_first arr string target int -> int
  (set i int 0)
  (loop
    (set val int (array_get arr i))
    (if (eq val target)
      (break))
    (set i int (add i 1)))
  (ret i))
```

### Pattern 3: Skip with Continue

```lisp
(fn count_positive arr string len int -> int
  (set i int 0)
  (set count int 0)
  (while (lt i len)
    (set val int (array_get arr i))
    (set i int (add i 1))
    (if (le val 0)
      (continue))
    (set count int (add count 1)))
  (ret count))
```

### Pattern 4: Conditional Logic

```lisp
(fn max a int b int -> int
  (if (gt a b)
    (ret a))
  (ret b))
```

**Advanced Pattern with Core IR** (use only when `if` can't express the logic):

```lisp
(fn complex_conditional flag bool -> string
  (set result string "default")
  (ifnot flag skip)
  (set result string "modified")
  (label skip)
  (ret result))
```

---

## Common Patterns for LLMs

### Accumulator Pattern

```lisp
(fn sum arr string n int -> int
  (set sum int 0)
  (set i int 0)
  (while (lt i n)
    (set val int (array_get arr i))
    (set sum int (add sum val))
    (set i int (add i 1)))
  (ret sum))
```

### Recursive Pattern

```lisp
(fn factorial n int -> int
  (if (eq n 0)
    (ret 1))
  (set n_minus_1 int (sub n 1))
  (set result int (factorial n_minus_1))
  (ret (mul n result)))
```

### Search Pattern

```lisp
(fn find arr string target int len int -> int
  (set i int 0)
  (while (lt i len)
    (set val int (array_get arr i))
    (if (eq val target)
      (ret i))
    (set i int (add i 1)))
  (ret -1))  ; Not found
```

### Filter Pattern

```lisp
(fn filter_evens arr string len int -> string
  (set result string (array_new))
  (set i int 0)
  (while (lt i len)
    (set val int (array_get arr i))
    (set remainder int (mod val 2))
    (set is_even bool (eq remainder 0))
    (if is_even
      (array_push result val))
    (set i int (add i 1)))
  (ret result))
```

### Financial Calculation Pattern (Decimal Type)

```lisp
(fn calculate_total prices string tax_rate decimal -> decimal
  (set total decimal (cast_int_decimal 0))
  (set i int 0)
  (set len int (array_length prices))
  (while (lt i len)
    (set price decimal (array_get prices i))
    (set total decimal (add total price))
    (set i int (add i 1)))
  
  ; Apply tax
  (set tax decimal (mul total tax_rate))
  (set total_with_tax decimal (add total tax))
  (ret total_with_tax))

(fn main -> int
  (set prices string (array_new))
  (array_push prices (cast_float_decimal 19.99))
  (array_push prices (cast_float_decimal 29.99))
  
  (set tax_rate decimal (cast_float_decimal 0.08))  ; 8% tax
  (set total decimal (calculate_total prices tax_rate))
  
  (print "Total with tax: ")
  (print total)  ; Precise decimal calculation
  (ret 0))
```

**Why use decimal for financial calculations:**
- Float: `0.1 + 0.2` = `0.30000000000000004` (wrong!)
- Decimal: `0.1 + 0.2` = `0.3` (correct!)
- Always use `decimal` for money, percentages, and accounting

---

## Testing Your Generated Code

AISL has a built-in test framework. Add tests to verify behavior:

```lisp
(module my_module
  (fn add_numbers x int y int -> int
    (ret (add x y)))
  
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
| `interpreter/interpreter.ml` | Core interpreter with all builtins |
| `interpreter/parser.ml` | S-expression parser |
| `interpreter/lexer.ml` | Tokenizer |
| `interpreter/ast.ml` | AST node types |
| `interpreter/types.ml` | Type kind definitions |
| `interpreter/vm.ml` | Entry point |
| `tests/` | 138 test files with examples |
| `examples/` | Complete working programs |

### Quick Lookups

- **Syntax questions**: See LANGUAGE_SPEC.md sections 1-3
- **Control flow**: See AISL-AGENT.md examples
- **Built-in functions**: See LANGUAGE_SPEC.md section 5 (180+ functions)
- **Type system**: See AISL-CORE.md section "Types"
- **Error handling**: Use try/catch for recoverable errors, guard checks for predictable ones. See LANGUAGE_SPEC.md.

---

## Common Pitfalls for LLMs

### ⚠️ CRITICAL: Reserved keyword conflicts with variable names

**PARSER BUG:** Certain keywords used in AISL's test-spec framework are reserved and CANNOT be used as variable names anywhere in your code, even outside of test contexts.

**Reserved keywords that cause parse errors:**
- `input` - Used in test-spec `(input ...)` clauses
- `expect` - Used in test-spec `(expect ...)` clauses  
- `case` - Used in test-spec `(case "description" ...)` clauses

### ❌ Don't: Use reserved keywords as variable names

```lisp
(fn process_data -> int
  (set input string "test")        ; ❌ ERROR: 'input' is reserved!
  (set result string (parse input))  ; ❌ Parsed as EXPR_LIT_UNIT, not variable!
  (ret 0))
```

**What happens:** The parser treats `input`, `expect`, and `case` as special keywords even outside test-spec contexts. When used as variable names, they are parsed as **unit literals (EXPR_LIT_UNIT)** instead of variable references (EXPR_VAR), causing type errors and segfaults.

### ✅ Do: Use descriptive, non-reserved variable names

```lisp
(fn process_data -> int
  (set data_input string "test")      ; ✅ Works: not a keyword
  (set my_input string "test")        ; ✅ Works: not a keyword
  (set input_data string "test")      ; ✅ Works: not a keyword
  (set result string (parse data_input))  ; ✅ Correctly parsed as variable
  (ret 0))
```

**Safe alternatives:**
- Instead of `input` → use `data_input`, `my_input`, `text_input`, `raw_input`
- Instead of `expect` → use `expected`, `expected_value`, `target`
- Instead of `case` → use `test_case`, `case_value`, `variant`

**Status:** This is a known parser limitation. The test-spec keywords should only be reserved within test-spec contexts, but currently they're reserved globally.

---

### If-Else Syntax

**If-else is fully supported** using the `(else ...)` block:

```lisp
; Simple if
(if (gt x 5)
  (print "greater than 5"))

; If-else
(if (gt x 5)
  (print "greater")
  (else
    (print "not greater")))

; Multiple statements in both branches
(if (gt x 0)
  (set result string "positive")
  (set count int (add count 1))
  (else
    (set result string "non-positive")
    (set count int (sub count 1))))

; Nested if-else
(if (gt x 0)
  (set result string "positive")
  (else
    (if (lt x 0)
      (set result string "negative")
      (else
        (set result string "zero")))))
```

**The `(else ...)` block must be the LAST element** inside the if body.

**The result variable pattern is still valid** and sometimes cleaner for simple cases:

```lisp
(set message string "failed")
(if (gt x 5)
  (set message string "success"))
(print message)
```

---

### ❌ Don't: Use 'mod' keyword for modules

```lisp
(mod my_module    ; ERROR: 'mod' is not valid
  (fn add x int y int -> int
    (ret (add x y))))
```

### ✅ Do: Use 'module' keyword

```lisp
(module my_module
  (fn add x int y int -> int
    (ret (add x y))))
```

**Note**: The `mod` keyword was renamed to `module` to avoid conflict with the modulo operation `(mod x y)`.

### ❌ Don't: Use built-in function names that require stdlib imports

```lisp
(module my_program
  ; Missing: (import string_utils)
  (fn main -> int
    (set text string "  hello  ")
    (set trimmed string (trim text))  ; ERROR: function 'trim' not found
    (ret 0)))
```

### ✅ Do: Import required stdlib modules

```lisp
(module my_program
  (import string_utils)  ; ✅ Import first!
  
  (fn main -> int
    (set text string "  hello  ")
    (set trimmed string (trim text))  ; ✅ Works now
    (ret 0)))
```

**Common functions that require imports:**
- String ops (split, trim, replace) → `(import string_utils)`
- JSON ops (json_parse, json_stringify) → `(import json_utils)`
- Regex (regex_compile, regex_match, regex_find) → `(import regex)`

### ❌ Don't: Mix types implicitly

```lisp
(set x int 10)
(set y float (add x 3.14))  ; ERROR: int + float
```

### ✅ Do: Convert explicitly

```lisp
(set x int 10)
(set x_float float (cast_int_float x))
(set y float (add x_float 3.14))
```

### ❌ Don't: Use infix operators

```lisp
(set sum int (x + y))  ; ERROR: Not valid syntax
```

### ✅ Do: Use function calls

```lisp
(set sum int (add x y))
```

### ❌ Don't: Forget type annotations

```lisp
(set count 0)  ; ERROR: Missing type
```

### ✅ Do: Always specify types

```lisp
(set count int 0)
```

### ❌ Don't: Use break/continue outside loops

```lisp
(fn example () -> int
  (break)  ; ERROR: Not in a loop
  (ret 0))
```

### ✅ Do: Only use break/continue inside while/loop

```lisp
(fn example () -> int
  (loop
    (break))  ; OK: Inside loop
  (ret 0))
```

### ❌ Don't: Write Core IR directly (usually)

```lisp
(fn example () -> int
  (label loop_start)
  (goto loop_start)  ; Tedious, error-prone
  (ret 0))
```

### ✅ Do: Use Agent constructs

```lisp
(fn example () -> int
  (loop
    (do_something))  ; Desugars automatically
  (ret 0))
```

### ❌ Don't: Use reserved type keywords as variable names

```lisp
(set json string "test")    ; ERROR: 'json' is a type keyword
(set array string "data")   ; ERROR: 'array' is a type keyword
(set map string "values")   ; ERROR: 'map' is a type keyword
```

**✅ FIXED (2026-02-08):** Parser now rejects type keywords with clear error message:
```
Parse error at line 3: Cannot use type keyword 'json' as variable name. 
Use a descriptive name instead (e.g., 'json_data', 'json_value')
```

**What used to happen (before fix):** The variable was parsed as a type instead of a name, causing it to store/print as "0" or garbage values instead of the actual content.

**Example that now fails at parse time:**
```lisp
(fn test -> int
  (set json string "{\"status\":\"ok\"}")  ; Parse error!
  (print json)
  (ret 0))
```

### ✅ Do: Use descriptive non-reserved names

```lisp
(set json_str string "test")     ; OK: Different name
(set data_array string "data")   ; OK: Different name
(set value_map string "values")  ; OK: Different name

; Fixed example:
(fn test -> int
  (set json_str string "{\"status\":\"ok\"}")
  (print json_str)  ; Prints: {"status":"ok"} (correct!)
  (ret 0))
```

**Reserved type keywords:** `int`, `float`, `string`, `bool`, `json`, `array`, `map`, `channel`, `future`, `unit`

### ❌ Don't: Name modules with type keywords

```lisp
; ❌ WRONG - Module name conflicts with type
(module json
  (fn parse_json ...))    ; ERROR: 'json' is a type keyword

; ❌ WRONG - These also fail
(module array ...)           ; ERROR: array is a type
(module map ...)             ; ERROR: map is a type
(module string ...)          ; ERROR: string is a type
```

### ✅ Do: Use descriptive module names

```lisp
; ✅ CORRECT - Descriptive names
(module json_utils
  (fn parse_json ...))

(module array_helpers ...)
(module map_utils ...)
(module string_utils ...)
```

**Why this matters**: The parser tokenizes type keywords specially (TOK_TYPE_JSON, etc.), so using them as module names causes confusing "Module '' not found" errors.

### ❌ Don't: Return string literals directly from if statements

```lisp
(fn get_message flag bool -> string
  (if flag
    (ret "yes"))          ; ERROR: String return from if doesn't work
  (ret "no"))
```

**Bug**: Returning string literals from inside `if` blocks doesn't work correctly. The function will always return the value after the if block, ignoring the conditional return.

### ✅ Do: Use result variable pattern for string returns

```lisp
(fn get_message flag bool -> string
  (set result string "no")
  (if flag
    (set result string "yes"))
  (ret result))
```

**Note**: Returning integers from if blocks works fine - this bug only affects string literals.

### ❌ Don't: Forget closing parenthesis on modules

```lisp
(module my_module
  (fn func1 ...)
  (fn func2 ...)
  ; Missing closing ) here!
```

**Error message**: "Module '' not found in search paths" (confusing!)

### ✅ Do: Always close module with )

```lisp
(module my_module
  (fn func1 ...)
  (fn func2 ...))
; Closing paren here ^
```

### ❌ Don't: Use multiple ret statements after labels

```lisp
(fn example flag bool -> string
  (ifnot flag return_b)
  (ret "A")              ; First ret
  (label return_b)
  (ret "B"))             ; ERROR: Parser doesn't allow this pattern
```

### ✅ Do: Use a result variable and single ret

```lisp
(fn example flag bool -> string
  (set result string "B")
  (ifnot flag skip)
  (set result string "A")
  (label skip)
  (ret result))          ; Single ret at end
```

### ⚠️ Important: Core IR constructs are NOT function calls

Core IR constructs like `label`, `goto`, and `ifnot` are special syntax, not function calls:

```lisp
; ❌ WRONG - Don't use 'call'
(call label my_label)
(call goto my_label)
(call ifnot condition my_label)

; ✅ CORRECT - Use directly
(label my_label)
(goto my_label)
(ifnot condition my_label)
```

**When to use Core IR constructs:**
- Use `label` and `goto` for complex control flow that can't be expressed with while/loop/if
- Use `ifnot` for advanced conditional jumps when `if` can't express the logic
- **Prefer Agent constructs (`if`, `while`, `loop`) whenever possible** - they desugar to Core IR automatically

**Important**: Always use `if` for simple conditionals. Only use `ifnot` + `label` for complex control flow patterns.

---

## Performance Characteristics

AISL is designed for predictable performance:

- **Type-directed dispatch**: Interpreter resolves operations based on argument types
- **No GC pauses**: OCaml's garbage collector is generational and incremental
- **Predictable control flow**: All structured constructs desugar to simple jumps
- **Direct interpretation**: Tree-walking interpreter with no compilation step
- **Fast startup**: Single-step execution — parse and run immediately

---

## Current Limitations

### Design Decisions

- **Try/catch for recovery**: Operations panic on error by default; use `(try ... (catch ...))` for recoverable errors
- **No closures**: Functions do not capture outer scope variables — all data must be passed as parameters
- **No null**: Variables must be initialized
- **No undefined behavior**: All operations have defined semantics
- **No operator overloading**: One operation name = one meaning

---

## Example: Complete Web Server

```lisp
(module web_server
  (fn handle_request client_socket string -> int
    (set request string (tcp_receive client_socket 4096))
    (set response string "HTTP/1.1 200 OK\r\n\r\nHello, World!")
    (tcp_send client_socket response)
    (tcp_close client_socket)
    (ret 0))
  
  (fn main -> int
    (set port int 8080)
    (set server_socket string (tcp_listen port))
    (print "Server listening on port 8080")
    (loop
      (set client_socket string (tcp_accept server_socket))
      (handle_request client_socket))
    (ret 0)))
```

---

## Summary: AISL in 10 Points

1. **Two layers**: Agent (what you write) desugars to Core (what runs)
2. **Explicit everything**: Types, control flow - no hidden behavior
3. **Type dispatch**: Write `add`, interpreter picks `add_int` or `add_float`
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
- **Tests**: `tests/` directory (138 test files)
- **Issues**: [Link to be added]

---

**AISL - Designed for AI, Built for Everyone.**

*For detailed technical specifications, see AISL-CORE.md and AISL-AGENT.md.*
