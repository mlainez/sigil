# AISL Tools

Utility tools for AISL development, written in **pure AISL**.

## Test Runner: `test_runner.aisl`

Simple informational tool about the test suite.

**Usage:**
```bash
# Compile
./compiler/c/bin/aislc tools/test_runner.aisl /tmp/test_runner.aislc

# Run
./compiler/c/bin/aisl-run /tmp/test_runner.aislc
```

**Output:**
```
AISL Test Runner - Sample Tests
Results:
10
sample tests passed
0
failed

Note: Run manual compilation test with:
  for f in tests/test_*.aisl; do ./compiler/c/bin/aislc $f /tmp/test.aislc && echo PASS || echo FAIL; done
```

**Current Status:**
- Total tests: 126
- All tests compile successfully
- All use test-spec format

**To run all tests manually:**
```bash
cd tests
for f in test_*.aisl; do
  ../compiler/c/bin/aislc "$f" "/tmp/${f%.aisl}.aislc" && echo "✓ $f" || echo "✗ $f"
done
```

---

## Design Philosophy

**ALL tooling MUST be written in pure AISL to:**
1. **Dogfood the language** - Discover limitations immediately
2. **Provide working examples** - LLMs learn from real code
3. **Eliminate external dependencies** - No Python, Bash, Node.js, etc.
4. **Prove AISL's completeness** - If it can't be done in AISL, fix AISL!

**No exceptions.** All tools are pure AISL with zero external dependencies.
