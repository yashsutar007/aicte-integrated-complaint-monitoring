# Destination: backend/routes/overlap.py
"""Explainable, heuristic overlap detection for complaint records.

This module proposes potential duplicate/related cases. It does not determine
that two complaints are duplicates automatically; a permitted user must review
and confirm or reject each suggestion.
"""

from difflib import SequenceMatcher
from itertools import combinations
import json
import re
from datetime import date, datetime
from decimal import Decimal

import mysql.connector
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from db import get_db_connection

overlap_bp = Blueprint("overlap", __name__, url_prefix="/api/overlap")
ADMIN_ROLES = {"ADMIN", "SUPER_ADMIN"}
VALID_REVIEW_STATUSES = {"SUGGESTED", "CONFIRMED", "REJECTED", "ALL"}
MAX_SCAN_RECORDS = 300
DEFAULT_CONFIDENCE = 50


def _normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _similarity(left, right):
    """Blend character-order similarity and token overlap into a 0..1 value."""
    a = _normalize(left)
    b = _normalize(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    token_a = set(a.split())
    token_b = set(b.split())
    union = token_a | token_b
    token_score = len(token_a & token_b) / len(union) if union else 0.0
    sequence_score = SequenceMatcher(None, a, b, autojunk=False).ratio()
    return round(0.55 * sequence_score + 0.45 * token_score, 4)


def _score_pair(left, right):
    title_score = _similarity(left.get("title"), right.get("title"))
    description_score = _similarity(left.get("description"), right.get("description"))
    same_category = bool(
        _normalize(left.get("category"))
        and _normalize(left.get("category")) == _normalize(right.get("category"))
    )
    same_institution = left.get("institution_id") == right.get("institution_id")

    score = (
        0.42 * title_score
        + 0.28 * description_score
        + 0.18 * float(same_category)
        + 0.12 * float(same_institution)
    )
    score = round(min(max(score, 0.0), 1.0), 4)

    evidence = []
    if same_institution:
        evidence.append("Both complaints concern the same institution")
    if same_category:
        evidence.append("Complaint category matches")
    if title_score >= 0.30:
        evidence.append(f"Title similarity: {round(title_score * 100)}%")
    if description_score >= 0.30:
        evidence.append(f"Description similarity: {round(description_score * 100)}%")
    if not evidence:
        evidence.append("The score comes from combined title, description, category and institution signals")

    # The matching score is a prioritization heuristic, not a calibrated probability.
    eligible = score >= 0.50 and (
        title_score >= 0.30
        or description_score >= 0.30
        or (same_institution and same_category and max(title_score, description_score) >= 0.22)
    )
    return {
        "score": score,
        "confidence": round(score * 100, 2),
        "title_similarity": title_score,
        "description_similarity": description_score,
        "same_category": same_category,
        "same_institution": same_institution,
        "explanation": "; ".join(evidence),
        "eligible": eligible,
    }


def _serialize_rows(rows):
    output = []
    for row in rows:
        item = dict(row)
        for key, value in item.items():
            if isinstance(value, (datetime, date)):
                item[key] = value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
            elif isinstance(value, Decimal):
                item[key] = float(value)
        output.append(item)
    return output


def _case_access_sql(alias):
    """Three bound user id placeholders; only own/assigned/team cases are visible."""
    return f"""(
        {alias}.created_by = %s
        OR EXISTS (
            SELECT 1 FROM complaint_assignments own_assignment
            WHERE own_assignment.complaint_id = {alias}.id
              AND own_assignment.released_at IS NULL
              AND own_assignment.assigned_to = %s
        )
        OR EXISTS (
            SELECT 1
            FROM complaint_assignments team_assignment
            JOIN user_bureaus membership ON membership.bureau_id = team_assignment.bureau_id
            WHERE team_assignment.complaint_id = {alias}.id
              AND team_assignment.released_at IS NULL
              AND membership.user_id = %s
        )
    )"""


def _accessible_cases(cursor, role, user_id):
    query = """SELECT c.id, c.case_number, c.institution_id, i.name AS institution_name,
                      c.title, c.description, c.category, c.priority, c.status,
                      c.created_by, c.created_at
               FROM complaints c
               JOIN institutions i ON i.id = c.institution_id"""
    params = []
    if role not in ADMIN_ROLES:
        query += " WHERE " + _case_access_sql("c")
        params.extend([user_id, user_id, user_id])
    query += " ORDER BY c.created_at DESC, c.id DESC LIMIT %s"
    params.append(MAX_SCAN_RECORDS)
    cursor.execute(query, tuple(params))
    return cursor.fetchall()


def _find_pair_link(cursor, left_id, right_id):
    cursor.execute(
        """SELECT id, review_status FROM complaint_links
           WHERE relationship = 'POTENTIAL_DUPLICATE'
             AND ((complaint_id = %s AND related_complaint_id = %s)
               OR (complaint_id = %s AND related_complaint_id = %s))
           LIMIT 1""",
        (left_id, right_id, right_id, left_id),
    )
    return cursor.fetchone()


@overlap_bp.get("/suggestions")
@jwt_required()
def list_suggestions():
    review_status = request.args.get("review_status", "SUGGESTED").strip().upper()
    if review_status not in VALID_REVIEW_STATUSES:
        return jsonify({"success": False, "message": "Invalid review_status filter."}), 400
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 50, type=int), 1), 100)
    role = str(get_jwt().get("role", "CASE_OFFICER")).upper()
    user_id = int(get_jwt_identity())

    conditions = ["cl.relationship = 'POTENTIAL_DUPLICATE'"]
    params = []
    if review_status != "ALL":
        conditions.append("cl.review_status = %s")
        params.append(review_status)
    if role not in ADMIN_ROLES:
        conditions.append(f"EXISTS (SELECT 1 FROM complaints scope_left WHERE scope_left.id = cl.complaint_id AND {_case_access_sql('scope_left')})")
        conditions.append(f"EXISTS (SELECT 1 FROM complaints scope_right WHERE scope_right.id = cl.related_complaint_id AND {_case_access_sql('scope_right')})")
        params.extend([user_id] * 6)

    where_sql = " WHERE " + " AND ".join(conditions)
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM complaint_links cl" + where_sql, tuple(params))
        total = int((cursor.fetchone() or {}).get("total", 0))
        cursor.execute(
            """SELECT cl.id, cl.complaint_id, cl.related_complaint_id, cl.relationship,
                      cl.review_status, cl.confidence, cl.explanation, cl.created_at,
                      c1.case_number AS case_number_a, c1.title AS title_a,
                      c1.priority AS priority_a, c1.status AS status_a,
                      i1.name AS institution_a,
                      c2.case_number AS case_number_b, c2.title AS title_b,
                      c2.priority AS priority_b, c2.status AS status_b,
                      i2.name AS institution_b
               FROM complaint_links cl
               JOIN complaints c1 ON c1.id = cl.complaint_id
               JOIN institutions i1 ON i1.id = c1.institution_id
               JOIN complaints c2 ON c2.id = cl.related_complaint_id
               JOIN institutions i2 ON i2.id = c2.institution_id"""
            + where_sql + " ORDER BY cl.confidence DESC, cl.created_at DESC, cl.id DESC LIMIT %s OFFSET %s",
            tuple(params + [page_size, (page - 1) * page_size]),
        )
        items = _serialize_rows(cursor.fetchall())
        return jsonify({"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}})
    except mysql.connector.Error:
        current_app.logger.exception("Overlap suggestions query failed")
        return jsonify({"success": False, "message": "Unable to load overlap suggestions."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@overlap_bp.post("/detect")
@jwt_required()
def detect_overlaps():
    data = request.get_json(silent=True) or {}
    try:
        min_confidence = float(data.get("min_confidence", DEFAULT_CONFIDENCE))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "min_confidence must be a number between 30 and 90."}), 400
    if not 30 <= min_confidence <= 90:
        return jsonify({"success": False, "message": "min_confidence must be between 30 and 90."}), 400

    target_id = data.get("complaint_id")
    if target_id not in (None, ""):
        try:
            target_id = int(target_id)
            if target_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "complaint_id must be a positive integer."}), 400
    else:
        target_id = None

    role = str(get_jwt().get("role", "CASE_OFFICER")).upper()
    user_id = int(get_jwt_identity())
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        candidates = _accessible_cases(cursor, role, user_id)
        by_id = {int(row["id"]): row for row in candidates}

        # Add an older target case if it was not in the newest scan window, while applying access scope.
        if target_id is not None and target_id not in by_id:
            query = """SELECT c.id, c.case_number, c.institution_id, i.name AS institution_name,
                              c.title, c.description, c.category, c.priority, c.status,
                              c.created_by, c.created_at
                       FROM complaints c JOIN institutions i ON i.id = c.institution_id
                       WHERE c.id = %s"""
            params = [target_id]
            if role not in ADMIN_ROLES:
                query += " AND " + _case_access_sql("c")
                params.extend([user_id, user_id, user_id])
            cursor.execute(query, tuple(params))
            target = cursor.fetchone()
            if target:
                by_id[target_id] = target
                candidates.append(target)
            else:
                return jsonify({"success": False, "message": "Complaint not found or outside your case access scope."}), 404

        if target_id is not None:
            if target_id not in by_id:
                return jsonify({"success": False, "message": "Complaint not found or outside your case access scope."}), 404
            pairs = [(by_id[target_id], case) for case in candidates if int(case["id"]) != target_id]
        else:
            pairs = list(combinations(candidates, 2))

        new_count = 0
        updated_count = 0
        reviewed_skipped = 0
        considered = 0
        for first, second in pairs:
            left_id, right_id = int(first["id"]), int(second["id"])
            if left_id == right_id:
                continue
            score = _score_pair(first, second)
            if score["confidence"] < min_confidence or not score["eligible"]:
                continue
            considered += 1
            left, right = (first, second) if left_id < right_id else (second, first)
            canonical_left_id, canonical_right_id = min(left_id, right_id), max(left_id, right_id)
            existing = _find_pair_link(cursor, canonical_left_id, canonical_right_id)
            if existing and existing["review_status"] in {"CONFIRMED", "REJECTED"}:
                reviewed_skipped += 1
                continue
            if existing:
                cursor.execute(
                    "UPDATE complaint_links SET confidence = %s, explanation = %s WHERE id = %s",
                    (score["confidence"], score["explanation"], existing["id"]),
                )
                updated_count += 1
            else:
                cursor.execute(
                    """INSERT INTO complaint_links
                       (complaint_id, related_complaint_id, relationship, review_status,
                        confidence, explanation, created_by)
                       VALUES (%s, %s, 'POTENTIAL_DUPLICATE', 'SUGGESTED', %s, %s, %s)""",
                    (canonical_left_id, canonical_right_id, score["confidence"], score["explanation"], user_id),
                )
                new_count += 1

        cursor.execute(
            """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
               VALUES (%s, 'OVERLAP_SCAN_COMPLETED', 'overlap_scan', %s, %s)""",
            (user_id, str(target_id) if target_id else "bulk", json.dumps({
                "min_confidence": min_confidence,
                "records_scanned": len(candidates),
                "pairs_compared": len(pairs),
                "qualifying_pairs": considered,
                "new_suggestions": new_count,
                "updated_suggestions": updated_count,
                "reviewed_pairs_skipped": reviewed_skipped,
            })),
        )
        conn.commit()
        return jsonify({
            "success": True,
            "message": "Overlap scan completed. Suggestions require human review.",
            "data": {
                "records_scanned": len(candidates),
                "pairs_compared": len(pairs),
                "qualifying_pairs": considered,
                "new_suggestions": new_count,
                "updated_suggestions": updated_count,
                "reviewed_pairs_skipped": reviewed_skipped,
                "min_confidence": min_confidence,
                "scope": "GLOBAL" if role in ADMIN_ROLES else "ACCESSIBLE_CASES_ONLY",
            },
        })
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Overlap scan database error")
        return jsonify({"success": False, "message": "Unable to run overlap detection."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@overlap_bp.patch("/suggestions/<int:suggestion_id>/review")
@jwt_required()
def review_suggestion(suggestion_id):
    data = request.get_json(silent=True) or {}
    decision = str(data.get("review_status", "")).strip().upper()
    if decision not in {"CONFIRMED", "REJECTED"}:
        return jsonify({"success": False, "message": "review_status must be CONFIRMED or REJECTED."}), 400

    role = str(get_jwt().get("role", "CASE_OFFICER")).upper()
    user_id = int(get_jwt_identity())
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """SELECT cl.id, cl.complaint_id, cl.related_complaint_id, cl.review_status,
                          cl.confidence, cl.explanation,
                          c1.case_number AS case_number_a, c2.case_number AS case_number_b
                   FROM complaint_links cl
                   JOIN complaints c1 ON c1.id = cl.complaint_id
                   JOIN complaints c2 ON c2.id = cl.related_complaint_id
                   WHERE cl.id = %s AND cl.relationship = 'POTENTIAL_DUPLICATE'"""
        params = [suggestion_id]
        if role not in ADMIN_ROLES:
            query += f" AND EXISTS (SELECT 1 FROM complaints scope_left WHERE scope_left.id = cl.complaint_id AND {_case_access_sql('scope_left')})"
            query += f" AND EXISTS (SELECT 1 FROM complaints scope_right WHERE scope_right.id = cl.related_complaint_id AND {_case_access_sql('scope_right')})"
            params.extend([user_id] * 6)
        cursor.execute(query, tuple(params))
        link = cursor.fetchone()
        if not link:
            return jsonify({"success": False, "message": "Overlap suggestion not found or outside your access scope."}), 404
        if link["review_status"] != "SUGGESTED":
            return jsonify({"success": False, "message": "This suggestion has already been reviewed."}), 409

        cursor.execute(
            "UPDATE complaint_links SET review_status = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP WHERE id = %s",
            (decision, user_id, suggestion_id),
        )
        action = "OVERLAP_REVIEW_CONFIRMED" if decision == "CONFIRMED" else "OVERLAP_REVIEW_REJECTED"
        comment = f"Potential duplicate suggestion #{suggestion_id} was {decision.lower()} (heuristic score {float(link['confidence'] or 0):.2f}/100)."
        for case_id in (int(link["complaint_id"]), int(link["related_complaint_id"])):
            cursor.execute(
                """INSERT INTO case_actions
                   (complaint_id, actor_id, action_type, from_status, to_status, comment)
                   VALUES (%s, %s, %s, NULL, NULL, %s)""",
                (case_id, user_id, action, comment),
            )
        cursor.execute(
            """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
               VALUES (%s, %s, 'complaint_link', %s, %s)""",
            (user_id, action, str(suggestion_id), json.dumps({
                "complaint_id": int(link["complaint_id"]),
                "related_complaint_id": int(link["related_complaint_id"]),
                "review_status": decision,
                "confidence": float(link["confidence"] or 0),
            })),
        )
        conn.commit()
        return jsonify({
            "success": True,
            "message": f"Suggestion {decision.lower()}.",
            "data": {"id": suggestion_id, "review_status": decision},
        })
    except mysql.connector.Error:
        if conn:
            conn.rollback()
        current_app.logger.exception("Overlap suggestion review database error")
        return jsonify({"success": False, "message": "Unable to save suggestion review."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
