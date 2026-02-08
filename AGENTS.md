# AISL for AI Agents: A Complete Guide

**Last Updated**: 2026-02-08  
**Target Audience**: LLMs, AI Agents, Code Generation Systems

**Recent Changes** (2026-02-08):
- Removed 621 lines of dead code from compiler (HTTP/WebSocket/base64 C implementations)
- Removed 137 verbose section header comments for token efficiency
- All HTTP/WebSocket functionality now in pure AISL (stdlib/net/)

---

## ⚡ FOR LLMs: OPTIMIZED FORMATS AVAILABLE

**⚠️ IMPORTANT: Always consult machine-readable formats FIRST**

**This document is human-readable prose with examples.**  
**For token-optimized LLM consumption, use these instead:**

- **`.aisl.grammar`** - Complete language reference in 45 lines (~400 tokens) - **CONSULT FIRST**
- **`.aisl.meta`** - Project context in compressed s-expr format (80% fewer tokens)
- **`.aisl.analysis`** - Deep architectural analysis + runtime discoveries

**Token efficiency:**
- This file: ~700 lines = ~8,000 tokens
- `.aisl.grammar`: ~45 lines = ~400 tokens
- **20x more efficient for context loading**

**Consultation order for AI agents:**
1. **FIRST**: `.aisl.grammar` - syntax, operations, critical notes
2. **SECOND**: `.aisl.meta` - project context
3. **THIRD**: `.aisl.analysis` - design decisions, discovered issues
4. **LAST**: This file (AGENTS.md) - only if you need detailed examples

**When to use each:**
- **Generating AISL code**: Load `.aisl.grammar` + `.aisl.meta` ONLY
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
    (set content string (call file_read path))
    (set converted string (call regex_replace pattern content))
    (call file_write path converted)
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
  (fn add_numbers ((a int) (b int)) -> int
    (ret (call add a b)))
  
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
- Type-directed dispatch - write `add`, compiler infers `add` vs `add`

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
    (call print "Hello, AISL!")
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
| `call` | `(call func arg1 arg2)` | Function invocation |
| `label` | `(call label name)` | Mark jump target |
| `goto` | `(call goto target)` | Unconditional jump |
| `ifnot` | `(call ifnot bool_var target)` | Jump if false |
| `ret` | `(ret expr)` | Return from function |

### Agent Constructs (What You Should Generate)

Generate these - the compiler desugars them to Core:

```lisp
; If statement - conditional execution
(if (call gt x 5)
  (call print "x is greater than 5"))

; While loop - iterate while condition holds
(while (call lt i 10)
  (set i int (call add i 1)))

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

**Note**: `if` is the primary conditional construct. It desugars to `ifnot` + `label` internally, but you should always use `if` for clarity.

---

## Type System

### Primitive Types

| Type | Description | Example |
|------|-------------|---------|
| `int` | 32-bit signed integer | `42` |
| `int` | 64-bit signed integer | `9223372036854775807` |
| `float` | 32-bit float | `3.14` |
| `float` | 64-bit float | `2.718281828` |
| `bool` | Boolean | `true`, `false` |
| `string` | UTF-8 string | `"hello"` |

### Type Annotations

**Every variable must have an explicit type:**

```lisp
(set count int 0)              ; Integer counter
(set price float 19.99)          ; Float price
(set name string "Alice")      ; String
(set active bool true)         ; Boolean
```

**No implicit conversions - be explicit:**

```lisp
; ❌ Wrong - mixing types
(set x int 10)
(set y float (call add x 3.14))  ; Type error!

; ✅ Correct - explicit conversion
(set x int 10)
(set x_float float (call cast_int_float x))
(set y float (call add x_float 3.14))
```

---

## Operations: Type-Directed Dispatch

**The killer feature for LLMs**: Write generic operation names, compiler infers types.

### Arithmetic

```lisp
(call add x y)     ; Becomes add, add, add, or add
(call sub x y)     ; Subtraction
(call mul x y)     ; Multiplication
(call div x y)     ; Division
(call mod x y)     ; Modulo (integers only)
(call neg x)       ; Negation
```

**You don't need to remember:** `add`, `add`, `add`, `add`  
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
(call sqrt x)      ; Square root (float/float only)
(call pow x y)     ; Power (float/float only)
```

### String Operations

```lisp
(call string_length text)              ; Get length -> int
(call string_concat a b)               ; Concatenate -> string
(call string_contains haystack needle) ; Check contains -> bool
(call string_split text delimiter)     ; Split -> array
(call string_trim text)                ; Remove whitespace -> string
(call string_replace text old new)     ; Replace substring -> string
```

### I/O Operations

**Polymorphic print** - works with all types automatically:

```lisp
; Print strings
(call print "Hello")           ; Prints: Hello

; Print integers
(set x int 42)
(call print x)                 ; Prints: 42

; Print booleans
(set flag bool true)
(call print flag)              ; Prints: true

; Print nested expressions (type inference!)
(call print (call lt 5 10))   ; Prints: true
(call print (call add 2 3))   ; Prints: 5

; Print with newline
(call print_ln "Done!")        ; Prints: Done!\n

; Read input
(call read_line)               ; Read line from stdin -> string
```

**How it works**: The compiler automatically dispatches to the correct print function based on the value's type:
- `int` → `print`
- `int` → `print`  
- `float` → `print`
- `float` → `print`
- `bool` → `io_print_bool`
- `string` → `io_print_str`
- `array` → `io_print_array`
- `map` → `io_print_map`

**You never need to remember the specific function names** - just use `(call print value)`!

### File Operations

```lisp
(call file_read path)        ; Read file -> string
(call file_write path data)  ; Write file
(call file_append path data) ; Append to file
(call file_exists path)      ; Check exists -> bool
(call file_delete path)      ; Delete file
```

---

## Standard Library Modules

**CRITICAL: Many operations that were previously built-in opcodes are now implemented in stdlib modules.**

AISL follows the philosophy: **"If it CAN be written in AISL, it MUST be written in AISL."** As of 2026-02-07, the following operations require importing stdlib modules:

### Operations That Require Stdlib Import

| Operation | Old (❌ Removed) | New (✅ Use This) |
|-----------|------------------|-------------------|
| **String operations** | `(call string_split ...)` | `(import string_utils)` then `(call split ...)` |
| | `(call string_trim ...)` | `(import string_utils)` then `(call trim ...)` |
| | `(call string_contains ...)` | `(import string_utils)` then `(call contains ...)` |
| | `(call string_replace ...)` | `(import string_utils)` then `(call replace ...)` |
| **JSON operations** | `(call json_parse ...)` | `(import json_utils)` then `(call json_parse ...)` |
| | `(call json_stringify ...)` | `(import json_utils)` then `(call json_stringify ...)` |
| | `(call json_new_object)` | `(import json_utils)` then `(call json_new_object)` |
| **Result type** | Not available | `(import result)` then `(call ok ...)`, `(call err ...)` |
| **Base64** | `(call base64_encode ...)` | `(import base64)` then `(call base64_encode ...)` |
| **Regex** | `(call regex_compile ...)` | `(import regex)` then `(call regex_compile ...)` |
| **Hashing** | `(call crypto_sha256 ...)` | `(import hash)` then `(call crypto_sha256 ...)` |

### How to Use Stdlib Modules

**1. Import at the top of your module:**

```lisp
(module my_program
  (import result)                   ; From stdlib/core/result.aisl
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
(set trimmed string (call trim text))

; JSON operations
(set obj json (call new_object))
(call set obj "key" "value")
(set json_str string (call stringify obj))

; Result type for error handling
(set result result (call ok "success"))
(if (call is_ok result)
  (set value string (call unwrap result)))
```

### Complete List of 11 Stdlib Modules

**Core (3):**
- `result` - Error handling (ok, err, is_ok, is_err, unwrap, unwrap_or, error_code, error_message)
- `string_utils` - String ops (split, trim, contains, replace, starts_with, ends_with, to_upper, to_lower)
- `conversion` - Type conversion (string_from_int, string_from_float, string_from_bool, bool_to_int, int_to_bool, kilometers_to_miles, celsius_to_fahrenheit)

**Data (2):**
- `json from data` - JSON (parse, stringify, new_object, new_array, get, set, has, delete, push, length, type)
- `base64 from data` - Base64 (encode, decode)

**Net (2):**
- `http from net` - HTTP client (get, post, put, delete, parse_response, build_request)
- `websocket from net` - WebSocket (connect, send, receive, close)

**Pattern (1):**
- `regex from pattern` - Regex (compile, match, find, find_all, replace)

**Crypto (1):**
- `hash from crypto` - Hashing (sha256, md5, sha1)

**System (2):**
- `time from sys` - Time (unix_timestamp, sleep, format_time)
- `process from sys` - Processes (spawn, wait, kill, exit, get_pid, get_env, set_env)


### When to Use Stdlib vs Built-in

**Use stdlib imports for:**
- ✅ String manipulation (split, trim, replace)
- ✅ Type conversion (string_from_int, string_from_float, bool_to_int)
- ✅ Unit conversion (kilometers_to_miles, celsius_to_fahrenheit)
- ✅ JSON operations (parse, stringify)
- ✅ Result type (error handling)
- ✅ Base64 encoding/decoding
- ✅ HTTP request building
- ✅ Regex operations
- ✅ Cryptographic hashing
- ✅ Time operations
- ✅ Process management

**Use built-in operations for:**
- ✅ Arithmetic (add, sub, mul, div, mod)
- ✅ Comparisons (eq, ne, lt, gt, le, ge)
- ✅ Basic math (abs, min, max, sqrt, pow)
- ✅ Type conversions (cast_int_float, string_from_int, etc.)
- ✅ Basic string ops (string_length, string_concat, string_substring)
- ✅ I/O (print, print_ln, read_line)
- ✅ File operations (file_read, file_write, file_exists)
- ✅ Arrays (array_new, array_push, array_get, array_set, array_length)
- ✅ Maps (map_new, map_set, map_get, map_has, map_delete)
- ✅ TCP/networking (tcp_listen, tcp_accept, tcp_connect, tcp_send, tcp_receive)

### Common Stdlib Patterns

**Pattern 1: Error Handling with Result Type**

```lisp
(module safe_file_reader
  (import result)
  
  (fn safe_read path string -> result
    (set exists bool (call file_exists path))
    (if (call not exists)
      (ret (call err 1 "File not found")))
    (set content string (call file_read path))
    (ret (call ok content)))
  
  (fn main -> int
    (set result result (call safe_read "data.txt"))
    (if (call is_ok result)
      (set content string (call unwrap result))
      (call print content)
      (ret 0))
    ; Handle error
    (set msg string (call error_message result))
    (call print msg)
    (ret 1)))
```

**Pattern 2: String Processing**

```lisp
(module text_processor
  (import string_utils)
  
  (fn process_text text string -> string
    (set trimmed string (call trim text))
    (set upper string (call to_upper trimmed))
    (set words array (call split upper " "))
    (ret upper))
  
  (fn main -> int
    (set result string (call process_text "  hello world  "))
    (call print result)  ; Prints: HELLO WORLD
    (ret 0)))
```

**Pattern 3: JSON API Response**

```lisp
(module api_client
  (import json_utils)
  (import http)
  
  (fn fetch_user id int -> json
    (set url string "https://api.example.com/users/")
    (set id_str string (call string_from_int id))
    (set full_url string (call string_concat url id_str))
    
    (set response string (call get full_url))
    (set json_obj json (call json_parse response))
    (ret json_obj))
  
  (fn main -> int
    (set user json (call fetch_user 123))
    (set name string (call json_get user "name"))
    (call print name)
    (ret 0)))
```

**Pattern 4: Multiple Imports**

```lisp
(module complete_example
  (import result)
  (import string_utils)
  (import json_utils)
  (import hash)
  
  (fn main -> int
    ; Use all imports together
    (set text string "  Hello  ")
    (set trimmed string (call trim text))
    (set hash_val string (call crypto_sha256 trimmed))
    
    (set obj json (call json_new_object))
    (call json_set obj "text" trimmed)
    (call json_set obj "hash" hash_val)
    
    (set result result (call ok (call json_stringify obj)))
    (if (call is_ok result)
      (call print (call unwrap result)))
    
    (ret 0)))
```

**Pattern 5: Type Conversion and Formatting**

```lisp
(module format_example
  (import conversion)
  
  (fn format_temperature celsius float -> string
    (set fahrenheit float (call celsius_to_fahrenheit celsius))
    (set c_str string (call string_from_float celsius))
    (set f_str string (call string_from_float fahrenheit))
    (set result string (call string_concat c_str "°C = "))
    (set result string (call string_concat result f_str))
    (set result string (call string_concat result "°F"))
    (ret result))
  
  (fn build_http_response status int body string -> string
    (set status_str string (call string_from_int status))
    (set response string (call string_concat "HTTP/1.1 " status_str))
    (set response string (call string_concat response " OK\r\n"))
    (set content_len int (call string_length body))
    (set len_str string (call string_from_int content_len))
    (set response string (call string_concat response "Content-Length: "))
    (set response string (call string_concat response len_str))
    (set response string (call string_concat response "\r\n\r\n"))
    (set response string (call string_concat response body))
    (ret response))
  
  (fn main -> int
    (set temp_str string (call format_temperature 25.0))
    (call print temp_str)  ; Prints: 25.000°C = 77.000°F
    
    (set response string (call build_http_response 200 "Hello"))
    (call print response)  ; Proper HTTP response with Content-Length
    
    (ret 0)))
```

### Important Notes for LLMs

1. **Always check if an operation needs an import** - If you get a "function not found" error, check if it's a stdlib function.

2. **Import modules at the top** - Put all `(import ...)` statements right after `(module ...)`.

3. **Use the correct import syntax:**
   - Simple import: `(import module_name)` - Module loader automatically searches `stdlib/core/`, `stdlib/data/`, `stdlib/net/`, `stdlib/sys/`, `stdlib/crypto/`, `stdlib/db/`, `stdlib/pattern/`
   - Example: `(import json_utils)` automatically finds `stdlib/data/json_utils.aisl`
   - Example: `(import http)` automatically finds `stdlib/net/http.aisl`
   - **NOTE**: The `(import module_name from subdir)` syntax is NOT supported!

4. **Function names match module names** - After importing `json_utils`, use `json_parse`, `json_stringify`, etc. (not shortened names).

5. **Documentation location:** See `stdlib/README.md` for complete documentation of all 12 modules.

---

## Control Flow Patterns

### Pattern 1: While Loop

```lisp
(fn countdown n int -> int
  (while (call gt n 0)
    (call print n)
    (set n int (call sub n 1)))
  (ret 0))
```

### Pattern 2: Infinite Loop with Break

```lisp
(fn find_first arr string target int -> int
  (set i int 0)
  (loop
    (set val int (call array_get arr i))
    (if (call eq val target)
      (break))
    (set i int (call add i 1)))
  (ret i))
```

### Pattern 3: Skip with Continue

```lisp
(fn count_positive arr string len int -> int
  (set i int 0)
  (set count int 0)
  (while (call lt i len)
    (set val int (call array_get arr i))
    (set i int (call add i 1))
    (if (call le val 0)
      (continue))
    (set count int (call add count 1)))
  (ret count))
```

### Pattern 4: Conditional Logic

```lisp
(fn max a int b int -> int
  (if (call gt a b)
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
  (while (call lt i n)
    (set val int (call array_get arr i))
    (set sum int (call add sum val))
    (set i int (call add i 1)))
  (ret sum))
```

### Recursive Pattern

```lisp
(fn factorial n int -> int
  (if (call eq n 0)
    (ret 1))
  (set n_minus_1 int (call sub n 1))
  (set result int (call factorial n_minus_1))
  (ret (call mul n result)))
```

### Search Pattern

```lisp
(fn find arr string target int len int -> int
  (set i int 0)
  (while (call lt i len)
    (set val int (call array_get arr i))
    (if (call eq val target)
      (ret i))
    (set i int (call add i 1)))
  (ret -1))  ; Not found
```

### Filter Pattern

```lisp
(fn filter_evens arr string len int -> string
  (set result string (call array_new))
  (set i int 0)
  (while (call lt i len)
    (set val int (call array_get arr i))
    (set remainder int (call mod val 2))
    (set is_even bool (call eq remainder 0))
    (if is_even
      (call array_push result val))
    (set i int (call add i 1)))
  (ret result))
```

### Error Handling Pattern (Result Type)

```lisp
(fn safe_file_read path string -> int
  ; Read file with error handling
  (set result string (call file_read_result path))
  (set success bool (call is_ok result))
  
  (if success
    ; Extract value from Ok result
    (set content string (call unwrap result))
    (call print content)
    (ret 1))
  
  ; Handle error case
  (set err_msg string (call error_message result))
  (call print err_msg)
  (ret 0))
```

### Safe Value Extraction Pattern

```lisp
(fn read_with_default path string -> string
  (set result string (call file_read_result path))
  (set default string "default content")
  ; Returns content if Ok, default if Err
  (set content string (call unwrap_or result default))
  (ret content))
```

### Error Checking Pattern

```lisp
(fn check_file_error path string -> int
  (set result string (call file_read_result path))
  (set is_error bool (call is_err result))
  
  (if is_error
    (set code int (call error_code result))
    (ret code))
  
  (ret 0))
```

---

## Testing Your Generated Code

AISL has a built-in test framework. Add tests to verify behavior:

```lisp
(module my_module
  (fn add_numbers x int y int -> int
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
- **Error handling**: See result type patterns above and tests/test_result_*.aisl

---

## Common Pitfalls for LLMs

### ❌ Don't: Use old 'mod' keyword for modules

```lisp
(mod my_module    ; ERROR: 'mod' is no longer valid
  (fn add x int y int -> int
    (ret (call add x y))))
```

### ✅ Do: Use 'module' keyword

```lisp
(module my_module
  (fn add x int y int -> int
    (ret (call add x y))))
```

**Note**: The `mod` keyword was renamed to `module` to avoid conflict with the modulo operation `(call mod x y)`.

### ❌ Don't: Use built-in function names that require stdlib imports

```lisp
(module my_program
  ; Missing: (import string_utils)
  (fn main -> int
    (set text string "  hello  ")
    (set trimmed string (call trim text))  ; ERROR: function 'trim' not found
    (ret 0)))
```

### ✅ Do: Import required stdlib modules

```lisp
(module my_program
  (import string_utils)  ; ✅ Import first!
  
  (fn main -> int
    (set text string "  hello  ")
    (set trimmed string (call trim text))  ; ✅ Works now
    (ret 0)))
```

**Common functions that require imports:**
- String ops (split, trim, replace) → `(import string_utils)`
- JSON ops (json_parse, json_stringify) → `(import json_utils)`
- Result type (ok, err, is_ok) → `(import result)`
- Base64 (base64_encode, base64_decode) → `(import base64)`
- Regex (regex_compile, regex_match, regex_find) → `(import regex)`

### ❌ Don't: Mix types implicitly

```lisp
(set x int 10)
(set y float (call add x 3.14))  ; ERROR: int + float
```

### ✅ Do: Convert explicitly

```lisp
(set x int 10)
(set x_float float (call cast_int_float x))
(set y float (call add x_float 3.14))
```

### ❌ Don't: Use infix operators

```lisp
(set sum int (x + y))  ; ERROR: Not valid syntax
```

### ✅ Do: Use function calls

```lisp
(set sum int (call add x y))
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
  (call label loop_start)
  (call goto loop_start)  ; Tedious, error-prone
  (ret 0))
```

### ✅ Do: Use Agent constructs

```lisp
(fn example () -> int
  (loop
    (call do_something))  ; Desugars automatically
  (ret 0))
```

### ❌ Don't: Use reserved type keywords as variable names

```lisp
(set json string "test")    ; ERROR: 'json' is a type keyword
(set array string "data")   ; ERROR: 'array' is a type keyword
(set map string "values")   ; ERROR: 'map' is a type keyword
```

### ✅ Do: Use descriptive non-reserved names

```lisp
(set json_str string "test")     ; OK: Different name
(set data_array string "data")   ; OK: Different name
(set value_map string "values")  ; OK: Different name
```

**Reserved type keywords:** `int`, `float`, `string`, `bool`, `json`, `array`, `map`, `result`, `option`

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

- **Zero runtime dispatch**: Type dispatch happens at compile time
- **No GC pauses**: Manual memory management (strings are ref-counted)
- **Predictable jumps**: All control flow compiles to simple jumps
- **Flat bytecode**: No complex stack frames, direct instruction execution
- **Fast compilation**: Single-pass compilation with simple desugaring

---

## Current Limitations (as of 2026-02-07)

### Not Yet Implemented

1. **Struct/Record types**: Planned but not implemented
   - Use multiple variables or arrays for now
   - Maps can be used for key-value pairs

2. **Option type**: For nullable values (Result type is complete)
   - `some`, `none`, `is_some`, `is_none` are planned
   - Use result type with special error codes as workaround

3. **Generics**: Not planned - use type-directed dispatch instead

### Design Decisions

- **No exceptions**: Use explicit error checking with result types
- **No null**: Variables must be initialized
- **No undefined behavior**: All operations have defined semantics
- **No operator overloading**: One operation name = one meaning

---

## Example: Complete Web Server

```lisp
(module web_server
  (fn handle_request client_socket string -> int
    (set request string (call tcp_receive client_socket 4096))
    (set response string "HTTP/1.1 200 OK\r\n\r\nHello, World!")
    (call tcp_send client_socket response)
    (call tcp_close client_socket)
    (ret 0))
  
  (fn main -> int
    (set port int 8080)
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
3. **Type dispatch**: Write `add`, compiler picks `add` or `add`
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
- **Tests**: `tests/` directory (85 test files)
- **Issues**: [Link to be added]

---

**AISL - Designed for AI, Built for Everyone.**

*For detailed technical specifications, see AISL-CORE.md and AISL-AGENT.md.*
