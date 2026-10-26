# Destination: backend/routes/workflow.py
"""Case workflow and action-history APIs for AikyaTrace.

Uses existing complaints, case_actions, notifications and audit_logs tables.
No database migration is required.
"""

import json
from datetime import date, datetime
from decimal import Decimal

import mysql.connector
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from db import get_db_connection

workflow_bp = Blueprint("workflow", __name__, url_prefix="/api/workflow")

ADMIN_ROLES = {"ADMIN", "SUPER_ADMIN"}
WRITE_ROLES = {"ADMIN", "SUPER_ADMIN", "BUREAU_OFFICER", "CASE_OFFICER"}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_STATUSES = {
    "SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "AWAITING_INFORMATION",
    "RESOLVED", "CLOSED", "REOPENED",
}
ALLOWED_TRANSITIONS = {
    "SUBMITTED": {"UNDER_REVIEW", "ASSIGNED"},
    "UNDER_REVIEW": {"ASSIGNED", "AWAITING_INFORMATION", "RESOLVED"},
    "ASSIGNED": {"UNDER_REVIEW", "AWAITING_INFORMATION", "RESOLVED"},
    "AWAITING_INFORMATION": {"UNDER_REVIEW", "ASSIGNED"},
    "RESOLVED": {"CLOSED", "REOPENED"},
    "CLOSED": {"REOPENED"},
    "REOPENED": {"UNDER_REVIEW", "ASSIGNED"},
}
MAX_PAGE_SIZE = 100


def _role_user():
    role = str(get_jwt().get("role", "CASE_OFFICER")).upper()
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        user_id = 0
    return role, user_id


def _case_access_sql(alias="c"):
    return f"""(
        {alias}.created_by = %s
        OR EXISTS (
            SELECT 1 FROM complaint_assignments own_assignment
            WHERE own_assignment.complaint_id = {alias}.id
              AND own_assignment.released_at IS NULL
              AND own_assignment.assigned_to = %s
        )
        OR EXISTS (
            SELECT 1 FROM complaint_assignments team_assignment
            JOIN user_bureaus membership ON membership.bureau_id = team_assignment.bureau_id
            WHERE team_assignment.complaint_id = {alias}.id
              AND team_assignment.released_at IS NULL
              AND membership.user_id = %s
        )
    )"""


def _has_case_access(cursor, case_id, role, user_id):
    cursor.execute("SELECT c.id FROM complaints c WHERE c.id = %s", (case_id,))
    if not cursor.fetchone():
        return None
    if role in ADMIN_ROLES:
        return True
    cursor.execute(
        "SELECT c.id FROM complaints c WHERE c.id = %s AND " + _case_access_sql("c"),
        (case_id, user_id, user_id, user_id),
    )
    return cursor.fetchone() is not None


def _serialize_value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row):
    return {key: _serialize_value(value) for key, value in dict(row).items()}


def _audit(cursor, user_id, action, entity_type, entity_id, details):
    cursor.execute(
        """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
           VALUES (%s, %s, %s, %s, %s)""",
        (user_id, action, entity_type, str(entity_id), json.dumps(details, ensure_ascii=False)),
    )


def _notify_other_assignees(cursor, complaint_id, actor_id, title, message):
    cursor.execute(
        """SELECT DISTINCT assigned_to FROM complaint_assignments
           WHERE complaint_id = %s AND released_at IS NULL AND assigned_to IS NOT NULL""",
        (complaint_id,),
    )
    for row in cursor.fetchall():
        recipient_id = int(row["assigned_to"])
        if recipient_id == actor_id:
            continue
        cursor.execute(
            """INSERT INTO notifications (user_id, complaint_id, title, message, severity)
               VALUES (%s, %s, %s, %s, 'INFO')""",
            (recipient_id, complaint_id, title, message),
        )


def _get_case(cursor, case_id):
    cursor.execute(
        """SELECT c.id, c.case_number, c.institution_id, i.name AS institution_name,
                  c.title, c.description, c.category, c.priority, c.status,
                  c.current_bureau_id, b.name AS bureau_name, c.created_by,
                  c.reported_at, c.sla_due_at, c.created_at, c.updated_at
           FROM complaints c
           JOIN institutions i ON i.id = c.institution_id
           LEFT JOIN bureaus b ON b.id = c.current_bureau_id
           WHERE c.id = %s""",
        (case_id,),
    )
    return cursor.fetchone()


@workflow_bp.get("/cases")
@jwt_required()
def list_workflow_cases():
    status = request.args.get("status", "").strip().upper()
    priority = request.args.get("priority", "").strip().upper()
    search = request.args.get("search", "").strip()[:120]
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 50, type=int), 1), MAX_PAGE_SIZE)

    if status and status not in VALID_STATUSES:
        return jsonify({"success": False, "message": "Invalid complaint status filter."}), 400
    if priority and priority not in VALID_PRIORITIES:
        return jsonify({"success": False, "message": "Invalid priority filter."}), 400

    role, user_id = _role_user()
    conditions = []
    params = []
    if status:
        conditions.append("c.status = %s")
        params.append(status)
    if priority:
        conditions.append("c.priority = %s")
        params.append(priority)
    if search:
        wildcard = f"%{search}%"
        conditions.append("(c.case_number LIKE %s OR c.title LIKE %s OR i.name LIKE %s)")
        params.extend([wildcard, wildcard, wildcard])
    if role not in ADMIN_ROLES:
        conditions.append(_case_access_sql("c"))
        params.extend([user_id, user_id, user_id])

    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * page_size
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT COUNT(*) AS total FROM complaints c JOIN institutions i ON i.id = c.institution_id" + where_sql,
            tuple(params),
        )
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """SELECT c.id, c.case_number, c.title, c.category, c.priority, c.status,
                      c.institution_id, i.name AS institution_name, c.current_bureau_id,
                      b.name AS bureau_name, c.sla_due_at, c.created_at, c.updated_at
               FROM complaints c
               JOIN institutions i ON i.id = c.institution_id
               LEFT JOIN bureaus b ON b.id = c.current_bureau_id""" + where_sql +
            " ORDER BY c.updated_at DESC, c.id DESC LIMIT %s OFFSET %s",
            tuple(params + [page_size, offset]),
        )
        items = [_serialize_row(row) for row in cursor.fetchall()]
        return jsonify({"success": True, "data": {
            "items": items, "total": total, "page": page, "page_size": page_size
        }})
    except mysql.connector.Error:
        current_app.logger.exception("Workflow case list database error")
        return jsonify({"success": False, "message": "Unable to load workflow cases."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@workflow_bp.get("/cases/<int:case_id>/history")
@jwt_required()
def get_case_history(case_id):
    role, user_id = _role_user()
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        access = _has_case_access(cursor, case_id, role, user_id)
        if access is None:
            return jsonify({"success": False, "message": "Complaint not found."}), 404
        if not access:
            return jsonify({"success": False, "message": "You do not have access to this complaint."}), 403

        case = _get_case(cursor, case_id)
        cursor.execute(
            """SELECT ca.id, ca.complaint_id, ca.actor_id, u.full_name AS actor_name,
                      ca.action_type, ca.from_status, ca.to_status, ca.comment, ca.created_at
               FROM case_actions ca
               LEFT JOIN users u ON u.id = ca.actor_id
               WHERE ca.complaint_id = %s
               ORDER BY ca.created_at ASC, ca.id ASC""",
            (case_id,),
        )
        actions = [_serialize_row(row) for row in cursor.fetchall()]
        return jsonify({"success": True, "data": {
            "case": _serialize_row(case), "actions": actions
        }})
    except mysql.connector.Error:
        current_app.logger.exception("Case history database error")
        return jsonify({"success": False, "message": "Unable to load case history."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@workflow_bp.post("/cases/<int:case_id>/remarks")
@jwt_required()
def add_case_remark(case_id):
    role, user_id = _role_user()
    if role not in WRITE_ROLES:
        return jsonify({"success": False, "message": "Your role is read-only for workflow updates."}), 403

    data = request.get_json(silent=True) or {}
    comment_value = data.get("comment")
    if not isinstance(comment_value, str) or not comment_value.strip():
        return jsonify({"success": False, "message": "Enter a case remark."}), 400
    comment = comment_value.strip()
    if len(comment) > 2000:
        return jsonify({"success": False, "message": "Remark must be 2000 characters or fewer."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, status, case_number FROM complaints WHERE id = %s FOR UPDATE", (case_id,))
        case = cursor.fetchone()
        if not case:
            return jsonify({"success": False, "message": "Complaint not found."}), 404
        if not _has_case_access(cursor, case_id, role, user_id):
            return jsonify({"success": False, "message": "You do not have access to this complaint."}), 403

        cursor.execute(
            """INSERT INTO case_actions
               (complaint_id, actor_id, action_type, from_status, to_status, comment)
               VALUES (%s, %s, 'CASE_REMARK_ADDED', %s, %s, %s)""",
            (case_id, user_id, case["status"], case["status"], comment),
        )
        action_id = int(cursor.lastrowid)
        _audit(cursor, user_id, "CASE_REMARK_ADDED", "complaint", case_id, {
            "case_number": case["case_number"], "action_id": action_id,
        })
        _notify_other_assignees(
            cursor, case_id, user_id, "New case remark added",
            f"A new remark was added to case {case['case_number']}."
        )
        conn.commit()
        return jsonify({"success": True, "message": "Case remark added.", "data": {"action_id": action_id}}), 201
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Case remark database error")
        return jsonify({"success": False, "message": "Unable to add case remark."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@workflow_bp.patch("/cases/<int:case_id>/status")
@jwt_required()
def change_workflow_status(case_id):
    role, user_id = _role_user()
    if role not in WRITE_ROLES:
        return jsonify({"success": False, "message": "Your role is read-only for workflow updates."}), 403

    data = request.get_json(silent=True) or {}
    next_status = str(data.get("status", "")).strip().upper()
    if next_status not in VALID_STATUSES:
        return jsonify({"success": False, "message": "Provide a valid complaint status."}), 400
    comment_value = data.get("comment", "")
    if comment_value is not None and not isinstance(comment_value, str):
        return jsonify({"success": False, "message": "Status comment must be text."}), 400
    comment = (comment_value or "").strip() or None
    if comment and len(comment) > 2000:
        return jsonify({"success": False, "message": "Status comment must be 2000 characters or fewer."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, case_number, status FROM complaints WHERE id = %s FOR UPDATE",
            (case_id,),
        )
        case = cursor.fetchone()
        if not case:
            return jsonify({"success": False, "message": "Complaint not found."}), 404
        if not _has_case_access(cursor, case_id, role, user_id):
            return jsonify({"success": False, "message": "You do not have access to this complaint."}), 403

        previous_status = case["status"]
        if next_status == previous_status:
            return jsonify({"success": False, "message": "Complaint already has that status."}), 400
        if next_status not in ALLOWED_TRANSITIONS.get(previous_status, set()):
            return jsonify({
                "success": False,
                "message": f"Status cannot change from {previous_status} to {next_status}.",
            }), 400

        cursor.execute("UPDATE complaints SET status = %s WHERE id = %s", (next_status, case_id))
        cursor.execute(
            """INSERT INTO case_actions
               (complaint_id, actor_id, action_type, from_status, to_status, comment)
               VALUES (%s, %s, 'STATUS_CHANGED', %s, %s, %s)""",
            (case_id, user_id, previous_status, next_status, comment),
        )
        action_id = int(cursor.lastrowid)
        _audit(cursor, user_id, "CASE_STATUS_CHANGED", "complaint", case_id, {
            "case_number": case["case_number"], "action_id": action_id,
            "from_status": previous_status, "to_status": next_status,
        })
        _notify_other_assignees(
            cursor, case_id, user_id, "Case status updated",
            f"Case {case['case_number']} changed from {previous_status} to {next_status}."
        )
        conn.commit()
        return jsonify({"success": True, "message": "Case status updated.", "data": {
            "id": case_id, "previous_status": previous_status, "status": next_status,
            "action_id": action_id,
        }})
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Workflow status update database error")
        return jsonify({"success": False, "message": "Unable to update workflow status."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
