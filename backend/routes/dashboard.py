# Destination: backend/routes/dashboard.py

from datetime import datetime

import mysql.connector
from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from db import get_db_connection


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")
ADMIN_ROLES = {"ADMIN", "SUPER_ADMIN"}
DONE_STATUSES = {"RESOLVED", "CLOSED"}


def _case_scope():
    """Return SQL and parameters limiting non-admins to cases they own or are assigned."""
    role = str(get_jwt().get("role", "CASE_OFFICER")).upper()
    if role in ADMIN_ROLES:
        return "", ()

    user_id = int(get_jwt_identity())
    return (
        """
        AND (
            c.created_by = %s
            OR EXISTS (
                SELECT 1 FROM complaint_assignments mine
                WHERE mine.complaint_id = c.id
                  AND mine.released_at IS NULL
                  AND mine.assigned_to = %s
            )
            OR EXISTS (
                SELECT 1
                FROM complaint_assignments team_assignment
                JOIN user_bureaus membership
                  ON membership.bureau_id = team_assignment.bureau_id
                WHERE team_assignment.complaint_id = c.id
                  AND team_assignment.released_at IS NULL
                  AND membership.user_id = %s
            )
        )
        """,
        (user_id, user_id, user_id),
    )


def _isoformat_rows(rows):
    result = []
    for row in rows:
        item = dict(row)
        for key, value in item.items():
            if isinstance(value, datetime):
                item[key] = value.isoformat(sep=" ", timespec="seconds")
        result.append(item)
    return result


@dashboard_bp.get("/summary")
@jwt_required()
def dashboard_summary():
    scope_sql, scope_params = _case_scope()
    role = str(get_jwt().get("role", "CASE_OFFICER")).upper()
    user_id = int(get_jwt_identity())
    conn = cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            /* dashboard:metrics */
            SELECT
                (SELECT COUNT(*) FROM institutions) AS total_institutions,
                (SELECT COUNT(*) FROM institutions WHERE status = 'ACTIVE') AS active_institutions,
                COUNT(*) AS total_cases,
                COALESCE(SUM(CASE WHEN c.status NOT IN ('RESOLVED', 'CLOSED') THEN 1 ELSE 0 END), 0) AS open_cases,
                COALESCE(SUM(CASE WHEN c.status IN ('RESOLVED', 'CLOSED') THEN 1 ELSE 0 END), 0) AS resolved_cases,
                COALESCE(SUM(CASE WHEN c.priority = 'CRITICAL' AND c.status NOT IN ('RESOLVED', 'CLOSED') THEN 1 ELSE 0 END), 0) AS critical_open_cases,
                COALESCE(SUM(CASE WHEN c.sla_due_at < CURRENT_TIMESTAMP AND c.status NOT IN ('RESOLVED', 'CLOSED') THEN 1 ELSE 0 END), 0) AS overdue_cases,
                COALESCE(SUM(CASE WHEN c.sla_due_at >= CURRENT_TIMESTAMP AND c.sla_due_at <= DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 24 HOUR) AND c.status NOT IN ('RESOLVED', 'CLOSED') THEN 1 ELSE 0 END), 0) AS due_within_24h
            FROM complaints c
            WHERE 1 = 1
            """ + scope_sql,
            scope_params,
        )
        metrics = cursor.fetchone() or {}

        cursor.execute(
            """
            /* dashboard:status */
            SELECT c.status AS label, COUNT(*) AS count
            FROM complaints c
            WHERE 1 = 1
            """ + scope_sql + " GROUP BY c.status ORDER BY count DESC, c.status ASC",
            scope_params,
        )
        status_breakdown = _isoformat_rows(cursor.fetchall())

        cursor.execute(
            """
            /* dashboard:priority */
            SELECT c.priority AS label, COUNT(*) AS count
            FROM complaints c
            WHERE 1 = 1
            """ + scope_sql + " GROUP BY c.priority ORDER BY FIELD(c.priority, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW')",
            scope_params,
        )
        priority_breakdown = _isoformat_rows(cursor.fetchall())

        bureau_filter = ""
        bureau_params = ()
        if role not in ADMIN_ROLES:
            bureau_filter = "WHERE EXISTS (SELECT 1 FROM user_bureaus ub WHERE ub.bureau_id = b.id AND ub.user_id = %s)"
            bureau_params = (user_id,)

        cursor.execute(
            """
            /* dashboard:bureaus */
            SELECT b.id, b.name, b.code,
                   COUNT(DISTINCT CASE WHEN c.id IS NOT NULL THEN c.id END) AS active_cases
            FROM bureaus b
            LEFT JOIN complaint_assignments ca
              ON ca.bureau_id = b.id AND ca.released_at IS NULL
            LEFT JOIN complaints c
              ON c.id = ca.complaint_id AND c.status NOT IN ('RESOLVED', 'CLOSED')
            """ + bureau_filter + " GROUP BY b.id, b.name, b.code ORDER BY active_cases DESC, b.name ASC LIMIT 8",
            bureau_params,
        )
        bureau_workload = _isoformat_rows(cursor.fetchall())

        cursor.execute(
            """
            /* dashboard:recent_cases */
            SELECT c.id, c.case_number, c.title, c.priority, c.status,
                   c.sla_due_at, c.created_at, i.name AS institution_name,
                   b.name AS bureau_name
            FROM complaints c
            JOIN institutions i ON i.id = c.institution_id
            LEFT JOIN bureaus b ON b.id = c.current_bureau_id
            WHERE 1 = 1
            """ + scope_sql + " ORDER BY c.created_at DESC, c.id DESC LIMIT 8",
            scope_params,
        )
        recent_cases = _isoformat_rows(cursor.fetchall())

        cursor.execute(
            """
            /* dashboard:recent_activity */
            SELECT a.id, a.complaint_id, c.case_number, a.action_type,
                   a.from_status, a.to_status, a.comment, a.created_at,
                   u.full_name AS actor_name
            FROM case_actions a
            JOIN complaints c ON c.id = a.complaint_id
            JOIN users u ON u.id = a.actor_id
            WHERE 1 = 1
            """ + scope_sql.replace("c.created_by", "c.created_by") + " ORDER BY a.created_at DESC, a.id DESC LIMIT 8",
            scope_params,
        )
        recent_activity = _isoformat_rows(cursor.fetchall())

        response_metrics = {
            key: int(value or 0)
            for key, value in metrics.items()
        }
        return jsonify({
            "success": True,
            "data": {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "role_scope": "GLOBAL" if role in ADMIN_ROLES else "ASSIGNED_CASES_AND_OWN_CASES",
                "metrics": response_metrics,
                "status_breakdown": status_breakdown,
                "priority_breakdown": priority_breakdown,
                "bureau_workload": bureau_workload,
                "recent_cases": recent_cases,
                "recent_activity": recent_activity,
            },
        })
    except mysql.connector.Error:
        current_app.logger.exception("Dashboard summary database error")
        return jsonify({
            "success": False,
            "message": "Unable to load monitoring data. Check the database connection.",
        }), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
