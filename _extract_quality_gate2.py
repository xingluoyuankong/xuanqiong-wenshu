import re

with open(r'D:\小说写作\xuanqiong-wenshu\backend\app\services\pipeline_orchestrator.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find quality gate related methods and their line ranges
target_methods = [
    '_select_quality_gate_critique_summary',
    '_evaluate_structural_quality_gate_for_content',
    '_build_quality_issue_summary',
    '_attach_quality_gate_status_to_guard',
    '_quality_gate_patch_suggestion',
    '_build_quality_gate_patch_repair_issues',
    '_build_structural_quality_gate',
]

quality_gate_methods = []

for target in target_methods:
    start_line = None
    end_line = None
    indent_level = None
    
    for i, line in enumerate(lines):
        # Find method start
        if f'def {target}(' in line and start_line is None:
            start_line = i + 1
            # Determine indent level of the method body
            indent_level = len(line) - len(line.lstrip())
            continue
        
        # Find method end (next method/class at same or lower indent, or end of file)
        if start_line is not None and end_line is None:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                current_indent = len(line) - len(line.lstrip())
                # If we hit a line at the same or lower indent level that's a def/class
                if current_indent <= indent_level and (stripped.startswith('def ') or stripped.startswith('class ') or stripped.startswith('@')):
                    end_line = i
                    break
    
    if start_line is not None:
        if end_line is None:
            end_line = len(lines)
        quality_gate_methods.append((target, start_line, end_line))

with open(r'D:\小说写作\xuanqiong-wenshu\_quality_gate_methods.txt', 'w', encoding='utf-8') as f:
    total_lines = 0
    for name, start, end in quality_gate_methods:
        method_lines = end - start + 1
        total_lines += method_lines
        f.write(f"\n{'='*60}\n")
        f.write(f"Method: {name}\n")
        f.write(f"Lines: {start}-{end} ({method_lines} lines)\n")
        f.write(f"{'='*60}\n")
        for i in range(start-1, min(end, len(lines))):
            f.write(f"{i+1:4d}: {lines[i]}")
    
    f.write(f"\n\nTotal: {total_lines} lines across {len(quality_gate_methods)} methods\n")

print(f"Found {len(quality_gate_methods)} quality gate methods")
total = 0
for name, start, end in quality_gate_methods:
    lines_count = end - start + 1
    total += lines_count
    print(f"  {name}: lines {start}-{end} ({lines_count} lines)")
print(f"Total: {total} lines")
