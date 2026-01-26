# testing/test_job_tag_storage.py
"""
Tests for job tag storage in database.
"""

import os
import pytest
from datetime import datetime

# Set required environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")

from src.db import init_db, clear_visits, add_visit, get_visits


@pytest.fixture
def clean_db():
    """Clear database before each test."""
    init_db()
    clear_visits()
    yield
    clear_visits()


def test_add_visit_with_job_tag(clean_db):
    """Test that add_visit stores job_tag correctly."""
    start_at = "2025-01-15T10:00:00"
    end_at = "2025-01-15T12:00:00"
    client_id = "C_TEST"
    job_tag = "commercial"
    
    add_visit(start_at, end_at, client_id, job_tag)
    
    visits = get_visits()
    assert len(visits) == 1
    assert visits[0]["job_tag"] == "commercial"
    assert visits[0]["client_id"] == client_id


def test_add_visit_default_job_tag(clean_db):
    """Test that add_visit defaults to residential if no tag provided."""
    start_at = "2025-01-15T10:00:00"
    end_at = "2025-01-15T12:00:00"
    client_id = "C_TEST"
    
    add_visit(start_at, end_at, client_id)  # No job_tag provided
    
    visits = get_visits()
    assert len(visits) == 1
    assert visits[0]["job_tag"] == "residential"


def test_add_visit_invalid_job_tag(clean_db):
    """Test that invalid job_tag defaults to residential."""
    start_at = "2025-01-15T10:00:00"
    end_at = "2025-01-15T12:00:00"
    client_id = "C_TEST"
    
    add_visit(start_at, end_at, client_id, "invalid_tag")
    
    visits = get_visits()
    assert len(visits) == 1
    assert visits[0]["job_tag"] == "residential"


def test_multiple_visits_with_different_tags(clean_db):
    """Test storing multiple visits with different job tags."""
    visits_data = [
        ("2025-01-15T10:00:00", "2025-01-15T12:00:00", "C_COMMERCIAL", "commercial"),
        ("2025-01-15T14:00:00", "2025-01-15T16:00:00", "C_RESIDENTIAL", "residential"),
        ("2025-01-16T10:00:00", "2025-01-16T12:00:00", "C_COMMERCIAL2", "commercial"),
    ]
    
    for start_at, end_at, client_id, job_tag in visits_data:
        add_visit(start_at, end_at, client_id, job_tag)
    
    visits = get_visits()
    assert len(visits) == 3
    
    # Verify tags are stored correctly
    tags = [v["job_tag"] for v in visits]
    assert "commercial" in tags
    assert "residential" in tags
    assert tags.count("commercial") == 2
    assert tags.count("residential") == 1


def test_get_visits_returns_job_tag(clean_db):
    """Test that get_visits returns job_tag in results."""
    add_visit("2025-01-15T10:00:00", "2025-01-15T12:00:00", "C_TEST", "commercial")
    
    visits = get_visits()
    assert len(visits) == 1
    visit = visits[0]
    
    # Check all expected fields are present
    assert "job_tag" in visit
    assert "date" in visit
    assert "client_id" in visit
    assert "startAt" in visit
    assert "endAt" in visit
    assert visit["job_tag"] == "commercial"


def test_backward_compatibility(clean_db):
    """Test that old visits without job_tag default to residential."""
    # Simulate old visit without job_tag by inserting directly
    import sqlite3
    from src.db import DB_PATH
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO calander (date, client_id, start_time, finish_time)
            VALUES (?, ?, ?, ?)
        """, ("2025-01-15", "C_OLD", "2025-01-15T10:00:00", "2025-01-15T12:00:00"))
        conn.commit()
    
    visits = get_visits()
    assert len(visits) == 1
    # Should default to residential for old records
    assert visits[0]["job_tag"] == "residential"

