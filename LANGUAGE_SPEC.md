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
The ergonomic surface language that LLMs generate. Agent code includes structured control flow (`while`, `loop`, `break`, `continue`) and type-directed operations (`add` instead of `add_i32`). The compiler desugars Agent code to Core IR before execution.

**LLMs write Agent code. The VM runs Core code.**

---

## AISL-Agent Grammar (Surface Language)

This is what you write and what LLMs generate.

### Program Structure

```
program ::= (mod <name> <function>*)

function ::= (fn <name> (<param>*) -> <return_type> <statement>*)

param ::= (<name> <type>)

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

### Simple Example

```scheme
(mod hello
  (fn main () -> i32
    (call print "Hello, World!")
    (ret 0)))
```

---

## Types

### Primitive Types
- **i32** - 32-bit signed integer
- **i64** - 64-bit signed integer
- **f32** - 32-bit floating point
- **f64** - 64-bit floating point
- **bool** - Boolean (true/false)
- **string** - UTF-8 string
- **result** - Result type for error handling (ok or err) - ⚠️ PLANNED, not yet implemented

### Type Annotations

Variables must be explicitly typed:

```scheme
(set count i32 42)
(set name string "Alice")
(set active bool true)
(set price f64 19.99)
```

---

## Control Flow (Agent Layer)

### Structured Loops

**While Loop**: `(while <condition> <statements>...)`

Executes body while condition is true.

```scheme
(fn countdown ((n i32)) -> i32
  (while (call gt n 0)
    (call print_i32 n)
    (set n i32 (call sub n 1)))
  (ret 0))
```

**Infinite Loop**: `(loop <statements>...)`

Executes forever. Use for server loops.

```scheme
(fn start_server ((port i32)) -> i32
  (set server_sock string (call tcp_listen port))
  (loop
    (set client_sock string (call tcp_accept server_sock))
    (call handle_connection client_sock))
  (ret 0))
```

### Loop Control

**Break**: `(break)` - Exit nearest loop immediately

```scheme
(fn find_value ((arr string) (target i32)) -> i32
  (set i i32 0)
  (loop
    (set val i32 (call array_get arr i))
    (set found bool (call eq val target))
    (ifnot found skip)
    (break)
    (label skip)
    (set i i32 (call add i 1)))
  (ret i))
```

**Continue**: `(continue)` - Skip to next iteration

```scheme
(fn sum_positives ((arr string) (n i32)) -> i32
  (set i i32 0)
  (set sum i32 0)
  (while (call lt i n)
    (set val i32 (call array_get arr i))
    (set i i32 (call add i 1))
    (set is_negative bool (call lt val 0))
    (ifnot is_negative no_skip)
    (continue)
    (label no_skip)
    (set sum i32 (call add sum val)))
  (ret sum))
```

### Label-based Control Flow (Core Level)

For complex control flow, use labels and goto:

```scheme
(fn countdown_with_labels ((n i32)) -> i32
  (label loop)
  (set done bool (call le n 0))
  (ifnot done continue)
  (ret 0)
  (label continue)
  (call print_i32 n)
  (set n i32 (call sub n 1))
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
(fn factorial ((n i32)) -> i32
  (set is_base bool (call le n 1))
  (ifnot is_base recurse)
  (ret 1)
  (label recurse)
  (set n_minus_1 i32 (call sub n 1))
  (set result i32 (call factorial n_minus_1))
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
  (set count i32 (call add count 1)))

; Desugars to Core:
(label loop_start_2)
(set _cond_2 bool (call eq count 10))
(ifnot _cond_2 skip_break_2)
(goto loop_end_2)
(label skip_break_2)
(set count i32 (call add count 1))
(goto loop_start_2)
(label loop_end_2)
```

---

## Standard Library

AISL provides 180+ built-in functions. All use explicit `call` syntax.

### Type-Directed Operations

The compiler infers types automatically. Write operation names without type suffixes:

```scheme
; Arithmetic (works for i32, i64, f32, f64)
(call add a b)     ; Addition
(call sub a b)     ; Subtraction
(call mul a b)     ; Multiplication
(call div a b)     ; Division
(call mod a b)     ; Modulo (integers only)
(call neg a)       ; Negation

; Comparison (works for i32, i64, f32, f64)
(call eq a b)      ; Equal
(call ne a b)      ; Not equal
(call lt a b)      ; Less than
(call gt a b)      ; Greater than
(call le a b)      ; Less or equal
(call ge a b)      ; Greater or equal

; Math (works for i32, i64, f32, f64)
(call abs value)   ; Absolute value
(call min a b)     ; Minimum
(call max a b)     ; Maximum
(call sqrt value)  ; Square root (f32, f64 only)
(call pow base exp); Power (f32, f64 only)
```

The compiler automatically selects the correct operation based on variable types:
```scheme
(set x i32 10)
(set y i32 20)
(set sum i32 (call add x y))  ; Compiler uses add_i32

(set a f64 3.14)
(set b f64 2.71)
(set result f64 (call mul a b))  ; Compiler uses mul_f64
```

### String Operations

```scheme
(call string_length text)              ; Get length -> i32
(call string_concat a b)               ; Concatenate -> string
(call string_contains haystack needle) ; Check contains -> bool
(call string_split text delimiter)     ; Split -> array
(call string_trim text)                ; Remove whitespace -> string
(call string_replace text old new)     ; Replace substring -> string
(call string_to_upper text)            ; Convert to uppercase -> string
(call string_to_lower text)            ; Convert to lowercase -> string
(call string_substring text start len) ; Extract substring -> string
```

### I/O Operations

```scheme
(call print text)              ; Print string
(call print_i32 number)        ; Print i32
(call print_i64 number)        ; Print i64
(call print_f32 number)        ; Print f32
(call print_f64 number)        ; Print f64
(call print_bool value)        ; Print bool
```

### File Operations

```scheme
(call file_read path)          ; Read file -> string (panics on error)
(call file_write path content) ; Write file
(call file_append path content); Append to file
(call file_exists path)        ; Check exists -> bool
(call file_delete path)        ; Delete file
(call file_size path)          ; Get size -> i64
```

### Error Handling

**⚠️ NOTE**: Result/Option types are planned but not yet implemented. Current file operations panic on error.

**Current Workaround**: Use `file_exists` to check before reading:

```scheme
(fn safe_read_file ((path string)) -> i32
  (set exists bool (call file_exists path))
  (call ifnot exists handle_error)
  ; File exists, safe to read
  (set content string (call file_read path))
  (call print content)
  (ret 0)
  ; Error path
  (call label handle_error)
  (call print "Error: File does not exist")
  (ret 1))
```

**Future**: Result type operations (planned, not yet implemented):

```scheme
; These operations are NOT yet available:
(call file_read_result path)  ; Returns result type (FUTURE)
(call is_ok result)            ; Check if ok -> bool (FUTURE)
(call is_err result)           ; Check if error -> bool (FUTURE)
(call unwrap result)           ; Extract value (FUTURE)
(call unwrap_or result default); Extract value or default (FUTURE)
(call error_code result)       ; Get error code -> i32 (FUTURE)
(call error_message result)    ; Get error message -> string (FUTURE)
```

### TCP Networking

```scheme
(call tcp_listen port)           ; Listen -> socket
(call tcp_accept server_socket)  ; Accept -> socket
(call tcp_connect host port)     ; Connect -> socket
(call tcp_send socket data)      ; Send -> i32
(call tcp_receive socket bytes)  ; Receive -> string
(call tcp_close socket)          ; Close socket
```

### HTTP Operations

```scheme
(call http_get url)              ; GET -> response
(call http_post url body)        ; POST -> response
(call http_put url body)         ; PUT -> response
(call http_delete url)           ; DELETE -> response
(call http_get_status response)  ; Status code -> i32
(call http_get_body response)    ; Body -> string
```

### JSON Operations

```scheme
(call json_parse text)           ; Parse JSON
(call json_stringify obj)        ; To JSON string
(call json_new_object)           ; Empty object
(call json_new_array)            ; Empty array
(call json_get obj key)          ; Get value
(call json_set obj key value)    ; Set value
(call json_push array value)     ; Add to array
(call json_length obj)           ; Length -> i32
```

### Array Operations

```scheme
(call array_new size)            ; Create array
(call array_push array value)    ; Add element
(call array_get array index)     ; Get element
(call array_set array index val) ; Set element
(call array_length array)        ; Length -> i32
```

### Map Operations

```scheme
(call map_new)                   ; Create map
(call map_set map key value)     ; Set key-value
(call map_get map key)           ; Get value
(call map_has map key)           ; Check key -> bool
(call map_delete map key)        ; Remove key
(call map_length map)            ; Size -> i32
```

### Type Conversions

```scheme
(call cast_i32_i64 value)        ; i32 -> i64
(call cast_i64_i32 value)        ; i64 -> i32 (truncate)
(call cast_i32_f32 value)        ; i32 -> f32
(call cast_i32_f64 value)        ; i32 -> f64
(call cast_f32_i32 value)        ; f32 -> i32 (truncate)
(call cast_f64_i32 value)        ; f64 -> i32 (truncate)
(call string_from_i32 value)     ; i32 -> string
(call string_from_i64 value)     ; i64 -> string
(call string_from_f32 value)     ; f32 -> string
(call string_from_f64 value)     ; f64 -> string
(call string_from_bool value)    ; bool -> string
```

### Conditional Functions

```scheme
(call if_i32 condition then else)    ; Conditional i32
(call if_i64 condition then else)    ; Conditional i64
(call if_f32 condition then else)    ; Conditional f32
(call if_f64 condition then else)    ; Conditional f64
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
(mod sinatra
  (fn handle_connection ((client_sock string)) -> i32
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

  (fn start_server ((port i32)) -> i32
    (call print "Server running on http://localhost:8080")
    (set server_sock string (call tcp_listen port))
    (loop
      (set client_sock string (call tcp_accept server_sock))
      (call handle_connection client_sock))
    (ret 0))

  (fn main () -> i32
    (call start_server 8080)
    (ret 0)))
```

This server demonstrates:
- Structured loop (`loop`) for accept loop
- Type-directed operations (no `_i32` suffixes needed for comparison)
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

## File Extensions

- `.aisl` - AISL-Agent source files
- `.aislc` - Compiled bytecode (Core IR)
