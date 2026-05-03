#!/usr/bin/env python3
"""Build Tier 1 corpus seeds for the agent harness failure modes:

  Group A (12): $0 + (split $0 "\\n") shapes — drown out the (argv) instinct.
  Group B (8):  header-aware tabular — index columns by header position.
  Group C (6):  find_all with capturing groups vs full-match shapes.

Each seed is verified end-to-end: the Sigil program is executed against
the args and only kept if its stdout matches expected verbatim. Append
to training_corpus.jsonl and rebuild rag_index.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO / "interpreter" / "_build" / "default" / "vm.exe")
CORPUS = str(REPO / "benchmark" / "training_corpus.jsonl")
SEED_OUT = str(REPO / "benchmark" / "tier1_agent_seeds.jsonl")

SYSTEM = (
    "You write Sigil programs. Sigil is an S-expression language designed "
    "for minimal tokens. Programs may use (module name ...) wrapping or "
    "top-level script mode. CLI args: $0 is the first user arg as a string, "
    "#0 is the first as an int. The harness passes ALL input as a single "
    "multi-line string in $0 — use (split $0 \"\\n\") to get lines, NOT "
    "(argv). (argv) is the list of separate CLI arguments. For tabular "
    "input with a header row (e.g. \"date,category,amount\"), index by "
    "column position; the categorical field is rarely (first row). "
    "find_all returns the full match per hit when the pattern has no "
    "capturing groups, and the group per hit when it has one. Use short "
    "aliases: len, str, fmt, split, join, sort, push, filter, map_arr, "
    "reduce, counter, sort_by, entries, enumerate, scan, find_all, "
    "regex_find, regex_match. Output ONLY raw Sigil code."
)


def run_sigil(code: str, args: list) -> tuple[bool, str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run([SIGIL_BIN, f.name] + args,
                              capture_output=True, text=True, timeout=10,
                              errors="replace")
            return r.returncode == 0, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return False, "", "timeout"
        finally:
            os.unlink(f.name)


# ============================================================================
# Group A — $0 + (split $0 "\n") shapes
# ============================================================================
GROUP_A = [
    {
        "desc": "Take a multi-line string in arg0. Print each line uppercased, one per line.",
        "args": ["alpha\nbeta\ngamma"],
        "expected": "ALPHA\nBETA\nGAMMA\n",
        "code": '(for-each line (split $0 "\\n") (println (upper line)))',
    },
    {
        "desc": "Multi-line input in arg0; print only lines containing 'ERROR'.",
        "args": ["INFO ok\nERROR fail\nWARN slow\nERROR timeout"],
        "expected": "ERROR fail\nERROR timeout\n",
        "code": '(for-each line (split $0 "\\n") (if (in "ERROR" line) (println line)))',
    },
    {
        "desc": "Each line of arg0 is one integer. Print their sum.",
        "args": ["10\n20\n30\n5"],
        "expected": "65\n",
        "code": '(println (sum (map_arr (split $0 "\\n") (\\l (parse_int l)))))',
    },
    {
        "desc": "Each line of arg0 is space-separated tokens. Print the first token of each line.",
        "args": ["alpha 1 2\nbeta 3 4\ngamma 5 6"],
        "expected": "alpha\nbeta\ngamma\n",
        "code": '(for-each line (split $0 "\\n") (println (first (split line " "))))',
    },
    {
        "desc": "Multi-line input in arg0. Print the count of lines.",
        "args": ["a\nb\nc\nd"],
        "expected": "4\n",
        "code": '(println (len (split $0 "\\n")))',
    },
    {
        "desc": "Multi-line input in arg0. Print only lines whose length is greater than 5 characters.",
        "args": ["ok\nlonger line\nhi\nanother long one\nbye"],
        "expected": "longer line\nanother long one\n",
        "code": '(for-each line (split $0 "\\n") (if (gt (len line) 5) (println line)))',
    },
    {
        "desc": "Each line of arg0 is 'KEY=VAL'. Print VAL for each, one per line.",
        "args": ["A=1\nB=hello\nC=42"],
        "expected": "1\nhello\n42\n",
        "code": '(for-each line (split $0 "\\n") (println (last (split line "="))))',
    },
    {
        "desc": "Multi-line input in arg0. Print lines in reverse order (last first).",
        "args": ["one\ntwo\nthree\nfour"],
        "expected": "four\nthree\ntwo\none\n",
        "code": '(for-each line (rev (split $0 "\\n")) (println line))',
    },
    {
        "desc": "Each line of arg0 is a tab-separated row of 3 columns. Print the second column of each row.",
        "args": ["a\tb\tc\nx\ty\tz\n1\t2\t3"],
        "expected": "b\ny\n2\n",
        "code": '(for-each line (split $0 "\\n") (println (array_get (split line "\\t") 1)))',
    },
    {
        "desc": "Multi-line input in arg0. Print the longest line (by character count).",
        "args": ["short\na bit longer\nmid\nthe longest line here"],
        "expected": "the longest line here\n",
        "code": '(println (last (sort_by (split $0 "\\n") (\\l (len l)))))',
    },
    {
        "desc": "Each line of arg0 is one word. Print only distinct words in input order.",
        "args": ["apple\nbanana\napple\ncherry\nbanana\napple"],
        "expected": "apple\nbanana\ncherry\n",
        "code": '(set seen {})\n(for-each w (split $0 "\\n")\n  (if (not (in w seen))\n    (do (println w) (set seen (json_set seen [w] true)))))',
    },
    {
        "desc": "Multi-line input in arg0. Print every line, prefixed with its 1-based line number and a colon-space (e.g. '1: alpha').",
        "args": ["alpha\nbeta\ngamma"],
        "expected": "1: alpha\n2: beta\n3: gamma\n",
        "code": '(set lines (split $0 "\\n"))\n(for i 0 (len lines)\n  (println (fmt "{}: {}" (add i 1) (array_get lines i))))',
    },
]

# ============================================================================
# Group B — header-aware tabular
# ============================================================================
GROUP_B = [
    {
        "desc": "CSV in arg0 with header 'name,age,city'. Print names of people whose city is 'paris', one per line, in input order.",
        "args": ["name,age,city\nalice,30,paris\nbob,25,nyc\ncarol,28,paris\ndave,35,tokyo"],
        "expected": "alice\ncarol\n",
        "code": '(set rows (slice (split $0 "\\n") 1 (len (split $0 "\\n"))))\n(for-each row rows\n  (set fields (split row ","))\n  (if (eq (array_get fields 2) "paris")\n    (println (array_get fields 0))))',
    },
    {
        "desc": "CSV in arg0 with header 'date,category,amount'. Group sum of amount by category, print 'CATEGORY: TOTAL' (no formatting), one per line in input order of first appearance.",
        "args": ["date,category,amount\n2026-01,food,10\n2026-02,transit,5\n2026-03,food,20\n2026-04,transit,3"],
        "expected": "food: 30\ntransit: 8\n",
        "code": '(set sums {})\n(set order [])\n(set rows (slice (split $0 "\\n") 1 (len (split $0 "\\n"))))\n(for-each row rows\n  (set fields (split row ","))\n  (set cat (array_get fields 1))\n  (set amt (parse_int (array_get fields 2)))\n  (if (not (in cat sums)) (push order cat))\n  (set sums (json_set sums [cat] (add (get_or sums cat 0) amt))))\n(for-each k order\n  (println (fmt "{}: {}" k (json_get sums [k]))))',
    },
    {
        "desc": "TSV in arg0 with header 'sku\\tprice\\tqty'. Print total revenue (price*qty summed across all rows) as a single integer.",
        "args": ["sku\tprice\tqty\nA1\t10\t3\nB2\t20\t2\nC3\t5\t7"],
        "expected": "105\n",
        "code": '(set rows (slice (split $0 "\\n") 1 (len (split $0 "\\n"))))\n(println (sum (map_arr rows (\\r (mul (parse_int (array_get (split r "\\t") 1)) (parse_int (array_get (split r "\\t") 2)))))))',
    },
    {
        "desc": "CSV in arg0 with header 'username,role,tenure'. Count rows where role is 'admin'. Print the count as a single integer.",
        "args": ["username,role,tenure\nalice,admin,5\nbob,user,2\ncarol,admin,7\ndave,guest,1"],
        "expected": "2\n",
        "code": '(set rows (slice (split $0 "\\n") 1 (len (split $0 "\\n"))))\n(println (len (filter rows (\\r (eq (array_get (split r ",") 1) "admin")))))',
    },
    {
        "desc": "CSV in arg0 with header 'id,name,score'. Print the names of the top 3 by score (descending), one per line.",
        "args": ["id,name,score\n1,alice,87\n2,bob,92\n3,carol,75\n4,dave,99\n5,eve,88"],
        "expected": "dave\nbob\neve\n",
        "code": '(set rows (slice (split $0 "\\n") 1 (len (split $0 "\\n"))))\n(set ranked (rev (sort_by rows (\\r (parse_int (array_get (split r ",") 2))))))\n(for-each r (slice ranked 0 3)\n  (println (array_get (split r ",") 1)))',
    },
    {
        "desc": "CSV in arg0 with header 'src_ip,dst_port,bytes'. Sum bytes by dst_port. Print 'PORT: TOTAL' one per line in input order of first port appearance.",
        "args": ["src_ip,dst_port,bytes\n10.0.0.1,80,1500\n10.0.0.2,443,2000\n10.0.0.3,80,500\n10.0.0.4,443,3000"],
        "expected": "80: 2000\n443: 5000\n",
        "code": '(set sums {})\n(set order [])\n(set rows (slice (split $0 "\\n") 1 (len (split $0 "\\n"))))\n(for-each row rows\n  (set f (split row ","))\n  (set port (array_get f 1))\n  (set b (parse_int (array_get f 2)))\n  (if (not (in port sums)) (push order port))\n  (set sums (json_set sums [port] (add (get_or sums port 0) b))))\n(for-each k order\n  (println (fmt "{}: {}" k (json_get sums [k]))))',
    },
    {
        "desc": "TSV in arg0 with header 'product\\tsales\\treturns'. Print product names where returns are at least 10 percent of sales (returns*10 >= sales), one per line in input order.",
        "args": ["product\tsales\treturns\nwidget\t100\t5\ngadget\t200\t30\nthingy\t50\t6\nfoobar\t1000\t90"],
        "expected": "gadget\nthingy\n",
        "code": '(set rows (slice (split $0 "\\n") 1 (len (split $0 "\\n"))))\n(for-each row rows\n  (set f (split row "\\t"))\n  (if (ge (mul (parse_int (array_get f 2)) 10) (parse_int (array_get f 1)))\n    (println (array_get f 0))))',
    },
    {
        "desc": "CSV in arg0 with header 'user,action,timestamp'. Sort rows by timestamp ascending and print just the user column for each row, one per line.",
        "args": ["user,action,timestamp\nalice,login,300\nbob,logout,150\ncarol,login,200\ndave,view,100"],
        "expected": "dave\nbob\ncarol\nalice\n",
        "code": '(set rows (slice (split $0 "\\n") 1 (len (split $0 "\\n"))))\n(set sorted (sort_by rows (\\r (parse_int (array_get (split r ",") 2)))))\n(for-each r sorted\n  (println (array_get (split r ",") 0)))',
    },
]

# ============================================================================
# Group C — find_all with/without capturing groups
# ============================================================================
GROUP_C = [
    {
        "desc": "From the Python source in arg0, extract just the names of every top-level (no leading whitespace) `def NAME(`. Print the names, one per line, in order.",
        "args": ["def alpha():\n    pass\n\nclass C:\n    def inside(self):\n        pass\n\ndef beta(x):\n    return x\n\ndef gamma():\n    pass"],
        "expected": "alpha\nbeta\ngamma\n",
        "code": '(for-each line (split $0 "\\n")\n  (if (regex_match "^def [a-zA-Z_]" line)\n    (println (array_get (split (array_get (split line "(") 0) " ") 1))))',
    },
    {
        "desc": "Extract every dotted-quad IPv4 address from arg0 and print one per line in order of appearance. Do not include partials (1.2.3) or numbers > 255 in any octet.",
        "args": ["see 10.0.0.1 and 192.168.1.42, but not 1.2.3 or 10.0.0.1 again"],
        "expected": "10.0.0.1\n192.168.1.42\n10.0.0.1\n",
        "code": '(for-each ip (find_all "\\b(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])(?:\\.(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])){3}\\b" $0)\n  (println ip))',
    },
    {
        "desc": "Extract every YYYY-MM-DD date from arg0 and print one per line in order.",
        "args": ["log on 2026-05-03 and 2024-12-31; also 2024-13-99 (wrong) and 2025-01-15"],
        "expected": "2026-05-03\n2024-12-31\n2024-13-99\n2025-01-15\n",
        "code": '(for-each d (find_all "\\d{4}-\\d{2}-\\d{2}" $0) (println d))',
    },
    {
        "desc": "Extract every semantic version (vMAJOR.MINOR.PATCH) from arg0 and print one per line in order.",
        "args": ["release v1.2.3 then v2.0.0 then v1.10.5 final"],
        "expected": "v1.2.3\nv2.0.0\nv1.10.5\n",
        "code": '(for-each v (find_all "v\\d+\\.\\d+\\.\\d+" $0) (println v))',
    },
    {
        "desc": "Extract every email address from arg0 and print one per line in order. An email is one or more word/dot/dash chars, then '@', then one or more word/dot chars with at least one dot.",
        "args": ["mail alice@example.com and bob.smith@test.co or carol@x.y.z, not just-a-word."],
        "expected": "alice@example.com\nbob.smith@test.co\ncarol@x.y.z\n",
        "code": '(for-each e (find_all "[\\w.-]+@[\\w.]+\\.[\\w]+" $0) (println e))',
    },
    {
        "desc": "Print only the local part (before the '@') of every email address in arg0, one per line in order.",
        "args": ["alice@example.com bob@x.y carol@a.b"],
        "expected": "alice\nbob\ncarol\n",
        "code": '(for-each e (find_all "[\\w.-]+@[\\w.]+\\.[\\w]+" $0)\n  (println (first (split e "@"))))',
    },
]


def main() -> int:
    all_seeds = GROUP_A + GROUP_B + GROUP_C
    print(f"Verifying {len(all_seeds)} seeds...")

    verified = []
    failures = []
    for s in all_seeds:
        ok, out, err = run_sigil(s["code"], s["args"])
        if ok and out == s["expected"]:
            verified.append(s)
            print(f"  PASS  {s['desc'][:60]}")
        else:
            failures.append((s, ok, out, err))
            print(f"  FAIL  {s['desc'][:60]}")
            print(f"        got returncode_ok={ok} stdout={out!r} stderr={err!r}")

    print(f"\n{len(verified)}/{len(all_seeds)} seeds verified.")

    if failures:
        print(f"{len(failures)} seed(s) need code fixes before commit.")

    # Write the verified seeds in the chat-format used by the corpus
    with open(SEED_OUT, "w") as out:
        for s in verified:
            entry = {"messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": s["desc"]},
                {"role": "assistant", "content": s["code"]},
            ]}
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"Wrote {len(verified)} verified seeds to {SEED_OUT}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
