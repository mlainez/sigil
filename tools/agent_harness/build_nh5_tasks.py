#!/usr/bin/env python3
"""Build the 30-task NH5 agent harness suite.

Loads the existing 8 tasks from agent_tasks_8.json (backup of the
original) and adds 22 new multi-step tasks covering shapes the
8-task suite doesn't reach. Verifies each new task by running its
reference Python implementation against the input and checking that
the expected output matches.

The 8-task suite has been the agent harness benchmark across
Phases 18-26. Phase 27's NH5 hypothesis (papers/HYPOTHESES.md) is
that 8 tasks are too few to distinguish signal from noise — a 30-task
suite drops per-task contribution from 12.5pp to 3.3pp.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
EXISTING = REPO / "tools" / "agent_harness" / "agent_tasks_8.json"
OUT = REPO / "tools" / "agent_harness" / "agent_tasks.json"


# ============================================================================
# 22 new multi-step tasks. Each task has a Python reference implementation
# that's executed against the input to verify the expected output.
# ============================================================================

NEW_TASKS = [
    # --- Shell-pipeline shapes (cut/sort/uniq style multi-stage) ---
    {
        "id": "passwd_top_shells",
        "shape": "shell_pipeline",
        "goal": "From this /etc/passwd-style input, find the 2 most-used login shells (last colon-separated field). Print 'SHELL: COUNT' descending by count, ties broken by first appearance.",
        "input": "root:x:0:0:root:/root:/bin/bash\nalice:x:1000:1000::/home/alice:/bin/bash\nbob:x:1001:1001::/home/bob:/bin/zsh\ncarol:x:1002:1002::/home/carol:/bin/bash\ndave:x:1003:1003::/home/dave:/usr/bin/fish\neve:x:1004:1004::/home/eve:/bin/zsh",
        "python": (
            "import sys\nfrom collections import Counter\n"
            "lines = sys.argv[1].split('\\n')\n"
            "shells = [l.split(':')[-1] for l in lines if l]\n"
            "c = Counter(shells)\n"
            "# Sort by count desc, tie-break by first-appearance order\n"
            "order = []\n"
            "seen = set()\n"
            "for s in shells:\n"
            "    if s not in seen: seen.add(s); order.append(s)\n"
            "ranked = sorted(order, key=lambda s: -c[s])\n"
            "for s in ranked[:2]:\n"
            "    sys.stdout.write(f'{s}: {c[s]}\\n')"
        ),
    },
    {
        "id": "wc_top_words",
        "shape": "shell_pipeline",
        "goal": "From this multi-line text, find the 3 most-common words (case-insensitive, ignoring punctuation). Print 'word: count' descending by count.",
        "input": "The quick brown fox jumps over the lazy dog.\nThe fox was very quick. The dog was lazy.\nA dog and a fox went on an adventure.",
        "python": (
            "import sys, re\nfrom collections import Counter\n"
            "text = sys.argv[1].lower()\n"
            "words = re.findall(r'[a-z]+', text)\n"
            "c = Counter(words)\n"
            "for w, n in c.most_common(3):\n"
            "    sys.stdout.write(f'{w}: {n}\\n')"
        ),
    },
    {
        "id": "find_files_by_size",
        "shape": "shell_pipeline",
        "goal": "From this 'find -printf' output (each line 'SIZE PATH'), print the 3 largest files as 'PATH SIZE' descending.",
        "input": "1024 /tmp/a.txt\n8192 /tmp/big.log\n512 /tmp/small.cfg\n4096 /tmp/medium.dat\n16384 /tmp/huge.bin\n2048 /tmp/notes.md",
        "python": (
            "import sys\n"
            "rows = [(int(l.split()[0]), l.split()[1]) for l in sys.argv[1].split('\\n') if l]\n"
            "for size, path in sorted(rows, key=lambda r: -r[0])[:3]:\n"
            "    sys.stdout.write(f'{path} {size}\\n')"
        ),
    },

    # --- Config / env parsing ---
    {
        "id": "env_filter_prefix",
        "shape": "config_parsing",
        "goal": "From this KEY=VALUE input (one per line), print only entries whose KEY starts with 'APP_'. Output 'KEY=VALUE' alphabetically sorted by KEY.",
        "input": "PATH=/usr/bin\nAPP_PORT=8080\nHOME=/root\nAPP_DEBUG=1\nLANG=en_US\nAPP_HOST=localhost",
        "python": (
            "import sys\n"
            "kvs = [l for l in sys.argv[1].split('\\n') if l.startswith('APP_')]\n"
            "for kv in sorted(kvs, key=lambda x: x.split('=')[0]):\n"
            "    sys.stdout.write(kv + '\\n')"
        ),
    },
    {
        "id": "ini_section_keys",
        "shape": "config_parsing",
        "goal": "From this INI-style config, print all keys that appear under the [database] section. One key per line, in input order.",
        "input": "[server]\nport=8080\nhost=localhost\n[database]\nuser=admin\npassword=secret\nhost=db.local\n[logging]\nlevel=INFO",
        "python": (
            "import sys\n"
            "section = None\n"
            "for line in sys.argv[1].split('\\n'):\n"
            "    line = line.strip()\n"
            "    if line.startswith('['):\n"
            "        section = line.strip('[]')\n"
            "    elif '=' in line and section == 'database':\n"
            "        sys.stdout.write(line.split('=')[0] + '\\n')"
        ),
    },

    # --- Timestamp arithmetic / time bucketing ---
    {
        "id": "log_count_by_hour",
        "shape": "timestamp_arithmetic",
        "goal": "From timestamped log lines 'YYYY-MM-DDTHH:MM:SS message', count entries per hour (HH only). Print 'HH: COUNT' sorted by hour ascending.",
        "input": "2026-05-01T08:14:01 startup\n2026-05-01T08:30:22 ready\n2026-05-01T09:01:11 request\n2026-05-01T09:45:55 request\n2026-05-01T09:50:12 request\n2026-05-01T10:01:33 request\n2026-05-01T10:15:00 shutdown",
        "python": (
            "import sys\nfrom collections import Counter\n"
            "hours = [l.split('T')[1][:2] for l in sys.argv[1].split('\\n') if l]\n"
            "c = Counter(hours)\n"
            "for h in sorted(c):\n"
            "    sys.stdout.write(f'{h}: {c[h]}\\n')"
        ),
    },
    {
        "id": "duration_total_minutes",
        "shape": "timestamp_arithmetic",
        "goal": "Each line is 'HH:MM-HH:MM' representing a time range. Print the total minutes across all ranges as a single integer.",
        "input": "09:00-10:30\n14:15-15:45\n11:00-11:50",
        "python": (
            "import sys\n"
            "def m(t):\n"
            "    h, mn = t.split(':')\n"
            "    return int(h)*60 + int(mn)\n"
            "total = sum(m(l.split('-')[1]) - m(l.split('-')[0]) for l in sys.argv[1].split('\\n') if l)\n"
            "sys.stdout.write(f'{total}\\n')"
        ),
    },

    # --- Process log filter / categorize ---
    {
        "id": "syslog_grep_unique_processes",
        "shape": "process_log_filter",
        "goal": "From syslog-style lines 'TIMESTAMP HOST PROCESS[PID]: MESSAGE', print the distinct PROCESS names (no [PID]) alphabetically sorted, one per line.",
        "input": "May 01 10:00:01 host kernel[0]: boot\nMay 01 10:00:02 host systemd[1]: ready\nMay 01 10:00:03 host sshd[123]: connection\nMay 01 10:00:04 host kernel[0]: tick\nMay 01 10:00:05 host cron[456]: job",
        "python": (
            "import sys, re\n"
            "procs = set()\n"
            "for l in sys.argv[1].split('\\n'):\n"
            "    m = re.search(r' ([a-zA-Z_]+)\\[', l)\n"
            "    if m: procs.add(m.group(1))\n"
            "for p in sorted(procs):\n"
            "    sys.stdout.write(p + '\\n')"
        ),
    },
    {
        "id": "errors_by_category",
        "shape": "process_log_filter",
        "goal": "Each line is 'LEVEL: MESSAGE'. Count ERROR-level lines by the first word of MESSAGE. Print 'WORD COUNT' descending by count.",
        "input": "INFO: starting up\nERROR: timeout connecting\nERROR: timeout waiting\nWARN: slow query\nERROR: connection refused\nINFO: shutdown\nERROR: timeout reading",
        "python": (
            "import sys\nfrom collections import Counter\n"
            "words = []\n"
            "for l in sys.argv[1].split('\\n'):\n"
            "    if l.startswith('ERROR:'):\n"
            "        first = l.split(':',1)[1].strip().split()[0]\n"
            "        words.append(first)\n"
            "c = Counter(words)\n"
            "for w, n in sorted(c.items(), key=lambda x: -x[1]):\n"
            "    sys.stdout.write(f'{w} {n}\\n')"
        ),
    },

    # --- Compose / multi-stage transforms ---
    {
        "id": "csv_filter_then_top",
        "shape": "compose_sort",
        "goal": "CSV with header 'name,score'. Filter rows where score > 70 (numeric), then print the names of the top 3 (highest score first).",
        "input": "name,score\nalice,82\nbob,65\ncarol,91\ndave,77\neve,55\nfrank,88",
        "python": (
            "import sys\n"
            "lines = sys.argv[1].split('\\n')[1:]  # skip header\n"
            "rows = [(l.split(',')[0], int(l.split(',')[1])) for l in lines if l]\n"
            "filtered = [r for r in rows if r[1] > 70]\n"
            "for name, _ in sorted(filtered, key=lambda r: -r[1])[:3]:\n"
            "    sys.stdout.write(name + '\\n')"
        ),
    },
    {
        "id": "running_sum",
        "shape": "cumulative_calc",
        "goal": "Each line is one integer. Print the running sum (cumulative total) after each line, one per line.",
        "input": "5\n3\n8\n2\n4",
        "python": (
            "import sys\n"
            "total = 0\n"
            "for l in sys.argv[1].split('\\n'):\n"
            "    if l:\n"
            "        total += int(l)\n"
            "        sys.stdout.write(f'{total}\\n')"
        ),
    },
    {
        "id": "csv_to_json_array",
        "shape": "format_conversion",
        "goal": "Convert CSV with header 'id,name,active' to a single-line compact JSON array of objects. id and active should be integers. Output exactly the JSON, no trailing newline.",
        "input": "id,name,active\n1,alice,1\n2,bob,0\n3,carol,1",
        "python": (
            "import sys, json\n"
            "lines = sys.argv[1].split('\\n')\n"
            "header = lines[0].split(',')\n"
            "rows = []\n"
            "for l in lines[1:]:\n"
            "    if l:\n"
            "        f = l.split(',')\n"
            "        rows.append({'id': int(f[0]), 'name': f[1], 'active': int(f[2])})\n"
            "sys.stdout.write(json.dumps(rows, separators=(',', ':')))"
        ),
    },

    # --- Nested JSON extract ---
    {
        "id": "json_users_with_admin_role",
        "shape": "nested_json_extract",
        "goal": "From this JSON array of objects with 'name' and 'roles' (a list of strings), print names of users that include 'admin' in their roles. One per line in input order.",
        "input": '[{"name":"alice","roles":["user","editor"]},{"name":"bob","roles":["admin","user"]},{"name":"carol","roles":["user"]},{"name":"dave","roles":["admin"]}]',
        "python": (
            "import sys, json\n"
            "for u in json.loads(sys.argv[1]):\n"
            "    if 'admin' in u['roles']:\n"
            "        sys.stdout.write(u['name'] + '\\n')"
        ),
    },
    {
        "id": "json_path_max_value",
        "shape": "nested_json_extract",
        "goal": "From this JSON object {\"items\":[{\"name\":..., \"price\":...}, ...]}, print the name of the item with the highest price.",
        "input": '{"items":[{"name":"apple","price":1.50},{"name":"banana","price":0.75},{"name":"cherry","price":3.00},{"name":"date","price":2.25}]}',
        "python": (
            "import sys, json\n"
            "items = json.loads(sys.argv[1])['items']\n"
            "best = max(items, key=lambda x: x['price'])\n"
            "sys.stdout.write(best['name'] + '\\n')"
        ),
    },

    # --- Multi-regex extract ---
    {
        "id": "extract_versions_sorted",
        "shape": "multi_regex_extract",
        "goal": "Extract all semantic versions (vMAJOR.MINOR.PATCH) from arg0, deduplicate, and print them sorted ascending by version (semantic, not lexical). One per line.",
        "input": "release v2.0.0 and v1.10.5 and v2.0.0 again, but also v1.2.3 and v10.0.0",
        "python": (
            "import sys, re\n"
            "vs = set(re.findall(r'v\\d+\\.\\d+\\.\\d+', sys.argv[1]))\n"
            "key = lambda v: tuple(int(x) for x in v[1:].split('.'))\n"
            "for v in sorted(vs, key=key):\n"
            "    sys.stdout.write(v + '\\n')"
        ),
    },
    {
        "id": "extract_phone_then_format",
        "shape": "multi_regex_extract",
        "goal": "Extract all 10-digit phone numbers from arg0 (with or without dashes/spaces), then print each as '(XXX) XXX-XXXX' format, one per line in input order.",
        "input": "Call 555-123-4567 or 555.987.6543 or 5551234567 anytime",
        "python": (
            "import sys, re\n"
            "raw = re.findall(r'\\d{3}[-. ]?\\d{3}[-. ]?\\d{4}', sys.argv[1])\n"
            "for r in raw:\n"
            "    digits = re.sub(r'\\D', '', r)\n"
            "    sys.stdout.write(f'({digits[:3]}) {digits[3:6]}-{digits[6:]}\\n')"
        ),
    },

    # --- Range / threshold filtering ---
    {
        "id": "histogram_buckets",
        "shape": "range_filter",
        "goal": "Each line is a single integer score 0-100. Bucket into 'A: 90-100', 'B: 80-89', 'C: 70-79', 'D: 60-69', 'F: 0-59'. Print 'BUCKET: COUNT' for each bucket that has at least one entry, in A→F order.",
        "input": "85\n92\n67\n78\n95\n55\n88\n72\n91\n45",
        "python": (
            "import sys\n"
            "buckets = {'A':0,'B':0,'C':0,'D':0,'F':0}\n"
            "for l in sys.argv[1].split('\\n'):\n"
            "    if l:\n"
            "        n = int(l)\n"
            "        if n >= 90: buckets['A'] += 1\n"
            "        elif n >= 80: buckets['B'] += 1\n"
            "        elif n >= 70: buckets['C'] += 1\n"
            "        elif n >= 60: buckets['D'] += 1\n"
            "        else: buckets['F'] += 1\n"
            "for b in 'ABCDF':\n"
            "    if buckets[b] > 0:\n"
            "        sys.stdout.write(f'{b}: {buckets[b]}\\n')"
        ),
    },
    {
        "id": "filter_lines_in_range",
        "shape": "range_filter",
        "goal": "Each line has 'NAME VALUE' (space-separated; VALUE is a float). Print names of entries where VALUE is between 10.0 and 50.0 inclusive, alphabetically sorted.",
        "input": "alpha 5.0\nbeta 25.5\ngamma 100.0\ndelta 12.3\nepsilon 50.0\nzeta 7.7\neta 35.1",
        "python": (
            "import sys\n"
            "names = [l.split()[0] for l in sys.argv[1].split('\\n') if l and 10.0 <= float(l.split()[1]) <= 50.0]\n"
            "for n in sorted(names):\n"
            "    sys.stdout.write(n + '\\n')"
        ),
    },

    # --- Dedupe with count ---
    {
        "id": "uniq_c_with_threshold",
        "shape": "dedupe_with_count",
        "goal": "Each line is one word. Print 'WORD COUNT' for words that appear at least 2 times, sorted descending by count, ties broken alphabetically. No output if no word qualifies.",
        "input": "apple\nbanana\napple\ncherry\nbanana\napple\ndate\nelderberry",
        "python": (
            "import sys\nfrom collections import Counter\n"
            "c = Counter(l for l in sys.argv[1].split('\\n') if l)\n"
            "qual = [(w,n) for w,n in c.items() if n >= 2]\n"
            "for w, n in sorted(qual, key=lambda x: (-x[1], x[0])):\n"
            "    sys.stdout.write(f'{w} {n}\\n')"
        ),
    },

    # --- Code mining variants ---
    {
        "id": "extract_python_imports",
        "shape": "code_mining",
        "goal": "From this Python source, extract all top-level module names imported (handle 'import X', 'import X as Y', 'from X import Y'). Print the module names alphabetically sorted, deduplicated, one per line.",
        "input": "import os\nimport sys\nfrom typing import List, Dict\nfrom collections import defaultdict\nimport re\nfrom os import path\nimport json as js",
        "python": (
            "import sys, re\n"
            "mods = set()\n"
            "for l in sys.argv[1].split('\\n'):\n"
            "    l = l.strip()\n"
            "    m = re.match(r'^import (\\w+)', l)\n"
            "    if m: mods.add(m.group(1)); continue\n"
            "    m = re.match(r'^from (\\w+) import', l)\n"
            "    if m: mods.add(m.group(1))\n"
            "for m in sorted(mods):\n"
            "    sys.stdout.write(m + '\\n')"
        ),
    },

    # --- CSV join shape ---
    {
        "id": "csv_lookup_join",
        "shape": "csv_join",
        "goal": "arg0 contains two CSV blocks separated by a blank line. First block has 'id,name'; second has 'id,score'. Print 'NAME SCORE' for each id present in BOTH blocks, sorted alphabetically by name.",
        "input": "id,name\n1,alice\n2,bob\n3,carol\n4,dave\n\nid,score\n2,90\n3,85\n5,70\n2,75",
        "python": (
            "import sys\n"
            "blocks = sys.argv[1].split('\\n\\n')\n"
            "names = {}\n"
            "for l in blocks[0].split('\\n')[1:]:\n"
            "    if l:\n"
            "        i, n = l.split(',')\n"
            "        names[i] = n\n"
            "rows = []\n"
            "for l in blocks[1].split('\\n')[1:]:\n"
            "    if l:\n"
            "        i, s = l.split(',')\n"
            "        if i in names:\n"
            "            rows.append((names[i], s))\n"
            "for n, s in sorted(set(rows)):\n"
            "    sys.stdout.write(f'{n} {s}\\n')"
        ),
    },

    # --- Text diff style ---
    {
        "id": "lines_only_in_a",
        "shape": "text_diff",
        "goal": "arg0 contains two newline-separated blocks separated by '---' on its own line. Print lines that appear in the first block but NOT in the second block, in input order, deduplicated.",
        "input": "alpha\nbeta\ngamma\ndelta\n---\nbeta\ngamma\nepsilon",
        "python": (
            "import sys\n"
            "blocks = sys.argv[1].split('\\n---\\n')\n"
            "a_lines = blocks[0].split('\\n')\n"
            "b_set = set(blocks[1].split('\\n'))\n"
            "seen = set()\n"
            "for l in a_lines:\n"
            "    if l and l not in b_set and l not in seen:\n"
            "        seen.add(l)\n"
            "        sys.stdout.write(l + '\\n')"
        ),
    },
]


def run_python(code: str, args: list) -> tuple[bool, str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([sys.executable, f.name] + args,
                              capture_output=True, text=True, timeout=10)
            return r.returncode == 0, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return False, "", "timeout"


def main():
    existing = json.loads(EXISTING.read_text())
    print(f"Loaded {len(existing)} existing tasks from {EXISTING.name}")

    print(f"\nVerifying {len(NEW_TASKS)} new tasks via Python reference...")
    verified = []
    for t in NEW_TASKS:
        ok, out, err = run_python(t["python"], [t["input"]])
        if not ok:
            print(f"  FAIL  {t['id']}: Python errored: {err[:80]}")
            continue
        # The reference Python defines what 'expected' should be
        t_with_expected = {
            "id": t["id"],
            "shape": t["shape"],
            "goal": t["goal"],
            "input": t["input"],
            "expected": out,
        }
        verified.append(t_with_expected)
        print(f"  PASS  {t['id']}: {len(out.encode())}b expected output")

    print(f"\n{len(verified)}/{len(NEW_TASKS)} verified.")

    combined = existing + verified
    OUT.write_text(json.dumps(combined, indent=2))
    print(f"\nWrote {len(combined)} tasks to {OUT}")
    print(f"  - {len(existing)} existing")
    print(f"  - {len(verified)} new")

    return 0 if len(verified) == len(NEW_TASKS) else 1


if __name__ == "__main__":
    sys.exit(main())
