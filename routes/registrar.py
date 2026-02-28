from flask import Blueprint, render_template, session, redirect, request, flash
from db import get_db_connection
from werkzeug.security import generate_password_hash
import secrets
import string
import logging
import psycopg2.extras

# Setup logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

registrar_bp = Blueprint("registrar", __name__)

def generate_password(length=8):
    """Generate a cryptographically secure random password"""
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


@registrar_bp.route("/registrar", methods=["GET", "POST"])
def registrar_dashboard():
    if session.get("role") != "registrar":
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("Missing branch in session. Please login again.", "error")
        return redirect("/logout")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Handle Approve/Reject actions
        if request.method == "POST":
            enrollment_id = request.form.get("enrollment_id")
            action = request.form.get("action")  # expected: 'approved' or 'rejected'

            if not enrollment_id:
                flash("Missing enrollment ID", "error")
                return redirect("/registrar")

            if action not in ("approved", "rejected"):
                flash("Invalid action", "error")
                return redirect("/registrar")

            cursor.execute("""
                UPDATE enrollments
                SET status=%s
                WHERE enrollment_id=%s AND branch_id=%s
            """, (action, enrollment_id, branch_id))

            if cursor.rowcount == 0:
                db.rollback()
                flash("Enrollment not found for your branch.", "error")
                return redirect("/registrar")

            db.commit()

            # Fetch branch_enrollment_no for user-friendly message
            cursor.execute("""
                SELECT COALESCE(branch_enrollment_no, %s) AS display_no
                FROM enrollments WHERE enrollment_id=%s
            """, (enrollment_id, enrollment_id))
            disp_row = cursor.fetchone()
            display_no = disp_row["display_no"] if disp_row else enrollment_id

            if action == "approved":
                flash(f"Enrollment #{display_no} approved successfully", "success")
            else:
                flash(f"Enrollment #{display_no} rejected", "warning")

        # Fetch enrollments for this branch ordered by per-branch number
        cursor.execute("""
            SELECT *,
                   COALESCE(branch_enrollment_no, enrollment_id) AS display_no
            FROM enrollments
            WHERE branch_id=%s
            ORDER BY branch_enrollment_no ASC NULLS LAST, created_at DESC
        """, (branch_id,))
        enrollments = cursor.fetchall()

        # Attach documents + flags
        for enrollment in enrollments:
            eid = enrollment["enrollment_id"]

            # Documents (NO ORDER BY - safe)
            cursor.execute("""
                SELECT *
                FROM enrollment_documents
                WHERE enrollment_id=%s
            """, (eid,))
            enrollment["documents"] = cursor.fetchall()

            # Student account exists?
            cursor.execute("""
                SELECT 1
                FROM student_accounts
                WHERE enrollment_id=%s
            """, (eid,))
            enrollment["has_student_account"] = cursor.fetchone() is not None

            # Parent link exists? (student_id refers to enrollment_id in your current schema)
            cursor.execute("""
                SELECT ps.*, u.username
                FROM parent_student ps
                JOIN users u ON ps.parent_id = u.user_id
                WHERE ps.student_id = %s
            """, (eid,))
            parent_link = cursor.fetchone()
            enrollment["has_parent_account"] = parent_link is not None
            enrollment["parent_username"] = parent_link["username"] if parent_link else None

        return render_template("registrar_dashboard.html", enrollments=enrollments)

    except Exception as e:
        db.rollback()
        logger.error(f"Registrar dashboard error: {str(e)}")
        flash("Something went wrong in registrar dashboard. Please try again.", "error")
        return redirect("/registrar")

    finally:
        cursor.close()
        db.close()


@registrar_bp.route("/registrar/create-student-account/<int:enrollment_id>", methods=["POST"])
def create_student_account(enrollment_id):
    if session.get("role") != "registrar":
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("Missing branch in session. Please login again.", "error")
        return redirect("/logout")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Verify enrollment exists, approved, and belongs to this branch
        cursor.execute("""
            SELECT *
            FROM enrollments
            WHERE enrollment_id=%s AND branch_id=%s AND status='approved'
        """, (enrollment_id, branch_id))
        enrollment = cursor.fetchone()

        if not enrollment:
            flash("Enrollment not found or not approved", "error")
            return redirect("/registrar")

        # Student account already exists?
        cursor.execute("""
            SELECT 1 FROM student_accounts WHERE enrollment_id=%s
        """, (enrollment_id,))
        if cursor.fetchone():
            flash("Student account already exists for this enrollment", "warning")
            return redirect("/registrar")

        # Use branch_code + per-branch enrollment no for username, e.g. LDMAJ_0001
        cursor.execute("SELECT branch_code FROM branches WHERE branch_id=%s", (branch_id,))
        brow = cursor.fetchone()
        branch_code = (brow["branch_code"] if brow and brow.get("branch_code") else "").strip().upper()
        if not branch_code:
            branch_code = f"B{branch_id}"

        branch_no = enrollment.get("branch_enrollment_no") or enrollment_id
        try:
            num = int(branch_no)
            branch_no_str = f"{num:04d}"
        except Exception:
            branch_no_str = str(branch_no)

        username = f"{branch_code}_{branch_no_str}"
        # Default password: secure random, stored hashed; student will be forced to change on first login
        temp_password = generate_password()
        hashed_password = generate_password_hash(temp_password)

        try:
            cursor.execute("""
                INSERT INTO student_accounts
                  (enrollment_id, branch_id, username, password, is_active, require_password_change)
                VALUES
                  (%s, %s, %s, %s, TRUE, TRUE)
            """, (enrollment_id, enrollment["branch_id"], username, hashed_password))

            db.commit()

            return render_template(
                "account_created.html",
                account_type="student",
                student_name=enrollment.get("student_name"),
                enrollment_id=enrollment.get("branch_enrollment_no") or enrollment_id,
                username=username,
                password=temp_password
            )

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create student account: {str(e)}")
            flash("Failed to create student account. Please try again.", "error")
            return redirect("/registrar")

    except Exception as e:
        db.rollback()
        logger.error(f"Create student account error: {str(e)}")
        flash("Something went wrong while creating student account.", "error")
        return redirect("/registrar")

    finally:
        cursor.close()
        db.close()


@registrar_bp.route("/registrar/create-parent-account/<int:enrollment_id>", methods=["POST"])
def create_parent_account(enrollment_id):
    if session.get("role") != "registrar":
        return redirect("/")

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("Missing branch in session. Please login again.", "error")
        return redirect("/logout")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Verify enrollment exists, approved, and belongs to this branch
        cursor.execute("""
            SELECT *
            FROM enrollments
            WHERE enrollment_id=%s AND branch_id=%s AND status='approved'
        """, (enrollment_id, branch_id))
        enrollment = cursor.fetchone()

        if not enrollment:
            flash("Enrollment not found or not approved", "error")
            return redirect("/registrar")

        # Parent link already exists?
        cursor.execute("""
            SELECT ps.*, u.username
            FROM parent_student ps
            JOIN users u ON ps.parent_id = u.user_id
            WHERE ps.student_id = %s
        """, (enrollment_id,))
        existing_parent = cursor.fetchone()

        if existing_parent:
            flash(
                f"Parent account already exists for this enrollment (Username: {existing_parent['username']})",
                "warning"
            )
            return redirect("/registrar")

        # Use branch_code + running parent number per branch, e.g. LDMAJ_Parent1
        cursor.execute("SELECT branch_code FROM branches WHERE branch_id=%s", (branch_id,))
        brow = cursor.fetchone()
        branch_code = (brow["branch_code"] if brow and brow.get("branch_code") else "").strip().upper()
        if not branch_code:
            branch_code = f"B{branch_id}"

        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM users
            WHERE role='parent' AND branch_id=%s AND username ILIKE %s
        """, (branch_id, f"{branch_code}_Parent%"))
        prow = cursor.fetchone() or {}
        next_no = (prow.get("cnt") or 0) + 1

        username = f"{branch_code}_Parent{next_no}"
        # Default password: secure random, stored hashed
        temp_password = generate_password()
        hashed_password = generate_password_hash(temp_password)

        try:
            # Create parent user account, get user_id
            cursor.execute("""
                INSERT INTO users
                  (username, password, role, branch_id, require_password_change)
                VALUES
                  (%s, %s, 'parent', %s, TRUE)
                RETURNING user_id
            """, (username, hashed_password, branch_id))

            parent_id = cursor.fetchone()["user_id"]

            # Link parent to student (your current schema uses enrollment_id as student_id)
            cursor.execute("""
                INSERT INTO parent_student (parent_id, student_id, relationship)
                VALUES (%s, %s, 'guardian')
            """, (parent_id, enrollment_id))

            db.commit()

            return render_template(
                "account_created.html",
                account_type="parent",
                student_name=enrollment.get("student_name"),
                enrollment_id=enrollment.get("branch_enrollment_no") or enrollment_id,
                username=username,
                password=temp_password
            )

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create parent account: {str(e)}")
            flash("Failed to create parent account. Please try again.", "error")
            return redirect("/registrar")

    except Exception as e:
        db.rollback()
        logger.error(f"Create parent account error: {str(e)}")
        flash("Something went wrong while creating parent account.", "error")
        return redirect("/registrar")

    finally:
        cursor.close()
        db.close()


@registrar_bp.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
