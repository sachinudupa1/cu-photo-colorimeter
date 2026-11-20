from fastapi.testclient import TestClient
from backend.app.main import app


def test_health_endpoint_is_live_without_firebase_credentials():
    response = TestClient(app).get('/health')
    assert response.status_code == 200
    assert response.json()['ok'] is True
