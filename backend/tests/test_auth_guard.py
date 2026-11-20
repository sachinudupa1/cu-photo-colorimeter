from fastapi.testclient import TestClient
from backend.app.main import app


def test_private_endpoint_rejects_missing_authentication():
    response = TestClient(app).get('/api/team/dashboard')
    assert response.status_code == 401


def test_private_endpoint_does_not_accept_a_fake_bearer_token(monkeypatch):
    from backend.app import security
    monkeypatch.setattr(security, 'auth_verify_id_token', lambda token: (_ for _ in ()).throw(ValueError('bad token')))
    response = TestClient(app).get('/api/team/dashboard', headers={'Authorization': 'Bearer not-a-real-token'})
    assert response.status_code == 401
