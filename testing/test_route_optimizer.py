# testing/test_route_optimizer.py
"""
Tests for route optimization placeholder behavior.
"""

import os
from fastapi.testclient import TestClient

# Set required environment variables before importing app/settings
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")

from src.api.route_optimizer import optimize_visit_order
from src.webapp import app


def test_optimize_visit_order_disabled():
    visits = [{"startAt": "2025-01-01T08:00:00", "endAt": "2025-01-01T10:00:00"}]
    result = optimize_visit_order(visits, mode="none")
    assert result["mode"] == "none"
    assert result["optimized"] is False
    assert result["visit_count"] == 1


def test_optimize_schedule_endpoint_returns_route_metadata():
    client = TestClient(app)
    response = client.post("/optimize-schedule")
    assert response.status_code == 200
    data = response.json()
    assert "route_optimization" in data
    assert data["route_optimization"]["mode"] in {"none", "jobber", "external"}

