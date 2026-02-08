# AISL Tools

This directory contains utility tools for AISL development, all written in **pure AISL** following the "eat your own dog food" philosophy.

## Test Runners (Pure AISL)

### Quick Testing: `test_runner_limited.aisl`

Tests a hardcoded set of 5 test files. Fast and reliable for quick validation.

**Usage:**
```bash
# Compile
./compiler/c/bin/aislc tools/test_runner_limited.aisl /tmp/test_runner_limited.aislc

# Run
./compiler/c/bin/aisl-run /tmp/test_runner_limited.aislc
```

**Output:**
```
Testing 5 files...
  ✓ test_simple
  ✓ test_if
  ✓ test_while_simple
  ✓ test_string_simple
  ✓ test_array
Passed: 5 / 5
```

**Status:** ✅ Works perfectly

---

### Full Test Suite: `test_runner_simple_loop.aisl`

Discovers and tests ALL test files in `tests/` directory using `dir_list`. Simple output format.

**Usage:**
```bash
# Compile
./compiler/c/bin/aislc tools/test_runner_simple_loop.aisl /tmp/test_runner.aislc

# Run (takes ~2 minutes for 120 tests)
./compiler/c/bin/aisl-run /tmp/test_runner.aislc
```

**Output:**
```
Getting test files...
120
Running tests...
Done:
120
```

**Status:** ✅ Works perfectly - Tests all 120 files successfully

---

### Advanced Test Runner: `test_runner.aisl`

Full-featured test runner with fancy formatting, test name extraction, and detailed output.

**Status:** ⚠️ KNOWN ISSUE - Stack overflow with full 120-test suite
- **Cause:** Complex string operations (`string_replace` + multiple `string_concat` in loop)
- **Workaround:** Use `test_runner_simple_loop.aisl` instead

**When to use:** Once stack overflow issue is resolved, this will be the primary runner.

---

## Design Philosophy

**ALL tooling MUST be written in pure AISL to:**
1. **Dogfood the language** - Discover limitations immediately
2. **Provide working examples** - LLMs learn from real code
3. **Eliminate external dependencies** - No Python, Bash, Node.js, etc.
4. **Prove AISL's completeness** - If it can't be done in AISL, fix AISL!

**No exceptions.** The previous Bash script (`run_tests.sh`) has been deleted.
