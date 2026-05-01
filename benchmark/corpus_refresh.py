#!/usr/bin/env python3
"""Corpus refresh: bring training_corpus.jsonl in line with the current
language surface (canonical names, new prelude, fixed if-Lisp-form traps).

Phase A: mechanical safe rewrites.
- (arg_int <int_literal>) -> (argv_int <int_literal>)
- (regex_find_all -> (find_all
- (regex_find_all)/(regex_find_all <args>) renames where unambiguous

Phase B: generation of new examples is in a separate script (refresh_seeds.py).

This script is idempotent: running twice produces no further changes.

Outputs:
- training_corpus.refreshed.jsonl  (the new corpus)
- corpus_refresh_log.txt           (per-entry change log)
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORPUS_IN = REPO / "benchmark" / "training_corpus.jsonl"
CORPUS_OUT = REPO / "benchmark" / "training_corpus.refreshed.jsonl"
LOG_OUT = REPO / "benchmark" / "corpus_refresh_log.txt"


REWRITES = [
    # 1. (arg_int <decimal>) -> (argv_int <decimal>) — safe rename, only when
    #    the argument is a literal int. Don't touch (arg_int some_var) because
    #    that may be an intentional use of the alias.
    (re.compile(r'\(arg_int\s+(\d+)\)'), r'(argv_int \1)'),

    # 2. (regex_find_all <pat> <text>) -> (find_all <pat> <text>) — find_all
    #    is the prelude alias, simpler and matches SLIM_HEADER guidance.
    (re.compile(r'\(regex_find_all\s+'), '(find_all '),
]


def refresh_entry(entry: dict, rewrites) -> tuple[dict, list[str]]:
    """Apply mechanical rewrites to the assistant message of one entry.
    Returns (new_entry, list_of_change_descriptions)."""
    msgs = entry["messages"]
    asst_idx = next((i for i, m in enumerate(msgs) if m["role"] == "assistant"), None)
    if asst_idx is None:
        return entry, []
    code = msgs[asst_idx]["content"]
    changes = []
    for pat, repl in rewrites:
        new_code, n = pat.subn(repl, code)
        if n:
            changes.append(f"  {pat.pattern!r} -> {repl!r}  ({n} occurrences)")
            code = new_code
    if changes:
        msgs = list(msgs)
        msgs[asst_idx] = {**msgs[asst_idx], "content": code}
        entry = {**entry, "messages": msgs}
    return entry, changes


def main():
    n_total = 0
    n_changed = 0
    log_lines = []
    out_lines = []

    with CORPUS_IN.open() as fin:
        for line in fin:
            line = line.rstrip("\n")
            if not line:
                continue
            n_total += 1
            entry = json.loads(line)
            new_entry, changes = refresh_entry(entry, REWRITES)
            if changes:
                n_changed += 1
                user_q = ""
                for m in entry["messages"]:
                    if m["role"] == "user":
                        user_q = m["content"][:80]
                        break
                log_lines.append(f"Entry {n_total} ({user_q!r}):")
                log_lines.extend(changes)
                log_lines.append("")
            out_lines.append(json.dumps(new_entry, ensure_ascii=False))

    CORPUS_OUT.write_text("\n".join(out_lines) + "\n")
    LOG_OUT.write_text("\n".join(log_lines))

    print(f"Total entries: {n_total}")
    print(f"Changed: {n_changed} ({100 * n_changed / n_total:.1f}%)")
    print(f"Output: {CORPUS_OUT}")
    print(f"Log:    {LOG_OUT}")


if __name__ == "__main__":
    main()
