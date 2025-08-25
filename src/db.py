import sqlite3
from datetime import datetime

DB_PATH = "jobber_calendar.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL
            )
        """)

def get_visits():
    with sqlite3.connect(DB_PATH) as conn:
        return [dict(row) for row in conn.execute("SELECT start_at, end_at FROM visits")]

def add_visit(start_at, end_at):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO visits (start_at, end_at) VALUES (?, ?)", (start_at, end_at))
        conn.commit()

#Only for testing
def clear_visits():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM visits")
        conn.commit()