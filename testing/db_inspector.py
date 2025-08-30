# testing/db_inspector.py
"""
Script to inspect database contents during testing
"""

import sqlite3
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import DB_PATH, get_visits
from datetime import datetime


def inspect_database():
    """Show current database contents"""
    print("=== Database Inspection ===")

    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"Database file not found: {DB_PATH}")
        return

    print(f"Database file: {DB_PATH}")
    print(f"File size: {os.path.getsize(DB_PATH)} bytes")

    # Connect and check schema
    with sqlite3.connect(DB_PATH) as conn:
        # Get table info
        cursor = conn.execute("PRAGMA table_info(calander)")
        columns = cursor.fetchall()

        print(f"\nTable Schema:")
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            is_pk = "PRIMARY KEY" if col[5] else ""
            print(f"  {col_name} ({col_type}) {is_pk}")

        # Get row count
        cursor = conn.execute("SELECT COUNT(*) FROM calander")
        row_count = cursor.fetchone()[0]
        print(f"\nTotal rows: {row_count}")

        if row_count > 0:
            # Show all data
            cursor = conn.execute("""
                SELECT id, date, client_id, start_time, finish_time 
                FROM calander 
                ORDER BY start_time
            """)
            rows = cursor.fetchall()

            print(f"\nAll Records:")
            print(f"{'ID':<4} {'Date':<12} {'Client ID':<12} {'Start Time':<20} {'Finish Time':<20}")
            print("-" * 70)

            for row in rows:
                row_id, date, client_id, start_time, finish_time = row
                # Format timestamps
                try:
                    start_dt = datetime.fromisoformat(start_time)
                    finish_dt = datetime.fromisoformat(finish_time)
                    start_str = start_dt.strftime("%m-%d %H:%M")
                    finish_str = finish_dt.strftime("%m-%d %H:%M")
                except:
                    start_str = start_time[:16] if start_time else "N/A"
                    finish_str = finish_time[:16] if finish_time else "N/A"

                print(f"{row_id:<4} {date:<12} {client_id:<12} {start_str:<20} {finish_str:<20}")


def test_database_operations():
    """Test database operations and show results"""
    from src.db import init_db, clear_visits, add_visit, get_visits

    print("\n=== Testing Database Operations ===")

    # Initialize
    init_db()
    print("Database initialized")

    # Show before clearing
    print(f"Records before clear: {len(get_visits())}")

    # Clear
    clear_visits()
    print("Database cleared")
    inspect_database()

    # Add test data
    test_data = [
        ("2025-08-29T09:00:00", "2025-08-29T11:00:00", "C001"),
        ("2025-08-29T13:00:00", "2025-08-29T15:00:00", "C002"),
        ("2025-08-30T10:00:00", "2025-08-30T12:00:00", "C003")
    ]

    print(f"\nAdding {len(test_data)} test records...")
    for start, end, client_id in test_data:
        add_visit(start, end, client_id)

    inspect_database()

    # Test removal
    print(f"\nRemoving client C002...")
    from src.db import remove_visit_by_name
    removed = remove_visit_by_name("C002")
    print(f"Removed {removed} records")

    inspect_database()


def monitor_during_tests():
    """Show database state during test execution"""
    print("\n=== Live Database Monitoring ===")
    print("Run this script while your tests are running to see changes")
    print("Press Ctrl+C to stop monitoring")

    import time

    try:
        last_count = 0
        while True:
            visits = get_visits()
            current_count = len(visits)

            if current_count != last_count:
                print(f"\nChange detected! Records: {current_count}")
                if visits:
                    print("Current bookings:")
                    for visit in visits[-3:]:  # Show last 3
                        start_dt = datetime.fromisoformat(visit['startAt'])
                        print(f"  {visit['client_id']}: {start_dt.strftime('%m-%d %H:%M')}")
                last_count = current_count

            time.sleep(2)  # Check every 2 seconds

    except KeyboardInterrupt:
        print("\nMonitoring stopped")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_database_operations()
        elif sys.argv[1] == "monitor":
            monitor_during_tests()
        else:
            print("Usage: python db_inspector.py [test|monitor]")
    else:
        inspect_database()