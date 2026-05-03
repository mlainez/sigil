#!/usr/bin/env python3
"""Audit the training corpus for pristineness before the v7 retrain.

Three checks per entry:
  1. parse-clean (vm.exe --lint passes)
  2. argv-misuse heuristic: program calls (argv) AND the user description
     mentions multi-line input → flag for review
  3. deprecated builtin names: scan for known-bad reaches (parse_float
     when not aliased, cast_*, argv_str, etc.)

Usage:
  python3 audit_corpus.py             # report only
  python3 audit_corpus.py --quarantine # move bad entries to corpus_quarantine.jsonl

Output: a per-entry report + summary counts. Exit 0 if all pristine, 1 if
any failures. Bad entries can be quarantined for manual review.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO / "interpreter" / "_build" / "default" / "vm.exe")
CORPUS = REPO / "benchmark" / "training_corpus.jsonl"
QUARANTINE = REPO / "benchmark" / "corpus_quarantine.jsonl"


def lint_sigil(code: str) -> tuple[bool, str]:
    """Run vm.exe --lint on code; return (ok, error_message)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run(
                [SIGIL_BIN, "--lint", f.name],
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "SIGIL_DIAGNOSE": "0"},
            )
            if r.returncode == 0:
                return True, ""
            err = (r.stderr.strip() or r.stdout.strip()).splitlines()
            return False, err[0] if err else "unknown lint failure"
        except subprocess.TimeoutExpired:
            return False, "lint timeout"
        finally:
            os.unlink(f.name)


# Heuristics for argv misuse detection
_ARGV_CALL = re.compile(r"\(argv\)\b")
_MULTILINE_HINTS = re.compile(
    r"\b(multi-?line|each line|per line|lines? of arg0|"
    r"newline-?separated|log lines?|\\n)\b",
    re.IGNORECASE,
)
_DOLLAR_ZERO = re.compile(r"\$0\b")
_SPLIT_DOLLAR_ZERO_NL = re.compile(r'\(split\s+\$0\s+"\\n"\)')


def argv_misuse_score(user_msg: str, asst_code: str) -> tuple[bool, str]:
    """Heuristic: did the model use (argv) when input is multi-line in $0?

    Flag if ALL of:
      - user description suggests multi-line input
      - assistant code calls (argv)
      - assistant code does NOT also use (split $0 "\\n")

    Returns (is_suspicious, reason). False positives are possible (some
    tasks legitimately use argv with multi-line CLI args), so this is a
    flag-for-review, not auto-quarantine.
    """
    has_argv = bool(_ARGV_CALL.search(asst_code))
    suggests_multiline = bool(_MULTILINE_HINTS.search(user_msg))
    has_split_dollar = bool(_SPLIT_DOLLAR_ZERO_NL.search(asst_code))
    if has_argv and suggests_multiline and not has_split_dollar:
        return True, "uses (argv) but description suggests multi-line $0 input and code lacks (split $0 \"\\n\")"
    return False, ""


# Builtin names that DO NOT exist in the current interpreter — flagging
# these means the entry will hit a runtime error on first call. Verified
# against interpreter.ml on 2026-05-03. cast_int_float / cast_float_int /
# string_length DO exist; the original _BAD_NAMES list was over-eager.
_BAD_NAMES = [
    ("parse_float",       "use (float s) — parse_float is not a builtin"),
    ("argv_str",          "no such builtin — use $0/$1 or (arg_str i)"),
    ("to_int",            "use (parse_int s) or (int v)"),
    ("first_index_of",    "use (index_of arr x)"),
    ("regex_replace_all", "use (regex_replace pat text repl) — already replaces all"),
]


def deprecated_name_scan(code: str) -> list[str]:
    """Scan for known-bad builtin names (whole-word matches)."""
    flags = []
    for name, msg in _BAD_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", code):
            flags.append(f"{name}: {msg}")
    return flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarantine", action="store_true",
                    help="Move flagged entries to corpus_quarantine.jsonl")
    ap.add_argument("--corpus", default=str(CORPUS))
    ap.add_argument("--quiet", action="store_true",
                    help="Only print summary + flagged entries")
    args = ap.parse_args()

    corpus_path = Path(args.corpus)
    entries = [json.loads(line) for line in corpus_path.read_text().splitlines() if line.strip()]
    print(f"Auditing {len(entries)} entries from {corpus_path}\n")

    parse_failures = []
    argv_misuses = []
    deprecated_uses = []

    for idx, entry in enumerate(entries):
        msgs = entry.get("messages", [])
        user_msg = ""
        asst_code = ""
        for m in msgs:
            if m.get("role") == "user":
                user_msg = m.get("content", "")
            elif m.get("role") == "assistant":
                asst_code = m.get("content", "")
        if not asst_code:
            parse_failures.append((idx, "missing assistant content"))
            continue

        # 1. lint
        ok, err = lint_sigil(asst_code)
        if not ok:
            parse_failures.append((idx, err[:120]))
            if not args.quiet:
                print(f"  [{idx:5d}] LINT  {err[:80]}")
                print(f"          desc: {user_msg[:80]}")

        # 2. argv-misuse heuristic
        misuse, reason = argv_misuse_score(user_msg, asst_code)
        if misuse:
            argv_misuses.append((idx, reason))
            if not args.quiet:
                print(f"  [{idx:5d}] ARGV  {reason}")
                print(f"          desc: {user_msg[:80]}")

        # 3. deprecated names
        flags = deprecated_name_scan(asst_code)
        if flags:
            deprecated_uses.append((idx, flags))
            if not args.quiet:
                print(f"  [{idx:5d}] NAME  {'; '.join(flags)}")
                print(f"          desc: {user_msg[:80]}")

        if (idx + 1) % 200 == 0:
            print(f"  ... {idx+1}/{len(entries)} entries audited")

    print("\n=== AUDIT SUMMARY ===")
    print(f"  Total entries:      {len(entries)}")
    print(f"  Parse failures:     {len(parse_failures)}")
    print(f"  argv-misuse flags:  {len(argv_misuses)}")
    print(f"  Deprecated-name flags: {len(deprecated_uses)}")
    bad_set = set()
    for i, _ in parse_failures: bad_set.add(i)
    for i, _ in argv_misuses: bad_set.add(i)
    for i, _ in deprecated_uses: bad_set.add(i)
    print(f"  Total flagged (any reason): {len(bad_set)} ({100*len(bad_set)/max(len(entries),1):.1f}%)")

    if args.quarantine and bad_set:
        kept = [e for i, e in enumerate(entries) if i not in bad_set]
        flagged = [e for i, e in enumerate(entries) if i in bad_set]
        QUARANTINE.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in flagged) + "\n")
        corpus_path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in kept) + "\n")
        print(f"\n  Quarantined {len(flagged)} entries to {QUARANTINE}")
        print(f"  Kept {len(kept)} entries in {corpus_path}")

    return 0 if not bad_set else 1


if __name__ == "__main__":
    sys.exit(main())
