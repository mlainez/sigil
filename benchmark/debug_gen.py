#!/usr/bin/env python3
"""Debug the generation + validation pipeline."""

import subprocess
import tempfile
import os
from pathlib import Path

GRAMMAR = Path("/var/home/marc/Projects/sigil/.sigil.grammar").read_text()
SIGIL_BIN = "/var/home/marc/Projects/sigil/interpreter/_build/default/vm.exe"

task = "Write a program that takes a price and tax rate (as percentages) and prints the total with tax"

prompt = (
    f"{GRAMMAR}\n\n"
    f"Generate ONLY a complete (module name ...) Sigil program. "
    f"No markdown fences. No explanations. Just raw Sigil code.\n\n"
    f"Task: {task}"
)

print(f"Prompt length: {len(prompt)} chars")

r = subprocess.run(
    ["claude", "--print", "--model", "claude-sonnet-4-6", "-p", prompt],
    capture_output=True, text=True, timeout=60, cwd="/tmp",
)
code = r.stdout.strip()
print(f"Code length: {len(code)}")
print(f"Has (module: {'(module' in code}")
print(f"Code:\n{code[:500]}")
print()

# Strip fences
for fence in ["```sigil", "```lisp", "```"]:
    if code.startswith(fence):
        code = code[len(fence):].strip()
        break
if code.endswith("```"):
    code = code[:-3].strip()

print(f"After strip - Has (module: {'(module' in code}")
print(f"After strip length: {len(code)}")

# Validate
with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
    f.write(code)
    f.flush()
    rv = subprocess.run([SIGIL_BIN, f.name], capture_output=True, text=True, timeout=5)
    print(f"\nValidation:")
    print(f"  Exit code: {rv.returncode}")
    print(f"  Stdout: [{rv.stdout[:100]}]")
    print(f"  Stderr: [{rv.stderr[:200]}]")
    os.unlink(f.name)
