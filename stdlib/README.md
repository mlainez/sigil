# AISL Standard Library

The AISL Standard Library provides high-level functionality implemented in **pure AISL code**. This follows AISL's core philosophy: **"If it CAN be written in AISL, it MUST be written in AISL."**

All stdlib modules are written in AISL and compiled to bytecode, making them:
- **Readable** - Easy to understand and modify
- **Maintainable** - Written in the same language as user code
- **Self-documenting** - Working examples for LLMs to learn from
- **Zero external dependencies** - No Python, npm, or other tooling required

---

## Complete Module Listing (11 Modules)

### Core Modules (2)

#### `stdlib/core/result.aisl`
**Purpose:** Result type for explicit error handling (replaces exceptions)

**Functions (7):**
- `ok(value)` - Create success result
- `err(code, message)` - Create error result  
- `is_ok(result)` - Check if result succeeded → bool
- `is_err(result)` - Check if result failed → bool
- `unwrap(result)` - Extract value (panics on error) → string
- `unwrap_or(result, default)` - Extract value or return default → string
- `error_code(result)` - Get error code → i32
- `error_message(result)` - Get error message → string

**Stats:** 7 functions, 112 instructions

**Import:** `(import result)`

**Example:**
```scheme
(module result_demo
  (import result)
  
  (fn safe_divide a i32 b i32 -> result
    (if (call eq b 0)
      (ret (call err 1 "Division by zero")))
    (set quotient i32 (call div a b))
    (ret (call ok quotient)))
  
  (fn main -> int
    (set res result (call safe_divide 10 2))
    (if (call is_ok res)
      (set val string (call unwrap res))
      (call print val))
    (ret 0)))
```

---

#### `stdlib/core/string_utils.aisl`
**Purpose:** Advanced string manipulation operations

**Functions (8):**
- `split(text, delimiter)` - Split string into array → array
- `trim(text)` - Remove leading/trailing whitespace → string
- `contains(haystack, needle)` - Check if string contains substring → bool
- `replace(text, old, new)` - Replace all occurrences → string
- `starts_with(text, prefix)` - Check if string starts with prefix → bool
- `ends_with(text, suffix)` - Check if string ends with suffix → bool
- `to_upper(text)` - Convert to uppercase → string
- `to_lower(text)` - Convert to lowercase → string

**Stats:** 8 functions, 700 instructions

**Import:** `(import string_utils)`

**Example:**
```scheme
(module string_demo
  (import string_utils)
  
  (fn main -> int
    (set text string "  Hello World  ")
    (set trimmed string (call trim text))
    (set upper string (call to_upper trimmed))
    (call print upper)  ; Prints: HELLO WORLD
    (ret 0)))
```

---

### Data Modules (2)

#### `stdlib/data/json.aisl`
**Purpose:** JSON parsing, manipulation, and serialization

**Functions (8):**
- `parse(text)` - Parse JSON string → json
- `stringify(obj)` - Convert to JSON string → string
- `new_object()` - Create empty JSON object → json
- `new_array()` - Create empty JSON array → json
- `get(obj, key)` - Get value from object → string
- `set(obj, key, value)` - Set value in object
- `has(obj, key)` - Check if key exists → bool
- `delete(obj, key)` - Remove key from object
- `push(array, value)` - Add element to array
- `length(obj)` - Get length → i32
- `type(json_val)` - Get JSON type → string

**Stats:** 8 functions, 987 instructions

**Import:** `(import json from data)`

**Example:**
```scheme
(module json_demo
  (import json from data)
  
  (fn main -> int
    (set obj json (call new_object))
    (call set obj "name" "Alice")
    (call set obj "age" "30")
    (set json_str string (call stringify obj))
    (call print json_str)
    (ret 0)))
```

---

#### `stdlib/data/base64.aisl`
**Purpose:** Base64 encoding and decoding

**Functions (2):**
- `encode(input)` - Encode string to base64 → string
- `decode(input)` - Decode base64 to string → string

**Stats:** 2 functions, 255 instructions

**Import:** `(import base64 from data)`

**Example:**
```scheme
(module base64_demo
  (import base64 from data)
  
  (fn main -> int
    (set text string "Hello, World!")
    (set encoded string (call encode text))
    (call print encoded)  ; Prints: SGVsbG8sIFdvcmxkIQ==
    
    (set decoded string (call decode encoded))
    (call print decoded)  ; Prints: Hello, World!
    (ret 0)))
```

---

### Network Modules (2)

#### `stdlib/net/http.aisl`
**Purpose:** HTTP client operations (wraps built-in TCP/HTTP opcodes)

**Functions (6):**
- `get(url)` - HTTP GET request → string
- `post(url, body)` - HTTP POST request → string
- `put(url, body)` - HTTP PUT request → string
- `delete(url)` - HTTP DELETE request → string
- `parse_response(response)` - Parse HTTP response → map
- `build_request(method, path, headers, body)` - Build HTTP request → string

**Stats:** 6 functions, 82 instructions

**Import:** `(import http from net)`

**Example:**
```scheme
(module http_demo
  (import http from net)
  
  (fn main -> int
    (set response string (call get "https://api.example.com/data"))
    (call print response)
    (ret 0)))
```

---

#### `stdlib/net/websocket.aisl`
**Purpose:** WebSocket client operations

**Functions (4):**
- `connect(url)` - Connect to WebSocket server → string (socket)
- `send(socket, message)` - Send message → i32
- `receive(socket)` - Receive message → string
- `close(socket)` - Close connection → i32

**Stats:** 4 functions, 16 instructions

**Import:** `(import websocket from net)`

**Example:**
```scheme
(module ws_demo
  (import websocket from net)
  
  (fn main -> int
    (set socket string (call connect "ws://localhost:8080"))
    (call send socket "Hello!")
    (set msg string (call receive socket))
    (call print msg)
    (call close socket)
    (ret 0)))
```

---

### Pattern Modules (1)

#### `stdlib/pattern/regex.aisl`
**Purpose:** Regular expression operations (wraps built-in regex opcodes)

**Functions (5):**
- `compile(pattern)` - Compile regex pattern → regex
- `match(regex, text)` - Test if text matches → bool
- `find(regex, text)` - Find first match → string
- `find_all(regex, text)` - Find all matches → array
- `replace(regex, text, replacement)` - Replace all matches → string

**Stats:** 5 functions, 21 instructions

**Import:** `(import regex from pattern)`

**Example:**
```scheme
(module regex_demo
  (import regex from pattern)
  
  (fn main -> int
    (set pattern regex (call compile "\\d+"))
    (set matches array (call find_all pattern "foo 123 bar 456"))
    (call print matches)  ; Prints: ["123", "456"]
    (ret 0)))
```

---

### Crypto Modules (1)

#### `stdlib/crypto/hash.aisl`
**Purpose:** Cryptographic hash functions

**Functions (3):**
- `sha256(input)` - SHA-256 hash → string (hex)
- `md5(input)` - MD5 hash → string (hex)
- `sha1(input)` - SHA-1 hash → string (hex)

**Stats:** 3 functions, 11 instructions

**Import:** `(import hash from crypto)`

**Example:**
```scheme
(module hash_demo
  (import hash from crypto)
  
  (fn main -> int
    (set text string "hello")
    (set hash string (call sha256 text))
    (call print hash)
    (ret 0)))
```

---

### Database Modules (1)

#### `stdlib/db/sqlite.aisl`
**Purpose:** SQLite database operations

**Functions (10):**
- `open(path)` - Open database → string (handle)
- `close(db)` - Close database → i32
- `exec(db, sql)` - Execute SQL (no result) → i32
- `query(db, sql)` - Execute SQL (returns result) → string
- `prepare(db, sql)` - Prepare statement → string (stmt)
- `bind(stmt, index, value)` - Bind parameter → i32
- `step(stmt)` - Execute next step → i32
- `column(stmt, index)` - Get column value → string
- `finalize(stmt)` - Finalize statement → i32
- `last_insert_id(db)` - Get last insert ID → i64
- `changes(db)` - Get affected rows → i32
- `error_msg(db)` - Get error message → string

**Stats:** 10 functions, 43 instructions

**Import:** `(import sqlite from db)`

**Example:**
```scheme
(module db_demo
  (import sqlite from db)
  
  (fn main -> int
    (set db string (call open "test.db"))
    (call exec db "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    (call exec db "INSERT INTO users (name) VALUES ('Alice')")
    (set result string (call query db "SELECT * FROM users"))
    (call print result)
    (call close db)
    (ret 0)))
```

---

### System Modules (2)

#### `stdlib/sys/time.aisl`
**Purpose:** Time and date operations

**Functions (3):**
- `unix_timestamp()` - Get current Unix timestamp → i64
- `sleep(milliseconds)` - Sleep for duration → i32
- `format_time(timestamp, format)` - Format timestamp → string

**Stats:** 3 functions, 11 instructions

**Import:** `(import time from sys)`

**Example:**
```scheme
(module time_demo
  (import time from sys)
  
  (fn main -> int
    (set now i64 (call unix_timestamp))
    (call print now)
    (call sleep 1000)  ; Sleep 1 second
    (ret 0)))
```

---

#### `stdlib/sys/process.aisl`
**Purpose:** Process management and environment variables

**Functions (7):**
- `spawn(command, args)` - Spawn process → i32 (pid)
- `wait(pid)` - Wait for process → i32 (exit code)
- `kill(pid, signal)` - Send signal to process → i32
- `exit(code)` - Exit program → void
- `get_pid()` - Get current process ID → i32
- `get_env(name)` - Get environment variable → string
- `set_env(name, value)` - Set environment variable → i32

**Stats:** 7 functions, 25 instructions

**Import:** `(import process from sys)`

**Example:**
```scheme
(module process_demo
  (import process from sys)
  
  (fn main -> int
    (set pid i32 (call get_pid))
    (call print "Process ID:")
    (call print pid)
    
    (set home string (call get_env "HOME"))
    (call print "Home directory:")
    (call print home)
    
    (ret 0)))
```

---

## Import Syntax

### Basic Import
```scheme
(import module_name)              ; Import from stdlib/core/module_name.aisl
```

### Import from Subdirectory
```scheme
(import module_name from subdir)  ; Import from stdlib/subdir/module_name.aisl
```

### Examples
```scheme
(import result)                   ; stdlib/core/result.aisl
(import string_utils)             ; stdlib/core/string_utils.aisl
(import json from data)           ; stdlib/data/json.aisl
(import regex from pattern)       ; stdlib/pattern/regex.aisl
(import hash from crypto)         ; stdlib/crypto/hash.aisl
(import sqlite from db)           ; stdlib/db/sqlite.aisl
(import http from net)            ; stdlib/net/http.aisl
(import time from sys)            ; stdlib/sys/time.aisl
```

---

## Design Philosophy

### Why Stdlib Modules?

1. **Eating Our Own Dog Food**: Writing utility code in AISL forces the language to be complete and self-sufficient.

2. **LLM Learning**: Stdlib modules become working examples for LLMs to learn AISL patterns.

3. **No External Dependencies**: Everything is pure AISL - no Python, npm, or other tooling.

4. **Maintainability**: Written in the same language as user code, easy to read and modify.

5. **Architectural Cleanliness**: VM only contains true primitives and system calls. High-level logic lives in AISL.

### What Belongs in Stdlib?

**✅ Belongs in stdlib (pure AISL):**
- String manipulation (split, trim, replace)
- JSON operations (parse, stringify)
- Result type (error handling)
- Base64 encoding/decoding
- HTTP request building
- Data structure wrappers

**❌ Stays in VM (C implementation):**
- True system calls (TCP, file I/O, process spawning)
- VM primitives (stack operations, arithmetic, collections)
- Performance-critical code (regex engine, crypto primitives)
- External library bindings (SQLite, OpenSSL)

---

## Contributing to Stdlib

### Guidelines

1. **Write in pure AISL** - No Python or shell scripts
2. **Keep it minimal** - Only essential functionality
3. **Document clearly** - Add usage examples
4. **Test thoroughly** - Use the test framework
5. **Follow conventions** - Match existing module style

### Module Template

```scheme
(module module_name
  ; Brief description of what this module does
  
  (fn function_name param1 type1 param2 type2 -> return_type
    ; Function implementation
    (ret result))
  
  ; More functions...
  
  (meta-note "Brief description of module purpose and usage"))
```

### Naming Conventions

- **Module names**: `lowercase_with_underscores`
- **Function names**: `lowercase_with_underscores`
- **Avoid conflicts**: Don't use type keywords (json, array, map, string)

---

## Testing Stdlib Modules

### Compile a Module
```bash
./compiler/c/bin/aislc stdlib/core/result.aisl /tmp/result.aislc
```

### Test All Modules
```bash
for f in stdlib/*/*.aisl; do
  echo "Testing: $f"
  ./compiler/c/bin/aislc "$f" "/tmp/$(basename $f .aisl).aislc"
done
```

### Integration Tests
See test files:
- `test_new_stdlib.aisl` - Tests regex + hash modules
- `test_stdlib_integration.aisl` - Tests result + string_utils
- `test_stdlib_import.aisl` - Tests import mechanism

---

## Summary Statistics

| Category | Modules | Functions | Instructions |
|----------|---------|-----------|--------------|
| Core | 2 | 15 | 812 |
| Data | 2 | 10 | 1,242 |
| Network | 2 | 10 | 98 |
| Pattern | 1 | 5 | 21 |
| Crypto | 1 | 3 | 11 |
| Database | 1 | 10 | 43 |
| System | 2 | 10 | 36 |
| **Total** | **11** | **63** | **2,263** |

---

**AISL Standard Library - Pure AISL, Zero Dependencies, Maximum Clarity**
