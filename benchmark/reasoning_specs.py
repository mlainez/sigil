"""50 reasoning-targeted task specs designed to bridge specific gaps in the
fine-tuned 7B's reasoning. Each spec teaches a pattern the model has been
observed to get wrong:

  - Sequence definitions with boundary clarity (15)
  - Parallel two-walk / zip-style patterns (10)
  - Cumulative / running aggregation (10)
  - String boundary handling (10)
  - State-machine scans (5)

These are NOT duplicates of any iteration_tasks.py test task. They exercise
the same idioms on structurally distinct problems.
"""

SPECS = [
    # === SEQUENCES WITH BOUNDARY CLARITY (15) ===
    # Each shows a different sequence + the EXACT boundary semantics the
    # task description specifies. The corpus must teach: "when n=k, do
    # exactly k iterations starting from these initial values."

    {"id": "fib_at_index",
     "desc": "Take a non-negative integer i in arg0. Print F(i) where F(0)=0, F(1)=1, F(k)=F(k-1)+F(k-2). For i=0 print 0; for i=10 print 55.",
     "args": ["7"], "expected": "13\n",
     "python": "import sys\ni=int(sys.argv[1])\na,b=0,1\nfor _ in range(i): a,b=b,a+b\nprint(a)"},

    {"id": "lucas_at_index",
     "desc": "Take a non-negative integer i in arg0. Print L(i) where L(0)=2, L(1)=1, L(k)=L(k-1)+L(k-2). For i=0 print 2; for i=1 print 1; for i=2 print 3.",
     "args": ["5"], "expected": "11\n",
     "python": "import sys\ni=int(sys.argv[1])\na,b=2,1\nfor _ in range(i): a,b=b,a+b\nprint(a)"},

    {"id": "trib_at_index",
     "desc": "Take a non-negative integer i in arg0. Print T(i) where T(0)=0, T(1)=1, T(2)=1, T(k)=T(k-1)+T(k-2)+T(k-3). For i=0 print 0; for i=4 print 4.",
     "args": ["6"], "expected": "13\n",
     "python": ("import sys\ni=int(sys.argv[1])\na,b,c=0,1,1\n"
                "for _ in range(i): a,b,c=b,c,a+b+c\nprint(a)")},

    {"id": "tetra_at_index",
     "desc": "Take a non-negative integer i in arg0. Print N(i) where N(0)=0, N(1)=1, N(2)=1, N(3)=2, N(k)=N(k-1)+N(k-2)+N(k-3)+N(k-4). For i=4 print 4.",
     "args": ["6"], "expected": "15\n",
     "python": ("import sys\ni=int(sys.argv[1])\na,b,c,d=0,1,1,2\n"
                "for _ in range(i): a,b,c,d=b,c,d,a+b+c+d\nprint(a)")},

    {"id": "geometric_at_index",
     "desc": "Take a non-negative integer i in arg0 and a positive integer r in arg1. Print r^i (r to the power i). For i=0 print 1; for i=3 r=2 print 8.",
     "args": ["4", "3"], "expected": "81\n",
     "python": "import sys\nprint(int(sys.argv[2])**int(sys.argv[1]))"},

    {"id": "factorial_iterative",
     "desc": "Take a non-negative integer n in arg0. Print n! using iterative multiplication. 0!=1, 5!=120.",
     "args": ["6"], "expected": "720\n",
     "python": ("import sys\nn=int(sys.argv[1]); r=1\n"
                "for i in range(2, n+1): r*=i\nprint(r)")},

    {"id": "double_each_step",
     "desc": "Take a non-negative integer n in arg0. Starting from 1, double n times and print the result. n=0 → 1, n=3 → 8.",
     "args": ["5"], "expected": "32\n",
     "python": ("import sys\nn=int(sys.argv[1]); v=1\n"
                "for _ in range(n): v*=2\nprint(v)")},

    {"id": "halve_or_triple_steps",
     "desc": "Take a positive integer n in arg0. Apply: if even halve it, else triple it and add 1. Repeat until n=1. Print number of steps. (Collatz, but report steps not stops.)",
     "args": ["6"], "expected": "8\n",
     "python": ("import sys\nn=int(sys.argv[1]); s=0\n"
                "while n!=1:\n    n = n//2 if n%2==0 else 3*n+1\n    s+=1\n"
                "print(s)")},

    {"id": "sum_geometric_to_n",
     "desc": "Take a non-negative integer n in arg0 and a positive integer r in arg1. Print 1 + r + r^2 + ... + r^n.",
     "args": ["4", "2"], "expected": "31\n",
     "python": ("import sys\nn=int(sys.argv[1]); r=int(sys.argv[2])\n"
                "print(sum(r**i for i in range(n+1)))")},

    {"id": "sum_arith_first_n",
     "desc": "Take a positive integer n and a positive integer step in args. Print sum 1 + (1+step) + (1+2*step) + ... for n terms. n=4 step=2: 1+3+5+7 = 16.",
     "args": ["5", "3"], "expected": "35\n",
     "python": ("import sys\nn=int(sys.argv[1]); s=int(sys.argv[2])\n"
                "print(sum(1 + i*s for i in range(n)))")},

    {"id": "iterate_function_n_times",
     "desc": "Take a non-negative integer n in arg0 and an integer x in arg1. Apply f(x) = 2*x + 1 exactly n times to x. Print the result. n=0 returns x.",
     "args": ["3", "1"], "expected": "15\n",
     "python": ("import sys\nn=int(sys.argv[1]); x=int(sys.argv[2])\n"
                "for _ in range(n): x = 2*x + 1\nprint(x)")},

    {"id": "sum_first_n_terms_alt",
     "desc": "Take a positive integer n in arg0. Print the sum 1 - 2 + 3 - 4 + ... + (-1)^(n+1) * n. n=4: 1-2+3-4 = -2.",
     "args": ["5"], "expected": "3\n",
     "python": ("import sys\nn=int(sys.argv[1])\n"
                "print(sum((-1)**(i+1) * i for i in range(1, n+1)))")},

    {"id": "step_count_to_zero",
     "desc": "Take a positive integer n in arg0 and a positive step in arg1. Print how many subtractions of step from n are needed before n drops to 0 or below.",
     "args": ["10", "3"], "expected": "4\n",
     "python": ("import sys\nn,s=int(sys.argv[1]),int(sys.argv[2])\n"
                "c=0\nwhile n > 0: n -= s; c += 1\nprint(c)")},

    {"id": "sum_of_powers_two",
     "desc": "Take a non-negative integer n in arg0. Print 2^0 + 2^1 + ... + 2^n. n=0 → 1; n=3 → 15.",
     "args": ["6"], "expected": "127\n",
     "python": "import sys\nn=int(sys.argv[1])\nprint((1<<(n+1)) - 1)"},

    {"id": "exponent_via_repeated_mul",
     "desc": "Take two non-negative integers base and exp in args. Print base^exp computed by iterative multiplication (no pow). 0 ^ 0 = 1.",
     "args": ["3", "5"], "expected": "243\n",
     "python": ("import sys\nb,e=int(sys.argv[1]),int(sys.argv[2])\n"
                "r=1\nfor _ in range(e): r *= b\nprint(r)")},

    # === PARALLEL TWO-WALK (10) ===
    # Teaches the model to walk two collections in lockstep using zip
    # or explicit indexing, with proper boundary handling.

    {"id": "elementwise_sum_arrays",
     "desc": "Take two space-separated lists of integers of equal length in args. Print element-wise sum, space-separated.",
     "args": ["1 2 3 4", "5 6 7 8"], "expected": "6 8 10 12\n",
     "python": ("import sys\na=[int(x) for x in sys.argv[1].split()]\n"
                "b=[int(x) for x in sys.argv[2].split()]\n"
                "print(' '.join(str(x+y) for x,y in zip(a,b)))")},

    {"id": "elementwise_max_arrays",
     "desc": "Take two space-separated lists of integers of equal length. Print element-wise max, space-separated.",
     "args": ["1 5 3 9", "4 2 8 7"], "expected": "4 5 8 9\n",
     "python": ("import sys\na=[int(x) for x in sys.argv[1].split()]\n"
                "b=[int(x) for x in sys.argv[2].split()]\n"
                "print(' '.join(str(max(x,y)) for x,y in zip(a,b)))")},

    {"id": "count_matching_positions",
     "desc": "Take two equal-length strings. Print the count of positions where the characters match.",
     "args": ["abcde", "axcye"], "expected": "3\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "print(sum(1 for x,y in zip(a,b) if x==y))")},

    {"id": "count_matching_until_diff",
     "desc": "Take two strings. Print the length of the longest common prefix (count from start until first difference or end of shorter).",
     "args": ["interview", "interest"], "expected": "5\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]; n=0\n"
                "while n<len(a) and n<len(b) and a[n]==b[n]: n+=1\n"
                "print(n)")},

    {"id": "interleave_chars_strict",
     "desc": "Take two strings of equal length. Print them interleaved character by character. Strings have exactly equal length.",
     "args": ["abc", "123"], "expected": "a1b2c3\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "print(''.join(c+d for c,d in zip(a,b)))")},

    {"id": "interleave_uneven",
     "desc": "Take two strings (possibly different lengths). Print interleaved char-by-char; once one runs out, append the remainder of the other.",
     "args": ["ab", "12345"], "expected": "a1b2345\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "out=[]; m=max(len(a),len(b))\n"
                "for i in range(m):\n"
                "    if i<len(a): out.append(a[i])\n"
                "    if i<len(b): out.append(b[i])\n"
                "print(''.join(out))")},

    {"id": "dot_product_ints",
     "desc": "Take two space-separated lists of integers of equal length. Print their dot product (sum of pairwise products).",
     "args": ["1 2 3", "4 5 6"], "expected": "32\n",
     "python": ("import sys\na=[int(x) for x in sys.argv[1].split()]\n"
                "b=[int(x) for x in sys.argv[2].split()]\n"
                "print(sum(x*y for x,y in zip(a,b)))")},

    {"id": "merge_sorted_lists",
     "desc": "Take two SORTED ascending space-separated lists of integers. Print them merged into one sorted list, space-separated.",
     "args": ["1 3 5", "2 4 6 8"], "expected": "1 2 3 4 5 6 8\n",
     "python": ("import sys\na=[int(x) for x in sys.argv[1].split()]\n"
                "b=[int(x) for x in sys.argv[2].split()]\n"
                "out=[]; i=j=0\n"
                "while i<len(a) and j<len(b):\n"
                "    if a[i]<=b[j]: out.append(a[i]); i+=1\n"
                "    else: out.append(b[j]); j+=1\n"
                "out += a[i:] + b[j:]\n"
                "print(' '.join(str(x) for x in out))")},

    {"id": "pair_sum_indices",
     "desc": "Take a space-separated list of integers and a target int. Print the 0-based indices i,j (i<j, comma-separated) of the first pair that sums to target. Print 'NONE' if no pair exists.",
     "args": ["2 7 11 15", "9"], "expected": "0,1\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "t=int(sys.argv[2]); seen={}\n"
                "for i,x in enumerate(xs):\n"
                "    if t-x in seen: print(f'{seen[t-x]},{i}'); break\n"
                "    seen[x]=i\nelse:\n    print('NONE')")},

    {"id": "diff_at_each_step",
     "desc": "Take a space-separated list of integers (length >= 2). Print the differences between consecutive elements (n-1 values), space-separated.",
     "args": ["1 3 6 10 15"], "expected": "2 3 4 5\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "print(' '.join(str(xs[i+1]-xs[i]) for i in range(len(xs)-1)))")},

    # === CUMULATIVE / RUNNING AGGREGATION (10) ===

    {"id": "running_sum",
     "desc": "Take a space-separated list of integers. Print the running sum after each prefix, space-separated.",
     "args": ["1 2 3 4 5"], "expected": "1 3 6 10 15\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "out=[]; s=0\n"
                "for x in xs: s+=x; out.append(str(s))\n"
                "print(' '.join(out))")},

    {"id": "running_product",
     "desc": "Take a space-separated list of positive integers. Print the running product after each prefix, space-separated.",
     "args": ["2 3 4 5"], "expected": "2 6 24 120\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "out=[]; p=1\n"
                "for x in xs: p*=x; out.append(str(p))\n"
                "print(' '.join(out))")},

    {"id": "running_min",
     "desc": "Take a space-separated list of integers. Print the running minimum after each prefix, space-separated.",
     "args": ["5 3 8 1 4 1"], "expected": "5 3 3 1 1 1\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "out=[]; m=xs[0]\n"
                "for x in xs:\n    if x<m: m=x\n    out.append(str(m))\n"
                "print(' '.join(out))")},

    {"id": "running_avg_truncated",
     "desc": "Take a space-separated list of integers. Print the running floor-division average after each prefix, space-separated. After k elements, average is sum_so_far // k.",
     "args": ["10 20 30 40"], "expected": "10 15 20 25\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "out=[]; s=0\n"
                "for i,x in enumerate(xs, start=1):\n    s += x; out.append(str(s//i))\n"
                "print(' '.join(out))")},

    {"id": "cumulative_count",
     "desc": "Take a string. After each character print the running count of occurrences of that character so far in the string, space-separated.",
     "args": ["abacab"], "expected": "1 1 2 1 3 2\n",
     "python": ("import sys\ns=sys.argv[1]; counts={}\n"
                "out=[]\n"
                "for c in s:\n    counts[c]=counts.get(c,0)+1; out.append(str(counts[c]))\n"
                "print(' '.join(out))")},

    {"id": "max_so_far_index",
     "desc": "Take a space-separated list of integers. Print the 0-based index of the maximum value SO FAR after each prefix, space-separated. On ties, keep the earliest.",
     "args": ["3 1 4 1 5 9 2"], "expected": "0 0 2 2 4 5 5\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "out=[]; mi=0\n"
                "for i,x in enumerate(xs):\n    if x > xs[mi]: mi=i\n    out.append(str(mi))\n"
                "print(' '.join(out))")},

    {"id": "running_unique_count",
     "desc": "Take a space-separated list of strings. After each prefix print the count of distinct strings seen so far, space-separated.",
     "args": ["a b a c b d"], "expected": "1 2 2 3 3 4\n",
     "python": ("import sys\nws=sys.argv[1].split(); seen=set(); out=[]\n"
                "for w in ws: seen.add(w); out.append(str(len(seen)))\n"
                "print(' '.join(out))")},

    {"id": "fold_string_concat",
     "desc": "Take a comma-separated list of strings. Print prefix-fold concatenations: after each prefix print all elements joined with no separator. Each result on its own line.",
     "args": ["a,b,c,d"], "expected": "a\nab\nabc\nabcd\n",
     "python": ("import sys\nws=sys.argv[1].split(','); acc=''\n"
                "for w in ws: acc += w; print(acc)")},

    {"id": "running_xor",
     "desc": "Take a space-separated list of non-negative integers. Print the running XOR after each prefix, space-separated.",
     "args": ["5 3 6 2"], "expected": "5 6 0 2\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "out=[]; v=0\n"
                "for x in xs: v ^= x; out.append(str(v))\n"
                "print(' '.join(out))")},

    {"id": "running_max_diff",
     "desc": "Take a space-separated list of integers (length >= 1). Print the running difference between max and min seen so far, space-separated.",
     "args": ["3 1 4 1 5"], "expected": "0 2 3 3 4\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "out=[]; mn=mx=xs[0]\n"
                "for x in xs:\n    if x<mn: mn=x\n    if x>mx: mx=x\n    out.append(str(mx-mn))\n"
                "print(' '.join(out))")},

    # === STRING BOUNDARY HANDLING (10) ===

    {"id": "trim_n_chars_left",
     "desc": "Take a string and a non-negative integer n. Print the string with the first n characters removed. If n >= length, print empty string.",
     "args": ["hello world", "6"], "expected": "world\n",
     "python": ("import sys\ns,n=sys.argv[1],int(sys.argv[2])\n"
                "print(s[n:] if n<=len(s) else '')")},

    {"id": "trim_n_chars_right",
     "desc": "Take a string and a non-negative integer n. Print the string with the last n characters removed.",
     "args": ["hello world", "6"], "expected": "hello\n",
     "python": ("import sys\ns,n=sys.argv[1],int(sys.argv[2])\n"
                "print(s[:-n] if 0<n<=len(s) else (s if n==0 else ''))")},

    {"id": "first_n_chars_or_all",
     "desc": "Take a string and a non-negative integer n. Print the first n characters; if string is shorter, print it in full.",
     "args": ["hello", "3"], "expected": "hel\n",
     "python": "import sys\nprint(sys.argv[1][:int(sys.argv[2])])"},

    {"id": "last_n_chars_or_all",
     "desc": "Take a string and a non-negative integer n. Print the last n characters; if shorter, print in full.",
     "args": ["hello", "3"], "expected": "llo\n",
     "python": ("import sys\ns,n=sys.argv[1],int(sys.argv[2])\n"
                "print(s[-n:] if n>0 and len(s)>=n else (s if n>0 else ''))")},

    {"id": "split_at_index",
     "desc": "Take a string and a non-negative integer i. Print the prefix of length i and the suffix on separate lines. If i >= len, print whole string then empty line.",
     "args": ["hello", "2"], "expected": "he\nllo\n",
     "python": ("import sys\ns,i=sys.argv[1],int(sys.argv[2])\n"
                "i=min(i,len(s))\nprint(s[:i])\nprint(s[i:])")},

    {"id": "remove_char_at_index",
     "desc": "Take a string and a 0-based index. Print the string with that one character removed.",
     "args": ["hello", "2"], "expected": "helo\n",
     "python": ("import sys\ns,i=sys.argv[1],int(sys.argv[2])\n"
                "print(s[:i] + s[i+1:])")},

    {"id": "insert_at_index",
     "desc": "Take three args: a string, a 0-based index, and an insertion string. Print the result with the second string inserted at that index.",
     "args": ["hello", "2", "XX"], "expected": "heXXllo\n",
     "python": ("import sys\ns,i,x=sys.argv[1],int(sys.argv[2]),sys.argv[3]\n"
                "print(s[:i] + x + s[i:])")},

    {"id": "count_chars_excluding_last",
     "desc": "Take a string and a single character. Print how many times the character appears in the string, EXCLUDING the last character of the string.",
     "args": ["banana", "a"], "expected": "2\n",
     "python": ("import sys\ns,c=sys.argv[1],sys.argv[2]\n"
                "print(s[:-1].count(c))")},

    {"id": "between_first_and_last_occurrence",
     "desc": "Take a string and a single character that appears at least twice. Print the substring strictly between the first and last occurrences (exclusive on both ends).",
     "args": ["abracadabra", "a"], "expected": "bracadabr\n",
     "python": ("import sys\ns,c=sys.argv[1],sys.argv[2]\n"
                "f=s.find(c); l=s.rfind(c)\n"
                "print(s[f+1:l])")},

    {"id": "string_window_at_index",
     "desc": "Take a string, a 0-based start index, and a positive length. Print exactly the substring of that length starting at index. If it would go past the end, print only what's available.",
     "args": ["abcdefgh", "2", "4"], "expected": "cdef\n",
     "python": ("import sys\ns,i,n=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])\n"
                "print(s[i:i+n])")},

    # === STATE-MACHINE SCANS (5) ===

    {"id": "longest_alternating_run",
     "desc": "Take a string of '0' and '1'. Print the length of the longest contiguous substring of strictly alternating characters (0101... or 1010...).",
     "args": ["110010101011"], "expected": "8\n",
     "python": ("import sys\ns=sys.argv[1]\n"
                "best=cur=1 if s else 0\n"
                "for i in range(1,len(s)):\n"
                "    if s[i]!=s[i-1]: cur+=1; best=max(best,cur)\n    else: cur=1\n"
                "print(best)")},

    {"id": "first_index_after_increase",
     "desc": "Take a space-separated list of integers. Print the 0-based index of the first element that is strictly less than its predecessor. Print -1 if the list is non-decreasing.",
     "args": ["1 2 3 5 4 7"], "expected": "4\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "for i in range(1,len(xs)):\n    if xs[i]<xs[i-1]: print(i); break\n"
                "else:\n    print(-1)")},

    {"id": "count_transitions",
     "desc": "Take a string. Print the number of positions where the character differs from its predecessor. (Length-of-runs minus 1.)",
     "args": ["aaabbcdda"], "expected": "4\n",
     "python": ("import sys\ns=sys.argv[1]\n"
                "print(sum(1 for i in range(1,len(s)) if s[i]!=s[i-1]))")},

    {"id": "first_balanced_position",
     "desc": "Take a string of '(' and ')'. Print the 0-based index right after which the running paren depth (open count minus close count) first becomes 0 starting from 0. Print -1 if depth never returns to 0.",
     "args": ["(())()"], "expected": "3\n",
     "python": ("import sys\ns=sys.argv[1]; d=0\n"
                "for i,c in enumerate(s):\n"
                "    if c=='(': d+=1\n    elif c==')': d-=1\n"
                "    if d==0 and i>0: print(i); break\n"
                "else:\n    print(-1)")},

    {"id": "longest_run_strictly_increasing",
     "desc": "Take a space-separated list of integers (length >= 1). Print the length of the longest run of strictly increasing values.",
     "args": ["1 2 3 1 2 1 5 6 2"], "expected": "3\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "best=cur=1 if xs else 0\n"
                "for i in range(1,len(xs)):\n"
                "    if xs[i]>xs[i-1]: cur+=1\n    else: cur=1\n"
                "    best=max(best,cur)\n"
                "print(best)")},
]
