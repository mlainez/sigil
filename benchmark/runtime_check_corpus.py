#!/usr/bin/env python3
"""Pass 3 of corpus cleanup: runtime check.

For each entry, run vm.exe with an empty CLI arg. The point is not to verify
correctness (we don't have expected outputs) but to catch the silent-poison
shape: code that lints fine but references a non-existent builtin or variable.
Those would runtime-error with `Undefined variable: X` or `Unknown function: X`.

We classify each entry's runtime outcome:
  ok            - exit code 0, any output
  type_error    - "Type mismatch: ..." (legitimate runtime error from arg shape)
  index_error   - "out of bounds" (legitimate, depends on input)
  undefined     - "Undefined variable" or "Unknown function" — the silent poison
  panic         - explicit (panic ...) call from the program
  parse_error   - shouldn't happen after pass 2, but catch anyway
  timeout       - 5s wall

Entries with `undefined` are dropped or fixed.
"""
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIGIL = str(REPO / "interpreter" / "_build" / "default" / "vm.exe")
CORPUS_IN = REPO / "benchmark" / "training_corpus.cleaned.jsonl"
CORPUS_OUT = REPO / "benchmark" / "training_corpus.runtime_clean.jsonl"
LOG_OUT = REPO / "benchmark" / "runtime_check_log.txt"


def classify_run(code: str) -> tuple[str, str]:
    """Run vm.exe with one synthetic CLI arg ('test'). Classify the outcome."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False)
    f.write(code); f.close()
    try:
        r = subprocess.run([SIGIL, f.name, "test"],
                          capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return "ok", ""
        err = (r.stderr or "").strip()
        first = err.splitlines()[0] if err else ""
        if "Undefined variable" in err or "Unknown function" in err:
            return "undefined", first[:200]
        if "Type mismatch" in err or "expected" in err.lower():
            return "type_error", first[:200]
        if "out of bounds" in err or "index" in err.lower():
            return "index_error", first[:200]
        if "panic" in err.lower():
            return "panic", first[:200]
        if "Parse error" in err or "Lex" in err:
            return "parse_error", first[:200]
        return "other_error", first[:200]
    except subprocess.TimeoutExpired:
        return "timeout", ""
    except Exception as e:
        return "exception", str(e)[:200]
    finally:
        os.unlink(f.name)


def main():
    with CORPUS_IN.open() as fin:
        entries = [json.loads(l) for l in fin if l.strip()]

    print(f"Runtime-checking {len(entries)} entries (~{len(entries) * 0.5:.0f}s estimated)...")

    classes = Counter()
    drop_log = []
    keep = []
    undefined_funcs = Counter()
    for i, entry in enumerate(entries):
        msgs = entry["messages"]
        asst = next((m for m in msgs if m["role"] == "assistant"), None)
        if not asst:
            classes["empty"] += 1
            continue
        cls, msg = classify_run(asst["content"])
        classes[cls] += 1

        if cls == "undefined":
            # Extract the actual identifier name from the error message
            m = re.search(r'(?:Undefined variable|Unknown function):\s*(\w+)', msg)
            if m:
                undefined_funcs[m.group(1)] += 1
            user = next((mm["content"][:60] for mm in msgs if mm["role"] == "user"), "")
            drop_log.append(f"DROP entry {i} (undefined): {msg}\n  user: {user!r}\n  code: {asst['content'][:150]}")
            continue  # drop

        keep.append(entry)

        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(entries)} processed; classes={dict(classes)}")

    print()
    print(f"=== Final classification (n={len(entries)}) ===")
    for k in sorted(classes, key=lambda x: -classes[x]):
        print(f"  {k:14s} {classes[k]:>5}  ({100*classes[k]/len(entries):.1f}%)")
    print()
    if undefined_funcs:
        print("Most common undefined references (in dropped entries):")
        for name, cnt in undefined_funcs.most_common(15):
            print(f"  {cnt:>4} | {name}")

    CORPUS_OUT.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in keep) + "\n")
    LOG_OUT.write_text("\n".join(drop_log))
    print()
    print(f"Final clean corpus: {CORPUS_OUT} ({len(keep)} entries kept; {len(entries) - len(keep)} dropped)")
    print(f"Drop log: {LOG_OUT}")


if __name__ == "__main__":
    main()
