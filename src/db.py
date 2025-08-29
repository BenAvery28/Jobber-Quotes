import sqlite3
import calendar as cal
from datetime import datetime

DB_PATH = "jobber_calendar.db"

def init_db():
    """
    Initialize the database and ensure the 'calendar' table exists.
    Columns:
      - date: unique date for the booking (YYYY-MM-DD) (primary key)
      - name: optional name of the client/job
      - start_at: ISO timestamp of job start
      - end_at: ISO timestamp of job end
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calendar (
                date TEXT PRIMARY KEY,
                name TEXT,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL
            )
        """)


def get_visits():
    """
    Fetch all bookings from the calendar.
    Returns: list of dicts {date, name, startAt, endAt}
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT date, name, start_at, end_at FROM calendar")
        return [
            {"date": date, "name": name, "startAt": start, "endAt": end}
            for date, name, start, end in cursor.fetchall()
        ]


def add_visit(start_at: str, end_at: str, name: str = None):
    """
    Add a visit (job booking) to the calendar.
    The date is extracted from start_at (YYYY-MM-DD).
    """
    job_date = datetime.fromisoformat(start_at).strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO calendar (date, name, start_at, end_at) VALUES (?, ?, ?, ?)",
            (job_date, name, start_at, end_at),
        )
        conn.commit()


def clear_visits():
    """
    Remove all bookings (testing only).
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM calendar")
        conn.commit()


def remove_visit_by_name(name: str) -> int:
    """
    Delete all bookings with the given name.
    Returns: number of rows deleted.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("DELETE FROM calendar WHERE name = ?", (name,))
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
            FROM calendar
            WHERE date BETWEEN ? AND ?
        """, (month_start, month_end))
        result = cursor.fetchone()[0]
        return result
