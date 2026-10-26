
import re

import bcrypt
import mysql.connector
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
)

from db import get_db_connection

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def public_user(row):
    return {
        "id": row["id"],
        "name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
    }


def token_response(row, status_code=200):
    user = public_user(row)
    token = create_access_token(
        identity=str(user["id"]),
        additional_claims={"role": user["role"], "email": user["email"]},
    )
    return jsonify({
        "success": True,
        "message": "Authentication successful",
        "data": {"user": user, "access_token": token},
    }), status_code


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({
            "success": False,
            "message": "Name, email and password are required.",
        }), 400

    if len(name) > 150:
        return jsonify({
            "success": False,
            "message": "Name must be 150 characters or fewer.",
        }), 400

    if len(email) > 255 or not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", email
    ):
        return jsonify({
            "success": False,
            "message": "Enter a valid email address.",
        }), 400

    if not isinstance(password, str) or len(password) < 8:
        return jsonify({
            "success": False,
            "message": "Password must contain at least 8 characters.",
        }), 400

    if len(password.encode("utf-8")) > 72:
        return jsonify({
            "success": False,
            "message": "Password is too long. Use at most 72 UTF-8 bytes.",
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({
                "success": False,
                "message": "An account with this email already exists.",
            }), 409

        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        # Public registration never allows users to choose an admin role.
        cursor.execute(
            """
            INSERT INTO users (full_name, email, password_hash, role)
            VALUES (%s, %s, %s, 'CASE_OFFICER')
            """,
            (name, email, password_hash),
        )
        user_id = cursor.lastrowid
        conn.commit()

        cursor.execute(
            """
            SELECT id, full_name, email, role, is_active
            FROM users WHERE id = %s
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return token_response(row, 201)

    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({
            "success": False,
            "message": "An account with this email already exists.",
        }), 409

    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Registration database error")
        return jsonify({
            "success": False,
            "message": "Database unavailable. Check the backend configuration.",
        }), 503

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not email or not isinstance(password, str) or not password:
        return jsonify({
            "success": False,
            "message": "Email and password are required.",
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, full_name, email, password_hash, role, is_active
            FROM users WHERE email = %s
            """,
            (email,),
        )
        row = cursor.fetchone()

        # Use the same error for unknown emails and incorrect passwords.
        if (
            not row
            or not row["is_active"]
            or not bcrypt.checkpw(
                password.encode("utf-8"),
                row["password_hash"].encode("utf-8"),
            )
        ):
            return jsonify({
                "success": False,
                "message": "Invalid email or password.",
            }), 401

        return token_response(row)

    except mysql.connector.Error:
        current_app.logger.exception("Login database error")
        return jsonify({
            "success": False,
            "message": "Database unavailable. Check the backend configuration.",
        }), 503

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@auth_bp.get("/me")
@jwt_required()
def get_current_user():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, full_name, email, role, is_active
            FROM users WHERE id = %s
            """,
            (int(get_jwt_identity()),),
        )
        row = cursor.fetchone()

        if not row or not row["is_active"]:
            return jsonify({
                "success": False,
                "message": "User account not found or inactive.",
            }), 401

        return jsonify({"success": True, "data": {"user": public_user(row)}})

    except mysql.connector.Error:
        current_app.logger.exception("User lookup database error")
        return jsonify({
            "success": False,
            "message": "Database unavailable. Check the backend configuration.",
        }), 503

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
