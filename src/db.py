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
                finish_time TEXT NOT NULL,
                job_tag TEXT DEFAULT 'residential'
            )
        """)
        # Add job_tag column if it doesn't exist (migration for existing databases)
        try:
            conn.execute("ALTER TABLE calander ADD COLUMN job_tag TEXT DEFAULT 'residential'")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass
        # Add booking_status column for tentative bookings (pseudo-reshuffler)
        try:
            conn.execute("ALTER TABLE calander ADD COLUMN booking_status TEXT DEFAULT 'confirmed'")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass
    conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_quotes (
                    quote_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    start_at TEXT NOT NULL,
                    end_at TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                )
            """)
    # Recurring jobs table - holds templates for recurring jobs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recurring_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            job_tag TEXT DEFAULT 'residential',
            day_of_week INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            duration_hours REAL NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            UNIQUE(client_id, day_of_week, start_time)
        )
    """)


def get_visits(include_tentative=True):
    """
    Fetch all bookings from the calander.
    Args:
        include_tentative: If False, only return confirmed bookings
    Returns: list of dicts {date, client_id, startAt, endAt, job_tag, booking_status}
    """
    with sqlite3.connect(DB_PATH) as conn:
        if include_tentative:
            cursor = conn.execute("""
                SELECT date, client_id, start_time, finish_time, 
                       COALESCE(job_tag, 'residential'), 
                       COALESCE(booking_status, 'confirmed')
                FROM calander
            """)
        else:
            cursor = conn.execute("""
                SELECT date, client_id, start_time, finish_time, 
                       COALESCE(job_tag, 'residential'), 
                       COALESCE(booking_status, 'confirmed')
                FROM calander
                WHERE COALESCE(booking_status, 'confirmed') = 'confirmed'
            """)
        return [
            {
                "date": date, 
                "client_id": client_id, 
                "startAt": start_time, 
                "endAt": finish_time, 
                "job_tag": job_tag or "residential",
                "booking_status": booking_status or "confirmed"
            }
            for date, client_id, start_time, finish_time, job_tag, booking_status in cursor.fetchall()
        ]


def add_visit(start_at: str, end_at: str, client_id: str = None, job_tag: str = "residential", 
              booking_status: str = "confirmed"):
    """
    Add a visit (job booking) to the calander.
    The date is extracted from start_at (YYYY-MM-DD).
    
    Args:
        start_at: Start time (ISO format)
        end_at: End time (ISO format)
        client_id: Client ID from Jobber
        job_tag: Job classification ('commercial' or 'residential', default 'residential')
        booking_status: 'confirmed' or 'tentative' (default 'confirmed')
    """
    job_date = datetime.fromisoformat(start_at).strftime("%Y-%m-%d")
    if client_id is None:
        client_id = "C123"  # Default client ID for backward compatibility
    
    # Ensure job_tag is valid
    if job_tag not in ["commercial", "residential"]:
        job_tag = "residential"
    
    # Ensure booking_status is valid
    if booking_status not in ["confirmed", "tentative"]:
        booking_status = "confirmed"

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO calander (date, client_id, start_time, finish_time, job_tag, booking_status) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job_date, client_id, start_at, end_at, job_tag, booking_status),
        )
        conn.commit()


def update_booking_status(client_id: str, start_at: str, new_status: str):
    """
    Update the booking status for a specific booking.
    Used by pseudo-reshuffler to confirm tentative bookings or make them tentative.
    
    Args:
        client_id: Client ID
        start_at: Start time (ISO format) to identify the booking
        new_status: 'confirmed' or 'tentative'
    Returns:
        int: Number of rows updated
    """
    if new_status not in ["confirmed", "tentative"]:
        raise ValueError("booking_status must be 'confirmed' or 'tentative'")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            UPDATE calander 
            SET booking_status = ?
            WHERE client_id = ? AND start_time = ?
        """, (new_status, client_id, start_at))
        conn.commit()
        return cursor.rowcount


def get_tentative_bookings():
    """
    Get all tentative bookings that can be reshuffled.
    Returns: list of dicts with booking details
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            SELECT date, client_id, start_time, finish_time, 
                   COALESCE(job_tag, 'residential')
            FROM calander
            WHERE COALESCE(booking_status, 'confirmed') = 'tentative'
        """)
        return [
            {
                "date": date,
                "client_id": client_id,
                "startAt": start_time,
                "endAt": finish_time,
                "job_tag": job_tag or "residential"
            }
            for date, client_id, start_time, finish_time, job_tag in cursor.fetchall()
        ]


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


def clear_processed_quotes():
    """
    Remove all processed quote records (testing only).
    Used to reset idempotency tracking between tests.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM processed_quotes")
        conn.commit()


def get_processed_quote(quote_id: str):
    """
    Returns processed quote row if it exists, else None.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("""
            SELECT quote_id, client_id, job_id, start_at, end_at, processed_at
            FROM processed_quotes
            WHERE quote_id = ?
        """, (quote_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "quote_id": row[0],
            "client_id": row[1],
            "job_id": row[2],
            "start_at": row[3],
            "end_at": row[4],
            "processed_at": row[5],
        }

def mark_quote_processed(quote_id: str, client_id: str, job_id: str, start_at: str, end_at: str):
    """
    Mark a quote as processed. Safe if called once; will raise if duplicate quote_id.
    """
    processed_at = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO processed_quotes (quote_id, client_id, job_id, start_at, end_at, processed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (quote_id, client_id, job_id, start_at, end_at, processed_at))
        conn.commit()


# -------------------
# RECURRING JOBS FUNCTIONS
# -------------------

def create_recurring_job(client_id: str, day_of_week: int, start_time: str, duration_hours: float,
                        start_date: str, end_date: str, job_tag: str = "residential"):
    """
    Create a recurring job template.
    
    Args:
        client_id: Client ID from Jobber
        day_of_week: Day of week (0=Monday, 1=Tuesday, ..., 3=Thursday)
        start_time: Start time in HH:MM format (e.g., "10:00")
        duration_hours: Duration in hours (e.g., 2.0)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        job_tag: Job classification ('commercial' or 'residential')
    
    Returns:
        int: ID of the created recurring job
    """
    if job_tag not in ["commercial", "residential"]:
        job_tag = "residential"
    
    created_at = datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            INSERT INTO recurring_jobs 
            (client_id, job_tag, day_of_week, start_time, duration_hours, start_date, end_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (client_id, job_tag, day_of_week, start_time, duration_hours, start_date, end_date, created_at))
        conn.commit()
        return cursor.lastrowid


def get_recurring_jobs(client_id: str = None, active_only: bool = True):
    """
    Get recurring job templates.
    
    Args:
        client_id: If provided, filter by client_id
        active_only: If True, only return active recurring jobs
    
    Returns:
        list: List of recurring job dicts
    """
    with sqlite3.connect(DB_PATH) as conn:
        if client_id:
            if active_only:
                cursor = conn.execute("""
                    SELECT id, client_id, job_tag, day_of_week, start_time, duration_hours,
                           start_date, end_date, created_at, is_active
                    FROM recurring_jobs
                    WHERE client_id = ? AND is_active = 1
                """, (client_id,))
            else:
                cursor = conn.execute("""
                    SELECT id, client_id, job_tag, day_of_week, start_time, duration_hours,
                           start_date, end_date, created_at, is_active
                    FROM recurring_jobs
                    WHERE client_id = ?
                """, (client_id,))
        else:
            if active_only:
                cursor = conn.execute("""
                    SELECT id, client_id, job_tag, day_of_week, start_time, duration_hours,
                           start_date, end_date, created_at, is_active
                    FROM recurring_jobs
                    WHERE is_active = 1
                """)
            else:
                cursor = conn.execute("""
                    SELECT id, client_id, job_tag, day_of_week, start_time, duration_hours,
                           start_date, end_date, created_at, is_active
                    FROM recurring_jobs
                """)
        
        return [
            {
                "id": row[0],
                "client_id": row[1],
                "job_tag": row[2],
                "day_of_week": row[3],
                "start_time": row[4],
                "duration_hours": row[5],
                "start_date": row[6],
                "end_date": row[7],
                "created_at": row[8],
                "is_active": bool(row[9])
            }
            for row in cursor.fetchall()
        ]


def deactivate_recurring_job(recurring_job_id: int):
    """
    Deactivate a recurring job (soft delete).
    
    Args:
        recurring_job_id: ID of recurring job to deactivate
    
    Returns:
        int: Number of rows updated
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            UPDATE recurring_jobs
            SET is_active = 0
            WHERE id = ?
        """, (recurring_job_id,))
        conn.commit()
        return cursor.rowcount

