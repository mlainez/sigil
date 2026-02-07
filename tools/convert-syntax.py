#!/usr/bin/env python3
"""
Convert AISL files from nested parameter syntax to flat syntax.
OLD: (fn add ((a i32) (b i32)) -> i32
NEW: (fn add a i32 b i32 -> i32
"""

import re
import sys
from pathlib import Path

def convert_function_params(content):
    """Convert nested param syntax to flat syntax"""
    
    # Pattern: (fn name ((p1 t1) (p2 t2) ...) -> type
    # Replace with: (fn name p1 t1 p2 t2 -> type
    
    def replace_params(match):
        fn_keyword = match.group(1)
        fn_name = match.group(2)
        params_str = match.group(3)
        rest = match.group(4)
        
        # Extract individual parameters from ((p1 t1) (p2 t2))
        # Pattern: (name type)
        param_pattern = r'\((\w+)\s+(\w+)\)'
        params = re.findall(param_pattern, params_str)
        
        if not params:
            # No parameters case: (fn name () -> type
            return f'{fn_keyword} {fn_name} -> {rest}'
        
        # Build flat parameter list: p1 t1 p2 t2
        flat_params = ' '.join(f'{name} {typ}' for name, typ in params)
        
        return f'{fn_keyword} {fn_name} {flat_params} -> {rest}'
    
    # Match function definitions with nested params
    # Pattern: (fn <name> ((<params>)*) -> <rest>
    pattern = r'\((fn)\s+(\w+)\s+\(([^)]*(?:\([^)]*\)[^)]*)*)\)\s+->\s+(.+)'
    
    converted = re.sub(pattern, replace_params, content)
    return converted

def main():
    if len(sys.argv) < 2:
        print("Usage: convert-syntax.py <file1.aisl> [file2.aisl ...]")
        print("   or: convert-syntax.py tests/*.aisl")
        sys.exit(1)
    
    for file_path in sys.argv[1:]:
        path = Path(file_path)
        if not path.exists():
            print(f"Skip: {path} (not found)")
            continue
        
        content = path.read_text()
        converted = convert_function_params(content)
        
        if content != converted:
            path.write_text(converted)
            print(f"✓ Converted: {path}")
        else:
            print(f"  Unchanged: {path}")

if __name__ == '__main__':
    main()
