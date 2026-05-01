# LLM-Driven Sigil Generation: Strategy & Pipeline

How we get correct Sigil out of language models for corpus extension, in
the cheapest way that preserves Sigil's design principles.

This document is a **post-mortem of the strategy** that emerged from a
campaign extending the corpus past 990 programs. It captures *why* the
pipeline looks the way it does, not just what it does.

## Outcome (so this is real, not theory)

Starting from a set of 32 hard-residue tasks that had previously failed
across multiple model attempts:

| Pipeline iteration | Total solved | Opus calls |
|---|---|---|
| Original (Opus fallback default) | 23/55 (22 via Opus) | 22 |
| After tier-1 changes (aliases, builtins) | 19/32 | 0 |
| Add `str` varargs concat + polymorphic `+` | 21/32 | 0 |
| Add `str` type alias | 21/32 (steady) | 0 |
| Add coaching loop (Sonnet hints, qwen fixes) | 25/32 | 0 |
| Add `fmt %s/%d` + polymorphic `get` | 26/32 | 0 |

**Net: ~9× lift on local-model success rate, zero Opus tokens, ~75% lower
Sonnet spend** versus the original "Sonnet-writes-code" approach.

## Core principles

### 1. Don't fight what the model expects — see if a small language tweak turns failure into success

LLMs are trained on Python, JavaScript, Rust, Java. When asked to produce
Sigil, they reach for muscle-memory idioms first. Two responses are
possible:

- **Reject and re-prompt**: tell the model "Sigil doesn't have that, use X
  instead." Burns tokens. Often doesn't stick across long programs.
- **Accept the idiom if it's *semantically the same* as something Sigil
  already does**: add a lightweight alias.

The second is often free. Examples we shipped:

| LLM idiom | Failure before | Fix |
|---|---|---|
| `(index_of "abc" "b")` | `Undefined: index_of` | Polymorphic `index_of` (string + array dispatch) |
| `(pop arr)` | `Undefined: pop` | New builtin |
| `(parse_int "42")` | `Undefined: parse_int` | New builtin (singular form of `parse_ints`) |
| `(sort_by xs (\(a b) (lt a b)))` | "expects 1 arg, got 2" | Added 2-arg comparator overload |
| `(+ "Hello, " name)` | "Invalid arguments to add" | `+` polymorphic on strings/arrays/maps |
| `(str a b c)` | "str takes 1 argument" | `str` accepts varargs as concat |
| `(fmt "%s=%s" k v)` | output `%s=%s` literally | `fmt` accepts `%s/%d/%f` alongside `{}` |
| `(get m "key")` | `Undefined: get` | Polymorphic strict-access builtin |
| `(fn f x str -> str ...)` | "Expected type but got Symbol(str)" | `str` accepted as alias for `string` in type position |
| `(join arr ",")` vs `(join "," arr)` | "join takes (array, string)" | Both arg orders accepted |

Every one of these is **the same concept** as something Sigil already had —
the alias just accepts the cross-language *name* for it.

### 2. The principles we did NOT compromise

When evaluating a proposed accommodation, check it against Sigil's design.
If accepting the idiom would dilute the language, **don't ship it**.

| Tempting alias | Why we rejected it |
|---|---|
| `i8`/`i16`/`i32`/`i64`/`u32`/`f64`/`isize` | Sigil deliberately doesn't model bit widths. Accepting these would pretend it does. |
| `null` / `nil` / `None` as type tokens | These are *values* in their host languages, not types. Mapping them to `unit` is semantic confusion. |
| `any` / `Any` for unit/dynamic | `any` means "supertype of all" in TS/Kotlin — opposite of unit. |
| Make `set` rebind to a different type | The static binding is load-bearing for type contracts. The fix isn't to weaken `set`; it's to make the patterns that need rebinding (counter loops) work some other way. |
| Make `get` defaulting (return unit on miss) | We have `get_or` for that. `get` is the *strict* form. Each name has a distinct role. |
| Generic dynamic-type escape hatch | Defeats the purpose of having types at all. |

### 3. Evidence-based, not speculative

We added aliases only when the failure log showed a model wrote the
unsupported form. Speculative additions (a full Rust width family, all of
Java's primitive type names, `null`/`None`/`any` etc.) were tried and then
**reverted** when grep showed zero requests across all logs.

The rule: **grep the failure logs before adding an alias**. If the model
isn't asking for it, don't add it.

```bash
grep -hoE "Expected type but got Symbol\([a-zA-Z_]+\)" benchmark/*.json | sort | uniq -c
grep -hoE "Undefined variable: [a-zA-Z_]+" benchmark/*.json | sort | uniq -c
```

### 4. Use a smarter model to coach the local one — not to replace it

A 32B local model produces *almost*-correct Sigil. The naive fix is "ask
Sonnet to write the code instead." But that:

- Burns subscription tokens on output
- Removes qwen's voice from the corpus (less idiom diversity for SFT)
- Doesn't teach qwen anything

The better pattern: **Sonnet writes a 1-3 sentence hint about what's
broken; qwen rewrites its own code with the hint embedded in the prompt.**

```
ollama tries → fails
  ↓
Sonnet sees broken code + error
  ↓
Sonnet emits a SHORT hint (no code)
  ↓
ollama retries with hint embedded in original prompt
  ↓
[loop up to N times]
```

In our run on 20 hard tasks: **5 of 13 wins came from coached qwen** —
qwen wrote the final code, Sonnet only nudged it. Sonnet output was ~150
tokens × 5 (hints) instead of ~300 tokens × 13 (full programs).

### 5. Session-resume to amortize prompt cost

Coaching needs Sonnet to "know" Sigil's grammar. Re-sending the 5K-token
grammar reference on every coaching call wastes tokens.

We use `claude --print --resume <session_id>` so each worker thread
maintains a single Sonnet session per run. The grammar preamble is sent
**once per worker** (and then cached automatically by Anthropic's prompt
cache); subsequent coaching calls only send the per-task delta (broken
code + error + task spec) — typically 200-500 tokens.

Concrete pattern:

```python
# First call per worker: include preamble; capture session_id from --output-format json
# Subsequent calls: --resume <session_id>, send only the delta
```

Implemented in `corpus_extender.py:_claude_with_session`.

### 6. Tier the pipeline cheapest-first; let the cheap tier do most of the work

```
Tier 1: ollama (free, local)         3 attempts at temps 0.0, 0.4, 0.7
   ↓ fail
Tier 2: Sonnet hint → ollama retry   2 coaching cycles
   ↓ fail
Tier 3: Sonnet writes from scratch   2 attempts (last resort)
   ↓ fail
Tier 4: Opus fallback                ONLY if explicitly requested via --fallback
```

Default: **Opus is opt-in** (`--fallback ""`). 99% of runs should not
need it. The campaign above used 0 Opus calls.

## Pipeline file layout

| File | Role |
|---|---|
| `corpus_extender.py` | Per-task pipeline (ollama → coach → Sonnet → optional Opus). Single-shot generation per task with retries. |
| `corpus_extender_batched.py` | Batch variant that asks Sonnet for N programs in one call. Cheaper per-task input cost; harder to coach. |
| `task_bank.py` + `generated_tasks.jsonl` | Task specs (id, desc, args, expected, python reference). |
| `meta_gen_tasks.py` | Generates new task specs from category seeds. |

Run shape:

```bash
# Free-first generation, Opus disabled
python benchmark/corpus_extender.py \
    --ollama-url http://127.0.0.1:11434 \
    --ollama-model qwen2.5-coder:32b \
    --primary claude-sonnet-4-6 \
    --fallback "" \
    --workers 2 --attempts 2

# To retry a specific failing slice
python benchmark/corpus_extender.py --ids "id1,id2" --force ...

# Strict logic-bug residue: fall back to Opus selectively
python benchmark/corpus_extender.py --ids "$(jq -r '...failed...' log.json)" \
    --fallback claude-opus-4-7
```

## When to add a language change vs. when to accept the failure

A failure pattern is worth a language change when:

1. **It appears across multiple tasks** (not a one-off task quirk).
2. **The model's idiom is semantically clean** in the source language
   (e.g. Python `dict.get`, Rust `&str`).
3. **Accepting it doesn't dilute Sigil's principles** (see Section 2).
4. **The fix is small** (a few OCaml lines, no parser surgery).

If those don't hold, the failure stays a failure. Two valid responses:

- **Coach harder**: write a more precise hint prompt that points the model
  away from the idiom.
- **Accept the spec is too hard for the local model**: route it to Sonnet
  or Opus selectively. Not every task needs to come from qwen.

## Pitfalls we hit (and how to avoid)

| Pitfall | Symptom | Fix |
|---|---|---|
| Added `i32`/`u64`/`f64` etc. | Pretending Sigil has bit widths | Pruned. Only ship semantic aliases. |
| Made `arr`/`num`/`obj` reserved keywords | 21 existing tests broke (used these as variable names) | Keep as type aliases in `parse_type`, *don't* add to `type_keywords` reserved list. Parser disambiguates by context. |
| First-attempt-only ollama with temp=0 | "Retrying" was deterministic, gave same wrong answer | Vary temperature on retries (0.0, 0.4, 0.7). |
| Tail-piping background runs | Output buffered until process exits — couldn't see progress | Don't `\| tail -N` background runs. Read the file mid-flight. |
| Subprocess UnicodeDecodeError on bad bytes from Sigil | Whole worker pool crashed mid-run | `subprocess.run(..., errors="replace")`. |
| Speculative aliases without grep evidence | Adds reserved words that block user code | `grep` failure logs FIRST; add only what's actually requested. |

## What the campaign measured (by the numbers)

Hardest-residue task set: 32 IDs that had failed across earlier runs.

```
Round 1 (str alias + 6 builtins + sort_by 2-arg)     → 19 ok / 0 Opus
Round 2 (+ str-varargs + polymorphic +)               → 21 ok / 0 Opus
Round 3 (alias churn — pruned speculative ones)       → 19 ok / 0 Opus
Round 4 (clean run on pruned binary)                  → 12 ok / 0 Opus  [rate-limited mid-run]
Round 5 (coaching loop)                               → 13 ok / 0 Opus  (5 coached qwen wins)
Round 6 (final 7 + fmt %s/%d + polymorphic get)       → 1 ok / 0 Opus  (logic gaps remain)
─────────────────────────────────────────────────────────────────────────
Cumulative coverage of original 32:                    26 / 32 = 81%
```

The 6 leftover tasks have genuine logic-bug issues that won't yield to
language tweaks. They need either:
- Better/more specific coaching prompts
- Selective Opus fallback (`--fallback claude-opus-4-7`)
- Hand-written reference implementations

## Tl;dr for future-self

1. Run with ollama first; Opus off by default.
2. When a model fails, look at *what* it wrote. If it's a clean
   cross-language idiom for the same concept, accept the idiom.
3. Speculative aliases get reverted. Evidence first.
4. When Sonnet has to step in, prefer hints over rewrites.
5. `--resume` Sonnet sessions per worker so the grammar primer isn't
   resent on every call.
