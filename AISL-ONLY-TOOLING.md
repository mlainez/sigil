# AISL-ONLY TOOLING DIRECTIVE

## 🚨 CRITICAL RULE: NO PYTHON, NO BASH, ONLY AISL

**Every utility script, converter, tool, or automation in this project MUST be written in pure AISL.**

This is not a suggestion. This is a core design principle.

## Why This Matters

### 1. **Immediate Gap Discovery**
When you try to write a real tool in AISL, you discover what's missing immediately.
- Need regex? Find it exists (vm.c:3593)
- Need file I/O? Find it exists (compiler.c:1800+)
- Need string ops? Find them all (compiler.c:1600+)

### 2. **Living Examples**
Every script becomes a working example that LLMs can learn from.
- `scripts/convert_syntax.aisl` - regex, file I/O, string manipulation
- `tests/test_*.aisl` - test framework, assertions
- Future: build.aisl, docs_gen.aisl, etc.

### 3. **Zero Dependencies**
AISL programs run on the AISL VM. No Python, no Node, no external tools.
This makes the project self-contained and portable.

### 4. **Forces Completeness**
If AISL can't do something you need:
- **GOOD**: You found a gap, add it to AISL
- **BAD**: You work around it with Python

## The Python Trap

When you write Python instead of AISL:
- ❌ You avoid making AISL better
- ❌ You create external dependencies
- ❌ You produce no example code
- ❌ You don't validate AISL's expressiveness

When you write AISL:
- ✅ You discover what's missing
- ✅ You add features to fill gaps
- ✅ You create examples
- ✅ You prove AISL works

## Process

### When you need a script:

1. **Check AISL stdlib** - Does the operation exist?
   - `grep "operation_name" compiler/c/src/compiler.c`
   - Check vm.c for implementations
   - Read LANGUAGE_SPEC.md section 5

2. **Write in AISL** - Start coding
   - Use existing ops
   - Leverage regex, file I/O, strings, arrays

3. **If missing ops** - Extend AISL
   - Add to vm.c (implementation)
   - Add to compiler.c (compiler support)
   - Add to runtime.c (registration)
   - Update docs

4. **Never fallback** - No Python/Bash
   - If you wrote Python, DELETE IT
   - Rewrite in AISL
   - Fix any AISL gaps you find

## Examples

### ✅ CORRECT: Pure AISL

```lisp
; scripts/convert_syntax.aisl
(mod convert_syntax
  (fn convert_file path string -> int
    (set content string (call file_read path))
    (set pattern string "\\(\\(.*\\)\\)")
    (set regex regex (call regex_compile pattern))
    (set result string (call regex_replace regex content "..."))
    (call file_write path result)
    (ret 0)))
```

### ❌ WRONG: Python fallback

```python
# scripts/convert_syntax.py
def convert_file(path):
    with open(path) as f:
        content = f.read()
    # ... conversion logic
    with open(path, 'w') as f:
        f.write(result)
```

## Current Status

**Scripts that are AISL** ✅:
- `scripts/convert_syntax.aisl` - Syntax converter (regex, file I/O)
- All tests in `tests/` - Test framework examples

**Scripts that need conversion** ❌:
- `scripts/convert_syntax.py` - DELETE after AISL version works
- Any build scripts - TODO: write build.aisl
- Any code generators - TODO: write in AISL

## Enforcement

When reviewing code or generating scripts:

1. **First check**: Is this a script/tool?
2. **Second check**: Is it written in AISL?
3. **If not AISL**: STOP and rewrite in AISL

No exceptions. No "temporary" Python scripts. No "quick" Bash hacks.

**AISL only. Always.**

## Benefits So Far

We discovered:
- ✅ Regex exists and works (was going to "implement" it!)
- ✅ File I/O complete
- ✅ String ops comprehensive
- ✅ Array operations sufficient

None of this would have been discovered if we defaulted to Python.

## Remember

**If AISL can't do what you need, that's not a problem with your task.**  
**That's a gap in AISL that needs filling.**

Make AISL complete. Don't work around it.
