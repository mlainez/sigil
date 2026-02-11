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
- **Zero operator precedence** - all operations are explicit function calls
- **Zero implicit conversions** - types are always explicit
- **One canonical form** - only ONE way to do everything
- **Flat control flow** - structured constructs with simple semantics
- **Type-directed dispatch** - write `add`, interpreter infers `add_int` vs `add_float`
- **S-expression syntax** - trivial to parse and generate

## Architecture: The Two-Layer Innovation

AISL's killer feature is its **two-layer architecture** that prevents language entropy over time:

```
+---------------------------------------------+
|         AISL-Agent (Surface)                |
|  What LLMs Write: while, loop, break       |
|  Ergonomic, can evolve over time            |
+---------------------+-----------------------+
                      |
                      v
+---------------------------------------------+
|          AISL-Core (IR)                     |
|  Concepts: set, goto, label, ifnot, ret     |
|  Minimal, frozen forever (5 statements)     |
+---------------------------------------------+
```

### Why This Matters

- **LLMs write Agent code** - Natural, structured syntax they understand
- **Interpreter handles both layers** - Agent constructs evaluated directly alongside Core primitives
- **Core is frozen** - Your LLM training never becomes outdated
- **Agent evolves** - New features can be added without breaking Core
- **Deterministic** - Same input = same output, always

**Result:** LLM-generated code has a stable target that will never change, while surface syntax can improve over time.

## Quick Start

### Hello World

```lisp
(module hello
  (fn main -> int
    (print "Hello, AISL!")
    (ret 0)))
```

### Build the Interpreter

```bash
# Prerequisites: OCaml 5.2.1, opam, dune, openssl-dev
cd interpreter
eval $(opam env)
dune build
```

### Run

```bash
# Run AISL source directly (single step, no compilation)
./interpreter/_build/default/vm.exe hello.aisl
```

## Language Philosophy

### Design Principles (AI-Driven Decisions)

These design decisions were made during collaborative AI-human development to maximize LLM code generation reliability:

1. **ONE WAY ONLY** - Every construct has exactly one canonical form. No alternatives, no shortcuts, no "you can also...". Zero ambiguity.

2. **Explicit Everything** - Types, conversions, control flow, error handling - nothing is implicit. What you see is what you get.

3. **Type-Directed Dispatch** - LLMs write `(add x y)`, interpreter infers whether to use `add_int` or `add_float` based on `x`'s type. Reduces cognitive load.

4. **Flat Structure** - Sequential statements with simple jumps. No deeply nested expressions that require tracking complex state.

5. **S-Expression Syntax** - Uniform, parenthesized Lisp-style syntax. Trivial to parse, generate, and validate.

6. **Frozen Core IR** - The 5 Core statements (`set`, `label`, `goto`, `ifnot`, `ret`) will never change. Future-proof.

7. **No Comments** - AISL intentionally has no comment syntax. Use descriptive names and `meta-note` in tests. Forces clarity.

8. **Eating Our Own Dog Food** - All tooling, utilities, and stdlib modules are written in pure AISL. If AISL can't express something, we fix AISL, not reach for Python.

9. **Panic-Based Errors** - Operations fail with clear panic messages. LLM regenerates with checks when needed.

10. **Machine-Readable First** - Documentation prioritizes machine-readable formats (`.aisl.grammar`, `.aisl.meta`) over prose. LLMs read these first.

## Use Cases

### What AISL is FOR

- **AI Code Generation** - Primary design goal
- **Web Services** - HTTP servers, REST APIs, WebSocket servers
- **CLI Tools** - System utilities, automation scripts
- **Network Services** - TCP servers, TLS, WebSocket protocol implementations
- **Data Processing** - JSON/CSV parsing, transformations
- **System Integration** - Process spawning, IPC, database clients

### What AISL is NOT FOR

- **Real-time Systems** - Tree-walking interpreter overhead
- **Low-level System Programming** - No manual memory management, no pointers
- **GUI Applications** - No GUI framework (yet)
- **Performance-Critical Inner Loops** - Compile to C/Rust for hot paths

## Core Features

### Types (Simplified for LLM Predictability)

```lisp
int      ; 64-bit signed integer (ONLY int type)
float    ; 64-bit floating point (ONLY float type)
decimal  ; Arbitrary precision decimal (financial math)
bool     ; Boolean (true/false)
string   ; UTF-8 string
array    ; Dynamic array
map      ; Hash map
json     ; JSON values
regex    ; Compiled regular expression
socket   ; TCP socket handle
process  ; Process handle (for DB, subprocesses)
```

**AI Decision:** Only TWO numeric types (`int`, `float`) plus `decimal` for financial precision - not i8/i16/i32/i64/u8/u16/u32/u64. Less for LLMs to remember, still covers 99% of use cases.

### Control Flow (Agent Layer)

```lisp
(while condition statements...)   ; While loop
(loop statements...)              ; Infinite loop
(if condition statements...)      ; Conditional
(if condition then... (else ...)) ; If-else conditional
(for-each var type collection     ; For-each iteration
  statements...)
(break)                           ; Exit loop
(continue)                        ; Next iteration
(and expr1 expr2)                 ; Short-circuit AND
(or expr1 expr2)                  ; Short-circuit OR

; Core constructs (available for complex control flow)
(label name)                      ; Jump target
(goto target)                     ; Unconditional jump
(ifnot bool_var target)           ; Jump if false
```

**AI Decision:** Structured constructs are evaluated directly by the interpreter. LLMs write ergonomic code, interpreter handles semantics.

### Type-Directed Dispatch (LLM Superpower)

```lisp
; LLM writes this (generic)
(set x int 10)
(set y int 20)
(set sum int (add x y))    ; Interpreter infers add_int

(set a float 3.14)
(set b float 2.71)
(set total float (add a b)) ; Interpreter infers add_float
```

**AI Decision:** LLMs don't need to remember `add_int`, `add_i64`, `add_f32`, `add_f64` - just write `add` and the interpreter figures it out.

### Error Handling

```lisp
(fn safe_divide a int b int -> int
  (if (eq b 0)
    (panic "Division by zero"))
  (ret (div a b)))

(fn main -> int
  (set value int (safe_divide 10 0))
  (print value)
  (ret 0))
```

**AI Decision:** Operations panic on error with clear messages. LLM regenerates with checks (file_exists, etc.) when panics occur.

## Standard Library (14 Modules in Pure AISL)

All stdlib modules are implemented **in pure AISL**, not native code. This enforces our philosophy: "If it CAN be written in AISL, it MUST be written in AISL."

### Core (9 modules)
- **string_utils** - String operations (`split`, `trim`, `contains`, `replace`, `starts_with`, `ends_with`, `to_upper`, `to_lower`)
- **conversion** - Type conversion (`string_from_int`, `bool_to_int`, `kilometers_to_miles`)
- **array_utils** - Array utilities (`array_sum`, `array_product`, `array_find`, `array_contains`, `array_reverse`)
- **math** - Math operations (`abs`, `min`, `max`)
- **math_extended** - Extended math (`clamp`, `sign`, `lerp`, `is_even`, `is_odd`)
- **filesystem** - File utilities (`read_file_safe`, `write_file_safe`, `copy_file`, `read_lines`)
- **network** - Network utilities (`is_valid_port`, `build_url`, `parse_url`, `extract_domain`)
- **text_utils** - Text utilities (`repeat_string`, `pad_left`, `pad_right`, `truncate`, `word_count`)
- **validation** - Validation (`in_range`, `is_positive`, `is_negative`, `is_zero`)

### Data (1 module)
- **json_utils** - JSON parsing and generation

### Net (1 module)
- **http** - HTTP client (GET, POST, PUT, DELETE)

### Pattern (1 module)
- **regex** - Regular expressions

### System (1 module)
- **process** - Process management

### Database (1 module)
- **sqlite** - SQLite database (via process spawning)

**Plus 180+ built-in operations** for arithmetic, comparisons, I/O, TCP/TLS networking, WebSocket protocol, file system, arrays, maps, string formatting, and more.

## Examples

### Factorial (Recursion)

```lisp
(module factorial
  (fn factorial n int -> int
    (if (eq n 0)
      (ret 1))
    (set n_minus_1 int (sub n 1))
    (set prev int (factorial n_minus_1))
    (ret (mul n prev)))

  (fn main -> int
    (set result int (factorial 5))
    (print result)  ; Prints: 120
    (ret 0)))
```

### Web Server (Real HTTP Server in 20 Lines)

```lisp
(module web_server
  (fn handle_request client_sock string -> int
    (set request string (tcp_receive client_sock 4096))
    (set response string "HTTP/1.1 200 OK\r\n\r\nHello from AISL!")
    (tcp_send client_sock response)
    (tcp_close client_sock)
    (ret 0))

  (fn main -> int
    (set server_sock string (tcp_listen 8080))
    (print "Server listening on port 8080")
    (loop
      (set client_sock string (tcp_accept server_sock))
      (handle_request client_sock))
    (ret 0)))
```

### For-Each Loop

```lisp
(module foreach_demo
  (fn sum_array arr array -> int
    (set total int 0)
    (for-each val int arr
      (set total int (add total val)))
    (ret total))

  (fn main -> int
    (set nums array (array_new))
    (array_push nums 10)
    (array_push nums 20)
    (array_push nums 30)
    (set result int (sum_array nums))
    (print result)  ; Prints: 60
    (ret 0)))
```

See [examples/](examples/) for complete working examples including a real-time WebSocket chat app and a TODO app with SQLite.

## Testing

AISL has **138 passing tests** covering all language features. All tests use the `test-spec` structure:

```lisp
(module test_addition
  (fn add_numbers a int b int -> int
    (ret (add a b)))

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
+-- README.md                   # This file
+-- AGENTS.md                   # LLM quick reference (8K tokens)
+-- LANGUAGE_SPEC.md            # Complete language specification
+-- AISL-CORE.md                # Core IR specification (frozen forever)
+-- AISL-AGENT.md               # Agent surface language
+-- .aisl.grammar               # Machine-readable grammar (~1600 tokens)
+-- .aisl.analysis              # Deep architectural analysis
|
+-- interpreter/                # OCaml tree-walking interpreter
|   +-- lexer.ml                # S-expression tokenizer
|   +-- parser.ml               # Recursive descent parser
|   +-- types.ml                # Type kind definitions
|   +-- ast.ml                  # AST node types
|   +-- interpreter.ml          # Evaluator + 180+ builtins (~2500 lines)
|   +-- vm.ml                   # Entry point
|   +-- dune / dune-project     # Build configuration
|   +-- _build/                 # Build output
|
+-- stdlib/                     # Standard library (17 modules, pure AISL!)
|   +-- core/                   # Core modules (string_utils, conversion, array_utils, math, math_extended, filesystem, network, text_utils, validation)
|   +-- crypto/                 # Cryptography (base64, hash, hmac)
|   +-- data/                   # Data formats (json_utils)
|   +-- net/                    # Networking (http)
|   +-- pattern/                # Pattern matching (regex)
|   +-- sys/                    # System (process)
|   +-- db/                     # Databases (sqlite)
|   +-- README.md               # Stdlib documentation
|
+-- tests/                      # Test suite (138 tests, all passing)
|   +-- test_*.aisl             # Unit tests
|   +-- README.md
|
+-- examples/                   # Example programs
|   +-- hello_world.aisl
|   +-- chat_app/               # Real-time WebSocket chat application
|   +-- todo_app/               # TODO app with SQLite backend
```

## Documentation Hierarchy (For LLMs)

**When generating AISL code, LLMs should consult in this order:**

1. **`.aisl.grammar`** (~800 tokens) - Complete syntax reference, CONSULT FIRST
2. **`.aisl.analysis`** (detailed) - Design decisions, known issues
3. **`AGENTS.md`** (8K tokens) - LLM-optimized quick reference with examples
4. **`LANGUAGE_SPEC.md`** (full) - Complete specification for deep dives

**Why this order?** Token efficiency. `.aisl.grammar` is 10x more efficient than prose documentation.

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

**Decision:** Write `(add x y)`, not `(add_int x y)`.

**Rationale:**
- Reduces cognitive load for LLMs (don't memorize 50 operation variants)
- Interpreter infers types from variable declarations
- Still fully statically typed (no runtime dispatch overhead)
- Feels more natural for LLMs trained on high-level languages

### 5. Why Frozen Core IR?

**Decision:** The 5 Core statements will never change, ever.

**Rationale:**
- LLM training data never becomes outdated
- Agent layer can evolve without breaking Core
- Simplifies interpreter implementation
- Easier to reason about correctness
- Future implementations can target the same IR

### 6. Why No `main()` in Tests?

**Decision:** Test files use `test-spec`, not `main()` functions.

**Rationale:**
- ONE WAY to write tests (zero ambiguity)
- Test framework provides entry point automatically
- Declarative test structure easier for LLMs to generate
- Prevents mixing test logic with test execution

### 7. Why Pure AISL Stdlib?

**Decision:** All stdlib modules must be written in pure AISL.

**Rationale:**
- Eating our own dog food - discovers language limitations immediately
- Stdlib modules become learning examples for LLMs
- No FFI/dependency hellscape
- Forces AISL to be complete and self-sufficient
- If AISL can't express something, we extend AISL

## Building from Source

```bash
# Prerequisites: OCaml 5.2.1 (via opam), dune 3.21+, openssl-dev
cd interpreter
eval $(opam env)
dune build

# Binary created at:
# interpreter/_build/default/vm.exe
```

## Running Tests

```bash
# Run all 138 tests
cd interpreter
eval $(opam env)
total=0; passed=0
for f in ../tests/test_*.aisl; do
  total=$((total+1))
  timeout 5 ./_build/default/vm.exe "$f" >/dev/null 2>&1 && passed=$((passed+1))
done
echo "$passed/$total"
```

## Performance Characteristics

- **Interpretation:** Tree-walking, direct AST evaluation - no separate compilation step
- **Startup:** Fast (<10ms) - parse and execute in one step
- **No GC pauses:** OCaml garbage collector handles memory
- **Cold start:** Minimal overhead (no bytecode generation, no JIT warmup)
- **WebSocket:** Native binary frame encoding/decoding with SHA-1 handshake

**Not designed for:** Number-crunching inner loops. Use C/Rust for hot paths, AISL for glue code.

## Contributing

AISL is currently in active development. All changes must:

1. Maintain zero ambiguity (ONE WAY ONLY)
2. Pass all 138 tests
3. Update machine-readable docs (`.aisl.grammar`, `.aisl.meta`)
4. Write new stdlib modules in pure AISL
5. Follow the "frozen Core IR" principle

## Strengths

- **LLM-Optimized** - Designed for reliable AI code generation
- **Zero Ambiguity** - Every construct has exactly one meaning
- **Stable Target** - Core IR frozen forever
- **Batteries Included** - 180+ built-in operations, 17 stdlib modules
- **Fast Startup** - Direct interpretation, <10ms
- **Easy to Parse** - S-expression syntax
- **Explicit Everything** - No surprises, no hidden behavior
- **Real-World Ready** - Production HTTP/WebSocket servers, database clients, JSON processing

## Weaknesses (Known Limitations)

- **Interpreter Overhead** - Not as fast as compiled C/Rust (not the goal)
- **No SIMD** - Tree-walking interpreter doesn't vectorize
- **No Parallel Execution** - Single-threaded for now (async planned)
- **Limited Ecosystem** - Young language, stdlib still growing
- **No IDE Support** - LSP server planned but not implemented

## Roadmap

### Near Term
- [ ] LSP server for editor integration
- [ ] Async/await for concurrent I/O
- [ ] More stdlib modules (HTTP server framework, database clients)
- [ ] Package manager

### Long Term
- [ ] Bytecode compiler for performance
- [ ] WebAssembly target
- [ ] Parallel execution model
- [ ] Native compilation (AISL -> C)

---

## About the Name

**AISL** = **A**I-Optimized **S**ystems **L**anguage

Also: "AISL" sounds like "aisle" - a clear path forward for AI code generation.

---

**AISL - Designed by AI, for AI. Built for Everyone.**

*Created through collaborative AI-human design to solve the hard problem: making LLMs generate correct code, reliably.*
