import sqlite3
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()

# Get all threads with >50 user messages, check if they mention xuanqiong
cursor.execute("""
    SELECT ti.thread_id, COUNT(*) as cnt
    FROM thread_items ti
    WHERE ti.item_type = 'userMessage'
    GROUP BY ti.thread_id
    HAVING cnt > 50
    ORDER BY cnt DESC
    LIMIT 30
""")
threads = cursor.fetchall()

results = []
for tid, cnt in threads:
    cursor.execute("""
        SELECT item_json FROM thread_items
        WHERE thread_id = ? AND item_type = 'userMessage'
        ORDER BY created_at_ms ASC LIMIT 1
    """, (tid,))
    row = cursor.fetchone()
    if row:
        try:
            d = json.loads(row[0])
            content = d.get('content', [])
            text = ''
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text = part.get('text', '')
                        break
            if 'xuanqiong' in text or '玄穹' in text:
                results.append((tid, cnt, text[:300]))
        except:
            pass

with open(r'D:\小说写作\xuanqiong-wenshu\_session_results.txt', 'w', encoding='utf-8') as f:
    for tid, cnt, text in results:
        f.write(f"\nThread: {tid}\nItems: {cnt}\nFirst: {text}\n---\n")

print(f"Found {len(results)} matching threads, written to _session_results.txt")
conn.close()
