from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from db import get_db_connection
from werkzeug.security import generate_password_hash
import logging
import psycopg2.extras

# Setup logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

parent_bp = Blueprint("parent", __name__)

def _require_parent():
    return session.get("role") == "parent"


@parent_bp.route("/parent/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not password:
            flash("Username and password are required", "error")
            return redirect(url_for("parent.register"))

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return redirect(url_for("parent.register"))

        hashed_password = generate_password_hash(password)

        db = get_db_connection()
        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            cursor.execute("SELECT 1 FROM users WHERE username=%s", (username,))
            if cursor.fetchone():
                flash("Username already exists", "error")
                return redirect(url_for("parent.register"))

            cursor.execute("""
                INSERT INTO users (username, password, role, branch_id, require_password_change)
                VALUES (%s, %s, 'parent', NULL, 1)
                RETURNING user_id
            """, (username, hashed_password))

            user_id = cursor.fetchone()["user_id"]
            db.commit()

            session["user_id"] = user_id
            session["role"] = "parent"
            session["branch_id"] = None

            flash("Registration successful! Set your new password, then you can link your children.", "success")
            return redirect(url_for("auth.change_password"))

        except Exception as e:
            db.rollback()
            logger.error(f"Parent registration failed: {str(e)}")
            flash("Registration failed. Please try again.", "error")
            return redirect(url_for("parent.register"))

        finally:
            cursor.close()
            db.close()

    return render_template("parent_register.html")


@parent_bp.route("/parent/dashboard")
def dashboard():
    if not _require_parent():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT ps.*, e.student_name, e.grade_level, e.status,
                   br.branch_name, br.location,
                   b.bill_id, b.total_amount, b.amount_paid, b.balance, b.status as bill_status,
                   e.enrollment_id
            FROM parent_student ps
            JOIN enrollments e ON ps.student_id = e.enrollment_id
            JOIN branches br ON e.branch_id = br.branch_id
            LEFT JOIN billing b ON e.enrollment_id = b.enrollment_id
            WHERE ps.parent_id = %s
            ORDER BY e.created_at DESC
        """, (session.get("user_id"),))

        children = cursor.fetchall()
        return render_template("parent_dashboard.html", children=children)

    finally:
        cursor.close()
        db.close()


@parent_bp.route("/parent/link-child", methods=["GET", "POST"])
def link_child():
    if not _require_parent():
        return redirect("/")

    if request.method == "POST":
        enrollment_id = request.form.get("enrollment_id", "").strip()
        relationship = request.form.get("relationship", "").strip()

        if not enrollment_id.isdigit():
            flash("Invalid enrollment ID", "error")
            return redirect(url_for("parent.link_child"))

        enrollment_id_int = int(enrollment_id)

        db = get_db_connection()
        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            cursor.execute("SELECT * FROM enrollments WHERE enrollment_id=%s", (enrollment_id_int,))
            enrollment = cursor.fetchone()

            if not enrollment:
                flash("Invalid enrollment ID", "error")
                return redirect(url_for("parent.link_child"))

            cursor.execute("""
                SELECT 1 FROM parent_student
                WHERE parent_id=%s AND student_id=%s
            """, (session.get("user_id"), enrollment_id_int))

            if cursor.fetchone():
                flash("This child is already linked to your account", "warning")
                return redirect(url_for("parent.dashboard"))

            cursor.execute("""
                INSERT INTO parent_student (parent_id, student_id, relationship)
                VALUES (%s, %s, %s)
            """, (session.get("user_id"), enrollment_id_int, relationship))

            db.commit()
            flash(f"Successfully linked {enrollment.get('student_name', 'child')} to your account", "success")
            return redirect(url_for("parent.dashboard"))

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to link child: {str(e)}")
            flash("Failed to link child. Please try again.", "error")
            return redirect(url_for("parent.link_child"))

        finally:
            cursor.close()
            db.close()

    return render_template("parent_link_child.html")


@parent_bp.route("/parent/child/<int:enrollment_id>")
def child_detail(enrollment_id):
    if not _require_parent():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT ps.*, e.*, br.branch_name, br.location
            FROM parent_student ps
            JOIN enrollments e ON ps.student_id = e.enrollment_id
            JOIN branches br ON e.branch_id = br.branch_id
            WHERE ps.parent_id=%s AND ps.student_id=%s
        """, (session.get("user_id"), enrollment_id))

        child = cursor.fetchone()
        if not child:
            flash("Child not found or access denied", "error")
            return redirect(url_for("parent.dashboard"))

        cursor.execute("SELECT * FROM enrollment_documents WHERE enrollment_id=%s", (enrollment_id,))
        documents = cursor.fetchall()

        cursor.execute("SELECT * FROM enrollment_books WHERE enrollment_id=%s", (enrollment_id,))
        books = cursor.fetchall()

        cursor.execute("SELECT * FROM enrollment_uniforms WHERE enrollment_id=%s", (enrollment_id,))
        uniforms = cursor.fetchall()

        return render_template(
            "parent_child_detail.html",
            child=child,
            documents=documents,
            books=books,
            uniforms=uniforms
        )

    finally:
        cursor.close()
        db.close()


@parent_bp.route("/parent/child/<int:enrollment_id>/bills")
def child_bills(enrollment_id):
    if not _require_parent():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT ps.*, e.student_name, e.grade_level, e.enrollment_id
            FROM parent_student ps
            JOIN enrollments e ON ps.student_id = e.enrollment_id
            WHERE ps.parent_id=%s AND ps.student_id=%s
        """, (session.get("user_id"), enrollment_id))

        child = cursor.fetchone()
        if not child:
            flash("Child not found or access denied", "error")
            return redirect(url_for("parent.dashboard"))

        cursor.execute("SELECT * FROM billing WHERE enrollment_id=%s", (enrollment_id,))
        bill = cursor.fetchone()

        payments = []
        if bill:
            cursor.execute("""
                SELECT p.*, u.username as received_by_name
                FROM payments p
                LEFT JOIN users u ON p.received_by = u.user_id
                WHERE p.bill_id=%s
                ORDER BY p.payment_date DESC
            """, (bill["bill_id"],))
            payments = cursor.fetchall()

        return render_template(
            "parent_child_bills.html",
            child=child,
            bill=bill,
            payments=payments
        )

    finally:
        cursor.close()
        db.close()


# ✅ Sidebar "Reserve Items" — smart redirect
@parent_bp.route("/parent/reserve")
def parent_reserve():
    if not _require_parent():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""
            SELECT e.enrollment_id, e.student_name, e.grade_level
            FROM parent_student ps
            JOIN enrollments e ON ps.student_id = e.enrollment_id
            WHERE ps.parent_id = %s
            ORDER BY e.student_name
        """, (session.get("user_id"),))
        children = cursor.fetchall()

        if not children:
            flash("No linked children found. Please link a child first.", "warning")
            return redirect(url_for("parent.link_child"))

        if len(children) == 1:
            # Only one child — go straight to reservation
            return redirect(url_for(
                "student.student_reservation",
                enrollment_id=children[0]["enrollment_id"]
            ))

        # Multiple children — show picker
        return render_template("parent_reserve_picker.html", children=children)

    finally:
        cursor.close()
        db.close()


# ✅ Parent → Reserve items for this child (redirect to student reservation page)
@parent_bp.route("/parent/child/<int:enrollment_id>/reserve")
def child_reserve(enrollment_id):
    if not _require_parent():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""
            SELECT 1
            FROM parent_student
            WHERE parent_id=%s AND student_id=%s
            LIMIT 1
        """, (session.get("user_id"), enrollment_id))

        if not cursor.fetchone():
            flash("Child not found or access denied", "error")
            return redirect(url_for("parent.dashboard"))

        # Redirect to the existing student reservation route, passing enrollment_id in query string
        return redirect(url_for("student.student_reservation", enrollment_id=enrollment_id))

    finally:
        cursor.close()
        db.close()


@parent_bp.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response