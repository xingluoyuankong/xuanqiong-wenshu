import sqlite3
import json

conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()

# Check what item_types exist
cursor.execute("SELECT item_type, COUNT(*) FROM thread_items GROUP BY item_type")
print("Item types:", cursor.fetchall())

# Look at a sample item
cursor.execute("SELECT item_json, item_type FROM thread_items LIMIT 3")
for row in cursor.fetchall():
    try:
        data = json.loads(row[0])
        print(f"\nType: {row[1]}")
        print(f"Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        if isinstance(data, dict):
            for k in ['type', 'role', 'content', 'text', 'message']:
                if k in data:
                    v = data[k]
                    if isinstance(v, str):
                        print(f"  {k}: {v[:200]}")
                    elif isinstance(v, list):
                        print(f"  {k}: list[{len(v)}]")
                    else:
                        print(f"  {k}: {type(v)}")
    except Exception as e:
        print(f"Parse error: {e}")

# Get distinct threads
cursor.execute("SELECT DISTINCT thread_id FROM thread_items ORDER BY thread_id DESC LIMIT 20")
threads = cursor.fetchall()
print(f"\nRecent threads: {len(threads)}")
for t in threads:
    tid = t[0]
    cursor.execute("SELECT COUNT(*) FROM thread_items WHERE thread_id = ?", (tid,))
    cnt = cursor.fetchone()[0]
    cursor.execute("SELECT item_json FROM thread_items WHERE thread_id = ? LIMIT 1", (tid,))
    row = cursor.fetchone()
    first_text = ''
    if row:
        try:
            d = json.loads(row[0])
            if isinstance(d, dict):
                c = d.get('content', d.get('text', ''))
                if isinstance(c, list):
                    for p in c:
                        if isinstance(p, dict) and p.get('type') == 'text':
                            first_text = p.get('text', '')[:150]
                            break
                elif isinstance(c, str):
                    first_text = c[:150]
        except:
            pass
    print(f"  {tid[:20]}... items={cnt} | {first_text}")

conn.close()
