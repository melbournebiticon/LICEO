import re as _re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from db import get_db_connection
import psycopg2.extras

teacher_bp = Blueprint("teacher", __name__)

GRADE_LEVELS = [
    "Kinder", "Grade 1", "Grade 2", "Grade 3",
    "Grade 4", "Grade 5", "Grade 6",
    "Grade 7", "Grade 8", "Grade 9", "Grade 10",
    "Grade 11", "Grade 12",
]


# ── helpers ──────────────────────────────────────────────
def _require_teacher():
    return session.get("role") == "teacher"


def _normalize_grade(grade_str):
    """Accept both '7' and 'Grade 7' — returns (grade_full, grade_short)."""
    m = _re.match(r'^Grade\s+(\d+)$', grade_str, _re.IGNORECASE)
    num = m.group(1) if m else None
    return grade_str, (num or grade_str)


# ── DEBUG ─────────────────────────────────────────────────
@teacher_bp.route("/teacher/debug")
def teacher_debug():
    if not _require_teacher():
        return redirect("/")
    branch_id = session.get("branch_id")
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT enrollment_id, student_name, grade_level, status, branch_id
            FROM enrollments
            WHERE branch_id = %s
            ORDER BY grade_level, student_name
        """, (branch_id,))
        rows = cur.fetchall()
        return jsonify({
            "session_branch_id": branch_id,
            "count": len(rows),
            "enrollments": [dict(r) for r in rows]
        })
    finally:
        cur.close()
        db.close()


# ── Dashboard ─────────────────────────────────────────────
@teacher_bp.route("/teacher")
def teacher_dashboard():
    if not _require_teacher():
        return redirect("/")

    user_id   = session.get("user_id")
    branch_id = session.get("branch_id")

    db = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("SELECT grade_level FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        teacher_grade = (row[0] or "").strip() if row else ""
    finally:
        cur.close()
        db.close()

    selected_grade = (request.args.get("grade") or teacher_grade or "").strip()

    students = []
    announcements = []
    stats = {"total": 0, "cleared": 0, "pending_bill": 0,
             "reserved": 0, "claimed": 0, "no_reservation": 0}

    if selected_grade:
        grade_full, grade_short = _normalize_grade(selected_grade)

        db  = get_db_connection()
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            # ── Students ──
            cur.execute("""
                SELECT
                    e.enrollment_id,
                    e.student_name,
                    e.grade_level,
                    e.status            AS enrollment_status,

                    COALESCE((
                        SELECT CASE
                            WHEN SUM(b.total_amount - COALESCE(b.amount_paid,0)) <= 0
                            THEN 'CLEARED' ELSE 'PENDING'
                        END
                        FROM billing b
                        WHERE b.enrollment_id = e.enrollment_id
                    ), 'NO_BILL') AS billing_status,

                    COALESCE((
                        SELECT UPPER(r.status)
                        FROM reservations r
                        WHERE r.enrollment_id = e.enrollment_id
                          AND r.branch_id = %(branch_id)s
                        ORDER BY r.created_at DESC
                        LIMIT 1
                    ), 'NONE') AS reservation_status

                FROM enrollments e
                WHERE e.branch_id = %(branch_id)s
                  AND (
                      e.grade_level ILIKE %(grade_full)s
                      OR e.grade_level ILIKE %(grade_short)s
                  )
                  AND e.status = 'approved'
                ORDER BY e.student_name ASC
            """, {
                "branch_id":   branch_id,
                "grade_full":  grade_full,
                "grade_short": grade_short,
            })
            students = cur.fetchall() or []

            stats["total"] = len(students)
            for s in students:
                billing = (s["billing_status"] or "").upper()
                if billing == "CLEARED":
                    stats["cleared"] += 1
                elif billing in ("PENDING", "NO_BILL"):
                    stats["pending_bill"] += 1

                res = (s["reservation_status"] or "").upper()
                if res == "CLAIMED":
                    stats["claimed"] += 1
                elif res in ("PENDING", "RESERVED"):
                    stats["reserved"] += 1
                else:
                    stats["no_reservation"] += 1

            # ── Announcements for this grade ──
            cur.execute("""
                SELECT a.announcement_id, a.title, a.body,
                       a.created_at, u.username AS posted_by,
                       u.full_name, u.gender
                FROM teacher_announcements a
                JOIN users u ON u.user_id = a.teacher_user_id
                WHERE a.branch_id   = %(branch_id)s
                  AND (
                      a.grade_level ILIKE %(grade_full)s
                      OR a.grade_level ILIKE %(grade_short)s
                  )
                ORDER BY a.created_at DESC
            """, {
                "branch_id":   branch_id,
                "grade_full":  grade_full,
                "grade_short": grade_short,
            })
            raw_ann = cur.fetchall() or []

            # Build display name: "Ms. Joy Cruz" or "Mr. Juan dela Cruz"
            announcements = []
            for a in raw_ann:
                a = dict(a)
                prefix = ""
                if a.get("gender") == "female":
                    prefix = "Ms. "
                elif a.get("gender") == "male":
                    prefix = "Mr. "
                a["display_name"] = prefix + (a.get("full_name") or a.get("posted_by") or "Teacher")
                announcements.append(a)

        finally:
            cur.close()
            db.close()

    return render_template(
        "teacher_dashboard.html",
        students=students,
        stats=stats,
        teacher_grade=teacher_grade,
        selected_grade=selected_grade,
        grade_levels=GRADE_LEVELS,
        announcements=announcements,
        teacher_user_id=session.get("user_id"),
    )


# ── Save grade assignment ─────────────────────────────────
@teacher_bp.route("/teacher/set-grade", methods=["POST"])
def teacher_set_grade():
    if not _require_teacher():
        return redirect("/")

    user_id = session.get("user_id")
    grade   = (request.form.get("grade_level") or "").strip()

    if grade not in GRADE_LEVELS:
        flash("Invalid grade level.", "error")
        return redirect(url_for("teacher.teacher_dashboard"))

    db  = get_db_connection()
    cur = db.cursor()
    try:
        # Check if branch admin already assigned a grade — if so, block the change
        cur.execute("SELECT grade_level FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        existing_grade = (row[0] or "").strip() if row else ""

        if existing_grade:
            flash(f"Your grade level ({existing_grade}) is assigned by the Branch Admin and cannot be changed.", "warning")
            return redirect(url_for("teacher.teacher_dashboard") + f"?grade={existing_grade}")

        cur.execute("UPDATE users SET grade_level = %s WHERE user_id = %s",
                    (grade, user_id))
        db.commit()
        flash(f"Grade level set to {grade}.", "success")

    except Exception as e:
        db.rollback()
        flash(str(e), "error")
    finally:
        cur.close()
        db.close()

    return redirect(url_for("teacher.teacher_dashboard") + f"?grade={grade}")


# ── Post Announcement ─────────────────────────────────────
@teacher_bp.route("/teacher/announce", methods=["POST"])
def teacher_announce():
    if not _require_teacher():
        return redirect("/")

    user_id   = session.get("user_id")
    branch_id = session.get("branch_id")
    title     = (request.form.get("title") or "").strip()
    body      = (request.form.get("body")  or "").strip()
    grade     = (request.form.get("grade_level") or "").strip()

    # grade comes from hidden field (current selected_grade in dashboard)
    back_url = url_for("teacher.teacher_dashboard") + (f"?grade={grade}" if grade else "")

    if not title:
        flash("Announcement title is required.", "error")
        return redirect(back_url)

    if not grade:
        flash("Please select your grade level first.", "error")
        return redirect(url_for("teacher.teacher_dashboard"))

    db  = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO teacher_announcements
                (teacher_user_id, branch_id, grade_level, title, body)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, branch_id, grade, title, body or None))
        db.commit()
        flash("Announcement posted! Students in your class will see it.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Could not post announcement: {e}", "error")
    finally:
        cur.close()
        db.close()

    return redirect(back_url)


# ── Delete Announcement ───────────────────────────────────
@teacher_bp.route("/teacher/announce/<int:announcement_id>/delete", methods=["POST"])
def teacher_announce_delete(announcement_id):
    if not _require_teacher():
        return redirect("/")

    user_id = session.get("user_id")
    grade   = (request.form.get("grade_level") or "").strip()
    back_url = url_for("teacher.teacher_dashboard") + (f"?grade={grade}" if grade else "")

    db  = get_db_connection()
    cur = db.cursor()
    try:
        # Only allow deleting own announcements
        cur.execute("""
            DELETE FROM teacher_announcements
            WHERE announcement_id = %s AND teacher_user_id = %s
        """, (announcement_id, user_id))
        db.commit()
        if cur.rowcount:
            flash("Announcement deleted.", "success")
        else:
            flash("Announcement not found or not yours.", "error")
    except Exception as e:
        db.rollback()
        flash(str(e), "error")
    finally:
        cur.close()
        db.close()

    return redirect(back_url)


# ── Edit Announcement ─────────────────────────────────────
@teacher_bp.route("/teacher/announce/<int:announcement_id>/edit", methods=["POST"])
def teacher_announce_edit(announcement_id):
    if not _require_teacher():
        return redirect("/")

    user_id = session.get("user_id")
    grade   = (request.form.get("grade_level") or "").strip()
    title   = (request.form.get("title") or "").strip()
    body    = (request.form.get("body")  or "").strip()
    back_url = url_for("teacher.teacher_dashboard") + (f"?grade={grade}" if grade else "")

    if not title:
        flash("Title cannot be empty.", "error")
        return redirect(back_url)

    db  = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE teacher_announcements
               SET title = %s, body = %s
             WHERE announcement_id = %s AND teacher_user_id = %s
        """, (title, body or None, announcement_id, user_id))
        db.commit()
        if cur.rowcount:
            flash("Announcement updated.", "success")
        else:
            flash("Announcement not found or not yours.", "error")
    except Exception as e:
        db.rollback()
        flash(str(e), "error")
    finally:
        cur.close()
        db.close()

    return redirect(back_url)
