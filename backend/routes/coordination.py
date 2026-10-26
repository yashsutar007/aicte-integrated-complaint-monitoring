# Destination: backend/routes/coordination.py
"""Related-case linking and inter-Bureau coordination APIs.

Links are suggestions until an authorized user confirms them. Notes are stored in
case_actions so this module uses the existing schema without a migration.
"""

import json
from datetime import date, datetime
from decimal import Decimal

import mysql.connector
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from db import get_db_connection

coordination_bp = Blueprint("coordination", __name__, url_prefix="/api/coordination")
ADMIN_ROLES = {"ADMIN", "SUPER_ADMIN"}
WRITE_ROLES = {"ADMIN", "SUPER_ADMIN", "BUREAU_OFFICER", "CASE_OFFICER"}
VALID_RELATIONSHIPS = {"RELATED", "FOLLOW_UP"}
VALID_REVIEW_FILTERS = {"ALL", "SUGGESTED", "CONFIRMED", "REJECTED"}
VALID_RELATIONSHIP_FILTERS = {"ALL", "RELATED", "FOLLOW_UP", "POTENTIAL_DUPLICATE"}
MAX_PAGE_SIZE = 100


def _role_user():
    role = str(get_jwt().get("role", "CASE_OFFICER")).upper()
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        user_id = 0
    return role, user_id


def _case_access_sql(alias):
    """Access based on creator, current assignment, or Bureau membership."""
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
    query = "SELECT c.id FROM complaints c WHERE c.id = %s"
    params = [case_id]
    if role not in ADMIN_ROLES:
        query += " AND " + _case_access_sql("c")
        params.extend([user_id, user_id, user_id])
    cursor.execute(query, tuple(params))
    return cursor.fetchone() is not None


def _serialize(rows):
    output = []
    for row in rows:
        item = dict(row)
        for key, value in item.items():
            if isinstance(value, datetime):
                item[key] = value.isoformat(sep=" ")
            elif isinstance(value, date):
                item[key] = value.isoformat()
            elif isinstance(value, Decimal):
                item[key] = float(value)
        output.append(item)
    return output


def _audit(cursor, user_id, action, entity_type, entity_id, details):
    cursor.execute(
        """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
           VALUES (%s, %s, %s, %s, %s)""",
        (user_id, action, entity_type, str(entity_id), json.dumps(details, ensure_ascii=False)),
    )


def _case_action(cursor, complaint_id, user_id, action_type, comment):
    cursor.execute(
        """INSERT INTO case_actions
           (complaint_id, actor_id, action_type, from_status, to_status, comment)
           VALUES (%s, %s, %s, NULL, NULL, %s)""",
        (complaint_id, user_id, action_type, comment),
    )
    return int(cursor.lastrowid)


def _notify_assignees(cursor, complaint_ids, actor_id, title, message):
    if not complaint_ids:
        return
    placeholders = ",".join(["%s"] * len(complaint_ids))
    cursor.execute(
        f"""SELECT assigned_to, MIN(complaint_id) AS complaint_id
            FROM complaint_assignments
            WHERE complaint_id IN ({placeholders})
              AND released_at IS NULL AND assigned_to IS NOT NULL
            GROUP BY assigned_to""",
        tuple(complaint_ids),
    )
    for target in cursor.fetchall():
        recipient_id = int(target["assigned_to"])
        if recipient_id == actor_id:
            continue
        cursor.execute(
            """INSERT INTO notifications
               (user_id, complaint_id, title, message, severity)
               VALUES (%s, %s, %s, %s, 'INFO')""",
            (recipient_id, int(target["complaint_id"]), title, message),
        )


def _get_link(cursor, link_id):
    cursor.execute(
        """SELECT cl.id, cl.complaint_id, cl.related_complaint_id,
                  cl.relationship, cl.review_status, cl.confidence,
                  cl.explanation, cl.created_by, cl.reviewed_by,
                  cl.created_at, cl.reviewed_at,
                  c1.case_number AS case_number_a, c1.title AS title_a,
                  c1.status AS status_a, c1.priority AS priority_a,
                  c1.created_by AS created_by_a,
                  c2.case_number AS case_number_b, c2.title AS title_b,
                  c2.status AS status_b, c2.priority AS priority_b,
                  c2.created_by AS created_by_b
           FROM complaint_links cl
           JOIN complaints c1 ON c1.id = cl.complaint_id
           JOIN complaints c2 ON c2.id = cl.related_complaint_id
           WHERE cl.id = %s""",
        (link_id,),
    )
    return cursor.fetchone()


def _may_access_either(cursor, link, role, user_id):
    return (
        _has_case_access(cursor, int(link["complaint_id"]), role, user_id)
        or _has_case_access(cursor, int(link["related_complaint_id"]), role, user_id)
    )


@coordination_bp.get("/links")
@jwt_required()
def list_related_links():
    review_status = request.args.get("review_status", "ALL").strip().upper()
    relationship = request.args.get("relationship", "ALL").strip().upper()
    if review_status not in VALID_REVIEW_FILTERS:
        return jsonify({"success": False, "message": "Invalid review_status filter."}), 400
    if relationship not in VALID_RELATIONSHIP_FILTERS:
        return jsonify({"success": False, "message": "Invalid relationship filter."}), 400

    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 50, type=int), 1), MAX_PAGE_SIZE)
    search = request.args.get("search", "").strip()[:120]
    role, user_id = _role_user()

    conditions = ["1=1"]
    params = []
    if review_status != "ALL":
        conditions.append("cl.review_status = %s")
        params.append(review_status)
    if relationship != "ALL":
        conditions.append("cl.relationship = %s")
        params.append(relationship)
    if search:
        wildcard = f"%{search}%"
        conditions.append("(c1.case_number LIKE %s OR c2.case_number LIKE %s OR c1.title LIKE %s OR c2.title LIKE %s)")
        params.extend([wildcard] * 4)

    if role not in ADMIN_ROLES:
        # A user who can access either side may see the relationship metadata so
        # their Bureau can coordinate; writes still require access to both sides.
        conditions.append(f"({_case_access_sql('c1')} OR {_case_access_sql('c2')})")
        params.extend([user_id] * 6)

    from_sql = """ FROM complaint_links cl
        JOIN complaints c1 ON c1.id = cl.complaint_id
        JOIN institutions i1 ON i1.id = c1.institution_id
        LEFT JOIN bureaus b1 ON b1.id = c1.current_bureau_id
        JOIN complaints c2 ON c2.id = cl.related_complaint_id
        JOIN institutions i2 ON i2.id = c2.institution_id
        LEFT JOIN bureaus b2 ON b2.id = c2.current_bureau_id """
    where_sql = " WHERE " + " AND ".join(conditions)
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total" + from_sql + where_sql, tuple(params))
        total = int((cursor.fetchone() or {}).get("total", 0))
        cursor.execute(
            """SELECT cl.id, cl.complaint_id, cl.related_complaint_id,
                      cl.relationship, cl.review_status, cl.confidence,
                      cl.explanation, cl.created_by, cl.reviewed_by,
                      cl.created_at, cl.reviewed_at,
                      c1.case_number AS case_number_a, c1.title AS title_a,
                      c1.status AS status_a, c1.priority AS priority_a,
                      i1.name AS institution_a, b1.name AS bureau_a,
                      c2.case_number AS case_number_b, c2.title AS title_b,
                      c2.status AS status_b, c2.priority AS priority_b,
                      i2.name AS institution_b, b2.name AS bureau_b,
                      creator.full_name AS created_by_name,
                      reviewer.full_name AS reviewed_by_name"""
            + from_sql
            + " LEFT JOIN users creator ON creator.id = cl.created_by"
            + " LEFT JOIN users reviewer ON reviewer.id = cl.reviewed_by"
            + where_sql
            + " ORDER BY CASE cl.review_status WHEN 'SUGGESTED' THEN 0 WHEN 'CONFIRMED' THEN 1 ELSE 2 END, cl.created_at DESC, cl.id DESC LIMIT %s OFFSET %s",
            tuple(params + [page_size, (page - 1) * page_size]),
        )
        return jsonify({"success": True, "data": {
            "items": _serialize(cursor.fetchall()), "total": total,
            "page": page, "page_size": page_size,
        }})
    except mysql.connector.Error:
        current_app.logger.exception("Unable to list related cases")
        return jsonify({"success": False, "message": "Unable to load related cases."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@coordination_bp.post("/links")
@jwt_required()
def create_related_link():
    role, user_id = _role_user()
    if role not in WRITE_ROLES:
        return jsonify({"success": False, "message": "Your role is read-only for case coordination."}), 403
    data = request.get_json(silent=True) or {}
    try:
        complaint_id = int(data.get("complaint_id"))
        related_id = int(data.get("related_complaint_id"))
        if complaint_id <= 0 or related_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Both complaint IDs must be positive integers."}), 400
    if complaint_id == related_id:
        return jsonify({"success": False, "message": "A case cannot be linked to itself."}), 400
    relationship = str(data.get("relationship", "RELATED")).strip().upper()
    if relationship not in VALID_RELATIONSHIPS:
        return jsonify({"success": False, "message": "relationship must be RELATED or FOLLOW_UP. Use Overlap Detection for duplicate suggestions."}), 400
    explanation = str(data.get("explanation", "")).strip()
    if len(explanation) > 1000:
        return jsonify({"success": False, "message": "Explanation must be 1000 characters or fewer."}), 400

    left_id, right_id = (sorted((complaint_id, related_id)) if relationship == "RELATED" else (complaint_id, related_id))
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if not _has_case_access(cursor, left_id, role, user_id) or not _has_case_access(cursor, right_id, role, user_id):
            return jsonify({"success": False, "message": "One or both cases were not found or are outside your access scope."}), 404

        # RELATED is symmetric and uses canonical ID ordering. FOLLOW_UP is directional.
        if relationship == "RELATED":
            cursor.execute(
                """SELECT id FROM complaint_links
                   WHERE relationship = 'RELATED'
                     AND ((complaint_id = %s AND related_complaint_id = %s)
                       OR (complaint_id = %s AND related_complaint_id = %s))
                   LIMIT 1""",
                (left_id, right_id, right_id, left_id),
            )
        else:
            cursor.execute(
                "SELECT id FROM complaint_links WHERE complaint_id = %s AND related_complaint_id = %s AND relationship = 'FOLLOW_UP' LIMIT 1",
                (left_id, right_id),
            )
        if cursor.fetchone():
            return jsonify({"success": False, "message": "This relationship already exists."}), 409

        cursor.execute(
            """INSERT INTO complaint_links
               (complaint_id, related_complaint_id, relationship, review_status,
                confidence, explanation, created_by)
               VALUES (%s, %s, %s, 'SUGGESTED', NULL, %s, %s)""",
            (left_id, right_id, relationship, explanation or None, user_id),
        )
        link_id = int(cursor.lastrowid)
        detail = f"Related-case link #{link_id} ({relationship}) was suggested between cases #{left_id} and #{right_id}."
        _case_action(cursor, left_id, user_id, "RELATED_CASE_LINK_SUGGESTED", detail)
        _case_action(cursor, right_id, user_id, "RELATED_CASE_LINK_SUGGESTED", detail)
        _audit(cursor, user_id, "RELATED_CASE_LINK_SUGGESTED", "complaint_link", link_id, {
            "complaint_id": left_id, "related_complaint_id": right_id,
            "relationship": relationship, "review_status": "SUGGESTED",
        })
        _notify_assignees(cursor, [left_id, right_id], user_id, "Related case link needs review", detail)
        conn.commit()
        return jsonify({"success": True, "message": "Related-case link suggested for review.", "data": {"id": link_id, "complaint_id": left_id, "related_complaint_id": right_id, "relationship": relationship, "review_status": "SUGGESTED"}}), 201
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Unable to create related-case link")
        return jsonify({"success": False, "message": "Unable to create related-case link."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@coordination_bp.patch("/links/<int:link_id>/review")
@jwt_required()
def review_related_link(link_id):
    role, user_id = _role_user()
    if role not in WRITE_ROLES:
        return jsonify({"success": False, "message": "Your role is read-only for case coordination."}), 403
    data = request.get_json(silent=True) or {}
    decision = str(data.get("review_status", "")).strip().upper()
    if decision not in {"CONFIRMED", "REJECTED"}:
        return jsonify({"success": False, "message": "review_status must be CONFIRMED or REJECTED."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        link = _get_link(cursor, link_id)
        if not link or link["relationship"] == "POTENTIAL_DUPLICATE":
            return jsonify({"success": False, "message": "Related-case link not found. Review duplicate suggestions in Overlap Detection."}), 404
        if not _has_case_access(cursor, int(link["complaint_id"]), role, user_id) or not _has_case_access(cursor, int(link["related_complaint_id"]), role, user_id):
            return jsonify({"success": False, "message": "Related-case link not found or outside your access scope."}), 404
        if link["review_status"] != "SUGGESTED":
            return jsonify({"success": False, "message": "This relationship has already been reviewed."}), 409

        cursor.execute(
            "UPDATE complaint_links SET review_status = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP WHERE id = %s",
            (decision, user_id, link_id),
        )
        action = "RELATED_CASE_LINK_CONFIRMED" if decision == "CONFIRMED" else "RELATED_CASE_LINK_REJECTED"
        comment = f"Related-case link #{link_id} ({link['relationship']}) was {decision.lower()}."
        for case_id in (int(link["complaint_id"]), int(link["related_complaint_id"])):
            _case_action(cursor, case_id, user_id, action, comment)
        _audit(cursor, user_id, action, "complaint_link", link_id, {
            "complaint_id": int(link["complaint_id"]),
            "related_complaint_id": int(link["related_complaint_id"]),
            "relationship": link["relationship"], "review_status": decision,
        })
        _notify_assignees(cursor, [int(link["complaint_id"]), int(link["related_complaint_id"])], user_id, f"Related case link {decision.lower()}", comment)
        conn.commit()
        return jsonify({"success": True, "message": f"Related-case link {decision.lower()}.", "data": {"id": link_id, "review_status": decision}})
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Unable to review related-case link")
        return jsonify({"success": False, "message": "Unable to save review decision."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@coordination_bp.get("/links/<int:link_id>/notes")
@jwt_required()
def list_coordination_notes(link_id):
    role, user_id = _role_user()
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        link = _get_link(cursor, link_id)
        if not link or not _may_access_either(cursor, link, role, user_id):
            return jsonify({"success": False, "message": "Related-case link not found or outside your access scope."}), 404
        prefix = f"[LINK_ID={link_id}] "
        cursor.execute(
            """SELECT ca.id, ca.complaint_id, ca.actor_id,
                      u.full_name AS author_name,
                      SUBSTRING(ca.comment, CHAR_LENGTH(%s) + 1) AS note,
                      ca.created_at
               FROM case_actions ca JOIN users u ON u.id = ca.actor_id
               WHERE LEFT(ca.comment, CHAR_LENGTH(%s)) = %s
                 AND ca.complaint_id IN (%s, %s)
                 AND ca.action_type = 'INTER_BUREAU_NOTE'
               ORDER BY ca.created_at ASC, ca.id ASC""",
            (prefix, prefix, prefix, int(link["complaint_id"]), int(link["related_complaint_id"])),
        )
        return jsonify({"success": True, "data": {"items": _serialize(cursor.fetchall())}})
    except mysql.connector.Error:
        current_app.logger.exception("Unable to list coordination notes")
        return jsonify({"success": False, "message": "Unable to load coordination notes."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@coordination_bp.post("/links/<int:link_id>/notes")
@jwt_required()
def add_coordination_note(link_id):
    role, user_id = _role_user()
    if role not in WRITE_ROLES:
        return jsonify({"success": False, "message": "Your role is read-only for case coordination."}), 403
    data = request.get_json(silent=True) or {}
    note = str(data.get("note", "")).strip()
    if not note:
        return jsonify({"success": False, "message": "Enter a coordination note."}), 400
    if len(note) > 2000:
        return jsonify({"success": False, "message": "Coordination note must be 2000 characters or fewer."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        link = _get_link(cursor, link_id)
        if not link or not _may_access_either(cursor, link, role, user_id):
            return jsonify({"success": False, "message": "Related-case link not found or outside your access scope."}), 404
        left_id, right_id = int(link["complaint_id"]), int(link["related_complaint_id"])
        if _has_case_access(cursor, left_id, role, user_id):
            note_case_id = left_id
        elif _has_case_access(cursor, right_id, role, user_id):
            note_case_id = right_id
        else:
            return jsonify({"success": False, "message": "You cannot add a note to this relationship."}), 403

        prefix = f"[LINK_ID={link_id}] "
        note_action_id = _case_action(cursor, note_case_id, user_id, "INTER_BUREAU_NOTE", prefix + note)
        _audit(cursor, user_id, "INTER_BUREAU_NOTE_ADDED", "complaint_link", link_id, {
            "complaint_id": left_id, "related_complaint_id": right_id,
            "note_length": len(note),
        })
        _notify_assignees(cursor, [left_id, right_id], user_id, "New inter-Bureau coordination note", f"A coordination note was added for related case link #{link_id}.")
        conn.commit()
        cursor.execute(
            "SELECT ca.id, ca.complaint_id, ca.actor_id, u.full_name AS author_name, %s AS note, ca.created_at FROM case_actions ca JOIN users u ON u.id = ca.actor_id WHERE ca.id = %s",
            (note, note_action_id),
        )
        created = cursor.fetchone()
        return jsonify({"success": True, "message": "Coordination note added.", "data": _serialize([created])[0] if created else {"note": note}}), 201
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Unable to add coordination note")
        return jsonify({"success": False, "message": "Unable to add coordination note."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
