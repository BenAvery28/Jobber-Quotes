# testing/test_calander_functionality.py
"""
Comprehensive tests for the new calander table functionality
Tests the database operations, client ID handling, and integration with scheduling system
"""

import pytest
import sqlite3
from datetime import datetime, timedelta
from src.db import init_db, add_visit, get_visits, clear_visits, remove_visit_by_name, get_booked_days_in_current_month, \
    DB_PATH
from testing.mock_data import generate_mock_calander_data, generate_test_webhook_variations


class TestCalanderDatabase:
    """Test suite for calander database operations"""

    def setup_method(self):
        """Setup before each test"""
        init_db()
        clear_visits()

    def test_calander_table_creation(self):
        """Test that the calander table is created with correct schema"""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("PRAGMA table_info(calander)")
            columns = cursor.fetchall()

            # Expected columns: id, date, client_id, start_time, finish_time
            column_names = [col[1] for col in columns]
            assert "id" in column_names
            assert "date" in column_names
            assert "client_id" in column_names
            assert "start_time" in column_names
            assert "finish_time" in column_names
            assert len(column_names) == 5

    def test_add_single_visit(self):
        """Test adding a single visit with client_id"""
        start_time = "2025-08-29T10:00:00"
        end_time = "2025-08-29T12:00:00"
        client_id = "C123"

        add_visit(start_time, end_time, client_id)

        visits = get_visits()
        assert len(visits) == 1

        visit = visits[0]
        assert visit["startAt"] == start_time
        assert visit["endAt"] == end_time
        assert visit["client_id"] == client_id
        assert visit["date"] == "2025-08-29"

    def test_add_multiple_visits_same_client(self):
        """Test adding multiple visits for the same client"""
        client_id = "C456"
        visits_data = [
            ("2025-08-29T09:00:00", "2025-08-29T11:00:00"),
            ("2025-08-30T13:00:00", "2025-08-30T15:00:00"),
            ("2025-08-31T10:00:00", "2025-08-31T12:00:00")
        ]

        for start, end in visits_data:
            add_visit(start, end, client_id)

        visits = get_visits()
        assert len(visits) == 3

        # All visits should have the same client_id
        for visit in visits:
            assert visit["client_id"] == client_id

    def test_add_multiple_visits_different_clients(self):
        """Test adding visits for different clients"""
        visits_data = [
            ("2025-08-29T09:00:00", "2025-08-29T11:00:00", "C100"),
            ("2025-08-29T13:00:00", "2025-08-29T15:00:00", "C200"),
            ("2025-08-30T10:00:00", "2025-08-30T12:00:00", "C300")
        ]

        for start, end, client_id in visits_data:
            add_visit(start, end, client_id)

        visits = get_visits()
        assert len(visits) == 3

        client_ids = [visit["client_id"] for visit in visits]
        assert "C100" in client_ids
        assert "C200" in client_ids
        assert "C300" in client_ids

    def test_add_visits_different_dates_same_client(self):
        """Test that same client can have multiple visits on different dates"""
        client_id = "C111"
        visits_data = [
            ("2025-08-29T10:00:00", "2025-08-29T12:00:00"),
            ("2025-08-30T10:00:00", "2025-08-30T12:00:00")
        ]

        for start, end in visits_data:
            add_visit(start, end, client_id)

        visits = get_visits()
        assert len(visits) == 2  # Both visits should be added

        for visit in visits:
            assert visit["client_id"] == client_id

    def test_remove_visit_by_client_id(self):
        """Test removing visits by client ID"""
        # Add visits for multiple clients
        visits_data = [
            ("2025-08-29T09:00:00", "2025-08-29T11:00:00", "C100"),
            ("2025-08-30T09:00:00", "2025-08-30T11:00:00", "C100"),  # Same client
            ("2025-08-31T09:00:00", "2025-08-31T11:00:00", "C200"),
        ]

        for start, end, client_id in visits_data:
            add_visit(start, end, client_id)

        # Remove visits for C100
        removed_count = remove_visit_by_name("C100")
        assert removed_count == 2

        visits = get_visits()
        assert len(visits) == 1
        assert visits[0]["client_id"] == "C200"

    def test_clear_all_visits(self):
        """Test clearing all visits"""
        # Add some visits
        mock_data = generate_mock_calander_data()
        for entry in mock_data:
            add_visit(entry["start_time"], entry["finish_time"], entry["client_id"])

        assert len(get_visits()) > 0

        # Clear all
        clear_visits()
        assert len(get_visits()) == 0

    def test_get_booked_days_current_month(self):
        """Test counting booked days in current month"""
        current_date = datetime.now()

        # Add visits in current month
        visits_current_month = [
            (current_date.replace(day=5, hour=10).isoformat(),
             current_date.replace(day=5, hour=12).isoformat(), "C100"),
            (current_date.replace(day=10, hour=10).isoformat(),
             current_date.replace(day=10, hour=12).isoformat(), "C200"),
            (current_date.replace(day=5, hour=14).isoformat(),  # Same day as first
             current_date.replace(day=5, hour=16).isoformat(), "C300"),
        ]

        # Add visit in different month
        next_month = current_date + timedelta(days=32)
        visits_next_month = [
            (next_month.replace(day=1, hour=10).isoformat(),
             next_month.replace(day=1, hour=12).isoformat(), "C400")
        ]

        for start, end, client_id in visits_current_month + visits_next_month:
            add_visit(start, end, client_id)

        # Should count 2 distinct days in current month (day 5 and day 10)
        booked_days = get_booked_days_in_current_month()
        assert booked_days == 2


class TestCalanderIntegration:
    """Test integration between calander database and scheduling system"""

    def setup_method(self):
        """Setup before each test"""
        init_db()
        clear_visits()

    def test_scheduler_uses_calander_data(self):
        """Test that scheduler properly reads from calander table"""
        from src.api.scheduler import check_availability

        # Add a booking to calander
        occupied_start = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        occupied_end = occupied_start + timedelta(hours=2)

        add_visit(occupied_start.isoformat(), occupied_end.isoformat(), "C100")

        # Get visits from database
        visits = get_visits()

        # Test availability check - should return False for overlapping time
        overlap_start = occupied_start + timedelta(minutes=30)  # 30 min into existing booking
        duration = timedelta(hours=1)

        is_available = check_availability(overlap_start, duration, visits)
        assert not is_available

        # Test availability check - should return True for non-overlapping time
        free_start = occupied_end + timedelta(hours=1)  # 1 hour after existing booking
        is_available = check_availability(free_start, duration, visits)
        assert is_available

    def test_mock_data_generation(self):
        """Test that mock data generators create valid calander entries"""
        mock_entries = generate_mock_calander_data()

        assert len(mock_entries) > 0

        for entry in mock_entries:
            # Verify all required fields are present
            assert "date" in entry
            assert "client_id" in entry
            assert "start_time" in entry
            assert "finish_time" in entry

            # Verify data formats
            assert entry["client_id"].startswith("C")

            # Verify date/time formats
            start_dt = datetime.fromisoformat(entry["start_time"])
            finish_dt = datetime.fromisoformat(entry["finish_time"])
            assert finish_dt > start_dt

            # Verify date matches start_time date
            expected_date = start_dt.strftime("%Y-%m-%d")
            assert entry["date"] == expected_date

    def test_webhook_test_variations(self):
        """Test that webhook variations contain proper client IDs"""
        test_cases = generate_test_webhook_variations()

        assert len(test_cases) > 0

        for case in test_cases:
            payload = case["payload"]

            # Verify structure
            assert "client" in payload
            assert "id" in payload["client"]
            assert payload["client"]["id"].startswith("C")

            # Verify properties structure
            assert "properties" in payload["client"]
            assert len(payload["client"]["properties"]) > 0
            assert "city" in payload["client"]["properties"][0]


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        """Setup before each test"""
        init_db()
        clear_visits()

    def test_add_visit_no_client_id(self):
        """Test adding visit with None client_id (should use default)"""
        start_time = "2025-08-29T10:00:00"
        end_time = "2025-08-29T12:00:00"

        add_visit(start_time, end_time, None)

        visits = get_visits()
        assert len(visits) == 1
        assert visits[0]["client_id"] == "C123"  # Default from add_visit function

    def test_remove_nonexistent_client(self):
        """Test removing visits for client that doesn't exist"""
        # Add a visit
        add_visit("2025-08-29T10:00:00", "2025-08-29T12:00:00", "C100")

        # Try to remove different client
        removed_count = remove_visit_by_name("C999")
        assert removed_count == 0

        # Original visit should still exist
        visits = get_visits()
        assert len(visits) == 1
        assert visits[0]["client_id"] == "C100"

    def test_invalid_datetime_formats(self):
        """Test handling of various datetime formats"""
        # This tests the robustness of datetime parsing
        valid_formats = [
            "2025-08-29T10:00:00",
            "2025-08-29T10:00:00.000000",
        ]

        for i, time_format in enumerate(valid_formats):
            start_time = time_format
            end_time = time_format.replace("10:00:00", "12:00:00")
            client_id = f"C{i}"

            try:
                add_visit(start_time, end_time, client_id)
                visits = get_visits()
                # Should have successfully added the visit
                assert any(v["client_id"] == client_id for v in visits)
            except Exception as e:
                pytest.fail(f"Failed to handle datetime format {time_format}: {e}")


if __name__ == "__main__":
    # Run tests if this file is executed directly
    pytest.main([__file__, "-v"])