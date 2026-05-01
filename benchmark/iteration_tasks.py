"""Bank of 100 fresh task specs for the rag_loop iteration suite.

Layout: 10 batches × 10 tasks each. Each batch has a topical theme so the
A/B reveals gaps in a coherent area. None of these are duplicates of
rag_ab.py or rag_ab_v2.py.

Each spec: id, desc, args, expected, python. The Python reference is
validated by rag_loop before the A/B runs.
"""

# Batch 3: text formatting / padding / wrapping
BATCH_3 = [
    {"id": "right_pad_spaces", "desc": "Take a string in arg0 and a positive integer n in arg1. Print arg0 padded on the RIGHT with spaces until length is n. If already at least n, print unchanged.",
     "args": ["hi", "5"], "expected": "hi   \n",
     "python": "import sys\ns,n=sys.argv[1],int(sys.argv[2])\nprint(s if len(s)>=n else s+' '*(n-len(s)))"},
    {"id": "center_pad", "desc": "Take a string in arg0 and a positive integer n in arg1. Print arg0 centered in a field of width n using spaces (extra space on the right if odd).",
     "args": ["hi", "6"], "expected": "  hi  \n",
     "python": "import sys\ns,n=sys.argv[1],int(sys.argv[2])\nprint(s.center(n))"},
    {"id": "truncate_ellipsis", "desc": "Take a string in arg0 and a positive integer n in arg1. If arg0 is longer than n, print the first n-3 chars followed by '...'. Otherwise print arg0 unchanged.",
     "args": ["hello world", "8"], "expected": "hello...\n",
     "python": "import sys\ns,n=sys.argv[1],int(sys.argv[2])\nprint(s if len(s)<=n else s[:n-3]+'...')"},
    {"id": "wrap_words", "desc": "Take a sentence in arg0 and a positive integer n in arg1. Greedily wrap into lines of width <= n, words separated by single space; print each line on its own.",
     "args": ["the quick brown fox jumps", "10"], "expected": "the quick\nbrown fox\njumps\n",
     "python": ("import sys\nimport textwrap\nfor l in textwrap.wrap(sys.argv[1], int(sys.argv[2])):\n    print(l)")},
    {"id": "indent_lines", "desc": "Take a multi-line string in arg0 (lines separated by '\\n') and a non-negative integer n in arg1. Print each line with n leading spaces.",
     "args": ["a\nb\nc", "2"], "expected": "  a\n  b\n  c\n",
     "python": ("import sys\npad=' '*int(sys.argv[2])\nfor l in sys.argv[1].split('\\n'):\n    print(pad+l)")},
    {"id": "title_each_word", "desc": "Take a sentence in arg0. Print it with the first letter of each whitespace-separated word uppercased and the rest lowercased.",
     "args": ["heLLo woRLd FOO"], "expected": "Hello World Foo\n",
     "python": "import sys\nprint(' '.join(w[:1].upper()+w[1:].lower() for w in sys.argv[1].split()))"},
    {"id": "hyphenate_camel", "desc": "Take a camelCase string in arg0 (single word, starts lowercase). Print it with hyphens inserted before each uppercase letter and the whole thing lowercased.",
     "args": ["camelCaseExample"], "expected": "camel-case-example\n",
     "python": ("import sys, re\nprint(re.sub(r'([A-Z])', r'-\\1', sys.argv[1]).lower())")},
    {"id": "snake_to_pascal", "desc": "Take a snake_case string in arg0. Print it converted to PascalCase: split on '_', capitalize each part, concatenate.",
     "args": ["hello_world_foo"], "expected": "HelloWorldFoo\n",
     "python": "import sys\nprint(''.join(p.capitalize() for p in sys.argv[1].split('_')))"},
    {"id": "strip_punct", "desc": "Take a string in arg0. Print it with all ASCII punctuation chars removed. Punctuation is anything in '!\"#$%&\\'()*+,-./:;<=>?@[\\\\]^_`{|}~'.",
     "args": ["hello, world!"], "expected": "hello world\n",
     "python": ("import sys, string\nprint(''.join(c for c in sys.argv[1] if c not in string.punctuation))")},
    {"id": "reverse_words", "desc": "Take a sentence in arg0. Print the same words but in reverse order, single space separated.",
     "args": ["the quick brown fox"], "expected": "fox brown quick the\n",
     "python": "import sys\nprint(' '.join(reversed(sys.argv[1].split())))"},
]

# Batch 4: numeric / digit operations
BATCH_4 = [
    {"id": "sum_of_digits", "desc": "Take a non-negative integer in arg0. Print the sum of its decimal digits.",
     "args": ["1234"], "expected": "10\n",
     "python": "import sys\nprint(sum(int(c) for c in sys.argv[1]))"},
    {"id": "count_digits_in_n", "desc": "Take a non-negative integer in arg0. Print how many decimal digits it has.",
     "args": ["12345"], "expected": "5\n",
     "python": "import sys\nprint(len(sys.argv[1]))"},
    {"id": "is_prime", "desc": "Take a positive integer n in arg0. Print 'yes' if n is prime, 'no' otherwise. 1 is not prime; 2 is prime.",
     "args": ["7"], "expected": "yes\n",
     "python": ("import sys\nn=int(sys.argv[1])\n"
                "is_p = n>=2 and all(n%i!=0 for i in range(2,int(n**0.5)+1))\n"
                "print('yes' if is_p else 'no')")},
    {"id": "gcd_two", "desc": "Take two positive integers in arg0 and arg1. Print their greatest common divisor.",
     "args": ["48", "18"], "expected": "6\n",
     "python": "import sys, math\nprint(math.gcd(int(sys.argv[1]), int(sys.argv[2])))"},
    {"id": "lcm_two", "desc": "Take two positive integers in arg0 and arg1. Print their least common multiple.",
     "args": ["4", "6"], "expected": "12\n",
     "python": "import sys, math\na,b=int(sys.argv[1]),int(sys.argv[2])\nprint(a*b//math.gcd(a,b))"},
    {"id": "power_of_two", "desc": "Take a positive integer n in arg0. Print 'yes' if n is a power of 2 (1, 2, 4, 8, 16, ...), 'no' otherwise.",
     "args": ["16"], "expected": "yes\n",
     "python": ("import sys\nn=int(sys.argv[1])\nprint('yes' if n>0 and (n&(n-1))==0 else 'no')")},
    {"id": "n_choose_k", "desc": "Take two non-negative integers n and k in arg0 and arg1, with k<=n. Print the binomial coefficient n choose k.",
     "args": ["5", "2"], "expected": "10\n",
     "python": "import sys, math\nprint(math.comb(int(sys.argv[1]), int(sys.argv[2])))"},
    {"id": "factorial_n", "desc": "Take a non-negative integer n in arg0. Print n!.",
     "args": ["5"], "expected": "120\n",
     "python": "import sys, math\nprint(math.factorial(int(sys.argv[1])))"},
    {"id": "abs_diff", "desc": "Take two integers in arg0 and arg1 (may be negative). Print the absolute value of their difference.",
     "args": ["3", "-5"], "expected": "8\n",
     "python": "import sys\nprint(abs(int(sys.argv[1]) - int(sys.argv[2])))"},
    {"id": "int_sqrt", "desc": "Take a non-negative integer n in arg0. Print the floor of its square root (largest integer k such that k*k <= n).",
     "args": ["17"], "expected": "4\n",
     "python": "import sys, math\nprint(math.isqrt(int(sys.argv[1])))"},
]

# Batch 5: array set operations
BATCH_5 = [
    {"id": "intersect_int_arrays", "desc": "Take two space-separated lists of integers in arg0 and arg1. Print the integers that appear in both, each once, in the order they first appear in arg0, space-separated.",
     "args": ["1 2 3 4 5", "3 5 7 1"], "expected": "1 3 5\n",
     "python": ("import sys\na=sys.argv[1].split(); bs=set(sys.argv[2].split())\n"
                "seen=set(); out=[]\n"
                "for x in a:\n    if x in bs and x not in seen:\n        out.append(x); seen.add(x)\n"
                "print(' '.join(out))")},
    {"id": "union_preserve_order", "desc": "Take two space-separated lists of strings in arg0 and arg1. Print the union (each string once) in the order: all unique items from arg0 first (in original order), then any new items from arg1 (in original order).",
     "args": ["a b c", "c d a e"], "expected": "a b c d e\n",
     "python": ("import sys\na=sys.argv[1].split(); b=sys.argv[2].split()\n"
                "seen=set(); out=[]\n"
                "for x in a+b:\n    if x not in seen:\n        seen.add(x); out.append(x)\n"
                "print(' '.join(out))")},
    {"id": "symmetric_diff", "desc": "Take two space-separated lists of strings in arg0 and arg1. Print the items that appear in exactly one of them (set symmetric difference). Print them sorted ascending, space-separated.",
     "args": ["a b c d", "c d e f"], "expected": "a b e f\n",
     "python": ("import sys\na=set(sys.argv[1].split()); b=set(sys.argv[2].split())\n"
                "print(' '.join(sorted(a.symmetric_difference(b))))")},
    {"id": "is_subset", "desc": "Take two space-separated lists of strings in arg0 and arg1. Print 'yes' if every distinct item in arg0 also appears in arg1, otherwise 'no'.",
     "args": ["a b c", "a b c d e"], "expected": "yes\n",
     "python": ("import sys\na=set(sys.argv[1].split()); b=set(sys.argv[2].split())\n"
                "print('yes' if a.issubset(b) else 'no')")},
    {"id": "freq_count_top_k", "desc": "Take a space-separated list of strings in arg0 and a positive integer k in arg1. Print the top k most-frequent strings, breaking ties by first-occurrence order, space-separated.",
     "args": ["a b a c b a d", "2"], "expected": "a b\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "items=sys.argv[1].split(); k=int(sys.argv[2])\n"
                "first={}\n"
                "for i,x in enumerate(items):\n    first.setdefault(x,i)\n"
                "c=Counter(items)\n"
                "ranked=sorted(c.keys(), key=lambda x: (-c[x], first[x]))\n"
                "print(' '.join(ranked[:k]))")},
    {"id": "sort_freq_desc", "desc": "Take a space-separated list of strings in arg0. Print each distinct string and its count formatted 'X:N', most-frequent first, ties broken by first-occurrence order, space-separated.",
     "args": ["a b a c b a"], "expected": "a:3 b:2 c:1\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "items=sys.argv[1].split()\nfirst={}\n"
                "for i,x in enumerate(items): first.setdefault(x,i)\n"
                "c=Counter(items)\n"
                "ranked=sorted(c.keys(), key=lambda x: (-c[x], first[x]))\n"
                "print(' '.join(f'{x}:{c[x]}' for x in ranked))")},
    {"id": "majority_or_none", "desc": "Take a space-separated list of strings in arg0. Print the string that appears more than half the time. If no such string exists, print 'none'.",
     "args": ["a a a b c"], "expected": "a\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "items=sys.argv[1].split()\n"
                "c=Counter(items); maj=None\n"
                "for k,v in c.items():\n    if v*2 > len(items): maj=k; break\n"
                "print(maj or 'none')")},
    {"id": "remove_dupes_keep_last", "desc": "Take a space-separated list of strings in arg0. Print the distinct items in the order of their LAST occurrence in arg0, space-separated.",
     "args": ["a b a c b d"], "expected": "a c b d\n",
     "python": ("import sys\nitems=sys.argv[1].split()\n"
                "seen=set(); out=[]\n"
                "for x in reversed(items):\n    if x not in seen:\n        seen.add(x); out.append(x)\n"
                "print(' '.join(reversed(out)))")},
    {"id": "common_prefix_words", "desc": "Take a space-separated list of words in arg0. Print the longest common prefix of all the words. If no common prefix, print empty string.",
     "args": ["flower flow flight"], "expected": "fl\n",
     "python": ("import sys\nws=sys.argv[1].split()\n"
                "if not ws: print(''); sys.exit()\n"
                "p=ws[0]\nfor w in ws[1:]:\n    while not w.startswith(p): p=p[:-1]\n"
                "print(p)")},
    {"id": "split_evens_odds", "desc": "Take a space-separated list of integers in arg0. Print two lines: first all even values in original order space-separated, then all odd values in original order space-separated. Print empty line for an empty group.",
     "args": ["3 1 4 1 5 9 2 6"], "expected": "4 2 6\n3 1 1 5 9\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "ev=[str(x) for x in xs if x%2==0]\n"
                "od=[str(x) for x in xs if x%2!=0]\n"
                "print(' '.join(ev))\nprint(' '.join(od))")},
]

# Batch 6: parsing (CSV / log / config)
BATCH_6 = [
    {"id": "csv_count_rows", "desc": "Take a CSV string in arg0 (rows separated by '\\n'; the first row is a header). Print the number of data rows (excluding header).",
     "args": ["a,b\n1,2\n3,4\n5,6"], "expected": "3\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\nprint(len(rows)-1)")},
    {"id": "csv_select_column", "desc": "Take a CSV string in arg0 (rows '\\n', fields ','). The first row is a header. Take a column name in arg1. Print the values from that column for all data rows, one per line.",
     "args": ["name,age\nalice,30\nbob,25", "name"], "expected": "alice\nbob\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\nh=rows[0].split(',')\n"
                "i=h.index(sys.argv[2])\n"
                "for r in rows[1:]:\n    print(r.split(',')[i])")},
    {"id": "log_count_level", "desc": "Take a multi-line log in arg0 (lines '\\n'). Each line starts with a level token: INFO, WARN, or ERROR followed by space and message. Take a level in arg1. Print how many lines have that level.",
     "args": ["INFO ok\nWARN slow\nERROR boom\nINFO again", "INFO"], "expected": "2\n",
     "python": ("import sys\n"
                "lines=sys.argv[1].split('\\n'); lvl=sys.argv[2]\n"
                "print(sum(1 for l in lines if l.split(' ',1)[0]==lvl))")},
    {"id": "log_extract_messages", "desc": "Take a multi-line log in arg0 and a level in arg1 (INFO|WARN|ERROR). Print the messages (text after the level + single space) of all lines with that level, one per line, preserving order.",
     "args": ["INFO ok\nWARN slow\nERROR boom\nINFO again", "INFO"], "expected": "ok\nagain\n",
     "python": ("import sys\nlines=sys.argv[1].split('\\n'); lvl=sys.argv[2]\n"
                "for l in lines:\n    p=l.split(' ',1)\n"
                "    if len(p)==2 and p[0]==lvl: print(p[1])")},
    {"id": "config_get_key", "desc": "Take a config string in arg0 (lines '\\n', each line is 'key=value'). Take a key in arg1. Print the value associated with the key. If the key is missing, print 'NONE'.",
     "args": ["host=localhost\nport=8080\nuser=admin", "port"], "expected": "8080\n",
     "python": ("import sys\nfor l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l:\n        k,v=l.split('=',1)\n"
                "        if k==sys.argv[2]: print(v); break\nelse:\n    print('NONE')")},
    {"id": "config_keys_sorted", "desc": "Take a config string in arg0 (lines 'key=value'). Print all keys in alphabetical order, one per line.",
     "args": ["port=8080\nhost=local\nuser=admin"], "expected": "host\nport\nuser\n",
     "python": ("import sys\nks=[l.split('=',1)[0] for l in sys.argv[1].split('\\n') if '=' in l]\n"
                "for k in sorted(ks): print(k)")},
    {"id": "csv_filter_by_value", "desc": "Take a CSV in arg0 (header + data). Take a column name in arg1 and a value in arg2. Print the data rows where that column equals that value, one per line, full row preserved.",
     "args": ["name,role\nalice,dev\nbob,pm\ncarol,dev", "role", "dev"], "expected": "alice,dev\ncarol,dev\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n'); h=rows[0].split(',')\n"
                "i=h.index(sys.argv[2])\n"
                "for r in rows[1:]:\n    if r.split(',')[i]==sys.argv[3]: print(r)")},
    {"id": "kv_pairs_to_json_like", "desc": "Take key=value pairs separated by ',' in arg0. Print them as 'key:value;key:value;' (replace = with :, , with ;), trailing semicolon included.",
     "args": ["a=1,b=2,c=3"], "expected": "a:1;b:2;c:3;\n",
     "python": ("import sys\n"
                "out=[]\n"
                "for p in sys.argv[1].split(','):\n    k,v=p.split('=',1); out.append(f'{k}:{v}')\n"
                "print(';'.join(out)+';')")},
    {"id": "sum_field_in_csv", "desc": "Take a CSV in arg0 (header + data). Take a numeric column name in arg1. Print the sum of that column for all data rows.",
     "args": ["name,price\napple,3\nbanana,5\ncherry,2", "price"], "expected": "10\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n'); h=rows[0].split(',')\n"
                "i=h.index(sys.argv[2])\n"
                "print(sum(int(r.split(',')[i]) for r in rows[1:]))")},
    {"id": "count_log_unique_users", "desc": "Take a multi-line log in arg0 where each line is 'user action' (single space). Print the number of distinct users.",
     "args": ["alice login\nbob login\nalice logout\ncarol login\nbob logout"], "expected": "3\n",
     "python": ("import sys\nusers={l.split(' ',1)[0] for l in sys.argv[1].split('\\n') if ' ' in l}\n"
                "print(len(users))")},
]

# Batch 7: state machines / scanning
BATCH_7 = [
    {"id": "balanced_brackets_multi", "desc": "Take a string in arg0 containing only '()[]{}' characters. Print 'yes' if all brackets are balanced and properly nested, 'no' otherwise.",
     "args": ["({[]})"], "expected": "yes\n",
     "python": ("import sys\ns=sys.argv[1]; pairs={')':'(',']':'[','}':'{'}; st=[]\n"
                "ok=True\n"
                "for c in s:\n    if c in '([{': st.append(c)\n"
                "    elif c in ')]}':\n        if not st or st.pop()!=pairs[c]: ok=False; break\n"
                "print('yes' if ok and not st else 'no')")},
    {"id": "first_unbalanced_index", "desc": "Take a string of '()' in arg0. Print the 0-based index of the first character that is unbalanced (a ')' with no matching '(' before it). If all are balanced, print -1.",
     "args": ["(()))(" ], "expected": "4\n",
     "python": ("import sys\ns=sys.argv[1]; d=0; idx=-1\n"
                "for i,c in enumerate(s):\n"
                "    if c=='(': d+=1\n    elif c==')':\n        if d==0: idx=i; break\n        d-=1\n"
                "print(idx)")},
    {"id": "longest_run_letter", "desc": "Take a string in arg0. Print the length of the longest run of identical letters (any character, in fact).",
     "args": ["aaabbbbcdd"], "expected": "4\n",
     "python": ("import sys\ns=sys.argv[1]; best=cur=1 if s else 0\n"
                "for i in range(1,len(s)):\n    if s[i]==s[i-1]: cur+=1\n    else: cur=1\n"
                "    if cur>best: best=cur\n"
                "print(best)")},
    {"id": "split_on_consecutive", "desc": "Take a string in arg0. Print groups of consecutive identical characters as 'XN' (char then count), space-separated.",
     "args": ["aaabbcdddd"], "expected": "a3 b2 c1 d4\n",
     "python": ("import sys\ns=sys.argv[1]; out=[]; i=0\n"
                "while i<len(s):\n    j=i\n    while j<len(s) and s[j]==s[i]: j+=1\n"
                "    out.append(f'{s[i]}{j-i}'); i=j\n"
                "print(' '.join(out))")},
    {"id": "max_consecutive_evens", "desc": "Take a space-separated list of integers in arg0. Print the length of the longest streak of consecutive even values.",
     "args": ["1 2 4 6 1 8 10 12 14 1"], "expected": "4\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\nbest=cur=0\n"
                "for v in xs:\n    if v%2==0: cur+=1; best=max(best,cur)\n    else: cur=0\n"
                "print(best)")},
    {"id": "longest_increasing_streak", "desc": "Take a space-separated list of integers in arg0. Print the length of the longest strictly increasing contiguous streak.",
     "args": ["1 2 3 1 2 3 4 1"], "expected": "4\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "best=cur=1 if xs else 0\n"
                "for i in range(1,len(xs)):\n    if xs[i]>xs[i-1]: cur+=1\n    else: cur=1\n"
                "    if cur>best: best=cur\n"
                "print(best)")},
    {"id": "every_other_letter", "desc": "Take a string in arg0. Print every other character starting from index 0 (the 0th, 2nd, 4th, ...).",
     "args": ["abcdefgh"], "expected": "aceg\n",
     "python": "import sys\nprint(sys.argv[1][::2])"},
    {"id": "find_substring_index", "desc": "Take two strings in arg0 and arg1. Print the 0-based index of the first occurrence of arg1 in arg0, or -1 if not found.",
     "args": ["hello world", "world"], "expected": "6\n",
     "python": "import sys\nprint(sys.argv[1].find(sys.argv[2]))"},
    {"id": "all_caps_or_not", "desc": "Take a string in arg0. Print 'yes' if every ASCII letter in arg0 is uppercase (non-letters allowed and ignored), otherwise 'no'.",
     "args": ["HELLO, WORLD!"], "expected": "yes\n",
     "python": ("import sys\ns=sys.argv[1]\n"
                "letters=[c for c in s if c.isalpha()]\n"
                "print('yes' if letters and all(c.isupper() for c in letters) else 'no' if letters else 'no')")},
    {"id": "starts_and_ends_same", "desc": "Take a string in arg0. Print 'yes' if its first character equals its last character, 'no' otherwise. For empty string print 'no'.",
     "args": ["abcba"], "expected": "yes\n",
     "python": ("import sys\ns=sys.argv[1]\nprint('yes' if s and s[0]==s[-1] else 'no')")},
]

# Batch 8: distance / similarity
BATCH_8 = [
    {"id": "hamming_distance", "desc": "Take two strings of equal length in arg0 and arg1. Print the number of positions where they differ.",
     "args": ["karolin", "kathrin"], "expected": "3\n",
     "python": "import sys\na,b=sys.argv[1],sys.argv[2]\nprint(sum(1 for x,y in zip(a,b) if x!=y))"},
    {"id": "common_chars_count", "desc": "Take two strings in arg0 and arg1. Print how many distinct ASCII characters appear in both.",
     "args": ["abcde", "becfg"], "expected": "3\n",
     "python": "import sys\nprint(len(set(sys.argv[1]) & set(sys.argv[2])))"},
    {"id": "is_anagram", "desc": "Take two strings in arg0 and arg1 (lowercase ASCII letters only). Print 'yes' if they are anagrams of each other, 'no' otherwise.",
     "args": ["listen", "silent"], "expected": "yes\n",
     "python": ("import sys\nprint('yes' if sorted(sys.argv[1])==sorted(sys.argv[2]) else 'no')")},
    {"id": "longest_common_prefix_two", "desc": "Take two strings in arg0 and arg1. Print their longest common prefix.",
     "args": ["interview", "internal"], "expected": "inter\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]; n=0\n"
                "while n<len(a) and n<len(b) and a[n]==b[n]: n+=1\nprint(a[:n])")},
    {"id": "longest_common_suffix_two", "desc": "Take two strings in arg0 and arg1. Print their longest common suffix.",
     "args": ["running", "swimming"], "expected": "ing\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]; n=0\n"
                "while n<len(a) and n<len(b) and a[-1-n]==b[-1-n]: n+=1\nprint(a[len(a)-n:])")},
    {"id": "edit_one_apart", "desc": "Take two strings in arg0 and arg1. Print 'yes' if they differ by exactly one substitution, one insertion, or one deletion. Equal strings print 'no' (zero edits, not one).",
     "args": ["abc", "abd"], "expected": "yes\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if a==b: print('no')\nelif abs(len(a)-len(b))>1: print('no')\n"
                "elif len(a)==len(b):\n    diffs=sum(1 for x,y in zip(a,b) if x!=y); print('yes' if diffs==1 else 'no')\n"
                "else:\n    s,l=(a,b) if len(a)<len(b) else (b,a)\n"
                "    i=0; ok=True; off=0\n"
                "    while i<len(s):\n"
                "        if s[i]!=l[i+off]:\n"
                "            if off==1: ok=False; break\n            off=1; continue\n        i+=1\n"
                "    print('yes' if ok else 'no')")},
    {"id": "shared_word_count", "desc": "Take two sentences in arg0 and arg1 (whitespace-separated words). Print the number of distinct words that appear in both.",
     "args": ["the quick brown fox", "fox jumps over the dog"], "expected": "2\n",
     "python": ("import sys\nprint(len(set(sys.argv[1].split()) & set(sys.argv[2].split())))")},
    {"id": "is_rotation_of", "desc": "Take two strings in arg0 and arg1. Print 'yes' if arg1 is a rotation of arg0 (same chars in cyclic order), 'no' otherwise.",
     "args": ["waterbottle", "erbottlewat"], "expected": "yes\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "print('yes' if len(a)==len(b) and a and b in a+a else 'no')")},
    {"id": "char_overlap_ratio", "desc": "Take two strings in arg0 and arg1. Print the size of (set of chars in both) divided by (size of set of chars in either), as a float with 3 decimal places. If both empty, print '0.000'.",
     "args": ["abcde", "becfg"], "expected": "0.429\n",
     "python": ("import sys\na=set(sys.argv[1]); b=set(sys.argv[2])\n"
                "u=a|b\n"
                "print(f'{len(a&b)/len(u):.3f}' if u else '0.000')")},
    {"id": "is_subsequence", "desc": "Take two strings in arg0 (the candidate) and arg1 (the target). Print 'yes' if every character of arg0 appears in arg1 in the same relative order (not necessarily consecutive), 'no' otherwise.",
     "args": ["ace", "abcde"], "expected": "yes\n",
     "python": ("import sys\ns,t=sys.argv[1],sys.argv[2]; i=0\n"
                "for c in t:\n    if i<len(s) and c==s[i]: i+=1\n"
                "print('yes' if i==len(s) else 'no')")},
]

# Batch 9: hierarchical / paths
BATCH_9 = [
    {"id": "path_basename", "desc": "Take a Unix-style path in arg0 (forward slashes). Print the basename — the part after the last '/'. If no slash, print the whole string.",
     "args": ["/usr/local/bin/sigil"], "expected": "sigil\n",
     "python": "import sys\nprint(sys.argv[1].split('/')[-1])"},
    {"id": "path_dirname", "desc": "Take a Unix-style path in arg0 (forward slashes). Print the dirname — everything before the last '/'. If no slash, print empty string.",
     "args": ["/usr/local/bin/sigil"], "expected": "/usr/local/bin\n",
     "python": ("import sys\np=sys.argv[1]\n"
                "if '/' in p: print(p.rsplit('/',1)[0])\nelse: print('')")},
    {"id": "path_extension", "desc": "Take a filename in arg0 (no slashes). Print its extension (the part after the last '.'). If no '.', print empty string.",
     "args": ["report.tar.gz"], "expected": "gz\n",
     "python": ("import sys\np=sys.argv[1]\n"
                "if '.' in p: print(p.rsplit('.',1)[1])\nelse: print('')")},
    {"id": "path_join_parts", "desc": "Take a space-separated list of path segments in arg0. Print them joined by '/' with no leading or trailing slash.",
     "args": ["usr local bin sigil"], "expected": "usr/local/bin/sigil\n",
     "python": "import sys\nprint('/'.join(sys.argv[1].split()))"},
    {"id": "path_depth", "desc": "Take a Unix path in arg0. Print the depth — the count of non-empty segments separated by '/'.",
     "args": ["/a/b/c"], "expected": "3\n",
     "python": "import sys\nprint(sum(1 for p in sys.argv[1].split('/') if p))"},
    {"id": "path_strip_leading_slash", "desc": "Take a path in arg0. If it starts with '/', print it without the leading '/'. Otherwise print unchanged.",
     "args": ["/usr/local"], "expected": "usr/local\n",
     "python": "import sys\np=sys.argv[1]\nprint(p[1:] if p.startswith('/') else p)"},
    {"id": "path_normalize_dots", "desc": "Take a Unix path in arg0 (no '..', possibly '.' segments). Print it with '.' segments removed and consecutive slashes collapsed. Preserve a leading '/' if any.",
     "args": ["/usr/./local//bin/./sigil"], "expected": "/usr/local/bin/sigil\n",
     "python": ("import sys\np=sys.argv[1]\nlead='/' if p.startswith('/') else ''\n"
                "segs=[s for s in p.split('/') if s and s!='.']\n"
                "print(lead+'/'.join(segs))")},
    {"id": "longest_path_segment", "desc": "Take a Unix path in arg0. Print the longest path segment (between slashes). On ties, the first wins.",
     "args": ["/a/bb/ccc/dd/c"], "expected": "ccc\n",
     "python": ("import sys\nsegs=[s for s in sys.argv[1].split('/') if s]\n"
                "best=segs[0]\nfor s in segs[1:]:\n    if len(s)>len(best): best=s\n"
                "print(best)")},
    {"id": "ends_with_extension", "desc": "Take a filename in arg0 and an extension in arg1 (without leading '.'). Print 'yes' if arg0 ends with '.<ext>', 'no' otherwise.",
     "args": ["report.txt", "txt"], "expected": "yes\n",
     "python": ("import sys\nprint('yes' if sys.argv[1].endswith('.'+sys.argv[2]) else 'no')")},
    {"id": "swap_extension", "desc": "Take a filename in arg0 (with at least one '.') and a new extension in arg1 (no leading '.'). Print arg0 with its extension replaced by arg1.",
     "args": ["report.txt", "md"], "expected": "report.md\n",
     "python": ("import sys\np=sys.argv[1].rsplit('.',1)[0]\nprint(p+'.'+sys.argv[2])")},
]

# Batch 10: bit operations
BATCH_10 = [
    {"id": "popcount", "desc": "Take a non-negative integer n in arg0. Print the number of 1 bits in its binary representation (popcount).",
     "args": ["13"], "expected": "3\n",
     "python": "import sys\nprint(bin(int(sys.argv[1])).count('1'))"},
    {"id": "to_binary_str", "desc": "Take a non-negative integer n in arg0. Print n's binary representation as a string of '0' and '1' chars (no '0b' prefix). For 0 print '0'.",
     "args": ["13"], "expected": "1101\n",
     "python": "import sys\nn=int(sys.argv[1])\nprint(bin(n)[2:] if n else '0')"},
    {"id": "binary_to_int", "desc": "Take a binary string in arg0 (only '0' and '1'). Print the decimal integer value.",
     "args": ["1101"], "expected": "13\n",
     "python": "import sys\nprint(int(sys.argv[1], 2))"},
    {"id": "bit_at_index", "desc": "Take a non-negative integer n in arg0 and a non-negative integer i in arg1. Print 1 if the i-th bit of n is set (LSB is index 0), 0 otherwise.",
     "args": ["13", "2"], "expected": "1\n",
     "python": "import sys\nprint((int(sys.argv[1])>>int(sys.argv[2])) & 1)"},
    {"id": "set_bit", "desc": "Take a non-negative integer n in arg0 and a non-negative bit index i in arg1. Print n with the i-th bit set to 1 (LSB is index 0).",
     "args": ["8", "1"], "expected": "10\n",
     "python": "import sys\nprint(int(sys.argv[1]) | (1 << int(sys.argv[2])))"},
    {"id": "clear_bit", "desc": "Take a non-negative integer n in arg0 and a non-negative bit index i in arg1. Print n with the i-th bit cleared (set to 0).",
     "args": ["13", "0"], "expected": "12\n",
     "python": "import sys\nprint(int(sys.argv[1]) & ~(1 << int(sys.argv[2])))"},
    {"id": "highest_set_bit", "desc": "Take a positive integer n in arg0. Print the 0-based index of its highest set bit (e.g. for 13 = 0b1101 print 3).",
     "args": ["13"], "expected": "3\n",
     "python": "import sys\nn=int(sys.argv[1])\nprint(n.bit_length()-1)"},
    {"id": "and_two", "desc": "Take two non-negative integers in arg0 and arg1. Print the bitwise AND of them.",
     "args": ["12", "10"], "expected": "8\n",
     "python": "import sys\nprint(int(sys.argv[1]) & int(sys.argv[2]))"},
    {"id": "xor_two", "desc": "Take two non-negative integers in arg0 and arg1. Print the bitwise XOR of them.",
     "args": ["12", "10"], "expected": "6\n",
     "python": "import sys\nprint(int(sys.argv[1]) ^ int(sys.argv[2]))"},
    {"id": "shift_left", "desc": "Take a non-negative integer n in arg0 and a non-negative shift k in arg1. Print n shifted left by k bits.",
     "args": ["3", "4"], "expected": "48\n",
     "python": "import sys\nprint(int(sys.argv[1]) << int(sys.argv[2]))"},
]

# Batch 11: combinatorics / sequences
BATCH_11 = [
    {"id": "fibonacci_nth", "desc": "Take a non-negative integer n in arg0. Print the n-th Fibonacci number, where F(0)=0, F(1)=1.",
     "args": ["10"], "expected": "55\n",
     "python": ("import sys\nn=int(sys.argv[1]); a,b=0,1\n"
                "for _ in range(n): a,b=b,a+b\n"
                "print(a)")},
    {"id": "triangular_n", "desc": "Take a non-negative integer n in arg0. Print the n-th triangular number (1+2+...+n).",
     "args": ["7"], "expected": "28\n",
     "python": "import sys\nn=int(sys.argv[1])\nprint(n*(n+1)//2)"},
    {"id": "collatz_steps", "desc": "Take a positive integer n in arg0. Apply the Collatz rule (n→n/2 if even, n→3n+1 if odd) until n=1; print the number of steps it took.",
     "args": ["6"], "expected": "8\n",
     "python": ("import sys\nn=int(sys.argv[1]); s=0\n"
                "while n!=1:\n    n = n//2 if n%2==0 else 3*n+1\n    s+=1\n"
                "print(s)")},
    {"id": "perfect_or_not", "desc": "Take a positive integer n in arg0. Print 'yes' if n equals the sum of its proper divisors (excluding n itself), 'no' otherwise.",
     "args": ["28"], "expected": "yes\n",
     "python": ("import sys\nn=int(sys.argv[1])\n"
                "s=sum(i for i in range(1,n) if n%i==0)\n"
                "print('yes' if s==n else 'no')")},
    {"id": "divisor_count", "desc": "Take a positive integer n in arg0. Print the number of positive divisors of n (including 1 and n).",
     "args": ["12"], "expected": "6\n",
     "python": ("import sys\nn=int(sys.argv[1])\n"
                "print(sum(1 for i in range(1,n+1) if n%i==0))")},
    {"id": "geometric_partial_sum", "desc": "Take a non-negative integer n in arg0. Print the sum 1 + 2 + 4 + ... + 2^n (powers of 2 from 2^0 to 2^n inclusive).",
     "args": ["5"], "expected": "63\n",
     "python": "import sys\nn=int(sys.argv[1])\nprint((1<<(n+1)) - 1)"},
    {"id": "tribonacci_nth", "desc": "Take a non-negative integer n in arg0. Print the n-th Tribonacci number where T(0)=0, T(1)=1, T(2)=1, T(k)=T(k-1)+T(k-2)+T(k-3).",
     "args": ["7"], "expected": "24\n",
     "python": ("import sys\nn=int(sys.argv[1])\na,b,c=0,1,1\n"
                "for _ in range(n): a,b,c=b,c,a+b+c\n"
                "print(a)")},
    {"id": "sum_evens_to_n", "desc": "Take a non-negative integer n in arg0. Print the sum of even integers from 0 to n inclusive.",
     "args": ["10"], "expected": "30\n",
     "python": ("import sys\nn=int(sys.argv[1])\n"
                "print(sum(i for i in range(n+1) if i%2==0))")},
    {"id": "first_n_primes", "desc": "Take a positive integer n in arg0. Print the first n prime numbers, space-separated.",
     "args": ["5"], "expected": "2 3 5 7 11\n",
     "python": ("import sys\nn=int(sys.argv[1]); ps=[]; k=2\n"
                "while len(ps)<n:\n"
                "    if all(k%p!=0 for p in ps if p*p<=k): ps.append(k)\n    k+=1\n"
                "print(' '.join(str(p) for p in ps))")},
    {"id": "harmonic_partial_truncated", "desc": "Take a positive integer n in arg0. Print the truncated-to-3-decimal sum 1/1 + 1/2 + ... + 1/n.",
     "args": ["4"], "expected": "2.083\n",
     "python": ("import sys\nn=int(sys.argv[1])\n"
                "s=sum(1/i for i in range(1,n+1))\n"
                "print(f'{s:.3f}')")},
]

# Batch 12: misc / boundary cases
BATCH_12 = [
    {"id": "max_three", "desc": "Take three integers in arg0, arg1, arg2. Print the largest.",
     "args": ["3", "7", "5"], "expected": "7\n",
     "python": "import sys\nprint(max(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])))"},
    {"id": "min_three", "desc": "Take three integers in arg0, arg1, arg2. Print the smallest.",
     "args": ["3", "7", "5"], "expected": "3\n",
     "python": "import sys\nprint(min(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])))"},
    {"id": "clamp_value", "desc": "Take three integers x, lo, hi in arg0, arg1, arg2. Print x clamped to [lo, hi]: lo if x<lo, hi if x>hi, else x.",
     "args": ["12", "0", "10"], "expected": "10\n",
     "python": ("import sys\nx,lo,hi=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])\n"
                "print(min(hi, max(lo, x)))")},
    {"id": "celsius_to_fahrenheit", "desc": "Take an integer Celsius temperature in arg0. Print the equivalent Fahrenheit as a float with 1 decimal: F = C*9/5 + 32.",
     "args": ["100"], "expected": "212.0\n",
     "python": "import sys\nc=int(sys.argv[1])\nprint(f'{c*9/5+32:.1f}')"},
    {"id": "is_palindrome_int", "desc": "Take a non-negative integer in arg0. Print 'yes' if its decimal representation reads the same forward and backward, 'no' otherwise.",
     "args": ["12321"], "expected": "yes\n",
     "python": ("import sys\ns=sys.argv[1]\nprint('yes' if s==s[::-1] else 'no')")},
    {"id": "average_of_ints", "desc": "Take a space-separated list of integers in arg0. Print the integer floor of their arithmetic mean.",
     "args": ["1 2 3 4 5"], "expected": "3\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "print(sum(xs)//len(xs))")},
    {"id": "histogram_text", "desc": "Take a space-separated list of non-negative integers in arg0. Print one line per integer with that many '#' characters.",
     "args": ["3 1 4 2"], "expected": "###\n#\n####\n##\n",
     "python": ("import sys\nfor x in sys.argv[1].split():\n    print('#'*int(x))")},
    {"id": "first_n_evens", "desc": "Take a positive integer n in arg0. Print the first n positive even integers (2, 4, 6, ...) space-separated.",
     "args": ["4"], "expected": "2 4 6 8\n",
     "python": ("import sys\nn=int(sys.argv[1])\n"
                "print(' '.join(str(2*i) for i in range(1,n+1)))")},
    {"id": "modular_pow", "desc": "Take three positive integers base, exp, mod in arg0, arg1, arg2. Print (base^exp) mod mod efficiently (e.g. via repeated squaring).",
     "args": ["3", "5", "7"], "expected": "5\n",
     "python": ("import sys\nb,e,m=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])\n"
                "print(pow(b,e,m))")},
    {"id": "first_word_longer_than", "desc": "Take a sentence in arg0 and an integer threshold in arg1. Print the first whitespace-separated word with length > arg1. If none, print 'NONE'.",
     "args": ["hi short medium longer longest", "5"], "expected": "medium\n",
     "python": ("import sys\nws=sys.argv[1].split(); k=int(sys.argv[2])\n"
                "for w in ws:\n    if len(w)>k: print(w); break\nelse:\n    print('NONE')")},
]

ALL_BATCHES = [BATCH_3, BATCH_4, BATCH_5, BATCH_6, BATCH_7, BATCH_8,
               BATCH_9, BATCH_10, BATCH_11, BATCH_12]
