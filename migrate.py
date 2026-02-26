import sqlite3
import os

db_path = "test.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE shipments ADD COLUMN status VARCHAR DEFAULT 'BOOKED'")
        conn.commit()
        print("Migrated: Added 'status' column to shipments.")
    except sqlite3.OperationalError:
        print("Column 'status' already exists or table not found. Skipping.")
    finally:
        conn.close()
else:
    print("test.db not found. No migration needed (FastAPI will create it).")
