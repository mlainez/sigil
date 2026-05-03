#!/usr/bin/env python3
"""Extend the Sigil training corpus by generating new examples via Opus.

For each task in task_bank.TASKS:
  1. Verify Python reference produces expected output.
  2. Ask Claude Opus 4.7 to write Sigil for the same task.
  3. Run Sigil with the task's args, compare stdout to expected.
  4. Retry up to N times on failure.
  5. Save successful programs to examples/corpus_extensions/{id}.sigil.

Parallel workers via ThreadPoolExecutor. Each worker invokes `claude --print`.
Re-running is safe: existing files are skipped unless --force.

Usage:
    python corpus_extender.py                    # all tasks, 5 workers
    python corpus_extender.py --workers 3
    python corpus_extender.py --limit 20         # pilot
    python corpus_extender.py --ids str_upper,num_add
    python corpus_extender.py --force            # re-generate even if exists
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_bank import TASKS as HAND_TASKS
import rag

# Merge hand-crafted + Opus-generated tasks
def _load_generated():
    p = Path(__file__).resolve().parent / "generated_tasks.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out

TASKS = HAND_TASKS + _load_generated()

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")
GRAMMAR = (REPO_ROOT / ".sigil.grammar").read_text()
OUT_DIR = REPO_ROOT / "examples" / "corpus_extensions"


SLIM_HEADER = """Sigil is a Lisp-shaped scripting language. Here are 6 worked examples:

# Uppercase the first arg
(println (upper $0))

# Sum all space-separated ints in arg
(println (sum (parse_ints $0)))

# Word count of arg
(println (len (split $0 " ")))

# Sum of squares of evens in arg (functional pipeline)
(println (sum (map_arr (filter (parse_ints $0) (\\x (eq (mod x 2) 0))) (\\x (mul x x)))))

# CSV row filter where city == arg1; uses for-each
(set rows (split $0 "\\n"))
(for-each row rows
  (set fields (split row ","))
  (if (eq (last fields) $1)
    (println row)))

# Caesar cipher shift on alpha
(fn shift c int n int -> int
  (cond
    ((and (ge c 65) (le c 90)) (ret (add 65 (mod (add (sub c 65) n) 26))))
    ((and (ge c 97) (le c 122)) (ret (add 97 (mod (add (sub c 97) n) 26))))
    (true (ret c))))
(println (join (map_arr (chars $1) (\\c (char_from_code (shift (string_get c 0) #0)))) ""))

Key builtins: len, str, fmt, split, join, sort, push, filter, map_arr, reduce,
first, last, rev, swapcase, title, uniq, counter, sort_by, entries, enumerate,
scan, slice, merge, range, sum, parse_int, parse_ints, chars, char_from_code.
NOTE: (slice arr start end) is END-EXCLUSIVE (Python-style). For a length-based
slice use (array_slice arr start length). sort and sort_by both mutate AND
return the input array — `(sort xs)` and `(set ys (sort xs))` both work.
string_replace, string_find, string_contains, string_starts_with, mod, add, sub,
mul, div, eq, ne, lt, gt, le, ge, neg, abs, in, has, get_or.
Char access: (string_at s i) returns a 1-char STRING at index i (use this for
char comparisons like (eq (string_at s 0) "a")). (string_get s i) returns the
INT char code (use for (is_digit ...) etc which accept both forms).
Regex: (find_all pattern text) → array of matches; (regex_match pat text) →
bool; (regex_find pat text) → first-match string; (regex_replace pat text repl)
→ replaced string.
String-pair builtins (added 2026-04-30): (common_prefix a b) → longest common
prefix string. (common_suffix a b) → longest common suffix. (is_subseq haystack
needle) → bool, true if needle is a subsequence of haystack. (is_rotation a b)
→ bool, b is a cyclic rotation of a. (edit_distance a b) → int Levenshtein.
(common_chars a b) → multiset intersection as string in order of a. sub and mul
are variadic-fold like add: (sub a b c) means a-b-c, (mul a b c) means a*b*c.
Text-shape prelude (auto-loaded): (tokens s) → array of whitespace-separated
non-empty pieces (use this for `wc -w`-style splitting instead of
(split s " ")). (squeeze s) → string with runs of spaces/tabs collapsed to
a single space (preserves leading/trailing). (split_blocks s) → array of
paragraphs split on blank lines. (find_all pattern text) → array of all
regex matches in order. (line_count s) → int line count, ignoring a final
trailing newline. For wc -l style "count of newline characters" use
(count s "\\n").
JSON: json_parse, json_get, json_set, json_has, json_delete accept an
array of keys for deep walks: (json_get j ["users" 0 "name"]). String segments
look up map keys; int segments index arrays. For path-from-CLI-string use
(json_get j (split $1 ".")) — string-int segments auto-promote on arrays.
DO NOT loop (set j (json_get j k)) — `set` is statically typed and rebinding
to a different type fails.
CLI args: $0/#0 are LITERAL only. For variable index use (arg_str i)/(argv_int i),
and (argv) for the array, (argv_count) for length. (argv_int i) fetches CLI
argv[i] parsed as int — to parse a STRING into int use (parse_int s). They are
DIFFERENT operations.
INPUT SHAPE: the harness passes the WHOLE input (all lines, the entire CSV,
the full log) as a single string in $0. (argv) is "smart": when there's
exactly 1 CLI arg AND it contains newlines, (argv) returns the lines —
equivalent to (split $0 "\\n"). So both shapes work for line iteration:
  (for-each line (argv) ...)         ; auto-splits
  (for-each line (split $0 "\\n") ...) ; explicit
For the literal CLI argv vector with no auto-splitting, use (argv_raw).
TABULAR DATA RULE: if the task names columns ("CSV with columns date,category,amount"),
SKIP the header row and index by POSITION matching the column you want, not
always 0. For "sum by category" with header "date,category,amount", the
category field is (array_get row 1) — NOT (first row). Read the header
description carefully before indexing.
REGEX find_all RULE: (find_all pat text) returns the FULL match for each hit
— ALWAYS group 0, regardless of capturing groups in the pattern. To extract
just a sub-pattern, write a regex that matches ONLY that sub-pattern, OR
post-process the full match with split. Example: to extract names from
"def NAME(" lines, do (find_all "def \\w+" src) then (last (split m " "))
per hit, or per-line: (if (regex_match "^def \\w" line) (println
(array_get (split line "(") 0))) and post-process.
fn signatures REQUIRE per-param types and `-> rettype` (e.g. (fn add a int b int -> int ...)).
reduce: (reduce arr fn init) OR (reduce fn init arr) — never (arr init fn).
Aliases: map=map_arr, head=first, tail=rest, contains=in, size/length=len,
upcase=upper, downcase=lower, let=set, def=fn. + - * / % < > <= >= = work.
HOFs map_arr/filter accept either (fn arr) or (arr fn).
Empty: [] {{}}. Lambdas (\\x ...) or (\\(x y) ...). (println x) auto-newlines.
Sigil has NO comments — no ; // # — strip them entirely.
"""


PROMPT = """{grammar}

Write a Sigil program that does exactly this:

TASK: {desc}

Example: when called with CLI args {args}, output must be EXACTLY:
{expected!r}

Rules — follow STRICTLY for correct and minimal code:
1. Prefer top-level script mode (no (module ...) wrapper) unless you need multiple fns.
2. CLI args: $0 is first user arg as string, #0 is first as int. $1, #1 for second, etc.
   For DYNAMIC index (variable i): use (arg_str i) or (arg_int i). $i with i a variable is INVALID.
   Use (argv) for the array, (argv_count) for length.
3. Type rules (CRITICAL):
   - (set ...) and (for-each ...) — type annotation OPTIONAL.
   - (fn ...) — every parameter REQUIRES a type, plus `-> RETTYPE`. Example:
     (fn add a int b int -> int (ret (+ a b)))
   - `set` is statically typed: once a variable is bound to a type, it stays that type.
     Do NOT reassign a map-typed var to an int — use a fresh variable name.
4. PREFER functional pipelines: (sum (map_arr arr (\\x ...))) over (for-each + accumulator).
5. Short aliases: len, str, fmt, split, join, sort, push, filter, map_arr, reduce,
   first, last, rev, swapcase, title, uniq, counter, sort_by, entries, enumerate,
   scan, map_kv, map_pairs, diff, inter, union, slice, merge, range.
6. Accepted alt-names: map=map_arr, head/car=first, tail/cdr=rest, contains/has=in,
   size/length=len, upcase=upper, downcase=lower, let=set, def=fn. Arithmetic
   operators + - * / % < > <= >= = work as builtins too.
7. HOF arg orders:
   - map_arr/filter: either (fn arr) or (arr fn) accepted.
   - reduce: (reduce arr fn init) OR (reduce fn init arr). NEVER (arr init fn).
8. Empty collections: [] and {{}}. NEVER (array_new) or (map_new).
9. Lambdas: (\\x expr) for 1 arg, (\\(x y) expr) for multi.
10. (println x) auto-adds newline; don't add \\n yourself.
11. Comparisons are prefix: (eq a b), (lt a b), (gt a b), (ge a b), (le a b).
12. JSON deep traversal: json_get/json_set/json_has/json_delete accept an
    ARRAY of keys for deep walks: (json_get j ["users" 0 "name"]). String segments
    look up maps; int segments index arrays. For runtime paths from CLI strings:
    (json_get j (split $1 ".")) — string segments that look numeric auto-promote
    when current node is an array. (json_has j ["a" "b"]) is safe (returns false on
    any missing segment instead of raising). NEVER loop `(set j (json_get j k))` —
    the rebind fails because j was statically typed at first json_parse.

Output ONLY the raw Sigil code. No markdown fences. No prose. No (module) unless needed."""


def run_python(code: str, args: list) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([sys.executable, f.name] + args,
                             capture_output=True, text=True, timeout=10,
                             errors="replace")
            return r.returncode == 0, r.stdout
        except subprocess.TimeoutExpired:
            return False, ""
        finally:
            os.unlink(f.name)


def run_sigil(code: str, args: list, diagnose: bool = True) -> tuple[bool, str, str]:
    """Run a Sigil program. Diagnostics (argv-misuse, no-output-produced) are
    ON by default — they help validator_hint rewrite retry prompts when
    a program "succeeds" with empty/wrong output. Pass diagnose=False to
    silence (rare; used when capturing stderr for non-diagnostic purposes)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            env = os.environ.copy()
            if not diagnose:
                env["SIGIL_DIAGNOSE"] = "0"
            r = subprocess.run([SIGIL_BIN, f.name] + args,
                             capture_output=True, text=True, timeout=10,
                             errors="replace", env=env)
            return r.returncode == 0, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return False, "", "timed out after 10s"
        finally:
            os.unlink(f.name)


def strip_fences(code: str) -> str:
    s = code.strip()
    for fence in ["```sigil", "```lisp", "```scheme", "```clojure", "```"]:
        if s.startswith(fence):
            s = s[len(fence):].lstrip()
            break
    if s.endswith("```"):
        s = s[:-3].rstrip()
    # Strip BARE language-name first lines. Models sometimes emit a chat-style
    # "python\n<actual code>" preamble even without the markdown fences,
    # especially under multi-step composition pressure (NH2 / Phase 27 finding:
    # 19/25 NH5 30-task failures had a stray 'python' header at the top of
    # otherwise-Sigil code that strip_fences was leaving in place).
    first_line, _, rest = s.partition("\n")
    if first_line.strip() in {"python", "lisp", "scheme", "clojure", "sigil",
                              "javascript", "typescript", "rust", "go", "ruby"}:
        s = rest.lstrip()
    # Some local LLMs double-escape backslashes (\\x → \\\\x). Halve runs of
    # 2+ backslashes back to one (Sigil never uses literal \\ in source).
    if "\\\\" in s:
        s = s.replace("\\\\", "\\")
    return s


def gen_sigil_ollama(task: dict, model: str, url: str = "http://127.0.0.1:11434",
                     timeout: int = 180, slim: bool = False,
                     temperature: float = 0.0,
                     rag_block: str = "") -> str:
    """Call a local ollama instance. Defaults to FULL grammar — local inference
    is free per-token, so the bigger context is worth it for smaller models.
    `temperature` lets retries vary the output (temp=0 is deterministic).
    `rag_block` is an optional few-shot block prepended after the grammar
    header (see rag.format_examples)."""
    import urllib.request
    import urllib.error
    header = SLIM_HEADER if slim else GRAMMAR
    if rag_block:
        header = header + "\n" + rag_block
    prompt = PROMPT.format(grammar=header, desc=task["desc"],
                          args=task["args"], expected=task["expected"])
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 4096, "top_p": 0.9},
    }).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return strip_fences(data.get("response", ""))
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return ""


HINT_PREAMBLE = """You are a senior code reviewer for the Sigil language.
A small local model is writing Sigil programs and getting them wrong.
Your job: for each broken attempt I send you, write a SHORT hint (1-3
sentences MAX) that pinpoints exactly what's wrong, so the small model
can correct itself.

Rules:
- DO NOT write or rewrite code. The small model writes the code.
- Be specific: name the line, builtin, type mismatch, or argument order
  that's broken — whichever applies.
- If multiple bugs, focus on the FIRST one the small model needs to fix.
- Keep total hint under ~60 words.

Sigil quick reference (for your reasoning, not for output):
- (println x) auto-newlines. (print x) does not.
- Builtins: len, str, fmt, split, join, sort, push, filter, map_arr, reduce,
  first, last, rev, range, slice, sum, parse_ints, parse_int, chars,
  index_of, pop, second, sort_by (1-arg key fn or 2-arg comparator).
- (str a b c) concatenates (varargs). (+ "a" "b") concatenates strings.
  + is also polymorphic on arrays/maps.
- json_get/json_set accept array-of-keys: (json_get j ["users" 0 "name"]).
- $0/$1 LITERAL string args; #0/#1 literal int. Dynamic: (arg_str i)/(arg_int i).
- fn signatures need per-param types and `-> rettype`. Aliases: str=string.
- `set` is statically typed: don't rebind a var to a different type.
- HOFs accept either (fn arr) or (arr fn). reduce: (reduce arr fn init).

Acknowledge with just "ready" — then I'll send the first broken attempt.
"""


HINT_DELTA = """TASK: {desc}
CLI args: {args}
Expected stdout (exact): {expected!r}

Small model wrote:
```
{code}
```

When run, it produced:
  stdout: {got_stdout!r}
  stderr: {got_stderr!r}

In 1-3 sentences (no code), tell the small model what to fix."""


# Per-worker session id. Each ThreadPoolExecutor worker keeps its own
# claude --print session so the FIX_PREAMBLE is sent once per worker, then
# subsequent fix calls --resume into the warm session and only send the delta.
_session = threading.local()


def _claude_with_session(prompt: str, model: str, session_id: str | None,
                         timeout: int = 180) -> tuple[str, str]:
    """Run `claude --print` with --output-format json. Returns (text, session_id).
    If session_id is None, starts a new session; otherwise resumes it."""
    cmd = ["claude", "--print", "--output-format", "json", "--model", model]
    if session_id:
        cmd += ["--resume", session_id]
    cmd += ["-p", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd="/tmp", errors="replace")
    except Exception:
        return "", session_id or ""
    if not r.stdout.strip():
        return "", session_id or ""
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout, session_id or ""
    text = data.get("result") or data.get("text") or ""
    new_sid = data.get("session_id") or session_id or ""
    return text, new_sid


def gen_hint(task: dict, broken_code: str, got_stdout: str, got_stderr: str,
             model: str) -> str:
    """Ask Sonnet for a SHORT (1-3 sentence) hint about what's wrong with
    qwen's broken code. Sonnet does NOT write code — it coaches.

    First call per worker primes a session with the reviewer preamble;
    subsequent calls --resume into the warm session and only send the
    per-task delta — keeping per-call input small."""
    delta = HINT_DELTA.format(
        desc=task["desc"], args=task["args"], expected=task["expected"],
        code=broken_code, got_stdout=got_stdout, got_stderr=got_stderr)
    sid = getattr(_session, "id", None)
    prompt = delta if sid else (HINT_PREAMBLE + delta)
    text, new_sid = _claude_with_session(prompt, model, sid)
    if new_sid:
        _session.id = new_sid
    if not text:
        return ""
    hint = text.strip()
    if any(m in hint.lower() for m in RATE_LIMIT_MARKERS):
        return ""
    # Strip any accidental code blocks / fences the model included
    if "```" in hint:
        before = hint.split("```", 1)[0].strip()
        if before:
            hint = before
    return hint


OLLAMA_RETRY_PROMPT = """{grammar}

Write a Sigil program that does exactly this:

TASK: {desc}

When called with CLI args {args}, output must be EXACTLY:
{expected!r}

YOUR PREVIOUS ATTEMPT was wrong. Here it is:
```
{prev_code}
```

When that ran, it produced:
  stdout: {got_stdout!r}
  stderr: {got_stderr!r}

A reviewer looked at it and gave you this hint:
> {hint}

Apply the hint and try again. Output ONLY the corrected Sigil code.
No markdown fences, no prose."""


def gen_sigil_ollama_with_hint(task: dict, model: str, url: str,
                                prev_code: str, got_stdout: str, got_stderr: str,
                                hint: str, temperature: float = 0.3,
                                timeout: int = 180,
                                rag_block: str = "") -> str:
    """Ollama re-attempt with broken code + reviewer hint in the prompt.
    Slightly higher temp than the deterministic first try, so the retry
    actually explores a different solution path.
    `rag_block` is an optional few-shot block (see rag.format_examples)."""
    import urllib.request
    import urllib.error
    grammar = GRAMMAR + "\n" + rag_block if rag_block else GRAMMAR
    prompt = OLLAMA_RETRY_PROMPT.format(
        grammar=grammar, desc=task["desc"], args=task["args"],
        expected=task["expected"], prev_code=prev_code,
        got_stdout=got_stdout, got_stderr=got_stderr, hint=hint)
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 4096, "top_p": 0.9},
    }).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return strip_fences(data.get("response", ""))
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return ""


RATE_LIMIT_MARKERS = [
    "out of extra usage",
    "resets ",
    "rate limit",
    "usage limit",
]


def gen_sigil(task: dict, model: str = "claude-opus-4-7", slim: bool = False) -> str:
    header = SLIM_HEADER if slim else GRAMMAR
    prompt = PROMPT.format(grammar=header, desc=task["desc"],
                          args=task["args"], expected=task["expected"])
    try:
        r = subprocess.run(
            ["claude", "--print", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=180, cwd="/tmp",
        )
        out = strip_fences(r.stdout)
        # Detect Claude CLI rate-limit / error messages and bail — they're not
        # Sigil code, trying to parse them just wastes time.
        low = out.lower()
        if any(m in low for m in RATE_LIMIT_MARKERS):
            return ""
        return out
    except Exception:
        return ""


def process_task(task: dict, force: bool = False, attempts: int = 3,
                 primary: str = "claude-sonnet-4-6",
                 fallback: str | None = "claude-opus-4-7",
                 slim: bool = True,
                 ollama_url: str | None = None,
                 ollama_model: str | None = None,
                 coach_only: bool = False,
                 rag_index: dict | None = None,
                 rag_k: int = 5) -> dict:
    out_path = OUT_DIR / f"{task['id']}.sigil"
    if out_path.exists() and not force:
        return {"id": task["id"], "status": "skip-exists"}

    # Check Python reference produces expected output (catches bad specs)
    ok_py, out_py = run_python(task["python"], task["args"])
    if not ok_py or out_py != task["expected"]:
        return {"id": task["id"], "status": "bad-python-spec",
                "note": f"py_out={out_py!r} expected={task['expected']!r}"}

    last_err = ""; last_sigil = ""

    # Build a RAG few-shot block once for this task, reused across tier 1 + 1.5.
    rag_block = ""
    if rag_index is not None:
        try:
            hits = rag.query(task["desc"], k=rag_k, index=rag_index)
            rag_block = rag.format_examples(hits)
        except Exception:
            rag_block = ""

    # Tier 1: ollama (free, local) if configured. Multiple attempts with
    # increasing temperature so retries actually vary the output.
    last_ollama_code = ""; last_ollama_stdout = ""; last_ollama_stderr = ""
    if ollama_url and ollama_model:
        ollama_temps = [0.0, 0.4, 0.7][:max(1, attempts)]
        for attempt, temp in enumerate(ollama_temps):
            sigil = gen_sigil_ollama(task, ollama_model, ollama_url,
                                     temperature=temp, rag_block=rag_block)
            if not sigil:
                last_err = "ollama empty response"
                continue
            last_sigil = sigil
            ok_s, out_s, err = run_sigil(sigil, task["args"])
            if ok_s and out_s == task["expected"]:
                out_path.write_text(sigil.rstrip() + "\n")
                return {"id": task["id"], "status": "ok",
                        "attempts": attempt + 1,
                        "tokens": len(sigil), "via": ollama_model}
            # Save the most-promising broken output for the fix tier.
            # Prefer outputs that at least produced stdout over ones that crashed.
            if out_s or not last_ollama_code:
                last_ollama_code = sigil
                last_ollama_stdout = out_s
                last_ollama_stderr = err
            last_err = f"ollama: stdout={out_s[:60]!r} stderr={err[:80]!r}"

    # Tier 1.5: coaching loop — Sonnet writes SHORT hints, ollama writes the
    # fix. Final code stays in qwen's voice (better corpus variety) and we
    # spend Sonnet only on tiny coaching messages, not full programs.
    coach_iters = 2  # how many hint→retry cycles to attempt
    if last_ollama_code and primary and ollama_url and ollama_model:
        for c_iter in range(coach_iters):
            hint = gen_hint(task, last_ollama_code,
                            last_ollama_stdout, last_ollama_stderr,
                            model=primary)
            if not hint:
                last_err = "hint: empty"
                break
            sigil = gen_sigil_ollama_with_hint(
                task, ollama_model, ollama_url,
                prev_code=last_ollama_code,
                got_stdout=last_ollama_stdout,
                got_stderr=last_ollama_stderr,
                hint=hint,
                temperature=0.3 + 0.2 * c_iter,
                rag_block=rag_block)
            if not sigil:
                last_err = "ollama (hinted) empty"
                continue
            last_sigil = sigil
            ok_s, out_s, err = run_sigil(sigil, task["args"])
            if ok_s and out_s == task["expected"]:
                out_path.write_text(sigil.rstrip() + "\n")
                return {"id": task["id"], "status": "ok",
                        "attempts": len(ollama_temps) + c_iter + 1,
                        "tokens": len(sigil),
                        "via": f"{ollama_model} (coached)"}
            # Update broken-attempt context for the next coaching round
            last_ollama_code = sigil
            last_ollama_stdout = out_s
            last_ollama_stderr = err
            last_err = f"coached: stdout={out_s[:60]!r} stderr={err[:80]!r}"

    # Tier 2: primary cloud model with slim header (skip if disabled or coach_only)
    via = primary
    if primary and not coach_only:
      for attempt in range(attempts):
        sigil = gen_sigil(task, model=primary, slim=slim)
        if not sigil:
            last_err = "empty response"
            continue
        last_sigil = sigil
        ok_s, out_s, err = run_sigil(sigil, task["args"])
        if ok_s and out_s == task["expected"]:
            out_path.write_text(sigil.rstrip() + "\n")
            return {"id": task["id"], "status": "ok", "attempts": attempt + 1,
                    "tokens": len(sigil), "via": via}
        last_err = f"stdout={out_s[:60]!r} stderr={err[:80]!r}"

    # Tier 3: fallback cloud model with full grammar (max quality)
    if fallback and not coach_only:
        via = fallback + " (fallback)"
        sigil = gen_sigil(task, model=fallback, slim=False)
        if sigil:
            last_sigil = sigil
            ok_s, out_s, err = run_sigil(sigil, task["args"])
            if ok_s and out_s == task["expected"]:
                out_path.write_text(sigil.rstrip() + "\n")
                return {"id": task["id"], "status": "ok", "attempts": attempts + 1,
                        "tokens": len(sigil), "via": via}
            last_err = f"fallback: stdout={out_s[:60]!r} stderr={err[:80]!r}"

    return {"id": task["id"], "status": "failed", "attempts": attempts,
            "note": last_err, "last_sigil": last_sigil[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", type=str, default=None,
                    help="Comma-separated task ids")
    ap.add_argument("--force", action="store_true",
                    help="Regenerate even if output file exists")
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--primary", type=str, default="claude-sonnet-4-6",
                    help="Primary model (cheap)")
    ap.add_argument("--fallback", type=str, default="",
                    help="Opus-tier fallback after primary fails; '' (default) skips it. "
                         "Pass --fallback claude-opus-4-7 to enable.")
    ap.add_argument("--full-grammar", action="store_true",
                    help="Use full grammar (5K tok) instead of slim header (1.3K tok)")
    ap.add_argument("--ollama-url", type=str, default=None,
                    help="If set, try local ollama first (e.g. http://127.0.0.1:11434). "
                         "Falls back to --primary then --fallback on failure.")
    ap.add_argument("--ollama-model", type=str, default=None,
                    help="Ollama model tag (e.g. qwen2.5:7b). Required with --ollama-url.")
    ap.add_argument("--coach-only", action="store_true",
                    help="Use --primary only as a HINT coach for ollama (tier 1.5). "
                         "Skip tier-2/3 cloud code-gen entirely — saves cloud tokens.")
    ap.add_argument("--rag", action="store_true",
                    help="Retrieve top-K similar prior solutions from rag_index.json "
                         "and inline as few-shot examples in the ollama prompt.")
    ap.add_argument("--rag-k", type=int, default=5)
    ap.add_argument("--rag-index", type=str,
                    default=str(REPO_ROOT / "benchmark" / "rag_index.json"))
    args = ap.parse_args()
    fallback = args.fallback if args.fallback else None
    slim = not args.full_grammar
    if args.ollama_url and not args.ollama_model:
        ap.error("--ollama-url requires --ollama-model")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tasks = TASKS
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",")}
        tasks = [t for t in tasks if t["id"] in wanted]
    if args.limit:
        tasks = tasks[:args.limit]

    print(f"Extending with {len(tasks)} tasks, {args.workers} workers, {args.attempts} attempts each")
    if args.ollama_url:
        print(f"Tier 1 (free): ollama {args.ollama_model} @ {args.ollama_url}")
    if args.coach_only:
        print(f"Tier 1.5 (coach-only): {args.primary} writes hints; tier-2/3 cloud code-gen DISABLED")
    else:
        print(f"Tier 2: {args.primary} ({'slim' if slim else 'full'})  Tier 3 (fallback): {fallback or 'none'}")
    print(f"Output dir: {OUT_DIR}")

    rag_index = None
    if args.rag:
        idx_path = Path(args.rag_index)
        if not idx_path.exists():
            print(f"--rag set but {idx_path} missing. Run: python benchmark/rag.py build")
            sys.exit(1)
        rag_index = rag.load_index(idx_path)
        print(f"RAG: loaded {rag_index['count']} entries (dim {rag_index['dim']}) from {idx_path}")
    print()

    start = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process_task, t, args.force, args.attempts,
                            args.primary, fallback, slim,
                            args.ollama_url, args.ollama_model,
                            args.coach_only,
                            rag_index, args.rag_k): t for t in tasks}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            status = r["status"]
            marker = {"ok": "✓", "skip-exists": "=", "bad-python-spec": "!",
                     "failed": "✗"}.get(status, "?")
            extra = ""
            if status == "ok":
                extra = f" (att {r['attempts']}, {r['tokens']}b)"
            elif status == "bad-python-spec":
                extra = f" {r.get('note', '')[:70]}"
            elif status == "failed":
                extra = f" {r.get('note', '')[:70]}"
            print(f"  [{i}/{len(tasks)}] {marker} {r['id']}{extra}")
            results.append(r)

    elapsed = time.time() - start
    counts = {"ok": 0, "skip-exists": 0, "bad-python-spec": 0, "failed": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print(f"\n=== DONE in {elapsed:.1f}s ===")
    for k, v in counts.items():
        print(f"  {k}: {v}")

    log_path = REPO_ROOT / "benchmark" / f"corpus_extension_log.json"
    log_path.write_text(json.dumps(results, indent=2))
    print(f"\nLog saved to {log_path}")


if __name__ == "__main__":
    main()
