# Sigil Standard Library

The Sigil Standard Library provides high-level functionality implemented in **pure Sigil code**. This follows Sigil's core philosophy: **"If it CAN be written in Sigil, it MUST be written in Sigil."**

All stdlib modules are written in Sigil and interpreted directly, making them:
- **Readable** - Easy to understand and modify
- **Maintainable** - Written in the same language as user code
- **Self-documenting** - Working examples for LLMs to learn from
- **Zero external dependencies** - No Python, npm, or other tooling required

## Builtin vs stdlib boundary

A function lives in the OCaml interpreter (a **builtin**) only if at least one of:

1. It cannot be expressed in Sigil at all — needs FFI / syscall / OCaml-library access (I/O, regex via `Str`, `Unix.*`, file/socket/process, `Sys.argv`).
2. It is a runtime/type primitive — `len`, `type_of`, equality dispatch (touches the value tag).
3. It is a syntactic operator — arithmetic, comparison, boolean ops.
4. It is a performance-critical primitive whose Sigil implementation would be unworkably slow (e.g. `sort`).

**Everything else belongs in the stdlib, written in Sigil.** Convenience names that the model reaches for (`tokens`, `squeeze`, `find_all`, …) belong in the auto-loaded prelude rather than the OCaml dispatch table — same zero-import experience for the model, but the implementation is composable Sigil code that doubles as documentation.

When in doubt: write it in Sigil. If the benchmark forces it into OCaml for performance reasons, leave the Sigil version next to it as a reference.

## Auto-loaded prelude

`stdlib/core/prelude.sigil` is loaded into every program's global environment before user code runs — no `(import prelude)` required. Its functions resolve as if they were builtins. User imports and user functions can still shadow prelude names.

The prelude is the right home for any composition that:
- Captures a common LLM failure shape (e.g. `(split s " ")` losing on multi-space input → `tokens`).
- Has a name the model reaches for that doesn't already exist (e.g. `find_all`).

Add to the prelude rather than the OCaml interpreter unless the function genuinely needs primitive access.

## Import Syntax

```lisp
(import string_utils)     ; stdlib/core/string_utils.sigil
(import json_utils)        ; stdlib/data/json_utils.sigil
(import http)              ; stdlib/net/http.sigil
(import sqlite)            ; stdlib/db/sqlite.sigil
(import regex)             ; stdlib/pattern/regex.sigil
(import process)           ; stdlib/sys/process.sigil
```

The module loader automatically searches all stdlib subdirectories (`core/`, `data/`, `net/`, `sys/`, `db/`, `pattern/`, `crypto/`).

## Available Modules (18 Total)

### Auto-loaded
- **prelude** - Zero-import convenience functions: `tokens` (whitespace split, drops empties), `squeeze` (collapse runs of whitespace), `split_blocks` (paragraph split on blank lines), `find_all` (regex matches as array; alias for `regex_find_all`).

### Core (9 modules)
- **string_utils** - String operations (split, trim, contains, replace, starts_with, ends_with, to_upper, to_lower)
- **conversion** - Type conversions (string_from_int, string_from_float, string_from_bool, bool_to_int, int_to_bool, kilometers_to_miles, celsius_to_fahrenheit)
- **array_utils** - Array utilities (array_sum, array_product, array_find, array_contains, array_min, array_max, array_reverse, array_fill, array_range)
- **math** - Math operations (abs, abs_float, min, max, min_float, max_float)
- **math_extended** - Extended math (clamp, sign, lerp, is_even, is_odd, square, cube)
- **filesystem** - File utilities (read_file_safe, write_file_safe, delete_if_exists, copy_file, read_lines, count_lines)
- **network** - Network utilities (is_valid_port, normalize_path, build_url, build_query_string, parse_url, extract_domain)
- **text_utils** - Text utilities (repeat_string, pad_left, pad_right, truncate, word_count, reverse_string, is_empty)
- **validation** - Validation (in_range, is_positive, is_negative, is_zero, is_divisible_by)

### Data (1 module)
- **json_utils** - JSON parsing and manipulation (parse, stringify, new_object, new_array, get, set, has, delete, push, length, type)

### Net (1 module)
- **http** - HTTP client operations (get, post, put, delete, parse_response, build_request)

### Pattern (1 module)
- **regex** - Regular expression operations (compile, match, find, find_all, replace)

### System (1 module)
- **process** - Process management (spawn, wait, kill, exit, get_pid, get_env, set_env)

### Database (1 module)
- **sqlite** - SQLite database operations (open, close, exec, query, prepare, bind, step, column, finalize, last_insert_id, changes, error_msg)

### Crypto (3 modules)
- **base64** - Base64 encoding/decoding (base64_encode, base64_decode) — pure Sigil, no external dependencies
- **hash** - Cryptographic hash functions (sha256, md5) — pure Sigil using bitwise builtins
- **hmac** - HMAC message authentication (hmac_sha256) — pure Sigil using hash module

## Module Structure

```
stdlib/
├── core/           # Core language extensions (9 modules)
├── crypto/         # Cryptography (3 modules)
├── data/           # Data format handling (1 module)
├── net/            # Networking (1 module)
├── pattern/        # Pattern matching (1 module)
├── sys/            # System operations (1 module)
└── db/             # Database drivers (1 module)
```

## Stdlib gotcha: the if-Lisp-form trap

Sigil's `if` parser supports two shapes:

```
(if cond then-stmt)                    ; 1 body expr → then-only
(if cond then-expr else-expr)          ; 2 body exprs → Lisp/Scheme form
(if cond stmt1 stmt2 ... (else ...))   ; explicit else marker
(if cond stmt1 stmt2 stmt3 ...)        ; 3+ body exprs, no (else ...) → all then-body
```

The **2-body case is the trap**. If you intend the second statement as a sequenced part of the then-branch, the parser instead reads it as the else-branch. Symptom: cleared/skipped state when the condition is false, or stray writes when it is true.

When you want a 2-statement then-body with no else, write the no-op marker explicitly:

```lisp
(if cond
  (set is_neg true)
  (set start 1)
  (else))
```

This bug pattern was the cause of all 4 long-standing test failures fixed in 2026-05-01: `hex_to_int`, `binary_to_int`, MD5's main round dispatch in `crypto/hash.sigil`, and the if-multi tests. Audit any new stdlib code for this shape; the parser will not warn you.

---

**Sigil Standard Library - Pure Sigil, Zero Dependencies, Maximum Clarity**
