# AISL Test Suite Status

**Last Updated:** 2026-02-07  
**Test Suite:** 127/137 passing (92.7%) ✅

---

## Summary

After fixing critical test-spec segfault bug:
- **Compile errors:** 9 tests (missing custom helper functions - test quality issues)
- **Runtime errors:** 1 test (type mismatch in test code)
- **Passing:** 127 tests

---

## Progress History

| Commit | Passing | Total | Rate | Change | Notes |
|--------|---------|-------|------|--------|-------|
| Initial | 86/136 | 136 | 63.2% | Baseline | Pre-stdlib migration |
| After i32/f32 fixes | 99/136 | 136 | 72.7% | +13 tests | Type fixes |
| After stdlib functions | 104/137 | 137 | 75.9% | +5 tests | Added missing stdlib funcs |
| **After test-spec fix** | **127/137** | **137** | **92.7%** | **+23 tests** | **Fixed segfault bug** |

---

## The Critical Bug (FIXED ✅)

**Problem:** Test-spec tests segfaulted when importing any stdlib module

**Root Cause:** In `compiler/c/src/compiler.c` lines 2444-2454, when generating a dummy `main()` function for test-spec modules, the compiler was:
1. Declaring the main function
2. Emitting bytecode instructions for the function body
3. **BUT never calling `bytecode_set_function_start()` to set the instruction offset**

This caused the VM to jump to invalid memory when trying to execute main.

**Fix Applied (commit fbed0b3):**
```c
// Added line 2450:
bytecode_set_function_start(comp->program, main_idx, comp->program->instruction_count);
```

**Impact:**
- Fixed 23 segfaulting tests with 1 line of code
- All stdlib imports now work correctly with test-spec
- Test suite jumped from 75.9% to 92.7% passing

---

## Remaining Issues (10 tests)

### Compilation Failures (9 tests) - Test Quality Issues

These tests call helper functions that were never implemented. They are **not framework bugs**.

**Tests with missing custom functions:**
1. `test_both_modules.aisl` - calls `build_object_one()` (doesn't exist)
2. `test_final_http_json.aisl` - calls `build_object_one()` (doesn't exist)
3. `test_http_json_modules.aisl` - calls `build_object_one()` (doesn't exist)
4. `test_json_only.aisl` - calls `build_object_one()` (doesn't exist)
5. `test_json_simple.aisl` - calls `build_object_one()` (doesn't exist)  
6. `test_json_test.aisl` - imports `json_test` module (doesn't exist)
7. `test_json_utils.aisl` - calls `build_object_one()` (doesn't exist)
8. `test_json_utils_module.aisl` - calls `get_length()` (doesn't exist)
9. `test_working_modules.aisl` - imports `math`, `array_utils`, `conversion` (don't exist)

**Common missing functions:**
- `build_object_one(key, value)` - should be `json_new_object()` + `json_set()`
- `to_string(obj)` - should be `json_stringify()`
- `from_string(text)` - should be `json_parse()`
- `is_object()`, `is_array()`, `get_length()` - never implemented

**Fix:** Rewrite these 9 tests to use actual stdlib functions, or delete them as they appear to be experimental/incomplete tests.

### Runtime Error (1 test) - Test Code Bug

**test_json_type_debug.aisl** - Type mismatch causing floating point exception:
- Line 18: `(set arr_type string (call json_type arr))`
- `arr` is an `array` (from `json_new_array`)
- But `json_type` expects a `map` parameter
- This is a bug in the test code, not the framework

**Fix:** Either:
1. Change `json_type` to accept both map and array
2. Fix the test to not call `json_type` on arrays

---

## Known Compiler/Language Bugs

### Bug #1: Nested Returns in If Statements (UNFIXED)

**Status:** Known issue, workaround available

**Problem:**
```lisp
(fn example flag bool -> string
  (if flag
    (ret "yes"))  ; ❌ Execution continues after this!
  (ret "no"))
```

**Workaround:**
```lisp
(fn example flag bool -> string
  (set result string "no")
  (if flag
    (set result string "yes"))
  (ret result))  ; ✅ Single return at end
```

**Impact:** Affects any function with conditional returns. Medium severity.

**Location:** Likely in `compiler/c/src/desugar.c` - if statement desugaring doesn't properly handle return statements.

---

## Passing Test Categories (127 tests)

### Core Language (25 tests)
- Arithmetic, comparisons, type conversions
- Control flow (if, while, loop, break, continue)
- Functions, recursion, parameters
- Variables, locals, scope

### Data Structures (18 tests)
- Arrays: creation, access, modification, iteration
- Maps: creation, get/set, has/delete, keys
- Strings: concatenation, length, substring, comparison

### Stdlib Modules (42 tests) ✅
- **string_utils** (11 tests): split, trim, contains, replace, reverse
- **result** (4 tests): ok, err, is_ok, is_err, unwrap, error_code
- **json_utils** (6 tests): parse, stringify, new_object, set/get
- **http** (2 tests): get_status_text
- Mixed module tests (19 tests)

### I/O & Files (8 tests)
- Print, print_ln (polymorphic)
- File read/write/append/exists/delete
- Path operations

### Networking (5 tests)
- TCP listen/accept/connect/send/receive
- Basic server patterns

### Test Framework (29 tests)
- test-spec with input/expect
- Multiple test cases per function
- Edge cases and error conditions

---

## Next Steps

1. **Fix the 9 test quality issues:**
   - Rewrite tests to use actual stdlib functions
   - Or delete experimental/incomplete tests
   - Target: 136/137 tests passing

2. **Fix test_json_type_debug runtime error:**
   - Make `json_type` polymorphic (accept map or array)
   - Or fix test to not call it on arrays
   - Target: 137/137 tests passing (100%)

3. **Fix nested return bug (optional):**
   - Debug desugar.c if statement handling
   - Ensure return inside if properly terminates function
   - Update documentation when fixed

---

## What Was Fixed This Session

### Critical Bug: Test-Spec Segfault with Imports (commit fbed0b3)
- Added missing `bytecode_set_function_start()` call
- Fixed 23 segfaulting tests
- All stdlib modules now work correctly with test-spec

### Type System Migration (commits 59b1035, dc75ade, 30ef0b9)
- All i32/f32 references updated to i64/f64
- Cast functions updated
- String conversion functions updated  
- 8 tests rewritten to remove if_i32

### Stdlib Enhancements (commit dc75ade)
- Added `json_new_object`, `json_new_array`, `json_set`, `json_get`, `json_push`, `json_length`, `json_type`
- Added `error_code` to result module (with pure AISL int parser)
- Updated `err()` to accept error code parameter
- Added `get_status_text` to http module
- Added `string_reverse` to string_utils module

### Result Module Fix (commit 30ef0b9)
- Fixed boolean storage issue (maps only store strings)
- Changed from storing `true`/`false` booleans to `"true"`/`"false"` strings
- Fixed all comparison logic to use `string_eq`
- Fixed `unwrap` to avoid nested return bug

---

## Documentation Files

- **This file (TEST_STATUS.md):** Current test suite status
- **AGENTS.md:** LLM reference for generating AISL code (updated with bug notes)
- **.aisl.grammar:** Token-optimized language reference for LLMs
- **.aisl.analysis:** Deep architectural analysis + runtime discoveries
- **LANGUAGE_SPEC.md:** Complete human-readable language specification

---

**Conclusion:** The critical test-spec segfault bug is FIXED! Test suite is now at 92.7% passing. Remaining 10 failures are test quality issues (9 compile errors, 1 runtime error), not framework bugs.
