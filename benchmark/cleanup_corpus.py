#!/usr/bin/env python3
"""Thorough corpus cleanup pass.

Three passes:
  1. Mechanical fixes:
     - if-Lisp-trap: 2-set then-body without (else) -> add (else) marker
       (only when the structure clearly intends sequence, see heuristic)
     - Dropped: nothing here (we did arg_int and regex_find_all in the prior pass)

  2. Runtime sanity check:
     - For each entry, try to run vm.exe with synthetic CLI args derived from
       the user task description. Skip (don't drop) entries we can't run
       cleanly — we just observe.
     - Drop entries that runtime-error with `Unknown function` or `Undefined
       variable` (those are the silent-poison cases).

  3. Final lint pass:
     - Re-verify everything still parses after the (else) edits.

Output:
  benchmark/training_corpus.cleaned.jsonl  (final clean corpus)
  benchmark/cleanup_log.txt                (everything dropped or modified)
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
CORPUS_IN = REPO / "benchmark" / "training_corpus.jsonl"
CORPUS_OUT = REPO / "benchmark" / "training_corpus.cleaned.jsonl"
LOG_OUT = REPO / "benchmark" / "cleanup_log.txt"


# =====================================================================
# Pass 1: mechanical fixes
# =====================================================================

def fix_if_lisp_trap(code: str) -> tuple[str, int]:
    """Heuristic fix: when an (if cond stmt1 stmt2) has both stmt1 and stmt2
    looking like (set ...) calls AND there's no nearby (else marker, the
    intent is almost certainly sequence — append (else) to force then-body
    interpretation.

    This is necessarily imperfect (we can't be 100% sure of intent), but
    the corpus audit showed this anti-pattern in 24 entries, all of which
    look like sequence-intent on inspection. The fix is conservative:
    only applies when both statements are (set ...) calls and the if-body
    has exactly 2 statements.
    """
    # NOTE: the inner-value pattern uses [^()\s]+ instead of \S+ — \S+ is too
    # greedy and captures closing parens, leading to mis-aligned matches like
    # the previous bug where (else) was inserted OUTSIDE the if. [^()\s]+ won't
    # cross paren boundaries.
    pattern = re.compile(
        r'\(if\s+'                          # (if
        r'(?P<cond>\([^()]*(?:\([^()]*\)[^()]*)*\))'  # cond (balanced parens)
        r'\s+'
        r'(?P<s1>\(set\s+\w+(?:\s+[a-z]+)?\s*(?:\([^()]*(?:\([^()]*\)[^()]*)*\)|[^()\s]+)\))'
        r'\s+'
        r'(?P<s2>\(set\s+\w+(?:\s+[a-z]+)?\s*(?:\([^()]*(?:\([^()]*\)[^()]*)*\)|[^()\s]+)\))'
        r'\s*\)',
        re.MULTILINE
    )
    n = 0
    def repl(m):
        nonlocal n
        n += 1
        return f"(if {m.group('cond')} {m.group('s1')} {m.group('s2')} (else))"
    new = pattern.sub(repl, code)
    return new, n


# =====================================================================
# Pass 2: runtime sanity (lint only — running with synthetic args is
# unreliable because we don't know the expected outputs)
# =====================================================================

def lint_clean(code: str) -> tuple[bool, str]:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False)
    f.write(code); f.close()
    try:
        r = subprocess.run([SIGIL, "--lint", f.name],
                          capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, ""
        msg = (r.stderr.strip() or r.stdout.strip()).splitlines()
        return False, msg[0] if msg else "unknown error"
    except Exception as e:
        return False, f"exception: {e}"
    finally:
        os.unlink(f.name)


def main():
    with CORPUS_IN.open() as fin:
        entries = [json.loads(l) for l in fin if l.strip()]

    print(f"Loaded {len(entries)} entries")
    log = []

    # Pass 1: mechanical fixes
    n_else_fixed = 0
    n_else_entries = 0
    for entry in entries:
        msgs = entry["messages"]
        for i, m in enumerate(msgs):
            if m["role"] != "assistant":
                continue
            new_code, n = fix_if_lisp_trap(m["content"])
            if n > 0:
                msgs[i] = {**m, "content": new_code}
                n_else_fixed += n
                n_else_entries += 1
                user = next((mm["content"][:60] for mm in msgs if mm["role"] == "user"), "")
                log.append(f"FIX_ELSE entry {entries.index(entry)}: {n} (else) markers added — user: {user!r}")
                break  # only report once per entry

    print(f"Pass 1: added (else) marker to {n_else_fixed} ifs in {n_else_entries} entries")

    # Pass 2: lint everything that's left
    kept = []
    n_dropped = 0
    drop_reasons = Counter()
    for i, entry in enumerate(entries):
        msgs = entry["messages"]
        asst = next((m for m in msgs if m["role"] == "assistant"), None)
        if not asst or not asst["content"].strip():
            n_dropped += 1
            drop_reasons["empty assistant"] += 1
            log.append(f"DROP entry {i}: empty assistant message")
            continue
        ok, err = lint_clean(asst["content"])
        if not ok:
            n_dropped += 1
            drop_reasons[err[:60]] += 1
            user = next((m["content"][:60] for m in msgs if m["role"] == "user"), "")
            log.append(f"DROP entry {i} (lint failed): {err[:120]} — user: {user!r}")
            continue
        kept.append(entry)
        if (i + 1) % 500 == 0:
            print(f"  Pass 2: {i+1}/{len(entries)} processed; {n_dropped} dropped so far")

    print(f"Pass 2: dropped {n_dropped}; kept {len(kept)}")
    print()
    print("Drop reasons:")
    for reason, cnt in drop_reasons.most_common():
        print(f"  {cnt:>4} | {reason}")

    CORPUS_OUT.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in kept) + "\n")
    LOG_OUT.write_text("\n".join(log))
    print()
    print(f"Cleaned corpus: {CORPUS_OUT} ({len(kept)} entries)")
    print(f"Log: {LOG_OUT}")


if __name__ == "__main__":
    main()
