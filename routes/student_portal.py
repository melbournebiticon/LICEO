from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from db import get_db_connection
from werkzeug.security import generate_password_hash
import logging
import psycopg2.extras

# Setup logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

student_portal_bp = Blueprint("student_portal", __name__)

def _require_student():
    return session.get("role") == "student"


@student_portal_bp.route("/student/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        enrollment_id = request.form.get("enrollment_id", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        email = request.form.get("email", "").strip()

        # Validation
        if not enrollment_id.isdigit():
            flash("Enrollment ID must be a number", "error")
            return redirect(url_for("student_portal.register"))

        if not username:
            flash("Username is required", "error")
            return redirect(url_for("student_portal.register"))

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return redirect(url_for("student_portal.register"))

        enrollment_id_int = int(enrollment_id)

        db = get_db_connection()
        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Verify enrollment exists and is approved
            cursor.execute("""
                SELECT *
                FROM enrollments
                WHERE enrollment_id=%s AND status='approved'
            """, (enrollment_id_int,))
            enrollment = cursor.fetchone()

            if not enrollment:
                flash("Invalid enrollment ID or enrollment not yet approved", "error")
                return redirect(url_for("student_portal.register"))

            # Check if student account already exists for this enrollment
            cursor.execute("""
                SELECT 1 FROM student_accounts WHERE enrollment_id=%s
            """, (enrollment_id_int,))
            if cursor.fetchone():
                flash("Student account already exists for this enrollment", "warning")
                return redirect(url_for("student_portal.register"))

            # Check if username already taken
            cursor.execute("""
                SELECT 1 FROM student_accounts WHERE username=%s
            """, (username,))
            if cursor.fetchone():
                flash("Username already taken", "error")
                return redirect(url_for("student_portal.register"))

            # Hash password
            hashed_password = generate_password_hash(password)

            try:
                # Create student account
                cursor.execute("""
                    INSERT INTO student_accounts
                      (enrollment_id, username, password, email, is_active, require_password_change)
                    VALUES
                      (%s, %s, %s, %s, TRUE, TRUE)
                """, (enrollment_id_int, username, hashed_password, email))

                db.commit()
                flash("Student account created successfully! You can now login.", "success")
                return redirect("/login")

            except Exception as e:
                db.rollback()
                logger.error(f"Student registration failed: {str(e)}")
                flash("Registration failed. Please try again.", "error")
                return redirect(url_for("student_portal.register"))

        finally:
            cursor.close()
            db.close()

    return render_template("student_register.html")


@student_portal_bp.route("/student/dashboard")
def dashboard():
    if not _require_student():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Get student account info
        cursor.execute("""
            SELECT sa.*, e.*, br.branch_name, br.location
            FROM student_accounts sa
            JOIN enrollments e ON sa.enrollment_id = e.enrollment_id
            JOIN branches br ON e.branch_id = br.branch_id
            WHERE sa.account_id = %s
        """, (session.get("student_account_id"),))
        student = cursor.fetchone()

        if not student:
            flash("Student account not found", "error")
            return redirect("/")

        # Billing info
        cursor.execute("SELECT * FROM billing WHERE enrollment_id=%s", (student["enrollment_id"],))
        bill = cursor.fetchone()

        # Counts (use COALESCE for safety)
        cursor.execute("""
            SELECT COUNT(*) AS doc_count
            FROM enrollment_documents
            WHERE enrollment_id=%s
        """, (student["enrollment_id"],))
        doc_count = (cursor.fetchone() or {}).get("doc_count", 0)

        cursor.execute("""
            SELECT COUNT(*) AS book_count
            FROM enrollment_books
            WHERE enrollment_id=%s
        """, (student["enrollment_id"],))
        book_count = (cursor.fetchone() or {}).get("book_count", 0)

        cursor.execute("""
            SELECT COUNT(*) AS uniform_count
            FROM enrollment_uniforms
            WHERE enrollment_id=%s
        """, (student["enrollment_id"],))
        uniform_count = (cursor.fetchone() or {}).get("uniform_count", 0)

        return render_template(
            "student_dashboard.html",
            student=student,
            bill=bill,
            doc_count=doc_count,
            book_count=book_count,
            uniform_count=uniform_count
        )

    finally:
        cursor.close()
        db.close()


@student_portal_bp.route("/student/enrollment-status")
def enrollment_status():
    if not _require_student():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT sa.*, e.*, br.branch_name, br.location
            FROM student_accounts sa
            JOIN enrollments e ON sa.enrollment_id = e.enrollment_id
            JOIN branches br ON e.branch_id = br.branch_id
            WHERE sa.account_id = %s
        """, (session.get("student_account_id"),))
        enrollment = cursor.fetchone()

        if not enrollment:
            flash("Enrollment not found", "error")
            return redirect(url_for("student_portal.dashboard"))

        cursor.execute("SELECT * FROM enrollment_documents WHERE enrollment_id=%s", (enrollment["enrollment_id"],))
        documents = cursor.fetchall()

        cursor.execute("SELECT * FROM enrollment_books WHERE enrollment_id=%s", (enrollment["enrollment_id"],))
        books = cursor.fetchall()

        cursor.execute("SELECT * FROM enrollment_uniforms WHERE enrollment_id=%s", (enrollment["enrollment_id"],))
        uniforms = cursor.fetchall()

        return render_template(
            "student_enrollment_detail.html",
            enrollment=enrollment,
            documents=documents,
            books=books,
            uniforms=uniforms
        )

    finally:
        cursor.close()
        db.close()


@student_portal_bp.route("/student/billing")
def billing():
    if not _require_student():
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT sa.*, e.student_name, e.grade_level
            FROM student_accounts sa
            JOIN enrollments e ON sa.enrollment_id = e.enrollment_id
            WHERE sa.account_id = %s
        """, (session.get("student_account_id"),))
        student = cursor.fetchone()

        if not student:
            flash("Student account not found", "error")
            return redirect("/")

        cursor.execute("SELECT * FROM billing WHERE enrollment_id=%s", (student["enrollment_id"],))
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
            "student_billing_view.html",
            student=student,
            bill=bill,
            payments=payments
        )

    finally:
        cursor.close()
        db.close()


@student_portal_bp.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
