# AISL Tests

This directory contains test files used during AISL development and testing.

## Directory Contents

This directory contains:
- **Unit tests** - Testing individual language features
- **Integration tests** - Testing combinations of features
- **Debug files** - Experimental code used during debugging
- **Old server implementations** - Various iterations of web server development

## Test Categories

### Language Feature Tests
Tests for core language functionality like:
- Type system (i32, i64, f32, f64, string, bool)
- Control flow (if, while, for, labels/goto)
- Functions and recursion
- Variables and scope
- Operators and comparisons
- String operations
- Arrays and maps

### Standard Library Tests
Tests for the 467-function AISL standard library:
- File I/O operations
- Network operations (TCP, HTTP)
- JSON parsing and manipulation
- Regular expressions
- Process management
- Garbage collection

### Historical Files
- Multiple server implementation attempts (simple_server, echo_server, etc.)
- Sinatra web server iterations (sinatra_debug, sinatra_simple, etc.)
- Debug and verification scripts

## Running Tests

Individual tests can be run with:

```bash
# Compile a test
./compiler/c/bin/aislc tests/test_add.aisl test.aislc

# Run the test
./compiler/c/bin/aisl-run test.aislc
```

## Note

Most files in this directory are for development/debugging purposes and may not represent best practices or final implementations. For production-quality examples, see the `examples/` directory.
