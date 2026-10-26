from app import create_app
from flask_jwt_extended import create_access_token

TEST_SECRET = "unit-test-secret-that-is-at-least-32-bytes-long"


def make_client(role="ADMIN"):
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    with app.app_context():
        token = create_access_token(
            identity="1", additional_claims={"role": role, "email": "unit@example.test"}
        )
    client = app.test_client()
    return client, {"Authorization": f"Bearer {token}"}


def test_bureaus_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    assert app.test_client().get("/api/bureaus").status_code == 401


def test_create_bureau_rejects_missing_name_without_database_call():
    client, headers = make_client()
    response = client.post("/api/bureaus", json={"code": "BUREAU-01"}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["message"] == "Bureau name is required."


def test_create_bureau_rejects_invalid_code_without_database_call():
    client, headers = make_client()
    response = client.post("/api/bureaus", json={"name": "Academic Bureau", "code": "?"}, headers=headers)
    assert response.status_code == 400
    assert "bureau code" in response.get_json()["message"].lower()


def test_case_officer_cannot_create_bureau():
    client, headers = make_client("CASE_OFFICER")
    response = client.post("/api/bureaus", json={"name": "Academic Bureau", "code": "ACADEMIC-01"}, headers=headers)
    assert response.status_code == 403


def test_bureau_status_requires_boolean():
    client, headers = make_client()
    response = client.patch("/api/bureaus/1/status", json={"is_active": "false"}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["message"] == "is_active must be true or false."


def test_eligible_officers_requires_admin():
    client, headers = make_client("CASE_OFFICER")
    response = client.get("/api/bureaus/eligible-officers", headers=headers)
    assert response.status_code == 403


def test_members_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    assert app.test_client().get("/api/bureaus/1/members").status_code == 401


def test_add_bureau_member_rejects_missing_user_id_without_database_call():
    client, headers = make_client()
    response = client.post("/api/bureaus/1/members", json={}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["message"] == "Select a valid officer."


def test_assignments_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    assert app.test_client().get("/api/assignments").status_code == 401


def test_assignment_rejects_missing_case_and_bureau_without_database_call():
    client, headers = make_client()
    response = client.post("/api/assignments", json={}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["message"] == "Select a case and a Bureau or Cell."


def test_case_officer_cannot_assign_case():
    client, headers = make_client("CASE_OFFICER")
    response = client.post("/api/assignments", json={"complaint_id": 1, "bureau_id": 1}, headers=headers)
    assert response.status_code == 403


def test_assignment_rejects_non_numeric_officer_without_database_call():
    client, headers = make_client()
    response = client.post(
        "/api/assignments",
        json={"complaint_id": 1, "bureau_id": 1, "assigned_to": "not-an-id"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "valid officer" in response.get_json()["message"].lower()


def test_assignment_rejects_overlong_note_without_database_call():
    client, headers = make_client()
    response = client.post(
        "/api/assignments",
        json={"complaint_id": 1, "bureau_id": 1, "note": "x" * 1001},
        headers=headers,
    )
    assert response.status_code == 400
    assert "1000 characters" in response.get_json()["message"]


def test_assignment_status_filter_rejects_unknown_status_without_database_call():
    client, headers = make_client()
    response = client.get("/api/assignments?status=BAD_STATUS", headers=headers)
    assert response.status_code == 400
    assert response.get_json()["message"] == "Invalid complaint status."
