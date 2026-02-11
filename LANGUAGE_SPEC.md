# AISL Language Specification

AISL (AI-Optimized Systems Language) - A two-layer programming language designed for LLM code generation with explicit syntax, zero ambiguity, and stable IR.

## Architecture: Two Layers

AISL consists of two distinct layers:

### AISL-Core (IR Layer)
The minimal, stable intermediate representation. This layer is **frozen** - it will never change. Core consists of only 5 statement types:
- `set` - Variable binding
- `label` - Jump targets
- `goto` - Unconditional jumps
- `ifnot` - Conditional jumps
- `ret` - Return from function

### AISL-Agent (Surface Layer)
The ergonomic surface language that LLMs generate. Agent code includes structured control flow (`while`, `loop`, `break`, `continue`) and type-directed operations (`add` instead of `add`). The interpreter handles Agent code directly — no separate compilation step.

**LLMs write Agent code. The interpreter runs it directly.**

---

## AISL-Agent Grammar (Surface Language)

This is what you write and what LLMs generate.

### Program Structure

```
program ::= (module <name> <function>*)

function ::= (fn <name> <param_flat>* -> <return_type> <statement>*)

param_flat ::= <name> <type>

statement ::= (set <var> <type> <expr>)
            | (<function> <arg>*)
            | (label <name>)
            | (goto <label>)
            | (ifnot <bool_var> <label>)
            | (while <bool_expr> <statement>*)
            | (loop <statement>*)
            | (if <bool_expr> <statement>* [(else <statement>*)])
            | (cond (<bool_expr> <statement>*)*)
            | (for-each <var> <type> <collection_expr> <statement>*)
            | (try <statement>* (catch <var> <type> <statement>*))
            | (break)
            | (continue)
            | (ret <expr>)

expr ::= <literal>
       | <variable>
       | (<function> <arg>*)
       | (and <expr> <expr>)     ; Short-circuit: e2 not evaluated if e1 is false
       | (or <expr> <expr>)      ; Short-circuit: e2 not evaluated if e1 is true
       | [<expr>*]               ; Array literal
       | {<expr> <expr>}*        ; Map literal (key-value pairs)

literal ::= <number> | <string> | true | false
```

**Entry Point:** Programs execute starting from the `main` function. The main function must:
- Be named exactly `main` (not `main_func` or anything else)
- Return type `int` (exit code: 0 = success, non-zero = error)
- Take no parameters (unless your program requires command-line arguments)

Test files using the `test-spec` framework don't require a `main` function.

### Simple Example

```scheme
(module hello
  (fn main -> int
    (print "Hello, World!")
    (ret 0)))
```

---

## Types

### Primitive Types
- **int** - 64-bit signed integer
- **float** - 64-bit floating point
- **decimal** - Arbitrary precision decimal (financial calculations)
- **bool** - Boolean (true/false)
- **string** - UTF-8 string
- **regex** - Compiled regular expression pattern
- **array** - Dynamic array
- **map** - Hash map

### Type Annotations

Variables must be explicitly typed:

```scheme
(set count int 42)
(set name string "Alice")
(set active bool true)
(set price float 19.99)
```

---

## Control Flow (Agent Layer)

### Conditional

**If**: `(if <condition> <statements>...)`

Executes body if condition is true.

```scheme
(fn check_positive n int -> string
  (set result string "not positive")
  (if (gt n 0)
    (set result string "positive"))
  (ret result))
```

**If-Else**: `(if <condition> <then-statements>... (else <else-statements>...))`

Executes then-branch if condition is true, else-branch otherwise.

```scheme
(fn classify n int -> string
  (set result string "zero")
  (if (gt n 0)
    (set result string "positive")
    (else
      (if (lt n 0)
        (set result string "negative"))))
  (ret result))
```

### Cond (Flat Multi-Branch Conditional)

**Cond**: `(cond (<condition> <statements>...)...)`

Evaluates conditions in order, executes the body of the first matching branch. Returns unit if no condition matches. Use `true` as the last condition for a default/else branch.

```scheme
(fn classify_number n int -> string
  (set result string "unknown")
  (cond
    ((gt n 0) (set result string "positive"))
    ((lt n 0) (set result string "negative"))
    (true (set result string "zero")))
  (ret result))

(fn grade_score score int -> string
  (set result string "F")
  (cond
    ((ge score 90) (set result string "A"))
    ((ge score 80) (set result string "B"))
    ((ge score 70) (set result string "C"))
    ((ge score 60) (set result string "D"))
    (true (set result string "F")))
  (ret result))
```

**When to use `cond` vs nested `if-else`:**
- Use `cond` when you have 3+ mutually exclusive branches — flatter, more readable
- Use `if-else` for simple binary conditions
- `cond` evaluates conditions top-to-bottom, executes first match only

### Structured Loops

**While Loop**: `(while <condition> <statements>...)`

Executes body while condition is true.

```scheme
(fn countdown n int -> int
  (while (gt n 0)
    (print n)
    (set n int (sub n 1)))
  (ret 0))
```

**Infinite Loop**: `(loop <statements>...)`

Executes forever. Use for server loops.

```scheme
(fn start_server port int -> int
  (set server_sock string (tcp_listen port))
  (loop
    (set client_sock string (tcp_accept server_sock))
    (handle_connection client_sock))
  (ret 0))
```

### Loop Control

**Break**: `(break)` - Exit nearest loop immediately

```scheme
(fn find_value arr string target int -> int
  (set i int 0)
  (loop
    (set val int (array_get arr i))
    (set found bool (eq val target))
    (ifnot found skip)
    (break)
    (label skip)
    (set i int (add i 1)))
  (ret i))
```

**Continue**: `(continue)` - Skip to next iteration

```scheme
(fn sum_positives arr string n int -> int
  (set i int 0)
  (set sum int 0)
  (while (lt i n)
    (set val int (array_get arr i))
    (set i int (add i 1))
    (set is_negative bool (lt val 0))
    (ifnot is_negative no_skip)
    (continue)
    (label no_skip)
    (set sum int (add sum val)))
  (ret sum))
```

### For-Each Loop

**For-Each**: `(for-each <var> <type> <collection> <statements>...)`

Iterates over array elements or map keys.

```scheme
; Iterate array elements
(fn sum_array arr array -> int
  (set total int 0)
  (for-each val int arr
    (set total int (add total val)))
  (ret total))

; Iterate map keys
(fn print_keys m map -> int
  (for-each key string m
    (print key))
  (ret 0))
```

For-each supports `break` and `continue`. Element type is validated at runtime against the declared type.

### Array and Map Literals

**Array literal**: `[<elements>...]`

Creates an array inline from evaluated expressions.

```scheme
(set nums array [1 2 3 4 5])
(set names array ["Alice" "Bob" "Charlie"])
(set empty array [])
(set mixed array [1 2 3])  ; All elements must be same type at runtime
```

**Map literal**: `{<key> <value> ...}`

Creates a map inline from key-value pairs. Keys must evaluate to strings.

```scheme
(set config map {"host" "localhost" "port" 8080})
(set user map {"name" "Alice" "age" 30})
(set empty_map map {})
```

Array and map literals produce the same runtime values as `array_new`/`map_new` + push/set operations. Map keys maintain insertion order.

### Label-based Control Flow (Core Level)

For complex control flow, use labels and goto:

```scheme
(fn countdown_with_labels n int -> int
  (label loop)
  (set done bool (le n 0))
  (ifnot done continue)
  (ret 0)
  (label continue)
  (print n)
  (set n int (sub n 1))
  (goto loop))
```

**Statement**: `(ifnot <bool_var> <label>)` - Jump to label if variable is false

### Boolean Special Forms

**Short-circuit and**: `(and <expr1> <expr2>)`
- Returns false immediately if expr1 is false; expr2 is NOT evaluated
- Both expressions must evaluate to bool

**Short-circuit or**: `(or <expr1> <expr2>)`
- Returns true immediately if expr1 is true; expr2 is NOT evaluated
- Both expressions must evaluate to bool

**Logical not**: `(not <expr>)` - Regular function call, negates boolean

```scheme
; Short-circuit prevents division by zero
(if (and (ne b 0) (gt (div a b) threshold))
  (print "above threshold"))

; Short-circuit with or
(if (or (eq x 0) (eq y 0))
  (print "at least one is zero"))
```

**Important**: `and`/`or` are special forms (AST nodes), not function calls. They are evaluated before their arguments, enabling short-circuit behavior.

### Control Flow Rules

**Agent Layer (enforced by compiler):**
- `break`/`continue` only valid inside `while`/`loop`
- Nested loops: `break`/`continue` affect innermost loop
- Cannot goto into loop body from outside

**Core Layer (programmer responsibility):**
- Labels are function-scoped
- `goto` can jump to any label in same function
- No restrictions on jump targets

### Recursion

Functions can call themselves:

```scheme
(fn factorial n int -> int
  (set is_base bool (le n 1))
  (ifnot is_base recurse)
  (ret 1)
  (label recurse)
  (set n_minus_1 int (sub n 1))
  (set result int (factorial n_minus_1))
  (ret (mul n result)))
```

---

## How Agent Code Desugars to Core

### While Loop Desugaring

```scheme
; Agent code:
(while (lt count 10)
  (print count))

; Desugars to Core:
(label loop_start_1)
(set _cond_1 bool (lt count 10))
(ifnot _cond_1 loop_end_1)
(print count)
(goto loop_start_1)
(label loop_end_1)
```

### Break Statement Desugaring

```scheme
; Agent code:
(loop
  (if (eq count 10) (break))
  (set count int (add count 1)))

; Desugars to Core:
(label loop_start_2)
(set _cond_2 bool (eq count 10))
(ifnot _cond_2 skip_break_2)
(goto loop_end_2)
(label skip_break_2)
(set count int (add count 1))
(goto loop_start_2)
(label loop_end_2)
```

---

## Standard Library

AISL provides 180+ built-in functions. All use direct call syntax: `(function arg1 arg2)`.

### Standard Library Modules

Many high-level operations are now implemented in **pure AISL stdlib modules** instead of built-in opcodes. This follows AISL's philosophy: "If it CAN be written in AISL, it MUST be written in AISL."

**Available stdlib modules (14 total):**

**Core (9 modules):**
- `stdlib/core/string_utils.aisl` - Advanced string operations (split, trim, contains, replace, starts_with, ends_with, to_upper, to_lower)
- `stdlib/core/conversion.aisl` - Type conversion (string_from_int, bool_to_int, kilometers_to_miles)
- `stdlib/core/array_utils.aisl` - Array utilities (array_sum, array_product, array_find, array_contains, array_min, array_max, array_reverse, array_fill, array_range)
- `stdlib/core/math.aisl` - Math operations (abs, abs_float, min, max, min_float, max_float)
- `stdlib/core/math_extended.aisl` - Extended math (clamp, sign, lerp, is_even, is_odd, square, cube)
- `stdlib/core/filesystem.aisl` - File utilities (read_file_safe, write_file_safe, delete_if_exists, copy_file, read_lines, count_lines)
- `stdlib/core/network.aisl` - Network utilities (is_valid_port, normalize_path, build_url, build_query_string, parse_url, extract_domain)
- `stdlib/core/text_utils.aisl` - Text utilities (repeat_string, pad_left, pad_right, truncate, word_count, reverse_string, is_empty)
- `stdlib/core/validation.aisl` - Validation (in_range, is_positive, is_negative, is_zero, is_divisible_by)

**Data (1 module):**
- `stdlib/data/json_utils.aisl` - JSON parsing and manipulation (parse, stringify, new_object, new_array, get, set, has, delete, push, length, type)

**Net (1 module):**
- `stdlib/net/http.aisl` - HTTP client operations (get, post, put, delete, parse_response, build_request)

**Pattern (1 module):**
- `stdlib/pattern/regex.aisl` - Regular expression operations (compile, match, find, find_all, replace)

**Database (1 module):**
- `stdlib/db/sqlite.aisl` - SQLite database operations (open, close, exec, query, prepare, bind, step, column, finalize, last_insert_id, changes, error_msg)

**System (1 module):**
- `stdlib/sys/process.aisl` - Process management (spawn, wait, kill, exit, get_pid, get_env, set_env)

**Importing stdlib modules:**

```scheme
(module my_program
  (import json_utils) ; Import from stdlib/data/json_utils.aisl
  (import regex)      ; Import from stdlib/pattern/regex.aisl
  
  (fn main -> int
    ; Use imported functions
    (set json_obj json (json_new_object))
    (json_set json_obj "status" "ok")
    
    (ret 0)))
```

**Note:** String operations like split, to_upper, and to_lower are implemented in stdlib modules (import string_utils). However, string_contains, string_trim, string_replace, string_starts_with, string_ends_with, and string_split are also available as builtins without any import. JSON operations are implemented as builtins (json_parse, json_stringify, etc.) and also available via stdlib.

See `stdlib/README.md` for complete documentation of all stdlib modules.

### Type-Directed Operations

The interpreter infers types automatically. Write operation names without type suffixes:

```scheme
; Arithmetic (works for int, int, float, float)
(add a b)     ; Addition
(sub a b)     ; Subtraction
(mul a b)     ; Multiplication
(div a b)     ; Division
(mod a b)     ; Modulo (integers only)
(neg a)       ; Negation

; Comparison (works for int, int, float, float)
(eq a b)      ; Equal
(ne a b)      ; Not equal
(lt a b)      ; Less than
(gt a b)      ; Greater than
(le a b)      ; Less or equal
(ge a b)      ; Greater or equal

; Math (works for int, int, float, float)
(abs value)   ; Absolute value
(min a b)     ; Minimum
(max a b)     ; Maximum
(sqrt value)  ; Square root (float, float only)
(pow base exp); Power (float, float only)
(floor value) ; Round toward -infinity (float -> int)
(ceil value)  ; Round toward +infinity (float -> int)
(round value) ; Round to nearest (float -> int)
```

The interpreter automatically selects the correct operation based on variable types:
```scheme
(set x int 10)
(set y int 20)
(set sum int (add x y))  ; Interpreter uses add

(set a float 3.14)
(set b float 2.71)
(set result float (mul a b))  ; Interpreter uses mul
```

### String Operations

**Built-in string operations** (always available):

```scheme
(string_length text)              ; Get length -> int
(string_concat a b)               ; Concatenate -> string
(string_equals a b)               ; Compare equality -> bool
(string_slice text start len)     ; Extract substring (start index, length) -> string
(string_format template args...)  ; Format with {} placeholders -> string
(string_find haystack needle)     ; Find index of needle (-1 if not found) -> int
(string_contains haystack needle) ; Check contains -> bool
(string_trim text)                ; Remove whitespace from both ends -> string
(string_replace text old new)     ; Replace ALL occurrences -> string
(string_starts_with text prefix)  ; Check prefix -> bool
(string_ends_with text suffix)    ; Check suffix -> bool
(string_split text delimiter)     ; Split into array -> array
```

**Advanced string operations** (available via `(import string_utils)` — note: trim, contains, replace, starts_with, ends_with are also builtins):

```scheme
(split text delimiter)            ; Split -> array
(trim text)                       ; Remove whitespace -> string
(contains haystack needle)        ; Check contains -> bool
(replace text old new)            ; Replace substring -> string
(starts_with text prefix)         ; Check prefix -> bool
(ends_with text suffix)           ; Check suffix -> bool
(to_upper text)                   ; Convert to uppercase -> string
(to_lower text)                   ; Convert to lowercase -> string
```

**Example:**
```scheme
(module string_demo
  (import string_utils)                ; Import advanced operations
  
  (fn main -> int
    (set text string "  hello world  ")
    (set trimmed string (trim text))           ; -> "hello world"
    (set words array (split trimmed " "))      ; -> ["hello", "world"]
    (set upper string (to_upper trimmed))      ; -> "HELLO WORLD"
    (ret 0)))
```

### Regular Expression Operations

**AISL has full regex support built-in** using POSIX Extended Regular Expression syntax:

```scheme
; Compile a pattern into a regex object
(set pattern string "\\d+")
(set digit_regex regex (regex_compile pattern))

; Test if a string matches the pattern
(set text string "abc123")
(set has_digits bool (regex_match digit_regex text))  ; -> true

; Find first match
(set first string (regex_find digit_regex "foo 123 bar"))  ; -> "123"

; Find all matches (returns array of strings)
(set numbers array (regex_find_all digit_regex "123 456 789"))
; -> ["123", "456", "789"]

; Replace all matches
(set cleaned string (regex_replace digit_regex "foo 123 bar" "NUM"))
; -> "foo NUM bar"
```

**Common regex patterns:**

```scheme
; Match word characters
(set word_pattern string "\\w+")
(set word_regex regex (regex_compile word_pattern))

; Match email addresses
(set email_pattern string "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}")
(set email_regex regex (regex_compile email_pattern))

; Extract function signatures
(set fn_pattern string "\\(fn (\\w+)")
(set fn_regex regex (regex_compile fn_pattern))
(set matches array (regex_find_all fn_regex source_code))
```

**Important**: Remember to escape backslashes in string literals: `"\\d"` not `"\d"`

### I/O Operations

```scheme
(print value)             ; Print any type (polymorphic dispatch)
(println value)           ; Print with newline
(read_line)               ; Read line from stdin -> string
```

### File Operations

```scheme
(file_read path)          ; Read file -> string (panics on error)
(file_write path content) ; Write file -> bool
(file_append path content); Append to file -> bool
(file_exists path)        ; Check exists -> bool
(file_delete path)        ; Delete file -> bool
(file_size path)          ; Get size -> int
```

### System Operations

```scheme
(argv)                    ; Get command-line arguments (after filename) -> array of strings
(argv_count)              ; Get count of extra arguments -> int
```

### Error Handling

AISL supports **try/catch** for recoverable error handling, alongside **guard checks** for predictable errors.

#### Try/Catch

**Syntax:** `(try <body-statements>... (catch <var> <type> <handler-statements>...))`

Catches `RuntimeError` exceptions (division by zero, array out of bounds, file not found, etc.) and binds the error message to the catch variable as a string.

```scheme
; Catch division by zero
(try
  (set result int (div 10 0))
  (catch err string
    (print "Caught error: ")
    (print err)))

; Use catch to provide fallback values
(set val int 0)
(try
  (set val int (array_get arr 999))
  (catch err string
    (set val int -1)))

; Nested try/catch
(try
  (try
    (set x int (div 1 0))
    (catch inner_err string
      (print "Inner caught: ")
      (print inner_err)))
  (print "Outer continues")
  (catch outer_err string
    (print "Outer caught: ")
    (print outer_err)))
```

**Rules:**
- The `(catch ...)` clause must be the **last element** inside the `(try ...)` block
- Catch variable type must be `string` (error messages are always strings)
- Try/catch blocks can be nested — inner catch handles inner errors
- After the catch block completes, execution continues after the try/catch
- If no error occurs, the catch block is skipped entirely

#### Guard Checks (Still Recommended for Simple Cases)

For predictable errors, guard checks are simpler and more explicit:

```scheme
(fn safe_divide a int b int -> int
  (if (eq b 0)
    (ret 0))
  (ret (div a b)))

(fn safe_read path string -> string
  (if (not (file_exists path))
    (ret ""))
  (ret (file_read path)))
```

**When to use which:**
- **Guard checks**: When you know exactly what might fail (division by zero, missing file)
- **Try/catch**: When the error source is less predictable, or when wrapping complex operations that might fail in multiple ways

### TCP Networking

```scheme
(tcp_listen port)           ; Listen -> socket
(tcp_accept server_socket)  ; Accept -> socket
(tcp_connect host port)     ; Connect -> socket
(tcp_send socket data)      ; Send -> int
(tcp_receive socket bytes)  ; Receive -> string
(tcp_close socket)          ; Close socket
```

### HTTP Operations

```scheme
(http_get url)              ; GET -> response
(http_post url body)        ; POST -> response
(http_put url body)         ; PUT -> response
(http_delete url)           ; DELETE -> response
(http_get_status response)  ; Status code -> int
(http_get_body response)    ; Body -> string
```

### JSON Operations

**All JSON operations require `(import json_utils)` from stdlib:**

```scheme
(json_parse text)                    ; Parse JSON string -> json
(json_stringify obj)                 ; Convert to JSON string -> string
(json_new_object)                    ; Create empty object -> json
(json_new_array)                     ; Create empty array -> json
(json_get obj key)                   ; Get value from object -> string
(json_set obj key value)             ; Set value in object
(json_has obj key)                   ; Check if key exists -> bool
(json_delete obj key)                ; Remove key from object
(json_push array_val value)          ; Add element to array
(json_length obj)                    ; Get length -> int
(json_type json_val)                 ; Get JSON type -> string ("object", "array", "string", "number", "bool", "null")
```

**Example:**
```scheme
(module json_demo
  (import json_utils)
  
  (fn main -> int
    ; Parse JSON
    (set json_str string "{\"name\":\"Alice\",\"age\":30}")
    (set obj json (json_parse json_str))
    
    ; Modify JSON
    (set new_obj json (json_new_object))
    (json_set new_obj "status" "active")
    (json_set new_obj "count" "42")
    
    ; Convert back to string
    (set result string (json_stringify new_obj))
    (print result)                ; Prints: {"status":"active","count":"42"}
    
    (ret 0)))
```

### Array Operations

```scheme
(array_new)                  ; Create array
(array_push arr value)       ; Add element
(array_get arr index)        ; Get element
(array_set arr index val)    ; Set element
(array_length arr)           ; Length -> int
```

### Map Operations

```scheme
(map_new)                   ; Create map
(map_set m key value)       ; Set key-value
(map_get m key)             ; Get value
(map_has m key)             ; Check key -> bool
(map_delete m key)          ; Remove key
(map_length m)              ; Size -> int
```

### Type Conversions

```scheme
(cast_int_float value)      ; int -> float
(cast_float_int value)      ; float -> int (truncate)
(cast_int_decimal value)    ; int -> decimal
(cast_decimal_int value)    ; decimal -> int
(cast_float_decimal value)  ; float -> decimal
(cast_decimal_float value)  ; decimal -> float
(string_from_int value)     ; int -> string
(string_from_float value)   ; float -> string
(string_from_bool value)    ; bool -> string
```

### Conditional Functions

```scheme
(if_int condition then else)       ; Conditional int
(if_float condition then else)     ; Conditional float
(if_string condition then else)    ; Conditional string
```

### Garbage Collection

```scheme
(gc_collect)                ; Force collection
(gc_stats)                  ; GC statistics
```

---

## Complete Example: Web Server

```scheme
(module sinatra
  (fn handle_connection client_sock string -> int
    (set request string (tcp_receive client_sock 4096))
    (set has_json bool (string_contains request "GET /hello.json "))
    (set has_html bool (string_contains request "GET /hello "))
    
    (set json_resp string "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}")
    (set html_resp string "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<h1>Hello</h1>")
    (set not_found string "HTTP/1.1 404 Not Found\r\n\r\nNot Found")
    
    (set response string not_found)
    (set response string (if_string has_html html_resp response))
    (set response string (if_string has_json json_resp response))
    
    (tcp_send client_sock response)
    (tcp_close client_sock)
    (ret 0))

  (fn start_server port int -> int
    (print "Server running on http://localhost:8080")
    (set server_sock string (tcp_listen port))
    (loop
      (set client_sock string (tcp_accept server_sock))
      (handle_connection client_sock))
    (ret 0))

  (fn main -> int
    (start_server 8080)
    (ret 0)))
```

This server demonstrates:
- Structured loop (`loop`) for accept loop
- Type-directed operations (no `_int` suffixes needed for comparison)
- String operations
- TCP networking
- Conditional routing with `if_string`

---

## Functions & Scope

### No Closures (By Design)

AISL functions deliberately do **not** capture their defining scope. When a function is called, only other function definitions are visible — regular variables from the outer scope are NOT accessible.

```scheme
(module scope_example
  (fn helper x int -> int
    (ret (mul x 2)))
  
  (fn main -> int
    (set multiplier int 10)
    
    ; helper can be called (functions are visible)
    (set result int (helper 5))       ; Works: returns 10
    
    ; But if helper tried to access 'multiplier', it would fail
    ; Functions only see: their parameters + other functions
    (ret 0)))
```

### Why No Closures?

This is intentional for LLM code generation:

1. **Explicitness**: Function behavior is fully determined by its signature + body
2. **No hidden dependencies**: Reading the function signature tells you ALL its inputs
3. **Predictability**: No spooky action at a distance from captured variables
4. **Debuggability**: No need to trace what was captured when the function was created

### Rules for Function Scope

- Functions **can** call other functions defined in the same module
- Functions **cannot** access variables from outer scopes
- All data must be passed **explicitly as parameters**
- Functions are pure transforms: parameters in, return value out

```scheme
; ❌ WRONG - Trying to use outer variable
(fn main -> int
  (set factor int 5)
  (set result int (apply_factor 10))  ; apply_factor can't see 'factor'!
  (ret result))

; ✅ CORRECT - Pass data explicitly
(fn apply_factor x int factor int -> int
  (ret (mul x factor)))

(fn main -> int
  (set factor int 5)
  (set result int (apply_factor 10 factor))  ; Pass factor as argument
  (ret result))
```

---

## Key Design Principles

1. **Two-Layer Architecture** - Core IR is frozen; Agent layer adds ergonomics
2. **Explicit Types** - Every variable has declared type
3. **Type-Directed Dispatch** - Interpreter infers operation types automatically
4. **Flat Structure** - No complex nested expressions
5. **Structured Control** - `while`/`loop`/`for-each` handled directly by interpreter
6. **Try/Catch + Guard Checks** - Try/catch for recoverable errors; guard checks for predictable ones
7. **Direct Function Calls** - All operations use `(function arg1 arg2)` syntax
8. **No Operator Precedence** - Everything is a function call
9. **S-Expression Syntax** - Lisp-style parenthesized syntax
10. **LLM-First Design** - Optimized for code generation by AI

---

## Execution

```bash
# Run AISL program directly (single-step: parse and execute)
./interpreter/_build/default/vm.exe program.aisl
```

## Test Framework

**CRITICAL:** All test files in `tests/` directory matching `test_*.aisl` MUST use the test framework.

### Required Structure

Every test file must include:
1. **`test-spec`** declarations with `case`, `input`, and `expect` keywords
2. **Functions that return values** - not just print statements
3. **`meta-note`** at the end to document what the test validates

### Example Test File

```scheme
(module test_addition
  (fn add_numbers a int b int -> int
    (ret (add a b)))
  
  (test-spec add_numbers
    (case "adds positive numbers"
      (input 2 3)
      (expect 5))
    (case "adds negative numbers"
      (input -5 -3)
      (expect -8))
    (case "adds zero"
      (input 0 0)
      (expect 0)))
  
  (meta-note "Tests integer addition with various inputs"))
```

### What NOT to Do

**DON'T create test files that:**
- Only print output without returning verifiable values
- Return 0 unconditionally without testing anything
- Lack `test-spec` declarations
- Use comments (AISL doesn't support comments)

### Test Framework Keywords

- **`test-spec`** - Declares test cases for a function
- **`case`** - Individual test case with description
- **`input`** - Arguments to pass to the function
- **`expect`** - Expected return value
- **`meta-note`** - Documents what the test file validates

## File Extensions

- `.aisl` - AISL source files
