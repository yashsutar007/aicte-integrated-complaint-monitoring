
from app import create_app


def test_health_endpoint():
    app = create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert response.get_json()["status"] == "healthy"


def test_root_endpoint():
    app = create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "API is running" in response.get_json()["message"]


def test_registration_rejects_missing_fields():
    app = create_app({"TESTING": True})
    client = app.test_client()

    response = client.post("/api/auth/register", json={})

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_login_rejects_missing_fields():
    app = create_app({"TESTING": True})
    client = app.test_client()

    response = client.post("/api/auth/login", json={})

    assert response.status_code == 400
    assert response.get_json()["success"] is False
