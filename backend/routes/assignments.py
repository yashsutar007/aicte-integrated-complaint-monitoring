"""Bureau and case assignment endpoints for the AICTE complaint prototype."""

import json
import re
from datetime import datetime

import mysql.connector
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from db import get_db_connection

bureaus_bp = Blueprint("bureaus", __name__, url_prefix="/api/bureaus")
assignments_bp = Blueprint("assignments", __name__, url_prefix="/api/assignments")
ADMIN_ROLES = {"ADMIN", "SUPER_ADMIN"}
ASSIGNMENT_ROLES = {"ADMIN", "SUPER_ADMIN", "BUREAU_OFFICER"}
VALID_CASE_STATUSES = {
    "SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "AWAITING_INFORMATION",
    "RESOLVED", "CLOSED", "REOPENED",
}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _role():
    return str(get_jwt().get("role", "CASE_OFFICER")).upper()


def _current_user_id():
    try:
        return int(get_jwt_identity())
    except (TypeError, ValueError):
        return 0


def _forbidden(message="You do not have permission to perform this action."):
    return jsonify({"success": False, "message": message}), 403


def _audit(cursor, action, entity_type, entity_id, details):
    cursor.execute(
        """INSERT INTO audit_logs
           (user_id, action, entity_type, entity_id, details, ip_address)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            _current_user_id(), action, entity_type, str(entity_id),
            json.dumps(details, ensure_ascii=False), request.remote_addr,
        ),
    )


def _clean_bureau_fields(data, existing=None):
    existing = existing or {}
    name = str(data.get("name", existing.get("name", ""))).strip()
    code = str(data.get("code", existing.get("code", ""))).strip().upper()
    description_value = data.get("description", existing.get("description"))
    description = str(description_value or "").strip() or None

    if not name:
        return None, (jsonify({"success": False, "message": "Bureau name is required."}), 400)
    if len(name) > 150:
        return None, (jsonify({"success": False, "message": "Bureau name must be 150 characters or fewer."}), 400)
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,39}", code):
        return None, (jsonify({"success": False, "message": "Use a bureau code of 2–40 letters, numbers, hyphens or underscores."}), 400)
    if description and len(description) > 2000:
        return None, (jsonify({"success": False, "message": "Description must be 2000 characters or fewer."}), 400)
    return {"name": name, "code": code, "description": description}, None


@bureaus_bp.get("")
@jwt_required()
def list_bureaus():
    conn = cursor = None
    role = _role()
    user_id = _current_user_id()
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        where = ""
        params = []
        if role in ADMIN_ROLES:
            if request.args.get("active_only", "false").lower() in {"1", "true", "yes"}:
                where = "WHERE b.is_active = TRUE"
        else:
            where = "WHERE b.is_active = TRUE AND EXISTS (SELECT 1 FROM user_bureaus my_bureau WHERE my_bureau.bureau_id = b.id AND my_bureau.user_id = %s)"
            params.append(user_id)
        cursor.execute(
            """SELECT b.id, b.name, b.code, b.description, b.is_active, b.created_at,
                      COUNT(DISTINCT ub.user_id) AS member_count,
                      COUNT(DISTINCT CASE WHEN ca.released_at IS NULL THEN ca.complaint_id END)
                        AS active_assignment_count
               FROM bureaus b
               LEFT JOIN user_bureaus ub ON ub.bureau_id = b.id
               LEFT JOIN complaint_assignments ca ON ca.bureau_id = b.id
               """ + where + " GROUP BY b.id ORDER BY b.is_active DESC, b.name ASC",
            tuple(params),
        )
        return jsonify({"success": True, "data": {"items": cursor.fetchall()}})
    except mysql.connector.Error:
        current_app.logger.exception("Bureau list database error")
        return jsonify({"success": False, "message": "Unable to load Bureaus and Cells."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@bureaus_bp.post("")
@jwt_required()
def create_bureau():
    if _role() not in ADMIN_ROLES:
        return _forbidden("Only administrators can create Bureaus or Cells.")
    data = request.get_json(silent=True) or {}
    cleaned, error = _clean_bureau_fields(data)
    if error:
        return error
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO bureaus (name, code, description) VALUES (%s, %s, %s)",
            (cleaned["name"], cleaned["code"], cleaned["description"]),
        )
        bureau_id = cursor.lastrowid
        _audit(cursor, "BUREAU_CREATED", "bureau", bureau_id, {"name": cleaned["name"], "code": cleaned["code"]})
        conn.commit()
        cursor.execute(
            "SELECT id, name, code, description, is_active, created_at FROM bureaus WHERE id=%s",
            (bureau_id,),
        )
        return jsonify({"success": True, "message": "Bureau or Cell created.", "data": {"bureau": cursor.fetchone()}}), 201
    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": "That bureau code or name is already in use."}), 409
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Bureau creation database error")
        return jsonify({"success": False, "message": "Unable to create Bureau or Cell."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@bureaus_bp.put("/<int:bureau_id>")
@jwt_required()
def update_bureau(bureau_id):
    if _role() not in ADMIN_ROLES:
        return _forbidden("Only administrators can update Bureaus or Cells.")
    data = request.get_json(silent=True) or {}
    if not any(key in data for key in ("name", "code", "description")):
        return jsonify({"success": False, "message": "Provide a bureau name, code or description to update."}), 400
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, code, description FROM bureaus WHERE id=%s", (bureau_id,))
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"success": False, "message": "Bureau or Cell not found."}), 404
        cleaned, error = _clean_bureau_fields(data, existing)
        if error:
            return error
        cursor.execute(
            "UPDATE bureaus SET name=%s, code=%s, description=%s WHERE id=%s",
            (cleaned["name"], cleaned["code"], cleaned["description"], bureau_id),
        )
        _audit(cursor, "BUREAU_UPDATED", "bureau", bureau_id, cleaned)
        conn.commit()
        cursor.execute(
            "SELECT id, name, code, description, is_active, created_at FROM bureaus WHERE id=%s",
            (bureau_id,),
        )
        return jsonify({"success": True, "message": "Bureau or Cell updated.", "data": {"bureau": cursor.fetchone()}})
    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": "That bureau code or name is already in use."}), 409
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Bureau update database error")
        return jsonify({"success": False, "message": "Unable to update Bureau or Cell."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@bureaus_bp.patch("/<int:bureau_id>/status")
@jwt_required()
def set_bureau_status(bureau_id):
    if _role() not in ADMIN_ROLES:
        return _forbidden("Only administrators can change Bureau status.")
    data = request.get_json(silent=True) or {}
    is_active = data.get("is_active")
    if type(is_active) is not bool:
        return jsonify({"success": False, "message": "is_active must be true or false."}), 400
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, is_active FROM bureaus WHERE id=%s", (bureau_id,))
        bureau = cursor.fetchone()
        if not bureau:
            return jsonify({"success": False, "message": "Bureau or Cell not found."}), 404
        cursor.execute("UPDATE bureaus SET is_active=%s WHERE id=%s", (is_active, bureau_id))
        _audit(cursor, "BUREAU_ACTIVATED" if is_active else "BUREAU_DEACTIVATED", "bureau", bureau_id, {"is_active": is_active})
        conn.commit()
        return jsonify({"success": True, "message": f"Bureau { 'activated' if is_active else 'deactivated' }.", "data": {"id": bureau_id, "is_active": is_active}})
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Bureau status database error")
        return jsonify({"success": False, "message": "Unable to update Bureau status."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@bureaus_bp.get("/eligible-officers")
@jwt_required()
def eligible_officers():
    if _role() not in ADMIN_ROLES:
        return _forbidden("Only administrators can view the officer directory for membership management.")
    search = request.args.get("search", "").strip()
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        params = []
        where = "WHERE is_active=TRUE AND role IN ('CASE_OFFICER','BUREAU_OFFICER')"
        if search:
            where += " AND (full_name LIKE %s OR email LIKE %s)"
            params.extend([f"%{search}%", f"%{search}%"])
        cursor.execute(
            "SELECT id, full_name, email, role FROM users " + where + " ORDER BY full_name LIMIT 250",
            tuple(params),
        )
        return jsonify({"success": True, "data": {"items": cursor.fetchall()}})
    except mysql.connector.Error:
        current_app.logger.exception("Eligible officer list database error")
        return jsonify({"success": False, "message": "Unable to load eligible officers."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@bureaus_bp.get("/<int:bureau_id>/members")
@jwt_required()
def list_bureau_members(bureau_id):
    role = _role()
    user_id = _current_user_id()
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, is_active FROM bureaus WHERE id=%s", (bureau_id,))
        bureau = cursor.fetchone()
        if not bureau:
            return jsonify({"success": False, "message": "Bureau or Cell not found."}), 404
        if role not in ADMIN_ROLES:
            cursor.execute("SELECT 1 FROM user_bureaus WHERE bureau_id=%s AND user_id=%s", (bureau_id, user_id))
            if not cursor.fetchone():
                return _forbidden("You are not a member of this Bureau or Cell.")
        cursor.execute(
            """SELECT u.id, u.full_name, u.email, u.role, u.is_active,
                      ub.bureau_id, ub.bureau_id AS membership_bureau_id
               FROM user_bureaus ub JOIN users u ON u.id=ub.user_id
               WHERE ub.bureau_id=%s ORDER BY u.full_name""",
            (bureau_id,),
        )
        return jsonify({"success": True, "data": {"items": cursor.fetchall()}})
    except mysql.connector.Error:
        current_app.logger.exception("Bureau member list database error")
        return jsonify({"success": False, "message": "Unable to load Bureau members."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@bureaus_bp.post("/<int:bureau_id>/members")
@jwt_required()
def add_bureau_member(bureau_id):
    if _role() not in ADMIN_ROLES:
        return _forbidden("Only administrators can manage Bureau membership.")
    data = request.get_json(silent=True) or {}
    try:
        member_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Select a valid officer."}), 400
    if member_id <= 0:
        return jsonify({"success": False, "message": "Select a valid officer."}), 400
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, is_active FROM bureaus WHERE id=%s", (bureau_id,))
        bureau = cursor.fetchone()
        if not bureau or not bureau["is_active"]:
            return jsonify({"success": False, "message": "Active Bureau or Cell not found."}), 404
        cursor.execute(
            "SELECT id, full_name, role FROM users WHERE id=%s AND is_active=TRUE AND role IN ('CASE_OFFICER','BUREAU_OFFICER')",
            (member_id,),
        )
        member = cursor.fetchone()
        if not member:
            return jsonify({"success": False, "message": "Select an active case officer or Bureau officer."}), 400
        cursor.execute("INSERT IGNORE INTO user_bureaus (user_id, bureau_id) VALUES (%s, %s)", (member_id, bureau_id))
        added = cursor.rowcount == 1
        if added:
            _audit(cursor, "BUREAU_MEMBER_ADDED", "bureau", bureau_id, {"user_id": member_id, "user_name": member["full_name"]})
        conn.commit()
        return jsonify({"success": True, "message": "Officer added to Bureau." if added else "Officer is already a member of this Bureau.", "data": {"user_id": member_id, "bureau_id": bureau_id, "added": added}}), 201 if added else 200
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Add Bureau member database error")
        return jsonify({"success": False, "message": "Unable to add Bureau member."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@bureaus_bp.delete("/<int:bureau_id>/members/<int:user_id>")
@jwt_required()
def remove_bureau_member(bureau_id, user_id):
    if _role() not in ADMIN_ROLES:
        return _forbidden("Only administrators can manage Bureau membership.")
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT ca.id FROM complaint_assignments ca
               JOIN complaints c ON c.id=ca.complaint_id
               WHERE ca.bureau_id=%s AND ca.assigned_to=%s AND ca.released_at IS NULL
                 AND c.status NOT IN ('RESOLVED','CLOSED') LIMIT 1""",
            (bureau_id, user_id),
        )
        if cursor.fetchone():
            return jsonify({"success": False, "message": "Reassign this officer's active cases before removing them from the Bureau."}), 409
        cursor.execute("DELETE FROM user_bureaus WHERE bureau_id=%s AND user_id=%s", (bureau_id, user_id))
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({"success": False, "message": "Bureau membership not found."}), 404
        _audit(cursor, "BUREAU_MEMBER_REMOVED", "bureau", bureau_id, {"user_id": user_id})
        conn.commit()
        return jsonify({"success": True, "message": "Officer removed from Bureau."})
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Remove Bureau member database error")
        return jsonify({"success": False, "message": "Unable to remove Bureau member."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@assignments_bp.get("")
@jwt_required()
def list_assignments():
    role = _role()
    user_id = _current_user_id()
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip().upper()
    priority = request.args.get("priority", "").strip().upper()
    bureau_id = request.args.get("bureau_id", type=int)
    unassigned_only = request.args.get("unassigned", "false").lower() in {"1", "true", "yes"}
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 50, type=int), 1), 100)
    if status and status not in VALID_CASE_STATUSES:
        return jsonify({"success": False, "message": "Invalid complaint status."}), 400
    if priority and priority not in VALID_PRIORITIES:
        return jsonify({"success": False, "message": "Invalid complaint priority."}), 400
    conditions = []
    params = []
    if search:
        like = f"%{search}%"
        conditions.append("(c.case_number LIKE %s OR c.title LIKE %s OR i.name LIKE %s)")
        params.extend([like, like, like])
    if status:
        conditions.append("c.status=%s")
        params.append(status)
    if priority:
        conditions.append("c.priority=%s")
        params.append(priority)
    if bureau_id:
        conditions.append("c.current_bureau_id=%s")
        params.append(bureau_id)
    if unassigned_only:
        conditions.append("ca.id IS NULL")
    if role not in ADMIN_ROLES:
        conditions.append("(c.created_by=%s OR c.current_bureau_id IN (SELECT bureau_id FROM user_bureaus WHERE user_id=%s))")
        params.extend([user_id, user_id])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    joins = """ FROM complaints c
               JOIN institutions i ON i.id=c.institution_id
               LEFT JOIN complaint_assignments ca ON ca.complaint_id=c.id AND ca.released_at IS NULL
               LEFT JOIN bureaus b ON b.id=c.current_bureau_id
               LEFT JOIN users u ON u.id=ca.assigned_to """
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(DISTINCT c.id) AS total" + joins + where, tuple(params))
        total = int(cursor.fetchone()["total"])
        offset = (page - 1) * page_size
        cursor.execute(
            """SELECT c.id AS complaint_id, c.case_number, c.title, c.category,
                      c.institution_id, i.name AS institution_name, c.priority, c.status,
                      c.sla_due_at, c.created_at, c.created_by,
                      c.current_bureau_id AS bureau_id, b.name AS bureau_name,
                      ca.id AS assignment_id, ca.assigned_to, u.full_name AS assigned_to_name,
                      u.email AS assigned_to_email, ca.assigned_by, ca.assigned_at,
                      CASE WHEN ca.id IS NULL THEN 'UNASSIGNED' ELSE 'ASSIGNED' END AS assignment_state
               """ + joins + where +
            " ORDER BY (ca.id IS NULL) DESC, FIELD(c.priority,'CRITICAL','HIGH','MEDIUM','LOW'), c.created_at DESC LIMIT %s OFFSET %s",
            tuple(params + [page_size, offset]),
        )
        return jsonify({"success": True, "data": {"items": cursor.fetchall(), "total": total, "page": page, "page_size": page_size}})
    except mysql.connector.Error:
        current_app.logger.exception("Assignment list database error")
        return jsonify({"success": False, "message": "Unable to load case assignments."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@assignments_bp.post("")
@jwt_required()
def create_or_reassign_case():
    role = _role()
    if role not in ASSIGNMENT_ROLES:
        return _forbidden("Only administrators and Bureau officers can assign cases.")
    data = request.get_json(silent=True) or {}
    try:
        complaint_id = int(data.get("complaint_id"))
        bureau_id = int(data.get("bureau_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Select a case and a Bureau or Cell."}), 400
    if complaint_id <= 0 or bureau_id <= 0:
        return jsonify({"success": False, "message": "Select a valid case and Bureau or Cell."}), 400
    assigned_to_value = data.get("assigned_to")
    assigned_to = None
    if assigned_to_value not in (None, ""):
        try:
            assigned_to = int(assigned_to_value)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Select a valid officer or leave the officer field blank."}), 400
        if assigned_to <= 0:
            return jsonify({"success": False, "message": "Select a valid officer or leave the officer field blank."}), 400
    note = str(data.get("note", "")).strip() or None
    if note and len(note) > 1000:
        return jsonify({"success": False, "message": "Assignment note must be 1000 characters or fewer."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        conn.start_transaction()
        cursor.execute("SELECT id, name, is_active FROM bureaus WHERE id=%s FOR UPDATE", (bureau_id,))
        bureau = cursor.fetchone()
        if not bureau or not bureau["is_active"]:
            conn.rollback()
            return jsonify({"success": False, "message": "Active Bureau or Cell not found."}), 400
        if role == "BUREAU_OFFICER":
            cursor.execute("SELECT 1 FROM user_bureaus WHERE user_id=%s AND bureau_id=%s", (_current_user_id(), bureau_id))
            if not cursor.fetchone():
                conn.rollback()
                return _forbidden("You can assign cases only within your own Bureau or Cell.")

        cursor.execute(
            "SELECT id, case_number, status, current_bureau_id FROM complaints WHERE id=%s FOR UPDATE",
            (complaint_id,),
        )
        case = cursor.fetchone()
        if not case:
            conn.rollback()
            return jsonify({"success": False, "message": "Complaint case not found."}), 404
        if case["status"] in {"RESOLVED", "CLOSED"}:
            conn.rollback()
            return jsonify({"success": False, "message": "Reopen this case before assigning it."}), 409

        assignee = None
        if assigned_to is not None:
            cursor.execute(
                """SELECT u.id, u.full_name, u.email FROM users u
                   JOIN user_bureaus ub ON ub.user_id=u.id
                   WHERE u.id=%s AND u.is_active=TRUE
                     AND u.role IN ('CASE_OFFICER','BUREAU_OFFICER') AND ub.bureau_id=%s""",
                (assigned_to, bureau_id),
            )
            assignee = cursor.fetchone()
            if not assignee:
                conn.rollback()
                return jsonify({"success": False, "message": "The selected officer must be active and a member of the selected Bureau."}), 400

        cursor.execute(
            "SELECT id, bureau_id, assigned_to FROM complaint_assignments WHERE complaint_id=%s AND released_at IS NULL ORDER BY id DESC LIMIT 1 FOR UPDATE",
            (complaint_id,),
        )
        old_assignment = cursor.fetchone()
        if old_assignment:
            cursor.execute("UPDATE complaint_assignments SET released_at=%s WHERE id=%s", (datetime.now(), old_assignment["id"]))

        cursor.execute(
            """INSERT INTO complaint_assignments
               (complaint_id, bureau_id, assigned_to, assigned_by, note)
               VALUES (%s, %s, %s, %s, %s)""",
            (complaint_id, bureau_id, assigned_to, _current_user_id(), note),
        )
        assignment_id = cursor.lastrowid
        cursor.execute("UPDATE complaints SET current_bureau_id=%s, status='ASSIGNED' WHERE id=%s", (bureau_id, complaint_id))
        action_type = "CASE_REASSIGNED" if old_assignment else "CASE_ASSIGNED"
        action_comment = note or f"Assigned to {bureau['name']}" + (f" / {assignee['full_name']}" if assignee else "")
        cursor.execute(
            """INSERT INTO case_actions
               (complaint_id, actor_id, action_type, from_status, to_status, comment)
               VALUES (%s, %s, %s, %s, 'ASSIGNED', %s)""",
            (complaint_id, _current_user_id(), action_type, case["status"], action_comment),
        )
        if assignee:
            cursor.execute(
                """INSERT INTO notifications (user_id, complaint_id, title, message, severity)
                   VALUES (%s, %s, %s, %s, 'INFO')""",
                (assignee["id"], complaint_id, "Case assigned to you", f"{case['case_number']} has been assigned to you in {bureau['name']}."),
            )
        _audit(cursor, action_type, "complaint", complaint_id, {
            "case_number": case["case_number"], "bureau_id": bureau_id,
            "bureau_name": bureau["name"], "assigned_to": assigned_to,
            "assigned_to_name": assignee["full_name"] if assignee else None,
            "previous_assignment_id": old_assignment["id"] if old_assignment else None,
        })
        conn.commit()
        cursor.execute(
            """SELECT ca.id AS assignment_id, ca.complaint_id, c.case_number, c.title,
                      ca.bureau_id, b.name AS bureau_name, ca.assigned_to,
                      u.full_name AS assigned_to_name, ca.assigned_by, ca.assigned_at, ca.note
               FROM complaint_assignments ca
               JOIN complaints c ON c.id=ca.complaint_id
               JOIN bureaus b ON b.id=ca.bureau_id
               LEFT JOIN users u ON u.id=ca.assigned_to
               WHERE ca.id=%s""",
            (assignment_id,),
        )
        assignment = cursor.fetchone()
        return jsonify({"success": True, "message": "Case assignment saved.", "data": {"assignment": assignment}}), 200 if old_assignment else 201
    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": "An assignment reference is invalid. Check the selected case, Bureau and officer."}), 400
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Case assignment database error")
        return jsonify({"success": False, "message": "Unable to assign case. Please retry."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@assignments_bp.get("/complaints/<int:complaint_id>/history")
@jwt_required()
def assignment_history(complaint_id):
    role = _role()
    user_id = _current_user_id()
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, created_by, current_bureau_id FROM complaints WHERE id=%s", (complaint_id,))
        case = cursor.fetchone()
        if not case:
            return jsonify({"success": False, "message": "Complaint case not found."}), 404
        if role not in ADMIN_ROLES and case["created_by"] != user_id:
            cursor.execute("SELECT 1 FROM user_bureaus WHERE user_id=%s AND bureau_id=%s", (user_id, case["current_bureau_id"]))
            if not cursor.fetchone():
                return _forbidden("You cannot view this case's assignment history.")
        cursor.execute(
            """SELECT ca.id AS assignment_id, ca.bureau_id, b.name AS bureau_name,
                      ca.assigned_to, assigned.full_name AS assigned_to_name,
                      ca.assigned_by, assigner.full_name AS assigned_by_name,
                      ca.note, ca.assigned_at, ca.released_at
               FROM complaint_assignments ca JOIN bureaus b ON b.id=ca.bureau_id
               LEFT JOIN users assigned ON assigned.id=ca.assigned_to
               LEFT JOIN users assigner ON assigner.id=ca.assigned_by
               WHERE ca.complaint_id=%s ORDER BY ca.assigned_at DESC, ca.id DESC""",
            (complaint_id,),
        )
        return jsonify({"success": True, "data": {"items": cursor.fetchall()}})
    except mysql.connector.Error:
        current_app.logger.exception("Assignment history database error")
        return jsonify({"success": False, "message": "Unable to load assignment history."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
