# AISL Tools

This directory contains utility tools for AISL development, all written in **pure AISL** following the "eat your own dog food" philosophy.

## Test Runner: `test_runner.aisl`

Discovers and tests ALL test files in `tests/` directory using `dir_list`.

**Usage:**
```bash
# Compile
./compiler/c/bin/aislc tools/test_runner.aisl /tmp/test_runner.aislc

# Run (takes ~2 minutes for 115 tests)
./compiler/c/bin/aisl-run /tmp/test_runner.aislc
```

**Output:**
```
Getting test files...
115
Running tests...
Done:
115
```

**Features:**
- ✅ Auto-discovers test files (no hardcoding)
- ✅ Tests all 115 files in ~2 minutes
- ✅ Clean, simple output
- ✅ Returns count of passed tests

**Exit code:** 0 (always - just counts successful compilations)

---

## Design Philosophy

**ALL tooling MUST be written in pure AISL to:**
1. **Dogfood the language** - Discover limitations immediately
2. **Provide working examples** - LLMs learn from real code
3. **Eliminate external dependencies** - No Python, Bash, Node.js, etc.
4. **Prove AISL's completeness** - If it can't be done in AISL, fix AISL!

**No exceptions.** All tools are pure AISL with zero external dependencies.
