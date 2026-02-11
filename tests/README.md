# AISL Tests

Test files for AISL language features and standard library.

## Test Status

**126 tests - All passing, all use test-spec format**

## Test Categories

### Language Features
- Type system (int, float, string, bool, decimal, json, regex)
- Control flow (if, if-else, while, loop, for-each, break, continue)
- Functions and recursion
- Variables and operators
- Short-circuit boolean operators (and, or)
- String operations (including string_format, string_find)
- Arrays and maps
- Channels
- Decimal arithmetic
- Type enforcement (runtime type checking on set)

### Standard Library
- File I/O operations
- Network operations (TCP, HTTP, WebSocket)
- JSON parsing and manipulation
- SQLite database
- Process management
- Type conversions
- Math functions
- String utilities
- Regex operations (POSIX extended via OCaml Str)
- Base64 encoding/decoding
- Cryptographic hashing

## Running Tests

Individual test:

```bash
./interpreter/_build/default/vm.exe tests/test_add.aisl
```

All tests:

```bash
total=0; passed=0; for f in tests/test_*.aisl; do total=$((total+1)); timeout 5 ./interpreter/_build/default/vm.exe "$f" >/dev/null 2>&1 && passed=$((passed+1)); done; echo "$passed/$total"
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
