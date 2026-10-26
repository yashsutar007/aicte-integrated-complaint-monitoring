# Destination: backend/tests/test_coordination_routes.py
from flask_jwt_extended import create_access_token
from app import create_app

TEST_SECRET = "coordination-unit-test-secret-at-least-32-bytes"


def client_for(role="ADMIN", user_id="1"):
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    with app.app_context():
        token = create_access_token(
            identity=user_id,
            additional_claims={"role": role, "email": "coordination@example.test"},
        )
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_related_links_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    assert app.test_client().get("/api/coordination/links").status_code == 401


def test_links_reject_invalid_review_filter_before_database_call():
    client, headers = client_for()
    response = client.get("/api/coordination/links?review_status=WAITING", headers=headers)
    assert response.status_code == 400


def test_links_reject_invalid_relationship_filter_before_database_call():
    client, headers = client_for()
    response = client.get("/api/coordination/links?relationship=UNRELATED", headers=headers)
    assert response.status_code == 400


def test_create_link_requires_two_positive_ids():
    client, headers = client_for()
    response = client.post("/api/coordination/links", json={"complaint_id": 1}, headers=headers)
    assert response.status_code == 400
    assert "positive integers" in response.get_json()["message"]


def test_create_link_rejects_linking_a_case_to_itself():
    client, headers = client_for()
    response = client.post("/api/coordination/links", json={"complaint_id": 1, "related_complaint_id": 1}, headers=headers)
    assert response.status_code == 400


def test_create_link_rejects_duplicate_relationship_type():
    client, headers = client_for()
    response = client.post("/api/coordination/links", json={"complaint_id": 1, "related_complaint_id": 2, "relationship": "POTENTIAL_DUPLICATE"}, headers=headers)
    assert response.status_code == 400
    assert "Overlap Detection" in response.get_json()["message"]


def test_viewer_cannot_create_link():
    client, headers = client_for(role="VIEWER")
    response = client.post("/api/coordination/links", json={"complaint_id": 1, "related_complaint_id": 2, "relationship": "RELATED"}, headers=headers)
    assert response.status_code == 403


def test_review_rejects_invalid_decision_before_database_call():
    client, headers = client_for()
    response = client.patch("/api/coordination/links/1/review", json={"review_status": "MAYBE"}, headers=headers)
    assert response.status_code == 400


def test_empty_coordination_note_rejected_before_database_call():
    client, headers = client_for()
    response = client.post("/api/coordination/links/1/notes", json={"note": "   "}, headers=headers)
    assert response.status_code == 400


def test_viewer_cannot_add_coordination_note():
    client, headers = client_for(role="VIEWER")
    response = client.post("/api/coordination/links/1/notes", json={"note": "Please coordinate the review."}, headers=headers)
    assert response.status_code == 403
