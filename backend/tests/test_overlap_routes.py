# Destination: backend/tests/test_overlap_routes.py
from flask_jwt_extended import create_access_token

from app import create_app
from routes.overlap import _score_pair, _similarity

TEST_SECRET = "overlap-unit-test-secret-at-least-32-bytes"


def client_for(role="ADMIN", user_id="1"):
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    with app.app_context():
        token = create_access_token(
            identity=user_id,
            additional_claims={"role": role, "email": "overlap@example.test"},
        )
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_overlap_suggestions_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    assert app.test_client().get("/api/overlap/suggestions").status_code == 401


def test_exact_text_similarity_is_one():
    assert _similarity("Delayed grievance response", "delayed grievance response") == 1.0


def test_empty_text_similarity_is_zero():
    assert _similarity("", "some complaint text") == 0.0


def test_score_pair_explains_same_institution_and_category():
    left = {"id": 1, "institution_id": 7, "title": "Delayed student grievance resolution", "description": "Students report that grievance responses are delayed for weeks.", "category": "Student Grievance"}
    right = {"id": 2, "institution_id": 7, "title": "Delay in student grievance resolution", "description": "Student grievance replies are delayed for several weeks.", "category": "Student Grievance"}
    result = _score_pair(left, right)
    assert result["confidence"] >= 50
    assert result["eligible"] is True
    assert "same institution" in result["explanation"].lower()
    assert "category" in result["explanation"].lower()


def test_unrelated_complaints_do_not_qualify():
    left = {"id": 1, "institution_id": 1, "title": "Campus library air conditioning not working", "description": "The library AC is not cooling the reading room.", "category": "Infrastructure"}
    right = {"id": 2, "institution_id": 2, "title": "Faculty payroll records discrepancy", "description": "A payroll spreadsheet shows incorrect salary totals.", "category": "Finance"}
    result = _score_pair(left, right)
    assert result["confidence"] < 50
    assert result["eligible"] is False


def test_detect_rejects_invalid_threshold_before_database_call():
    client, headers = client_for()
    response = client.post("/api/overlap/detect", json={"min_confidence": 99}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_detect_rejects_invalid_complaint_id_before_database_call():
    client, headers = client_for()
    response = client.post("/api/overlap/detect", json={"complaint_id": "not-a-number"}, headers=headers)
    assert response.status_code == 400


def test_suggestions_reject_invalid_review_filter_before_database_call():
    client, headers = client_for()
    response = client.get("/api/overlap/suggestions?review_status=WAITING", headers=headers)
    assert response.status_code == 400


def test_review_rejects_invalid_decision_before_database_call():
    client, headers = client_for()
    response = client.patch("/api/overlap/suggestions/1/review", json={"review_status": "MAYBE"}, headers=headers)
    assert response.status_code == 400
