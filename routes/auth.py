from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from db import get_db_connection
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2.extras

auth_bp = Blueprint("auth", __name__)

def check_password_change_required(user_data, is_student=False):
    """Check if user needs to change password on first login"""
    return user_data.get("require_password_change", 0) == 1


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        db = get_db_connection()
        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # ✅ 1) Check regular users (super_admin, branch_admin, registrar, cashier, parent, librarian, student if exists)
            cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = cursor.fetchone()

            if user:
                stored = user.get("password") or ""

                if stored.startswith(("scrypt:", "pbkdf2:", "$2b$", "$2a$")):
                    password_valid = check_password_hash(stored, password)
                else:
                    password_valid = (stored == password)

                if password_valid:
                    # ✅ prevent leftover sessions
                    session.clear()

                    session["user_id"] = user["user_id"]
                    session["role"] = user["role"]
                    session["branch_id"] = user.get("branch_id")

                    # Force password change if required
                    if check_password_change_required(user):
                        return redirect(url_for("auth.change_password"))

                    role = user["role"]
                    if role == "super_admin":
                        return redirect("/super-admin")
                    elif role == "branch_admin":
                        return redirect("/branch-admin")
                    elif role == "registrar":
                        return redirect("/registrar")
                    elif role == "cashier":
                        return redirect("/cashier")
                    elif role == "librarian":
                        return redirect("/librarian")
                    elif role == "parent":
                        return redirect("/parent/dashboard")
                    elif role == "student":
                        # ✅ if student exists in users table already, still set enrollment context if possible
                        # (optional: best effort)
                        cursor.execute("""
                            SELECT sa.enrollment_id, e.student_name, e.grade_level, e.branch_id
                            FROM student_accounts sa
                            JOIN enrollments e ON e.enrollment_id = sa.enrollment_id
                            WHERE sa.username = %s
                            LIMIT 1
                        """, (username,))
                        en = cursor.fetchone()
                        if en:
                            session["student_account_id"] = en.get("account_id")  # might be None; safe
                            session["enrollment_id"] = en.get("enrollment_id")
                            session["student_name"] = en.get("student_name")
                            session["student_grade_level"] = en.get("grade_level")
                            session["branch_id"] = en.get("branch_id") or session.get("branch_id")
                        return redirect("/student/dashboard")
                    else:
                        return redirect("/")

            # ✅ 2) Check student accounts (MAIN student login path)
            cursor.execute("""
                SELECT
                    sa.*,
                    e.branch_id AS enroll_branch_id,
                    e.student_name,
                    e.grade_level
                FROM student_accounts sa
                JOIN enrollments e ON sa.enrollment_id = e.enrollment_id
                WHERE sa.username=%s
                LIMIT 1
            """, (username,))
            student = cursor.fetchone()

            if student and student.get("is_active"):
                stored = student.get("password") or ""

                if stored.startswith(("scrypt:", "pbkdf2:", "$2b$", "$2a$")):
                    password_valid = check_password_hash(stored, password)
                else:
                    password_valid = (stored == password)

                if password_valid:
                    branch_id = student.get("enroll_branch_id") or student.get("branch_id")
                    enrollment_id = student.get("enrollment_id")

                    # ✅ ensure student has a matching row in users (reservations.student_user_id NOT NULL)
                    cursor.execute("""
                        SELECT user_id
                        FROM users
                        WHERE username=%s
                        LIMIT 1
                    """, (username,))
                    urow = cursor.fetchone()

                    if urow:
                        student_user_id = urow["user_id"]
                        cursor.execute("""
                            UPDATE users
                            SET role='student', branch_id=%s
                            WHERE user_id=%s
                        """, (branch_id, student_user_id))
                    else:
                        cursor.execute("""
                            INSERT INTO users (branch_id, username, password, role, require_password_change, last_password_change)
                            VALUES (%s, %s, %s, 'student', %s, NOW())
                            RETURNING user_id
                        """, (
                            branch_id,
                            username,
                            stored,
                            student.get("require_password_change", 0)
                        ))
                        student_user_id = cursor.fetchone()["user_id"]

                    db.commit()

                    # ✅ set sessions properly + enrollment-based references
                    session.clear()
                    session["user_id"] = student_user_id
                    session["student_account_id"] = student["account_id"]
                    session["role"] = "student"
                    session["branch_id"] = branch_id

                    # ✅ enrollment reference for filters (THIS IS WHAT YOU NEED)
                    session["enrollment_id"] = enrollment_id
                    session["student_name"] = student.get("student_name")
                    session["student_grade_level"] = student.get("grade_level")

                    if check_password_change_required(student, is_student=True):
                        return redirect(url_for("auth.change_password"))

                    return redirect("/student/dashboard")

            flash("Invalid username or password", "error")
            return redirect(url_for("auth.login"))

        except Exception as e:
            db.rollback()
            flash(f"Login error: {str(e)}", "error")
            return redirect(url_for("auth.login"))

        finally:
            cursor.close()
            db.close()

    return render_template("login.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "role" not in session:
        return redirect(url_for("auth.login"))

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        is_required = False

        if session["role"] == "student" and session.get("student_account_id"):
            cursor.execute(
                "SELECT require_password_change FROM student_accounts WHERE account_id=%s",
                (session.get("student_account_id"),)
            )
            account = cursor.fetchone()
            is_required = (account.get("require_password_change", 0) == 1) if account else False
        else:
            # All other roles (registrar, cashier, librarian, branch_admin, etc.) or student without student_account_id
            cursor.execute(
                "SELECT require_password_change FROM users WHERE user_id=%s",
                (session.get("user_id"),)
            )
            user = cursor.fetchone()
            # Treat None or missing column as 0; 1 = force change (same as registrar, cashier, librarian when created by Branch Admin)
            is_required = (user.get("require_password_change", 0) == 1) if user else False

        if request.method == "POST":
            new_password = (request.form.get("new_password") or "").strip()
            confirm_password = (request.form.get("confirm_password") or "").strip()

            if not new_password:
                flash("Please enter a new password.", "error")
                return redirect(url_for("auth.change_password"))

            if not is_required:
                current_password = (request.form.get("current_password") or "").strip()

                if session["role"] == "student" and session.get("student_account_id"):
                    cursor.execute(
                        "SELECT password FROM student_accounts WHERE account_id=%s",
                        (session.get("student_account_id"),)
                    )
                else:
                    cursor.execute(
                        "SELECT password FROM users WHERE user_id=%s",
                        (session.get("user_id"),)
                    )

                account_row = cursor.fetchone()

                if not account_row:
                    flash("Account not found", "error")
                    return redirect(url_for("auth.change_password"))

                stored = account_row.get("password") or ""
                if stored.startswith(("scrypt:", "pbkdf2:", "$2b$", "$2a$")):
                    current_password_valid = check_password_hash(stored, current_password)
                else:
                    current_password_valid = (stored == current_password)

                if not current_password_valid:
                    flash("Current password is incorrect", "error")
                    return redirect(url_for("auth.change_password"))

            if len(new_password) < 6:
                flash("New password must be at least 6 characters", "error")
                return redirect(url_for("auth.change_password"))

            if new_password != confirm_password:
                flash("New passwords do not match", "error")
                return redirect(url_for("auth.change_password"))

            hashed_password = generate_password_hash(new_password)

            try:
                if session["role"] == "student" and session.get("student_account_id"):
                    # Try full UPDATE first; if any fails (e.g. column missing), rollback and do password-only for both
                    try:
                        cursor.execute("""
                            UPDATE student_accounts
                            SET password=%s, require_password_change=0
                            WHERE account_id=%s
                        """, (hashed_password, session.get("student_account_id")))
                        cursor.execute("""
                            UPDATE users SET password=%s, require_password_change=0 WHERE user_id=%s
                        """, (hashed_password, session.get("user_id")))
                    except Exception:
                        db.rollback()
                        cursor.execute("""
                            UPDATE student_accounts SET password=%s WHERE account_id=%s
                        """, (hashed_password, session.get("student_account_id")))
                        cursor.execute("""
                            UPDATE users SET password=%s WHERE user_id=%s
                        """, (hashed_password, session.get("user_id")))

                else:
                    try:
                        cursor.execute("""
                            UPDATE users
                            SET password=%s, require_password_change=0
                            WHERE user_id=%s
                        """, (hashed_password, session.get("user_id")))
                    except Exception:
                        db.rollback()
                        cursor.execute("""
                            UPDATE users SET password=%s WHERE user_id=%s
                        """, (hashed_password, session.get("user_id")))

                db.commit()
                flash("Password changed successfully!", "success")

                role = session.get("role")
                if role == "super_admin":
                    return redirect("/super-admin")
                elif role == "branch_admin":
                    return redirect("/branch-admin")
                elif role == "registrar":
                    return redirect("/registrar")
                elif role == "cashier":
                    return redirect("/cashier")
                elif role == "librarian":
                    return redirect("/librarian")
                elif role == "parent":
                    return redirect("/parent/dashboard")
                elif role == "student":
                    return redirect("/student/dashboard")
                else:
                    return redirect("/")

            except Exception as e:
                db.rollback()
                err_msg = str(e).strip()
                if len(err_msg) > 120:
                    err_msg = err_msg[:120] + "..."
                flash(f"Failed to change password. Please try again. ({err_msg})", "error")
                return redirect(url_for("auth.change_password"))

        return render_template("change_password.html", required=is_required)

    finally:
        cursor.close()
        db.close()


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/")