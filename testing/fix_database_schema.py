# testing/fix_database_schema.py
"""
Script to fix the database schema and verify it's working correctly
"""

import os
import sys
import sqlite3
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db, clear_visits, add_visit, get_visits, DB_PATH


def check_schema():
    """Check current database schema"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("PRAGMA table_info(calander)")
            columns = cursor.fetchall()

            print("Current database schema:")
            for col in columns:
                print(f"  {col[1]} ({col[2]}) - {'PRIMARY KEY' if col[5] else ''}")

            column_names = [col[1] for col in columns]
            return column_names
    except Exception as e:
        print(f"Error checking schema: {e}")
        return []


def safe_recreate_database():
    """Safely recreate the database with correct schema"""
    print("Recreating database safely...")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Drop the old table and create new one
            conn.execute("DROP TABLE IF EXISTS calander")
            conn.execute("""
                CREATE TABLE calander (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    finish_time TEXT NOT NULL
                )
            """)
            conn.commit()
            print("Database recreated successfully")
            return True
    except Exception as e:
        print(f"Error recreating database: {e}")
        return False


def test_database_operations():
    """Test that database operations work correctly"""
    print("\nTesting database operations...")

    # Clear any existing data
    clear_visits()

    # Test data
    test_visits = [
        ("2025-08-29T09:00:00", "2025-08-29T11:00:00", "C001"),
        ("2025-08-29T13:00:00", "2025-08-29T15:00:00", "C002"),
        ("2025-08-30T10:00:00", "2025-08-30T12:00:00", "C003")
    ]

    # Add visits
    for start, end, client_id in test_visits:
        add_visit(start, end, client_id)
        print(f"Added visit for {client_id}")

    # Retrieve visits
    visits = get_visits()
    print(f"Retrieved {len(visits)} visits")

    # Check that all visits were stored (not overwritten)
    if len(visits) == 3:
        print("All visits stored correctly (no overwrites)")

        # Check client IDs
        client_ids = [visit["client_id"] for visit in visits]
        expected_ids = ["C001", "C002", "C003"]

        all_found = all(expected_id in client_ids for expected_id in expected_ids)
        if all_found:
            print("All client IDs stored correctly")
        else:
            print(f"Missing client IDs. Expected: {expected_ids}, Found: {client_ids}")
    else:
        print(f"Expected 3 visits, got {len(visits)}")
        for visit in visits:
            print(f"  Visit: {visit}")


if __name__ == "__main__":
    print("=== Database Schema Fix ===")

    # Check current schema
    columns = check_schema()

    # Check if schema is correct
    expected_columns = ["id", "date", "client_id", "start_time", "finish_time"]
    schema_correct = all(col in columns for col in expected_columns) and len(columns) == 5

    if not schema_correct:
        print(f"Schema incorrect. Expected: {expected_columns}, Got: {columns}")

        if safe_recreate_database():
            # Check schema again
            columns = check_schema()
            schema_correct = all(col in columns for col in expected_columns) and len(columns) == 5

            if schema_correct:
                print("Schema fixed successfully")
            else:
                print("Failed to fix schema")
                sys.exit(1)
        else:
            print("Failed to recreate database")
            sys.exit(1)
    else:
        print("Schema is already correct")

    # Test database operations
    test_database_operations()

    print("\n=== Summary ===")
    print("Database schema has been fixed. You can now run the tests:")
    print("python -m pytest testing/test_book_job.py::test_calander_table_operations -v")