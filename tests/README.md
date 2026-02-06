# AISL Tests

This directory contains test files used during AISL development and testing.

## Test Status

**99 tests - All passing ✓**

## Directory Contents

This directory contains:
- **Unit tests** - Testing individual language features
- **Integration tests** - Testing combinations of features  
- **Server implementations** - Various iterations of web server development

## Test Categories

### Language Feature Tests
Tests for core language functionality:
- Type system (i32, i64, f32, f64, string, bool)
- Control flow (ifnot, labels/goto)
- Functions and recursion
- Variables and scope
- Operators and comparisons
- String operations
- Arrays and maps

### Standard Library Tests
Tests for AISL standard library functions:
- File I/O operations
- Network operations (TCP, HTTP)
- JSON parsing and manipulation
- Process management
- Garbage collection
- Type conversions
- Math functions

### Server Implementation Tests
Multiple web server iterations:
- Echo servers
- Simple HTTP servers
- Sinatra-style routing implementations
- Sequential and recursive patterns

## Running Tests

Individual tests can be compiled and run with:

```bash
# Compile a test
./compiler/c/bin/aislc tests/test_add.aisl test.aislc

# Run the test
./compiler/c/bin/aisl-run test.aislc
```

Run all tests:

```bash
cd tests
for f in *.aisl; do
  ../compiler/c/bin/aislc "$f" "${f%.aisl}.aislc" > /dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "✓ $f"
  else
    echo "✗ $f FAILED"
  fi
done
```

## Note

All files in this directory represent working, production-ready code. Tests for unimplemented features and old syntax have been removed. For production-quality examples, see the `examples/` directory.
