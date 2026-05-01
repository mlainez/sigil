"""50 task specs targeting the 6 string-pair builtins introduced for v3:

  common_prefix, common_suffix, is_subseq, is_rotation, edit_distance,
  common_chars

Plus variadic sub / mul patterns ((sub a b c), (mul a b c)).

Each spec produces a Python reference whose stdout the corpus extender uses
as ground truth. The Sigil solutions are *expected* to use the new builtins;
the extender pipeline + the RAG layer guides the small model toward them.

These IDs do not duplicate anything in iteration_tasks.ALL_BATCHES — the
v3 corpus expansion stays disjoint from the v2 evaluation set.
"""

SPECS = [
    # === common_prefix (6) ===
    {"id": "v3_cp_two_words",
     "desc": "Take two strings in arg0 and arg1. Print the longest common prefix of the two strings (may be empty).",
     "args": ["interview", "interval"], "expected": "interv\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[i]==b[i]: i+=1\nprint(a[:i])")},
    {"id": "v3_cp_no_overlap",
     "desc": "Take two strings in arg0 and arg1. Print the longest common prefix; if none, print an empty line.",
     "args": ["apple", "banana"], "expected": "\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[i]==b[i]: i+=1\nprint(a[:i])")},
    {"id": "v3_cp_one_empty",
     "desc": "Take two strings in arg0 and arg1. Print the longest common prefix; one of them may be empty.",
     "args": ["", "anything"], "expected": "\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[i]==b[i]: i+=1\nprint(a[:i])")},
    {"id": "v3_cp_identical",
     "desc": "Take two identical strings. Print their longest common prefix (which equals either input).",
     "args": ["hello", "hello"], "expected": "hello\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[i]==b[i]: i+=1\nprint(a[:i])")},
    {"id": "v3_cp_length",
     "desc": "Take two strings in arg0 and arg1. Print the length (integer) of their longest common prefix.",
     "args": ["prefixes", "prefactor"], "expected": "4\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[i]==b[i]: i+=1\nprint(i)")},
    {"id": "v3_cp_words_equal_check",
     "desc": "Take two strings. If their longest common prefix is non-empty, print yes; otherwise print no.",
     "args": ["sunshine", "sunset"], "expected": "yes\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[i]==b[i]: i+=1\nprint('yes' if i>0 else 'no')")},

    # === common_suffix (6) ===
    {"id": "v3_cs_two_words",
     "desc": "Take two strings in arg0 and arg1. Print their longest common suffix (the trailing matching part).",
     "args": ["walking", "running"], "expected": "ing\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[len(a)-1-i]==b[len(b)-1-i]: i+=1\n"
                "print(a[len(a)-i:] if i else '')")},
    {"id": "v3_cs_no_overlap",
     "desc": "Take two strings; print their longest common suffix (may be empty).",
     "args": ["abc", "xyz"], "expected": "\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[len(a)-1-i]==b[len(b)-1-i]: i+=1\n"
                "print(a[len(a)-i:] if i else '')")},
    {"id": "v3_cs_extension",
     "desc": "Take two filenames in arg0 and arg1. Print the longest common suffix of the two filenames (the shared trailing portion, including any leading dot).",
     "args": ["report.pdf", "summary.pdf"], "expected": ".pdf\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[len(a)-1-i]==b[len(b)-1-i]: i+=1\n"
                "print(a[len(a)-i:] if i else '')")},
    {"id": "v3_cs_length",
     "desc": "Take two strings in arg0 and arg1. Print the length (integer) of their longest common suffix.",
     "args": ["loyalty", "royalty"], "expected": "6\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[len(a)-1-i]==b[len(b)-1-i]: i+=1\nprint(i)")},
    {"id": "v3_cs_match_check",
     "desc": "Take two strings. If their longest common suffix is at least 3 characters, print yes; otherwise print no.",
     "args": ["coding", "trading"], "expected": "yes\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[len(a)-1-i]==b[len(b)-1-i]: i+=1\n"
                "print('yes' if i>=3 else 'no')")},
    {"id": "v3_cs_identical",
     "desc": "Take two identical strings. Print their longest common suffix (which equals either input).",
     "args": ["pattern", "pattern"], "expected": "pattern\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "i=0\nwhile i<min(len(a),len(b)) and a[len(a)-1-i]==b[len(b)-1-i]: i+=1\n"
                "print(a[len(a)-i:] if i else '')")},

    # === is_subseq (8) ===
    {"id": "v3_subseq_simple",
     "desc": "Take two strings: a candidate in arg0 and a target in arg1. Print yes if arg1's characters appear inside arg0 in the same order (not necessarily contiguous), otherwise no.",
     "args": ["abcdef", "ace"], "expected": "yes\n",
     "python": ("import sys\nh,n=sys.argv[1],sys.argv[2]\n"
                "i=0\nfor c in h:\n  if i<len(n) and c==n[i]: i+=1\nprint('yes' if i==len(n) else 'no')")},
    {"id": "v3_subseq_no",
     "desc": "Take two strings (haystack arg0, needle arg1). Print yes if arg1 is a subsequence of arg0, no otherwise.",
     "args": ["abcdef", "afe"], "expected": "no\n",
     "python": ("import sys\nh,n=sys.argv[1],sys.argv[2]\n"
                "i=0\nfor c in h:\n  if i<len(n) and c==n[i]: i+=1\nprint('yes' if i==len(n) else 'no')")},
    {"id": "v3_subseq_empty_needle",
     "desc": "Take a haystack string in arg0 and a needle string in arg1; the needle may be empty. Print yes if arg1 is a subsequence of arg0 (an empty needle is always a subsequence), no otherwise.",
     "args": ["anything", ""], "expected": "yes\n",
     "python": ("import sys\nh,n=sys.argv[1],sys.argv[2]\n"
                "i=0\nfor c in h:\n  if i<len(n) and c==n[i]: i+=1\nprint('yes' if i==len(n) else 'no')")},
    {"id": "v3_subseq_full_match",
     "desc": "Take haystack and needle strings. Print yes if needle is a subsequence of haystack, no otherwise.",
     "args": ["programming", "prgmin"], "expected": "yes\n",
     "python": ("import sys\nh,n=sys.argv[1],sys.argv[2]\n"
                "i=0\nfor c in h:\n  if i<len(n) and c==n[i]: i+=1\nprint('yes' if i==len(n) else 'no')")},
    {"id": "v3_subseq_too_long",
     "desc": "Take haystack and needle strings. Print yes if needle is a subsequence of haystack, no otherwise.",
     "args": ["abc", "abcd"], "expected": "no\n",
     "python": ("import sys\nh,n=sys.argv[1],sys.argv[2]\n"
                "i=0\nfor c in h:\n  if i<len(n) and c==n[i]: i+=1\nprint('yes' if i==len(n) else 'no')")},
    {"id": "v3_subseq_repeated",
     "desc": "Take two strings (haystack arg0, needle arg1). Print yes if arg1 is a subsequence of arg0, no otherwise.",
     "args": ["abacaba", "aaa"], "expected": "yes\n",
     "python": ("import sys\nh,n=sys.argv[1],sys.argv[2]\n"
                "i=0\nfor c in h:\n  if i<len(n) and c==n[i]: i+=1\nprint('yes' if i==len(n) else 'no')")},
    {"id": "v3_subseq_count_chars",
     "desc": "Take haystack arg0 and needle arg1. Print the number of needle characters consumed in order while scanning haystack (the matched-prefix length of the greedy subsequence walk).",
     "args": ["zaybxc", "abc"], "expected": "3\n",
     "python": ("import sys\nh,n=sys.argv[1],sys.argv[2]\n"
                "i=0\nfor c in h:\n  if i<len(n) and c==n[i]: i+=1\nprint(i)")},
    {"id": "v3_subseq_word_match",
     "desc": "Take a long string in arg0 and a short word in arg1. If arg1 is a subsequence of arg0, print yes-N where N is the length of arg1; otherwise print no.",
     "args": ["thequickbrownfox", "qckb"], "expected": "yes-4\n",
     "python": ("import sys\nh,n=sys.argv[1],sys.argv[2]\n"
                "i=0\nfor c in h:\n  if i<len(n) and c==n[i]: i+=1\n"
                "print(f'yes-{len(n)}' if i==len(n) else 'no')")},

    # === is_rotation (6) ===
    {"id": "v3_rot_simple",
     "desc": "Take two strings (a in arg0, b in arg1). Print yes if b is a cyclic rotation of a (same length, b appears as a substring of a+a), otherwise no.",
     "args": ["abcde", "cdeab"], "expected": "yes\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "print('yes' if len(a)==len(b) and b in (a+a) and len(a)>0 else ('yes' if a==b=='' else 'no'))")},
    {"id": "v3_rot_no",
     "desc": "Take two strings (a in arg0, b in arg1). Print yes if b is a cyclic rotation of a, otherwise no.",
     "args": ["hello", "olleh"], "expected": "no\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "print('yes' if len(a)==len(b) and b in (a+a) and len(a)>0 else ('yes' if a==b=='' else 'no'))")},
    {"id": "v3_rot_diff_len",
     "desc": "Take two strings. Print yes if the second is a rotation of the first; if they have different lengths, the answer is no.",
     "args": ["abc", "abcd"], "expected": "no\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "print('yes' if len(a)==len(b) and b in (a+a) and len(a)>0 else ('yes' if a==b=='' else 'no'))")},
    {"id": "v3_rot_same",
     "desc": "Take two equal strings. Print yes if the second is a rotation of the first (a string is always a rotation of itself).",
     "args": ["python", "python"], "expected": "yes\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "print('yes' if len(a)==len(b) and b in (a+a) and len(a)>0 else ('yes' if a==b=='' else 'no'))")},
    {"id": "v3_rot_full_cycle",
     "desc": "Take two strings (a, b). Print yes if b is a cyclic rotation of a, no otherwise.",
     "args": ["abcdef", "defabc"], "expected": "yes\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "print('yes' if len(a)==len(b) and b in (a+a) and len(a)>0 else ('yes' if a==b=='' else 'no'))")},
    {"id": "v3_rot_count_shifts",
     "desc": "Take two equal-length strings. If the second is a cyclic rotation of the first, print the number of left-shifts needed; otherwise print -1.",
     "args": ["abcde", "cdeab"], "expected": "2\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if len(a)!=len(b): print(-1)\n"
                "else:\n  k=(a+a).find(b)\n  print(k if 0<=k<len(a) else -1)")},

    # === edit_distance (8) ===
    {"id": "v3_ed_classic",
     "desc": "Take two strings in arg0 and arg1. Print the Levenshtein edit distance (insertions/deletions/substitutions all cost 1).",
     "args": ["kitten", "sitting"], "expected": "3\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if len(a)<len(b): a,b=b,a\n"
                "p=list(range(len(b)+1))\n"
                "for i,ca in enumerate(a,1):\n"
                "  c=[i]+[0]*len(b)\n"
                "  for j,cb in enumerate(b,1):\n"
                "    c[j]=min(p[j]+1,c[j-1]+1,p[j-1]+(0 if ca==cb else 1))\n"
                "  p=c\nprint(p[-1])")},
    {"id": "v3_ed_zero",
     "desc": "Take two identical strings. Print their edit distance (which is 0).",
     "args": ["same", "same"], "expected": "0\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if len(a)<len(b): a,b=b,a\n"
                "p=list(range(len(b)+1))\n"
                "for i,ca in enumerate(a,1):\n"
                "  c=[i]+[0]*len(b)\n"
                "  for j,cb in enumerate(b,1):\n"
                "    c[j]=min(p[j]+1,c[j-1]+1,p[j-1]+(0 if ca==cb else 1))\n"
                "  p=c\nprint(p[-1])")},
    {"id": "v3_ed_one_off",
     "desc": "Take two strings in arg0 and arg1. Print the Levenshtein edit distance.",
     "args": ["cat", "cut"], "expected": "1\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if len(a)<len(b): a,b=b,a\n"
                "p=list(range(len(b)+1))\n"
                "for i,ca in enumerate(a,1):\n"
                "  c=[i]+[0]*len(b)\n"
                "  for j,cb in enumerate(b,1):\n"
                "    c[j]=min(p[j]+1,c[j-1]+1,p[j-1]+(0 if ca==cb else 1))\n"
                "  p=c\nprint(p[-1])")},
    {"id": "v3_ed_one_apart",
     "desc": "Take two strings. If their Levenshtein edit distance is exactly 1, print yes; otherwise print no.",
     "args": ["pale", "bale"], "expected": "yes\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if len(a)<len(b): a,b=b,a\n"
                "p=list(range(len(b)+1))\n"
                "for i,ca in enumerate(a,1):\n"
                "  c=[i]+[0]*len(b)\n"
                "  for j,cb in enumerate(b,1):\n"
                "    c[j]=min(p[j]+1,c[j-1]+1,p[j-1]+(0 if ca==cb else 1))\n"
                "  p=c\nprint('yes' if p[-1]==1 else 'no')")},
    {"id": "v3_ed_one_apart_no",
     "desc": "Take two strings. Print yes if their edit distance is exactly 1, otherwise no.",
     "args": ["pale", "tale!"], "expected": "no\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if len(a)<len(b): a,b=b,a\n"
                "p=list(range(len(b)+1))\n"
                "for i,ca in enumerate(a,1):\n"
                "  c=[i]+[0]*len(b)\n"
                "  for j,cb in enumerate(b,1):\n"
                "    c[j]=min(p[j]+1,c[j-1]+1,p[j-1]+(0 if ca==cb else 1))\n"
                "  p=c\nprint('yes' if p[-1]==1 else 'no')")},
    {"id": "v3_ed_within_k",
     "desc": "Take two strings in arg0 and arg1, plus a non-negative integer k in arg2. Print yes if their Levenshtein edit distance is at most k, otherwise no.",
     "args": ["saturday", "sunday", "3"], "expected": "yes\n",
     "python": ("import sys\na,b,k=sys.argv[1],sys.argv[2],int(sys.argv[3])\n"
                "if len(a)<len(b): a,b=b,a\n"
                "p=list(range(len(b)+1))\n"
                "for i,ca in enumerate(a,1):\n"
                "  c=[i]+[0]*len(b)\n"
                "  for j,cb in enumerate(b,1):\n"
                "    c[j]=min(p[j]+1,c[j-1]+1,p[j-1]+(0 if ca==cb else 1))\n"
                "  p=c\nprint('yes' if p[-1]<=k else 'no')")},
    {"id": "v3_ed_empty",
     "desc": "Take two strings (one may be empty). Print their Levenshtein edit distance (which equals the length of the non-empty one when one is empty).",
     "args": ["hello", ""], "expected": "5\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if len(a)<len(b): a,b=b,a\n"
                "p=list(range(len(b)+1))\n"
                "for i,ca in enumerate(a,1):\n"
                "  c=[i]+[0]*len(b)\n"
                "  for j,cb in enumerate(b,1):\n"
                "    c[j]=min(p[j]+1,c[j-1]+1,p[j-1]+(0 if ca==cb else 1))\n"
                "  p=c\nprint(p[-1])")},
    {"id": "v3_ed_anagram_check",
     "desc": "Take two strings of the same length. Print the Levenshtein edit distance.",
     "args": ["abcd", "dcba"], "expected": "4\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "if len(a)<len(b): a,b=b,a\n"
                "p=list(range(len(b)+1))\n"
                "for i,ca in enumerate(a,1):\n"
                "  c=[i]+[0]*len(b)\n"
                "  for j,cb in enumerate(b,1):\n"
                "    c[j]=min(p[j]+1,c[j-1]+1,p[j-1]+(0 if ca==cb else 1))\n"
                "  p=c\nprint(p[-1])")},

    # === common_chars (6) ===
    {"id": "v3_cc_count",
     "desc": "Take two strings in arg0 and arg1. Print the count (integer) of characters in the multiset intersection (each character counted by the minimum of its frequency in the two strings).",
     "args": ["hello", "world"], "expected": "2\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "a,b=sys.argv[1],sys.argv[2]\n"
                "ca,cb=Counter(a),Counter(b)\n"
                "print(sum((ca&cb).values()))")},
    {"id": "v3_cc_string",
     "desc": "Take two strings. Print the multiset intersection of their characters in the order they appear in arg0 (each character used at most as many times as it appears in arg1).",
     "args": ["abca", "ac"], "expected": "ac\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "a,b=sys.argv[1],sys.argv[2]\nbc=Counter(b)\n"
                "out=[]\nfor c in a:\n  if bc[c]>0: out.append(c); bc[c]-=1\nprint(''.join(out))")},
    {"id": "v3_cc_anagram_check",
     "desc": "Take two strings. If they share at least 3 characters in their multiset intersection, print yes; otherwise no.",
     "args": ["listen", "silent"], "expected": "yes\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "a,b=sys.argv[1],sys.argv[2]\n"
                "print('yes' if sum((Counter(a)&Counter(b)).values())>=3 else 'no')")},
    {"id": "v3_cc_zero",
     "desc": "Take two strings with no common characters. Print the count (integer) of common characters in their multiset intersection.",
     "args": ["abc", "xyz"], "expected": "0\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "a,b=sys.argv[1],sys.argv[2]\n"
                "print(sum((Counter(a)&Counter(b)).values()))")},
    {"id": "v3_cc_repeated",
     "desc": "Take two strings. Print the multiset-intersection count (each char minimum-of-frequencies).",
     "args": ["aabbcc", "abcabc"], "expected": "6\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "a,b=sys.argv[1],sys.argv[2]\n"
                "print(sum((Counter(a)&Counter(b)).values()))")},
    {"id": "v3_cc_subset",
     "desc": "Take two strings. Print yes if every character of arg1 (counted with multiplicity) appears in arg0, no otherwise.",
     "args": ["banana", "naa"], "expected": "yes\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "a,b=sys.argv[1],sys.argv[2]\n"
                "ca,cb=Counter(a),Counter(b)\n"
                "print('yes' if all(ca[c]>=v for c,v in cb.items()) else 'no')")},

    # === variadic sub (5) ===
    {"id": "v3_sub3",
     "desc": "Take three integers in arg0, arg1, arg2. Print the result of arg0 - arg1 - arg2.",
     "args": ["100", "10", "3"], "expected": "87\n",
     "python": "import sys\nprint(int(sys.argv[1])-int(sys.argv[2])-int(sys.argv[3]))"},
    {"id": "v3_sub4",
     "desc": "Take four integers as space-separated arg0. Print a-b-c-d (left-associative subtraction).",
     "args": ["100 10 5 3"], "expected": "82\n",
     "python": ("import sys\nxs=[int(x) for x in sys.argv[1].split()]\n"
                "r=xs[0]\nfor x in xs[1:]: r-=x\nprint(r)")},
    {"id": "v3_sub_index_arith",
     "desc": "Take a string in arg0 and two non-negative integers in arg1 and arg2. Print the 1-character string at index (length - arg1 - arg2 - 1) of the input string. Errors if the result is out of range.",
     "args": ["abcdefgh", "1", "1"], "expected": "f\n",
     "python": ("import sys\ns=sys.argv[1]; a=int(sys.argv[2]); b=int(sys.argv[3])\n"
                "print(s[len(s)-a-b-1])")},
    {"id": "v3_sub_chain_neg",
     "desc": "Take three integers. Print arg0 - arg1 - arg2.",
     "args": ["5", "10", "3"], "expected": "-8\n",
     "python": "import sys\nprint(int(sys.argv[1])-int(sys.argv[2])-int(sys.argv[3]))"},
    {"id": "v3_sub_then_compare",
     "desc": "Take three integers. If arg0 - arg1 - arg2 is greater than 0, print positive; if equal to 0, print zero; otherwise print negative.",
     "args": ["20", "5", "3"], "expected": "positive\n",
     "python": ("import sys\nv=int(sys.argv[1])-int(sys.argv[2])-int(sys.argv[3])\n"
                "print('positive' if v>0 else ('zero' if v==0 else 'negative'))")},

    # === variadic mul (5) ===
    {"id": "v3_mul3",
     "desc": "Take three integers. Print their product (a * b * c).",
     "args": ["2", "3", "4"], "expected": "24\n",
     "python": "import sys\nprint(int(sys.argv[1])*int(sys.argv[2])*int(sys.argv[3]))"},
    {"id": "v3_mul_chain",
     "desc": "Take five space-separated integers in arg0. Print the product of all of them.",
     "args": ["1 2 3 4 5"], "expected": "120\n",
     "python": ("import sys\nfrom functools import reduce\n"
                "print(reduce(lambda a,b: a*b, [int(x) for x in sys.argv[1].split()], 1))")},
    {"id": "v3_mul_volume",
     "desc": "Take three integers in arg0, arg1, arg2 representing length, width, height. Print their volume (the product).",
     "args": ["2", "3", "4"], "expected": "24\n",
     "python": "import sys\nprint(int(sys.argv[1])*int(sys.argv[2])*int(sys.argv[3]))"},
    {"id": "v3_mul_with_zero",
     "desc": "Take four integers and print their product.",
     "args": ["7", "0", "3", "9"], "expected": "0\n",
     "python": ("import sys\nfrom functools import reduce\n"
                "print(reduce(lambda a,b: a*b, [int(x) for x in sys.argv[1:5]], 1))")},
    {"id": "v3_mul_squared_volume",
     "desc": "Take an integer side length in arg0. Print side*side*side (the cube).",
     "args": ["5"], "expected": "125\n",
     "python": "import sys\ns=int(sys.argv[1])\nprint(s*s*s)"},
]


if __name__ == "__main__":
    # Smoke-validate Python references against expected stdout.
    import json, subprocess, tempfile, os
    failed = 0
    for s in SPECS:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(s["python"])
            path = f.name
        try:
            r = subprocess.run(["python3", path] + s["args"],
                               capture_output=True, text=True, timeout=10)
            got = r.stdout
            if got != s["expected"]:
                print(f"FAIL {s['id']}: got {got!r}, expected {s['expected']!r}")
                failed += 1
            else:
                print(f"  ok  {s['id']}")
        finally:
            os.unlink(path)
    print(f"\nTotal: {len(SPECS)}  failed: {failed}")
