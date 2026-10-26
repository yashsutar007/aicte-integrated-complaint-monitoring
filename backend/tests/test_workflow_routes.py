# Destination: backend/tests/test_workflow_routes.py
from flask_jwt_extended import create_access_token
from app import create_app
from routes.workflow import ALLOWED_TRANSITIONS

TEST_SECRET = "aikyatrace-workflow-test-secret-at-least-32-bytes"


def client_for(role="ADMIN", user_id="1"):
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    with app.app_context():
        token = create_access_token(
            identity=user_id,
            additional_claims={"role": role, "email": "workflow@example.test"},
        )
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_workflow_case_list_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    assert app.test_client().get("/api/workflow/cases").status_code == 401


def test_workflow_history_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    assert app.test_client().get("/api/workflow/cases/1/history").status_code == 401


def test_list_rejects_invalid_status_before_database_call():
    client, headers = client_for()
    response = client.get("/api/workflow/cases?status=WAITING", headers=headers)
    assert response.status_code == 400
    assert "status" in response.get_json()["message"].lower()


def test_list_rejects_invalid_priority_before_database_call():
    client, headers = client_for()
    response = client.get("/api/workflow/cases?priority=URGENT", headers=headers)
    assert response.status_code == 400
    assert "priority" in response.get_json()["message"].lower()


def test_viewer_cannot_add_case_remark():
    client, headers = client_for(role="VIEWER")
    response = client.post("/api/workflow/cases/1/remarks", json={"comment": "Test remark"}, headers=headers)
    assert response.status_code == 403


def test_empty_case_remark_is_rejected_before_database_call():
    client, headers = client_for(role="CASE_OFFICER")
    response = client.post("/api/workflow/cases/1/remarks", json={"comment": "   "}, headers=headers)
    assert response.status_code == 400


def test_non_text_case_remark_is_rejected_before_database_call():
    client, headers = client_for(role="CASE_OFFICER")
    response = client.post("/api/workflow/cases/1/remarks", json={"comment": 123}, headers=headers)
    assert response.status_code == 400


def test_too_long_case_remark_is_rejected_before_database_call():
    client, headers = client_for(role="CASE_OFFICER")
    response = client.post("/api/workflow/cases/1/remarks", json={"comment": "x" * 2001}, headers=headers)
    assert response.status_code == 400


def test_viewer_cannot_change_workflow_status():
    client, headers = client_for(role="VIEWER")
    response = client.patch("/api/workflow/cases/1/status", json={"status": "UNDER_REVIEW"}, headers=headers)
    assert response.status_code == 403


def test_invalid_workflow_status_is_rejected_before_database_call():
    client, headers = client_for(role="CASE_OFFICER")
    response = client.patch("/api/workflow/cases/1/status", json={"status": "WAITING"}, headers=headers)
    assert response.status_code == 400


def test_non_text_status_comment_is_rejected_before_database_call():
    client, headers = client_for(role="CASE_OFFICER")
    response = client.patch("/api/workflow/cases/1/status", json={"status": "UNDER_REVIEW", "comment": 42}, headers=headers)
    assert response.status_code == 400


def test_status_transition_map_matches_case_workflow():
    assert "UNDER_REVIEW" in ALLOWED_TRANSITIONS["SUBMITTED"]
    assert "CLOSED" not in ALLOWED_TRANSITIONS["SUBMITTED"]
    assert "REOPENED" in ALLOWED_TRANSITIONS["CLOSED"]
