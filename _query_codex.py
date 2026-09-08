import sqlite3
import json

# Query thread history
conn = sqlite3.connect(r'C:\Users\XZXyuan\.codex\thread_history_1.sqlite')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('Tables:', tables)
for t in tables:
    tname = t[0]
    cursor.execute(f'PRAGMA table_info({tname})')
    cols = cursor.fetchall()
    print(f'\nTable {tname} columns:')
    for c in cols:
        print(f'  {c}')
    cursor.execute(f'SELECT COUNT(*) FROM {tname}')
    count = cursor.fetchone()[0]
    print(f'  Row count: {count}')
conn.close()
