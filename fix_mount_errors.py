#!/usr/bin/env python3
"""
fix_mount_errors.py
===================
Fixes Textual MountError by ensuring all containers are mounted to DOM before adding children.

Run this to auto-fix all tab files.
"""

from pathlib import Path
import re

def fix_file(filepath: Path) -> bool:
    """Fix mounting order in a single file."""
    print(f"Fixing {filepath.name}...")
    
    content = filepath.read_text(encoding='utf-8')
    original = content
    
    # Common patterns to fix:
    # Pattern 1: container.mount(child) before pane.mount(container)
    # Solution: Move pane.mount(container) to right after container creation
    
    # This is a simplified auto-fixer - manual fixing might be needed for complex cases
    lines = content.split('\n')
    fixed_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Detect container creation (Vertical/Horizontal)
        if re.match(r'\s+([\w_]+)\s*=\s*(Vertical|Horizontal)\(', line):
            var_name = re.match(r'\s+([\w_]+)\s*=\s*(Vertical|Horizontal)\(', line).group(1)
            fixed_lines.append(line)
            i += 1
            
            # Look ahead - if next line is NOT pane.mount, add it
            if i < len(lines):
                next_line = lines[i]
                if 'pane.mount(' + var_name not in next_line and var_name + '.mount(' in next_line:
                    # Insert pane.mount before first child mount
                    indent = len(line) - len(line.lstrip())
                    fixed_lines.append(' ' * indent + f'pane.mount({var_name})')
        else:
            fixed_lines.append(line)
            i += 1
    
    new_content = '\n'.join(fixed_lines)
    
    if new_content != original:
        filepath.write_text(new_content, encoding='utf-8')
        print(f"  ✅ Fixed {filepath.name}")
        return True
    else:
        print(f"  ℹ️  No changes needed for {filepath.name}")
        return False

def main():
    """Fix all tab files."""
    tabs_dir = Path(__file__).parent / 'ui' / 'tabs'
    
    if not tabs_dir.exists():
        print(f"❌ Directory not found: {tabs_dir}")
        return
    
    files_to_fix = [
        'java_tab.py',
        'plugins_tab.py',
        'editor_tab.py',
        'eula_tab.py',
    ]
    
    print("🔧 Fixing Textual MountError issues...\n")
    
    fixed = 0
    for filename in files_to_fix:
        filepath = tabs_dir / filename
        if filepath.exists():
            if fix_file(filepath):
                fixed += 1
        else:
            print(f"⚠️  Not found: {filename}")
    
    print(f"\n✅ Fixed {fixed} files!")
    print("\nℹ️  Note: Complex cases may still need manual review.")
    print("Run: python main.py")

if __name__ == '__main__':
    main()
