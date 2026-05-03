#!/usr/bin/env python3
"""Build Tier 2.5 corpus seeds — aggregation + format-conversion.

Targets the 3-of-5 Path C failures (Phase 23) that fail on the
"count by key" / "sum by key" / "group-and-aggregate" step. Plus a
small TSV/CSV → Markdown pack for the tsv_to_markdown failure.

Each seed is verified end-to-end against the live interpreter.
Append to training_corpus.jsonl, rebuild RAG index.
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
SEED_OUT = str(REPO / "benchmark" / "tier25_agent_seeds.jsonl")

SYSTEM = (
    "You write Sigil programs. Sigil is an S-expression language designed "
    "for minimal tokens. CLI args: $0 is the first user arg as a string. "
    "The harness passes ALL input as a single multi-line string in $0; "
    "use (split $0 \"\\n\") to iterate lines. For aggregation tasks the "
    "canonical pattern is: build a map with (json_set m [key] (add "
    "(get_or m key 0) ...)) inside a (for-each), then iterate "
    "(map_keys m) to print results. Use short aliases: len, str, fmt, "
    "split, join, sort, push, filter, map_arr, reduce, sort_by, "
    "json_set, json_get, get_or, map_keys, in. Output ONLY raw Sigil code."
)


def run_sigil(code: str, args: list) -> tuple[bool, str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code); f.flush()
        try:
            # Disable diagnostics here so seed verification stderr is clean
            env = os.environ.copy()
            env["SIGIL_DIAGNOSE"] = "0"
            r = subprocess.run([SIGIL_BIN, f.name] + args,
                              capture_output=True, text=True, timeout=10,
                              errors="replace", env=env)
            return r.returncode == 0, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return False, "", "timeout"
        finally:
            os.unlink(f.name)


# ============================================================================
# Group D — aggregation (count by key, sum by key, group-and-aggregate)
# ============================================================================
GROUP_D = [
    {
        "desc": "Each line of arg0 is a single word. Count occurrences of each unique word and print 'WORD COUNT' one per line in input order of first appearance.",
        "args": ["apple\nbanana\napple\ncherry\nbanana\napple"],
        "expected": "apple 3\nbanana 2\ncherry 1\n",
        "code": '(set counts {})\n(set order [])\n(for-each w (split $0 "\\n")\n  (if (not (in w counts)) (push order w))\n  (set counts (json_set counts [w] (add (get_or counts w 0) 1))))\n(for-each k order\n  (println (fmt "{} {}" k (json_get counts [k]))))',
    },
    {
        "desc": "Each line of arg0 is space-separated 'KEY VALUE' where VALUE is an integer. Sum VALUE by KEY and print 'KEY TOTAL' one per line in input order of first KEY appearance.",
        "args": ["a 10\nb 5\na 20\nc 7\nb 3\na 1"],
        "expected": "a 31\nb 8\nc 7\n",
        "code": '(set sums {})\n(set order [])\n(for-each line (split $0 "\\n")\n  (set parts (split line " "))\n  (set k (first parts))\n  (set v (parse_int (last parts)))\n  (if (not (in k sums)) (push order k))\n  (set sums (json_set sums [k] (add (get_or sums k 0) v))))\n(for-each k order\n  (println (fmt "{} {}" k (json_get sums [k]))))',
    },
    {
        "desc": "Each line of arg0 is a string. Find the line that appears most frequently. Print just that line (if tied, print the first one to reach the max).",
        "args": ["alpha\nbeta\nalpha\ngamma\nbeta\nalpha"],
        "expected": "alpha\n",
        "code": '(set counts {})\n(set order [])\n(for-each line (split $0 "\\n")\n  (if (not (in line counts)) (push order line))\n  (set counts (json_set counts [line] (add (get_or counts line 0) 1))))\n(set best "")\n(set best_count 0)\n(for-each k order\n  (if (gt (json_get counts [k]) best_count)\n    (do (set best k) (set best_count (json_get counts [k])))))\n(println best)',
    },
    {
        "desc": "Each line of arg0 is space-separated tokens. Count distinct tokens per line and print just the count for each line, one per line.",
        "args": ["a b c\na a b\nx y z w\np p p"],
        "expected": "3\n2\n4\n1\n",
        "code": '(for-each line (split $0 "\\n")\n  (set seen {})\n  (set count 0)\n  (for-each tok (split line " ")\n    (if (not (in tok seen))\n      (do (set seen (json_set seen [tok] true)) (set count (add count 1)))))\n  (println count))',
    },
    {
        "desc": "Each line of arg0 is one word. Print the top 3 most common words by count, descending, formatted 'WORD: COUNT' one per line. If a tie occurs in count, break by input order of first appearance.",
        "args": ["a\nb\na\nc\nd\nb\na\nc\ne\nb"],
        "expected": "a: 3\nb: 3\nc: 2\n",
        "code": '(set counts {})\n(set order [])\n(set idx 0)\n(set first_idx {})\n(for-each w (split $0 "\\n")\n  (if (not (in w counts))\n    (do (push order w) (set first_idx (json_set first_idx [w] idx))))\n  (set counts (json_set counts [w] (add (get_or counts w 0) 1)))\n  (set idx (add idx 1)))\n(set ranked (sort_by order (\\k (sub 0 (mul (json_get counts [k]) 1000000)))))\n(for-each k (slice ranked 0 3)\n  (println (fmt "{}: {}" k (json_get counts [k]))))',
    },
    {
        "desc": "Each line of arg0 is comma-separated 'CATEGORY,AMOUNT' where AMOUNT is a decimal. Sum AMOUNT by CATEGORY and print 'CATEGORY: TOTAL' (TOTAL formatted with 2 decimals) one per line in input order of first appearance.",
        "args": ["food,42.50\ntransit,18.00\nfood,33.20\nutility,120.00\nfood,18.50\ntransit,7.50"],
        "expected": "food: 94.20\ntransit: 25.50\nutility: 120.00\n",
        "code": '(set sums {})\n(set order [])\n(for-each line (split $0 "\\n")\n  (set parts (split line ","))\n  (set k (first parts))\n  (set v (float (last parts)))\n  (if (not (in k sums)) (push order k))\n  (set sums (json_set sums [k] (add (get_or sums k 0.0) v))))\n(for-each k order\n  (println (fmt "{}: {:.2f}" k (json_get sums [k]))))',
    },
    {
        "desc": "Each line of arg0 is a tab-separated row 'IP\\tSTATUS' where STATUS is an integer code. Count how many rows have each STATUS code. Print 'CODE COUNT' one per line in input order of first appearance.",
        "args": ["10.0.0.1\t200\n10.0.0.2\t404\n10.0.0.1\t200\n10.0.0.3\t500\n10.0.0.2\t404\n10.0.0.4\t200"],
        "expected": "200 3\n404 2\n500 1\n",
        "code": '(set counts {})\n(set order [])\n(for-each line (split $0 "\\n")\n  (set code (last (split line "\\t")))\n  (if (not (in code counts)) (push order code))\n  (set counts (json_set counts [code] (add (get_or counts code 0) 1))))\n(for-each k order\n  (println (fmt "{} {}" k (json_get counts [k]))))',
    },
    {
        "desc": "Each line of arg0 is whitespace-separated 'TIMESTAMP LEVEL MESSAGE'. Count how many lines have each LEVEL. Print 'LEVEL COUNT' one per line in input order of first appearance.",
        "args": ["10:00 INFO ok\n10:01 ERROR fail\n10:02 INFO start\n10:03 ERROR timeout\n10:04 WARN slow\n10:05 ERROR connection"],
        "expected": "INFO 2\nERROR 3\nWARN 1\n",
        "code": '(set counts {})\n(set order [])\n(for-each line (split $0 "\\n")\n  (set level (array_get (split line " ") 1))\n  (if (not (in level counts)) (push order level))\n  (set counts (json_set counts [level] (add (get_or counts level 0) 1))))\n(for-each k order\n  (println (fmt "{} {}" k (json_get counts [k]))))',
    },
    {
        "desc": "Each line of arg0 is space-separated 'KEY VALUE' integer pairs. Print the SINGLE key with the largest sum of values. (If tied, the first to reach the max.)",
        "args": ["a 1\nb 5\na 2\nc 3\nb 1\na 10"],
        "expected": "a\n",
        "code": '(set sums {})\n(set order [])\n(for-each line (split $0 "\\n")\n  (set parts (split line " "))\n  (set k (first parts))\n  (set v (parse_int (last parts)))\n  (if (not (in k sums)) (push order k))\n  (set sums (json_set sums [k] (add (get_or sums k 0) v))))\n(set best "")\n(set best_sum -999999)\n(for-each k order\n  (if (gt (json_get sums [k]) best_sum)\n    (do (set best k) (set best_sum (json_get sums [k])))))\n(println best)',
    },
    {
        "desc": "Each line of arg0 is one word. Print the count of DISTINCT words as a single integer.",
        "args": ["apple\nbanana\napple\ncherry\nbanana"],
        "expected": "3\n",
        "code": '(set seen {})\n(for-each w (split $0 "\\n")\n  (set seen (json_set seen [w] true)))\n(println (len (map_keys seen)))',
    },
    {
        "desc": "Each line of arg0 is space-separated tokens. Sum the count of tokens across all lines. Print as a single integer.",
        "args": ["a b c\nd e\nf g h i\nj"],
        "expected": "10\n",
        "code": '(println (sum (map_arr (split $0 "\\n") (\\line (len (split line " "))))))',
    },
    {
        "desc": "Each line of arg0 is comma-separated 'CATEGORY,VALUE' where VALUE is an integer. Print the top-2 categories with the largest sum of VALUE, descending, formatted 'CATEGORY: SUM' one per line. Tie-break by input order of first appearance.",
        "args": ["a,5\nb,10\na,3\nc,2\nb,4\na,1\nc,8"],
        "expected": "b: 14\nc: 10\n",
        "code": '(set sums {})\n(set order [])\n(for-each line (split $0 "\\n")\n  (set parts (split line ","))\n  (set k (first parts))\n  (set v (parse_int (last parts)))\n  (if (not (in k sums)) (push order k))\n  (set sums (json_set sums [k] (add (get_or sums k 0) v))))\n(set ranked (sort_by order (\\k (sub 0 (json_get sums [k])))))\n(for-each k (slice ranked 0 2)\n  (println (fmt "{}: {}" k (json_get sums [k]))))',
    },
]

# ============================================================================
# Group E — TSV/CSV → Markdown table
# ============================================================================
GROUP_E = [
    {
        "desc": "Convert the TSV input in arg0 (with header row) to a Markdown table. Use ' | ' as separator and pipe-padded edges, and add a '| --- | --- | ... |' divider row after the header.",
        "args": ["name\tage\tcity\nalice\t30\tparis\nbob\t25\tnyc"],
        "expected": "| name | age | city |\n| --- | --- | --- |\n| alice | 30 | paris |\n| bob | 25 | nyc |\n",
        "code": '(set rows (split $0 "\\n"))\n(set header_fields (split (first rows) "\\t"))\n(println (fmt "| {} |" (join header_fields " | ")))\n(set dividers (map_arr header_fields (\\f "---")))\n(println (fmt "| {} |" (join dividers " | ")))\n(for-each row (rest rows)\n  (println (fmt "| {} |" (join (split row "\\t") " | "))))',
    },
    {
        "desc": "Convert the CSV input in arg0 (with header row) to a Markdown table. Use ' | ' as separator and pipe-padded edges, and add a '| --- | --- | ... |' divider row after the header.",
        "args": ["a,b,c\n1,2,3\n4,5,6"],
        "expected": "| a | b | c |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n",
        "code": '(set rows (split $0 "\\n"))\n(set header_fields (split (first rows) ","))\n(println (fmt "| {} |" (join header_fields " | ")))\n(set dividers (map_arr header_fields (\\f "---")))\n(println (fmt "| {} |" (join dividers " | ")))\n(for-each row (rest rows)\n  (println (fmt "| {} |" (join (split row ",") " | "))))',
    },
]


def main() -> int:
    all_seeds = GROUP_D + GROUP_E
    print(f"Verifying {len(all_seeds)} Tier 2.5 seeds...")

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
            print(f"        ok={ok} stdout={out!r}")
            print(f"        stderr={err!r}")
            print(f"        expected={s['expected']!r}")

    print(f"\n{len(verified)}/{len(all_seeds)} seeds verified.")

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
