#!/usr/bin/env python3
"""Retry failed corpus generation tasks."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")
GRAMMAR = (REPO_ROOT / ".sigil.grammar").read_text()
CORPUS_DIR = REPO_ROOT / "examples" / "corpus"

sys.path.insert(0, str(REPO_ROOT / "benchmark"))
from generate_corpus import TASKS

# Find which tasks already have corpus files by checking existing code
existing_code = set()
for f in CORPUS_DIR.glob("*.sigil"):
    existing_code.add(f.read_text().strip()[:100])

# Also check which tasks succeeded from the log
LOG = Path("/tmp/claude-1000/-var-home-marc-Projects-sigil/629f6688-63d5-4ed5-8f7e-929aef526c6c/tasks/bc1o8qlsy.output")
ok_snippets = set()
if LOG.exists():
    for line in LOG.read_text().split("\n"):
        if "OK" in line:
            m = re.search(r"OK.*?: (.+?)\.\.\.", line)
            if m:
                ok_snippets.add(m.group(1)[:50])

failed_tasks = []
for task in TASKS:
    if task[:50] not in ok_snippets:
        failed_tasks.append(task)

print(f"Failed tasks to retry: {len(failed_tasks)}")


def gen(task, model="claude-haiku-4-5-20251001"):
    prompt = (
        f"{GRAMMAR}\n\n"
        f"Generate ONLY a complete (module name ...) Sigil program. "
        f"No markdown fences. No explanations. Just the raw Sigil code.\n\n"
        f"Task: {task}"
    )
    try:
        r = subprocess.run(
            ["claude", "--print", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=60, cwd="/tmp",
        )
        code = r.stdout.strip()
        # Strip markdown fences
        for fence in ["```sigil", "```lisp", "```scheme", "```"]:
            if code.startswith(fence):
                code = code[len(fence):].strip()
                break
        if code.endswith("```"):
            code = code[:-3].strip()
        return code
    except Exception:
        return ""


def validate(code):
    if not code or "(module" not in code:
        return False, "no module"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            r = subprocess.run(
                [SIGIL_BIN, f.name],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return True, ""
            stderr = r.stderr
            if any(x in stderr for x in ["out of bounds", "Index", "argv", "Undefined variable"]):
                return True, ""
            return False, stderr[:100]
        except subprocess.TimeoutExpired:
            return False, "timeout"
        finally:
            os.unlink(f.name)


ok = 0
fail = 0
for i, task in enumerate(failed_tasks):
    success = False
    for attempt in range(3):
        code = gen(task)
        if not code:
            continue
        valid, err = validate(code)
        if valid:
            m = re.search(r"\(module\s+(\w+)", code)
            name = m.group(1) if m else f"gen_{i:04d}"
            fpath = CORPUS_DIR / f"{name}.sigil"
            if fpath.exists():
                fpath = CORPUS_DIR / f"{name}_{i:04d}.sigil"
            fpath.write_text(code.strip() + "\n")
            ok += 1
            print(f"  [{i+1}/{len(failed_tasks)}] OK (att {attempt+1}): {task[:60]}...")
            success = True
            break
    if not success:
        fail += 1
        print(f"  [{i+1}/{len(failed_tasks)}] FAIL: {task[:60]}...")

print(f"\nRetry results: {ok} OK, {fail} FAIL")
print(f"Total corpus files: {len(list(CORPUS_DIR.glob('*.sigil')))}")
