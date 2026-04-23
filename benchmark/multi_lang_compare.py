#!/usr/bin/env python3
"""Compare Sigil token efficiency against Python, JavaScript, and Go."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import tiktoken
enc = tiktoken.get_encoding("cl100k_base")

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = str(REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe")


def count_tokens(s):
    return len(enc.encode(s))


def run(cmd, args, code, ext):
    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False) as f:
        f.write(code); f.flush()
        try:
            r = subprocess.run(cmd + [f.name] + args, capture_output=True, text=True, timeout=10)
            return r.returncode == 0, r.stdout
        finally:
            os.unlink(f.name)


def run_sigil(code, args): return run([SIGIL_BIN], args, code, ".sigil")
def run_python(code, args): return run([sys.executable], args, code, ".py")
def run_node(code, args): return run(["node"], args, code, ".js")
def run_go(code, args): return run(["go", "run"], args, code, ".go")


# 15 constructs in 4 languages each
CASES = []

CASES.append(("01_hello_world", [], "Hello, World!\n",
    '(println "Hello, World!")',
    'print("Hello, World!")',
    'console.log("Hello, World!")',
    'package main\nimport "fmt"\nfunc main() { fmt.Println("Hello, World!") }'))

CASES.append(("02_cli_int_echo", ["42"], "42\n",
    '(println #0)',
    'import sys\nprint(int(sys.argv[1]))',
    'console.log(parseInt(process.argv[2]))',
    'package main\nimport ("fmt"; "os"; "strconv")\nfunc main() { n, _ := strconv.Atoi(os.Args[1]); fmt.Println(n) }'))

CASES.append(("03_indexed_loop", ["5"], "1\n2\n3\n4\n5\n",
    '(for i 1 (add #0 1) (println i))',
    'import sys\nn = int(sys.argv[1])\nfor i in range(1, n+1):\n    print(i)',
    'const n = parseInt(process.argv[2])\nfor (let i = 1; i <= n; i++) console.log(i)',
    'package main\nimport ("fmt"; "os"; "strconv")\nfunc main() {\n    n, _ := strconv.Atoi(os.Args[1])\n    for i := 1; i <= n; i++ { fmt.Println(i) }\n}'))

CASES.append(("04_array_sum", ["1 2 3 4 5"], "15\n",
    '(println (sum (parse_ints $0)))',
    'import sys\nprint(sum(int(x) for x in sys.argv[1].split()))',
    'console.log(process.argv[2].split(" ").reduce((a,b) => a+parseInt(b), 0))',
    'package main\nimport ("fmt"; "os"; "strconv"; "strings")\nfunc main() {\n    sum := 0\n    for _, s := range strings.Fields(os.Args[1]) {\n        n, _ := strconv.Atoi(s); sum += n\n    }\n    fmt.Println(sum)\n}'))

CASES.append(("05_string_vowel_count", ["hello world"], "3\n",
    '(println (count_in (lower $0) "aeiou"))',
    'import sys\nprint(sum(1 for c in sys.argv[1].lower() if c in "aeiou"))',
    'console.log([...process.argv[2].toLowerCase()].filter(c => "aeiou".includes(c)).length)',
    'package main\nimport ("fmt"; "os"; "strings")\nfunc main() {\n    s := strings.ToLower(os.Args[1]); c := 0\n    for _, r := range s { if strings.ContainsRune("aeiou", r) { c++ } }\n    fmt.Println(c)\n}'))

CASES.append(("06_filter_evens", ["1 2 3 4 5 6"], "2 4 6\n",
    '(println (join (filter (parse_ints $0) (\\x (eq (mod x 2) 0))) " "))',
    'import sys\nnums = sys.argv[1].split()\nprint(" ".join(n for n in nums if int(n)%2==0))',
    'console.log(process.argv[2].split(" ").filter(n => parseInt(n)%2===0).join(" "))',
    'package main\nimport ("fmt"; "os"; "strconv"; "strings")\nfunc main() {\n    var r []string\n    for _, s := range strings.Fields(os.Args[1]) {\n        n, _ := strconv.Atoi(s); if n%2==0 { r = append(r, s) }\n    }\n    fmt.Println(strings.Join(r, " "))\n}'))

CASES.append(("07_word_frequency", ["the cat sat on the mat"], "cat 1\nmat 1\non 1\nsat 1\nthe 2\n",
    '(set c (map_new)) (for-each w (split $0 " ") (map_inc c w)) (for-each k (sort (map_keys c)) (println k (map_get c k)))',
    'import sys\nfrom collections import Counter\nwords = sys.argv[1].split()\nfor k in sorted(Counter(words)):\n    print(f"{k} {Counter(words)[k]}")',
    'const c = {}\nfor (const w of process.argv[2].split(" ")) c[w] = (c[w]||0)+1\nfor (const k of Object.keys(c).sort()) console.log(k, c[k])',
    'package main\nimport ("fmt"; "os"; "sort"; "strings")\nfunc main() {\n    c := map[string]int{}\n    for _, w := range strings.Fields(os.Args[1]) { c[w]++ }\n    var ks []string\n    for k := range c { ks = append(ks, k) }\n    sort.Strings(ks)\n    for _, k := range ks { fmt.Println(k, c[k]) }\n}'))

CASES.append(("08_string_build", ["Alice", "30"], "Hello, Alice! You are 30 years old.\n",
    '(set name $0) (set age $1) (println (fmt "Hello, {name}! You are {age} years old."))',
    'import sys\nprint(f"Hello, {sys.argv[1]}! You are {sys.argv[2]} years old.")',
    'console.log(`Hello, ${process.argv[2]}! You are ${process.argv[3]} years old.`)',
    'package main\nimport ("fmt"; "os")\nfunc main() { fmt.Printf("Hello, %s! You are %s years old.\\n", os.Args[1], os.Args[2]) }'))

CASES.append(("09_safe_divide", ["10", "0"], "error\n",
    '(try (println (div #0 #1)) (catch err string (println "error")))',
    'import sys\ntry:\n    a, b = int(sys.argv[1]), int(sys.argv[2])\n    print(a // b)\nexcept Exception:\n    print("error")',
    'try {\n  const a = parseInt(process.argv[2]), b = parseInt(process.argv[3])\n  if (b===0) throw new Error()\n  console.log(Math.trunc(a/b))\n} catch { console.log("error") }',
    'package main\nimport ("fmt"; "os"; "strconv")\nfunc main() {\n    a, _ := strconv.Atoi(os.Args[1]); b, _ := strconv.Atoi(os.Args[2])\n    if b == 0 { fmt.Println("error"); return }\n    fmt.Println(a / b)\n}'))

CASES.append(("10_factorial_recursive", ["5"], "120\n",
    '(fn factorial n int -> int (if (le n 1) (ret 1)) (mul n (factorial (sub n 1)))) (println (factorial #0))',
    'import sys\ndef factorial(n):\n    return 1 if n <= 1 else n * factorial(n-1)\nprint(factorial(int(sys.argv[1])))',
    'function factorial(n) { return n <= 1 ? 1 : n * factorial(n-1) }\nconsole.log(factorial(parseInt(process.argv[2])))',
    'package main\nimport ("fmt"; "os"; "strconv")\nfunc factorial(n int) int { if n <= 1 { return 1 }; return n * factorial(n-1) }\nfunc main() { n, _ := strconv.Atoi(os.Args[1]); fmt.Println(factorial(n)) }'))

CASES.append(("11_substring_find", ["hello world", "world"], "6\n",
    '(println (string_find $0 $1))',
    'import sys\nprint(sys.argv[1].find(sys.argv[2]))',
    'console.log(process.argv[2].indexOf(process.argv[3]))',
    'package main\nimport ("fmt"; "os"; "strings")\nfunc main() { fmt.Println(strings.Index(os.Args[1], os.Args[2])) }'))

CASES.append(("12_sort_ints", ["5 2 8 1 9 3"], "1 2 3 5 8 9\n",
    '(set nums (parse_ints $0)) (sort nums) (println (join nums " "))',
    'import sys\nnums = sorted(int(x) for x in sys.argv[1].split())\nprint(" ".join(str(n) for n in nums))',
    'const n = process.argv[2].split(" ").map(Number).sort((a,b)=>a-b)\nconsole.log(n.join(" "))',
    'package main\nimport ("fmt"; "os"; "sort"; "strconv"; "strings")\nfunc main() {\n    var n []int\n    for _, s := range strings.Fields(os.Args[1]) { v,_ := strconv.Atoi(s); n = append(n, v) }\n    sort.Ints(n)\n    var ss []string; for _, v := range n { ss = append(ss, strconv.Itoa(v)) }\n    fmt.Println(strings.Join(ss, " "))\n}'))

CASES.append(("13_cond_dispatch", ["3"], "March\n",
    '(set names ["January" "February" "March" "April" "May" "June" "July" "August" "September" "October" "November" "December"]) (println (get_or names (sub #0 1) "invalid"))',
    'import sys\nnames = ["January","February","March","April","May","June","July","August","September","October","November","December"]\nm = int(sys.argv[1])\nprint(names[m-1] if 1 <= m <= 12 else "invalid")',
    'const names = ["January","February","March","April","May","June","July","August","September","October","November","December"]\nconst m = parseInt(process.argv[2])\nconsole.log(m>=1 && m<=12 ? names[m-1] : "invalid")',
    'package main\nimport ("fmt"; "os"; "strconv")\nfunc main() {\n    names := []string{"January","February","March","April","May","June","July","August","September","October","November","December"}\n    m, _ := strconv.Atoi(os.Args[1])\n    if m >= 1 && m <= 12 { fmt.Println(names[m-1]) } else { fmt.Println("invalid") }\n}'))

CASES.append(("14_json_assemble", ["Alice", "30"], '{"name":"Alice","age":30}\n',
    '(set name $0) (set age #1) (println (fmt "{{\\"name\\":\\"{name}\\",\\"age\\":{age}}}"))',
    'import sys, json\nprint(json.dumps({"name": sys.argv[1], "age": int(sys.argv[2])}, separators=(",",":")))',
    'console.log(JSON.stringify({name: process.argv[2], age: parseInt(process.argv[3])}))',
    'package main\nimport ("encoding/json"; "fmt"; "os"; "strconv")\nfunc main() {\n    age, _ := strconv.Atoi(os.Args[2])\n    b, _ := json.Marshal(map[string]interface{}{"name": os.Args[1], "age": age})\n    fmt.Println(string(b))\n}'))

CASES.append(("15_http_response", ["200", "OK"], "HTTP/1.1 200 OK\n",
    '(println "HTTP/1.1" $0 $1)',
    'import sys\nprint(f"HTTP/1.1 {sys.argv[1]} {sys.argv[2]}")',
    'console.log(`HTTP/1.1 ${process.argv[2]} ${process.argv[3]}`)',
    'package main\nimport ("fmt"; "os")\nfunc main() { fmt.Printf("HTTP/1.1 %s %s\\n", os.Args[1], os.Args[2]) }'))


def main():
    print(f"{'Construct':<28} {'Sigil':>6} {'Python':>7} {'JS':>5} {'Go':>5}  | {'vs Py':>6} {'vs JS':>6} {'vs Go':>6}")
    print("-" * 95)

    totals = {"sigil": 0, "python": 0, "js": 0, "go": 0}
    valid = 0

    for name, args, expected, sigil, py, js, go in CASES:
        # Validate
        ok_s, out_s = run_sigil(sigil, args)
        ok_p, out_p = run_python(py, args)
        ok_j, out_j = run_node(js, args)
        ok_g, out_g = run_go(go, args)

        all_ok = (ok_s and out_s == expected
                  and ok_p and out_p == expected
                  and ok_j and out_j == expected
                  and ok_g and out_g == expected)

        ts = count_tokens(sigil)
        tp = count_tokens(py)
        tj = count_tokens(js)
        tg = count_tokens(go)

        if all_ok:
            valid += 1
            totals["sigil"] += ts
            totals["python"] += tp
            totals["js"] += tj
            totals["go"] += tg

        rp = ts/tp if tp else 0
        rj = ts/tj if tj else 0
        rg = ts/tg if tg else 0
        flag = "" if all_ok else "  ⚠"
        print(f"{name:<28} {ts:>6} {tp:>7} {tj:>5} {tg:>5}  | {rp:>5.2f}x {rj:>5.2f}x {rg:>5.2f}x{flag}")

    print()
    print(f"Valid: {valid}/{len(CASES)}")
    print(f"Total tokens — Sigil: {totals['sigil']}, Python: {totals['python']}, JS: {totals['js']}, Go: {totals['go']}")
    if totals['python']:
        print(f"Sigil vs Python: {totals['sigil']/totals['python']:.2f}x")
        print(f"Sigil vs JavaScript: {totals['sigil']/totals['js']:.2f}x")
        print(f"Sigil vs Go: {totals['sigil']/totals['go']:.2f}x")


if __name__ == "__main__":
    main()
