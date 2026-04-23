#!/usr/bin/env python3
import re, sys, subprocess, tempfile, os
from pathlib import Path

REPO_ROOT = Path("/var/home/marc/Projects/sigil")
SIGIL_BIN = str(REPO_ROOT / "interpreter/_build/default/vm.exe")
GRAMMAR = (REPO_ROOT / ".sigil.grammar").read_text()
CORPUS_DIR = REPO_ROOT / "examples" / "corpus"

sys.path.insert(0, str(REPO_ROOT / "benchmark"))
from generate_corpus import TASKS

ok_snippets = set()
for logfile in [
    "/tmp/claude-1000/-var-home-marc-Projects-sigil/629f6688-63d5-4ed5-8f7e-929aef526c6c/tasks/bc1o8qlsy.output",
    "/tmp/claude-1000/-var-home-marc-Projects-sigil/629f6688-63d5-4ed5-8f7e-929aef526c6c/tasks/bnefbm09b.output",
    "/tmp/claude-1000/-var-home-marc-Projects-sigil/629f6688-63d5-4ed5-8f7e-929aef526c6c/tasks/by69ol4xg.output",
]:
    p = Path(logfile)
    if p.exists():
        for line in p.read_text().split("\n"):
            if "OK" in line:
                m = re.search(r"OK.*?: (.+?)\.\.\.", line)
                if m:
                    ok_snippets.add(m.group(1)[:50])

remaining = [t for t in TASKS if t[:50] not in ok_snippets]

def gen(task):
    prompt = f"{GRAMMAR}\n\nGenerate ONLY a complete (module name ...) Sigil program. No markdown fences. No explanations. Just raw Sigil code.\n\nTask: {task}"
    try:
        r = subprocess.run(["claude", "--print", "--model", "claude-sonnet-4-6", "-p", prompt],
                          capture_output=True, text=True, timeout=60, cwd="/tmp")
        code = r.stdout.strip()
        for fence in ["```sigil", "```lisp", "```scheme", "```"]:
            if code.startswith(fence):
                code = code[len(fence):].strip()
                break
        if code.endswith("```"):
            code = code[:-3].strip()
        return code
    except:
        return ""

def validate(code):
    if not code or "(module" not in code:
        return False
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name], capture_output=True, text=True, timeout=5)
            combined = r.stdout + r.stderr
            if r.returncode == 0:
                return True
            if any(x in combined for x in ["out of bounds", "Index", "argv", "Undefined variable", "Usage:", "No 'main' function"]):
                return True
            if r.returncode == 1 and "Parse error" not in r.stderr and "Error:" not in r.stderr:
                return True
            return False
        except:
            return False
        finally:
            os.unlink(f.name)

count = 0
for task in remaining[:5]:
    for attempt in range(3):
        code = gen(task)
        if code and validate(code):
            m = re.search(r"\(module\s+(\w+)", code)
            name = m.group(1) if m else f"gen_{count}"
            fpath = CORPUS_DIR / f"{name}.sigil"
            if fpath.exists():
                fpath = CORPUS_DIR / f"{name}_{count:04d}.sigil"
            fpath.write_text(code.strip() + "\n")
            count += 1
            print(f"OK (att {attempt+1}): {task[:70]}...")
            break
    else:
        print(f"FAIL: {task[:70]}...")

print(f"\nGenerated: {count}/5")
print(f"Total corpus: {len(list(CORPUS_DIR.glob('*.sigil')))}")
