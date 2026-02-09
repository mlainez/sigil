# AISL Tests

Test files for AISL language features and standard library.

## Test Status

**126 tests - All use test-spec format**

## Test Categories

### Language Features
- Type system (int, float, string, bool, decimal, json, regex)
- Control flow (if, while, loop, break, continue)
- Functions and recursion
- Variables and operators
- String operations
- Arrays and maps
- Channels
- Decimal arithmetic

### Standard Library
- File I/O operations
- Network operations (TCP, HTTP, WebSocket)
- JSON parsing and manipulation
- SQLite database
- Process management
- Type conversions
- Math functions
- String utilities
- Regex operations
- Base64 encoding/decoding
- Cryptographic hashing

## Running Tests

Individual test:

```bash
./compiler/c/bin/aislc tests/test_add.aisl /tmp/test.aislc
./compiler/c/bin/aisl-run /tmp/test.aislc
```

All tests:

```bash
cd tests
for f in test_*.aisl; do
  ../compiler/c/bin/aislc "$f" "/tmp/${f%.aisl}.aislc" > /dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "✓ $f"
  else
    echo "✗ $f"
  fi
done
```

## Test Format

All tests use the test-spec format with case/input/expect clauses:

```lisp
(test-spec function_name
  (case "description"
    (input arg1 arg2)
    (expect result)))
```

This ensures tests are verifiable and automated.
