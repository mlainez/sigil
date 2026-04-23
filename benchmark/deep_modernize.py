#!/usr/bin/env python3
"""Deep modernization: apply ALL safe efficiency improvements.

After this runs, tests + corpus should use the most token-efficient
constructs available. Each file is validated by running through the
interpreter — if validation fails, the change is reverted.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")


def validate(code: str) -> bool:
    """True if file parses and runs without parse error."""
    if not code.strip():
        return True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name], capture_output=True, text=True, timeout=5)
            # Reject parse errors
            if "Parse error" in r.stderr:
                return False
            return True  # Anything else (including runtime errors due to missing args) is fine
        except subprocess.TimeoutExpired:
            return True  # Server program
        finally:
            os.unlink(f.name)


def modernize(code: str) -> str:
    """Apply all safe modernization patterns."""

    # 1. Drop explicit type from (set x int LITERAL) when LITERAL is a typed literal
    # (set x int 42) -> (set x 42)
    code = re.sub(r'\(set\s+(\w+)\s+int\s+(-?\d+)\)', r'(set \1 \2)', code)
    # (set x float 3.14) -> (set x 3.14)
    code = re.sub(r'\(set\s+(\w+)\s+float\s+(-?\d+\.\d+(?:[eE][+-]?\d+)?)\)', r'(set \1 \2)', code)
    # (set x bool true) -> (set x true)
    code = re.sub(r'\(set\s+(\w+)\s+bool\s+(true|false)\)', r'(set \1 \2)', code)
    # (set x string "...") -> (set x "...")
    code = re.sub(r'\(set\s+(\w+)\s+string\s+(".*?(?<!\\)")\)', r'(set \1 \2)', code)
    # (set x string (some_call ...)) — only when result is obviously string
    # We'll be conservative and only match when it returns a string
    # (set x decimal 19.99d) -> (set x 19.99d)
    code = re.sub(r'\(set\s+(\w+)\s+decimal\s+(-?\d+(?:\.\d+)?d)\)', r'(set \1 \2)', code)

    # 2. (string_format ...) -> (fmt ...) — same semantics, shorter name
    code = re.sub(r'\(string_format\s', r'(fmt ', code)

    # 3. Drop (set ARGS array (argv)) when ARGS only used as (array_get ARGS N)
    # Find (set ARGS array (argv)) and rewrite all (array_get ARGS N) to $N
    arg_alias_pattern = re.compile(r'\(set\s+(\w+)\s+array\s+\(argv\)\)\s*\n?')
    aliases_seen = []
    for m in arg_alias_pattern.finditer(code):
        aliases_seen.append(m.group(1))

    for alias in aliases_seen:
        # Replace (string_to_int (array_get ALIAS N)) with #N
        code = re.sub(r'\(string_to_int\s+\(array_get\s+' + re.escape(alias) + r'\s+(\d+)\)\)',
                     r'#\1', code)
        # Replace (string_to_float (array_get ALIAS N)) with (float $N)
        code = re.sub(r'\(string_to_float\s+\(array_get\s+' + re.escape(alias) + r'\s+(\d+)\)\)',
                     r'(float $\1)', code)
        # Replace (array_get ALIAS N) with $N
        code = re.sub(r'\(array_get\s+' + re.escape(alias) + r'\s+(\d+)\)', r'$\1', code)
        # If alias no longer appears outside its declaration, remove the binding
        all_refs = len(re.findall(r'\b' + re.escape(alias) + r'\b', code))
        if all_refs <= 2:  # only the (set ALIAS array (argv)) binding line itself
            code = re.sub(r'\s*\(set\s+' + re.escape(alias) + r'\s+array\s+\(argv\)\)\n?',
                         '\n', code)

    # 4. Drop trailing (ret 0) from main — but only when main returns int
    # Pattern: (fn main -> int <body containing some (ret 0) at end>)
    # This is tricky to do safely with regex. Let's do a careful targeted rewrite:
    # find " (ret 0))" or "(ret 0)\n)" within (fn main -> int ...)
    # Simpler: scan for "(fn main -> int" and look for last (ret 0) before matching close-paren.
    # Skip for safety unless we have a paren matcher.

    # 5. (array_get arr (sub (len arr) 1)) -> (last arr)
    # The arg name has to match
    code = re.sub(r'\(array_get\s+(\w+)\s+\(sub\s+\(len\s+\1\)\s+1\)\)',
                 r'(last \1)', code)

    # 6. Standard renames (in case any slipped through)
    code = re.sub(r'\(string_length\s', r'(len ', code)
    code = re.sub(r'\(array_length\s', r'(len ', code)
    code = re.sub(r'\(map_length\s', r'(len ', code)
    code = re.sub(r'\(string_from_int\s', r'(str ', code)
    code = re.sub(r'\(string_from_float\s', r'(str ', code)
    code = re.sub(r'\(string_from_bool\s', r'(str ', code)

    # 7. Rename variable named 'len' (shadows builtin) to 'n'
    # Only safe when the rename is consistent within scope. Simple heuristic: if file has
    # (set len int ...) and uses len only as (for-each ... len ...) etc.
    if re.search(r'\(set\s+len\s+int', code):
        # Check no occurrence of (len ...) call with len as arg list
        # Risky — skip for now unless we want to do scope analysis
        pass

    return code


def process_file(path: Path) -> tuple[bool, str]:
    """Modernize a file. Returns (changed, message)."""
    original = path.read_text()
    modernized = modernize(original)

    if modernized == original:
        return False, "no changes"

    if not validate(original):
        return False, "original already broken — skipped"

    if not validate(modernized):
        return False, "modernization broke validation — reverting"

    path.write_text(modernized)
    return True, "updated"


def main():
    targets = []
    for d in [REPO_ROOT / "examples" / "corpus", REPO_ROOT / "tests"]:
        if d.exists():
            targets.extend(sorted(d.glob("*.sigil")))

    updated = 0
    skipped = 0
    unchanged = 0

    for f in targets:
        changed, msg = process_file(f)
        if changed:
            updated += 1
        elif msg == "no changes":
            unchanged += 1
        else:
            skipped += 1
            print(f"  {f.name}: {msg}")

    print(f"\nUpdated: {updated}")
    print(f"Unchanged: {unchanged}")
    print(f"Skipped (broken or break-on-modernize): {skipped}")
    print(f"Total: {len(targets)}")


if __name__ == "__main__":
    main()
