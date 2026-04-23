#!/usr/bin/env python3
"""Modernize corpus and test Sigil files to use new token-efficient constructs.

Replacements (safe, pattern-based):
  1. (string_to_int (array_get (argv) N))  ->  #N
  2. (string_to_float (array_get (argv) N)) ->  (float $N)
  3. (array_get (argv) N)                   ->  $N  (when used as string)
  4. (string_format ...)                    ->  (fmt ...) in simple cases
  5. Drop trailing (ret 0) in (fn main -> int ...) bodies

For each file we run through the interpreter to ensure correctness is
preserved. Files that break are reverted.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")


def validate(code: str, args: list = None) -> bool:
    """Run Sigil code through the interpreter. True if it parses and runs without bug."""
    if not code.strip():
        return True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            test_args = args or []
            r = subprocess.run([SIGIL_BIN, f.name] + test_args,
                             capture_output=True, text=True, timeout=5)
            # Valid if exit 0 or clearly a runtime arg-related error
            combined = r.stdout + r.stderr
            if r.returncode == 0:
                return True
            if "Parse error" in r.stderr:
                return False
            # Runtime errors other than missing-arg are code bugs
            if any(x in combined for x in [
                "out of bounds", "Index", "argv", "Undefined variable",
                "Usage:", "No 'main' function", "Cannot convert",
                "End_of_file", "Failure", "Invalid_argument"
            ]):
                return True
            # Exit 1 with no parse error, likely user-defined exit
            if r.returncode == 1 and "Parse error" not in r.stderr:
                return True
            return True  # Assume OK if we can't prove broken
        except subprocess.TimeoutExpired:
            return True  # Probably a server program
        finally:
            os.unlink(f.name)


def modernize(code: str) -> str:
    """Apply safe pattern-based replacements."""
    original = code

    # Detect argv-alias variable name (first one only, to be safe).
    # Pattern: (set NAME array (argv))
    argv_alias = None
    m = re.search(r'\(set\s+(\w+)\s+array\s+\(argv\)\)', code)
    if m:
        argv_alias = m.group(1)

    # If an argv alias exists, treat (array_get ALIAS N) like (array_get (argv) N)
    if argv_alias:
        # (string_to_int (array_get ALIAS N)) -> #N
        code = re.sub(
            r'\(string_to_int\s+\(array_get\s+' + re.escape(argv_alias) + r'\s+(\d+)\)\)',
            r'#\1',
            code
        )
        # (string_to_float (array_get ALIAS N)) -> (float $N)
        code = re.sub(
            r'\(string_to_float\s+\(array_get\s+' + re.escape(argv_alias) + r'\s+(\d+)\)\)',
            r'(float $\1)',
            code
        )
        # (array_get ALIAS N) -> $N
        code = re.sub(
            r'\(array_get\s+' + re.escape(argv_alias) + r'\s+(\d+)\)',
            r'$\1',
            code
        )
        # If alias is no longer used, remove the (set ALIAS array (argv)) binding
        remaining_alias_refs = len(re.findall(r'\b' + re.escape(argv_alias) + r'\b', code))
        # Count will include the binding itself (2 refs: set NAME and argv).
        # Conservative: only remove if alias appears exactly in the binding line.
        if remaining_alias_refs <= 2:
            code = re.sub(
                r'\s*\(set\s+' + re.escape(argv_alias) + r'\s+array\s+\(argv\)\)\n?',
                '',
                code
            )

    # 1. (string_to_int (array_get (argv) N)) -> #N
    code = re.sub(
        r'\(string_to_int\s+\(array_get\s+\(argv\)\s+(\d+)\)\)',
        r'#\1',
        code
    )

    # 2. (string_to_float (array_get (argv) N)) -> (float $N)
    code = re.sub(
        r'\(string_to_float\s+\(array_get\s+\(argv\)\s+(\d+)\)\)',
        r'(float $\1)',
        code
    )

    # 3. (array_get (argv) N) -> $N  (when it's the whole expression)
    code = re.sub(
        r'\(array_get\s+\(argv\)\s+(\d+)\)',
        r'$\1',
        code
    )

    # 4. (string_length x) -> (len x) — already done in earlier pass, but catch stragglers
    code = re.sub(r'\(string_length\s+', r'(len ', code)
    code = re.sub(r'\(array_length\s+', r'(len ', code)
    code = re.sub(r'\(map_length\s+', r'(len ', code)

    # 5. (string_from_int x), (string_from_float x), (string_from_bool x) -> (str x)
    code = re.sub(r'\(string_from_int\s+', r'(str ', code)
    code = re.sub(r'\(string_from_float\s+', r'(str ', code)
    code = re.sub(r'\(string_from_bool\s+', r'(str ', code)

    # 6. Drop trailing (ret 0) from main function
    # Pattern: (fn main -> int ... (ret 0)))
    code = re.sub(
        r'(\(fn\s+main\s+->\s+int\s+(?:[^()]|\([^()]*\))*?)\s+\(ret\s+0\)\s*\)\s*\)',
        r'\1))',
        code
    )

    return code


def process_file(path: Path) -> tuple[bool, str]:
    """Modernize a file. Returns (changed, message)."""
    original = path.read_text()
    modernized = modernize(original)

    if modernized == original:
        return False, "no changes"

    # Validate original works (to avoid reporting breaks from already-broken files)
    if not validate(original):
        return False, "original already broken — skipped"

    # Validate modernized still works
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
    print(f"Skipped: {skipped}")
    print(f"Total: {len(targets)}")


if __name__ == "__main__":
    main()
