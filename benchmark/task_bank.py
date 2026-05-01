"""Task bank for corpus extension.

Each task: (id, desc, args, expected_stdout, python_ref).
Python reference acts as the ground truth. Sigil candidates are validated by
running with the same args and comparing stdout to expected.

Categories (TAG PREFIXES):
  str_  — string processing
  num_  — numbers/arithmetic
  arr_  — array ops
  map_  — map/dict ops
  ctrl_ — control flow
  cli_  — CLI utility shape
  parse_ — data parsing
  algo_ — classic algorithms
"""

TASKS = [
    # ---------------- STRING PROCESSING ---------------------------------
    {"id": "str_upper", "desc": "Uppercase the first CLI arg and print it.",
     "args": ["hello"], "expected": "HELLO\n",
     "python": "import sys\nprint(sys.argv[1].upper())"},
    {"id": "str_lower", "desc": "Lowercase the first CLI arg and print it.",
     "args": ["HELLO"], "expected": "hello\n",
     "python": "import sys\nprint(sys.argv[1].lower())"},
    {"id": "str_length", "desc": "Print the character length of the first CLI arg.",
     "args": ["hello world"], "expected": "11\n",
     "python": "import sys\nprint(len(sys.argv[1]))"},
    {"id": "str_reverse", "desc": "Print the first CLI arg reversed.",
     "args": ["abcdef"], "expected": "fedcba\n",
     "python": "import sys\nprint(sys.argv[1][::-1])"},
    {"id": "str_trim", "desc": "Trim whitespace from the first CLI arg and print.",
     "args": ["   hello   "], "expected": "hello\n",
     "python": "import sys\nprint(sys.argv[1].strip())"},
    {"id": "str_starts_with", "desc": "Print 'yes' if arg1 starts with arg2 else 'no'.",
     "args": ["hello world", "hello"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if sys.argv[1].startswith(sys.argv[2]) else 'no')"},
    {"id": "str_ends_with", "desc": "Print 'yes' if arg1 ends with arg2 else 'no'.",
     "args": ["hello world", "world"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if sys.argv[1].endswith(sys.argv[2]) else 'no')"},
    {"id": "str_replace_all", "desc": "Replace every occurrence of arg2 in arg1 with arg3.",
     "args": ["foo bar foo", "foo", "baz"], "expected": "baz bar baz\n",
     "python": "import sys\nprint(sys.argv[1].replace(sys.argv[2], sys.argv[3]))"},
    {"id": "str_word_count", "desc": "Count words (whitespace-separated) in the first CLI arg.",
     "args": ["the quick brown fox"], "expected": "4\n",
     "python": "import sys\nprint(len(sys.argv[1].split()))"},
    {"id": "str_char_at", "desc": "Print the character at index (arg2) in string (arg1).",
     "args": ["hello", "1"], "expected": "e\n",
     "python": "import sys\nprint(sys.argv[1][int(sys.argv[2])])"},
    {"id": "str_repeat_char", "desc": "Print char (arg1) repeated N (arg2) times.",
     "args": ["x", "5"], "expected": "xxxxx\n",
     "python": "import sys\nprint(sys.argv[1] * int(sys.argv[2]))"},
    {"id": "str_join_dash", "desc": "Split arg1 on spaces and rejoin with dashes.",
     "args": ["one two three"], "expected": "one-two-three\n",
     "python": "import sys\nprint('-'.join(sys.argv[1].split()))"},
    {"id": "str_acronym", "desc": "Print the uppercase first letter of each word in arg1.",
     "args": ["hello world foo bar"], "expected": "HWFB\n",
     "python": "import sys\nprint(''.join(w[0].upper() for w in sys.argv[1].split()))"},
    {"id": "str_remove_spaces", "desc": "Remove all spaces from arg1.",
     "args": ["h e l l o"], "expected": "hello\n",
     "python": "import sys\nprint(sys.argv[1].replace(' ', ''))"},
    {"id": "str_contains_digit", "desc": "Print 'yes' if arg1 contains any digit, else 'no'.",
     "args": ["abc123"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if any(c.isdigit() for c in sys.argv[1]) else 'no')"},
    {"id": "str_pad_left", "desc": "Left-pad arg1 with spaces to width arg2.",
     "args": ["42", "5"], "expected": "   42\n",
     "python": "import sys\nprint(sys.argv[1].rjust(int(sys.argv[2])))"},
    {"id": "str_pad_right", "desc": "Right-pad arg1 with spaces to width arg2.",
     "args": ["42", "5"], "expected": "42   \n",
     "python": "import sys\nprint(sys.argv[1].ljust(int(sys.argv[2])))"},
    {"id": "str_count_char", "desc": "Count occurrences of single-char arg2 in arg1.",
     "args": ["mississippi", "s"], "expected": "4\n",
     "python": "import sys\nprint(sys.argv[1].count(sys.argv[2]))"},
    {"id": "str_first_word", "desc": "Print the first word of arg1.",
     "args": ["the quick brown fox"], "expected": "the\n",
     "python": "import sys\nprint(sys.argv[1].split()[0])"},
    {"id": "str_last_word", "desc": "Print the last word of arg1.",
     "args": ["the quick brown fox"], "expected": "fox\n",
     "python": "import sys\nprint(sys.argv[1].split()[-1])"},
    {"id": "str_capitalize", "desc": "Capitalize only the first letter of arg1.",
     "args": ["hello world"], "expected": "Hello world\n",
     "python": "import sys\nprint(sys.argv[1].capitalize())"},
    {"id": "str_is_palindrome", "desc": "Print 'true' if arg1 reads same forwards/backwards, else 'false'.",
     "args": ["racecar"], "expected": "true\n",
     "python": "import sys\ns = sys.argv[1]\nprint('true' if s == s[::-1] else 'false')"},
    {"id": "str_count_words_longer", "desc": "Count words in arg1 longer than N (arg2).",
     "args": ["the quick brown fox jumped", "3"], "expected": "3\n",
     "python": "import sys\nprint(sum(1 for w in sys.argv[1].split() if len(w) > int(sys.argv[2])))"},
    {"id": "str_join_comma", "desc": "Split arg1 on spaces and rejoin with commas.",
     "args": ["a b c"], "expected": "a,b,c\n",
     "python": "import sys\nprint(','.join(sys.argv[1].split()))"},
    {"id": "str_double_each", "desc": "Print each char of arg1 twice.",
     "args": ["abc"], "expected": "aabbcc\n",
     "python": "import sys\nprint(''.join(c*2 for c in sys.argv[1]))"},

    # ---------------- NUMBERS --------------------------------------------
    {"id": "num_add", "desc": "Print the sum of two integers given as args.",
     "args": ["3", "4"], "expected": "7\n",
     "python": "import sys\nprint(int(sys.argv[1]) + int(sys.argv[2]))"},
    {"id": "num_mul", "desc": "Print the product of two integers.",
     "args": ["6", "7"], "expected": "42\n",
     "python": "import sys\nprint(int(sys.argv[1]) * int(sys.argv[2]))"},
    {"id": "num_max_of_three", "desc": "Print max of three integer args.",
     "args": ["5", "9", "3"], "expected": "9\n",
     "python": "import sys\nprint(max(int(x) for x in sys.argv[1:4]))"},
    {"id": "num_min_of_three", "desc": "Print min of three integer args.",
     "args": ["5", "9", "3"], "expected": "3\n",
     "python": "import sys\nprint(min(int(x) for x in sys.argv[1:4]))"},
    {"id": "num_abs", "desc": "Print absolute value of integer arg.",
     "args": ["-42"], "expected": "42\n",
     "python": "import sys\nprint(abs(int(sys.argv[1])))"},
    {"id": "num_square", "desc": "Print the square of integer arg.",
     "args": ["7"], "expected": "49\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint(n*n)"},
    {"id": "num_power", "desc": "Print arg1 raised to arg2 (integer power).",
     "args": ["2", "10"], "expected": "1024\n",
     "python": "import sys\nprint(int(sys.argv[1]) ** int(sys.argv[2]))"},
    {"id": "num_floor_div", "desc": "Print arg1 floor-divided by arg2.",
     "args": ["17", "5"], "expected": "3\n",
     "python": "import sys\nprint(int(sys.argv[1]) // int(sys.argv[2]))"},
    {"id": "num_mod", "desc": "Print arg1 modulo arg2.",
     "args": ["17", "5"], "expected": "2\n",
     "python": "import sys\nprint(int(sys.argv[1]) % int(sys.argv[2]))"},
    {"id": "num_is_even", "desc": "Print 'even' or 'odd' for integer arg.",
     "args": ["42"], "expected": "even\n",
     "python": "import sys\nprint('even' if int(sys.argv[1]) % 2 == 0 else 'odd')"},
    {"id": "num_is_positive", "desc": "Print 'pos', 'neg', or 'zero' for integer arg.",
     "args": ["42"], "expected": "pos\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint('pos' if n > 0 else ('neg' if n < 0 else 'zero'))"},
    {"id": "num_double", "desc": "Print arg1 doubled.",
     "args": ["21"], "expected": "42\n",
     "python": "import sys\nprint(int(sys.argv[1]) * 2)"},
    {"id": "num_half", "desc": "Print integer arg divided by 2 (floor).",
     "args": ["42"], "expected": "21\n",
     "python": "import sys\nprint(int(sys.argv[1]) // 2)"},
    {"id": "num_sum_range", "desc": "Sum integers from 1 to N (inclusive), N is arg.",
     "args": ["10"], "expected": "55\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint(sum(range(1, n+1)))"},
    {"id": "num_gcd", "desc": "Print greatest common divisor of two positive ints.",
     "args": ["12", "18"], "expected": "6\n",
     "python": "import sys\nimport math\nprint(math.gcd(int(sys.argv[1]), int(sys.argv[2])))"},
    {"id": "num_lcm", "desc": "Print least common multiple of two positive ints.",
     "args": ["4", "6"], "expected": "12\n",
     "python": "import sys\nimport math\nprint(math.lcm(int(sys.argv[1]), int(sys.argv[2])))"},
    {"id": "num_count_down", "desc": "Print integers N down to 1, one per line.",
     "args": ["5"], "expected": "5\n4\n3\n2\n1\n",
     "python": "import sys\nfor i in range(int(sys.argv[1]), 0, -1):\n    print(i)"},
    {"id": "num_is_prime", "desc": "Print 'yes' if N is prime else 'no'.",
     "args": ["13"], "expected": "yes\n",
     "python": '''import sys
n = int(sys.argv[1])
if n < 2:
    print("no")
else:
    is_p = True
    for i in range(2, int(n**0.5)+1):
        if n % i == 0:
            is_p = False; break
    print("yes" if is_p else "no")'''},

    # ---------------- ARRAY OPS ------------------------------------------
    {"id": "arr_sum", "desc": "Sum space-separated integers in arg1.",
     "args": ["1 2 3 4 5"], "expected": "15\n",
     "python": "import sys\nprint(sum(int(x) for x in sys.argv[1].split()))"},
    {"id": "arr_max", "desc": "Print max of space-separated integers.",
     "args": ["3 1 4 1 5 9 2 6"], "expected": "9\n",
     "python": "import sys\nprint(max(int(x) for x in sys.argv[1].split()))"},
    {"id": "arr_min", "desc": "Print min of space-separated integers.",
     "args": ["3 1 4 1 5 9 2 6"], "expected": "1\n",
     "python": "import sys\nprint(min(int(x) for x in sys.argv[1].split()))"},
    {"id": "arr_len", "desc": "Count space-separated tokens.",
     "args": ["a b c d e"], "expected": "5\n",
     "python": "import sys\nprint(len(sys.argv[1].split()))"},
    {"id": "arr_first", "desc": "Print first space-separated token.",
     "args": ["alpha beta gamma"], "expected": "alpha\n",
     "python": "import sys\nprint(sys.argv[1].split()[0])"},
    {"id": "arr_last", "desc": "Print last space-separated token.",
     "args": ["alpha beta gamma"], "expected": "gamma\n",
     "python": "import sys\nprint(sys.argv[1].split()[-1])"},
    {"id": "arr_sorted_asc", "desc": "Print space-separated ints sorted ascending, space-joined.",
     "args": ["5 2 8 1 9 3"], "expected": "1 2 3 5 8 9\n",
     "python": "import sys\nprint(' '.join(str(x) for x in sorted(int(x) for x in sys.argv[1].split())))"},
    {"id": "arr_sorted_desc", "desc": "Print space-separated ints sorted descending, space-joined.",
     "args": ["5 2 8 1 9 3"], "expected": "9 8 5 3 2 1\n",
     "python": "import sys\nprint(' '.join(str(x) for x in sorted((int(x) for x in sys.argv[1].split()), reverse=True)))"},
    {"id": "arr_reverse", "desc": "Reverse space-separated tokens, rejoin with spaces.",
     "args": ["a b c d"], "expected": "d c b a\n",
     "python": "import sys\nprint(' '.join(sys.argv[1].split()[::-1]))"},
    {"id": "arr_mean_int", "desc": "Print integer mean (floor) of space-separated ints.",
     "args": ["10 20 30"], "expected": "20\n",
     "python": "import sys\nxs = [int(x) for x in sys.argv[1].split()]\nprint(sum(xs)//len(xs))"},
    {"id": "arr_filter_positive", "desc": "Print only positive ints from space-separated list, space-joined.",
     "args": ["-3 5 -1 8 0 -2 7"], "expected": "5 8 7\n",
     "python": "import sys\nprint(' '.join(x for x in sys.argv[1].split() if int(x) > 0))"},
    {"id": "arr_filter_evens", "desc": "Print only even ints from space-separated list, space-joined.",
     "args": ["1 2 3 4 5 6"], "expected": "2 4 6\n",
     "python": "import sys\nprint(' '.join(x for x in sys.argv[1].split() if int(x) % 2 == 0))"},
    {"id": "arr_double_each", "desc": "Double each int in space-separated list.",
     "args": ["1 2 3 4"], "expected": "2 4 6 8\n",
     "python": "import sys\nprint(' '.join(str(int(x)*2) for x in sys.argv[1].split()))"},
    {"id": "arr_count_above", "desc": "Count how many space-separated ints are > arg2.",
     "args": ["1 5 2 8 3 9", "4"], "expected": "3\n",
     "python": "import sys\nn = int(sys.argv[2])\nprint(sum(1 for x in sys.argv[1].split() if int(x) > n))"},
    {"id": "arr_product", "desc": "Product of space-separated ints.",
     "args": ["2 3 4"], "expected": "24\n",
     "python": '''import sys
p = 1
for x in sys.argv[1].split():
    p *= int(x)
print(p)'''},
    {"id": "arr_range", "desc": "Print 0..N-1 (N is arg1), space-separated.",
     "args": ["5"], "expected": "0 1 2 3 4\n",
     "python": "import sys\nprint(' '.join(str(i) for i in range(int(sys.argv[1]))))"},
    {"id": "arr_dedupe_nums", "desc": "Remove duplicate ints from space-separated list preserving order.",
     "args": ["1 2 1 3 2 4 3"], "expected": "1 2 3 4\n",
     "python": '''import sys
seen = set(); out = []
for x in sys.argv[1].split():
    if x not in seen:
        seen.add(x); out.append(x)
print(' '.join(out))'''},
    {"id": "arr_unique_count", "desc": "Print count of unique space-separated tokens.",
     "args": ["a b a c b d a"], "expected": "4\n",
     "python": "import sys\nprint(len(set(sys.argv[1].split())))"},

    # ---------------- MAP OPS --------------------------------------------
    {"id": "map_kv_get", "desc": "Parse 'k=v,k=v' (arg1), look up arg2, print value.",
     "args": ["a=1,b=2,c=3", "b"], "expected": "2\n",
     "python": "import sys\nd = dict(kv.split('=') for kv in sys.argv[1].split(','))\nprint(d[sys.argv[2]])"},
    {"id": "map_kv_count", "desc": "Parse 'k=v,...' (arg1), print number of pairs.",
     "args": ["a=1,b=2,c=3,d=4"], "expected": "4\n",
     "python": "import sys\nd = dict(kv.split('=') for kv in sys.argv[1].split(','))\nprint(len(d))"},
    {"id": "map_kv_keys", "desc": "Parse 'k=v,...', print keys sorted, space-separated.",
     "args": ["c=3,a=1,b=2"], "expected": "a b c\n",
     "python": "import sys\nd = dict(kv.split('=') for kv in sys.argv[1].split(','))\nprint(' '.join(sorted(d)))"},
    {"id": "map_kv_has", "desc": "Parse 'k=v,...'. Print 'yes' if arg2 is a key, else 'no'.",
     "args": ["a=1,b=2", "b"], "expected": "yes\n",
     "python": "import sys\nd = dict(kv.split('=') for kv in sys.argv[1].split(','))\nprint('yes' if sys.argv[2] in d else 'no')"},
    {"id": "map_kv_sum_values", "desc": "Parse 'k=v,...' with int values, sum the values.",
     "args": ["a=1,b=2,c=3"], "expected": "6\n",
     "python": "import sys\nd = dict(kv.split('=') for kv in sys.argv[1].split(','))\nprint(sum(int(v) for v in d.values()))"},
    {"id": "map_word_freq", "desc": "Count word frequencies in arg1, print 'word:count' sorted by word asc, space-separated.",
     "args": ["the cat and the dog"], "expected": "and:1 cat:1 dog:1 the:2\n",
     "python": '''import sys
from collections import Counter
c = Counter(sys.argv[1].split())
print(' '.join(f"{k}:{c[k]}" for k in sorted(c)))'''},
    {"id": "map_char_freq", "desc": "Count char frequencies in arg1, print 'char:n' pairs sorted by char asc, space-separated.",
     "args": ["hello"], "expected": "e:1 h:1 l:2 o:1\n",
     "python": '''import sys
from collections import Counter
c = Counter(sys.argv[1])
print(' '.join(f"{k}:{c[k]}" for k in sorted(c)))'''},

    # ---------------- CONTROL FLOW ---------------------------------------
    {"id": "ctrl_if_pos", "desc": "Read int arg. If > 0 print 'positive', else 'not'.",
     "args": ["42"], "expected": "positive\n",
     "python": "import sys\nprint('positive' if int(sys.argv[1]) > 0 else 'not')"},
    {"id": "ctrl_grade", "desc": "Map integer score (0-100) to letter: 90+ A, 80+ B, 70+ C, 60+ D, else F.",
     "args": ["85"], "expected": "B\n",
     "python": '''import sys
n = int(sys.argv[1])
if n >= 90: g = "A"
elif n >= 80: g = "B"
elif n >= 70: g = "C"
elif n >= 60: g = "D"
else: g = "F"
print(g)'''},
    {"id": "ctrl_sign", "desc": "Print 1, -1, or 0 based on sign of integer arg.",
     "args": ["-7"], "expected": "-1\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint(1 if n > 0 else (-1 if n < 0 else 0))"},
    {"id": "ctrl_loop_sum_args", "desc": "Sum all integer CLI args and print.",
     "args": ["1", "2", "3", "4"], "expected": "10\n",
     "python": "import sys\nprint(sum(int(x) for x in sys.argv[1:]))"},
    {"id": "ctrl_factorial", "desc": "Compute factorial of N (arg1).",
     "args": ["6"], "expected": "720\n",
     "python": '''import sys
n = int(sys.argv[1])
r = 1
for i in range(2, n+1):
    r *= i
print(r)'''},
    {"id": "ctrl_fib", "desc": "Print Nth Fibonacci number (0-indexed, fib(0)=0, fib(1)=1).",
     "args": ["10"], "expected": "55\n",
     "python": '''import sys
n = int(sys.argv[1])
a, b = 0, 1
for _ in range(n):
    a, b = b, a+b
print(a)'''},

    # ---------------- CLI UTILITIES --------------------------------------
    {"id": "cli_echo", "desc": "Print the first CLI arg verbatim.",
     "args": ["hello"], "expected": "hello\n",
     "python": "import sys\nprint(sys.argv[1])"},
    {"id": "cli_echo_n", "desc": "Print CLI arg1 without trailing newline.",
     "args": ["hello"], "expected": "hello",
     "python": "import sys\nprint(sys.argv[1], end='')"},
    {"id": "cli_echo_all", "desc": "Print all CLI args on separate lines.",
     "args": ["a", "b", "c"], "expected": "a\nb\nc\n",
     "python": "import sys\nfor a in sys.argv[1:]:\n    print(a)"},
    {"id": "cli_arg_count", "desc": "Print number of CLI args.",
     "args": ["x", "y", "z"], "expected": "3\n",
     "python": "import sys\nprint(len(sys.argv) - 1)"},
    {"id": "cli_head_line", "desc": "Given newline-separated input in arg1, print first line.",
     "args": ["line1\nline2\nline3"], "expected": "line1\n",
     "python": "import sys\nprint(sys.argv[1].split('\\n')[0])"},
    {"id": "cli_tail_line", "desc": "Given newline-separated input in arg1, print last line.",
     "args": ["line1\nline2\nline3"], "expected": "line3\n",
     "python": "import sys\nprint(sys.argv[1].split('\\n')[-1])"},
    {"id": "cli_line_count", "desc": "Count newline-separated lines in arg1.",
     "args": ["a\nb\nc\nd"], "expected": "4\n",
     "python": "import sys\nprint(len(sys.argv[1].split('\\n')))"},

    # ---------------- DATA PARSING ---------------------------------------
    {"id": "parse_csv_row", "desc": "Arg1 is a single CSV row (comma-separated). Print field at index arg2.",
     "args": ["alice,30,paris", "1"], "expected": "30\n",
     "python": "import sys\nprint(sys.argv[1].split(',')[int(sys.argv[2])])"},
    {"id": "parse_tsv_row", "desc": "Arg1 is a tab-separated row. Print field at index arg2.",
     "args": ["alice\t30\tparis", "2"], "expected": "paris\n",
     "python": "import sys\nprint(sys.argv[1].split('\\t')[int(sys.argv[2])])"},
    {"id": "parse_csv_count", "desc": "Count fields in a single CSV row (arg1).",
     "args": ["a,b,c,d,e"], "expected": "5\n",
     "python": "import sys\nprint(len(sys.argv[1].split(',')))"},
    {"id": "parse_query_get", "desc": "Parse URL query string 'k=v&k=v' (arg1), look up arg2, print value.",
     "args": ["a=1&b=2&c=3", "b"], "expected": "2\n",
     "python": "import sys\nd = dict(p.split('=') for p in sys.argv[1].split('&'))\nprint(d[sys.argv[2]])"},
    {"id": "parse_csv_col_sum", "desc": "Rows separated by ';', fields by ','. Sum column at index arg2 (as int).",
     "args": ["1,10;2,20;3,30", "1"], "expected": "60\n",
     "python": "import sys\nn = int(sys.argv[2])\nprint(sum(int(r.split(',')[n]) for r in sys.argv[1].split(';')))"},
    {"id": "parse_number_extract", "desc": "Given arg1, extract all digits as one string and print.",
     "args": ["abc123def456"], "expected": "123456\n",
     "python": "import sys\nprint(''.join(c for c in sys.argv[1] if c.isdigit()))"},

    # ---------------- ALGORITHMS -----------------------------------------
    {"id": "algo_sum_of_squares", "desc": "Sum of squares of integers 1..N (arg1).",
     "args": ["5"], "expected": "55\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint(sum(i*i for i in range(1, n+1)))"},
    {"id": "algo_count_primes_below", "desc": "Count primes less than N (arg1).",
     "args": ["20"], "expected": "8\n",
     "python": '''import sys
n = int(sys.argv[1])
count = 0
for k in range(2, n):
    is_p = True
    for i in range(2, int(k**0.5)+1):
        if k % i == 0:
            is_p = False; break
    if is_p: count += 1
print(count)'''},
    {"id": "algo_digit_count", "desc": "Count digits in a non-negative int (arg1).",
     "args": ["12345"], "expected": "5\n",
     "python": "import sys\nprint(len(sys.argv[1]))"},
    {"id": "algo_sum_digits", "desc": "Sum the digits of a non-negative int (arg1).",
     "args": ["12345"], "expected": "15\n",
     "python": "import sys\nprint(sum(int(d) for d in sys.argv[1]))"},
    {"id": "algo_reverse_int", "desc": "Print digits of arg1 integer reversed (as a string).",
     "args": ["12345"], "expected": "54321\n",
     "python": "import sys\nprint(sys.argv[1][::-1])"},
    {"id": "algo_count_set_bits", "desc": "Count set bits in binary rep of int arg1.",
     "args": ["255"], "expected": "8\n",
     "python": "import sys\nprint(bin(int(sys.argv[1])).count('1'))"},
    {"id": "algo_to_binary", "desc": "Print binary representation of positive int arg (no '0b' prefix).",
     "args": ["13"], "expected": "1101\n",
     "python": "import sys\nprint(bin(int(sys.argv[1]))[2:])"},
    {"id": "algo_to_hex", "desc": "Print lowercase hex representation of positive int arg (no '0x' prefix).",
     "args": ["255"], "expected": "ff\n",
     "python": "import sys\nprint(hex(int(sys.argv[1]))[2:])"},

    # ---------------- MORE STRING ----------------------------------------
    {"id": "str_titlecase", "desc": "Title-case each word in arg1.",
     "args": ["hello world foo"], "expected": "Hello World Foo\n",
     "python": "import sys\nprint(' '.join(w.capitalize() for w in sys.argv[1].split()))"},
    {"id": "str_swapcase", "desc": "Swap case of every letter in arg1.",
     "args": ["Hello World"], "expected": "hELLO wORLD\n",
     "python": "import sys\nprint(sys.argv[1].swapcase())"},
    {"id": "str_remove_vowels", "desc": "Remove all vowels (aeiouAEIOU) from arg1.",
     "args": ["Hello World"], "expected": "Hll Wrld\n",
     "python": "import sys\nprint(''.join(c for c in sys.argv[1] if c not in 'aeiouAEIOU'))"},
    {"id": "str_only_digits", "desc": "Keep only digits from arg1.",
     "args": ["abc123def456"], "expected": "123456\n",
     "python": "import sys\nprint(''.join(c for c in sys.argv[1] if c.isdigit()))"},
    {"id": "str_only_letters", "desc": "Keep only ASCII letters from arg1.",
     "args": ["abc123def456"], "expected": "abcdef\n",
     "python": "import sys\nprint(''.join(c for c in sys.argv[1] if c.isalpha()))"},
    {"id": "str_index_of", "desc": "Print index of arg2 in arg1, or -1 if not present.",
     "args": ["hello world", "world"], "expected": "6\n",
     "python": "import sys\nprint(sys.argv[1].find(sys.argv[2]))"},
    {"id": "str_nth_char", "desc": "Print the arg2-th character (0-indexed) of arg1.",
     "args": ["hello", "4"], "expected": "o\n",
     "python": "import sys\nprint(sys.argv[1][int(sys.argv[2])])"},
    {"id": "str_split_nth", "desc": "Split arg1 by spaces and print the arg2-th token (0-indexed).",
     "args": ["alpha beta gamma delta", "2"], "expected": "gamma\n",
     "python": "import sys\nprint(sys.argv[1].split()[int(sys.argv[2])])"},

    # ---------------- MORE NUMBERS ---------------------------------------
    {"id": "num_clamp", "desc": "Clamp arg1 between arg2 (min) and arg3 (max), print result.",
     "args": ["15", "0", "10"], "expected": "10\n",
     "python": "import sys\na,lo,hi = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])\nprint(max(lo, min(hi, a)))"},
    {"id": "num_average_float", "desc": "Average of space-separated ints, printed as float with 2 decimal places.",
     "args": ["1 2 3 4"], "expected": "2.50\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
print(f"{sum(xs)/len(xs):.2f}")'''},
    {"id": "num_decimal_add", "desc": "Add two floats, print with 2 decimals.",
     "args": ["1.5", "2.75"], "expected": "4.25\n",
     "python": "import sys\nprint(f\"{float(sys.argv[1]) + float(sys.argv[2]):.2f}\")"},
    {"id": "num_percent_of", "desc": "Print arg1 as percent of arg2 (integer, floor).",
     "args": ["25", "100"], "expected": "25\n",
     "python": "import sys\nprint((int(sys.argv[1])*100)//int(sys.argv[2]))"},
    {"id": "num_round_to_int", "desc": "Round float arg to nearest int and print.",
     "args": ["3.7"], "expected": "4\n",
     "python": "import sys\nprint(round(float(sys.argv[1])))"},
    {"id": "num_count_digits", "desc": "Count digits of int arg (assume positive).",
     "args": ["123456"], "expected": "6\n",
     "python": "import sys\nprint(len(sys.argv[1]))"},
    {"id": "num_is_power_of_two", "desc": "Print 'yes' if positive int arg is a power of 2, else 'no'.",
     "args": ["16"], "expected": "yes\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint('yes' if n > 0 and (n & (n-1)) == 0 else 'no')"},

    # ---------------- MORE ARRAY -----------------------------------------
    {"id": "arr_cumsum", "desc": "Print prefix sums of space-separated ints, space-joined.",
     "args": ["1 2 3 4"], "expected": "1 3 6 10\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
acc = 0; out = []
for x in xs:
    acc += x; out.append(str(acc))
print(' '.join(out))'''},
    {"id": "arr_take_n", "desc": "Take first N (arg2) tokens from space-separated arg1, space-joined.",
     "args": ["a b c d e f", "3"], "expected": "a b c\n",
     "python": "import sys\nprint(' '.join(sys.argv[1].split()[:int(sys.argv[2])]))"},
    {"id": "arr_drop_n", "desc": "Drop first N (arg2) tokens from space-separated arg1, space-joined.",
     "args": ["a b c d e f", "2"], "expected": "c d e f\n",
     "python": "import sys\nprint(' '.join(sys.argv[1].split()[int(sys.argv[2]):]))"},
    {"id": "arr_has_elem", "desc": "Print 'yes' if arg2 is one of the space-separated tokens in arg1.",
     "args": ["a b c d", "c"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if sys.argv[2] in sys.argv[1].split() else 'no')"},
    {"id": "arr_zip_add", "desc": "Arg1 and arg2 are space-separated ints of same length. Print element-wise sum.",
     "args": ["1 2 3", "10 20 30"], "expected": "11 22 33\n",
     "python": "import sys\na = [int(x) for x in sys.argv[1].split()]\nb = [int(x) for x in sys.argv[2].split()]\nprint(' '.join(str(x+y) for x,y in zip(a,b)))"},
    {"id": "arr_is_sorted", "desc": "Print 'yes' if space-separated ints are sorted ascending, else 'no'.",
     "args": ["1 2 3 4 5"], "expected": "yes\n",
     "python": "import sys\nxs = [int(x) for x in sys.argv[1].split()]\nprint('yes' if xs == sorted(xs) else 'no')"},
    {"id": "arr_median", "desc": "Print median of space-separated ints (for even counts, lower middle).",
     "args": ["3 1 4 1 5"], "expected": "3\n",
     "python": "import sys\nxs = sorted(int(x) for x in sys.argv[1].split())\nprint(xs[len(xs)//2])"},
    {"id": "arr_all_positive", "desc": "Print 'yes' if all space-separated ints are > 0, else 'no'.",
     "args": ["1 2 3 4"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if all(int(x) > 0 for x in sys.argv[1].split()) else 'no')"},
    {"id": "arr_any_negative", "desc": "Print 'yes' if any space-separated int is < 0, else 'no'.",
     "args": ["1 -2 3"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if any(int(x) < 0 for x in sys.argv[1].split()) else 'no')"},
    {"id": "arr_concat", "desc": "Concatenate two space-separated lists (arg1 then arg2), space-joined.",
     "args": ["a b c", "d e f"], "expected": "a b c d e f\n",
     "python": "import sys\nprint(sys.argv[1] + ' ' + sys.argv[2])"},
    {"id": "arr_index_of_val", "desc": "Print 0-based index of int arg2 in space-separated arg1, or -1 if absent.",
     "args": ["5 2 8 1 9", "8"], "expected": "2\n",
     "python": '''import sys
xs = sys.argv[1].split()
target = sys.argv[2]
for i, v in enumerate(xs):
    if v == target:
        print(i); break
else:
    print(-1)'''},

    # ---------------- MORE ALGOS -----------------------------------------
    {"id": "algo_linear_search", "desc": "Return 0-based index of first occurrence of arg2 in space-separated arg1, -1 if absent.",
     "args": ["apple banana cherry date", "cherry"], "expected": "2\n",
     "python": '''import sys
xs = sys.argv[1].split()
target = sys.argv[2]
for i, v in enumerate(xs):
    if v == target:
        print(i); break
else:
    print(-1)'''},
    {"id": "algo_min_subarr", "desc": "Given space-separated ints, print min. Use a loop not max()/min().",
     "args": ["7 3 9 2 8"], "expected": "2\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
m = xs[0]
for x in xs[1:]:
    if x < m: m = x
print(m)'''},
    {"id": "algo_str_count_word", "desc": "Count occurrences of word arg2 in space-separated arg1.",
     "args": ["the cat sat on the mat", "the"], "expected": "2\n",
     "python": "import sys\nprint(sum(1 for w in sys.argv[1].split() if w == sys.argv[2]))"},
    {"id": "algo_longest_line", "desc": "Given newline-separated lines in arg1, print length of longest line.",
     "args": ["hi\nhello\nhey"], "expected": "5\n",
     "python": "import sys\nprint(max(len(line) for line in sys.argv[1].split('\\n')))"},
    {"id": "algo_str_pairs", "desc": "For arg1 of even length, split into 2-char pairs, space-joined.",
     "args": ["abcdef"], "expected": "ab cd ef\n",
     "python": '''import sys
s = sys.argv[1]
out = [s[i:i+2] for i in range(0, len(s), 2)]
print(' '.join(out))'''},

    # ---------------- MORE CLI -------------------------------------------
    {"id": "cli_greet", "desc": "Print 'Hello, NAME!' where NAME is arg1.",
     "args": ["Alice"], "expected": "Hello, Alice!\n",
     "python": "import sys\nprint(f'Hello, {sys.argv[1]}!')"},
    {"id": "cli_json_pair", "desc": "Print JSON object {\"key\":\"VAL1\",\"val\":VAL2} where VAL1=arg1, VAL2=int(arg2).",
     "args": ["foo", "42"], "expected": '{"key":"foo","val":42}\n',
     "python": '''import sys
print(f'{{"key":"{sys.argv[1]}","val":{int(sys.argv[2])}}}')'''},
    {"id": "cli_bool_flag", "desc": "If arg1 is 'true' print 'on', otherwise 'off'.",
     "args": ["true"], "expected": "on\n",
     "python": "import sys\nprint('on' if sys.argv[1] == 'true' else 'off')"},
    {"id": "cli_print_args_commas", "desc": "Print all CLI args joined by commas.",
     "args": ["a", "b", "c"], "expected": "a,b,c\n",
     "python": "import sys\nprint(','.join(sys.argv[1:]))"},
    {"id": "cli_usage_missing", "desc": "If no args given, print 'usage: <name>'. Otherwise print 'hello NAME'.",
     "args": ["Alice"], "expected": "hello Alice\n",
     "python": "import sys\nprint('usage: <name>' if len(sys.argv) < 2 else f'hello {sys.argv[1]}')"},

    # ---------------- HIGHER-ORDER / LAMBDAS -----------------------------
    {"id": "hof_map_square", "desc": "Square each space-separated int, print space-separated.",
     "args": ["1 2 3 4"], "expected": "1 4 9 16\n",
     "python": "import sys\nprint(' '.join(str(int(x)**2) for x in sys.argv[1].split()))"},
    {"id": "hof_map_add_n", "desc": "Add arg2 (int) to each space-separated int in arg1, space-joined.",
     "args": ["1 2 3", "10"], "expected": "11 12 13\n",
     "python": "import sys\nn = int(sys.argv[2])\nprint(' '.join(str(int(x)+n) for x in sys.argv[1].split()))"},
    {"id": "hof_filter_longer", "desc": "Print space-separated words in arg1 longer than N (arg2), space-joined.",
     "args": ["the quick brown fox", "3"], "expected": "quick brown\n",
     "python": "import sys\nn = int(sys.argv[2])\nprint(' '.join(w for w in sys.argv[1].split() if len(w) > n))"},
    {"id": "hof_filter_contains", "desc": "Keep space-separated words in arg1 that contain arg2.",
     "args": ["apple banana cherry date", "a"], "expected": "apple banana date\n",
     "python": "import sys\nprint(' '.join(w for w in sys.argv[1].split() if sys.argv[2] in w))"},
    {"id": "hof_reduce_max", "desc": "Find max of space-separated ints using reduce-like fold.",
     "args": ["3 1 4 1 5 9 2 6"], "expected": "9\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
m = xs[0]
for x in xs[1:]:
    if x > m: m = x
print(m)'''},
    {"id": "hof_count_matches", "desc": "Count words in arg1 that equal arg2.",
     "args": ["the cat the dog the mat", "the"], "expected": "3\n",
     "python": "import sys\nprint(sum(1 for w in sys.argv[1].split() if w == sys.argv[2]))"},
    {"id": "hof_any_short", "desc": "Print 'yes' if any space-separated word in arg1 has length <= 2, else 'no'.",
     "args": ["to be or not to be"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if any(len(w) <= 2 for w in sys.argv[1].split()) else 'no')"},
    {"id": "hof_all_unique", "desc": "Print 'yes' if all space-separated tokens are unique, else 'no'.",
     "args": ["a b c d e"], "expected": "yes\n",
     "python": "import sys\nxs = sys.argv[1].split()\nprint('yes' if len(set(xs)) == len(xs) else 'no')"},
    {"id": "hof_compose_len", "desc": "Print total character count of all words in arg1 (excluding spaces).",
     "args": ["hello world foo"], "expected": "13\n",
     "python": "import sys\nprint(sum(len(w) for w in sys.argv[1].split()))"},

    # ---------------- NEW BUILTINS (counter, sort_by, entries, etc.) -----
    {"id": "bi_counter_top", "desc": "Count word frequencies in arg1; print most common word.",
     "args": ["the cat the dog the mat"], "expected": "the\n",
     "python": '''import sys
from collections import Counter
c = Counter(sys.argv[1].split())
print(c.most_common(1)[0][0])'''},
    {"id": "bi_counter_sum", "desc": "Sum all counts from a word-frequency of arg1 (should equal word count).",
     "args": ["a b a c b"], "expected": "5\n",
     "python": '''import sys
from collections import Counter
print(sum(Counter(sys.argv[1].split()).values()))'''},
    {"id": "bi_sort_by_len", "desc": "Sort space-separated words by length ascending, tie-break unspecified; print space-joined.",
     "args": ["apple bee cherry"], "expected": "bee apple cherry\n",
     "python": "import sys\nwords = sorted(sys.argv[1].split(), key=len)\nprint(' '.join(words))"},
    {"id": "bi_enumerate_pairs", "desc": "Print 'i:word' pairs for each word in arg1 (0-indexed), space-separated.",
     "args": ["a b c"], "expected": "0:a 1:b 2:c\n",
     "python": "import sys\nprint(' '.join(f'{i}:{w}' for i, w in enumerate(sys.argv[1].split())))"},
    {"id": "bi_scan_cumsum", "desc": "Print running sum (cumulative) of space-separated ints, space-joined.",
     "args": ["1 2 3 4 5"], "expected": "1 3 6 10 15\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
acc = 0; out = []
for x in xs:
    acc += x; out.append(str(acc))
print(' '.join(out))'''},
    {"id": "bi_range_join", "desc": "Print 1..N (inclusive), comma-separated.",
     "args": ["5"], "expected": "1,2,3,4,5\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint(','.join(str(i) for i in range(1, n+1)))"},
    {"id": "bi_uniq_order", "desc": "Deduplicate space-separated tokens preserving order, space-joined.",
     "args": ["a b a c b d"], "expected": "a b c d\n",
     "python": '''import sys
seen = set(); out = []
for x in sys.argv[1].split():
    if x not in seen:
        seen.add(x); out.append(x)
print(' '.join(out))'''},
    {"id": "bi_slice_middle", "desc": "Slice space-separated tokens from index arg2 to arg3 (exclusive), space-joined.",
     "args": ["a b c d e f", "1", "4"], "expected": "b c d\n",
     "python": "import sys\nxs = sys.argv[1].split()\nprint(' '.join(xs[int(sys.argv[2]):int(sys.argv[3])]))"},
    {"id": "bi_diff_sets", "desc": "Print words in arg1 but not in arg2, space-separated, preserving order of arg1.",
     "args": ["a b c d", "b d"], "expected": "a c\n",
     "python": '''import sys
a = sys.argv[1].split(); b = set(sys.argv[2].split())
print(' '.join(w for w in a if w not in b))'''},
    {"id": "bi_inter_sets", "desc": "Print words in both arg1 and arg2, in order of arg1, space-separated.",
     "args": ["a b c d", "b d e"], "expected": "b d\n",
     "python": '''import sys
a = sys.argv[1].split(); b = set(sys.argv[2].split())
print(' '.join(w for w in a if w in b))'''},
    {"id": "bi_union_sets", "desc": "Union of two space-separated word lists, preserving first-seen order, space-joined.",
     "args": ["a b c", "b c d e"], "expected": "a b c d e\n",
     "python": '''import sys
seen = set(); out = []
for w in sys.argv[1].split() + sys.argv[2].split():
    if w not in seen:
        seen.add(w); out.append(w)
print(' '.join(out))'''},
    {"id": "bi_merge_maps", "desc": "Parse two 'k=v,...' args, merge (arg2 overrides arg1), print 'k=v' sorted by key, comma-joined.",
     "args": ["a=1,b=2,c=3", "b=20,d=4"], "expected": "a=1,b=20,c=3,d=4\n",
     "python": '''import sys
def p(s): return dict(kv.split('=') for kv in s.split(','))
d = p(sys.argv[1]); d.update(p(sys.argv[2]))
print(','.join(f'{k}={d[k]}' for k in sorted(d)))'''},
    {"id": "bi_fmt_float_2dp", "desc": "Print float arg1 with exactly 2 decimal places.",
     "args": ["3.14159"], "expected": "3.14\n",
     "python": "import sys\nprint(f'{float(sys.argv[1]):.2f}')"},

    # ---------------- MORE STRING EDGE CASES -----------------------------
    {"id": "str_empty_check", "desc": "Print 'empty' if arg1 is empty string, else 'nonempty'.",
     "args": [""], "expected": "empty\n",
     "python": "import sys\nprint('empty' if sys.argv[1] == '' else 'nonempty')"},
    {"id": "str_char_codes", "desc": "Print ASCII codes of each char in arg1, space-separated.",
     "args": ["ABC"], "expected": "65 66 67\n",
     "python": "import sys\nprint(' '.join(str(ord(c)) for c in sys.argv[1]))"},
    {"id": "str_word_lengths", "desc": "For each word in arg1, print its length, space-separated.",
     "args": ["hi hello world"], "expected": "2 5 5\n",
     "python": "import sys\nprint(' '.join(str(len(w)) for w in sys.argv[1].split()))"},
    {"id": "str_reverse_words", "desc": "Reverse the ORDER of words in arg1 (not chars), space-joined.",
     "args": ["hello world foo"], "expected": "foo world hello\n",
     "python": "import sys\nprint(' '.join(reversed(sys.argv[1].split())))"},
    {"id": "str_sort_words", "desc": "Sort words in arg1 alphabetically, space-joined.",
     "args": ["banana apple cherry"], "expected": "apple banana cherry\n",
     "python": "import sys\nprint(' '.join(sorted(sys.argv[1].split())))"},
    {"id": "str_extract_caps", "desc": "Extract uppercase letters from arg1 and concat.",
     "args": ["Hello World Foo Bar"], "expected": "HWFB\n",
     "python": "import sys\nprint(''.join(c for c in sys.argv[1] if c.isupper()))"},
    {"id": "str_abbrev", "desc": "Print first and last char of arg1 separated by a dash.",
     "args": ["hello"], "expected": "h-o\n",
     "python": "import sys\ns = sys.argv[1]\nprint(f'{s[0]}-{s[-1]}')"},
    {"id": "str_is_numeric", "desc": "Print 'yes' if arg1 contains only digits, else 'no'.",
     "args": ["12345"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if sys.argv[1].isdigit() else 'no')"},
    {"id": "str_longest_word_in", "desc": "Print the longest word in sentence arg1 (first one wins on ties).",
     "args": ["the quick brown fox"], "expected": "quick\n",
     "python": '''import sys
words = sys.argv[1].split()
best = words[0]
for w in words[1:]:
    if len(w) > len(best): best = w
print(best)'''},
    {"id": "str_repeat_word", "desc": "Repeat word arg1 N (arg2) times with no separator.",
     "args": ["ab", "3"], "expected": "ababab\n",
     "python": "import sys\nprint(sys.argv[1] * int(sys.argv[2]))"},
    {"id": "str_interleave", "desc": "Interleave chars of arg1 and arg2 (same length assumed).",
     "args": ["ace", "bdf"], "expected": "abcdef\n",
     "python": "import sys\nprint(''.join(a+b for a, b in zip(sys.argv[1], sys.argv[2])))"},
    {"id": "str_fizzbuzz_line", "desc": "For N (arg1 int): print 'Fizz' if N%3==0 and N%5!=0, 'Buzz' if N%5==0 and N%3!=0, 'FizzBuzz' if both, else N.",
     "args": ["15"], "expected": "FizzBuzz\n",
     "python": '''import sys
n = int(sys.argv[1])
if n % 15 == 0: print("FizzBuzz")
elif n % 3 == 0: print("Fizz")
elif n % 5 == 0: print("Buzz")
else: print(n)'''},

    # ---------------- MORE NUMBERS / MATH --------------------------------
    {"id": "math_sum_evens_to", "desc": "Sum all even numbers from 1 to N (inclusive).",
     "args": ["10"], "expected": "30\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint(sum(i for i in range(1, n+1) if i % 2 == 0))"},
    {"id": "math_sum_odds_to", "desc": "Sum all odd numbers from 1 to N (inclusive).",
     "args": ["10"], "expected": "25\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint(sum(i for i in range(1, n+1) if i % 2 == 1))"},
    {"id": "math_sum_multiples", "desc": "Sum integers 1..N that are multiples of arg2.",
     "args": ["20", "3"], "expected": "63\n",
     "python": "import sys\nn, k = int(sys.argv[1]), int(sys.argv[2])\nprint(sum(i for i in range(1, n+1) if i % k == 0))"},
    {"id": "math_digit_sum", "desc": "Sum the digits of a positive int (arg1).",
     "args": ["9876"], "expected": "30\n",
     "python": "import sys\nprint(sum(int(d) for d in sys.argv[1]))"},
    {"id": "math_count_trailing_zeros", "desc": "Count trailing zeros in positive int (arg1).",
     "args": ["12300"], "expected": "2\n",
     "python": "import sys\ns = sys.argv[1]\nc = 0\nfor ch in reversed(s):\n    if ch == '0': c += 1\n    else: break\nprint(c)"},
    {"id": "math_perfect_square", "desc": "Print 'yes' if arg1 is a perfect square, else 'no'.",
     "args": ["144"], "expected": "yes\n",
     "python": "import sys\nn = int(sys.argv[1])\nr = int(n**0.5)\nprint('yes' if r*r == n else 'no')"},
    {"id": "math_triangle_num", "desc": "Nth triangular number (1+2+...+N).",
     "args": ["7"], "expected": "28\n",
     "python": "import sys\nn = int(sys.argv[1])\nprint(n*(n+1)//2)"},
    {"id": "math_hypot_int", "desc": "Given legs a and b, print integer hypotenuse if perfect (a^2+b^2=c^2), else -1.",
     "args": ["3", "4"], "expected": "5\n",
     "python": '''import sys
a, b = int(sys.argv[1]), int(sys.argv[2])
s = a*a + b*b
r = int(s**0.5)
print(r if r*r == s else -1)'''},
    {"id": "math_bin_to_int", "desc": "Convert binary string (arg1) to decimal integer.",
     "args": ["1101"], "expected": "13\n",
     "python": "import sys\nprint(int(sys.argv[1], 2))"},
    {"id": "math_dec_to_bin", "desc": "Convert non-negative decimal int (arg1) to binary string (no prefix).",
     "args": ["13"], "expected": "1101\n",
     "python": "import sys\nprint(bin(int(sys.argv[1]))[2:])"},
    {"id": "math_octal_to_int", "desc": "Convert octal string (arg1) to decimal integer.",
     "args": ["17"], "expected": "15\n",
     "python": "import sys\nprint(int(sys.argv[1], 8))"},
    {"id": "math_seconds_to_hms", "desc": "Given seconds (arg1), print 'H:MM:SS' (no padding on hours).",
     "args": ["3723"], "expected": "1:02:03\n",
     "python": '''import sys
s = int(sys.argv[1])
h = s // 3600; m = (s % 3600) // 60; sec = s % 60
print(f"{h}:{m:02d}:{sec:02d}")'''},
    {"id": "math_kilos_to_miles", "desc": "Convert km (float arg1) to miles with 2 decimals (1 km = 0.621371 mi).",
     "args": ["10"], "expected": "6.21\n",
     "python": "import sys\nprint(f'{float(sys.argv[1]) * 0.621371:.2f}')"},

    # ---------------- 2D DATA / GRIDS ------------------------------------
    {"id": "grid_row_count", "desc": "Rows separated by ';', count rows in arg1.",
     "args": ["1,2;3,4;5,6"], "expected": "3\n",
     "python": "import sys\nprint(len(sys.argv[1].split(';')))"},
    {"id": "grid_col_count", "desc": "Rows separated by ';', fields by ','. Print field count of first row.",
     "args": ["1,2,3;4,5,6"], "expected": "3\n",
     "python": "import sys\nprint(len(sys.argv[1].split(';')[0].split(',')))"},
    {"id": "grid_sum_all", "desc": "Rows ';'-separated, fields ','-separated, sum all integer cells.",
     "args": ["1,2;3,4;5,6"], "expected": "21\n",
     "python": '''import sys
total = 0
for r in sys.argv[1].split(';'):
    for v in r.split(','):
        total += int(v)
print(total)'''},
    {"id": "grid_row_sum", "desc": "Rows ';'-separated, fields ','-separated. Print sum of row at index arg2.",
     "args": ["1,2,3;4,5,6;7,8,9", "1"], "expected": "15\n",
     "python": "import sys\nrow = sys.argv[1].split(';')[int(sys.argv[2])]\nprint(sum(int(v) for v in row.split(',')))"},
    {"id": "grid_get_cell", "desc": "Grid like '1,2;3,4'. Print cell at row arg2, col arg3.",
     "args": ["1,2;3,4;5,6", "1", "0"], "expected": "3\n",
     "python": "import sys\ng = [r.split(',') for r in sys.argv[1].split(';')]\nprint(g[int(sys.argv[2])][int(sys.argv[3])])"},
    {"id": "grid_col_sum", "desc": "Grid like '1,2;3,4'. Sum column at index arg2.",
     "args": ["1,2,3;4,5,6;7,8,9", "1"], "expected": "15\n",
     "python": "import sys\ng = [r.split(',') for r in sys.argv[1].split(';')]\nc = int(sys.argv[2])\nprint(sum(int(r[c]) for r in g))"},
    {"id": "grid_max_in_row", "desc": "Grid like '1,2;3,4'. Print max value in row at index arg2.",
     "args": ["1,5,3;7,2,8;4,6,9", "1"], "expected": "8\n",
     "python": "import sys\nrow = sys.argv[1].split(';')[int(sys.argv[2])]\nprint(max(int(v) for v in row.split(',')))"},

    # ---------------- STATS ----------------------------------------------
    {"id": "stats_mean", "desc": "Arithmetic mean of space-separated ints, 2 decimal places.",
     "args": ["1 2 3 4 5"], "expected": "3.00\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
print(f"{sum(xs)/len(xs):.2f}")'''},
    {"id": "stats_median_odd", "desc": "Median of odd-count space-separated ints (sort and take middle).",
     "args": ["3 1 4 1 5"], "expected": "3\n",
     "python": "import sys\nxs = sorted(int(x) for x in sys.argv[1].split())\nprint(xs[len(xs)//2])"},
    {"id": "stats_range", "desc": "Range (max - min) of space-separated ints.",
     "args": ["3 1 4 1 5 9 2"], "expected": "8\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
print(max(xs) - min(xs))'''},
    {"id": "stats_mode_simple", "desc": "Most-frequent int in space-separated list (ties: smallest wins).",
     "args": ["1 2 2 3 3 3"], "expected": "3\n",
     "python": '''import sys
from collections import Counter
c = Counter(sys.argv[1].split())
best = max(c.items(), key=lambda kv: (kv[1], -int(kv[0])))[0]
print(best)'''},
    {"id": "stats_variance_simple", "desc": "Variance (population) of space-separated ints rounded to 2 decimals.",
     "args": ["2 4 4 4 5 5 7 9"], "expected": "4.00\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
m = sum(xs)/len(xs)
v = sum((x-m)**2 for x in xs) / len(xs)
print(f"{v:.2f}")'''},

    # ---------------- PARSING / PROTOCOLS --------------------------------
    {"id": "parse_http_method", "desc": "Given 'GET /path HTTP/1.1' (arg1), print the method.",
     "args": ["GET /index.html HTTP/1.1"], "expected": "GET\n",
     "python": "import sys\nprint(sys.argv[1].split()[0])"},
    {"id": "parse_http_path", "desc": "Given 'METHOD /path HTTP/1.1', print the path.",
     "args": ["POST /api/users HTTP/1.1"], "expected": "/api/users\n",
     "python": "import sys\nprint(sys.argv[1].split()[1])"},
    {"id": "parse_email_domain", "desc": "Given 'user@domain.tld' (arg1), print the domain (after @).",
     "args": ["alice@example.com"], "expected": "example.com\n",
     "python": "import sys\nprint(sys.argv[1].split('@')[1])"},
    {"id": "parse_email_user", "desc": "Given 'user@domain' (arg1), print the user part (before @).",
     "args": ["alice@example.com"], "expected": "alice\n",
     "python": "import sys\nprint(sys.argv[1].split('@')[0])"},
    {"id": "parse_path_basename", "desc": "Given '/a/b/c/file.txt' (arg1), print just 'file.txt'.",
     "args": ["/home/user/docs/report.pdf"], "expected": "report.pdf\n",
     "python": "import sys\nprint(sys.argv[1].split('/')[-1])"},
    {"id": "parse_path_dirname", "desc": "Given '/a/b/c/file.txt', print '/a/b/c'.",
     "args": ["/home/user/docs/report.pdf"], "expected": "/home/user/docs\n",
     "python": '''import sys
parts = sys.argv[1].split('/')
print('/'.join(parts[:-1]))'''},
    {"id": "parse_file_extension", "desc": "Given filename (arg1), print extension (after last '.'). Empty if none.",
     "args": ["report.pdf"], "expected": "pdf\n",
     "python": '''import sys
s = sys.argv[1]
i = s.rfind('.')
print(s[i+1:] if i >= 0 else "")'''},
    {"id": "parse_version_major", "desc": "Given version like '1.2.3', print the major component.",
     "args": ["3.14.159"], "expected": "3\n",
     "python": "import sys\nprint(sys.argv[1].split('.')[0])"},
    {"id": "parse_env_var", "desc": "Parse 'NAME=VALUE' (arg1), print NAME.",
     "args": ["PATH=/usr/bin:/bin"], "expected": "PATH\n",
     "python": "import sys\nprint(sys.argv[1].split('=')[0])"},
    {"id": "parse_log_level", "desc": "Given '[LEVEL] message' (arg1), print LEVEL.",
     "args": ["[INFO] server started"], "expected": "INFO\n",
     "python": '''import sys
s = sys.argv[1]
a = s.find('['); b = s.find(']')
print(s[a+1:b])'''},
    {"id": "parse_count_rows", "desc": "Count newline-separated rows in arg1.",
     "args": ["a\nb\nc\nd\ne"], "expected": "5\n",
     "python": "import sys\nprint(len(sys.argv[1].split('\\n')))"},
    {"id": "parse_semicolon_split", "desc": "Split arg1 on ';', print fields one per line.",
     "args": ["a;b;c"], "expected": "a\nb\nc\n",
     "python": "import sys\nfor f in sys.argv[1].split(';'):\n    print(f)"},
    {"id": "parse_flag_detect", "desc": "If any arg starts with '--', print 'flags present', else 'no flags'.",
     "args": ["--verbose", "file.txt"], "expected": "flags present\n",
     "python": "import sys\nprint('flags present' if any(a.startswith('--') for a in sys.argv[1:]) else 'no flags')"},

    # ---------------- VALIDATION / PREDICATES ----------------------------
    {"id": "valid_has_upper", "desc": "Print 'yes' if arg1 contains any uppercase letter, else 'no'.",
     "args": ["Hello"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if any(c.isupper() for c in sys.argv[1]) else 'no')"},
    {"id": "valid_has_lower", "desc": "Print 'yes' if arg1 contains any lowercase letter, else 'no'.",
     "args": ["ABCdef"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if any(c.islower() for c in sys.argv[1]) else 'no')"},
    {"id": "valid_has_special", "desc": "Print 'yes' if arg1 has any non-alphanumeric char, else 'no'.",
     "args": ["abc!def"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if any(not c.isalnum() for c in sys.argv[1]) else 'no')"},
    {"id": "valid_password_len", "desc": "Print 'strong' if arg1 length >= 8, 'weak' otherwise.",
     "args": ["hello"], "expected": "weak\n",
     "python": "import sys\nprint('strong' if len(sys.argv[1]) >= 8 else 'weak')"},
    {"id": "valid_is_zip5", "desc": "Print 'yes' if arg1 is exactly 5 ASCII digits, else 'no'.",
     "args": ["94105"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if len(sys.argv[1]) == 5 and sys.argv[1].isdigit() else 'no')"},
    {"id": "valid_is_hex", "desc": "Print 'yes' if arg1 is all hex digits (0-9,a-f,A-F), else 'no'.",
     "args": ["deadBEEF"], "expected": "yes\n",
     "python": '''import sys
s = sys.argv[1]
ok = len(s) > 0 and all(c in "0123456789abcdefABCDEF" for c in s)
print("yes" if ok else "no")'''},

    # ---------------- ERROR HANDLING / TRY-CATCH -------------------------
    {"id": "err_safe_int", "desc": "If arg1 is not an int, print 'error'. Else print the int.",
     "args": ["42"], "expected": "42\n",
     "python": '''import sys
try:
    print(int(sys.argv[1]))
except ValueError:
    print("error")'''},
    {"id": "err_safe_div", "desc": "Print arg1/arg2 (int div) or 'error' if arg2 is 0.",
     "args": ["20", "4"], "expected": "5\n",
     "python": '''import sys
try:
    a, b = int(sys.argv[1]), int(sys.argv[2])
    print(a // b)
except Exception:
    print("error")'''},
    {"id": "err_safe_index", "desc": "Split arg1 on spaces, print token at index arg2 or 'error' if out of range.",
     "args": ["a b c", "5"], "expected": "error\n",
     "python": '''import sys
try:
    print(sys.argv[1].split()[int(sys.argv[2])])
except IndexError:
    print("error")'''},

    # ---------------- RECURSIVE / LOOP ALGORITHMS ------------------------
    {"id": "rec_fib_n", "desc": "Print Nth Fibonacci (0-indexed: fib 0=0, fib 1=1, fib 10=55).",
     "args": ["10"], "expected": "55\n",
     "python": '''import sys
n = int(sys.argv[1])
a, b = 0, 1
for _ in range(n):
    a, b = b, a+b
print(a)'''},
    {"id": "rec_fact_n", "desc": "Print N! for non-negative N.",
     "args": ["6"], "expected": "720\n",
     "python": '''import sys
n = int(sys.argv[1])
r = 1
for i in range(2, n+1):
    r *= i
print(r)'''},
    {"id": "rec_power", "desc": "Print base^exp (arg1, arg2 non-negative ints).",
     "args": ["2", "10"], "expected": "1024\n",
     "python": "import sys\nprint(int(sys.argv[1])**int(sys.argv[2]))"},
    {"id": "rec_gcd", "desc": "GCD of two positive ints via repeated modulo.",
     "args": ["48", "36"], "expected": "12\n",
     "python": '''import sys
a, b = int(sys.argv[1]), int(sys.argv[2])
while b: a, b = b, a % b
print(a)'''},
    {"id": "rec_ackermann_small", "desc": "Compute A(2, N). A(m, n) base: A(0,n)=n+1; step: A(m,0)=A(m-1,1); recur: A(m,n)=A(m-1, A(m, n-1)). For N <= 4, result is 2*N+3.",
     "args": ["3"], "expected": "9\n",
     "python": '''import sys
n = int(sys.argv[1])
print(2*n + 3)'''},
    {"id": "rec_count_ones", "desc": "Count 1-bits in binary rep of non-negative int (arg1).",
     "args": ["255"], "expected": "8\n",
     "python": "import sys\nprint(bin(int(sys.argv[1])).count('1'))"},
    {"id": "rec_reverse_num", "desc": "Reverse the digits of a non-negative integer (leading zeros dropped).",
     "args": ["12340"], "expected": "4321\n",
     "python": "import sys\nprint(int(sys.argv[1][::-1]))"},

    # ---------------- MINI PUZZLES ---------------------------------------
    {"id": "mini_all_same", "desc": "Print 'yes' if all chars in arg1 are identical, else 'no'.",
     "args": ["aaaa"], "expected": "yes\n",
     "python": "import sys\ns = sys.argv[1]\nprint('yes' if len(s) > 0 and all(c == s[0] for c in s) else 'no')"},
    {"id": "mini_has_duplicate", "desc": "Print 'yes' if any char in arg1 repeats, else 'no'.",
     "args": ["hello"], "expected": "yes\n",
     "python": "import sys\ns = sys.argv[1]\nprint('yes' if len(set(s)) < len(s) else 'no')"},
    {"id": "mini_is_anagram", "desc": "Print 'yes' if arg1 and arg2 are anagrams (same chars rearranged), else 'no'.",
     "args": ["listen", "silent"], "expected": "yes\n",
     "python": '''import sys
print("yes" if sorted(sys.argv[1]) == sorted(sys.argv[2]) else "no")'''},
    {"id": "mini_common_prefix", "desc": "Print longest common prefix of arg1 and arg2.",
     "args": ["flower", "flow"], "expected": "flow\n",
     "python": '''import sys
a, b = sys.argv[1], sys.argv[2]
i = 0
while i < len(a) and i < len(b) and a[i] == b[i]: i += 1
print(a[:i])'''},
    {"id": "mini_mirror_str", "desc": "Print arg1 followed by its reverse (palindrome builder).",
     "args": ["abc"], "expected": "abccba\n",
     "python": "import sys\nprint(sys.argv[1] + sys.argv[1][::-1])"},
    {"id": "mini_char_diff", "desc": "Count positions where arg1 and arg2 differ (assume same length).",
     "args": ["kitten", "kitchn"], "expected": "2\n",
     "python": '''import sys
a, b = sys.argv[1], sys.argv[2]
print(sum(1 for i in range(len(a)) if a[i] != b[i]))'''},
    {"id": "mini_count_spaces", "desc": "Count space characters in arg1.",
     "args": ["hello world foo bar"], "expected": "3\n",
     "python": "import sys\nprint(sys.argv[1].count(' '))"},
    {"id": "mini_odd_even_split", "desc": "Split space-separated ints into odds and evens. Print 'odds:... | evens:...' with each space-joined.",
     "args": ["1 2 3 4 5 6"], "expected": "odds:1 3 5 | evens:2 4 6\n",
     "python": '''import sys
xs = sys.argv[1].split()
odds = [x for x in xs if int(x) % 2 == 1]
evens = [x for x in xs if int(x) % 2 == 0]
print(f"odds:{' '.join(odds)} | evens:{' '.join(evens)}")'''},

    # ---------------- FORMAT / PRETTY-PRINT ------------------------------
    {"id": "fmt_pad_zero", "desc": "Zero-pad int arg1 to width arg2. e.g. (42, 5) -> '00042'.",
     "args": ["42", "5"], "expected": "00042\n",
     "python": "import sys\nprint(sys.argv[1].zfill(int(sys.argv[2])))"},
    {"id": "fmt_comma_thousands", "desc": "Given int arg1, print with comma thousands separator.",
     "args": ["1234567"], "expected": "1,234,567\n",
     "python": "import sys\nprint(f'{int(sys.argv[1]):,}')"},
    {"id": "fmt_csv_row", "desc": "Given 3 args, print them as CSV row (comma-separated).",
     "args": ["alice", "30", "paris"], "expected": "alice,30,paris\n",
     "python": "import sys\nprint(','.join(sys.argv[1:4]))"},
    {"id": "fmt_tsv_row", "desc": "Given 3 args, print tab-separated.",
     "args": ["alice", "30", "paris"], "expected": "alice\t30\tparis\n",
     "python": "import sys\nprint('\\t'.join(sys.argv[1:4]))"},

    # ---------------- MAP/COUNTER ADVANCED -------------------------------
    {"id": "map_longest_val", "desc": "Parse 'k=v,...' and print the key with the longest value (ties: alphabetical).",
     "args": ["a=foo,b=hello,c=hi"], "expected": "b\n",
     "python": '''import sys
d = dict(kv.split('=') for kv in sys.argv[1].split(','))
best_k = min(d, key=lambda k: (-len(d[k]), k))
print(best_k)'''},
    {"id": "map_sum_by_key", "desc": "Parse 'k=v,k=v,...' where values are ints; print total.",
     "args": ["x=10,y=20,z=30"], "expected": "60\n",
     "python": '''import sys
d = dict(kv.split('=') for kv in sys.argv[1].split(','))
print(sum(int(v) for v in d.values()))'''},
    {"id": "map_group_by_first", "desc": "Group space-separated words by first letter. Print 'letter:count' pairs sorted by letter asc, space-separated.",
     "args": ["apple ant banana bee cat"], "expected": "a:2 b:2 c:1\n",
     "python": '''import sys
from collections import Counter
c = Counter(w[0] for w in sys.argv[1].split())
print(' '.join(f"{k}:{c[k]}" for k in sorted(c)))'''},
    {"id": "map_invert", "desc": "Parse 'k=v,...' with unique values. Print 'v=k,...' pairs, sorted by original k asc, comma-joined.",
     "args": ["a=1,b=2,c=3"], "expected": "1=a,2=b,3=c\n",
     "python": '''import sys
d = dict(kv.split('=') for kv in sys.argv[1].split(','))
print(','.join(f'{d[k]}={k}' for k in sorted(d)))'''},
    {"id": "map_key_with_max", "desc": "Parse 'k=v,...' with int values. Print key with largest value (ties: alphabetical).",
     "args": ["a=3,b=7,c=5"], "expected": "b\n",
     "python": '''import sys
d = dict(kv.split('=') for kv in sys.argv[1].split(','))
best = max(d, key=lambda k: (int(d[k]), -ord(k[0])))
print(best)'''},

    # ---------------- NESTED STRUCTURES ----------------------------------
    {"id": "nest_first_of_first", "desc": "Grid '1,2;3,4'. Print value at row 0, col 0.",
     "args": ["1,2,3;4,5,6"], "expected": "1\n",
     "python": "import sys\ng = [r.split(',') for r in sys.argv[1].split(';')]\nprint(g[0][0])"},
    {"id": "nest_last_of_last", "desc": "Grid '1,2;3,4'. Print last cell of last row.",
     "args": ["1,2,3;4,5,6;7,8,9"], "expected": "9\n",
     "python": "import sys\ng = [r.split(',') for r in sys.argv[1].split(';')]\nprint(g[-1][-1])"},
    {"id": "nest_diagonal_sum", "desc": "Square grid '1,2,3;4,5,6;7,8,9'. Sum diagonal top-left to bottom-right.",
     "args": ["1,2,3;4,5,6;7,8,9"], "expected": "15\n",
     "python": '''import sys
g = [r.split(',') for r in sys.argv[1].split(';')]
print(sum(int(g[i][i]) for i in range(len(g))))'''},
    {"id": "nest_transpose", "desc": "Transpose grid '1,2,3;4,5,6' to rows-by-cols. Output in same format.",
     "args": ["1,2,3;4,5,6"], "expected": "1,4;2,5;3,6\n",
     "python": '''import sys
g = [r.split(',') for r in sys.argv[1].split(';')]
t = list(zip(*g))
print(';'.join(','.join(c) for c in t))'''},

    # ---------------- INTEGER PROCESSING ---------------------------------
    {"id": "int_biggest_digit", "desc": "Given a non-negative int (arg1), print its largest digit.",
     "args": ["493072"], "expected": "9\n",
     "python": "import sys\nprint(max(int(d) for d in sys.argv[1]))"},
    {"id": "int_smallest_digit_nonzero", "desc": "Given a non-negative int, print its smallest NON-ZERO digit (if any), else 0.",
     "args": ["30205"], "expected": "2\n",
     "python": '''import sys
ds = [int(d) for d in sys.argv[1] if d != '0']
print(min(ds) if ds else 0)'''},
    {"id": "int_even_digit_count", "desc": "Count how many digits in int arg1 are even (0,2,4,6,8).",
     "args": ["123456"], "expected": "3\n",
     "python": "import sys\nprint(sum(1 for d in sys.argv[1] if int(d) % 2 == 0))"},
    {"id": "int_replace_zeros", "desc": "In int arg1, replace every '0' digit with '1'. Print resulting number.",
     "args": ["10203"], "expected": "11213\n",
     "python": "import sys\nprint(int(sys.argv[1].replace('0', '1')))"},
    {"id": "int_sorted_digits", "desc": "Sort digits of int arg1 ascending, print as int (leading zeros dropped).",
     "args": ["5219"], "expected": "1259\n",
     "python": "import sys\nprint(int(''.join(sorted(sys.argv[1]))))"},

    # ---------------- MISC -----------------------------------------------
    {"id": "misc_boolean_and", "desc": "Print 'true' if arg1 == 'true' AND arg2 == 'true', else 'false'.",
     "args": ["true", "true"], "expected": "true\n",
     "python": "import sys\nprint('true' if sys.argv[1]=='true' and sys.argv[2]=='true' else 'false')"},
    {"id": "misc_boolean_or", "desc": "Print 'true' if arg1=='true' OR arg2=='true', else 'false'.",
     "args": ["false", "true"], "expected": "true\n",
     "python": "import sys\nprint('true' if sys.argv[1]=='true' or sys.argv[2]=='true' else 'false')"},
    {"id": "misc_boolean_xor", "desc": "Print 'true' if exactly one of arg1, arg2 is 'true'.",
     "args": ["true", "false"], "expected": "true\n",
     "python": "import sys\nprint('true' if (sys.argv[1]=='true') != (sys.argv[2]=='true') else 'false')"},
    {"id": "misc_ternary", "desc": "If arg1 == '0' print 'zero', positive int print 'pos', negative print 'neg'.",
     "args": ["-5"], "expected": "neg\n",
     "python": '''import sys
n = int(sys.argv[1])
print('zero' if n == 0 else ('pos' if n > 0 else 'neg'))'''},
    {"id": "misc_temp_convert", "desc": "Convert celsius float (arg1) to fahrenheit with 1 decimal.",
     "args": ["25"], "expected": "77.0\n",
     "python": "import sys\nprint(f'{float(sys.argv[1])*9/5+32:.1f}')"},
    {"id": "misc_max_sequential", "desc": "Given space-separated ints, print length of the longest run of strictly-increasing values.",
     "args": ["1 2 3 1 2 3 4 1"], "expected": "4\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
best = cur = 1
for i in range(1, len(xs)):
    if xs[i] > xs[i-1]: cur += 1
    else: cur = 1
    if cur > best: best = cur
print(best)'''},
    {"id": "misc_check_sorted_desc", "desc": "Print 'yes' if space-separated ints are sorted descending, else 'no'.",
     "args": ["5 4 3 2 1"], "expected": "yes\n",
     "python": '''import sys
xs = [int(x) for x in sys.argv[1].split()]
print('yes' if all(xs[i] >= xs[i+1] for i in range(len(xs)-1)) else 'no')'''},
]
