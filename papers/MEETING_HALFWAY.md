# Meeting the Model Halfway: Language Design as Reasoning Aid

> **Status (2026-05-04): Sigil project closed.** This methodology was
> validated as the most durable transferable contribution. It ports
> verbatim to the successor project (`post-sigil/`). See
> [`SIGIL_RESULT.md`](./SIGIL_RESULT.md) for the close-out narrative;
> the principles below remain the operational guide for any future
> language-meets-pretrained-model design.

**Status:** working draft, 2026-04-30; promoted to *operational design philosophy* on 2026-05-01 after Phase 17 retrospective.
**Position:** what started as one design principle among many has become **the** design philosophy that emerged from working with pre-trained models. The original "ONE WAY ONLY" principle from the README turned out to be aspirational — the practical Sigil has ~30 aliases, each earned by a benchmark win where a model reached for a name from its training distribution.

Meeting halfway is not a workaround for the original design; it is what the design *became* when subjected to months of empirical testing against pre-trained Coder models.

## 1. The principle

When a small local LLM consistently produces a particular *shape* of
incorrect program, an AI-optimised language should consider absorbing
that mistake into its semantics or surface — making the model's
first-instinct expression produce correct code.

This is the inverse of conventional language design, which expects the
programmer to learn the language's idioms. An AI-optimised language
treats the model as the dominant programmer, and observes which idioms
the model reaches for under failure. Idioms that model after model
reaches for, on task after task, become evidence that the language's
existing surface is at the wrong altitude. The fix is not to teach
the model harder; it is to lower the language to where the model
already lives.

We call this **meeting the model halfway**. Not all the way: the
language still has a designed shape, a philosophy, an aesthetic. But
the parts of that shape that consistently mismatch with how the
model *naturally* reaches for solutions are evidence, not defects of
the model.

## 2. Why this is reasonable

Three observations support the position.

### 2.1 The model's reasoning path is approximately fixed

A 7B coder model, fine-tuned to a domain or not, has a strong
default for *how it reaches for solutions*. It pattern-matches from
its training distribution. You can lift the destination (what
language it writes) but not easily the path (the structural moves it
makes between problem and solution). When it consistently writes
`(zip a b)` to interleave two strings, that "zip" reach is baked
into the weights deeply enough that no amount of in-context priming
will redirect it on every call.

### 2.2 The cost of a new builtin is small

`zip`, `repeat_each`, `string_at` — each is a few dozen lines of
interpreter code. They are additive: existing programs continue to
parse and run. They do not foreclose any future design choice. The
risk of regret is bounded.

### 2.3 The compounding benefit is large

Each new builtin that meets a common reasoning move:
- Removes a class of failures from the corpus
- Removes a class of failures from inference
- Removes a category of corpus example that would otherwise need to
  teach the workaround

A single well-chosen builtin pays for itself across thousands of
generations.

## 3. Where the principle does NOT apply

The line is not arbitrary. The principle bends when:

- The mistake is a **reasoning failure that no syntax could absorb**.
  The model wrote `L(0)=2, L(1)=1` but then ran 5 iterations instead
  of 6 to compute Lucas(6). No language change makes that off-by-one
  go away. Document the pattern in corpus, but do not invent
  semantics.
- The mistake is a **memory failure**: the model thinks Padovan
  starts `1,1,2` instead of `1,1,1`. No language can fix the model's
  recall of a definition.
- The mistake **violates the language's coherent design**. Sigil is a
  Lisp; admitting Python-style indexing `s[i]` would change what
  Sigil *is*. The model can learn `(string_at s i)`; we should not
  change to `[i]` for it.
- The mistake is **a typo, not a reach**. The model emitted an extra
  closing paren. That is not a reasoning move; it is a counting
  failure. The right response is better diagnostics (the `--lint`
  mode), not a language that accepts unbalanced parens.

The decision rule: *if the model is reaching for a sensible
abstraction that has a clean implementation in the language's
existing style, add it. If the model is making a mistake about how
its own output should be balanced or what definitions are, the
language cannot fix that.*

## 4. Concrete fixes from the present work

The Sigil project has accumulated a sequence of meeting-halfway
decisions over the course of this research. Cataloguing them
illustrates the principle in action.

### 4.1 Polymorphic numeric operators

`(- x)` was originally a binary subtraction only. Models reach for
unary `-` constantly (Lisp/Scheme tradition, also Python's `-x`).
Adding unary form costs nothing and matches the reach.

### 4.2 `for-each` over strings

`for-each` originally required an array or map. Models reach for
`(for-each c s ...)` to iterate over the characters of a string.
Adding string iteration matches the reach. The alternative was
forcing every model to wrap with `(chars s)`, which adds noise and
is a frequent forgotten step.

### 4.3 `string_at` (NEW)

The pre-existing `string_get` returns the int char code. Models
reach for "give me the character as a string I can compare to other
strings." `string_at` returns a 1-character string. Both coexist;
`string_get` retains its low-level semantics for code that needs
the int.

### 4.4 `repeat_each` (NEW)

Pattern: `(join (map_arr coll (\x (repeat x n))) "")` — three
nested calls to express "repeat each element n times in place."
Models reach for it implicitly but execute it wrong. `repeat_each`
makes the obvious intent the obvious code.

### 4.5 `zip` (NEW)

Pattern: explicit index walk over two collections. Models get
off-by-one. `zip` makes the obvious intent a single call. The
language's existing polymorphism extends naturally: `zip` on two
strings returns a string; on two arrays returns an array.

### 4.6 `do` / `begin` / `progn`

Multi-statement bodies in Lisp dialects use `(do ...)` (Clojure),
`(begin ...)` (Scheme), `(progn ...)` (Common Lisp). Models reach
for one of these depending on what they were trained on most. All
three now resolve to the same Sigil construct. Adding the alias
costs nothing; not adding it forced gymnastic rewrites on every
retry.

### 4.7 PCRE-compatible regex via the Re library (canonical structural example)

This is the largest single meet-halfway change in the project's
history and the clearest illustration of the principle.

**Observation.** Across thousands of model-generated regexes during
the benchmark work, the model overwhelmingly writes Perl-compatible
regex syntax: `\b` for word boundaries, `\d`/`\w`/`\s` for character
classes, `*?`/`+?` for non-greedy quantifiers, `|` for alternation
without escape. This is uniformly the case across all trained Coder
models — Python `re`, JavaScript, Java, Perl, C#, and PHP all use
PCRE or compatible flavours. The model's training distribution is
overwhelmingly PCRE.

**Mismatch.** Sigil's interpreter originally backed regex with
OCaml's `Str` library, a POSIX-style flavour that requires escaped
alternation (`\|`), has no `\b`/`\d`/`\w`/`\s` shorthands, no
non-greedy quantifiers, treats `(` as a literal rather than a group
opener, and rejects `{n,m}` without explicit translation (we
maintained a `regex_translate_braces` helper for this).

The cost was a long tail of "regex matched nothing" failures across
the benchmark — `extract_emails`, `extract_dotted_ipv4`,
`extract_phone_numbers`, etc. — where the model wrote a syntactically
sensible Perl regex that `Str` silently rejected or misinterpreted.

**Fix.** Replaced `Str` with the [`re`](https://github.com/ocaml/ocaml-re)
library (Markus Mottl, well-maintained, packaged via opam). Single
helper: `Re.Perl.compile_pat` parses Perl-flavoured patterns natively.
Roughly 60 lines of `interpreter.ml` change across `regex_compile`,
`regex_match`, `regex_find`, `regex_find_all`, `regex_replace`. Kept
`regex_translate_braces` as dead code for now in case any external
caller depends on it; can be removed later.

**Cost.** ~30 minutes to swap; ~10 minutes to update the 4 alternation
tests in `test_regex.sigil` that used Str-style escaped pipes.
156/156 tests pass.

**Caveat / next step.** The 2186-entry training corpus contains
older examples using Str-style regex (literal `(`, escaped `\|`).
Under PCRE these patterns now error rather than silently matching
the wrong thing. Stream C dropped 2 tasks immediately after the
swap (`extract_function_names_py`, plus an unrelated generation
variance on `shell_argv_count`). The full payoff of the PCRE swap
requires a corpus refresh sweep + a Qwen v6 retrain; that work is
pending.

**Why this is the canonical example.** Every other meet-halfway
change in this section absorbs a model reach for a *single name* or
a *single shape*. The PCRE swap absorbs an entire **flavour** —
hundreds of distinct patterns the model knows how to write. It's
the largest leverage-per-line-of-code change in the project, and
the cleanest illustration that the right scope of "meet halfway"
is sometimes "pick the same regex flavour the model's training
distribution uses" rather than "add an alias."

### 4.7 Bit-op aliases

`band`, `bitand`, `xor`, `rsh`, `shl` — the canonical names are
`bit_and`, `bit_or`, `bit_xor`, `bit_shift_right`, `bit_shift_left`.
Models reach for the shorter forms (especially when imitating C/Rust
syntax). All resolve to the canonical implementations.

### 4.8 `keys` / `values` aliases for `map_keys` / `map_values`

Python/Ruby/JS reach. Aliases.

### 4.9 Adding standard 3-arg `if`

Sigil originally required `(if cond then-body (else else-body))` —
the explicit `(else ...)` wrap. Models reach for the standard
Lisp/Scheme `(if cond then else)` shape. We added support for
both; `(else ...)` remains for multi-statement else bodies.

### 4.10 What we did *not* do

To honour §3, here are mistakes we explicitly did NOT absorb:

- **Off-by-one errors in scans.** Adding "smart range" semantics
  would obscure rather than help. The corpus teaches the right
  pattern; the language does not lie about boundaries.
- **`(repeat str)` defaulting to 1.** Some models reach for
  `(repeat "ab")` expecting it to return "ab". We do not silently
  succeed on missing args; a missing arg is a reasoning error,
  not a reach we should support.
- **Python-style indexing `s[i]`.** This would break the
  S-expression grammar. The model can learn `string_at`.
- **Implicit type coercion in `eq`**. Comparing a string and an int
  is almost always a bug; we surface it as a type error rather than
  silently returning false.
- **Auto-balancing parens.** Lint reports the position; the model
  retries with a precise hint. The language does not pretend
  malformed programs are correct.

## 5. How to decide when to meet halfway

A practical test, derived from the failures observed in this work:

1. **Frequency.** The model reaches for the same shape in ≥3
   independent failure cases. (One-off failure: probably not a reach.)
2. **Cleanness.** A clean implementation exists in the language's
   existing style. (No syntax change required.)
3. **Composability.** The new builtin composes with existing
   builtins without breaking a published contract.
4. **Backward compatibility.** Existing programs continue to behave
   identically.
5. **Documentability.** The new builtin can be described in a single
   line of grammar header.

If all five hold, add the **function** (not necessarily as an OCaml
builtin — see below). If any fails, document the reach in corpus
and move on.

**Where the function lives** is a separate decision from whether to
add it. The interpreter has a small core of true builtins (I/O,
regex, syscall, runtime primitives, performance-critical ops); the
rest belongs in `stdlib/` written in Sigil. An auto-loaded prelude
gives stdlib functions the same zero-import experience as builtins
without inflating the OCaml dispatch table. See
`stdlib/README.md` for the boundary principle. The default for a
new meet-halfway addition is the prelude, not the interpreter; an
OCaml builtin should be justified by one of the four primitive
conditions in that doc.

## 6. Relation to the AI-optimised language hypothesis

Meeting halfway is the operational expression of the broader
hypothesis that drives this research: *that language designed for
the LLM-as-primary-programmer should differ in measurable ways from
language designed for the human-as-primary-programmer.*

The classical answer to "the model writes wrong code" is: train the
model harder. The AI-optimised answer is: notice which wrong codes
share a shape, and ask whether the shape is the language's hint to
evolve. Not every reach should be absorbed (§3), but most well-formed
reaches that the language could trivially admit should be.

A language that does this systematically becomes, over time, a
better fit for its model than for any human. That is the trade.
For workflows where the model is the primary programmer (agentic
tooling), that trade pays. For workflows where humans write most of
the code (general application development), the trade may not pay —
which is why this approach is specifically about *agent tooling*
and not about replacing Python.

## 7. Reproducibility commitment

Every meeting-halfway change in this work is documented in the git
log of `interpreter/interpreter.ml` and `interpreter/parser.ml` with
a commit message that names:
- The failure pattern observed
- The number of distinct tasks where it was observed
- The specific reach the model made
- The fix (alias / new builtin / parser tolerance)
- The regression-sweep result on the existing 1977-file corpus

Reviewers can reconstruct the path from any of these commits and
audit whether the principle was applied correctly.

## 8. Limitations

- **Subjective interpretation.** "Meet halfway" is a principle, not
  an algorithm. Different reviewers might draw §3's line differently.
- **Corpus drift.** As more changes are absorbed into the language,
  the model's reaches may shift in unpredictable ways. We need to
  re-measure periodically rather than assume the early reaches are
  the final ones.
- **Risk of bloat.** Each addition makes the language larger. We
  must periodically prune or re-canonicalise to keep the surface
  coherent.
- **Risk of overfitting to one model.** If we only ever measure
  reaches from Qwen-Coder, the language might absorb that model's
  quirks rather than universal patterns. Cross-validation against
  other small coder models is needed before claiming a fix is
  general.

These are real limitations. The principle is sound; its application
needs ongoing care.
