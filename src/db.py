import sqlite3
import calendar as cal
from datetime import datetime

DB_PATH = "jobber_calendar.db"


def init_db():
    """
    Initialize the database and ensure the 'calander' table exists.
    Columns:
      - id: auto-increment primary key
      - date: date of the current month (YYYY-MM-DD)
      - client_id: client ID given by Jobber
      - start_time: start time for the job (ISO timestamp)
      - finish_time: finish time of the job (ISO timestamp)
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calander (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                client_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                finish_time TEXT NOT NULL
            )
        """)


def get_visits():
    """
    Fetch all bookings from the calander.
    Returns: list of dicts {date, client_id, startAt, endAt}
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT date, client_id, start_time, finish_time FROM calander")
        return [
            {"date": date, "client_id": client_id, "startAt": start_time, "endAt": finish_time}
            for date, client_id, start_time, finish_time in cursor.fetchall()
        ]


def add_visit(start_at: str, end_at: str, client_id: str = None):
    """
    Add a visit (job booking) to the calander.
    The date is extracted from start_at (YYYY-MM-DD).
    """
    job_date = datetime.fromisoformat(start_at).strftime("%Y-%m-%d")
    if client_id is None:
        client_id = "C123"  # Default client ID for backward compatibility

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO calander (date, client_id, start_time, finish_time) VALUES (?, ?, ?, ?)",
            (job_date, client_id, start_at, end_at),
        )
        conn.commit()


def clear_visits():
    """
    Remove all bookings (testing only).
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM calander")
        conn.commit()


def remove_visit_by_name(name: str) -> int:
    """
    Delete all bookings with the given client_id.
    Returns: number of rows deleted.
    Note: Updated to use client_id instead of name for consistency
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("DELETE FROM calander WHERE client_id = ?", (name,))
        conn.commit()
        return cursor.rowcount


def get_booked_days_in_current_month() -> int:
    """
    Count how many distinct days in the current month have bookings.
    Example: If jobs exist on 2025-08-01 and 2025-08-05 → returns 2
    """
    now = datetime.now()
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    _, last_day = cal.monthrange(now.year, now.month)
    month_end = now.replace(day=last_day).strftime("%Y-%m-%d")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT date)
            FROM calander
            WHERE date BETWEEN ? AND ?
        """, (month_start, month_end))
        result = cursor.fetchone()[0]
        return result