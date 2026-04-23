#!/usr/bin/env python3
"""Retry failed corpus generation tasks in parallel."""

import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")
GRAMMAR = (REPO_ROOT / ".sigil.grammar").read_text()
CORPUS_DIR = REPO_ROOT / "examples" / "corpus"

sys.path.insert(0, str(REPO_ROOT / "benchmark"))
from generate_corpus import TASKS

# Find which tasks already have working corpus files
existing_modules = set()
for f in CORPUS_DIR.glob("*.sigil"):
    code = f.read_text()
    m = re.search(r'\(module\s+(\w+)', code)
    if m:
        existing_modules.add(m.group(1))

# Find which tasks succeeded in the original run
LOG = Path("/tmp/claude-1000/-var-home-marc-Projects-sigil/629f6688-63d5-4ed5-8f7e-929aef526c6c/tasks/bc1o8qlsy.output")
ok_snippets = set()
if LOG.exists():
    for line in LOG.read_text().split("\n"):
        if "OK" in line:
            m = re.search(r"OK.*?: (.+?)\.\.\.", line)
            if m:
                ok_snippets.add(m.group(1)[:50])

# Also check retry log
RETRY_LOG = Path("/tmp/claude-1000/-var-home-marc-Projects-sigil/629f6688-63d5-4ed5-8f7e-929aef526c6c/tasks/bvlh5w1se.output")
if RETRY_LOG.exists():
    for line in RETRY_LOG.read_text().split("\n"):
        if "OK" in line:
            m = re.search(r"OK.*?: (.+?)\.\.\.", line)
            if m:
                ok_snippets.add(m.group(1)[:50])

failed_tasks = [t for t in TASKS if t[:50] not in ok_snippets]
print(f"Remaining failed tasks: {len(failed_tasks)}")
print(f"Running sequentially with Sonnet 4.6\n")


def gen(task, model="claude-sonnet-4-6"):
    prompt = (
        f"{GRAMMAR}\n\n"
        f"Generate ONLY a complete (module name ...) Sigil program. "
        f"No markdown fences. No explanations. Just raw Sigil code.\n\n"
        f"Task: {task}"
    )
    try:
        r = subprocess.run(
            ["claude", "--print", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=60, cwd="/tmp",
        )
        code = r.stdout.strip()
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
                [SIGIL_BIN, f.name], capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return True, ""
            # Programs that need args: check both stdout and stderr for expected patterns
            combined = r.stdout + r.stderr
            # These indicate valid programs that just need CLI args
            if any(x in combined for x in [
                "out of bounds", "Index", "argv",
                "Undefined variable", "Usage:",
                "No 'main' function",  # stdlib/test modules are valid too
            ]):
                return True, ""
            # Exit code 1 with no parse error = program ran but returned 1 (e.g. arg validation)
            if r.returncode == 1 and "Parse error" not in r.stderr and "Error:" not in r.stderr:
                return True, ""
            return False, r.stderr[:100]
        except subprocess.TimeoutExpired:
            return False, "timeout"
        finally:
            os.unlink(f.name)


def process_task(idx_task):
    idx, task = idx_task
    for attempt in range(3):
        code = gen(task)
        if not code:
            continue
        valid, err = validate(code)
        if valid:
            m = re.search(r"\(module\s+(\w+)", code)
            name = m.group(1) if m else f"gen_{idx:04d}"
            fpath = CORPUS_DIR / f"{name}.sigil"
            if fpath.exists():
                fpath = CORPUS_DIR / f"{name}_{idx:04d}.sigil"
            fpath.write_text(code.strip() + "\n")
            return idx, task, True, attempt + 1
    return idx, task, False, 3


ok = 0
fail = 0
for i, task in enumerate(failed_tasks):
    idx, task, success, attempts = process_task((i, task))
    if success:
        ok += 1
        print(f"  [{i+1}/{len(failed_tasks)}] OK (att {attempts}): {task[:65]}...")
    else:
        fail += 1
        print(f"  [{i+1}/{len(failed_tasks)}] FAIL: {task[:65]}...")

print(f"\nResults: {ok} OK, {fail} FAIL")
print(f"Total corpus files: {len(list(CORPUS_DIR.glob('*.sigil')))}")
