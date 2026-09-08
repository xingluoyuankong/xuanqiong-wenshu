import sqlite3
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()

# Search for threads that mention xuanqiong-wenshu in context and are about optimization
# Look at the largest threads first (most work done)
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
print(f"Large threads: {len(threads)}")

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
            if 'xuanqiong' in text or '玄穹' in text or '小说写作' in text:
                # Get last user message too
                cursor.execute("""
                    SELECT item_json FROM thread_items
                    WHERE thread_id = ? AND item_type = 'userMessage'
                    ORDER BY created_at_ms DESC LIMIT 1
                """, (tid,))
                last_row = cursor.fetchone()
                last_text = ''
                if last_row:
                    try:
                        ld = json.loads(last_row[0])
                        lc = ld.get('content', [])
                        if isinstance(lc, list):
                            for part in lc:
                                if isinstance(part, dict) and part.get('type') == 'text':
                                    last_text = part.get('text', '')[:200]
                                    break
                    except:
                        pass
                print(f"\nThread: {tid}")
                print(f"Items: {cnt}")
                print(f"First: {text[:200]}")
                print(f"Last: {last_text}")
        except Exception as e:
            pass

conn.close()
