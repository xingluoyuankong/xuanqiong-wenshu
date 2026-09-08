import sqlite3
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()

# Search for threads containing the target title
target = '全面优化重构玄穹文枢'

# Get all threads with userMessage items
cursor.execute("""
    SELECT DISTINCT ti.thread_id
    FROM thread_items ti
    WHERE ti.item_type = 'userMessage'
    ORDER BY ti.thread_id DESC
""")
threads = cursor.fetchall()
print(f"Total threads with user messages: {len(threads)}")

for t in threads:
    tid = t[0]
    cursor.execute("""
        SELECT item_json FROM thread_items
        WHERE thread_id = ? AND item_type = 'userMessage'
        ORDER BY created_at_ms ASC LIMIT 5
    """, (tid,))
    rows = cursor.fetchall()
    for row in rows:
        try:
            d = json.loads(row[0])
            content = d.get('content', [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text = part.get('text', '')
                        if target in text or '玄穹文枢' in text or '全面优化' in text:
                            cursor.execute("SELECT COUNT(*) FROM thread_items WHERE thread_id = ?", (tid,))
                            cnt = cursor.fetchone()[0]
                            print(f"\n=== MATCH FOUND ===")
                            print(f"Thread ID: {tid}")
                            print(f"Total items: {cnt}")
                            print(f"First text: {text[:500]}")
                            print(f"=== END MATCH ===")
        except Exception as e:
            pass

conn.close()
