# coding: utf-8

from fastapi.testclient import TestClient


from openapi_server.models.health_response import HealthResponse  # noqa: F401


def test_health(client: TestClient):
    """Test case for health

    Liveness check
    """

    headers = {
    }
    response = client.request(
        "GET",
        "/health",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

