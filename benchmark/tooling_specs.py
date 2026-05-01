"""80 host-tooling-shape task specs. These are the actual purpose of Sigil:
short scripts that an AI agent might write to traverse files, parse logs,
filter text, transform data, format output, or replace shell one-liners.

Categories:
  - Path / filename manipulation (15)
  - CSV / TSV / delimited parsing (15)
  - Log parsing and filtering (15)
  - JSON-like / config parsing (10)
  - Text transformation pipelines (15)
  - Output formatting (10)

All inputs come via CLI args (string or stdin-equivalent multi-line via
\\n-delimited arg) since Sigil's runtime model is "arg in, stdout out."
"""

SPECS = [
    # === PATH / FILENAME MANIPULATION (15) ===
    {"id": "path_split_to_components",
     "desc": "Take a Unix path in arg0. Print each non-empty path component on its own line. Leading slash is not a component.",
     "args": ["/usr/local/bin/script.sh"], "expected": "usr\nlocal\nbin\nscript.sh\n",
     "python": ("import sys\np=sys.argv[1]\n"
                "for c in p.split('/'):\n    if c: print(c)")},
    {"id": "filename_no_extension",
     "desc": "Take a filename in arg0 (no path). Print it without its extension. If no '.' is present, print unchanged.",
     "args": ["report.tar.gz"], "expected": "report.tar\n",
     "python": ("import sys\np=sys.argv[1]\n"
                "i=p.rfind('.')\nprint(p[:i] if i>0 else p)")},
    {"id": "extension_only",
     "desc": "Take a filename in arg0. Print just the extension (without leading dot). If no extension, print empty.",
     "args": ["archive.tar.gz"], "expected": "gz\n",
     "python": ("import sys\np=sys.argv[1]\n"
                "i=p.rfind('.')\nprint(p[i+1:] if i>=0 and i<len(p)-1 else '')")},
    {"id": "make_absolute_relative",
     "desc": "Take a base path arg0 and a relative path arg1. Print the absolute path (concatenated with '/' between them, no double slashes).",
     "args": ["/home/user/", "docs/file.txt"], "expected": "/home/user/docs/file.txt\n",
     "python": ("import sys\nb,r=sys.argv[1],sys.argv[2]\n"
                "if not b.endswith('/'): b+='/'\nprint(b+r)")},
    {"id": "count_path_depth",
     "desc": "Take a Unix path. Print the depth (number of '/'-separated non-empty components).",
     "args": ["/a/b/c/d"], "expected": "4\n",
     "python": "import sys\nprint(sum(1 for c in sys.argv[1].split('/') if c))"},
    {"id": "is_hidden_file",
     "desc": "Take a filename (no path). Print 'yes' if it starts with '.', 'no' otherwise.",
     "args": [".bashrc"], "expected": "yes\n",
     "python": "import sys\nprint('yes' if sys.argv[1].startswith('.') else 'no')"},
    {"id": "filter_paths_by_ext",
     "desc": "Take a newline-separated list of filenames in arg0 and a target extension in arg1 (no leading dot). Print only filenames matching that extension, one per line, preserving order.",
     "args": ["a.py\nb.txt\nc.py\nd.md", "py"], "expected": "a.py\nc.py\n",
     "python": ("import sys\next=sys.argv[2]\n"
                "for f in sys.argv[1].split('\\n'):\n"
                "    if f.endswith('.'+ext): print(f)")},
    {"id": "common_prefix_paths",
     "desc": "Take two Unix paths. Print the longest common path prefix (including trailing '/' if applicable). If no common prefix beyond '/', print '/'.",
     "args": ["/usr/local/bin/foo", "/usr/local/lib/bar"], "expected": "/usr/local/\n",
     "python": ("import sys\na,b=sys.argv[1],sys.argv[2]\n"
                "ap=a.split('/'); bp=b.split('/')\n"
                "out=[]\n"
                "for x,y in zip(ap,bp):\n    if x==y: out.append(x)\n    else: break\n"
                "p='/'.join(out)\n"
                "if p and not p.endswith('/'): p+='/'\nprint(p)")},
    {"id": "swap_extension_keep_name",
     "desc": "Take a filename and a new extension (no leading dot). Print the filename with its existing extension replaced.",
     "args": ["report.txt", "md"], "expected": "report.md\n",
     "python": ("import sys\np,e=sys.argv[1],sys.argv[2]\n"
                "i=p.rfind('.')\nprint((p[:i] if i>0 else p) + '.' + e)")},
    {"id": "basename_without_ext",
     "desc": "Take a Unix path. Print the basename with extension stripped. /a/b/c.txt -> c.",
     "args": ["/a/b/report.tar.gz"], "expected": "report.tar\n",
     "python": ("import sys\nb=sys.argv[1].rsplit('/',1)[-1]\n"
                "i=b.rfind('.')\nprint(b[:i] if i>0 else b)")},
    {"id": "join_path_segments",
     "desc": "Take a comma-separated list of path segments. Print them joined with '/' between each (no leading or trailing slash).",
     "args": ["usr,local,bin,sigil"], "expected": "usr/local/bin/sigil\n",
     "python": "import sys\nprint('/'.join(sys.argv[1].split(',')))"},
    {"id": "normalize_double_slashes",
     "desc": "Take a Unix path that may contain doubled '//' separators. Print the path with consecutive slashes collapsed to one.",
     "args": ["/usr//local///bin/sigil"], "expected": "/usr/local/bin/sigil\n",
     "python": ("import sys, re\nprint(re.sub(r'/+', '/', sys.argv[1]))")},
    {"id": "filenames_starting_with",
     "desc": "Take a newline-separated list of filenames and a prefix. Print only filenames that start with the prefix, one per line, preserving order.",
     "args": ["test_a.py\nmain.py\ntest_b.py\nlib.py", "test_"], "expected": "test_a.py\ntest_b.py\n",
     "python": ("import sys\np=sys.argv[2]\n"
                "for f in sys.argv[1].split('\\n'):\n"
                "    if f.startswith(p): print(f)")},
    {"id": "ext_count",
     "desc": "Take a newline-separated list of filenames. Print each distinct extension and its count formatted 'EXT:N', sorted by extension alphabetically, space-separated. Files without extension grouped under 'NONE'.",
     "args": ["a.py\nb.txt\nc.py\nMakefile\nd.md\ne.py"], "expected": "NONE:1 md:1 py:3 txt:1\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "c=Counter()\n"
                "for f in sys.argv[1].split('\\n'):\n"
                "    if '.' not in f: c['NONE']+=1\n    else: c[f.rsplit('.',1)[1]]+=1\n"
                "print(' '.join(f'{k}:{c[k]}' for k in sorted(c)))")},
    {"id": "parent_directory",
     "desc": "Take a Unix path. Print its parent directory (everything before the last '/'). If no '/' or path is just '/', print '/'.",
     "args": ["/usr/local/bin/script.sh"], "expected": "/usr/local/bin\n",
     "python": ("import sys\np=sys.argv[1]\n"
                "if '/' not in p: print('/')\nelse:\n    r=p.rsplit('/',1)[0]\n    print(r if r else '/')")},

    # === CSV / TSV / DELIMITED PARSING (15) ===
    {"id": "csv_first_column",
     "desc": "Take a CSV string (rows separated by newlines, fields by commas) and a 0-based column index. Print that column's value from each row, one per line.",
     "args": ["a,1\nb,2\nc,3", "0"], "expected": "a\nb\nc\n",
     "python": ("import sys\ni=int(sys.argv[2])\n"
                "for r in sys.argv[1].split('\\n'):\n    print(r.split(',')[i])")},
    {"id": "csv_skip_header_print_col",
     "desc": "Take a CSV (first row is header) and a column NAME. Print that column's values for data rows only, one per line.",
     "args": ["name,age\nalice,30\nbob,25", "age"], "expected": "30\n25\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\n"
                "h=rows[0].split(','); i=h.index(sys.argv[2])\n"
                "for r in rows[1:]: print(r.split(',')[i])")},
    {"id": "tsv_count_rows",
     "desc": "Take a TSV string (rows separated by newlines, fields by tabs). Print the number of rows.",
     "args": ["a\\tb\nc\\td"], "expected": "2\n",
     "python": "import sys\nprint(len(sys.argv[1].split('\\n')))"},
    {"id": "csv_sum_numeric_col",
     "desc": "Take a CSV with header and a numeric column name. Print the sum of integer values in that column across data rows.",
     "args": ["item,qty\napple,5\nbanana,3\ncherry,7", "qty"], "expected": "15\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\n"
                "h=rows[0].split(','); i=h.index(sys.argv[2])\n"
                "print(sum(int(r.split(',')[i]) for r in rows[1:]))")},
    {"id": "csv_max_numeric_col",
     "desc": "Take a CSV with header and a numeric column name. Print the max integer value in that column across data rows.",
     "args": ["item,price\nA,10\nB,25\nC,7", "price"], "expected": "25\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\n"
                "h=rows[0].split(','); i=h.index(sys.argv[2])\n"
                "print(max(int(r.split(',')[i]) for r in rows[1:]))")},
    {"id": "csv_select_two_cols",
     "desc": "Take a CSV with header and two column names. Print those two columns from data rows in 'A=B' format, one per line.",
     "args": ["name,role,age\nalice,dev,30\nbob,pm,25", "name", "role"], "expected": "alice=dev\nbob=pm\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\n"
                "h=rows[0].split(','); i=h.index(sys.argv[2]); j=h.index(sys.argv[3])\n"
                "for r in rows[1:]:\n    f=r.split(','); print(f'{f[i]}={f[j]}')")},
    {"id": "csv_filter_rows_by_col",
     "desc": "Take CSV with header, a column name, and a value. Print full data rows where that column equals the value, one per line.",
     "args": ["name,role\nalice,dev\nbob,pm\ncarol,dev", "role", "dev"], "expected": "alice,dev\ncarol,dev\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\n"
                "h=rows[0].split(','); i=h.index(sys.argv[2])\n"
                "for r in rows[1:]:\n    if r.split(',')[i]==sys.argv[3]: print(r)")},
    {"id": "csv_count_rows_matching",
     "desc": "Take CSV with header, a column name, and a value. Print the count of data rows where that column equals the value.",
     "args": ["x,y\n1,a\n2,b\n3,a\n4,a", "y", "a"], "expected": "3\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\n"
                "h=rows[0].split(','); i=h.index(sys.argv[2])\n"
                "print(sum(1 for r in rows[1:] if r.split(',')[i]==sys.argv[3]))")},
    {"id": "csv_distinct_in_col",
     "desc": "Take CSV with header and a column name. Print distinct values in that column, sorted alphabetically, one per line.",
     "args": ["a,b\n1,x\n2,y\n3,x\n4,z", "b"], "expected": "x\ny\nz\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\n"
                "h=rows[0].split(','); i=h.index(sys.argv[2])\n"
                "vals={r.split(',')[i] for r in rows[1:]}\n"
                "for v in sorted(vals): print(v)")},
    {"id": "csv_replace_value",
     "desc": "Take CSV with header, a column name, an old value, and a new value. Print the CSV with that column's matching values replaced. Header stays.",
     "args": ["a,b\n1,x\n2,y\n3,x", "b", "x", "Z"], "expected": "a,b\n1,Z\n2,y\n3,Z\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n'); col=sys.argv[2]\n"
                "old=sys.argv[3]; new=sys.argv[4]\n"
                "h=rows[0].split(','); i=h.index(col)\n"
                "out=[rows[0]]\n"
                "for r in rows[1:]:\n    f=r.split(',')\n    if f[i]==old: f[i]=new\n    out.append(','.join(f))\n"
                "print('\\n'.join(out))")},
    {"id": "split_pipe_delimited",
     "desc": "Take a pipe-delimited string. Print each field on its own line.",
     "args": ["alice|30|dev"], "expected": "alice\n30\ndev\n",
     "python": ("import sys\nfor f in sys.argv[1].split('|'): print(f)")},
    {"id": "fields_to_aligned_table",
     "desc": "Take a CSV with no header (rows of equal-length records). Print each row with fields separated by exactly two spaces.",
     "args": ["a,bb,ccc\nd,e,f"], "expected": "a  bb  ccc\nd  e  f\n",
     "python": ("import sys\n"
                "for r in sys.argv[1].split('\\n'):\n    print('  '.join(r.split(',')))")},
    {"id": "csv_first_n_rows",
     "desc": "Take CSV (no header) and a positive integer n. Print the first n rows joined by newlines.",
     "args": ["a\nb\nc\nd\ne", "3"], "expected": "a\nb\nc\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n'); n=int(sys.argv[2])\n"
                "print('\\n'.join(rows[:n]))")},
    {"id": "csv_last_n_rows",
     "desc": "Take CSV (no header) and positive n. Print the last n rows joined by newlines.",
     "args": ["a\nb\nc\nd\ne", "2"], "expected": "d\ne\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n'); n=int(sys.argv[2])\n"
                "print('\\n'.join(rows[-n:]))")},
    {"id": "csv_avg_numeric_col_floor",
     "desc": "Take CSV with header and numeric column name. Print floor average of integer values in that column.",
     "args": ["x,n\na,10\nb,20\nc,30", "n"], "expected": "20\n",
     "python": ("import sys\nrows=sys.argv[1].split('\\n')\n"
                "h=rows[0].split(','); i=h.index(sys.argv[2])\n"
                "vs=[int(r.split(',')[i]) for r in rows[1:]]\n"
                "print(sum(vs)//len(vs))")},

    # === LOG PARSING AND FILTERING (15) ===
    {"id": "log_count_by_level",
     "desc": "Take multi-line log; each line starts with INFO, WARN, or ERROR. Print 'INFO:N WARN:N ERROR:N' (in that order, space-separated).",
     "args": ["INFO ok\nWARN slow\nERROR boom\nINFO again\nERROR fail"],
     "expected": "INFO:2 WARN:1 ERROR:2\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "c=Counter(line.split(' ',1)[0] for line in sys.argv[1].split('\\n'))\n"
                "print(' '.join(f'{lv}:{c.get(lv,0)}' for lv in ['INFO','WARN','ERROR']))")},
    {"id": "log_first_error",
     "desc": "Take multi-line log. Print the message portion (everything after the first space) of the FIRST line whose level is ERROR. Print 'NONE' if no ERROR.",
     "args": ["INFO ok\nWARN slow\nERROR boom\nERROR fail"],
     "expected": "boom\n",
     "python": ("import sys\nfor l in sys.argv[1].split('\\n'):\n"
                "    if l.startswith('ERROR '): print(l[6:]); break\nelse:\n    print('NONE')")},
    {"id": "log_extract_levels",
     "desc": "Take multi-line log. Print each line's level (first whitespace-separated token), one per line.",
     "args": ["INFO a\nWARN b\nERROR c\nINFO d"],
     "expected": "INFO\nWARN\nERROR\nINFO\n",
     "python": ("import sys\n"
                "for l in sys.argv[1].split('\\n'): print(l.split(' ',1)[0])")},
    {"id": "log_grep_substring",
     "desc": "Take multi-line log and a substring. Print only lines that contain the substring, in order.",
     "args": ["start\nfile read\nopen\nfile write\nclose", "file"],
     "expected": "file read\nfile write\n",
     "python": ("import sys\nq=sys.argv[2]\n"
                "for l in sys.argv[1].split('\\n'):\n    if q in l: print(l)")},
    {"id": "log_grep_v",
     "desc": "Take multi-line log and a substring. Print only lines that DO NOT contain the substring, in order.",
     "args": ["a\nb error c\nd\ne error f", "error"],
     "expected": "a\nd\n",
     "python": ("import sys\nq=sys.argv[2]\n"
                "for l in sys.argv[1].split('\\n'):\n    if q not in l: print(l)")},
    {"id": "log_unique_lines",
     "desc": "Take multi-line log. Print distinct lines in the order they first appear, one per line.",
     "args": ["a\nb\na\nc\nb\nd"],
     "expected": "a\nb\nc\nd\n",
     "python": ("import sys\nseen=set()\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if l not in seen: seen.add(l); print(l)")},
    {"id": "log_count_distinct",
     "desc": "Take multi-line log. Print the count of distinct lines.",
     "args": ["a\nb\na\nc\nb\nd"],
     "expected": "4\n",
     "python": "import sys\nprint(len(set(sys.argv[1].split('\\n'))))"},
    {"id": "log_count_word",
     "desc": "Take multi-line log and a word. Print the total number of times that word (whitespace-delimited) appears across all lines.",
     "args": ["error here\nno error\nerror error", "error"],
     "expected": "4\n",
     "python": ("import sys\nq=sys.argv[2]\n"
                "print(sum(line.split().count(q) for line in sys.argv[1].split('\\n')))")},
    {"id": "log_first_n_unique",
     "desc": "Take multi-line log and positive int n. Print the first n distinct lines (in first-appearance order), one per line.",
     "args": ["x\ny\nx\nz\nw\nz", "3"],
     "expected": "x\ny\nz\n",
     "python": ("import sys\nseen=set(); n=int(sys.argv[2]); cnt=0\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if l not in seen and cnt<n:\n        seen.add(l); print(l); cnt+=1")},
    {"id": "log_top_n_words",
     "desc": "Take multi-line log and positive int n. Print top-n most-frequent whitespace-tokens across all lines, ties broken by first-appearance order, space-separated.",
     "args": ["a b a c\nb a d", "2"],
     "expected": "a b\n",
     "python": ("import sys\nfrom collections import Counter\n"
                "tokens=[]\n"
                "for line in sys.argv[1].split('\\n'): tokens += line.split()\n"
                "first={}\n"
                "for i,t in enumerate(tokens): first.setdefault(t,i)\n"
                "c=Counter(tokens)\n"
                "ranked=sorted(c.keys(), key=lambda x:(-c[x], first[x]))\n"
                "n=int(sys.argv[2])\n"
                "print(' '.join(ranked[:n]))")},
    {"id": "log_lines_starting_with_digit",
     "desc": "Take multi-line log. Print only lines whose first character is a decimal digit.",
     "args": ["abc\n1: ok\n2: fail\nxyz"],
     "expected": "1: ok\n2: fail\n",
     "python": ("import sys\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if l and l[0].isdigit(): print(l)")},
    {"id": "log_strip_blank_lines",
     "desc": "Take multi-line log. Print all non-blank lines (lines that are not empty after stripping whitespace) in order.",
     "args": ["a\n\nb\n  \nc"],
     "expected": "a\nb\nc\n",
     "python": ("import sys\n"
                "for l in sys.argv[1].split('\\n'):\n    if l.strip(): print(l)")},
    {"id": "log_word_count_per_line",
     "desc": "Take multi-line log. Print 'NUM: line' for each line, where NUM is the count of whitespace-separated tokens. Numbers right-aligned to width 3.",
     "args": ["a b c\none\n  multi  spaces  here  ok"],
     "expected": "  3: a b c\n  1: one\n  4:   multi  spaces  here  ok\n",
     "python": ("import sys\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    n=len(l.split())\n    print(f'{n:>3}: {l}')")},
    {"id": "log_truncate_lines",
     "desc": "Take multi-line log and positive int n. Print each line truncated to at most n characters.",
     "args": ["hello world\nfoo\nbar baz", "5"],
     "expected": "hello\nfoo\nbar b\n",
     "python": ("import sys\nn=int(sys.argv[2])\n"
                "for l in sys.argv[1].split('\\n'): print(l[:n])")},
    {"id": "log_lines_between_markers",
     "desc": "Take multi-line log, a start marker, an end marker. Print lines strictly BETWEEN the first occurrence of start and the next occurrence of end (exclusive). Empty if not found.",
     "args": ["a\nSTART\nx\ny\nEND\nz", "START", "END"],
     "expected": "x\ny\n",
     "python": ("import sys\nlines=sys.argv[1].split('\\n')\n"
                "s,e=sys.argv[2],sys.argv[3]\n"
                "try: si=lines.index(s)\nexcept ValueError: print(''); sys.exit()\n"
                "try: ei=lines.index(e, si+1)\nexcept ValueError: print(''); sys.exit()\n"
                "print('\\n'.join(lines[si+1:ei]))")},

    # === JSON-LIKE / CONFIG PARSING (10) ===
    {"id": "config_count_lines",
     "desc": "Take a config string (lines of 'key=value'). Print the count of lines that have an '=' separator.",
     "args": ["a=1\nb=2\nbroken line\nc=3"],
     "expected": "3\n",
     "python": ("import sys\n"
                "print(sum(1 for l in sys.argv[1].split('\\n') if '=' in l))")},
    {"id": "config_to_lookup",
     "desc": "Take a config string (key=value lines) and a key. Print the value if found, otherwise 'NONE'.",
     "args": ["host=localhost\nport=8080\nuser=admin", "port"],
     "expected": "8080\n",
     "python": ("import sys\nk=sys.argv[2]\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l:\n        kk,v=l.split('=',1)\n"
                "        if kk==k: print(v); break\nelse:\n    print('NONE')")},
    {"id": "config_keys_in_order",
     "desc": "Take a config string. Print all keys (LHS of '=') in their original order, one per line.",
     "args": ["a=1\nb=2\nc=3"],
     "expected": "a\nb\nc\n",
     "python": ("import sys\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l: print(l.split('=',1)[0])")},
    {"id": "config_replace_value",
     "desc": "Take a config string, a key, and a new value. Print the config with that key's value replaced. Other lines unchanged.",
     "args": ["a=1\nb=2\nc=3", "b", "99"],
     "expected": "a=1\nb=99\nc=3\n",
     "python": ("import sys\nk,v=sys.argv[2],sys.argv[3]; out=[]\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l:\n        kk,_=l.split('=',1)\n"
                "        if kk==k: out.append(f'{k}={v}'); continue\n"
                "    out.append(l)\n"
                "print('\\n'.join(out))")},
    {"id": "config_remove_key",
     "desc": "Take a config string and a key to remove. Print the config without any line whose key matches.",
     "args": ["a=1\nb=2\nc=3\nb=4", "b"],
     "expected": "a=1\nc=3\n",
     "python": ("import sys\nk=sys.argv[2]; out=[]\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l and l.split('=',1)[0]==k: continue\n"
                "    out.append(l)\n"
                "print('\\n'.join(out))")},
    {"id": "config_sum_numeric",
     "desc": "Take a config string. Sum the integer values of all lines whose value is a valid integer. Print the total. Skip non-integer values.",
     "args": ["a=10\nb=foo\nc=20\nd=30"],
     "expected": "60\n",
     "python": ("import sys\ntotal=0\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l:\n        v=l.split('=',1)[1]\n"
                "        try: total+=int(v)\n        except ValueError: pass\n"
                "print(total)")},
    {"id": "kv_format_to_csv",
     "desc": "Take a config string. Print as a 2-column CSV with header 'key,value'.",
     "args": ["a=1\nb=2\nc=3"],
     "expected": "key,value\na,1\nb,2\nc,3\n",
     "python": ("import sys\nout=['key,value']\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l:\n        k,v=l.split('=',1); out.append(f'{k},{v}')\n"
                "print('\\n'.join(out))")},
    {"id": "json_like_kv_pairs",
     "desc": "Take a JSON-like flat object string in arg0 (e.g. '{\"a\": 1, \"b\": 2}'). Print each key:value on its own line, preserving order.",
     "args": ["{\"a\": 1, \"b\": 2, \"c\": 3}"],
     "expected": "a:1\nb:2\nc:3\n",
     "python": ("import sys, json\nd=json.loads(sys.argv[1])\n"
                "for k,v in d.items(): print(f'{k}:{v}')")},
    {"id": "config_double_check",
     "desc": "Take config string and two keys. Print 'BOTH' if both keys exist, 'FIRST' if only first, 'SECOND' if only second, 'NEITHER' if neither.",
     "args": ["host=x\nport=80", "host", "user"],
     "expected": "FIRST\n",
     "python": ("import sys\nk1,k2=sys.argv[2],sys.argv[3]\n"
                "keys={l.split('=',1)[0] for l in sys.argv[1].split('\\n') if '=' in l}\n"
                "a,b=k1 in keys, k2 in keys\n"
                "print('BOTH' if a and b else 'FIRST' if a else 'SECOND' if b else 'NEITHER')")},
    {"id": "kv_reverse_lookup",
     "desc": "Take a config string and a value. Print all keys whose value matches, sorted alphabetically, one per line. Print empty if none.",
     "args": ["a=x\nb=y\nc=x\nd=z", "x"],
     "expected": "a\nc\n",
     "python": ("import sys\nv=sys.argv[2]; ks=[]\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l:\n        k,vv=l.split('=',1)\n        if vv==v: ks.append(k)\n"
                "for k in sorted(ks): print(k)")},

    # === TEXT TRANSFORMATION PIPELINES (15) ===
    {"id": "uppercase_first_letter_each_word",
     "desc": "Take a sentence. Print it with the first letter of each whitespace-separated word uppercased, rest lowercased.",
     "args": ["heLLo woRLd"],
     "expected": "Hello World\n",
     "python": "import sys\nprint(' '.join(w[:1].upper()+w[1:].lower() for w in sys.argv[1].split()))"},
    {"id": "remove_vowels",
     "desc": "Take a string. Print it with all ASCII vowels (aeiouAEIOU) removed.",
     "args": ["Hello World"],
     "expected": "Hll Wrld\n",
     "python": ("import sys\nprint(''.join(c for c in sys.argv[1] if c not in 'aeiouAEIOU'))")},
    {"id": "keep_only_alpha",
     "desc": "Take a string. Print only its ASCII letters (a-z, A-Z), preserving order.",
     "args": ["abc-123-DEF.ghi!"],
     "expected": "abcDEFghi\n",
     "python": "import sys\nprint(''.join(c for c in sys.argv[1] if c.isalpha()))"},
    {"id": "kebab_to_snake",
     "desc": "Take a kebab-case string. Print it converted to snake_case (replace - with _).",
     "args": ["my-cool-thing"],
     "expected": "my_cool_thing\n",
     "python": "import sys\nprint(sys.argv[1].replace('-','_'))"},
    {"id": "snake_to_kebab",
     "desc": "Take snake_case. Print kebab-case.",
     "args": ["my_cool_thing"],
     "expected": "my-cool-thing\n",
     "python": "import sys\nprint(sys.argv[1].replace('_','-'))"},
    {"id": "trim_each_line",
     "desc": "Take multi-line string. Print each line with leading and trailing whitespace stripped.",
     "args": ["  a  \n\tb\t\n c "],
     "expected": "a\nb\nc\n",
     "python": ("import sys\nfor l in sys.argv[1].split('\\n'): print(l.strip())")},
    {"id": "indent_lines_n",
     "desc": "Take multi-line string and a non-negative integer n. Print each line prefixed with n spaces.",
     "args": ["a\nb\nc", "4"],
     "expected": "    a\n    b\n    c\n",
     "python": ("import sys\np=' '*int(sys.argv[2])\n"
                "for l in sys.argv[1].split('\\n'): print(p+l)")},
    {"id": "normalize_whitespace",
     "desc": "Take a string. Print it with all runs of whitespace collapsed to a single space, and leading/trailing whitespace stripped.",
     "args": ["  hello   world\t\nfoo  "],
     "expected": "hello world foo\n",
     "python": "import sys\nprint(' '.join(sys.argv[1].split()))"},
    {"id": "replace_substring",
     "desc": "Take three args: source string, target substring, replacement. Print source with all non-overlapping occurrences of target replaced.",
     "args": ["banana", "an", "X"],
     "expected": "bXXa\n",
     "python": "import sys\nprint(sys.argv[1].replace(sys.argv[2], sys.argv[3]))"},
    {"id": "wrap_each_line_with",
     "desc": "Take multi-line string and a wrapping string. Print each line with the wrapper before AND after.",
     "args": ["a\nb\nc", "##"],
     "expected": "##a##\n##b##\n##c##\n",
     "python": ("import sys\nw=sys.argv[2]\n"
                "for l in sys.argv[1].split('\\n'): print(w+l+w)")},
    {"id": "number_each_line",
     "desc": "Take multi-line string. Print each line prefixed with its 1-based number followed by ': '.",
     "args": ["alpha\nbeta\ngamma"],
     "expected": "1: alpha\n2: beta\n3: gamma\n",
     "python": ("import sys\n"
                "for i,l in enumerate(sys.argv[1].split('\\n'), start=1): print(f'{i}: {l}')")},
    {"id": "first_char_of_each_word",
     "desc": "Take a sentence. Print the concatenation of the first character of each whitespace-separated word.",
     "args": ["the quick brown fox"],
     "expected": "tqbf\n",
     "python": "import sys\nprint(''.join(w[0] for w in sys.argv[1].split() if w))"},
    {"id": "remove_consecutive_duplicates",
     "desc": "Take a string. Print it with each maximal run of identical chars collapsed to a single char.",
     "args": ["aaabbcccd"],
     "expected": "abcd\n",
     "python": ("import sys\ns=sys.argv[1]; out=[]\n"
                "for c in s:\n    if not out or out[-1]!=c: out.append(c)\n"
                "print(''.join(out))")},
    {"id": "wrap_text_at_n",
     "desc": "Take a sentence and a positive integer n. Greedily wrap into lines of width <= n (words separated by single space). Print each wrapped line.",
     "args": ["the quick brown fox jumps over", "10"],
     "expected": "the quick\nbrown fox\njumps over\n",
     "python": ("import sys, textwrap\n"
                "for l in textwrap.wrap(sys.argv[1], int(sys.argv[2])): print(l)")},
    {"id": "expand_tabs",
     "desc": "Take a string and a positive integer n. Print the string with each tab character replaced by n spaces.",
     "args": ["a\tb\tc", "4"],
     "expected": "a    b    c\n",
     "python": ("import sys\nprint(sys.argv[1].replace('\\t', ' '*int(sys.argv[2])))")},

    # === OUTPUT FORMATTING (10) ===
    {"id": "format_kv_table_two_col",
     "desc": "Take a config string. Print as a 2-column right-aligned table where keys are right-aligned to the longest key length.",
     "args": ["a=1\nbb=2\nccc=3"],
     "expected": "  a = 1\n bb = 2\nccc = 3\n",
     "python": ("import sys\nrows=[]\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l: rows.append(l.split('=',1))\n"
                "w=max(len(k) for k,_ in rows)\n"
                "for k,v in rows: print(f'{k:>{w}} = {v}')")},
    {"id": "json_print_object_compact",
     "desc": "Take a config string. Print it as a compact JSON object: {\"k\": \"v\", \"k2\": \"v2\"}. String values are quoted.",
     "args": ["a=1\nb=2"],
     "expected": "{\"a\": \"1\", \"b\": \"2\"}\n",
     "python": ("import sys\nparts=[]\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l:\n        k,v=l.split('=',1); parts.append(f'\"{k}\": \"{v}\"')\n"
                "print('{' + ', '.join(parts) + '}')")},
    {"id": "format_int_thousands",
     "desc": "Take an integer in arg0. Print it with comma thousands separators.",
     "args": ["1234567"],
     "expected": "1,234,567\n",
     "python": "import sys\nprint(f'{int(sys.argv[1]):,}')"},
    {"id": "format_float_two_decimals",
     "desc": "Take a numeric string in arg0. Print it as a float with exactly 2 decimal places.",
     "args": ["3.14159"],
     "expected": "3.14\n",
     "python": "import sys\nprint(f'{float(sys.argv[1]):.2f}')"},
    {"id": "right_align_to_width",
     "desc": "Take a string and a positive integer width. Print the string right-aligned in a field of that width using spaces.",
     "args": ["hi", "6"],
     "expected": "    hi\n",
     "python": "import sys\nprint(sys.argv[1].rjust(int(sys.argv[2])))"},
    {"id": "left_align_to_width",
     "desc": "Take a string and a positive integer width. Print left-aligned with trailing spaces to width. Print pipe at end to make trailing whitespace visible.",
     "args": ["hi", "6"],
     "expected": "hi    |\n",
     "python": "import sys\nprint(sys.argv[1].ljust(int(sys.argv[2])) + '|')"},
    {"id": "render_histogram_hashes",
     "desc": "Take a space-separated list of non-negative integers. For each, print one line with that many '#' characters.",
     "args": ["3 1 5"],
     "expected": "###\n#\n#####\n",
     "python": ("import sys\n"
                "for n in sys.argv[1].split(): print('#'*int(n))")},
    {"id": "render_aligned_pairs",
     "desc": "Take a config string. Print key:value pairs as right-aligned 'key=value' rows, where the right side is padded so all '=' align.",
     "args": ["a=1\nbbb=2\ncc=3"],
     "expected": "  a=1\nbbb=2\n cc=3\n",
     "python": ("import sys\nrows=[]\n"
                "for l in sys.argv[1].split('\\n'):\n"
                "    if '=' in l: rows.append(l.split('=',1))\n"
                "w=max(len(k) for k,_ in rows)\n"
                "for k,v in rows: print(f'{k:>{w}}={v}')")},
    {"id": "ordinal_suffix",
     "desc": "Take a positive integer in arg0. Print the integer with its English ordinal suffix appended (1st, 2nd, 3rd, 4th, ..., 11th, 12th, 13th, 21st, 22nd, ...).",
     "args": ["22"],
     "expected": "22nd\n",
     "python": ("import sys\nn=int(sys.argv[1])\n"
                "if 11<=(n%100)<=13: s='th'\nelse: s={1:'st',2:'nd',3:'rd'}.get(n%10,'th')\n"
                "print(f'{n}{s}')")},
    {"id": "human_readable_bytes",
     "desc": "Take a non-negative integer byte count in arg0. Print it as 'X.YZ B/KB/MB/GB/TB' with 2 decimal places, choosing the largest unit where the value is >= 1.",
     "args": ["1536"],
     "expected": "1.50 KB\n",
     "python": ("import sys\nn=float(sys.argv[1])\n"
                "for unit in ['B','KB','MB','GB','TB']:\n"
                "    if n < 1024 or unit == 'TB':\n        print(f'{n:.2f} {unit}'); break\n"
                "    n /= 1024")},
]
