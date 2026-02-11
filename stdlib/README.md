# AISL Standard Library

The AISL Standard Library provides high-level functionality implemented in **pure AISL code**. This follows AISL's core philosophy: **"If it CAN be written in AISL, it MUST be written in AISL."**

All stdlib modules are written in AISL and interpreted directly, making them:
- **Readable** - Easy to understand and modify
- **Maintainable** - Written in the same language as user code
- **Self-documenting** - Working examples for LLMs to learn from
- **Zero external dependencies** - No Python, npm, or other tooling required

## Import Syntax

```lisp
(import string_utils)     ; stdlib/core/string_utils.aisl
(import json_utils)        ; stdlib/data/json_utils.aisl
(import http)              ; stdlib/net/http.aisl
(import sqlite)            ; stdlib/db/sqlite.aisl
(import regex)             ; stdlib/pattern/regex.aisl
(import process)           ; stdlib/sys/process.aisl
```

The module loader automatically searches all stdlib subdirectories (`core/`, `data/`, `net/`, `sys/`, `db/`, `pattern/`, `crypto/`).

## Available Modules (17 Total)

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
- **base64** - Base64 encoding/decoding (base64_encode, base64_decode) — pure AISL, no external dependencies
- **hash** - Cryptographic hash functions (sha256, md5) — pure AISL using bitwise builtins
- **hmac** - HMAC message authentication (hmac_sha256) — pure AISL using hash module

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

---

**AISL Standard Library - Pure AISL, Zero Dependencies, Maximum Clarity**
