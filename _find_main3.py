import sqlite3
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()

# Search ALL user messages for the target keywords
cursor.execute("""
    SELECT DISTINCT thread_id FROM thread_items
    WHERE item_type = 'userMessage'
""")
all_threads = cursor.fetchall()

results = []
for (tid,) in all_threads:
    cursor.execute("""
        SELECT item_json, created_at_ms FROM thread_items
        WHERE thread_id = ? AND item_type = 'userMessage'
        ORDER BY created_at_ms ASC LIMIT 3
    """, (tid,))
    rows = cursor.fetchall()
    for item_json, ts in rows:
        try:
            d = json.loads(item_json)
            content = d.get('content', [])
            text = ''
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text = part.get('text', '')
                        break
            if '全面优化重构玄穹文枢' in text:
                cursor.execute("SELECT COUNT(*) FROM thread_items WHERE thread_id = ?", (tid,))
                cnt = cursor.fetchone()[0]
                results.append((tid, cnt, ts, text[:500]))
                break
        except:
            pass

# Sort by item count descending
results.sort(key=lambda x: -x[1])

with open(r'D:\小说写作\xuanqiong-wenshu\_session_results2.txt', 'w', encoding='utf-8') as f:
    for tid, cnt, ts, text in results:
        f.write(f"\nThread: {tid}\nItems: {cnt}\nTimestamp: {ts}\nFirst: {text}\n---\n")

print(f"Found {len(results)} threads matching '全面优化重构玄穹文枢'")
conn.close()
