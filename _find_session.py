import sqlite3
import json

conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()

# Find threads that contain the target title in their first user message
cursor.execute("""
    SELECT DISTINCT thread_id, MIN(created_at_ms) as first_msg
    FROM thread_items
    WHERE item_type = 'user'
    GROUP BY thread_id
    ORDER BY first_msg DESC
    LIMIT 50
""")
threads = cursor.fetchall()
print(f"Found {len(threads)} threads with user messages")

for thread_id, first_msg in threads[:30]:
    cursor.execute("""
        SELECT item_json, item_type FROM thread_items
        WHERE thread_id = ? AND item_type = 'user'
        ORDER BY created_at_ms ASC LIMIT 1
    """, (thread_id,))
    row = cursor.fetchone()
    if row:
        try:
            data = json.loads(row[0])
            # Try to extract text content
            text = ''
            if isinstance(data, dict):
                content = data.get('content', data.get('message', data.get('text', '')))
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get('type') == 'text':
                            text = part.get('text', '')[:200]
                            break
                elif isinstance(content, str):
                    text = content[:200]
                elif isinstance(data.get('text'), str):
                    text = data['text'][:200]
            print(f"Thread {thread_id[:16]}... | {first_msg} | {text[:150]}")
        except:
            print(f"Thread {thread_id[:16]}... | {first_msg} | (parse error)")

conn.close()
