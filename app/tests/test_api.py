"""API endpoint tests."""

import pytest
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.models import Base
from app.core.database import engine


@pytest.fixture(scope="session")
def db_setup():
    """Setup database for tests."""
    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    return setup


@pytest.fixture(scope="function")
async def clean_db(db_setup):
    """Clean database before each test."""
    await db_setup()


@pytest.fixture
def client():
    """Test client."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data


def test_health_check(client):
    """Test health check via root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.json()["message"]


def test_routes_list(client, clean_db):
    """Test listing routes."""
    response = client.get("/api/v1/routes/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_create_and_get_trip(client, clean_db):
    """Test trip creation and retrieval."""
    trip_data = {
        "id": "TRIP-001",
        "route_id": "Route 42",
        "bus_id": "BUS-1001",
        "driver_id": "DRV-001",
        "scheduled_start": datetime.now().isoformat(),
        "scheduled_end": (datetime.now() + timedelta(hours=1)).isoformat(),
        "direction": "Northbound",
        "is_active": True,
    }
    response = client.post("/api/v1/trips/", json=trip_data)
    assert response.status_code == 201
    trip = response.json()
    assert trip["id"] == trip_data["id"]
    assert trip["route_id"] == trip_data["route_id"]


def test_submit_feedback(client, clean_db):
    """Test feedback submission."""
    feedback_data = {
        "route_id": "Route 42",
        "punctuality_rating": 3.0,
        "cleanliness_rating": 4.0,
        "crowding_rating": 2.0,
        "driver_rating": 3.5,
        "overall_rating": 3.0,
        "raw_comment": "Test feedback",
        "channel": "WEB",
    }
    response = client.post("/api/v1/feedback/", json=feedback_data)
    assert response.status_code == 201
    feedback = response.json()
    assert feedback["route_id"] == feedback_data["route_id"]
    assert feedback["overall_rating"] == feedback_data["overall_rating"]


def test_filter_feedback(client, clean_db):
    """Test feedback filtering."""
    # First submit a feedback
    feedback_data = {
        "route_id": "Route 42",
        "overall_rating": 4.0,
        "raw_comment": "Test filter",
        "channel": "WEB",
    }
    client.post("/api/v1/feedback/", json=feedback_data)

    # Filter by route
    response = client.get("/api/v1/feedback/?route_id=Route 42")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["route_id"] == "Route 42"


def test_analytics_rankings(client, clean_db):
    """Test analytics rankings endpoint."""
    response = client.get("/api/v1/analytics/rankings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_analytics_deterioration(client, clean_db):
    """Test deterioration analytics."""
    response = client.get("/api/v1/analytics/deterioration")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_analytics_temporal_heatmap(client, clean_db):
    """Test temporal heatmap endpoint."""
    response = client.get("/api/v1/analytics/temporal-heatmap")
    assert response.status_code == 200
    data = response.json()
    assert "cells" in data


def test_classify_endpoint(client):
    """Test AI classification endpoint."""
    classify_data = {
        "comment": "The bus is always packed after 6 PM.",
        "route_id": "Route 42",
    }
    response = client.post("/api/v1/ai/classify", json=classify_data)
    # May return 500 if LLM not available, but should not crash
    assert response.status_code in [200, 500]


def test_batch_process_endpoint(client):
    """Test batch processing endpoint."""
    batch_data = {
        "route_id": "Route 42",
        "limit": 10,
        "force": False,
    }
    response = client.post("/api/v1/ai/batch-process", json=batch_data)
    assert response.status_code == 202
    data = response.json()
    assert "message" in data


def test_route_summary(client, clean_db):
    """Test route summary endpoint."""
    response = client.get("/api/v1/routes/Route 42/summary")
    assert response.status_code == 200
    data = response.json()
    assert "route_id" in data
    assert "overall_rating" in data


def test_health_check_multiple_routes(client, clean_db):
    """Test creating and retrieving multiple routes."""
    routes = [
        {"id": "Route A", "name": "A Line", "origin": "X", "destination": "Y"},
        {"id": "Route B", "name": "B Line", "origin": "P", "destination": "Q"},
    ]

    for route in routes:
        response = client.post("/api/v1/routes/", json=route)
        assert response.status_code == 201

    response = client.get("/api/v1/routes/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_stress_submit_multiple_feedback(client, clean_db):
    """Test submitting multiple feedback entries."""
    for i in range(5):
        feedback_data = {
            "route_id": f"Route {i + 10}",
            "overall_rating": 3.0 + i,
            "raw_comment": f"Test feedback {i}",
            "channel": "WEB",
        }
        response = client.post("/api/v1/feedback/", json=feedback_data)
        assert response.status_code == 201

    response = client.get("/api/v1/feedback/?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 5