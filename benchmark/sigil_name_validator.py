"""Static name validator for generated Sigil code.

NH2 Tier A: catches hallucinated builtins / made-up names BEFORE running
the program, so the retry loop can give the model a targeted "you wrote
NAME which doesn't exist; use PATTERN instead" hint instead of letting
the program fail at runtime with a generic "Undefined variable" error
that the model often can't act on.

The whitelist is loaded once at import time:
  - Direct match cases from interpreter/interpreter.ml's main match block
  - Symbol-rewrite aliases (the `let -> set` table at line ~1426)
  - Special forms parsed by parser.ml
  - Prelude functions defined in stdlib/core/prelude.sigil

User-defined functions (any `(fn NAME ...)` in the program itself) are
discovered at validate-time from the code under inspection.

Returns the unknown names encountered, with line numbers for the retry
prompt. The targeted-suggestion table maps known-bad reaches to canonical
patterns (json_incr → use json_set + get_or, etc.).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parent.parent
INTERP = REPO / "interpreter" / "interpreter.ml"
PARSER = REPO / "interpreter" / "parser.ml"
PRELUDE = REPO / "stdlib" / "core" / "prelude.sigil"


def _load_builtins() -> set[str]:
    """Parse interpreter.ml for every match-case starting `| "name"` in the
    builtin dispatch table. Includes ~240 names: print, println, set, len,
    str, fmt, split, join, sort, push, filter, map_arr, etc.

    Two patterns to catch:
      1. `| "NAME" -> ...` — main dispatch table (most builtins)
      2. `| Call ("NAME", ...) -> ...` — AST-level pattern matches (fmt is
         the canonical case, dispatched before main table for variadic args)
    Also catches chained name-aliases like `| "band" | "bitand" -> "bit_and"`
    where each alternative should be in the whitelist.
    """
    text = INTERP.read_text()
    names = set()
    # Pattern 1: main dispatch — `| "name" -> ...` or `| "a" | "b" -> ...`
    for m in re.finditer(r'^\s*\|\s*"([a-z_][a-z0-9_]*)"\s*(?:\||->)', text, re.M):
        names.add(m.group(1))
    # Pattern 2: AST-level Call match — `| Call ("name", ...)`
    for m in re.finditer(r'^\s*\|\s*Call\s*\(\s*"([a-z_][a-z0-9_]*)"', text, re.M):
        names.add(m.group(1))
    # Pattern 3: chained aliases — alternative names separated by `|` before `->`
    for m in re.finditer(r'^\s*\|\s*((?:"[a-z_][a-z0-9_]*"\s*\|\s*)+"[a-z_][a-z0-9_]*")\s*->',
                          text, re.M):
        for alt in re.findall(r'"([a-z_][a-z0-9_]*)"', m.group(1)):
            names.add(alt)
    return names


def _load_aliases() -> dict[str, str]:
    """Parse the eval_call symbol-rewrite table at line ~1426. Returns
    a dict mapping alias -> canonical (e.g. 'parse_float' -> 'float')."""
    text = INTERP.read_text()
    aliases = {}
    for m in re.finditer(r'^\s*\|\s*"([a-z_][a-z0-9_]*)"\s*(?:\|\s*"[^"]*"\s*)*->\s*"([a-z_]+)"',
                          text, re.M):
        aliases[m.group(1)] = m.group(2)
    # Also pull the chained-alias forms like `"band" | "bitand" | ... -> "bit_and"`
    for m in re.finditer(r'^\s*\|\s*((?:"[a-z_+\-*/%<>=!]+"\s*\|?\s*)+)->\s*"([a-z_]+)"',
                          text, re.M):
        for alias in re.findall(r'"([^"]+)"', m.group(1)):
            aliases[alias] = m.group(2)
    return aliases


def _load_special_forms() -> set[str]:
    """Parse parser.ml for special-form keywords."""
    return {
        "set", "let", "ret", "return", "if", "while", "loop", "for", "for-each",
        "and", "or", "not", "break", "continue", "cond", "do", "else",
        "fn", "module", "import", "test-spec", "case", "input", "expect", "meta-note",
        "true", "false",
    }


def _load_prelude_functions() -> set[str]:
    """Parse prelude.sigil for `(fn NAME ...)` definitions."""
    if not PRELUDE.exists():
        return set()
    text = PRELUDE.read_text()
    return set(re.findall(r'\(fn\s+([a-z_][a-z0-9_]*)', text))


# Build the full whitelist once
BUILTINS = _load_builtins()
ALIASES = _load_aliases()
SPECIAL_FORMS = _load_special_forms()
PRELUDE_FNS = _load_prelude_functions()
KNOWN_NAMES = BUILTINS | set(ALIASES.keys()) | SPECIAL_FORMS | PRELUDE_FNS


# Canonical-fix suggestions for common hallucinations. Each entry maps an
# observed-but-bad name to a one-line guidance string. Built incrementally
# as we see new misuses in the failure traces.
HALLUCINATION_FIXES = {
    "json_incr": (
        "(json_incr ...) doesn't exist. For count-by-key use the canonical "
        "pattern: (set m (json_set m [k] (add (get_or m k 0) 1)))"
    ),
    "json_decr": (
        "(json_decr ...) doesn't exist. To decrement use json_set with "
        "(sub (get_or m k 0) 1)."
    ),
    "argv_str": (
        "(argv_str) doesn't exist as a no-arg call. Use $0/$1/... for "
        "literal CLI args, or (arg_str i) for variable index."
    ),
    "stdin": (
        "(stdin) doesn't exist. The harness passes the whole input as $0; "
        "use (split $0 \"\\n\") to iterate lines."
    ),
    "read_input": (
        "(read_input) doesn't exist. Input is in $0 — use it directly."
    ),
    "max": (
        "(max) on a collection isn't a builtin. For max element use "
        "(last (sort xs)) or (reduce xs (\\a b (if (gt a b) a b)) 0)."
    ),
    "min": (
        "(min) on a collection isn't a builtin. For min element use "
        "(first (sort xs))."
    ),
    "to_lower": "use (lower s)",
    "to_upper": "use (upper s)",
    "to_string": "use (str v)",
    "starts_with": "use (string_starts_with s prefix)",
    "ends_with": "use (string_ends_with s suffix)",
    "string_split": "use (split s sep)",
    "string_join": "use (join arr sep)",
    "string_replace": "use (string_replace s old new)",
    "list": "use [] for empty array literal",
    "dict": "use {} for empty map literal",
    "array_new": "use [] for empty array literal",
    "map_new": "use {} for empty map literal",
}


class ValidationResult(NamedTuple):
    unknown_names: list[str]      # Names that aren't in the whitelist
    user_defined: set[str]        # Names defined by `(fn ...)` in this code
    targeted_hints: list[str]     # Per-unknown-name guidance
    wrong_language: str            # "" or "python"/"javascript"/... if detected


# Markers that mean the model emitted a different language entirely. When
# observed we short-circuit the unknown-names pathway with a clearer
# "rewrite in Sigil" instruction.
PYTHON_MARKERS = re.compile(
    r'^\s*(?:python\s*$|```python|from\s+\w+\s+import\s+|def\s+\w+\s*\(|'
    r'class\s+\w+\s*[:\(]|import\s+\w+\s*$|f"[^"]*\{[^}]+\}"|f\'[^\']*\{[^}]+\}\')',
    re.M,
)
JS_MARKERS = re.compile(
    r'^\s*(?:```javascript|const\s+\w+\s*=|function\s+\w+\s*\(|=>\s|console\.log\()',
    re.M,
)


def _detect_wrong_language(code: str) -> str:
    """Return 'python' / 'javascript' / '' if the generated code looks like
    a different language entirely. Models occasionally collapse to the
    pre-training distribution for code generation."""
    if PYTHON_MARKERS.search(code):
        return "python"
    if JS_MARKERS.search(code):
        return "javascript"
    return ""


def _strip_strings_and_comments(code: str) -> str:
    """Replace string literals with placeholder characters so name-grep
    doesn't match identifier-shaped tokens inside string contents. Sigil
    has no comments, so only string literals matter."""
    out = []
    i = 0
    in_str = False
    while i < len(code):
        c = code[i]
        if in_str:
            if c == "\\" and i + 1 < len(code):
                out.append("  ")
                i += 2
                continue
            if c == '"':
                out.append('"')
                in_str = False
            else:
                out.append(" ")
            i += 1
        else:
            out.append(c)
            if c == '"':
                in_str = True
            i += 1
    return "".join(out)


def validate(code: str) -> ValidationResult:
    """Walk Sigil code, identify all (NAME ...) call positions, return the
    set of names that aren't in our whitelist (or aren't user-defined in
    this same program)."""
    safe = _strip_strings_and_comments(code)

    # User-defined functions: any `(fn NAME ...` declaration.
    user_defined = set(re.findall(r'\(fn\s+([a-z_][a-z0-9_]*)', safe))

    # Lambda parameter names: `(\NAME ...)` or `(\(NAME1 NAME2 ...) ...)`.
    # These are local binders, not calls — don't flag them as unknowns.
    lam_params = set()
    for m in re.finditer(r'\\([a-z_][a-z0-9_]*)\b', safe):
        lam_params.add(m.group(1))
    for m in re.finditer(r'\\\(([a-z_][a-z0-9_\s]*)\)', safe):
        for nm in m.group(1).split():
            lam_params.add(nm)

    # `set NAME val` and `let NAME val` introduce local variables. Collect them
    # so we don't flag references like `(NAME args...)` as unknown calls when
    # NAME is actually a higher-order function value bound earlier.
    locals_ = set(re.findall(r'\((?:set|let)\s+([a-z_][a-z0-9_]*)', safe))

    # Collect every (NAME ... call position. Names in our whitelist + user-defined
    # + lambda-param + locals are fine; everything else is suspect.
    call_names = re.findall(r'\(([a-z_][a-z0-9_-]*)', safe)

    unknown = []
    seen = set()
    for nm in call_names:
        if nm in KNOWN_NAMES or nm in user_defined or nm in lam_params or nm in locals_:
            continue
        if nm in seen:
            continue
        seen.add(nm)
        unknown.append(nm)

    # Generate targeted hints for known-hallucination patterns
    hints = []
    for nm in unknown:
        if nm in HALLUCINATION_FIXES:
            hints.append(f"  - {HALLUCINATION_FIXES[nm]}")

    return ValidationResult(
        unknown_names=unknown,
        user_defined=user_defined,
        targeted_hints=hints,
        wrong_language=_detect_wrong_language(code),
    )


def format_validation_hint(result: ValidationResult) -> str:
    """Build a clear retry hint from a ValidationResult. Used by the
    retry loop in eval_real_tooling.py and sigil_mcp_server.py."""
    # Wrong-language path takes priority — don't bother listing every
    # Python identifier as "unknown name" when the whole program is Python.
    if result.wrong_language == "python":
        return ("Your program is Python, not Sigil. Rewrite it using Sigil's "
                "S-expression syntax: (set x val), (for-each x xs ...), "
                "(println msg), (split $0 \"\\n\"), etc. Do NOT use 'def', "
                "'import', 'from', 'class', or f-strings. Do NOT include "
                "code-fence headers like 'python' or '```'. Output only "
                "raw Sigil code.")
    if result.wrong_language == "javascript":
        return ("Your program is JavaScript, not Sigil. Rewrite it using "
                "Sigil's S-expression syntax. Do NOT use 'const', 'function', "
                "arrow functions, or console.log. Output only raw Sigil code.")
    if not result.unknown_names:
        return ""
    head = (f"Your program references {len(result.unknown_names)} name(s) "
            f"that don't exist as builtins, aliases, special forms, or "
            f"functions you defined: {', '.join(result.unknown_names)}. ")
    if result.targeted_hints:
        body = "Specific fixes:\n" + "\n".join(result.targeted_hints) + "\n"
    else:
        body = ""
    tail = ("Re-write the program using only valid Sigil names. The "
            "canonical builtins are listed in the system prompt header.")
    return head + body + tail


if __name__ == "__main__":
    import sys
    print(f"Loaded {len(BUILTINS)} builtins, {len(ALIASES)} aliases, "
          f"{len(SPECIAL_FORMS)} special forms, {len(PRELUDE_FNS)} prelude "
          f"functions = {len(KNOWN_NAMES)} known names total.\n")

    # Self-test on a known-bad snippet (the log_top_4xx_ip Path B failure)
    bad_code = """python
(set logs [])
(for-each line (split $0 "\\n")
    (push logs (json_parse line)))

(set counts {})
(for-each log logs
    (let ip (array_get log 0))
    (let code (int (array_get log 8)))
    (if (and (ge code 400) (lt code 600))
        (set counts (json_incr counts [ip] 1))))

(println (fmt "{}\\t{}" "ip" "count"))"""
    result = validate(bad_code)
    print(f"Self-test result on log_top_4xx_ip-style code:")
    print(f"  Unknown names: {result.unknown_names}")
    print(f"  User-defined:  {sorted(result.user_defined)}")
    print(f"  Hints:")
    for h in result.targeted_hints:
        print(h)
    print()
    print("Formatted hint to retry prompt:")
    print(format_validation_hint(result))
