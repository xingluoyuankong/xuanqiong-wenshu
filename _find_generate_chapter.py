import re

with open(r'D:\小说写作\xuanqiong-wenshu\backend\app\services\pipeline_orchestrator.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find generate_chapter method
start = None
for i, line in enumerate(lines):
    if 'async def generate_chapter(' in line:
        start = i
        break

if start is not None:
    # Find the end of the method (next method at same indent level)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line.startswith('        ') and not line.startswith('    #'):
            if line.startswith('    def ') or line.startswith('    async def ') or line.startswith('    @'):
                end = i
                break
    
    # Write the method to a file
    with open(r'D:\小说写作\xuanqiong-wenshu\_generate_chapter_method.txt', 'w', encoding='utf-8') as f:
        f.write(f"Method: generate_chapter\n")
        f.write(f"Lines: {start+1}-{end} ({end-start} lines)\n")
        f.write("="*60 + "\n")
        for i in range(start, min(end, start + 500)):
            f.write(f"{i+1:4d}: {lines[i]}")
    
    print(f"Found generate_chapter: lines {start+1}-{end} ({end-start} lines)")
else:
    print("Method not found")
