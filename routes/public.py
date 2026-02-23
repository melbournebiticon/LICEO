from flask import Blueprint, render_template, jsonify, session
from db import get_db_connection
import psycopg2.extras

public_bp = Blueprint("public", __name__)

def query_all(sql, params=None):
    """Helper: return list of rows (RealDictCursor)"""
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql, params or ())
        return cur.fetchall()
    finally:
        cur.close()
        db.close()

def query_one(sql, params=None):
    """Helper: return single row (RealDictCursor)"""
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql, params or ())
        return cur.fetchone()
    finally:
        cur.close()
        db.close()


# =========================
# PUBLIC PAGES
# =========================
@public_bp.route("/")
def homepage():
    announcements = query_all("""
        SELECT title, message, created_at
        FROM announcements
        WHERE is_active = TRUE
        ORDER BY created_at DESC
    """)

    branches = query_all("""
        SELECT branch_id, branch_name, location
        FROM branches
        WHERE is_active = TRUE
        ORDER BY branch_name ASC
    """)

    return render_template(
        "homepage.html",
        announcements=announcements,
        branches=branches
    )


@public_bp.route("/branch/<int:branch_id>")
def branch_page(branch_id):
    branch = query_one("""
        SELECT branch_id, branch_name, location
        FROM branches
        WHERE branch_id = %s AND is_active = TRUE
    """, (branch_id,))

    if not branch:
        return "Branch not found", 404

    return render_template("branch_page.html", branch=branch)


# =========================
# PUBLIC API (Chatbot FAQs)
# =========================
@public_bp.route("/api/faqs")
def api_faqs():
    role = session.get("role")
    branch_id = session.get("branch_id")

    db = get_db_connection()
    cur = db.cursor()
    try:
        # Logged in users: branch FAQs ONLY
        if role and branch_id:
            cur.execute("""
                SELECT question, answer
                FROM chatbot_faqs
                WHERE branch_id = %s
                ORDER BY id ASC
            """, (branch_id,))
        else:
            # Public (not logged in): general FAQs ONLY
            cur.execute("""
                SELECT question, answer
                FROM chatbot_faqs
                WHERE branch_id IS NULL
                ORDER BY id ASC
            """)

        rows = cur.fetchall() or []
        return jsonify([{"question": r[0], "answer": r[1]} for r in rows])

    except Exception:
        # wag app.logger dito kasi blueprint file; safe return empty
        return jsonify([]), 200
    finally:
        cur.close()
        db.close()
