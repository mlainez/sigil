# AISL - AI-Optimized Systems Language

**A programming language designed by AI, for AI code generation.**

AISL (AI-Optimized Systems Language) is a modern systems programming language specifically engineered to eliminate the ambiguities and complexities that make traditional languages difficult for Large Language Models (LLMs) to generate reliably. Every design decision prioritizes **predictability, explicitness, and zero ambiguity**.

## The Problem AISL Solves

**Traditional languages are hard for LLMs because:**
- Operator precedence creates ambiguity (`a + b * c` - which operation first?)
- Implicit type conversions hide behavior
- Multiple syntactic forms for the same construct
- Complex control flow nesting requires careful state tracking
- Hundreds of type-specific operations to memorize

**AISL fixes this:**
- ✅ **Zero operator precedence** - all operations are explicit function calls
- ✅ **Zero implicit conversions** - types are always explicit
- ✅ **One canonical form** - only ONE way to do everything
- ✅ **Flat control flow** - structured constructs desugar to simple jumps
- ✅ **Type-directed dispatch** - write `add`, compiler infers `add_int` vs `add_float`
- ✅ **S-expression syntax** - trivial to parse and generate

## Architecture: The Two-Layer Innovation

AISL's killer feature is its **two-layer architecture** that prevents language entropy over time:

```
┌─────────────────────────────────────────┐
│         AISL-Agent (Surface)            │
│  What LLMs Write: while, loop, break    │
│  Ergonomic, can evolve over time        │
└───────────────┬─────────────────────────┘
                │ Automatic Desugaring
                ▼
┌─────────────────────────────────────────┐
│          AISL-Core (IR)                 │
│  What VM Runs: set, call, goto, label   │
│  Minimal, frozen forever (6 statements) │
└─────────────────────────────────────────┘
```

### Why This Matters

- **LLMs write Agent code** - Natural, structured syntax they understand
- **VM runs Core code** - Minimal, stable IR that never changes
- **Core is frozen** - Your LLM training never becomes outdated
- **Agent evolves** - New features can be added without breaking Core
- **Deterministic** - Desugaring is automatic and predictable

**Result:** LLM-generated code has a stable target that will never change, while surface syntax can improve over time.

## Quick Start

### Hello World

```lisp
(module hello
  (fn main -> int
    (call print "Hello, AISL!")
    (ret 0)))
```

### Build the Compiler

```bash
cd compiler/c
make
```

### Compile and Run

```bash
# Compile AISL source to bytecode
./compiler/c/bin/aislc hello.aisl hello.aislc

# Execute bytecode
./compiler/c/bin/aisl-run hello.aislc
```

## Language Philosophy

### Design Principles (AI-Driven Decisions)

These design decisions were made during collaborative AI-human development to maximize LLM code generation reliability:

1. **ONE WAY ONLY** - Every construct has exactly one canonical form. No alternatives, no shortcuts, no "you can also...". Zero ambiguity.

2. **Explicit Everything** - Types, conversions, control flow, error handling - nothing is implicit. What you see is what you get.

3. **Type-Directed Dispatch** - LLMs write `(call add x y)`, compiler infers whether to use `add_int` or `add_float` based on `x`'s type. Reduces cognitive load.

4. **Flat Structure** - Sequential statements with simple jumps. No deeply nested expressions that require tracking complex state.

5. **S-Expression Syntax** - Uniform, parenthesized Lisp-style syntax. Trivial to parse, generate, and validate.

6. **Frozen Core IR** - The 6 Core statements (`set`, `call`, `label`, `goto`, `ifnot`, `ret`) will never change. Future-proof.

7. **No Comments** - AISL intentionally has no comment syntax. Use descriptive names and `meta-note` in tests. Forces clarity.

8. **Eating Our Own Dog Food** - All tooling, utilities, and stdlib modules are written in pure AISL. If AISL can't express something, we fix AISL, not reach for Python.

9. **Panic-Based Errors** - Operations fail with clear panic messages. LLM regenerates with checks when needed.

10. **Machine-Readable First** - Documentation prioritizes machine-readable formats (`.aisl.grammar`, `.aisl.meta`) over prose. LLMs read these first.

## Use Cases

### What AISL is FOR

✅ **AI Code Generation** - Primary design goal  
✅ **Web Services** - HTTP servers, REST APIs, WebSocket servers  
✅ **CLI Tools** - System utilities, automation scripts  
✅ **Network Services** - TCP servers, protocol implementations  
✅ **Data Processing** - JSON/CSV parsing, transformations  
✅ **System Integration** - Process spawning, IPC, database clients  

### What AISL is NOT FOR

❌ **Real-time Systems** - Bytecode interpreter overhead  
❌ **Low-level System Programming** - No manual memory management, no pointers  
❌ **GUI Applications** - No GUI framework (yet)  
❌ **Performance-Critical Inner Loops** - Compile to C/Rust for hot paths  

## Core Features

### Types (Simplified for LLM Predictability)

```lisp
int      ; 64-bit signed integer (ONLY int type)
float    ; 64-bit floating point (ONLY float type)
bool     ; Boolean (true/false)
string   ; UTF-8 string
array    ; Dynamic array
map      ; Hash map
json     ; JSON values
regex    ; Compiled regular expression
```

**AI Decision:** Only TWO numeric types (`int`, `float`) - not i8/i16/i32/i64/u8/u16/u32/u64. Less for LLMs to remember, still covers 99% of use cases.

### Control Flow (Agent Layer)

```lisp
; Structured constructs (what LLMs write)
(while condition statements...)   ; While loop
(loop statements...)              ; Infinite loop
(if condition statements...)      ; Conditional
(break)                           ; Exit loop
(continue)                        ; Next iteration

; Core constructs (what VM executes)
(label name)                      ; Jump target
(goto target)                     ; Unconditional jump
(ifnot bool_var target)          ; Jump if false
```

**AI Decision:** Structured constructs desugar to Core primitives. LLMs write ergonomic code, VM runs simple jumps. Best of both worlds.

### Type-Directed Dispatch (LLM Superpower)

```lisp
; LLM writes this (generic)
(set x int 10)
(set y int 20)
(set sum int (call add x y))    ; Compiler infers add_int

(set a float 3.14)
(set b float 2.71)
(set total float (call add a b)) ; Compiler infers add_float
```

**AI Decision:** LLMs don't need to remember `add_int`, `add_i64`, `add_f32`, `add_f64` - just write `add` and the compiler figures it out.

### Error Handling

```lisp
(fn safe_divide a int b int -> int
  (if (call eq b 0)
    (panic "Division by zero"))
  (ret (call div a b)))

(fn main -> int
  (set value int (call safe_divide 10 0))
  (call print value)
  (ret 0))
```

**AI Decision:** Operations panic on error with clear messages. LLM regenerates with checks (file_exists, etc.) when panics occur.

## Standard Library (13 Modules in Pure AISL)

All stdlib modules are implemented **in pure AISL**, not C. This enforces our philosophy: "If it CAN be written in AISL, it MUST be written in AISL."

### Core (2 modules)
- **string_utils** - String operations (`split`, `trim`, `contains`, `replace`, `starts_with`, `ends_with`)
- **conversion** - Type conversion (`string_from_int`, `bool_to_int`, `kilometers_to_miles`)

### Data (2 modules)
- **json_utils** - JSON parsing and generation
- **base64** - Base64 encoding/decoding

### Net (2 modules)
- **http** - HTTP client (GET, POST, PUT, DELETE)
- **websocket** - WebSocket client

### Pattern (1 module)
- **regex** - Regular expressions

### Crypto (1 module)
- **hash** - Cryptographic hashing (SHA256, MD5)

### System (2 modules)
- **time** - Time operations
- **process** - Process management

### Database (1 module)
- **sqlite** - SQLite database (via process spawning)

**Plus 180+ built-in operations** for arithmetic, comparisons, I/O, TCP networking, file system, arrays, maps.

## Examples

### Factorial (Recursion)

```lisp
(module factorial
  (fn factorial n int -> int
    (if (call eq n 0)
      (ret 1))
    (set n_minus_1 int (call sub n 1))
    (set prev int (call factorial n_minus_1))
    (ret (call mul n prev)))
  
  (fn main -> int
    (set result int (call factorial 5))
    (call print result)  ; Prints: 120
    (ret 0)))
```

### Web Server (Real HTTP Server in 20 Lines)

```lisp
(module web_server
  (fn handle_request client_sock string -> int
    (set request string (call tcp_receive client_sock 4096))
    (set response string "HTTP/1.1 200 OK\r\n\r\nHello from AISL!")
    (call tcp_send client_sock response)
    (call tcp_close client_sock)
    (ret 0))
  
  (fn main -> int
    (set server_sock string (call tcp_listen 8080))
    (call print "Server listening on port 8080")
    (loop
      (set client_sock string (call tcp_accept server_sock))
      (call handle_request client_sock))
    (ret 0)))
```

See [examples/](examples/) for 17 complete working examples.

## Testing

AISL has **126 passing tests** covering all language features. All tests use the `test-spec` structure:

```lisp
(module test_addition
  (fn add_numbers a int b int -> int
    (ret (call add a b)))
  
  (test-spec add_numbers
    (case "adds positive numbers"
      (input 2 3)
      (expect 5))
    (case "handles negative numbers"
      (input -5 -3)
      (expect -8)))
  
  (meta-note "Tests integer addition"))
```

**AI Decision:** No `main()` functions in tests. Test framework provides entry point. ONE WAY to write tests.

## Project Structure

```
aisl/
├── README.md                   # This file
├── AGENTS.md                   # LLM quick reference (8K tokens)
├── LANGUAGE_SPEC.md            # Complete language specification
├── AISL-CORE.md                # Core IR specification (frozen forever)
├── AISL-AGENT.md               # Agent surface language
├── .aisl.grammar               # Machine-readable grammar (400 tokens, 20x more efficient!)
├── .aisl.meta                  # Project context (compressed s-expr)
├── .aisl.analysis              # Deep architectural analysis
│
├── compiler/c/                 # C compiler and VM
│   ├── src/                    # Compiler implementation
│   │   ├── compiler.c          # Agent → Core desugaring + bytecode generation
│   │   ├── parser.c            # S-expression parser
│   │   ├── lexer.c             # Tokenizer
│   │   ├── desugar.c           # Agent → Core transformation
│   │   ├── vm.c                # Bytecode interpreter
│   │   ├── runtime.c           # Built-in functions (180+)
│   │   ├── module_loader.c     # Module import system
│   │   └── test_framework.c    # Test runner
│   ├── include/                # Header files
│   │   ├── bytecode.h          # Bytecode opcodes
│   │   ├── ast.h               # AST definitions
│   │   └── ...
│   ├── bin/
│   │   ├── aislc               # Compiler binary
│   │   └── aisl-run            # VM binary
│   └── Makefile
│
├── stdlib/                     # Standard library (pure AISL!)
│   ├── core/                   # Core modules (result, string_utils, conversion)
│   ├── data/                   # Data formats (json_utils, base64)
│   ├── net/                    # Networking (http, websocket)
│   ├── pattern/                # Pattern matching (regex)
│   ├── crypto/                 # Cryptography (hash)
│   ├── sys/                    # System (time, process)
│   ├── db/                     # Databases (sqlite)
│   └── README.md               # Stdlib documentation
│
├── tests/                      # Test suite (126 tests, all passing)
│   ├── test_*.aisl             # Unit tests
│   └── README.md
│
├── examples/                   # Example programs (17 examples)
│   ├── hello_world.aisl
│   ├── sinatra_demo.aisl       # Web server with routing
│   ├── working_server.aisl     # Production-ready HTTP server
│   ├── echo_server.aisl        # TCP echo server
│   └── ...
│
├── tools/                      # Utilities (written in pure AISL!)
│   ├── fix_tests.aisl          # Test file converter
│   └── test_runner.aisl        # Test harness
│
└── modules/                    # Legacy modules (being migrated to stdlib/)
```

## Documentation Hierarchy (For LLMs)

**When generating AISL code, LLMs should consult in this order:**

1. **`.aisl.grammar`** (400 tokens) - Complete syntax reference, CONSULT FIRST
2. **`.aisl.meta`** (compressed) - Project context
3. **`.aisl.analysis`** (detailed) - Design decisions, known issues
4. **`AGENTS.md`** (8K tokens) - LLM-optimized quick reference with examples
5. **`LANGUAGE_SPEC.md`** (full) - Complete specification for deep dives

**Why this order?** Token efficiency. `.aisl.grammar` is 20x more efficient than prose documentation.

## Key Design Decisions Explained

### 1. Why No Comments?

**Decision:** AISL intentionally has no comment syntax (no `;`, `//`, `#`, `/* */`).

**Rationale:** 
- Forces descriptive variable and function names
- Prevents commented-out code cruft
- Use `meta-note` in tests for documentation
- LLMs often struggle with comment placement - removing the feature removes the problem

### 2. Why Only Two Numeric Types?

**Decision:** Only `int` (64-bit) and `float` (64-bit), not i8/i16/i32/i64/u8/u16/u32/u64/f32/f64.

**Rationale:**
- 99% of code doesn't need 8 numeric types
- Fewer types = less for LLMs to memorize
- Simplifies type-directed dispatch
- Still covers all practical use cases
- If you need byte-level control, use arrays

### 3. Why S-Expressions?

**Decision:** Lisp-style parenthesized syntax instead of C-like syntax.

**Rationale:**
- Zero ambiguity in parsing
- No operator precedence rules
- Uniform structure (everything is `(operation args...)`)
- Trivial to generate programmatically
- LLMs already understand S-expressions from Common Lisp, Scheme, Clojure

### 4. Why Type-Directed Dispatch?

**Decision:** Write `(call add x y)`, not `(call add_int x y)`.

**Rationale:**
- Reduces cognitive load for LLMs (don't memorize 50 operation variants)
- Compiler infers types from variable declarations
- Still fully statically typed (no runtime dispatch)
- Feels more natural for LLMs trained on high-level languages

### 5. Why Frozen Core IR?

**Decision:** The 6 Core statements will never change, ever.

**Rationale:**
- LLM training data never becomes outdated
- Agent layer can evolve without breaking Core
- Simplifies VM implementation (fewer opcodes to optimize)
- Easier to reason about correctness
- Future compilers/VMs can target the same IR

### 6. Why No `main()` in Tests?

**Decision:** Test files use `test-spec`, not `main()` functions.

**Rationale:**
- ONE WAY to write tests (zero ambiguity)
- Test framework provides entry point automatically
- Declarative test structure easier for LLMs to generate
- Prevents mixing test logic with test execution

### 7. Why Pure AISL Stdlib?

**Decision:** All stdlib modules must be written in pure AISL, not C.

**Rationale:**
- Eating our own dog food - discovers language limitations immediately
- Stdlib modules become learning examples for LLMs
- No FFI/C dependency hellscape
- Forces AISL to be complete and self-sufficient
- If AISL can't express something, we extend AISL

## Building from Source

```bash
# Prerequisites: gcc, make, openssl-dev
cd compiler/c
make

# Binaries created:
# - bin/aislc      (compiler)
# - bin/aisl-run   (VM)
```

## Running Tests

```bash
# Run all 126 tests
cd compiler/c
for test in ../tests/test_*.aisl; do
  ./bin/aislc "$test" "/tmp/$(basename $test).aislc" && ./bin/aisl-run "/tmp/$(basename $test).aislc"
done
```

## Performance Characteristics

- **Compilation:** Single-pass, very fast (~1ms per module)
- **Bytecode:** Compact, efficient encoding
- **VM:** Stack-based interpreter, predictable performance
- **No GC pauses:** Strings are ref-counted
- **Cold start:** <1ms (no JIT warmup needed)

**Not designed for:** Number-crunching inner loops. Use C/Rust for hot paths, AISL for glue code.

## Contributing

AISL is currently in active development. All changes must:

1. ✅ Maintain zero ambiguity (ONE WAY ONLY)
2. ✅ Pass all 126 tests
3. ✅ Update machine-readable docs (`.aisl.grammar`, `.aisl.meta`)
4. ✅ Write new stdlib modules in pure AISL (no C)
5. ✅ Follow the "frozen Core IR" principle

## Strengths

✅ **LLM-Optimized** - Designed for reliable AI code generation  
✅ **Zero Ambiguity** - Every construct has exactly one meaning  
✅ **Stable Target** - Core IR frozen forever  
✅ **Batteries Included** - 180+ built-in functions, 14 stdlib modules  
✅ **Fast Compilation** - Single-pass, <1ms per module  
✅ **Easy to Parse** - S-expression syntax  
✅ **Explicit Everything** - No surprises, no hidden behavior  
✅ **Real-World Ready** - Production HTTP servers, database clients, JSON processing  

## Weaknesses (Known Limitations)

❌ **Interpreter Overhead** - Not as fast as compiled C/Rust (not the goal)  
❌ **No SIMD** - Bytecode VM doesn't vectorize  
❌ **No Parallel Execution** - Single-threaded for now (async planned)  
❌ **Limited Ecosystem** - Young language, stdlib still growing  
❌ **No IDE Support** - LSP server planned but not implemented  

## Roadmap

### Near Term
- [ ] LSP server for editor integration
- [ ] Async/await for concurrent I/O
- [ ] More stdlib modules (HTTP server framework, database clients)
- [ ] Package manager

### Long Term
- [ ] JIT compiler for hot paths
- [ ] WebAssembly target
- [ ] Parallel execution model
- [ ] Native compilation (AISL → C)

## License

[License information to be added]

---

## About the Name

**AISL** = **A**I-Optimized **S**ystems **L**anguage

Also: "AISL" sounds like "aisle" - a clear path forward for AI code generation. 🛤️

---

**AISL - Designed by AI, for AI. Built for Everyone.** 🤖

*Created through collaborative AI-human design to solve the hard problem: making LLMs generate correct code, reliably.*
