# Destination: backend/tests/test_business_routes.py

from app import create_app
from flask_jwt_extended import create_access_token


def make_client():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": "aicte-test-secret-key-for-unit-tests-at-least-32-bytes"})
    with app.app_context():
        token = create_access_token(identity="1", additional_claims={"role": "ADMIN"})
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


def test_institutions_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": "aicte-test-secret-key-for-unit-tests-at-least-32-bytes"})
    response = app.test_client().get("/api/institutions")
    assert response.status_code == 401


def test_create_institution_rejects_missing_name_without_database_call():
    client, headers = make_client()
    response = client.post("/api/institutions", json={"state": "Maharashtra"}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["message"] == "Institution name is required."


def test_create_institution_rejects_invalid_status_without_database_call():
    client, headers = make_client()
    response = client.post(
        "/api/institutions",
        json={"name": "Example Institute", "status": "NOT_A_STATUS"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_complaints_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": "aicte-test-secret-key-for-unit-tests-at-least-32-bytes"})
    response = app.test_client().get("/api/complaints")
    assert response.status_code == 401


def test_create_complaint_rejects_missing_required_fields_without_database_call():
    client, headers = make_client()
    response = client.post("/api/complaints", json={}, headers=headers)
    assert response.status_code == 400
    assert "required" in response.get_json()["message"].lower()


def test_create_complaint_rejects_invalid_priority_without_database_call():
    client, headers = make_client()
    response = client.post(
        "/api/complaints",
        json={
            "institution_id": 1,
            "title": "Test complaint",
            "description": "Synthetic test description",
            "category": "Compliance",
            "priority": "URGENT_NOT_SUPPORTED",
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()["message"] == "Invalid priority."


def test_status_change_rejects_unknown_status_without_database_call():
    client, headers = make_client()
    response = client.patch(
        "/api/complaints/123/status",
        json={"status": "NOT_A_STATUS"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()["message"] == "Provide a valid complaint status."


def test_status_change_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": "aicte-test-secret-key-for-unit-tests-at-least-32-bytes"})
    response = app.test_client().patch("/api/complaints/123/status", json={"status": "UNDER_REVIEW"})
    assert response.status_code == 401
