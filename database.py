import sqlite3

DB = "agent.db"

def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            role TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS seen_messages (
            message_id TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE,
            username TEXT,
            notes TEXT,
            status TEXT DEFAULT 'new',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def is_seen(message_id: str) -> bool:
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT 1 FROM seen_messages WHERE message_id = ?", (message_id,)).fetchone()
    conn.close()
    return row is not None

def mark_seen(message_id: str):
    conn = sqlite3.connect(DB)
    conn.execute("INSERT OR IGNORE INTO seen_messages (message_id) VALUES (?)", (message_id,))
    conn.commit()
    conn.close()

def save_message(user_id: str, role: str, message: str):
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO conversations (user_id, role, message) VALUES (?, ?, ?)", (user_id, role, message))
    conn.commit()
    conn.close()

def get_history(user_id: str, limit: int = 10) -> list[dict]:
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT role, message FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def add_lead(user_id: str, username: str = "", notes: str = ""):
    conn = sqlite3.connect(DB)
    conn.execute("INSERT OR IGNORE INTO leads (user_id, username, notes) VALUES (?, ?, ?)", (user_id, username, notes))
    conn.commit()
    conn.close()

def get_leads() -> list[dict]:
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT user_id, username, notes, status FROM leads ORDER BY created_at DESC").fetchall()
    conn.close()
    return [{"user_id": r[0], "username": r[1], "notes": r[2], "status": r[3]} for r in rows]
