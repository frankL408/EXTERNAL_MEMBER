import sqlite3

# Connect to your database
conn = sqlite3.connect('library.db')
cursor = conn.cursor()

try:
    # Add the rfid_uid column
    cursor.execute('ALTER TABLE member ADD COLUMN rfid_uid VARCHAR(50) UNIQUE')
    conn.commit()
    print("✅ Successfully added rfid_uid column to member table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("✅ rfid_uid column already exists")
    else:
        print(f"Error: {e}")

# Verify the column was added
cursor.execute("PRAGMA table_info(member)")
columns = cursor.fetchall()
print("\nMember table columns:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

conn.close()
