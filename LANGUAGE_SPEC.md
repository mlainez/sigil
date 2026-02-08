# AISL Language Specification

AISL (AI-Optimized Systems Language) - A two-layer programming language designed for LLM code generation with explicit syntax, zero ambiguity, and stable IR.

## Architecture: Two Layers

AISL consists of two distinct layers:

### AISL-Core (IR Layer)
The minimal, stable intermediate representation that the VM executes. This layer is **frozen** - it will never change. Core consists of only 6 statement types:
- `set` - Variable binding
- `call` - Function calls
- `label` - Jump targets
- `goto` - Unconditional jumps
- `ifnot` - Conditional jumps
- `ret` - Return from function

### AISL-Agent (Surface Layer)
The ergonomic surface language that LLMs generate. Agent code includes structured control flow (`while`, `loop`, `break`, `continue`) and type-directed operations (`add` instead of `add`). The compiler desugars Agent code to Core IR before execution.

**LLMs write Agent code. The VM runs Core code.**

---

## AISL-Agent Grammar (Surface Language)

This is what you write and what LLMs generate.

### Program Structure

```
program ::= (module <name> <function>*)

function ::= (fn <name> <param_flat>* -> <return_type> <statement>*)
           | (fn <name> (<param>*) -> <return_type> <statement>*)   [deprecated]

param_flat ::= <name> <type>  [NEW: Recommended for LLM code generation]

param ::= (<name> <type>)      [OLD: Still supported for backward compatibility]

statement ::= (set <var> <type> <expr>)
            | (call <function> <arg>*)
            | (label <name>)
            | (goto <label>)
            | (ifnot <bool_var> <label>)
            | (while <bool_expr> <statement>*)
            | (loop <statement>*)
            | (break)
            | (continue)
            | (ret <expr>)

expr ::= <literal>
       | <variable>
       | (call <function> <arg>*)

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
    (call print "Hello, World!")
    (ret 0)))
```

**Backward Compatibility Note**: The old nested parameter syntax `(fn main () -> int)` is still supported, but the new flat syntax `(fn main -> int)` is recommended for LLM code generation as it eliminates visual ambiguity.

---

## Types

### Primitive Types
- **int** - 32-bit signed integer
- **int** - 64-bit signed integer
- **float** - 32-bit floating point
- **float** - 64-bit floating point
- **bool** - Boolean (true/false)
- **string** - UTF-8 string
- **regex** - Compiled regular expression pattern
- **array** - Dynamic array
- **map** - Hash map
- **result** - Result type for error handling (ok or err)

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

### Structured Loops

**While Loop**: `(while <condition> <statements>...)`

Executes body while condition is true.

```scheme
(fn countdown n int -> int
  (while (call gt n 0)
    (call print n)
    (set n int (call sub n 1)))
  (ret 0))
```

**Infinite Loop**: `(loop <statements>...)`

Executes forever. Use for server loops.

```scheme
(fn start_server port int -> int
  (set server_sock string (call tcp_listen port))
  (loop
    (set client_sock string (call tcp_accept server_sock))
    (call handle_connection client_sock))
  (ret 0))
```

### Loop Control

**Break**: `(break)` - Exit nearest loop immediately

```scheme
(fn find_value arr string target int -> int
  (set i int 0)
  (loop
    (set val int (call array_get arr i))
    (set found bool (call eq val target))
    (ifnot found skip)
    (break)
    (label skip)
    (set i int (call add i 1)))
  (ret i))
```

**Continue**: `(continue)` - Skip to next iteration

```scheme
(fn sum_positives arr string n int -> int
  (set i int 0)
  (set sum int 0)
  (while (call lt i n)
    (set val int (call array_get arr i))
    (set i int (call add i 1))
    (set is_negative bool (call lt val 0))
    (ifnot is_negative no_skip)
    (continue)
    (label no_skip)
    (set sum int (call add sum val)))
  (ret sum))
```

### Label-based Control Flow (Core Level)

For complex control flow, use labels and goto:

```scheme
(fn countdown_with_labels n int -> int
  (label loop)
  (set done bool (call le n 0))
  (ifnot done continue)
  (ret 0)
  (label continue)
  (call print n)
  (set n int (call sub n 1))
  (goto loop))
```

**Statement**: `(ifnot <bool_var> <label>)` - Jump to label if variable is false

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
  (set is_base bool (call le n 1))
  (ifnot is_base recurse)
  (ret 1)
  (label recurse)
  (set n_minus_1 int (call sub n 1))
  (set result int (call factorial n_minus_1))
  (ret (call mul n result)))
```

---

## How Agent Code Desugars to Core

### While Loop Desugaring

```scheme
; Agent code:
(while (call lt count 10)
  (call print count))

; Desugars to Core:
(label loop_start_1)
(set _cond_1 bool (call lt count 10))
(ifnot _cond_1 loop_end_1)
(call print count)
(goto loop_start_1)
(label loop_end_1)
```

### Break Statement Desugaring

```scheme
; Agent code:
(loop
  (if (call eq count 10) (break))
  (set count int (call add count 1)))

; Desugars to Core:
(label loop_start_2)
(set _cond_2 bool (call eq count 10))
(ifnot _cond_2 skip_break_2)
(goto loop_end_2)
(label skip_break_2)
(set count int (call add count 1))
(goto loop_start_2)
(label loop_end_2)
```

---

## Standard Library

AISL provides 180+ built-in functions. All use explicit `call` syntax.

### Standard Library Modules

Many high-level operations are now implemented in **pure AISL stdlib modules** instead of built-in opcodes. This follows AISL's philosophy: "If it CAN be written in AISL, it MUST be written in AISL."

**Available stdlib modules (11 total):**

**Core (2 modules):**
- `stdlib/core/result.aisl` - Result type for error handling (ok, err, is_ok, is_err, unwrap, unwrap_or, error_code, error_message)
- `stdlib/core/string_utils.aisl` - Advanced string operations (split, trim, contains, replace, starts_with, ends_with, to_upper, to_lower)

**Data (2 modules):**
- `stdlib/data/json.aisl` - JSON parsing and manipulation (parse, stringify, new_object, new_array, get, set, has, delete, push, length, type)
- `stdlib/data/base64.aisl` - Base64 encoding/decoding (encode, decode)

**Net (2 modules):**
- `stdlib/net/http.aisl` - HTTP client operations (get, post, put, delete, parse_response, build_request)
- `stdlib/net/websocket.aisl` - WebSocket client (connect, send, receive, close)

**Pattern (1 module):**
- `stdlib/pattern/regex.aisl` - Regular expression operations (compile, match, find, find_all, replace)

**Crypto (1 module):**
- `stdlib/crypto/hash.aisl` - Cryptographic hash functions (sha256, md5, sha1)

**Database (1 module):**
- `stdlib/db/sqlite.aisl` - SQLite database operations (open, close, exec, query, prepare, bind, step, column, finalize, last_insert_id, changes, error_msg)

**System (2 modules):**
- `stdlib/sys/time.aisl` - Time operations (unix_timestamp, sleep, format_time)
- `stdlib/sys/process.aisl` - Process management (spawn, wait, kill, exit, get_pid, get_env, set_env)

**Importing stdlib modules:**

```scheme
(module my_program
  (import result)                    ; Import from stdlib/core/result.aisl
  (import json)                      ; Import from stdlib/data/json.aisl
  (import regex from pattern)        ; Import from stdlib/pattern/regex.aisl
  
  (fn main -> int
    ; Use imported functions
    (set result_val result (call ok "success!"))
    (set is_success bool (call is_ok result_val))
    
    (set json_obj json (call new_object))
    (call set json_obj "status" "ok")
    
    (ret 0)))
```

**Note:** String operations (split, trim, replace, etc.), JSON operations, Result type functions, and Base64 functions are no longer built-in opcodes - they are now implemented in stdlib modules. Import the appropriate module to use them.

See `stdlib/README.md` for complete documentation of all stdlib modules.

### Type-Directed Operations

The compiler infers types automatically. Write operation names without type suffixes:

```scheme
; Arithmetic (works for int, int, float, float)
(call add a b)     ; Addition
(call sub a b)     ; Subtraction
(call mul a b)     ; Multiplication
(call div a b)     ; Division
(call mod a b)     ; Modulo (integers only)
(call neg a)       ; Negation

; Comparison (works for int, int, float, float)
(call eq a b)      ; Equal
(call ne a b)      ; Not equal
(call lt a b)      ; Less than
(call gt a b)      ; Greater than
(call le a b)      ; Less or equal
(call ge a b)      ; Greater or equal

; Math (works for int, int, float, float)
(call abs value)   ; Absolute value
(call min a b)     ; Minimum
(call max a b)     ; Maximum
(call sqrt value)  ; Square root (float, float only)
(call pow base exp); Power (float, float only)
```

The compiler automatically selects the correct operation based on variable types:
```scheme
(set x int 10)
(set y int 20)
(set sum int (call add x y))  ; Compiler uses add

(set a float 3.14)
(set b float 2.71)
(set result float (call mul a b))  ; Compiler uses mul
```

### String Operations

**Built-in string operations** (always available):

```scheme
(call string_length text)              ; Get length -> int
(call string_concat a b)               ; Concatenate -> string
(call string_substring text start len) ; Extract substring -> string
```

**Advanced string operations** (require `(import string_utils)`):

```scheme
(call split text delimiter)            ; Split -> array
(call trim text)                       ; Remove whitespace -> string
(call contains haystack needle)        ; Check contains -> bool
(call replace text old new)            ; Replace substring -> string
(call starts_with text prefix)         ; Check prefix -> bool
(call ends_with text suffix)           ; Check suffix -> bool
(call to_upper text)                   ; Convert to uppercase -> string
(call to_lower text)                   ; Convert to lowercase -> string
```

**Example:**
```scheme
(module string_demo
  (import string_utils)                ; Import advanced operations
  
  (fn main -> int
    (set text string "  hello world  ")
    (set trimmed string (call trim text))           ; -> "hello world"
    (set words array (call split trimmed " "))      ; -> ["hello", "world"]
    (set upper string (call to_upper trimmed))      ; -> "HELLO WORLD"
    (ret 0)))
```

### Regular Expression Operations

**AISL has full regex support built-in** using POSIX Extended Regular Expression syntax:

```scheme
; Compile a pattern into a regex object
(set pattern string "\\d+")
(set digit_regex regex (call regex_compile pattern))

; Test if a string matches the pattern
(set text string "abc123")
(set has_digits bool (call regex_match digit_regex text))  ; -> true

; Find first match
(set first string (call regex_find digit_regex "foo 123 bar"))  ; -> "123"

; Find all matches (returns array of strings)
(set numbers array (call regex_find_all digit_regex "123 456 789"))
; -> ["123", "456", "789"]

; Replace all matches
(set cleaned string (call regex_replace digit_regex "foo 123 bar" "NUM"))
; -> "foo NUM bar"
```

**Common regex patterns:**

```scheme
; Match word characters
(set word_pattern string "\\w+")
(set word_regex regex (call regex_compile word_pattern))

; Match email addresses
(set email_pattern string "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}")
(set email_regex regex (call regex_compile email_pattern))

; Extract function signatures
(set fn_pattern string "\\(fn (\\w+)")
(set fn_regex regex (call regex_compile fn_pattern))
(set matches array (call regex_find_all fn_regex source_code))
```

**Important**: Remember to escape backslashes in string literals: `"\\d"` not `"\d"`

### I/O Operations

```scheme
(call print text)              ; Print string
(call print number)        ; Print int
(call print number)        ; Print int
(call print number)        ; Print float
(call print number)        ; Print float
(call print_bool value)        ; Print bool
```

### File Operations

```scheme
(call file_read path)          ; Read file -> string (panics on error)
(call file_write path content) ; Write file
(call file_append path content); Append to file
(call file_exists path)        ; Check exists -> bool
(call file_delete path)        ; Delete file
(call file_size path)          ; Get size -> int
```

### Error Handling

**Result type is now implemented in `stdlib/core/result.aisl`!**

AISL uses the Result type for explicit error handling. Import the result module to use it:

```scheme
(module error_handling_demo
  (import result)
  
  (fn safe_divide ((a int) (b int)) -> result
    (set is_zero bool (call eq b 0))
    (if is_zero
      (ret (call err 1 "Division by zero")))
    (set quotient int (call div a b))
    (ret (call ok quotient)))
  
  (fn main -> int
    (set result1 result (call safe_divide 10 2))
    (set success bool (call is_ok result1))
    
    (if success
      (set value string (call unwrap result1))
      (call print "Success:")
      (call print value))
    
    (set result2 result (call safe_divide 10 0))
    (set is_error bool (call is_err result2))
    
    (if is_error
      (set code int (call error_code result2))
      (set msg string (call error_message result2))
      (call print "Error code:")
      (call print code)
      (call print "Error message:")
      (call print msg))
    
    (ret 0)))
```

**Result type operations** (require `(import result)`):

```scheme
(call ok value)                 ; Create success result with value
(call err code message)         ; Create error result with code and message
(call is_ok result)             ; Check if result is ok -> bool
(call is_err result)            ; Check if result is error -> bool
(call unwrap result)            ; Extract value (panics if error) -> string
(call unwrap_or result default) ; Extract value or return default -> string
(call error_code result)        ; Get error code -> int
(call error_message result)     ; Get error message -> string
```

**File operations with Result type:**

Some file operations have `_result` variants that return Result instead of panicking:

```scheme
(fn safe_read_file path string -> int
  (set result result (call file_read_result path))
  (set success bool (call is_ok result))
  
  (if success
    (set content string (call unwrap result))
    (call print content)
    (ret 0))
  
  ; Handle error
  (set msg string (call error_message result))
  (call print "Error reading file:")
  (call print msg)
  (ret 1))
```

### TCP Networking

```scheme
(call tcp_listen port)           ; Listen -> socket
(call tcp_accept server_socket)  ; Accept -> socket
(call tcp_connect host port)     ; Connect -> socket
(call tcp_send socket data)      ; Send -> int
(call tcp_receive socket bytes)  ; Receive -> string
(call tcp_close socket)          ; Close socket
```

### HTTP Operations

```scheme
(call http_get url)              ; GET -> response
(call http_post url body)        ; POST -> response
(call http_put url body)         ; PUT -> response
(call http_delete url)           ; DELETE -> response
(call http_get_status response)  ; Status code -> int
(call http_get_body response)    ; Body -> string
```

### JSON Operations

**All JSON operations require `(import json)` from stdlib:**

```scheme
(call parse text)                    ; Parse JSON string -> json
(call stringify obj)                 ; Convert to JSON string -> string
(call new_object)                    ; Create empty object -> json
(call new_array)                     ; Create empty array -> json
(call get obj key)                   ; Get value from object -> string
(call set obj key value)             ; Set value in object
(call has obj key)                   ; Check if key exists -> bool
(call delete obj key)                ; Remove key from object
(call push array value)              ; Add element to array
(call length obj)                    ; Get length -> int
(call type json_val)                 ; Get JSON type -> string ("object", "array", "string", "number", "bool", "null")
```

**Example:**
```scheme
(module json_demo
  (import json from data)
  
  (fn main -> int
    ; Parse JSON
    (set json_str string "{\"name\":\"Alice\",\"age\":30}")
    (set obj json (call parse json_str))
    
    ; Modify JSON
    (set new_obj json (call new_object))
    (call set new_obj "status" "active")
    (call set new_obj "count" "42")
    
    ; Convert back to string
    (set result string (call stringify new_obj))
    (call print result)                ; Prints: {"status":"active","count":"42"}
    
    (ret 0)))
```

### Array Operations

```scheme
(call array_new size)            ; Create array
(call array_push array value)    ; Add element
(call array_get array index)     ; Get element
(call array_set array index val) ; Set element
(call array_length array)        ; Length -> int
```

### Map Operations

```scheme
(call map_new)                   ; Create map
(call map_set map key value)     ; Set key-value
(call map_get map key)           ; Get value
(call map_has map key)           ; Check key -> bool
(call map_delete map key)        ; Remove key
(call map_length map)            ; Size -> int
```

### Type Conversions

```scheme
(call cast_int_int value)        ; int -> int
(call cast_int_int value)        ; int -> int (truncate)
(call cast_int_float value)        ; int -> float
(call cast_int_float value)        ; int -> float
(call cast_float_int value)        ; float -> int (truncate)
(call cast_float_int value)        ; float -> int (truncate)
(call string_from_int value)     ; int -> string
(call string_from_int value)     ; int -> string
(call string_from_float value)     ; float -> string
(call string_from_float value)     ; float -> string
(call string_from_bool value)    ; bool -> string
```

### Conditional Functions

```scheme
(call if_int condition then else)    ; Conditional int
(call if_int condition then else)    ; Conditional int
(call if_float condition then else)    ; Conditional float
(call if_float condition then else)    ; Conditional float
(call if_string condition then else) ; Conditional string
```

### Garbage Collection

```scheme
(call gc_collect)                ; Force collection
(call gc_stats)                  ; GC statistics
```

---

## Complete Example: Web Server

```scheme
(module sinatra
  (fn handle_connection ((client_sock string)) -> int
    (set request string (call tcp_receive client_sock 4096))
    (set has_json bool (call string_contains request "GET /hello.json "))
    (set has_html bool (call string_contains request "GET /hello "))
    
    (set json_resp string "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}")
    (set html_resp string "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<h1>Hello</h1>")
    (set not_found string "HTTP/1.1 404 Not Found\r\n\r\nNot Found")
    
    (set response string not_found)
    (set response string (call if_string has_html html_resp response))
    (set response string (call if_string has_json json_resp response))
    
    (call tcp_send client_sock response)
    (call tcp_close client_sock)
    (ret 0))

  (fn start_server ((port int)) -> int
    (call print "Server running on http://localhost:8080")
    (set server_sock string (call tcp_listen port))
    (loop
      (set client_sock string (call tcp_accept server_sock))
      (call handle_connection client_sock))
    (ret 0))

  (fn main () -> int
    (call start_server 8080)
    (ret 0)))
```

This server demonstrates:
- Structured loop (`loop`) for accept loop
- Type-directed operations (no `_int` suffixes needed for comparison)
- String operations
- TCP networking
- Conditional routing with `if_string`

---

## Key Design Principles

1. **Two-Layer Architecture** - Core IR is frozen; Agent layer adds ergonomics
2. **Explicit Types** - Every variable has declared type
3. **Type-Directed Dispatch** - Compiler infers operation types automatically
4. **Flat Structure** - No complex nested expressions
5. **Structured Control** - `while`/`loop` desugar to labels/goto
6. **Explicit Error Handling** - Result type for fallible operations
7. **Function Calls** - All operations use explicit `call` syntax
8. **No Operator Precedence** - Everything is a function call
9. **S-Expression Syntax** - Lisp-style parenthesized syntax
10. **LLM-First Design** - Optimized for code generation by AI

---

## Compilation and Execution

```bash
# Compile AISL-Agent source to bytecode (via Core IR)
./compiler/c/bin/aislc program.aisl program.aislc

# Run bytecode
./compiler/c/bin/aisl-run program.aislc

# View desugared Core IR (for debugging)
./compiler/c/bin/aislc --emit-core program.aisl
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
  (fn add_numbers ((a int) (b int)) -> int
    (ret (call add a b)))
  
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

- `.aisl` - AISL-Agent source files
- `.aislc` - Compiled bytecode (Core IR)
