# Save as: backend/routes/institutions.py

import mysql.connector
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from db import get_db_connection

institutions_bp = Blueprint("institutions", __name__, url_prefix="/api/institutions")
VALID_STATUSES = {"ACTIVE", "INACTIVE", "UNDER_REVIEW"}


@institutions_bp.get("")
@jwt_required()
def list_institutions():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip().upper()
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 50, type=int), 1), 100)

    if status and status not in VALID_STATUSES:
        return jsonify({"success": False, "message": "Invalid institution status."}), 400

    conditions = []
    params = []
    if search:
        like = f"%{search}%"
        conditions.append(
            "(name LIKE %s OR institution_code LIKE %s OR district LIKE %s OR state LIKE %s)"
        )
        params.extend([like, like, like, like])
    if status:
        conditions.append("status = %s")
        params.append(status)

    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * page_size
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT COUNT(*) AS total FROM institutions{where_sql}", tuple(params))
        total = cursor.fetchone()["total"]
        cursor.execute(
            """SELECT id, institution_code, name, institution_type, state,
                      district, address, official_email, phone, status,
                      created_at, updated_at
               FROM institutions""" + where_sql +
            " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            tuple(params + [page_size, offset]),
        )
        items = cursor.fetchall()
        return jsonify({
            "success": True,
            "data": {"items": items, "total": total, "page": page, "page_size": page_size},
        })
    except mysql.connector.Error:
        current_app.logger.exception("Institution list database error")
        return jsonify({"success": False, "message": "Unable to load institutions."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@institutions_bp.post("")
@jwt_required()
def create_institution():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"success": False, "message": "Institution name is required."}), 400
    if len(name) > 255:
        return jsonify({"success": False, "message": "Institution name must be 255 characters or fewer."}), 400

    institution_code = str(data.get("institution_code", "")).strip() or None
    institution_type = str(data.get("institution_type", "")).strip() or None
    state = str(data.get("state", "")).strip() or None
    district = str(data.get("district", "")).strip() or None
    address = str(data.get("address", "")).strip() or None
    official_email = str(data.get("official_email", "")).strip().lower() or None
    phone = str(data.get("phone", "")).strip() or None
    status = str(data.get("status", "ACTIVE")).strip().upper()

    if status not in VALID_STATUSES:
        return jsonify({"success": False, "message": "Invalid institution status."}), 400
    if institution_code and len(institution_code) > 60:
        return jsonify({"success": False, "message": "Institution code must be 60 characters or fewer."}), 400
    if official_email and (len(official_email) > 255 or "@" not in official_email):
        return jsonify({"success": False, "message": "Enter a valid official email address."}), 400
    if phone and len(phone) > 25:
        return jsonify({"success": False, "message": "Phone must be 25 characters or fewer."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """INSERT INTO institutions
               (institution_code, name, institution_type, state, district, address,
                official_email, phone, status, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (institution_code, name, institution_type, state, district, address,
             official_email, phone, status, int(get_jwt_identity())),
        )
        institution_id = cursor.lastrowid
        conn.commit()
        cursor.execute(
            """SELECT id, institution_code, name, institution_type, state, district,
                      address, official_email, phone, status, created_at, updated_at
               FROM institutions WHERE id = %s""",
            (institution_id,),
        )
        institution = cursor.fetchone()
        return jsonify({"success": True, "message": "Institution created.", "data": {"institution": institution}}), 201
    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": "That institution code is already in use."}), 409
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Institution creation database error")
        return jsonify({"success": False, "message": "Unable to create institution."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@institutions_bp.get("/<int:institution_id>")
@jwt_required()
def get_institution(institution_id):
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT id, institution_code, name, institution_type, state, district,
                      address, official_email, phone, status, created_at, updated_at
               FROM institutions WHERE id = %s""",
            (institution_id,),
        )
        institution = cursor.fetchone()
        if not institution:
            return jsonify({"success": False, "message": "Institution not found."}), 404
        return jsonify({"success": True, "data": {"institution": institution}})
    except mysql.connector.Error:
        current_app.logger.exception("Institution detail database error")
        return jsonify({"success": False, "message": "Unable to load institution."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@institutions_bp.put("/<int:institution_id>")
@jwt_required()
def update_institution(institution_id):
    data = request.get_json(silent=True) or {}
    allowed_fields = {
        "institution_code", "name", "institution_type", "state", "district",
        "address", "official_email", "phone", "status",
    }
    if not any(field in data for field in allowed_fields):
        return jsonify({"success": False, "message": "Provide at least one field to update."}), 400

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT id, institution_code, name, institution_type, state, district,
                      address, official_email, phone, status
               FROM institutions WHERE id = %s""",
            (institution_id,),
        )
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"success": False, "message": "Institution not found."}), 404

        merged = {field: existing[field] for field in allowed_fields}
        merged.update({field: value for field, value in data.items() if field in allowed_fields})
        merged["name"] = str(merged["name"] or "").strip()
        if not merged["name"]:
            return jsonify({"success": False, "message": "Institution name cannot be empty."}), 400
        merged["status"] = str(merged["status"] or "ACTIVE").strip().upper()
        if merged["status"] not in VALID_STATUSES:
            return jsonify({"success": False, "message": "Invalid institution status."}), 400
        if merged["institution_code"] is not None:
            merged["institution_code"] = str(merged["institution_code"]).strip() or None
        if merged["official_email"] is not None:
            merged["official_email"] = str(merged["official_email"]).strip().lower() or None
            if merged["official_email"] and "@" not in merged["official_email"]:
                return jsonify({"success": False, "message": "Enter a valid official email address."}), 400

        for field in ("institution_type", "state", "district", "address", "phone"):
            if merged[field] is not None:
                merged[field] = str(merged[field]).strip() or None

        cursor.execute(
            """UPDATE institutions SET institution_code=%s, name=%s, institution_type=%s,
               state=%s, district=%s, address=%s, official_email=%s, phone=%s, status=%s
               WHERE id=%s""",
            (merged["institution_code"], merged["name"], merged["institution_type"],
             merged["state"], merged["district"], merged["address"],
             merged["official_email"], merged["phone"], merged["status"], institution_id),
        )
        conn.commit()
        cursor.execute(
            """SELECT id, institution_code, name, institution_type, state, district,
                      address, official_email, phone, status, created_at, updated_at
               FROM institutions WHERE id = %s""",
            (institution_id,),
        )
        institution = cursor.fetchone()
        return jsonify({"success": True, "message": "Institution updated.", "data": {"institution": institution}})
    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": "That institution code is already in use."}), 409
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Institution update database error")
        return jsonify({"success": False, "message": "Unable to update institution."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
