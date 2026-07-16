from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_check():
    """Health endpoint returns 200 with correct payload."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "recruittech-api"
    assert "version" in data


def test_health_check_has_request_id():
    """Logging middleware adds X-Request-ID header."""
    response = client.get("/health")
    assert "x-request-id" in response.headers


def test_not_found():
    """Non-existent routes return structured 404.

    Uses a multi-segment path so the legacy ``/api/<x>`` -> ``/api/v1/<x>``
    redirect cannot accidentally bind to a single-param route (e.g.
    ``/api/v1/{candidate_id}``) and short-circuit into a 401.
    """
    response = client.get("/api/this-route-does-not-exist/at/all")
    assert response.status_code == 404
