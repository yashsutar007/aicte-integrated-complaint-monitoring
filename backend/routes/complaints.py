# Save as: backend/routes/complaints.py

from datetime import datetime, timedelta
from uuid import uuid4

import mysql.connector
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from db import get_db_connection

complaints_bp = Blueprint("complaints", __name__, url_prefix="/api/complaints")
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


def _case_number():
    return f"AICTE-{datetime.now():%y%m%d}-{uuid4().hex[:8].upper()}"


@complaints_bp.get("")
@jwt_required()
def list_complaints():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip().upper()
    priority = request.args.get("priority", "").strip().upper()
    institution_id = request.args.get("institution_id", type=int)
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 50, type=int), 1), 100)

    if status and status not in VALID_STATUSES:
        return jsonify({"success": False, "message": "Invalid complaint status."}), 400
    if priority and priority not in VALID_PRIORITIES:
        return jsonify({"success": False, "message": "Invalid priority."}), 400

    conditions = []
    params = []
    if search:
        like = f"%{search}%"
        conditions.append("(c.case_number LIKE %s OR c.title LIKE %s OR c.description LIKE %s OR i.name LIKE %s)")
        params.extend([like, like, like, like])
    if status:
        conditions.append("c.status = %s")
        params.append(status)
    if priority:
        conditions.append("c.priority = %s")
        params.append(priority)
    if institution_id:
        conditions.append("c.institution_id = %s")
        params.append(institution_id)

    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * page_size
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT COUNT(*) AS total FROM complaints c JOIN institutions i ON i.id=c.institution_id" + where_sql,
            tuple(params),
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            """SELECT c.id, c.case_number, c.institution_id, i.name AS institution_name,
                      c.title, c.description, c.category, c.priority, c.status,
                      c.current_bureau_id, b.name AS bureau_name, c.created_by,
                      c.reported_at, c.sla_due_at, c.created_at, c.updated_at
               FROM complaints c
               JOIN institutions i ON i.id = c.institution_id
               LEFT JOIN bureaus b ON b.id = c.current_bureau_id""" + where_sql +
            " ORDER BY c.created_at DESC, c.id DESC LIMIT %s OFFSET %s",
            tuple(params + [page_size, offset]),
        )
        items = cursor.fetchall()
        return jsonify({"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}})
    except mysql.connector.Error:
        current_app.logger.exception("Complaint list database error")
        return jsonify({"success": False, "message": "Unable to load complaints."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@complaints_bp.post("")
@jwt_required()
def create_complaint():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    category = str(data.get("category", "")).strip()
    institution_id = data.get("institution_id")
    priority = str(data.get("priority", "MEDIUM")).strip().upper()

    if not institution_id or not title or not description or not category:
        return jsonify({"success": False, "message": "Institution, title, description and category are required."}), 400
    try:
        institution_id = int(institution_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Select a valid institution."}), 400
    if institution_id <= 0:
        return jsonify({"success": False, "message": "Select a valid institution."}), 400
    if len(title) > 255:
        return jsonify({"success": False, "message": "Title must be 255 characters or fewer."}), 400
    if len(category) > 100:
        return jsonify({"success": False, "message": "Category must be 100 characters or fewer."}), 400
    if priority not in VALID_PRIORITIES:
        return jsonify({"success": False, "message": "Invalid priority."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM institutions WHERE id = %s AND status = 'ACTIVE'", (institution_id,))
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "Active institution not found. Create or activate the institution first."}), 400

        cursor.execute("SELECT target_hours FROM sla_policies WHERE priority = %s AND is_active = TRUE", (priority,))
        policy = cursor.fetchone()
        target_hours = int(policy["target_hours"]) if policy else {"LOW": 240, "MEDIUM": 120, "HIGH": 48, "CRITICAL": 24}[priority]
        due_at = datetime.now() + timedelta(hours=target_hours)
        case_number = _case_number()
        cursor.execute(
            """INSERT INTO complaints
               (case_number, institution_id, title, description, category, priority,
                status, created_by, sla_due_at)
               VALUES (%s, %s, %s, %s, %s, %s, 'SUBMITTED', %s, %s)""",
            (case_number, institution_id, title, description, category, priority,
             int(get_jwt_identity()), due_at),
        )
        complaint_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO case_actions
               (complaint_id, actor_id, action_type, from_status, to_status, comment)
               VALUES (%s, %s, 'CASE_CREATED', NULL, 'SUBMITTED', %s)""",
            (complaint_id, int(get_jwt_identity()), "Complaint registered."),
        )
        conn.commit()
        cursor.execute(
            """SELECT c.id, c.case_number, c.institution_id, i.name AS institution_name,
                      c.title, c.description, c.category, c.priority, c.status,
                      c.current_bureau_id, c.created_by, c.reported_at, c.sla_due_at,
                      c.created_at, c.updated_at
               FROM complaints c JOIN institutions i ON i.id = c.institution_id
               WHERE c.id = %s""",
            (complaint_id,),
        )
        complaint = cursor.fetchone()
        return jsonify({"success": True, "message": "Complaint registered.", "data": {"complaint": complaint}}), 201
    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": "The institution or user reference is invalid."}), 400
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Complaint creation database error")
        return jsonify({"success": False, "message": "Unable to register complaint."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@complaints_bp.get("/<int:complaint_id>")
@jwt_required()
def get_complaint(complaint_id):
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT c.id, c.case_number, c.institution_id, i.name AS institution_name,
                      c.title, c.description, c.category, c.priority, c.status,
                      c.current_bureau_id, b.name AS bureau_name, c.created_by,
                      c.reported_at, c.sla_due_at, c.created_at, c.updated_at
               FROM complaints c JOIN institutions i ON i.id = c.institution_id
               LEFT JOIN bureaus b ON b.id = c.current_bureau_id
               WHERE c.id = %s""",
            (complaint_id,),
        )
        complaint = cursor.fetchone()
        if not complaint:
            return jsonify({"success": False, "message": "Complaint not found."}), 404
        cursor.execute(
            """SELECT id, actor_id, action_type, from_status, to_status, comment, created_at
               FROM case_actions WHERE complaint_id = %s ORDER BY created_at DESC, id DESC""",
            (complaint_id,),
        )
        actions = cursor.fetchall()
        return jsonify({"success": True, "data": {"complaint": complaint, "actions": actions}})
    except mysql.connector.Error:
        current_app.logger.exception("Complaint detail database error")
        return jsonify({"success": False, "message": "Unable to load complaint."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@complaints_bp.patch("/<int:complaint_id>/status")
@jwt_required()
def update_complaint_status(complaint_id):
    data = request.get_json(silent=True) or {}
    next_status = str(data.get("status", "")).strip().upper()
    comment = str(data.get("comment", "")).strip() or None
    if next_status not in VALID_STATUSES:
        return jsonify({"success": False, "message": "Provide a valid complaint status."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status FROM complaints WHERE id = %s", (complaint_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Complaint not found."}), 404
        previous_status = row["status"]
        if next_status == previous_status:
            return jsonify({"success": False, "message": "Complaint already has that status."}), 400
        if next_status not in ALLOWED_TRANSITIONS.get(previous_status, set()):
            return jsonify({
                "success": False,
                "message": f"Status cannot change from {previous_status} to {next_status}.",
            }), 400

        cursor.execute("UPDATE complaints SET status = %s WHERE id = %s", (next_status, complaint_id))
        cursor.execute(
            """INSERT INTO case_actions
               (complaint_id, actor_id, action_type, from_status, to_status, comment)
               VALUES (%s, %s, 'STATUS_CHANGED', %s, %s, %s)""",
            (complaint_id, int(get_jwt_identity()), previous_status, next_status, comment),
        )
        conn.commit()
        return jsonify({
            "success": True,
            "message": "Complaint status updated.",
            "data": {"id": complaint_id, "previous_status": previous_status, "status": next_status},
        })
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Complaint status update database error")
        return jsonify({"success": False, "message": "Unable to update complaint status."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
