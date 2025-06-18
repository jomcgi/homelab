"""
BDD-style integration tests for the Hike Finder API.

These tests verify the complete API behavior from HTTP request to response.
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api import app
from hike_finder import Hike, HikeFinderError
from scrape import Walk
from hourly_forecast import HourlyForecast
from weather_scoring import WeatherScore

# Test fixtures and step definitions
@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_hike_finder():
    """Mock HikeFinder for testing."""
    with patch('api.hike_finder') as mock:
        yield mock


@pytest.fixture
def sample_hikes():
    """Sample hike data for testing."""
    return [
        Hike(
            name="Ben Nevis",
            distance_km=17.0,
            duration_hours=8.0,
            url="https://example.com/ben-nevis",
            weather_score=85.0,
            weather_summary="Clear skies, light winds",
            distance_from_you_km=120.5
        ),
        Hike(
            name="Arthur's Seat",
            distance_km=3.2,
            duration_hours=1.5,
            url="https://example.com/arthurs-seat",
            weather_score=78.0,
            weather_summary="Partly cloudy, moderate winds",
            distance_from_you_km=2.1
        )
    ]


# Step definitions using pytest-bdd style
from pytest_bdd import scenarios, given, when, then, parsers

scenarios('features/api.feature')


@given('the API server is running')
def api_server_running(client):
    """API server is available for testing."""
    pass


@given('the hike finder has sample data')
def hike_finder_has_data(mock_hike_finder, sample_hikes):
    """Mock hike finder returns sample data."""
    mock_hike_finder.find_hikes.return_value = sample_hikes


@given('there is no hiking data')
def no_hiking_data(mock_hike_finder):
    """Mock hike finder has no data."""
    mock_hike_finder.find_hikes.side_effect = HikeFinderError("No hiking data found. Run update_data() first to download routes.")


@given('there are hiking routes in the database')
def hiking_routes_exist(mock_hike_finder, sample_hikes):
    """Mock hiking routes exist in database."""
    mock_hike_finder.find_hikes.return_value = sample_hikes


@given('there is weather forecast data')
def weather_data_exists(mock_hike_finder):
    """Mock weather forecast data exists."""
    # This is handled by the sample_hikes fixture
    pass


@when('I request the health check endpoint')
def request_health_check(client):
    """Make request to health check endpoint."""
    response = client.get("/health")
    # Store response in context for assertion
    request_health_check.response = response


@when('I check the data status')
def check_data_status(client):
    """Check the data status endpoint."""
    response = client.get("/data/status")
    check_data_status.response = response


@when('I search for hikes near Edinburgh with coordinates')
def search_hikes_edinburgh(client, mock_hike_finder, sample_hikes):
    """Search for hikes near Edinburgh."""
    request_data = {
        "latitude": 55.9533,
        "longitude": -3.1883,
        "radius_km": 25,
        "max_results": 5
    }
    
    mock_hike_finder.find_hikes.return_value = sample_hikes
    
    response = client.post("/hikes/search", json=request_data)
    search_hikes_edinburgh.response = response


@when('I search for hikes with invalid coordinates')
def search_invalid_coordinates(client):
    """Search with invalid coordinates."""
    request_data = {
        "latitude": 91,  # Invalid - outside valid range
        "longitude": -3.1883,
        "radius_km": 25,
        "max_results": 5
    }
    
    response = client.post("/hikes/search", json=request_data)
    search_invalid_coordinates.response = response


@when('I search for hikes with too large radius')
def search_large_radius(client):
    """Search with too large radius."""
    request_data = {
        "latitude": 55.9533,
        "longitude": -3.1883,
        "radius_km": 150,  # Too large - exceeds maximum
        "max_results": 5
    }
    
    response = client.post("/hikes/search", json=request_data)
    search_large_radius.response = response


@when('I request a data update') 
def request_data_update(client, mock_hike_finder):
    """Request data update."""
    response = client.post("/data/update")
    request_data_update.response = response


@when('I search for hikes in Antarctica')
def search_antarctica(client, mock_hike_finder):
    """Search for hikes in Antarctica (should return empty)."""
    request_data = {
        "latitude": -80,
        "longitude": 0,
        "radius_km": 25,
        "max_results": 5
    }
    
    # Mock returns empty list for Antarctica
    mock_hike_finder.find_hikes.return_value = []
    
    response = client.post("/hikes/search", json=request_data)
    search_antarctica.response = response


@then('I should get a healthy response')
def assert_healthy_response():
    """Assert health check returns healthy."""
    response = request_health_check.response
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@then('the status should be "no_data"')
def assert_no_data_status():
    """Assert status is no_data."""
    response = check_data_status.response
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_data"


@then('the message should mention missing data')
def assert_missing_data_message():
    """Assert message mentions missing data."""
    response = check_data_status.response
    data = response.json()
    assert "No hiking data found" in data["message"]


@then('I should get a list of hikes')
def assert_hikes_list():
    """Assert response contains list of hikes."""
    response = search_hikes_edinburgh.response
    assert response.status_code == 200
    data = response.json()
    assert "hikes" in data
    assert isinstance(data["hikes"], list)
    assert len(data["hikes"]) > 0


@then('each hike should have weather information')
def assert_weather_info():
    """Assert each hike has weather information."""
    response = search_hikes_edinburgh.response
    data = response.json()
    
    for hike in data["hikes"]:
        assert "weather_score" in hike
        assert "weather_summary" in hike
        assert isinstance(hike["weather_score"], (int, float))
        assert isinstance(hike["weather_summary"], str)


@then('the hikes should be sorted by weather score')
def assert_sorted_by_weather():
    """Assert hikes are sorted by weather score."""
    response = search_hikes_edinburgh.response
    data = response.json()
    
    if len(data["hikes"]) > 1:
        scores = [hike["weather_score"] for hike in data["hikes"]]
        # Should be sorted descending (best first)
        assert scores == sorted(scores, reverse=True)


@then('I should get a validation error')
def assert_validation_error():
    """Assert validation error response."""
    # Check both invalid coordinates and large radius responses
    if hasattr(search_invalid_coordinates, 'response'):
        response = search_invalid_coordinates.response
    elif hasattr(search_large_radius, 'response'):
        response = search_large_radius.response
    else:
        pytest.fail("No response found for validation error test")
    
    assert response.status_code == 422  # FastAPI validation error


@then('the update should start in the background')
def assert_background_update():
    """Assert update starts in background."""
    response = request_data_update.response
    assert response.status_code == 200


@then('I should get an accepted response')
def assert_accepted_response():
    """Assert accepted response for background task."""
    response = request_data_update.response
    data = response.json()
    assert data["status"] == "accepted"
    assert "background" in data["message"]


@then('I should get an empty list of hikes')
def assert_empty_hikes():
    """Assert empty list of hikes."""
    response = search_antarctica.response
    assert response.status_code == 200
    data = response.json()
    assert data["hikes"] == []


@then('the total found should be 0')
def assert_total_zero():
    """Assert total found is 0."""
    response = search_antarctica.response
    data = response.json()
    assert data["total_found"] == 0


# Additional integration tests without BDD for edge cases
class TestAPIEdgeCases:
    """Additional integration tests for edge cases."""
    
    def test_missing_request_fields(self, client):
        """Test API with missing required fields."""
        response = client.post("/hikes/search", json={"latitude": 55.9533})
        assert response.status_code == 422
    
    def test_hike_finder_internal_error(self, client, mock_hike_finder):
        """Test handling of internal HikeFinder errors."""
        mock_hike_finder.find_hikes.side_effect = Exception("Database connection failed")
        
        response = client.post("/hikes/search", json={
            "latitude": 55.9533,
            "longitude": -3.1883,
            "radius_km": 25,
            "max_results": 10
        })
        
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]
    
    def test_data_status_with_data(self, client, mock_hike_finder, sample_hikes):
        """Test data status when data is available."""
        mock_hike_finder.find_hikes.return_value = sample_hikes
        
        response = client.get("/data/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"