# AISL - AI-Optimized Systems Language

A two-layer programming language designed for LLM code generation with explicit syntax, zero ambiguity, and a stable intermediate representation.

## Architecture: Core + Agent

AISL consists of two layers:

- **AISL-Core** (IR Layer) - A minimal, frozen intermediate representation with only 6 statement types (`set`, `call`, `label`, `goto`, `ifnot`, `ret`). This is what the VM executes and will never change.

- **AISL-Agent** (Surface Language) - An ergonomic surface language with structured control flow (`while`, `loop`, `break`, `continue`) that LLMs generate. The compiler desugars Agent code to Core IR.

**LLMs write Agent code. The VM runs Core code.**

This architecture prevents long-term entropy: the Core IR remains stable forever, while the Agent layer evolves to improve LLM ergonomics.

## Quick Start

### Hello World

```scheme
(module hello
  (fn main () -> int
    (call print "Hello, World!")
    (ret 0)))
```

### Compile and Run

```bash
# Compile
./compiler/c/bin/aislc hello.aisl hello.aislc

# Run
./compiler/c/bin/aisl-run hello.aislc
```

## Why AISL?

### For LLMs (AI Code Generators)

1. **Two-Layer Design** - Stable IR (Core) + Ergonomic surface (Agent)
2. **Zero Ambiguity** - Every construct has exactly one meaning
3. **Type-Directed Operations** - Write `add`, not `add` (compiler infers types)
4. **Explicit Error Handling** - Result type for fallible operations
5. **Flat Structure** - No complex nesting, easy to generate
6. **S-Expression Syntax** - Trivial to parse and generate
7. **Predictable** - Deterministic behavior, same input → same output

### For Developers

1. **Comprehensive** - Build web servers, APIs, CLIs, system tools
2. **Fast** - Compiled to efficient bytecode
3. **Safe** - Strong typing prevents runtime errors
4. **Batteries Included** - 180+ built-in functions
5. **Clear Semantics** - Explicit control flow, no hidden behavior

## Language Features

- **Two-Layer Architecture**: Core IR (frozen) + Agent surface language
- **Types**: int, int, float, float, bool, string, result
- **Control Flow**: Structured loops (`while`, `loop`, `break`, `continue`) desugar to labels/goto
- **Error Handling**: Result type with `is_ok`, `unwrap`, `unwrap_or` operations
- **Type-Directed Operations**: Write `add`, compiler infers `add` vs `add`
- **Functions**: First-class with recursion support
- **Standard Library**: String ops, file I/O, TCP/HTTP, JSON, regex, crypto (180+ functions)
- **No Operator Precedence**: All operations are explicit function calls

## Documentation

- **[LANGUAGE_SPEC.md](LANGUAGE_SPEC.md)** - Complete language specification
- **[examples/](examples/)** - Example programs including a web server

## Examples

### Control Flow

```scheme
; While loop - iterate while condition is true
(fn countdown ((n int)) -> int
  (while (call gt n 0)
    (call print n)
    (set n int (call sub n 1)))
  (ret 0))

; Infinite loop - for servers and event loops
(fn start_server ((port int)) -> int
  (set server_sock string (call tcp_listen port))
  (loop
    (set client_sock string (call tcp_accept server_sock))
    (call handle_connection client_sock))
  (ret 0))

; Break - exit loop early
(fn find_in_array ((arr string) (target int) (n int)) -> int
  (set i int 0)
  (while (call lt i n)
    (set val int (call array_get arr i))
    (set found bool (call eq val target))
    (ifnot found skip)
    (break)
    (label skip)
    (set i int (call add i 1)))
  (ret i))

; Continue - skip to next iteration
(fn count_non_zero ((arr string) (n int)) -> int
  (set i int 0)
  (set count int 0)
  (while (call lt i n)
    (set val int (call array_get arr i))
    (set i int (call add i 1))
    (set is_zero bool (call eq val 0))
    (ifnot is_zero no_skip)
    (continue)
    (label no_skip)
    (set count int (call add count 1)))
  (ret count))
```

### Factorial (Recursion)

```scheme
(module factorial
  (fn fact ((n int)) -> int
    (set is_zero bool (call eq n 0))
    (set result int (call if_int is_zero 1 0))
    (if is_zero done)
    (set n_minus_1 int (call sub n 1))
    (set prev int (call fact n_minus_1))
    (set result int (call mul n prev))
    (label done)
    (ret result))

  (fn main () -> int
    (set x int (call fact 5))
    (call print x)
    (ret 0)))
```

### Web Server

```scheme
(module sinatra
  (fn handle_connection ((client_sock string)) -> int
    (set request string (call tcp_receive client_sock 4096))
    (set has_json bool (call string_contains request "/hello.json"))
    (set json_resp string "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"message\": \"Hello\"}")
    (set html_resp string "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html><body>Hello</body></html>")
    (set response string (call if_string has_json json_resp html_resp))
    (call tcp_send client_sock response)
    (call tcp_close client_sock)
    (ret 0))

  (fn main () -> int
    (set server_sock string (call tcp_listen 8080))
    (loop
      (set client_sock string (call tcp_accept server_sock))
      (call handle_connection client_sock))
    (ret 0)))
```

See [examples/sinatra.aisl](examples/sinatra.aisl) for the full working example.

## Project Structure

```
aisl/
├── README.md                  # This file
├── LANGUAGE_SPEC.md           # Complete language specification
├── compiler/c/                # C compiler and VM
│   ├── bin/
│   │   ├── aislc              # Compiler
│   │   └── aisl-run           # Runtime/VM
│   ├── src/                   # Compiler source code
│   └── Makefile
├── examples/                  # Example programs
│   ├── README.md
│   ├── hello_world.aisl
│   └── sinatra.aisl           # Web server example
└── tests/                     # Test files (111 tests)
```

## Building

```bash
cd compiler/c
make
```

This builds:
- `bin/aislc` - The AISL compiler
- `bin/aisl-run` - The AISL runtime/VM

## Testing

AISL has a built-in test framework. All test files in `tests/` directory must follow these requirements:

### Test File Requirements

**CRITICAL:** Every test file (`test_*.aisl`) MUST include:
1. `test-spec` declarations with `case`, `input`, and `expect` keywords
2. Functions that return verifiable values (not just print statements)
3. `meta-note` at the end documenting what the test validates

**Example:**
```lisp
(module test_addition
  (fn add_numbers ((a int) (b int)) -> int
    (ret (call add a b)))
  
  (test-spec add_numbers
    (case "adds positive numbers"
      (input 2 3)
      (expect 5))
    (case "adds negative numbers"
      (input -5 -3)
      (expect -8)))
  
  (meta-note "Tests integer addition with various inputs"))
```

### Running Tests

```bash
cd compiler/c
./bin/aislc ../tests/test_addition.aisl /tmp/test.aislc
./bin/aisl-run /tmp/test.aislc
```

The test framework automatically validates that function outputs match expected values.

## Design Principles

1. **Two-Layer Architecture** - Frozen Core IR + evolving Agent surface language
2. **Explicit Types** - Every variable has a declared type
3. **Type-Directed Dispatch** - Operations infer types automatically (LLM-friendly)
4. **Flat Structure** - No complex nested expressions
5. **Structured Control** - `while`/`loop`/`break`/`continue` desugar to Core primitives
6. **Explicit Error Handling** - Result type for operations that can fail
7. **Function Calls** - All operations use explicit `call` syntax
8. **No Operator Precedence** - No infix operators
9. **Deterministic** - Same input always produces same output
10. **S-Expression Syntax** - Lisp-style parenthesized syntax
11. **LLM-First Design** - Optimized for code generation by AI

## Standard Library Highlights

### Networking
- TCP server/client (`tcp_listen`, `tcp_accept`, `tcp_send`, `tcp_receive`)
- HTTP requests (`http_get`, `http_post`, `http_put`, `http_delete`)
- WebSocket support

### Data Formats
- JSON parsing and generation
- Base64 encoding/decoding
- Regular expressions

### File System
- File operations (`file_read`, `file_write`, `file_append`)
- Directory operations (`dir_list`, `dir_create`)

### Cryptography
- Hashing (MD5, SHA256)
- HMAC-SHA256

### Type Operations
- String manipulation (split, trim, replace, contains)
- Array operations (push, get, set, length)
- Map operations (get, set, has, delete)
- Type conversions (cast_int_int, cast_float_int, etc.)

### Math
- Arithmetic operations (add, sub, mul, div, mod)
- Comparisons (eq, ne, lt, gt, le, ge)
- Math functions (abs, min, max, sqrt, pow)

See [LANGUAGE_SPEC.md](LANGUAGE_SPEC.md) for the complete list of 180+ built-in functions.

## File Extensions

- `.aisl` - AISL source code
- `.aislc` - Compiled bytecode

## License

[License information to be added]

---

**AISL - Designed for AI, Built for Everyone.**
