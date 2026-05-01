#!/usr/bin/env python3
"""Patch rejected task specs with Sonnet.

When the ollama meta-generator runs, specs whose Python reference doesn't
match the stated expected output are saved to `rejected_tasks.jsonl` with
a `_reject_reason` field. This script reads those, asks Sonnet to fix
either the python code or the expected output (whichever is wrong), and
re-validates. Successfully patched specs are appended to
`generated_tasks.jsonl` and removed from the rejected file.

Uses claude --print --resume for session continuity so the Sigil context
isn't re-sent on every call.

Usage:
    python patch_rejected.py
    python patch_rejected.py --workers 2 --model claude-sonnet-4-6
    python patch_rejected.py --limit 50              # patch first 50 only
    python patch_rejected.py --dry-run               # don't write anything
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REJECTED_PATH = Path(__file__).resolve().parent / "rejected_tasks.jsonl"
OUT_PATH = Path(__file__).resolve().parent / "generated_tasks.jsonl"


PREAMBLE = """You are correcting task specifications for a Sigil training corpus.

Each spec describes a CLI program by:
  - id:       unique short string
  - desc:     one-line description of what the program does
  - args:     list of CLI arguments to pass
  - expected: the EXACT stdout the program should produce
  - python:   reference Python implementation

A spec is REJECTED when running the python with the args produces output
that does NOT match expected. Your job: fix whichever side is wrong.

Rules:
  - If python is correct but expected was misstated, update expected.
  - If expected is the intended behavior, fix python to match.
  - Keep desc accurate and concise.
  - args must be a list of strings.
  - Output ONLY a JSON object: {"id": ..., "desc": ..., "args": ...,
    "expected": ..., "python": ...}. No prose, no fences.

Acknowledge with "ready" — then I'll send rejects one at a time.
"""

DELTA = """Reject reason: {reason}

Original spec:
{spec_json}

Return the corrected spec as a single JSON object."""


_session = threading.local()
_write_lock = threading.Lock()


def _claude(prompt: str, model: str, sid: str | None,
            timeout: int = 180) -> tuple[str, str]:
    cmd = ["claude", "--print", "--output-format", "json", "--model", model]
    if sid:
        cmd += ["--resume", sid]
    cmd += ["-p", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd="/tmp", errors="replace")
    except Exception:
        return "", sid or ""
    if not r.stdout.strip():
        return "", sid or ""
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout, sid or ""
    return data.get("result") or "", data.get("session_id") or sid or ""


def _strip_to_json_obj(s: str) -> dict | None:
    s = s.strip()
    for fence in ["```json", "```"]:
        if s.startswith(fence):
            s = s[len(fence):].lstrip()
    if s.endswith("```"):
        s = s[:-3].rstrip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(s[a:b+1])
    except json.JSONDecodeError:
        return None


def _run_python(code: str, args: list) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([sys.executable, f.name] + [str(a) for a in args],
                               capture_output=True, text=True, timeout=10,
                               errors="replace")
            return r.returncode == 0, r.stdout
        finally:
            os.unlink(f.name)


def validate(spec: dict) -> tuple[bool, str]:
    for k in ("id", "desc", "args", "expected", "python"):
        if k not in spec:
            return False, f"missing key {k}"
    if not isinstance(spec["args"], list):
        return False, "args must be list"
    ok, out = _run_python(spec["python"], [str(a) for a in spec["args"]])
    if not ok:
        return False, "python failed"
    if out != spec["expected"]:
        return False, f"python_out={out!r} != expected={spec['expected']!r}"
    return True, ""


def patch_one(rec: dict, model: str) -> dict | None:
    """Returns the fixed spec, or None if patching failed."""
    reason = rec.pop("_reject_reason", "unknown")
    delta = DELTA.format(reason=reason, spec_json=json.dumps(rec, indent=2))
    sid = getattr(_session, "id", None)
    prompt = delta if sid else (PREAMBLE + delta)
    text, new_sid = _claude(prompt, model, sid)
    if new_sid:
        _session.id = new_sid
    if not text:
        return None
    fixed = _strip_to_json_obj(text)
    if not fixed:
        return None
    # Preserve the original id (so we don't drift in the corpus)
    fixed["id"] = rec.get("id") or fixed.get("id") or f"gen_{uuid.uuid4().hex[:6]}"
    ok, _ = validate(fixed)
    return fixed if ok else None


def load_rejected() -> list[dict]:
    if not REJECTED_PATH.exists():
        return []
    out = []
    for line in REJECTED_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def append_fixed(spec: dict) -> None:
    with _write_lock:
        with OUT_PATH.open("a") as f:
            f.write(json.dumps(spec) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--model", type=str, default="claude-sonnet-4-6")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rejected = load_rejected()
    if args.limit:
        rejected = rejected[:args.limit]
    if not rejected:
        print("No rejected specs to patch.")
        return

    print(f"Patching {len(rejected)} rejected specs with {args.model}, "
          f"{args.workers} workers")
    start = time.time()

    fixed_count = 0
    failed_count = 0
    fixed_records: list[dict] = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(patch_one, dict(rec), args.model): rec
                for rec in rejected}
        for fut in as_completed(futs):
            rec = futs[fut]
            try:
                fixed = fut.result()
            except Exception as e:
                fixed = None
                print(f"  ✗ {rec.get('id', '?')}: exception {e}")
            if fixed:
                fixed_count += 1
                fixed_records.append(fixed)
                if not args.dry_run:
                    append_fixed(fixed)
                print(f"  ✓ {fixed['id']}")
            else:
                failed_count += 1
                print(f"  ✗ {rec.get('id', '?')}")

    if not args.dry_run and fixed_records:
        # Rewrite rejected file removing the patched ones
        fixed_ids = {f["id"] for f in fixed_records}
        remaining = [r for r in rejected if r.get("id") not in fixed_ids]
        REJECTED_PATH.write_text(
            "".join(json.dumps(r) + "\n" for r in remaining))

    elapsed = time.time() - start
    print(f"\n=== DONE in {elapsed:.1f}s ===")
    print(f"  fixed:  {fixed_count}")
    print(f"  failed: {failed_count}")
    if not args.dry_run:
        print(f"  appended to: {OUT_PATH}")
        print(f"  remaining rejects in: {REJECTED_PATH}")


if __name__ == "__main__":
    main()
