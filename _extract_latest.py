import sqlite3
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()

# Get the most recent large session about this project
target_thread = '01a07f4c-cb93-79b2-8'  # The one with 558 items

cursor.execute("""
    SELECT thread_id FROM thread_items
    WHERE thread_id LIKE ?
    LIMIT 1
""", (target_thread + '%',))
row = cursor.fetchone()
if row:
    tid = row[0]
    print(f"Full thread ID: {tid}")
    
    # Get last 20 user messages
    cursor.execute("""
        SELECT item_json, created_at_ms FROM thread_items
        WHERE thread_id = ? AND item_type = 'userMessage'
        ORDER BY created_at_ms DESC LIMIT 10
    """, (tid,))
    rows = cursor.fetchall()
    print(f"\nLast {len(rows)} user messages:")
    for i, (item_json, ts) in enumerate(rows):
        try:
            d = json.loads(item_json)
            content = d.get('content', [])
            text = ''
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text = part.get('text', '')[:300]
                        break
            print(f"\n--- Message {i+1} (ts={ts}) ---")
            print(text)
        except Exception as e:
            print(f"Error: {e}")

conn.close()
