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
(import hash)              ; stdlib/crypto/hash.aisl
(import regex)             ; stdlib/pattern/regex.aisl
```

## Available Modules

### Core
- **string_utils** - String operations (split, trim, contains, replace)
- **conversion** - Type conversions (string_from_int, bool_to_int, etc.)
- **channel** - Concurrency primitives

### Data
- **json_utils** - JSON parsing and generation
- **base64** - Base64 encoding/decoding

### Net
- **http** - HTTP client operations
- **websocket** - WebSocket client

### Pattern
- **regex** - Regular expression operations

### Crypto
- **hash** - Cryptographic hashing (SHA256, MD5, SHA1)

### System
- **time** - Time and date operations
- **process** - Process management
- **sleep** - Sleep/delay operations

### Database
- **sqlite** - SQLite database operations

## Module Structure

```
stdlib/
├── core/           # Core language extensions
├── data/           # Data format handling
├── net/            # Networking
├── pattern/        # Pattern matching
├── crypto/        # Cryptography
├── sys/           # System operations
└── db/            # Database drivers
```

---

**AISL Standard Library - Pure AISL, Zero Dependencies, Maximum Clarity**
