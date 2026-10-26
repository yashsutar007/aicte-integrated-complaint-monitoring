# Destination: backend/tests/test_dashboard_routes.py

import mysql.connector
from flask_jwt_extended import create_access_token

from app import create_app
import routes.dashboard as dashboard_routes

TEST_SECRET = "dashboard-unit-test-secret-at-least-32-bytes"


class FakeCursor:
    def __init__(self):
        self.query = ""
        self.params = ()

    def execute(self, query, params=()):
        self.query = query
        self.params = params

    def fetchone(self):
        if "dashboard:metrics" in self.query:
            return {
                "total_institutions": 3,
                "active_institutions": 2,
                "total_cases": 4,
                "open_cases": 3,
                "resolved_cases": 1,
                "critical_open_cases": 1,
                "overdue_cases": 1,
                "due_within_24h": 2,
            }
        return None

    def fetchall(self):
        if "dashboard:status" in self.query:
            return [{"label": "SUBMITTED", "count": 2}, {"label": "ASSIGNED", "count": 2}]
        if "dashboard:priority" in self.query:
            return [{"label": "CRITICAL", "count": 1}, {"label": "HIGH", "count": 3}]
        if "dashboard:bureaus" in self.query:
            return [{"id": 1, "name": "Academic Compliance Cell", "code": "ACADEMIC-01", "active_cases": 2}]
        if "dashboard:recent_cases" in self.query:
            return [{"id": 1, "case_number": "AICTE-TEST-01", "title": "Synthetic test case", "priority": "HIGH", "status": "ASSIGNED", "sla_due_at": None, "created_at": None, "institution_name": "Demo Institute", "bureau_name": "Academic Compliance Cell"}]
        if "dashboard:recent_activity" in self.query:
            return [{"id": 1, "complaint_id": 1, "case_number": "AICTE-TEST-01", "action_type": "CASE_ASSIGNED", "from_status": "SUBMITTED", "to_status": "ASSIGNED", "comment": "Synthetic test action", "created_at": None, "actor_name": "Demo Admin"}]
        return []

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.fake_cursor = FakeCursor()

    def cursor(self, dictionary=False):
        assert dictionary is True
        return self.fake_cursor

    def is_connected(self):
        return True

    def close(self):
        pass


def client_for(role="ADMIN", user_id="1"):
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    with app.app_context():
        token = create_access_token(
            identity=user_id,
            additional_claims={"role": role, "email": "dashboard@example.test"},
        )
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_dashboard_requires_authentication():
    app = create_app({"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET})
    response = app.test_client().get("/api/dashboard/summary")
    assert response.status_code == 401


def test_dashboard_returns_database_metrics(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(dashboard_routes, "get_db_connection", lambda: connection)
    client, headers = client_for()

    response = client.get("/api/dashboard/summary", headers=headers)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["metrics"]["total_cases"] == 4
    assert payload["data"]["metrics"]["overdue_cases"] == 1
    assert payload["data"]["role_scope"] == "GLOBAL"
    assert payload["data"]["recent_cases"][0]["case_number"] == "AICTE-TEST-01"


def test_dashboard_non_admin_uses_assigned_case_scope(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(dashboard_routes, "get_db_connection", lambda: connection)
    client, headers = client_for(role="CASE_OFFICER", user_id="17")

    response = client.get("/api/dashboard/summary", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["data"]["role_scope"] == "ASSIGNED_CASES_AND_OWN_CASES"
    assert "mine.assigned_to = %s" in connection.fake_cursor.query or "membership.user_id = %s" in connection.fake_cursor.query
    assert connection.fake_cursor.params == (17, 17, 17)


def test_dashboard_returns_503_when_database_is_unavailable(monkeypatch):
    def fail_connection():
        raise mysql.connector.Error("synthetic database outage")

    monkeypatch.setattr(dashboard_routes, "get_db_connection", fail_connection)
    client, headers = client_for()

    response = client.get("/api/dashboard/summary", headers=headers)

    assert response.status_code == 503
    assert response.get_json()["success"] is False
