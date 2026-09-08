import sqlite3
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()

tid = '01a06d1c-19e0-75e0-a30e-9c3d0bae9867'

# Get last 15 user messages
cursor.execute("""
    SELECT item_json, created_at_ms FROM thread_items
    WHERE thread_id = ? AND item_type = 'userMessage'
    ORDER BY created_at_ms DESC LIMIT 15
""", (tid,))
rows = cursor.fetchall()

with open(r'D:\小说写作\xuanqiong-wenshu\_main_session_last_messages.txt', 'w', encoding='utf-8') as f:
    f.write(f"Thread: {tid}\n\n")
    for i, (item_json, ts) in enumerate(rows):
        try:
            d = json.loads(item_json)
            content = d.get('content', [])
            text = ''
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text = part.get('text', '')
                        break
            f.write(f"\n=== Message {i+1} (ts={ts}) ===\n")
            f.write(text[:1000] + '\n')
        except Exception as e:
            f.write(f"Error: {e}\n")

# Also get last 5 agent messages
cursor.execute("""
    SELECT item_json, created_at_ms FROM thread_items
    WHERE thread_id = ? AND item_type = 'agentMessage'
    ORDER BY created_at_ms DESC LIMIT 5
""", (tid,))
rows = cursor.fetchall()

with open(r'D:\小说写作\xuanqiong-wenshu\_main_session_last_agent.txt', 'w', encoding='utf-8') as f:
    for i, (item_json, ts) in enumerate(rows):
        try:
            d = json.loads(item_json)
            content = d.get('content', [])
            text = ''
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text = part.get('text', '')
                        break
            f.write(f"\n=== Agent Message {i+1} (ts={ts}) ===\n")
            f.write(text[:2000] + '\n')
        except Exception as e:
            f.write(f"Error: {e}\n")

print("Done")
conn.close()
