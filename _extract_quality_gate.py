import re

with open(r'D:\小说写作\xuanqiong-wenshu\backend\app\services\pipeline_orchestrator.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find quality gate related methods and their line ranges
quality_gate_methods = []
current_method = None
current_start = None

for i, line in enumerate(lines, 1):
    # Check for method definition
    match = re.match(r'    def (_evaluate_structural_quality_gate_for_content|_build_structural_quality_gate|_attach_quality_gate_status_to_guard|_build_quality_gate_patch_repair_issues|_quality_gate_patch_suggestion|_build_quality_issue_summary|_select_quality_gate_critique_summary)', line)
    if match:
        if current_method:
            quality_gate_methods.append((current_method, current_start, i-1))
        current_method = match.group(1)
        current_start = i
    
if current_method:
    quality_gate_methods.append((current_method, current_start, len(lines)))

with open(r'D:\小说写作\xuanqiong-wenshu\_quality_gate_methods.txt', 'w', encoding='utf-8') as f:
    for name, start, end in quality_gate_methods:
        f.write(f"\n{'='*60}\n")
        f.write(f"Method: {name}\n")
        f.write(f"Lines: {start}-{end} ({end-start+1} lines)\n")
        f.write(f"{'='*60}\n")
        for i in range(start-1, min(end, len(lines))):
            f.write(f"{i+1:4d}: {lines[i]}")

print(f"Found {len(quality_gate_methods)} quality gate methods")
for name, start, end in quality_gate_methods:
    print(f"  {name}: lines {start}-{end} ({end-start+1} lines)")
