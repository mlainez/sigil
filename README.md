# AISL - AI-Optimized Systems Language

A programming language designed for AI code generation with explicit syntax, zero ambiguity, and flat structure.

## Quick Start

### Hello World

```scheme
(mod hello
  (fn main () -> i32
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

### For AI Code Generators

1. **Zero Ambiguity** - Every construct has exactly one meaning
2. **Explicit Everything** - Types and operations are always explicit
3. **Flat Structure** - No complex nesting
4. **Predictable** - Deterministic behavior
5. **S-Expression Syntax** - Easy to parse and generate

### For Developers

1. **Comprehensive** - Build web servers, APIs, command-line tools
2. **Fast** - Compiled to efficient bytecode
3. **Safe** - Strong typing prevents errors
4. **Batteries Included** - 180+ built-in functions

## Language Features

- **Types**: i32, i64, f32, f64, bool, string
- **Control Flow**: Labels and goto (no while/for/if keywords)
- **Functions**: First-class with recursion support
- **Standard Library**: String ops, file I/O, TCP/HTTP, JSON, regex, crypto
- **No Operator Precedence**: All operations are explicit function calls

## Documentation

- **[LANGUAGE_SPEC.md](LANGUAGE_SPEC.md)** - Complete language specification
- **[examples/](examples/)** - Example programs including a web server

## Examples

### Factorial (Recursion)

```scheme
(mod factorial
  (fn fact ((n i32)) -> i32
    (set is_zero bool (call op_eq_i32 n 0))
    (set result i32 (call if_i32 is_zero 1 0))
    (if is_zero done)
    (set n_minus_1 i32 (call op_sub_i32 n 1))
    (set prev i32 (call fact n_minus_1))
    (set result i32 (call op_mul_i32 n prev))
    (label done)
    (ret result))

  (fn main () -> i32
    (set x i32 (call fact 5))
    (call print_i32 x)
    (ret 0)))
```

### Web Server

```scheme
(mod sinatra
  (fn handle_connection ((client_sock string)) -> i32
    (set request string (call tcp_receive client_sock 4096))
    (set has_json bool (call string_contains request "/hello.json"))
    (set json_resp string "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"message\": \"Hello\"}")
    (set html_resp string "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html><body>Hello</body></html>")
    (set response string (call if_string has_json json_resp html_resp))
    (call tcp_send client_sock response)
    (call tcp_close client_sock)
    (ret 0))

  (fn accept_loop ((server_sock string)) -> i32
    (set client_sock string (call tcp_accept server_sock))
    (call handle_connection client_sock)
    (call accept_loop server_sock)
    (ret 0))

  (fn main () -> i32
    (set server_sock string (call tcp_listen 8080))
    (call accept_loop server_sock)
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

## Design Principles

1. **Explicit Types** - Every variable has a declared type
2. **Flat Structure** - No complex nested expressions
3. **Label-based Control** - Use labels and goto instead of while/for
4. **Function Calls** - All operations use explicit `call` syntax
5. **No Operator Precedence** - No infix operators
6. **Deterministic** - Same input always produces same output
7. **S-Expression Syntax** - Lisp-style parenthesized syntax

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
- Type conversions (cast_i32_i64, cast_f32_i32, etc.)

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
